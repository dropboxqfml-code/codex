using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Management;
using System.Runtime.InteropServices;
using System.Security;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Diagnostics;

namespace ATIVBatteryGuard.WmiOneShotQuery
{
    // This separately approved experiment is never registered by the main app.
    // It has one fixed candidate and one SDK dispatch site. It provides no
    // synchronous invocation, retry, write command, DLL or driver fallback.
    internal sealed class WindowsOneShotBackend : IWsabiWmiOneShotBackend, IDisposable
    {
        private const string ExpectedModel = "940X3G/930X3G";
        private const string ExpectedBios = "P05ACJ.128.140819.dg";
        private const int MaximumDetachedBytes = 4096;
        private static readonly TimeSpan PreflightBudget = TimeSpan.FromSeconds(6);
        private static readonly TimeSpan QueryTimeout = TimeSpan.FromSeconds(2);
        private readonly object resourceGate = new object();
        private readonly Stopwatch elapsed = Stopwatch.StartNew();
        private ManagementObject target;
        private ManagementObject dataBuffer;
        private ManagementBaseObject input;
        private int preparationEntered;
        private int dispatchEntered;
        private bool prepared;
        private bool operationRunning;
        private bool disposed;

        public ProcessElevationState ReadElevation() => ProcessElevationProbe.Read();

        public WsabiWmiOneShotPreflight Prepare()
        {
            if (Interlocked.Exchange(ref preparationEntered, 1) != 0)
                return Failure(WsabiWmiMetadataStatus.Unavailable);
            if (Environment.OSVersion.Platform != PlatformID.Win32NT || !Environment.Is64BitProcess)
                return Failure(WsabiWmiMetadataStatus.UnsupportedPlatform);
            if (ReadElevation() != ProcessElevationState.Elevated)
                return Failure(WsabiWmiMetadataStatus.AccessDenied);
            lock (resourceGate)
            {
                if (disposed) return Failure(WsabiWmiMetadataStatus.Unavailable);
            }
            try
            {
                // The model and BIOS use exactly the fields of the earlier
                // device observation. No UUID, serial or account is queried.
                var deviceScope = OpenScope(@"root\CIMV2");
                string model = ReadSingleString(deviceScope,
                    "SELECT Name FROM Win32_ComputerSystemProduct", "Name");
                if (!MatchesFixedString(model, ExpectedModel)) return DeviceMismatch();
                string bios = ReadSingleString(deviceScope,
                    "SELECT SMBIOSBIOSVersion FROM Win32_BIOS", "SMBIOSBIOSVersion");
                if (!MatchesFixedString(bios, ExpectedBios)) return DeviceMismatch();
                RequirePreflightTime();

                WsabiWmiContractMetadataReport metadata = WsabiWmiContractMetadataProbe.Collect();
                RequirePreflightTime();
                WsabiWmiMethodBinder binder;
                if (!WsabiWmiMethodBinder.TryCreate(metadata, out binder) ||
                    metadata.MethodMetadata.MethodId != WsabiWmiOneShotPolicy.RequiredMethodId)
                    return new WsabiWmiOneShotPreflight(WsabiWmiMetadataStatus.Complete, true,
                        metadata, false, 0, null, false);

                var scope = OpenScope(WsabiWmiContractMetadataPolicy.LocalNamespace);
                string relativePath = null;
                bool? active = null;
                int count = 0;
                bool complete = false;
                using (var searcher = new ManagementObjectSearcher(scope,
                    new ObjectQuery("SELECT Active FROM WmiAcpiMethod"), CreateEnumerationOptions()))
                using (var collection = searcher.Get())
                using (var rows = collection.GetEnumerator())
                {
                    while (rows.MoveNext())
                    {
                        using (var row = rows.Current as ManagementObject)
                        {
                            if (row == null) throw FixedFailure();
                            RequirePreflightTime();
                            count++;
                            if (count == 2) break;
                            active = ReadActive(row);
                            ManagementPath path = row.Path;
                            if (!path.IsInstance || !string.Equals(path.ClassName,
                                WsabiWmiContractMetadataPolicy.MethodClass, StringComparison.OrdinalIgnoreCase))
                                throw FixedFailure();
                            relativePath = path.RelativePath;
                            if (string.IsNullOrEmpty(relativePath) || relativePath.Length > 4096)
                                throw FixedFailure();
                        }
                    }
                    complete = count < 2;
                }
                RequirePreflightTime();
                if (!complete || count != 1 || active != true)
                    return new WsabiWmiOneShotPreflight(WsabiWmiMetadataStatus.Complete,
                        true, metadata, complete, count, active, false);

                lock (resourceGate)
                {
                    if (disposed) throw FixedFailure();
                    // The observed relative key stays private. The endpoint is
                    // always the fixed local scope and fixed class, never a
                    // guessed key, a version-class row or a remote path.
                    target = new ManagementObject(scope, new ManagementPath(relativePath),
                        new ObjectGetOptions { Timeout = RemainingTimeout() });
                    target.Get();
                    RequirePreflightTime();
                    if (ReadActive(target) != true) throw FixedFailure();
                    input = target.GetMethodParameters(WsabiWmiContractMetadataPolicy.MethodName);
                    if (input == null || input.Properties.Count != 1) throw FixedFailure();
                    PropertyData parameter = input.Properties["inData"];
                    if (parameter == null || parameter.Type != CimType.Object || parameter.IsArray ||
                        WsabiWmiContractMetadataPolicy.NormalizeCimType(
                            parameter.Qualifiers["CIMTYPE"].Value) != WsabiWmiQualifierMatch.MatchesDataBuffer)
                        throw FixedFailure();
                    using (var bufferClass = new ManagementClass(scope,
                        new ManagementPath(WsabiWmiContractMetadataPolicy.BufferClass),
                        new ObjectGetOptions { Timeout = RemainingTimeout() }))
                    {
                        bufferClass.Get();
                        // CreateInstance only creates an in-memory object.
                        // No ManagementObject.Put or registration is performed.
                        dataBuffer = bufferClass.CreateInstance();
                    }
                    if (dataBuffer == null) throw FixedFailure();
                    RequirePreflightTime();
                    prepared = true;
                }
                return new WsabiWmiOneShotPreflight(WsabiWmiMetadataStatus.Complete,
                    true, metadata, true, 1, true, true);
            }
            catch (Exception exception)
            {
                lock (resourceGate) { DisposePrepared(); }
                return Failure(Classify(exception));
            }
        }

