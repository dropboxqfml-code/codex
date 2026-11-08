using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Management;
using System.Runtime.InteropServices;
using System.Security;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.WmiInterop;

namespace ATIVBatteryGuard.FixedReadTrial
{
    internal enum FixedReadPreflightStatus
    {
        Ready, UnsupportedPlatform, DeviceMismatch, MetadataMismatch, TargetMismatch,
        ClassNotFound, NamespaceNotFound, AccessDenied, TimedOut, Unavailable
    }

    internal enum FixedReadPreflightStage
    {
        Platform, DeviceScope, ModelRead, BiosRead, MethodScope, Metadata,
        MethodEnumeration, TargetRead, InputParameters, BufferInstance, Ready
    }

    // Only fixed categories leave preflight. Observed device strings, object
    // paths, qualifier values and SDK exceptions are never report fields.
    internal sealed class FixedReadPreflightResult
    {
        internal FixedReadPreflightStatus Status { get; }
        internal FixedReadPreflightStage Stage { get; }
        internal FixedReadPreparedResources Resources { get; }
        internal bool IsReady => Status == FixedReadPreflightStatus.Ready && Resources != null;

        internal FixedReadPreflightResult(FixedReadPreflightStatus status,
            FixedReadPreflightStage stage, FixedReadPreparedResources resources = null)
        {
            Status = status;
            Stage = stage;
            Resources = resources;
        }
    }

    // The SDK borrows target and atomically claims the input pair later. The
    // host must call AcceptInputOwnership only after preparation actually ends,
    // and Dispose only after its invocation's actual outer close has ended.
    internal sealed class FixedReadPreparedResources : IDisposable
    {
        // Keep wrappers alive even if a preparation throws before reporting
        // whether it claimed inputs. Unknown ownership cannot become GC cleanup.
        private static readonly object retainedGate = new object();
        private static readonly HashSet<FixedReadPreparedResources> retained =
            new HashSet<FixedReadPreparedResources>();
        private readonly object gate = new object();
        private ManagementObject target;
        private ManagementBaseObject parameters, buffer;
        private bool? inputOwnershipTransferred;
        private bool disposed;

        internal WsabiWmiSingleReadPlan Plan { get; }
        internal WsabiWmiWindowsSdkBinding Binding { get; }

        internal FixedReadPreparedResources(WsabiWmiSingleReadPlan plan,
            WsabiWmiWindowsSdkBinding binding, ManagementObject target,
            ManagementBaseObject parameters, ManagementBaseObject buffer)
        {
            Plan = plan;
            Binding = binding;
            this.target = target;
            this.parameters = parameters;
            this.buffer = buffer;
            lock (retainedGate) retained.Add(this);
        }

        internal void AcceptInputOwnership(bool transferred)
        {
            lock (gate)
            {
                if (disposed || (inputOwnershipTransferred.HasValue &&
                    inputOwnershipTransferred.Value != transferred))
                    throw new InvalidOperationException("The prepared input ownership could not be resolved.");
                inputOwnershipTransferred = transferred;
            }
        }

        public void Dispose()
        {
            lock (gate)
            {
                if (disposed || !inputOwnershipTransferred.HasValue) return;
                disposed = true;
                // A transferred pair belongs to SDK cleanup, including a
                // reported cleanup failure. Do not dispose or retry it here.
                if (!inputOwnershipTransferred.Value)
                {
                    DisposeQuiet(parameters);
                    DisposeQuiet(buffer);
                }
                parameters = null;
                buffer = null;
                DisposeQuiet(target);
                target = null;
                lock (retainedGate) retained.Remove(this);
            }
        }

        private static void DisposeQuiet(ManagementBaseObject value)
        {
            try { if (value != null) value.Dispose(); } catch { }
        }
    }

    // This class performs fixed, local read-only preflight and creates empty
    // in-memory SDK objects. It supplies no command, payload, frame or dispatch.
    internal static class WindowsFixedReadPreflight
    {
        private const string ExpectedModel = "940X3G/930X3G";
        private const string ExpectedBios = "P05ACJ.128.140819.dg";
        private static readonly TimeSpan PreflightBudget = TimeSpan.FromSeconds(6);
        private static readonly TimeSpan QueryTimeout = TimeSpan.FromSeconds(2);

