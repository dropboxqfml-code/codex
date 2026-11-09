using System;
using System.Collections.Generic;
using System.Management;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.WmiInterop
{
    public enum WsabiWmiProtectionSdkPreparationStatus
    {
        NotStarted, Ready, Stopped, TargetRejected, AllocationFailed, InputRejected,
        ObserverUnavailable, RegistrationFailed
    }

    // The real entry supplies its own native gate and lazy SDK factory. There
    // is no raw frame, command, dispatch delegate, gate or allocator argument.
    public static class WsabiWmiWindowsProtectionTrial
    {
        public static WsabiWmiWindowsProtectionTrialSession Prepare(
            WsabiWmiProtectionTransitionAttempt attempt, ManagementObject target)
        {
            var version = Environment.OSVersion.Version;
            if (Environment.OSVersion.Platform != PlatformID.Win32NT || !Environment.Is64BitProcess ||
                !Environment.Is64BitOperatingSystem || version.Major != 10 || version.Build < 10240 || version.Build >= 22000)
                throw Failure();
            return Create(attempt, target, new WsabiWmiWindowsMutexGate(), null, null, null);
        }

#if PORTABLE_TESTS
        internal static WsabiWmiWindowsProtectionTrialSession PrepareForTests(
            WsabiWmiProtectionTransitionAttempt attempt, ManagementObject target, IWsabiWmiExchangeGate gate,
            Func<ManagementBaseObject> parameters, Func<ManagementBaseObject> buffer,
            Func<ManagementOperationObserver> observer)
            => Create(attempt, target, gate, parameters, buffer, observer);
#endif

        private static WsabiWmiWindowsProtectionTrialSession Create(WsabiWmiProtectionTransitionAttempt attempt,
            ManagementObject target, IWsabiWmiExchangeGate gate, Func<ManagementBaseObject> parameters,
            Func<ManagementBaseObject> buffer, Func<ManagementOperationObserver> observer)
        {
            if (attempt == null || target == null || gate == null || !attempt.TargetMatches(target) || !ValidateTarget(target))
                throw Failure();
            var factory = new ProtectionSdkLeafFactory(attempt, target, parameters, buffer, observer);
            return new WsabiWmiWindowsProtectionTrialSession(
                new WsabiWmiProtectionTransitionSession(attempt, factory, gate), factory);
        }

        internal static bool ValidateTarget(ManagementObject target)
        {
            if (target == null || target.GetType() != typeof(ManagementObject)) return false;
            try
            {
                var scope = target.Scope;
                if (scope == null || !scope.IsConnected || scope.Path == null ||
                    !BoundEquals(scope.Path.Server, ".") ||
                    !BoundEquals(scope.Path.NamespacePath, WsabiWmiContractMetadataPolicy.LocalNamespace)) return false;
                var path = target.Path;
                return path != null && path.IsInstance && BoundEquals(path.ClassName, WsabiWmiContractMetadataPolicy.MethodClass);
            }
            catch { return false; }
        }

        private static bool BoundEquals(string actual, string expected)
            => actual != null && actual.Length <= 128 && string.Equals(actual, expected, StringComparison.OrdinalIgnoreCase);
        private static ArgumentException Failure() => new ArgumentException("The fixed protection trial target or platform did not match.");
    }

    public sealed class WsabiWmiWindowsProtectionTrialSession
    {
        private readonly WsabiWmiProtectionTransitionSession session;
        private readonly ProtectionSdkLeafFactory factory;
        internal WsabiWmiWindowsProtectionTrialSession(WsabiWmiProtectionTransitionSession session, ProtectionSdkLeafFactory factory)
        { this.session = session; this.factory = factory; }
        public int SdkEntries => factory.SdkEntries;
        public int SetterEntries => factory.SetterEntries;
        public WsabiWmiProtectionSdkPreparationStatus LastPreparationStatus => factory.LastPreparationStatus;
        public IReadOnlyList<WsabiWmiProtectionStageDiagnostic> GetStageDiagnostics() => session.GetStageDiagnostics();
        public Task<WsabiWmiProtectionTransitionOutcome> RunAndCloseAsync(Action<WsabiWmiProtectionTransitionOutcome> publish,
            CancellationToken token = default(CancellationToken)) => session.RunAndCloseAsync(publish, token);
        public Task<WsabiWmiProtectionCleanupStatus> RequestCloseAsync() => session.RequestCloseAsync();
#if PORTABLE_TESTS
        // Explicit fake-resource evidence only; absent from Release assemblies.
        internal void ConfirmDetachedForTests() => session.ConfirmDetachedForTests();
#endif
    }

    internal sealed class ProtectionSdkLeafFactory : IWsabiWmiProtectionLeafFactory
    {
        private readonly WsabiWmiProtectionTransitionAttempt attempt;
        private readonly ManagementObject target;
        private readonly Func<ManagementBaseObject> allocateParameters, allocateBuffer;
        private readonly Func<ManagementOperationObserver> allocateObserver;
        private readonly object dispatchGate = new object();
        private int sdkEntries, setterEntries, preparationStatus;
        public object TargetIdentity => target;
        internal int SdkEntries => Volatile.Read(ref sdkEntries);
        internal int SetterEntries => Volatile.Read(ref setterEntries);
        internal WsabiWmiProtectionSdkPreparationStatus LastPreparationStatus
            => (WsabiWmiProtectionSdkPreparationStatus)Volatile.Read(ref preparationStatus);

        internal ProtectionSdkLeafFactory(WsabiWmiProtectionTransitionAttempt attempt, ManagementObject target,
            Func<ManagementBaseObject> parameters, Func<ManagementBaseObject> buffer, Func<ManagementOperationObserver> observer)
        { this.attempt = attempt; this.target = target; allocateParameters = parameters; allocateBuffer = buffer; allocateObserver = observer; }

        public Task<WsabiWmiProtectionLeaf> PrepareAsync(WsabiWmiProtectionLeafRequest request, WsabiWmiProtectionStop stop)
        {
            if (request == null || stop == null || !attempt.ValidateRoleRequest(request.Role, request.Request)) throw Failure();
            // SDK getters and allocations never run synchronously on the owner
            // or cancellation thread. No later step is pre-created here.
            return Task.Run(() => PrepareCoreAsync(request, stop));
        }

        private async Task<WsabiWmiProtectionLeaf> PrepareCoreAsync(WsabiWmiProtectionLeafRequest request, WsabiWmiProtectionStop stop)
        {
            var owned = new LeafOwnership(target);
            try
            {
                if (stop.IsRequested) return NotReady(owned, WsabiWmiProtectionSdkPreparationStatus.Stopped);
                if (!attempt.TargetMatches(target) || !WsabiWmiWindowsProtectionTrial.ValidateTarget(target))
                    return NotReady(owned, WsabiWmiProtectionSdkPreparationStatus.TargetRejected);
                owned.Parameters = allocateParameters == null
                    ? target.GetMethodParameters(WsabiWmiContractMetadataPolicy.MethodName) : allocateParameters();
                if (!owned.Claim(owned.Parameters)) return NotReady(owned, WsabiWmiProtectionSdkPreparationStatus.InputRejected);
                if (stop.IsRequested) return NotReady(owned, WsabiWmiProtectionSdkPreparationStatus.Stopped);
                if (allocateBuffer == null)
                {
                    owned.BufferClass = new ManagementClass(target.Scope, new ManagementPath(attempt.Binder.BufferClass), null);
                    if (!owned.Claim(owned.BufferClass)) return NotReady(owned, WsabiWmiProtectionSdkPreparationStatus.InputRejected);
                    owned.Buffer = owned.BufferClass.CreateInstance();
                }
                else owned.Buffer = allocateBuffer();
                if (!owned.Claim(owned.Buffer)) return NotReady(owned, WsabiWmiProtectionSdkPreparationStatus.InputRejected);
                if (stop.IsRequested) return NotReady(owned, WsabiWmiProtectionSdkPreparationStatus.Stopped);
                var input = WsabiWmiWindowsInputPreparation.PopulateProtectionOwned(request, attempt.Binder,
                    owned.Parameters, owned.Buffer, owned, out owned.Inputs, target);
                if (input != WsabiWmiWindowsInputPreparationStatus.Populated)
                    return NotReady(owned, WsabiWmiProtectionSdkPreparationStatus.InputRejected);
                if (stop.IsRequested) return NotReady(owned, WsabiWmiProtectionSdkPreparationStatus.Stopped);
                var observer = allocateObserver == null ? new ManagementOperationObserver() : allocateObserver();
                if (observer == null) return NotReady(owned, WsabiWmiProtectionSdkPreparationStatus.ObserverUnavailable);
                int entered = 0;
                Action<ManagementOperationObserver, WsabiWmiMethodRequest> dispatch = (supplied, suppliedRequest) =>
                {
                    if (Interlocked.CompareExchange(ref entered, 1, 0) != 0 || !ReferenceEquals(supplied, observer) ||
                        !request.Matches(suppliedRequest) || !attempt.TargetMatches(target) ||
                        !WsabiWmiWindowsProtectionTrial.ValidateTarget(target) || stop.IsRequested) throw Failure();
                    lock (dispatchGate)
                    {
                        if (sdkEntries >= 7 || (request.Role == WsabiWmiProtectionTransitionStage.SemanticSet1 && setterEntries >= 1)) throw Failure();
                        sdkEntries++;
                        if (request.Role == WsabiWmiProtectionTransitionStage.SemanticSet1) setterEntries++;
                    }
                    try { target.InvokeMethod(observer, WsabiWmiContractMetadataPolicy.MethodName, owned.Parameters, new InvokeMethodOptions()); }
                    catch { throw Failure(); }
                };
                try { owned.Source = new WsabiWmiWindowsCallbackSource(observer, dispatch, owned.Inputs); }
                catch (ArgumentException) { return NotReady(owned, WsabiWmiProtectionSdkPreparationStatus.ObserverUnavailable); }
                var registration = await owned.Source.PrepareAsync(CancellationToken.None).ConfigureAwait(false);
                if (registration != WsabiWmiWindowsPreparationStatus.Ready || !owned.Source.TryReserve())
                    return NotReady(owned, WsabiWmiProtectionSdkPreparationStatus.RegistrationFailed);
                if (stop.IsRequested) return NotReady(owned, WsabiWmiProtectionSdkPreparationStatus.Stopped);
                SetStatus(WsabiWmiProtectionSdkPreparationStatus.Ready);
                return owned.Leaf(true);
            }
            catch { return NotReady(owned, WsabiWmiProtectionSdkPreparationStatus.AllocationFailed); }
        }

        private WsabiWmiProtectionLeaf NotReady(LeafOwnership ownership, WsabiWmiProtectionSdkPreparationStatus status)
        { SetStatus(status); return ownership.Leaf(false); }
        private void SetStatus(WsabiWmiProtectionSdkPreparationStatus status) => Volatile.Write(ref preparationStatus, (int)status);
        private static InvalidOperationException Failure() => new InvalidOperationException("The fixed protection SDK leaf did not dispatch normally.");

        private sealed class LeafOwnership
        {
            private readonly ManagementObject target;
            private readonly List<ManagementBaseObject> claimed = new List<ManagementBaseObject>();
            private readonly object closeGate = new object();
            private Task<WsabiWmiProtectionCleanupStatus> inputClose;
            internal ManagementBaseObject Parameters, Buffer;
            internal ManagementClass BufferClass;
            internal WsabiWmiWindowsOwnedInputPair Inputs;
            internal WsabiWmiWindowsCallbackSource Source;
            internal LeafOwnership(ManagementObject target) { this.target = target; }
            internal bool Claim(ManagementBaseObject value)
            {
                if (!WsabiWmiWindowsInputPreparation.TryClaimProtectionObject(value, this, target)) return false;
                claimed.Add(value); return true;
            }
            internal WsabiWmiProtectionLeaf Leaf(bool ready)
                => new WsabiWmiProtectionLeaf(ready, ready ? Source : null, CloseOutputAsync, CloseInputsAsync);
            private async Task<WsabiWmiProtectionCleanupStatus> CloseOutputAsync()
                => Source == null || await Source.CloseUnusedAsync().ConfigureAwait(false) == WsabiWmiWindowsCleanupStatus.Complete
                    ? WsabiWmiProtectionCleanupStatus.Complete : WsabiWmiProtectionCleanupStatus.Failed;
            private Task<WsabiWmiProtectionCleanupStatus> CloseInputsAsync()
            {
                lock (closeGate)
                {
                    if (inputClose == null) inputClose = ReleaseAsync();
                    return inputClose;
                }
            }
            private async Task<WsabiWmiProtectionCleanupStatus> ReleaseAsync()
            {
                bool failed = Inputs != null && await Inputs.ReleaseAsync().ConfigureAwait(false) == WsabiWmiWindowsCleanupStatus.Failed;
                await Task.Run(() =>
                {
                    foreach (var value in claimed)
                    {
                        if (Inputs != null && (ReferenceEquals(value, Parameters) || ReferenceEquals(value, Buffer))) continue;
                        try { value.Dispose(); } catch { failed = true; }
                    }
                }).ConfigureAwait(false);
                return failed ? WsabiWmiProtectionCleanupStatus.Failed : WsabiWmiProtectionCleanupStatus.Complete;
            }
        }
    }
}
