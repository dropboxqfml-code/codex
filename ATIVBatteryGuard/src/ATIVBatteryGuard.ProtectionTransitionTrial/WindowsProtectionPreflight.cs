using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Management;
using System.Runtime.InteropServices;
using System.Security;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.FixedReadTrial;

namespace ATIVBatteryGuard.ProtectionTransitionTrial
{
    internal enum ProtectionPreflightStatus
    {
        Ready, UnsupportedPlatform, DeviceMismatch, MetadataMismatch, TargetMismatch,
        ClassNotFound, NamespaceNotFound, AccessDenied, TimedOut, Unavailable
    }
    internal enum ProtectionPreflightStage
    {
        Platform, DeviceScope, ModelRead, BiosRead, MethodScope, Metadata,
        MethodEnumeration, TargetRead, Ready
    }
    internal sealed class ProtectionPreflightResult
    {
        internal ProtectionPreflightStatus Status { get; }
        internal ProtectionPreflightStage Stage { get; }
        internal ProtectionPreparedTarget Resources { get; }
        internal FixedReadPreflightSubstep Substep { get; }
        internal FixedReadPreflightError Error { get; }
        internal bool CleanupFailed { get; }
        internal bool IsReady => Status == ProtectionPreflightStatus.Ready && Resources != null;
        internal ProtectionPreflightResult(ProtectionPreflightStatus status,
            ProtectionPreflightStage stage, ProtectionPreparedTarget resources = null)
            : this(status, stage, resources, FixedReadPreflightSubstep.None, FixedReadPreflightError.None, false) { }
        internal ProtectionPreflightResult(ProtectionPreflightStatus status, ProtectionPreflightStage stage,
            ProtectionPreparedTarget resources, FixedReadPreflightSubstep substep, FixedReadPreflightError error, bool cleanupFailed)
        { Status = status; Stage = stage; Resources = resources; Substep = substep; Error = error; CleanupFailed = cleanupFailed; }
    }

    // The procedure borrows this sole target. No input or observer exists here.
    // Retain it through preparation and actual close, including uncertain exits.
    internal sealed class ProtectionPreparedTarget
    {
        private static readonly object retainedGate = new object();
        private static readonly HashSet<ProtectionPreparedTarget> retained = new HashSet<ProtectionPreparedTarget>();
        private readonly object gate = new object();
        private ManagementObject target;
        private bool closeAttempted, closeComplete;
        internal ManagementObject Target => target;
        internal WsabiWmiSingleReadTarget Facts { get; }
        internal WsabiWmiContractMetadataReport Metadata { get; }
        internal ProtectionPreparedTarget(ManagementObject target, WsabiWmiSingleReadTarget facts, WsabiWmiContractMetadataReport metadata)
        {
            this.target = target; Facts = facts; Metadata = metadata;
            lock (retainedGate) retained.Add(this);
        }
        internal bool CloseAfterActualCompletion()
        {
            lock (gate)
            {
                if (closeAttempted) return closeComplete;
                closeAttempted = true;
                try { target.Dispose(); }
                catch { return false; }
                target = null; closeComplete = true;
                lock (retainedGate) retained.Remove(this);
                return true;
            }
        }
    }

    // Fixed, local, read-only metadata preflight only. Stage SDK parameters,
    // data buffers and observers are deliberately created lazily by the leaf.
    internal static class WindowsProtectionPreflight
    {
        private const string ExpectedModel = "940X3G/930X3G";
        private const string ExpectedBios = "P05ACJ.128.140819.dg";
        private static readonly TimeSpan PreflightBudget = TimeSpan.FromSeconds(6);
        private static readonly TimeSpan QueryTimeout = TimeSpan.FromSeconds(2);