        internal static FixedReadPreflightResult Prepare()
        {
            var stage = FixedReadPreflightStage.Platform;
            // The executable's Windows 10 manifest is required for OSVersion.
            // Windows 11 also reports major 10; its builds are not this profile.
            Version version = Environment.OSVersion.Version;
            if (Environment.OSVersion.Platform != PlatformID.Win32NT ||
                !Environment.Is64BitOperatingSystem || !Environment.Is64BitProcess ||
                version.Major != 10 || version.Minor != 0 ||
                version.Build < 10240 || version.Build >= 22000)
                return Failure(FixedReadPreflightStatus.UnsupportedPlatform, stage);

            var elapsed = Stopwatch.StartNew();
            ManagementObject target = null;
            ManagementBaseObject parameters = null, buffer = null;
            try
            {
                stage = FixedReadPreflightStage.DeviceScope;
                var deviceScope = OpenScope(@"root\CIMV2", elapsed);
                stage = FixedReadPreflightStage.ModelRead;
                string model = ReadSingleString(deviceScope,
                    "SELECT Name FROM Win32_ComputerSystemProduct", "Name", elapsed);
                if (!MatchesDevice(model, ExpectedModel))
                    return Failure(FixedReadPreflightStatus.DeviceMismatch, stage);
                stage = FixedReadPreflightStage.BiosRead;
                string bios = ReadSingleString(deviceScope,
                    "SELECT SMBIOSBIOSVersion FROM Win32_BIOS", "SMBIOSBIOSVersion", elapsed);
                if (!MatchesDevice(bios, ExpectedBios))
                    return Failure(FixedReadPreflightStatus.DeviceMismatch, stage);

                stage = FixedReadPreflightStage.MethodScope;
                var scope = OpenScope(WsabiWmiContractMetadataPolicy.LocalNamespace, elapsed);
                stage = FixedReadPreflightStage.Metadata;
                var metadata = ReadMetadata(scope, elapsed);
                WsabiWmiMethodBinder binder;
                if (!WsabiWmiMethodBinder.TryCreate(metadata, out binder) || binder.ObservedMethodId != 1)
                    return Failure(FixedReadPreflightStatus.MetadataMismatch, stage);

                stage = FixedReadPreflightStage.MethodEnumeration;
                string relativePath = ReadSoleActivePath(scope, elapsed);
                if (relativePath == null)
                    return Failure(FixedReadPreflightStatus.TargetMismatch, stage);
                stage = FixedReadPreflightStage.TargetRead;
                target = new ManagementObject(scope, new ManagementPath(relativePath),
                    new ObjectGetOptions { Timeout = RemainingTimeout(elapsed) });
                target.Get();
                RequireTime(elapsed);
                if (!IsFixedInstance(target.Path) || ReadActive(target) != true)
                    return Failure(FixedReadPreflightStatus.TargetMismatch, stage);

                stage = FixedReadPreflightStage.InputParameters;
                parameters = target.GetMethodParameters(WsabiWmiContractMetadataPolicy.MethodName);
                RequireTime(elapsed);
                if (parameters == null || parameters.Properties.Count != 1 ||
                    ReadParameter(parameters, "inData").Binding != WsabiWmiParameterBinding.MatchesDataBuffer)
                    return Failure(FixedReadPreflightStatus.MetadataMismatch, stage);

                stage = FixedReadPreflightStage.BufferInstance;
                using (var bufferClass = OpenClass(scope, WsabiWmiContractMetadataPolicy.BufferClass, elapsed))
                {
                    bufferClass.Get();
                    RequireTime(elapsed);
                    if (!IsFixedClass(bufferClass, WsabiWmiContractMetadataPolicy.BufferClass) ||
                        !IsByteArray(ReadProperty(bufferClass, "Bytes")))
                        return Failure(FixedReadPreflightStatus.MetadataMismatch, stage);
                    // CreateInstance is local object construction. No Put,
                    // method invocation or request population is performed.
                    buffer = bufferClass.CreateInstance();
                }
                RequireTime(elapsed);
                if (buffer == null || !IsFixedClass(buffer, WsabiWmiContractMetadataPolicy.BufferClass) ||
                    !IsByteArray(ReadProperty(buffer, "Bytes")))
                    return Failure(FixedReadPreflightStatus.MetadataMismatch, stage);

                var facts = new WsabiWmiSingleReadTarget(model, bios, true,
                    WsabiWmiContractMetadataPolicy.LocalNamespace, WsabiWmiContractMetadataPolicy.MethodClass,
                    WsabiWmiContractMetadataPolicy.MethodName, true, 1, true, target);
                WsabiWmiSingleReadPlan plan;
                WsabiWmiSingleReadPlanIssue issue;
                if (!WsabiWmiSingleReadPlan.TryCreate(WsabiWmiReadTrialVariant.SingleReadWithoutHandshake,
                    facts, metadata, out plan, out issue))
                    return Failure(FixedReadPreflightStatus.MetadataMismatch, stage);
                var binding = new WsabiWmiWindowsSdkBinding(facts, target,
                    new ManagementOperationObserver(), parameters, buffer);
                RequireTime(elapsed);
                var resources = new FixedReadPreparedResources(plan, binding, target, parameters, buffer);
                // The host now owns the bundle, with later input ownership
                // unresolved until the fixed SDK preparation actually returns.
                target = null;
                parameters = null;
                buffer = null;
                return new FixedReadPreflightResult(FixedReadPreflightStatus.Ready,
                    FixedReadPreflightStage.Ready, resources);
            }
            catch (Exception exception) { return Failure(Classify(exception), stage); }
            finally
            {
                // No SDK invocation or ownership claim can occur in preflight.
                DisposeQuiet(parameters);
                DisposeQuiet(buffer);
                DisposeQuiet(target);
            }
        }

