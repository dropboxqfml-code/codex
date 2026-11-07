using System;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    public enum WsabiWmiReadTrialVariant { SingleReadWithoutHandshake, HandshakeThenRead }
    public enum WsabiWmiSingleReadPlanIssue
    {
        None, VariantNotAvailable, PlatformUnknownOrDifferent, DeviceScopeMismatch,
        TargetScopeMismatch, TargetNotUniqueAndActive, MetadataMismatch
    }

    // Detached supplier facts, not live device discovery. The opaque identity
    // is never displayed, compared with Equals, or treated as a serial/path.
    public sealed class WsabiWmiSingleReadTarget
    {
        internal object Identity { get; }
        public string ModelName { get; }
        public string BiosVersion { get; }
        public bool IsWindows10X64 { get; }
        public string NamespaceName { get; }
        public string ClassName { get; }
        public string MethodName { get; }
        public bool EnumerationComplete { get; }
        public int InstanceCount { get; }
        public bool? Active { get; }

        public WsabiWmiSingleReadTarget(string modelName, string biosVersion, bool isWindows10X64,
            string namespaceName, string className, string methodName,
            bool enumerationComplete, int instanceCount, bool? active, object targetIdentity)
        {
            ModelName = Bound(modelName); BiosVersion = Bound(biosVersion); IsWindows10X64 = isWindows10X64;
            NamespaceName = Bound(namespaceName); ClassName = Bound(className); MethodName = Bound(methodName);
            EnumerationComplete = enumerationComplete; InstanceCount = instanceCount; Active = active; Identity = targetIdentity;
        }

        private static string Bound(string value) => value != null && value.Length <= 128 ? value : null;
    }

    // A's declared scope only. This plan does not supply a firmware command,
    // prove that opaque request bytes read anything, or authorize execution.
    public sealed class WsabiWmiSingleReadPlan
    {
        public const int MaximumDispatchHandoffs = 1;
        public const int DeclaredHandshakeCalls = 0;
        public const int DeclaredRetries = 0;
        public const int DeclaredSettingWrites = 0;
        private const uint WindowsMethodId = 1;
        private readonly WsabiWmiSingleReadTarget target;
        public WsabiWmiMethodBinder Binder { get; }
        public bool MatchesCandidateScope => true;
        public bool IsHardwareObservation => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        private WsabiWmiSingleReadPlan(WsabiWmiSingleReadTarget target, WsabiWmiMethodBinder binder)
        {
            this.target = target; Binder = binder;
        }

        public static bool TryCreate(WsabiWmiReadTrialVariant variant, WsabiWmiSingleReadTarget target,
            WsabiWmiContractMetadataReport metadata, out WsabiWmiSingleReadPlan plan,
            out WsabiWmiSingleReadPlanIssue issue)
        {
            plan = null;
            issue = Validate(variant, target);
            if (issue != WsabiWmiSingleReadPlanIssue.None) return false;
            WsabiWmiMethodBinder binder;
            if (!WsabiWmiMethodBinder.TryCreate(metadata, out binder) || binder.ObservedMethodId != WindowsMethodId)
            {
                issue = WsabiWmiSingleReadPlanIssue.MetadataMismatch;
                return false;
            }
            plan = new WsabiWmiSingleReadPlan(target, binder);
            return true;
        }

        public bool MatchesTarget(WsabiWmiSingleReadTarget supplied)
            => Validate(WsabiWmiReadTrialVariant.SingleReadWithoutHandshake, supplied) == WsabiWmiSingleReadPlanIssue.None &&
                ReferenceEquals(target.Identity, supplied.Identity);

        // Bind an opaque supplier identity to the very same SDK wrapper without
        // introducing SDK dependencies, provider equality or identifier text.
        public bool MatchesTargetIdentity(object supplied)
            => supplied != null && ReferenceEquals(target.Identity, supplied);

        public bool TryFreezeRequest(WsabiWmiMethodRequest supplied, out WsabiWmiMethodRequest frozen)
        {
            frozen = null;
            if (supplied == null || supplied.ObservedMethodId != Binder.ObservedMethodId) return false;
            WsabiWmiMethodRequest canonical;
            if (!Binder.TryWrapFrame(supplied.Frame, out canonical) || canonical.FirmwareCommand != supplied.FirmwareCommand)
                return false;
            frozen = canonical;
            return true;
        }

        private static WsabiWmiSingleReadPlanIssue Validate(WsabiWmiReadTrialVariant variant, WsabiWmiSingleReadTarget value)
        {
            if (variant != WsabiWmiReadTrialVariant.SingleReadWithoutHandshake)
                return WsabiWmiSingleReadPlanIssue.VariantNotAvailable;
            if (value == null || !value.IsWindows10X64)
                return WsabiWmiSingleReadPlanIssue.PlatformUnknownOrDifferent;
            // This is one observed WMI Name, not two prefix model alternatives.
            if (!DeviceEquals(value.ModelName, "940X3G/930X3G") || !DeviceEquals(value.BiosVersion, "P05ACJ.128.140819.dg"))
                return WsabiWmiSingleReadPlanIssue.DeviceScopeMismatch;
            if (!ScopeEquals(value.NamespaceName, WsabiWmiContractMetadataPolicy.LocalNamespace) ||
                !ScopeEquals(value.ClassName, WsabiWmiContractMetadataPolicy.MethodClass) ||
                !ScopeEquals(value.MethodName, WsabiWmiContractMetadataPolicy.MethodName) || value.Identity == null)
                return WsabiWmiSingleReadPlanIssue.TargetScopeMismatch;
            if (!value.EnumerationComplete || value.InstanceCount != 1 || value.Active != true)
                return WsabiWmiSingleReadPlanIssue.TargetNotUniqueAndActive;
            return WsabiWmiSingleReadPlanIssue.None;
        }

        private static bool DeviceEquals(string actual, string expected)
            => actual != null && string.Equals(actual.Trim(), expected, StringComparison.OrdinalIgnoreCase);
        private static bool ScopeEquals(string actual, string expected)
            => string.Equals(actual, expected, StringComparison.OrdinalIgnoreCase);
    }
}