        public async Task<WsabiWmiMethodSnapshot> ExchangeAsync(WsabiWmiMethodRequest request,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (!WsabiWmiOneShotPolicy.IsApprovedRequest(request) ||
                ReadElevation() != ProcessElevationState.Elevated) throw FixedFailure();

            ManagementObject selectedTarget;
            ManagementBaseObject selectedInput;
            lock (resourceGate)
            {
                if (disposed || !prepared || operationRunning) throw FixedFailure();
                RequirePreflightTime();
                // These setters affect only the two in-memory parameter
                // objects, not a WMI repository object or firmware setting.
                dataBuffer["Bytes"] = request.Frame;
                input["inData"] = dataBuffer;
                RequirePreflightTime();
                if (Interlocked.Exchange(ref dispatchEntered, 1) != 0) throw FixedFailure();
                selectedTarget = target;
                selectedInput = input;
                operationRunning = true;
            }

            var completion = new TaskCompletionSource<WsabiWmiMethodSnapshot>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            var observer = new ManagementOperationObserver();
            var capture = new OneShotResultCapture<ManagementBaseObject>();
            ObjectReadyEventHandler onObject = (sender, args) =>
            {
                try { capture.Accept(args.NewObject); }
                catch { capture.Invalidate(); }
            };
            CompletedEventHandler onCompleted = (sender, args) =>
            {
                try
                {
                    // Completion status is not the discarded immediate HR.
                    // Capture closes once and disposes its chosen object before
                    // the Task can publish a detached snapshot.
                    WsabiWmiMethodSnapshot snapshot;
                    if (capture.TryComplete((int)args.Status, ReadDetachedOutput,
                        cancellationToken, out snapshot)) completion.TrySetResult(snapshot);
                }
                catch (OperationCanceledException) { completion.TrySetCanceled(); }
                catch { completion.TrySetException(FixedFailure()); }
            };
            observer.ObjectReady += onObject;
            observer.Completed += onCompleted;
            try
            {
                cancellationToken.ThrowIfCancellationRequested();
                RequirePreflightTime();
                // Exactly one SDK invocation site. There is no retry and no
                // synchronous method overload that hides positive HR values.
                selectedTarget.InvokeMethod(observer, WsabiWmiContractMetadataPolicy.MethodName,
                    selectedInput, new InvokeMethodOptions());
                // No timeout/cancellation pretends that provider work stopped.
                // The separate worker's own watchdog and parent impose 10 s.
                return await completion.Task.ConfigureAwait(false);
            }
            catch (OperationCanceledException) { throw new OperationCanceledException(cancellationToken); }
            catch { throw FixedFailure(); }
            finally
            {
                observer.ObjectReady -= onObject;
                observer.Completed -= onCompleted;
                capture.Dispose();
                lock (resourceGate)
                {
                    operationRunning = false;
                    if (disposed) DisposePrepared();
                }
            }
        }