        private static WsabiWmiContractMetadataReport ReadMetadata(ManagementScope scope, Stopwatch elapsed)
        {
            WsabiWmiContractMethodMetadata methodMetadata;
            using (var schema = OpenClass(scope, WsabiWmiContractMetadataPolicy.MethodClass, elapsed))
            {
                schema.Get();
                RequireTime(elapsed);
                if (!IsFixedClass(schema, WsabiWmiContractMetadataPolicy.MethodClass))
                    throw FixedFailure();
                var guid = WsabiWmiContractMetadataPolicy.CompareGuid(ReadQualifier(schema.Qualifiers, "Guid"));
                MethodData method;
                try { method = schema.Methods[WsabiWmiContractMetadataPolicy.MethodName]; }
                catch (ManagementException exception) when (exception.ErrorCode == ManagementStatus.NotFound ||
                    exception.ErrorCode == ManagementStatus.InvalidMethod) { method = null; }
                RequireTime(elapsed);
                if (method == null)
                    return new WsabiWmiContractMetadataReport(new WsabiWmiContractMethodMetadata(
                        WsabiWmiMetadataStatus.Partial, guidMatch: guid, methodFound: false));
                uint? methodId = WsabiWmiContractMetadataPolicy.NormalizeMethodId(
                    ReadQualifier(method.Qualifiers, "WmiMethodId"));
                WsabiWmiParameterMetadata input, output;
                using (var definition = method.InParameters) input = ReadParameter(definition, "inData");
                RequireTime(elapsed);
                using (var definition = method.OutParameters) output = ReadParameter(definition, "outData");
                RequireTime(elapsed);
                methodMetadata = WsabiWmiContractMethodMetadata.FromParameters(
                    WsabiWmiMetadataStatus.Complete, guid, methodId, true, input, output);
            }
            using (var schema = OpenClass(scope, WsabiWmiContractMetadataPolicy.BufferClass, elapsed))
            {
                schema.Get();
                RequireTime(elapsed);
                bool matches = IsFixedClass(schema, WsabiWmiContractMetadataPolicy.BufferClass) &&
                    IsByteArray(ReadProperty(schema, "Bytes"));
                RequireTime(elapsed);
                return new WsabiWmiContractMetadataReport(methodMetadata,
                    new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, matches));
            }
        }

