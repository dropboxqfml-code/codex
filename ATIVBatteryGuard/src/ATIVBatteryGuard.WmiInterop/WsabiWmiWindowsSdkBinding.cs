using System;
using System.Management;
using System.Threading;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.WmiInterop
{
    public enum WsabiWmiWindowsSdkBindingStatus
    {
        Ready, IdentityMismatch, BindingAlreadyUsed, UnsupportedTargetType,
        NotConnected, LocalScopeMismatch, InstanceMismatch, PropertyAccessFailed
    }

    // Supplied, materialized SDK references only. No discovery or query factory.
    // The target is borrowed; caller must exclude external mutation, Dispose or
    // independent dispatch until preparation/outer close has ended. Input
    // ownership transfers only at the existing common input-pair claim.
    public sealed class WsabiWmiWindowsSdkBinding
    {
        private readonly WsabiWmiSingleReadTarget facts;
        private readonly ManagementObject target;
        private readonly ManagementOperationObserver observer;
        private readonly ManagementBaseObject parameters, buffer;
        private int preparationClaimed, dispatchEntered;

        public WsabiWmiWindowsSdkBinding(WsabiWmiSingleReadTarget targetFacts, ManagementObject target,
            ManagementOperationObserver observer, ManagementBaseObject parameters, ManagementBaseObject buffer)
        {
            facts = targetFacts ?? throw new ArgumentNullException(nameof(targetFacts));
            this.target = target ?? throw new ArgumentNullException(nameof(target));
            this.observer = observer ?? throw new ArgumentNullException(nameof(observer));
            this.parameters = parameters ?? throw new ArgumentNullException(nameof(parameters));
            this.buffer = buffer ?? throw new ArgumentNullException(nameof(buffer));
            if (ReferenceEquals(target, parameters) || ReferenceEquals(target, buffer) || ReferenceEquals(parameters, buffer))
                throw new ArgumentException("The supplied SDK target and input wrappers must be distinct.");
        }

        internal ManagementObject Target => target;
        internal ManagementBaseObject Parameters => parameters;
        internal ManagementBaseObject Buffer => buffer;
        internal WsabiWmiWindowsReadTrialBinding CreateTrialBinding()
            => new WsabiWmiWindowsReadTrialBinding(facts, observer, Dispatch);
        internal bool TryClaim() => Interlocked.CompareExchange(ref preparationClaimed, 1, 0) == 0;

        internal WsabiWmiWindowsSdkBindingStatus ValidateTarget()
        {
            // Path is virtual, whereas SDK InvokeMethod uses private routing
            // fields. A subclass could show a different path to this check.
            if (target.GetType() != typeof(ManagementObject)) return WsabiWmiWindowsSdkBindingStatus.UnsupportedTargetType;
            try
            {
                ManagementScope scope = target.Scope;
                if (scope == null || !scope.IsConnected) return WsabiWmiWindowsSdkBindingStatus.NotConnected;
                ManagementPath scopePath = scope.Path;
                if (scopePath == null || !BoundEquals(scopePath.Server, ".") ||
                    !BoundEquals(scopePath.NamespacePath, WsabiWmiContractMetadataPolicy.LocalNamespace))
                    return WsabiWmiWindowsSdkBindingStatus.LocalScopeMismatch;
                ManagementPath instancePath = target.Path;
                if (instancePath == null || !instancePath.IsInstance ||
                    !BoundEquals(instancePath.ClassName, WsabiWmiContractMetadataPolicy.MethodClass))
                    return WsabiWmiWindowsSdkBindingStatus.InstanceMismatch;
                return WsabiWmiWindowsSdkBindingStatus.Ready;
            }
            catch { return WsabiWmiWindowsSdkBindingStatus.PropertyAccessFailed; }
        }

        private void Dispatch(ManagementOperationObserver supplied, WsabiWmiMethodRequest request)
        {
            // Existing fixed-request guard checks MethodId/command/all bytes
            // before entry. This bundle has no alternate target/input/callback.
            if (Interlocked.CompareExchange(ref dispatchEntered, 1, 0) != 0 || !ReferenceEquals(supplied, observer))
                throw Failure();
            try
            {
                target.InvokeMethod(observer, WsabiWmiContractMetadataPolicy.MethodName,
                    parameters, new InvokeMethodOptions());
            }
            catch { throw Failure(); } // Not a provider terminal or a retry.
        }

        private static bool BoundEquals(string actual, string expected)
            => actual != null && actual.Length <= 128 && string.Equals(actual, expected, StringComparison.OrdinalIgnoreCase);
        private static InvalidOperationException Failure()
            => new InvalidOperationException("The fixed SDK method dispatch did not return normally.");
    }
}