        private static object ReadDetachedOutput(ManagementBaseObject result)
        {
            var outer = new Dictionary<string, object>(StringComparer.Ordinal);
            PropertyData output = ReadProperty(result, "outData");
            if (output == null) return new ReadOnlyDictionary<string, object>(outer);
            if (output.Type != CimType.Object || output.IsArray)
            {
                outer["outData"] = new object();
                return new ReadOnlyDictionary<string, object>(outer);
            }
            using (var embedded = output.Value as ManagementBaseObject)
            {
                if (embedded == null || !string.Equals(embedded.ClassPath.ClassName,
                    WsabiWmiContractMetadataPolicy.BufferClass, StringComparison.OrdinalIgnoreCase))
                    outer["outData"] = new object();
                else
                {
                    var bytes = new Dictionary<string, object>(StringComparer.Ordinal);
                    PropertyData property = ReadProperty(embedded, "Bytes");
                    if (property != null)
                    {
                        if (property.Type != CimType.UInt8 || !property.IsArray) bytes["Bytes"] = new object();
                        else
                        {
                            object value = property.Value;
                            var array = value as Array;
                            if (value == null) bytes["Bytes"] = null;
                            else if (array == null || value.GetType().GetElementType() != typeof(byte))
                                bytes["Bytes"] = new object();
                            else
                            {
                                if (array.Length > MaximumDetachedBytes) throw FixedFailure();
                                bytes["Bytes"] = array.Clone();
                            }
                        }
                    }
                    outer["outData"] = new ReadOnlyDictionary<string, object>(bytes);
                }
            }
            return new ReadOnlyDictionary<string, object>(outer);
        }

        private string ReadSingleString(ManagementScope scope, string query, string propertyName)
        {
            string result = null;
            int count = 0;
            using (var searcher = new ManagementObjectSearcher(scope, new ObjectQuery(query), CreateEnumerationOptions()))
            using (var collection = searcher.Get())
            using (var rows = collection.GetEnumerator())
            {
                while (rows.MoveNext())
                {
                    using (var row = rows.Current)
                    {
                        RequirePreflightTime();
                        if (++count > 1) throw FixedFailure();
                        PropertyData property = ReadProperty(row, propertyName);
                        if (property == null || property.Type != CimType.String || property.IsArray) throw FixedFailure();
                        result = property.Value as string;
                        if (result == null || result.Length > 128) throw FixedFailure();
                    }
                }
            }
            if (count != 1) throw FixedFailure();
            RequirePreflightTime();
            return result;
        }