        private static string ReadSoleActivePath(ManagementScope scope, Stopwatch elapsed)
        {
            string relativePath = null;
            int count = 0;
            using (var searcher = new ManagementObjectSearcher(scope,
                new ObjectQuery("SELECT Active FROM WmiAcpiMethod"), Enumeration(elapsed, true)))
            using (var collection = searcher.Get())
            using (var rows = collection.GetEnumerator())
            {
                while (true)
                {
                    RequireTime(elapsed);
                    bool available = rows.MoveNext();
                    RequireTime(elapsed);
                    if (!available) break;
                    using (var row = rows.Current)
                    {
                        // One lookahead rejects multiple rows without reading
                        // a second target's properties or selecting among them.
                        if (++count > 1) return null;
                        var instance = row as ManagementObject;
                        if (instance == null || ReadActive(instance) != true || !IsFixedInstance(instance.Path))
                            return null;
                        relativePath = instance.Path.RelativePath;
                        if (string.IsNullOrEmpty(relativePath) || relativePath.Length > 4096) return null;
                        RequireTime(elapsed);
                    }
                }
            }
            RequireTime(elapsed);
            return count == 1 ? relativePath : null;
        }

        private static string ReadSingleString(ManagementScope scope, string query,
            string propertyName, Stopwatch elapsed)
        {
            string value = null;
            int count = 0;
            using (var searcher = new ManagementObjectSearcher(scope, new ObjectQuery(query), Enumeration(elapsed)))
            using (var collection = searcher.Get())
            using (var rows = collection.GetEnumerator())
            {
                while (true)
                {
                    RequireTime(elapsed);
                    bool available = rows.MoveNext();
                    RequireTime(elapsed);
                    if (!available) break;
                    using (var row = rows.Current)
                    {
                        if (++count > 1) throw FixedFailure();
                        PropertyData property = ReadProperty(row, propertyName);
                        if (property == null || property.Type != CimType.String || property.IsArray)
                            throw FixedFailure();
                        value = property.Value as string;
                        if (value == null || value.Length > 128) throw FixedFailure();
                        RequireTime(elapsed);
                    }
                }
            }
            RequireTime(elapsed);
            if (count != 1) throw FixedFailure();
            return value;
        }

        private static ManagementScope OpenScope(string name, Stopwatch elapsed)
        {
            var scope = new ManagementScope(@"\\.\" + name, new ConnectionOptions
            {
                Timeout = RemainingTimeout(elapsed), EnablePrivileges = false,
                Authentication = AuthenticationLevel.PacketPrivacy,
                Impersonation = ImpersonationLevel.Impersonate
            });
            scope.Connect();
            RequireTime(elapsed);
            return scope;
        }

        private static ManagementClass OpenClass(ManagementScope scope, string name, Stopwatch elapsed)
            => new ManagementClass(scope, new ManagementPath(name), new ObjectGetOptions
            {
                Timeout = RemainingTimeout(elapsed), UseAmendedQualifiers = false
            });

        private static EnumerationOptions Enumeration(Stopwatch elapsed, bool ensureLocatable = false)
            => new EnumerationOptions
            {
                Timeout = RemainingTimeout(elapsed), BlockSize = 1, Rewindable = false,
                ReturnImmediately = true, DirectRead = true, EnsureLocatable = ensureLocatable
            };

        private static bool IsFixedInstance(ManagementPath path)
            => path != null && path.IsInstance && string.Equals(path.ClassName,
                WsabiWmiContractMetadataPolicy.MethodClass, StringComparison.OrdinalIgnoreCase);

        private static bool IsFixedClass(ManagementBaseObject value, string className)
            => value != null && string.Equals(value.ClassPath.ClassName, className, StringComparison.OrdinalIgnoreCase);

        private static bool IsByteArray(PropertyData property)
            => property != null && property.Type == CimType.UInt8 && property.IsArray;