        internal static ProtectionPreflightResult Prepare()
        {
            var stage = ProtectionPreflightStage.Platform;
            Version version = Environment.OSVersion.Version;
            if (Environment.OSVersion.Platform != PlatformID.Win32NT ||
                !Environment.Is64BitOperatingSystem || !Environment.Is64BitProcess ||
                version.Major != 10 || version.Minor != 0 || version.Build < 10240 || version.Build >= 22000)
                return Failure(ProtectionPreflightStatus.UnsupportedPlatform, stage);
            var elapsed = Stopwatch.StartNew();
            var enumerationTrace = new FixedReadPreflightTracker(ClassifyTraceError);
            ManagementObject target = null;
            try
            {
                stage = ProtectionPreflightStage.DeviceScope;
                var deviceScope = OpenScope(@"root\CIMV2", elapsed);
                stage = ProtectionPreflightStage.ModelRead;
                string model = ReadSingleString(deviceScope, "SELECT Name FROM Win32_ComputerSystemProduct", "Name", elapsed);
                if (!MatchesDevice(model, ExpectedModel)) return Failure(ProtectionPreflightStatus.DeviceMismatch, stage);
                stage = ProtectionPreflightStage.BiosRead;
                string bios = ReadSingleString(deviceScope, "SELECT SMBIOSBIOSVersion FROM Win32_BIOS", "SMBIOSBIOSVersion", elapsed);
                if (!MatchesDevice(bios, ExpectedBios)) return Failure(ProtectionPreflightStatus.DeviceMismatch, stage);
                stage = ProtectionPreflightStage.MethodScope;
                var scope = OpenScope(WsabiWmiContractMetadataPolicy.LocalNamespace, elapsed);
                stage = ProtectionPreflightStage.Metadata;
                var metadata = ReadMetadata(scope, elapsed);
                WsabiWmiMethodBinder binder;
                if (!WsabiWmiMethodBinder.TryCreate(metadata, out binder) || binder.ObservedMethodId != 1)
                    return Failure(ProtectionPreflightStatus.MetadataMismatch, stage);
                stage = ProtectionPreflightStage.MethodEnumeration;
                string relativePath = ReadSoleActivePath(scope, elapsed, enumerationTrace);
                if (enumerationTrace.HasFailure) return Failure(StatusFor(enumerationTrace.Error), stage, enumerationTrace);
                if (relativePath == null) return Failure(ProtectionPreflightStatus.TargetMismatch, stage, enumerationTrace);
                stage = ProtectionPreflightStage.TargetRead;
                target = new ManagementObject(scope, new ManagementPath(relativePath), new ObjectGetOptions { Timeout = RemainingTimeout(elapsed) });
                target.Get(); RequireTime(elapsed);
                if (!IsFixedInstance(target.Path) || ReadActive(target) != true)
                    return Failure(ProtectionPreflightStatus.TargetMismatch, stage);
                var facts = new WsabiWmiSingleReadTarget(model, bios, true,
                    WsabiWmiContractMetadataPolicy.LocalNamespace, WsabiWmiContractMetadataPolicy.MethodClass,
                    WsabiWmiContractMetadataPolicy.MethodName, true, 1, true, target);
                var resources = new ProtectionPreparedTarget(target, facts, metadata);
                target = null;
                return new ProtectionPreflightResult(ProtectionPreflightStatus.Ready, ProtectionPreflightStage.Ready, resources);
            }
            catch (Exception error) { return Failure(Classify(error), stage, enumerationTrace); }
            finally { DisposeQuiet(target); }
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

        private static string ReadSoleActivePath(ManagementScope scope, Stopwatch elapsed,
            FixedReadPreflightTracker trace)
        {
            string relativePath = null;
            int count = 0;
            ManagementObjectSearcher searcher = null;
            ManagementObjectCollection collection = null;
            ManagementObjectCollection.ManagementObjectEnumerator rows = null;
            try
            {
                searcher = trace.Run(FixedReadPreflightSubstep.QueryCreate, () =>
                    new ManagementObjectSearcher(scope,
                        new ObjectQuery("SELECT Active FROM WmiAcpiMethod"), Enumeration(elapsed, true)));
                collection = trace.Run(FixedReadPreflightSubstep.QueryGet, () => searcher.Get());
                rows = trace.Run(FixedReadPreflightSubstep.EnumeratorCreate, () => collection.GetEnumerator());
                while (true)
                {
                    trace.Run(FixedReadPreflightSubstep.BudgetCheck, () => RequireTime(elapsed));
                    bool available = trace.Run(FixedReadPreflightSubstep.MoveNext, () => rows.MoveNext());
                    trace.Run(FixedReadPreflightSubstep.BudgetCheck, () => RequireTime(elapsed));
                    if (!available) break;
                    ManagementBaseObject row = null;
                    try
                    {
                        row = trace.Run(FixedReadPreflightSubstep.Current, () => rows.Current);
                        // One lookahead rejects multiple rows without reading
                        // a second target's properties or selecting among them.
                        if (++count > 1) return null;
                        var instance = row as ManagementObject;
                        if (instance == null) return null;
                        var active = trace.Run(FixedReadPreflightSubstep.ActivePropertyRead,
                            () => ReadProperty(instance, "Active"));
                        if (active == null) return null;
                        if (trace.Run(FixedReadPreflightSubstep.ActiveTypeRead, () => active.Type) != CimType.Boolean ||
                            trace.Run(FixedReadPreflightSubstep.ActiveArrayRead, () => active.IsArray)) return null;
                        object activeValue = trace.Run(FixedReadPreflightSubstep.ActiveValueRead, () => active.Value);
                        if (!(activeValue is bool) || !(bool)activeValue) return null;
                        var path = trace.Run(FixedReadPreflightSubstep.InstancePathRead, () => instance.Path);
                        if (path == null || !trace.Run(FixedReadPreflightSubstep.PathKindRead, () => path.IsInstance) ||
                            !string.Equals(trace.Run(FixedReadPreflightSubstep.PathClassRead, () => path.ClassName),
                                WsabiWmiContractMetadataPolicy.MethodClass, StringComparison.OrdinalIgnoreCase)) return null;
                        // Preserve the existing second Path access. Neither
                        // getter's result is stored in the detached trace.
                        var relativePathObject = trace.Run(FixedReadPreflightSubstep.RelativePathObjectRead,
                            () => instance.Path);
                        relativePath = trace.Run(FixedReadPreflightSubstep.RelativePathRead,
                            () => relativePathObject.RelativePath);
                        if (string.IsNullOrEmpty(relativePath) || relativePath.Length > 4096) return null;
                        trace.Run(FixedReadPreflightSubstep.BudgetCheck, () => RequireTime(elapsed));
                    }
                    finally
                    {
                        if (row != null) trace.DisposeTracked(FixedReadPreflightSubstep.RowDispose, () => row.Dispose());
                    }
                    // A cleanup-only failure used to leave through using's
                    // exception. Stop before another read, without losing it.
                    if (trace.HasFailure) return null;
                }
            }
            finally
            {
                if (rows != null) trace.DisposeTracked(FixedReadPreflightSubstep.EnumeratorDispose, () => rows.Dispose());
                if (collection != null) trace.DisposeTracked(FixedReadPreflightSubstep.CollectionDispose, () => collection.Dispose());
                if (searcher != null) trace.DisposeTracked(FixedReadPreflightSubstep.SearcherDispose, () => searcher.Dispose());
            }
            if (trace.HasFailure) return null;
            trace.Run(FixedReadPreflightSubstep.BudgetCheck, () => RequireTime(elapsed));
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

        private static ProtectionPreflightStatus Classify(Exception exception)
        {
            var management = exception as ManagementException;
            if (management != null)
            {
                switch (management.ErrorCode)
                {
                    case ManagementStatus.InvalidClass: return ProtectionPreflightStatus.ClassNotFound;
                    case ManagementStatus.InvalidNamespace: return ProtectionPreflightStatus.NamespaceNotFound;
                    case ManagementStatus.AccessDenied: return ProtectionPreflightStatus.AccessDenied;
                    case ManagementStatus.Timedout: return ProtectionPreflightStatus.TimedOut;
                }
            }
            if (exception is UnauthorizedAccessException || exception is SecurityException)
                return ProtectionPreflightStatus.AccessDenied;
            if (exception is TimeoutException) return ProtectionPreflightStatus.TimedOut;
            var com = exception as COMException;
            if (com != null)
            {
                switch (unchecked((uint)com.ErrorCode))
                {
                    case 0x80070005:
                    case 0x80041003: return ProtectionPreflightStatus.AccessDenied;
                    case 0x80041010: return ProtectionPreflightStatus.ClassNotFound;
                    case 0x8004100E: return ProtectionPreflightStatus.NamespaceNotFound;
                    case 0x80043001:
                    case 0x800705B4: return ProtectionPreflightStatus.TimedOut;
                }
            }
            // A missing instance/property is not evidence of missing class.
            return ProtectionPreflightStatus.Unavailable;
        }

        private static FixedReadPreflightError ClassifyTraceError(Exception exception)
        {
            var management = exception as ManagementException;
            return FixedReadPreflightErrors.Classify(exception,
                management == null ? (int?)null : (int)management.ErrorCode);
        }

        private static ProtectionPreflightStatus StatusFor(FixedReadPreflightError error)
        {
            switch (error)
            {
                case FixedReadPreflightError.WmiAccessDenied:
                case FixedReadPreflightError.WindowsAccessDenied:
                case FixedReadPreflightError.ManagedAccessDenied:
                case FixedReadPreflightError.ManagedSecurityDenied: return ProtectionPreflightStatus.AccessDenied;
                case FixedReadPreflightError.WmiClassNotFound: return ProtectionPreflightStatus.ClassNotFound;
                case FixedReadPreflightError.WmiNamespaceNotFound: return ProtectionPreflightStatus.NamespaceNotFound;
                case FixedReadPreflightError.WmiTimedOut:
                case FixedReadPreflightError.WindowsTimedOut:
                case FixedReadPreflightError.ManagedTimedOut: return ProtectionPreflightStatus.TimedOut;
                default: return ProtectionPreflightStatus.Unavailable;
            }
        }

        private static ProtectionPreflightResult Failure(ProtectionPreflightStatus status,
            ProtectionPreflightStage stage, FixedReadPreflightTracker trace = null)
            => stage == ProtectionPreflightStage.MethodEnumeration && trace != null
                ? new ProtectionPreflightResult(status, stage, null, trace.Substep, trace.Error, trace.CleanupFailed)
                : new ProtectionPreflightResult(status, stage);

        private static InvalidOperationException FixedFailure()
            => new InvalidOperationException("The fixed read preflight could not complete.");

        private static void DisposeQuiet(ManagementBaseObject value)
        {
            try { if (value != null) value.Dispose(); } catch { }
        }
    }
}