        private ManagementScope OpenScope(string name)
        {
            var scope = new ManagementScope(@"\\.\" + name, new ConnectionOptions
            {
                Timeout = RemainingTimeout(), EnablePrivileges = false,
                Authentication = AuthenticationLevel.PacketPrivacy,
                Impersonation = ImpersonationLevel.Impersonate
            });
            scope.Connect();
            RequirePreflightTime();
            return scope;
        }

        private EnumerationOptions CreateEnumerationOptions() => new EnumerationOptions
        {
            Timeout = RemainingTimeout(), BlockSize = 1, Rewindable = false,
            ReturnImmediately = true, DirectRead = true
        };

        private TimeSpan RemainingTimeout()
        {
            TimeSpan remaining = PreflightBudget - elapsed.Elapsed;
            if (remaining <= TimeSpan.Zero) throw new TimeoutException();
            return remaining < QueryTimeout ? remaining : QueryTimeout;
        }

        private void RequirePreflightTime()
        {
            if (elapsed.Elapsed >= PreflightBudget) throw new TimeoutException();
        }

        private static bool MatchesFixedString(string actual, string expected)
            => actual != null && actual.Length <= 128 &&
                string.Equals(actual.Trim(), expected, StringComparison.OrdinalIgnoreCase);

        private static bool? ReadActive(ManagementBaseObject value)
        {
            PropertyData property = ReadProperty(value, "Active");
            if (property == null || property.Type != CimType.Boolean || property.IsArray) return null;
            object active = property.Value;
            return active is bool ? (bool?)active : null;
        }

        private static PropertyData ReadProperty(ManagementBaseObject value, string name)
        {
            try { return value.Properties[name]; }
            catch (ManagementException exception) when (exception.ErrorCode == ManagementStatus.NotFound) { return null; }
        }

        private static WsabiWmiOneShotPreflight DeviceMismatch()
            => new WsabiWmiOneShotPreflight(WsabiWmiMetadataStatus.Complete, false, null, false, 0, null, false);

        private static WsabiWmiOneShotPreflight Failure(WsabiWmiMetadataStatus status)
            => new WsabiWmiOneShotPreflight(status, null, null, false, 0, null, false);

        private static WsabiWmiMetadataStatus Classify(Exception exception)
        {
            var management = exception as ManagementException;
            if (management != null)
            {
                switch (management.ErrorCode)
                {
                    case ManagementStatus.AccessDenied: return WsabiWmiMetadataStatus.AccessDenied;
                    case ManagementStatus.Timedout: return WsabiWmiMetadataStatus.TimedOut;
                    case ManagementStatus.InvalidClass: return WsabiWmiMetadataStatus.ClassNotFound;
                    // NotFound can identify a vanished instance or missing
                    // qualifier, so do not misreport it as class absence.
                    case ManagementStatus.NotFound: return WsabiWmiMetadataStatus.Unavailable;
                    case ManagementStatus.InvalidNamespace: return WsabiWmiMetadataStatus.NamespaceNotFound;
                }
            }
            if (exception is TimeoutException) return WsabiWmiMetadataStatus.TimedOut;
            if (exception is UnauthorizedAccessException || exception is SecurityException)
                return WsabiWmiMetadataStatus.AccessDenied;
            var com = exception as COMException;
            if (com != null && (unchecked((uint)com.ErrorCode) == 0x80070005 ||
                unchecked((uint)com.ErrorCode) == 0x80041003)) return WsabiWmiMetadataStatus.AccessDenied;
            return WsabiWmiMetadataStatus.Unavailable;
        }

        private static InvalidOperationException FixedFailure()
            => new InvalidOperationException("The fixed experiment could not complete.");

        private static void DisposeQuiet(IDisposable value)
        {
            try { if (value != null) value.Dispose(); } catch { }
        }

        private void DisposePrepared()
        {
            prepared = false;
            DisposeQuiet(input); input = null;
            DisposeQuiet(dataBuffer); dataBuffer = null;
            DisposeQuiet(target); target = null;
        }

        public void Dispose()
        {
            lock (resourceGate)
            {
                disposed = true;
                if (!operationRunning) DisposePrepared();
            }
        }
    }
}