        private static bool? ReadActive(ManagementBaseObject value)
        {
            PropertyData property = ReadProperty(value, "Active");
            if (property == null || property.Type != CimType.Boolean || property.IsArray) return null;
            object active = property.Value;
            return active is bool ? (bool?)active : null;
        }

        private static PropertyData ReadProperty(ManagementBaseObject definition, string name)
        {
            if (definition == null) return null;
            try { return definition.Properties[name]; }
            catch (ManagementException exception) when (exception.ErrorCode == ManagementStatus.NotFound) { return null; }
        }

        private static object ReadQualifier(QualifierDataCollection qualifiers, string name)
        {
            if (qualifiers == null) return null;
            try { return qualifiers[name]?.Value; }
            catch (ManagementException exception) when (exception.ErrorCode == ManagementStatus.NotFound) { return null; }
        }

        private static WsabiWmiParameterMetadata ReadParameter(ManagementBaseObject definition, string name)
        {
            PropertyData property = ReadProperty(definition, name);
            if (property == null) return WsabiWmiContractMetadataPolicy.InspectParameter(false, false, null, null);
            if (property.Type != CimType.Object || property.IsArray)
                return WsabiWmiContractMetadataPolicy.InspectParameter(true, false, null, null);
            // Definitions and generated input shapes only, never their values.
            return WsabiWmiContractMetadataPolicy.InspectParameter(true, true,
                ReadQualifier(property.Qualifiers, "EmbeddedInstance"), ReadQualifier(property.Qualifiers, "CIMTYPE"));
        }

        private static bool MatchesDevice(string actual, string expected)
            => actual != null && actual.Length <= 128 &&
                string.Equals(actual.Trim(), expected, StringComparison.OrdinalIgnoreCase);

        private static TimeSpan RemainingTimeout(Stopwatch elapsed)
        {
            TimeSpan remaining = PreflightBudget - elapsed.Elapsed;
            if (remaining <= TimeSpan.Zero) throw new TimeoutException();
            return remaining < QueryTimeout ? remaining : QueryTimeout;
        }

        private static void RequireTime(Stopwatch elapsed)
        {
            if (elapsed.Elapsed >= PreflightBudget) throw new TimeoutException();
        }

        private static FixedReadPreflightStatus Classify(Exception exception)
        {
            var management = exception as ManagementException;
            if (management != null)
            {
                switch (management.ErrorCode)
                {
                    case ManagementStatus.InvalidClass: return FixedReadPreflightStatus.ClassNotFound;
                    case ManagementStatus.InvalidNamespace: return FixedReadPreflightStatus.NamespaceNotFound;
                    case ManagementStatus.AccessDenied: return FixedReadPreflightStatus.AccessDenied;
                    case ManagementStatus.Timedout: return FixedReadPreflightStatus.TimedOut;
                }
            }
            if (exception is UnauthorizedAccessException || exception is SecurityException)
                return FixedReadPreflightStatus.AccessDenied;
            if (exception is TimeoutException) return FixedReadPreflightStatus.TimedOut;
            var com = exception as COMException;
            if (com != null)
            {
                switch (unchecked((uint)com.ErrorCode))
                {
                    case 0x80070005:
                    case 0x80041003: return FixedReadPreflightStatus.AccessDenied;
                    case 0x80041010: return FixedReadPreflightStatus.ClassNotFound;
                    case 0x8004100E: return FixedReadPreflightStatus.NamespaceNotFound;
                    case 0x80043001:
                    case 0x800705B4: return FixedReadPreflightStatus.TimedOut;
                }
            }
            // A missing instance/property is not evidence of missing class.
            return FixedReadPreflightStatus.Unavailable;
        }

        private static FixedReadPreflightResult Failure(FixedReadPreflightStatus status,
            FixedReadPreflightStage stage) => new FixedReadPreflightResult(status, stage);

        private static InvalidOperationException FixedFailure()
            => new InvalidOperationException("The fixed read preflight could not complete.");

        private static void DisposeQuiet(ManagementBaseObject value)
        {
            try { if (value != null) value.Dispose(); } catch { }
        }
    }
}
