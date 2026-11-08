using System;
using System.Management;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.WmiInterop
{
    // Immutable supplier bundle. Identity matching does not authenticate which
    // actual WMI object the supplied delegate uses, or its SDK call count.
    public sealed class WsabiWmiWindowsReadTrialBinding
    {
        internal WsabiWmiSingleReadTarget Target { get; }
        internal ManagementOperationObserver Observer { get; }
        internal Action<ManagementOperationObserver, WsabiWmiMethodRequest> Dispatch { get; }

        public WsabiWmiWindowsReadTrialBinding(WsabiWmiSingleReadTarget target,
            ManagementOperationObserver observer, Action<ManagementOperationObserver, WsabiWmiMethodRequest> dispatch)
        {
            Target = target;
            Observer = observer ?? throw new ArgumentNullException(nameof(observer));
            Dispatch = dispatch ?? throw new ArgumentNullException(nameof(dispatch));
        }
    }

    public enum WsabiWmiSingleReadPreparationStatus
    {
        Ready, PlanMissing, AttemptAlreadyUsed, TargetMismatch, RequestMismatch, PreparationNotReady,
        InputNotReady, SdkBindingNotReady, ReadSpecificationUnavailable
    }

    public sealed class WsabiWmiSingleReadPreparationResult
    {
        public WsabiWmiSingleReadPreparationStatus Status { get; }
        public WsabiWmiWindowsPreparationStatus? RegistrationStatus { get; }
        public WsabiWmiWindowsSingleReadInvocation Invocation { get; }
        public WsabiWmiWindowsInputPreparationStatus? InputStatus { get; }
        public bool InputOwnershipTransferred { get; }
        public WsabiWmiWindowsCleanupStatus? InputCleanupStatus { get; }
        public WsabiWmiWindowsSdkBindingStatus? SdkStatus { get; }
        public bool IsReady => Status == WsabiWmiSingleReadPreparationStatus.Ready && Invocation != null;

        internal WsabiWmiSingleReadPreparationResult(WsabiWmiSingleReadPreparationStatus status,
            WsabiWmiWindowsPreparationStatus? registrationStatus = null,
            WsabiWmiWindowsSingleReadInvocation invocation = null,
            WsabiWmiWindowsInputPreparationStatus? inputStatus = null, bool inputOwnershipTransferred = false,
            WsabiWmiWindowsCleanupStatus? inputCleanupStatus = null, WsabiWmiWindowsSdkBindingStatus? sdkStatus = null)
        {
            Status = status; RegistrationStatus = registrationStatus; Invocation = invocation;
            InputStatus = inputStatus; InputOwnershipTransferred = inputOwnershipTransferred;
            InputCleanupStatus = inputCleanupStatus;
            SdkStatus = sdkStatus;
        }
    }

    public static partial class WsabiWmiWindowsSingleReadPreparation
    {
        private static readonly ConditionalWeakTable<WsabiWmiSingleReadPlan, Attempt> Attempts =
            new ConditionalWeakTable<WsabiWmiSingleReadPlan, Attempt>();

        // No firmware template is supplied by this API. The opaque request must
        // already exist; synthetic binding is not proof of its read semantics.
        public static Task<WsabiWmiSingleReadPreparationResult> PrepareAsync(WsabiWmiSingleReadPlan plan,
            WsabiWmiWindowsReadTrialBinding binding, WsabiWmiMethodRequest fixedRequest,
            IWsabiWmiExchangeGate exchangeGate, TimeSpan acquireTimeout, TimeSpan responseTimeout,
            CancellationToken cancellationToken = default(CancellationToken))
        {
            ValidateArguments(binding, exchangeGate, acquireTimeout, responseTimeout);
            WsabiWmiMethodRequest frozen;
            var status = Begin(plan, binding, fixedRequest, out frozen);
            if (status != WsabiWmiSingleReadPreparationStatus.Ready) return Rejected(status);
            var guarded = new WsabiWmiSingleReadDispatch(binding, frozen);
            return PrepareCoreAsync(plan, guarded, frozen, exchangeGate, acquireTimeout, responseTimeout, cancellationToken);
        }

        // Caller must stop using/disposal of both supplied inputs while this
        // task is pending. Result explicitly states whether the atomic input
        // claim transferred ownership. This entry uses the supplied dispatch.
        public static Task<WsabiWmiSingleReadPreparationResult> PrepareWithInputsAsync(WsabiWmiSingleReadPlan plan,
            WsabiWmiWindowsReadTrialBinding binding, WsabiWmiMethodRequest fixedRequest,
            ManagementBaseObject parameters, ManagementBaseObject buffer,
            IWsabiWmiExchangeGate exchangeGate, TimeSpan acquireTimeout, TimeSpan responseTimeout,
            CancellationToken cancellationToken = default(CancellationToken))
        {
            ValidateArguments(binding, exchangeGate, acquireTimeout, responseTimeout);
            WsabiWmiMethodRequest frozen;
            var status = Begin(plan, binding, fixedRequest, out frozen);
            if (status != WsabiWmiSingleReadPreparationStatus.Ready) return Rejected(status);
            if (cancellationToken.IsCancellationRequested)
                return Task.FromResult(new WsabiWmiSingleReadPreparationResult(
                    WsabiWmiSingleReadPreparationStatus.PreparationNotReady, WsabiWmiWindowsPreparationStatus.Cancelled));
            return PopulateAndPrepareAsync(plan, binding, frozen, parameters, buffer,
                exchangeGate, acquireTimeout, responseTimeout, cancellationToken);
        }

        // Generic caller-supplied-request entry remains blocked: a valid
        // envelope/SDK binding does not supply a reviewed read specification.
        // Fixed A has its own sealed-attempt entry; this API never converts
        // caller bytes into that path or uses a runtime approval flag.
        public static Task<WsabiWmiSingleReadPreparationResult> PrepareSdkAsync(WsabiWmiSingleReadPlan plan,
            WsabiWmiWindowsSdkBinding binding, WsabiWmiMethodRequest fixedRequest,
            IWsabiWmiExchangeGate exchangeGate, TimeSpan acquireTimeout, TimeSpan responseTimeout,
            CancellationToken cancellationToken = default(CancellationToken))
        {
            WsabiWmiWindowsReadTrialBinding trialBinding;
            WsabiWmiMethodRequest frozen;
            var rejected = StartSdkPreparation(plan, binding, fixedRequest, exchangeGate,
                acquireTimeout, responseTimeout, cancellationToken, out trialBinding, out frozen);
            return Task.FromResult(rejected ?? new WsabiWmiSingleReadPreparationResult(
                WsabiWmiSingleReadPreparationStatus.ReadSpecificationUnavailable));
        }

        // Mechanical SDK integration kept internal. The separate fixed A entry
        // delegates here after its sealed-attempt claim; the generic public
        // entry stays blocked. Stand-in tests never conduct a hardware trial.
        internal static Task<WsabiWmiSingleReadPreparationResult> PrepareSdkBindingAsync(WsabiWmiSingleReadPlan plan,
            WsabiWmiWindowsSdkBinding binding, WsabiWmiMethodRequest fixedRequest,
            IWsabiWmiExchangeGate exchangeGate, TimeSpan acquireTimeout, TimeSpan responseTimeout,
            CancellationToken cancellationToken = default(CancellationToken))
        {
            WsabiWmiWindowsReadTrialBinding trialBinding;
            WsabiWmiMethodRequest frozen;
            var rejected = StartSdkPreparation(plan, binding, fixedRequest, exchangeGate,
                acquireTimeout, responseTimeout, cancellationToken, out trialBinding, out frozen);
            if (rejected != null) return Task.FromResult(rejected);
            return ValidateSdkAndPrepareAsync(plan, binding, trialBinding, frozen,
                exchangeGate, acquireTimeout, responseTimeout, cancellationToken);
        }

        private static WsabiWmiSingleReadPreparationResult StartSdkPreparation(WsabiWmiSingleReadPlan plan,
            WsabiWmiWindowsSdkBinding binding, WsabiWmiMethodRequest fixedRequest,
            IWsabiWmiExchangeGate exchangeGate, TimeSpan acquireTimeout, TimeSpan responseTimeout,
            CancellationToken token, out WsabiWmiWindowsReadTrialBinding trialBinding, out WsabiWmiMethodRequest frozen)
        {
            trialBinding = null;
            frozen = null;
            if (binding == null) throw new ArgumentNullException(nameof(binding));
            trialBinding = binding.CreateTrialBinding();
            ValidateArguments(trialBinding, exchangeGate, acquireTimeout, responseTimeout);
            var status = Begin(plan, trialBinding, fixedRequest, out frozen);
            if (status != WsabiWmiSingleReadPreparationStatus.Ready) return new WsabiWmiSingleReadPreparationResult(status);
            if (!plan.MatchesTargetIdentity(binding.Target))
                return SdkRejected(WsabiWmiWindowsSdkBindingStatus.IdentityMismatch);
            if (!binding.TryClaim()) return SdkRejected(WsabiWmiWindowsSdkBindingStatus.BindingAlreadyUsed);
            if (token.IsCancellationRequested)
                return new WsabiWmiSingleReadPreparationResult(WsabiWmiSingleReadPreparationStatus.PreparationNotReady,
                    WsabiWmiWindowsPreparationStatus.Cancelled);
            return null;
        }

        private static async Task<WsabiWmiSingleReadPreparationResult> ValidateSdkAndPrepareAsync(WsabiWmiSingleReadPlan plan,
            WsabiWmiWindowsSdkBinding binding, WsabiWmiWindowsReadTrialBinding trialBinding, WsabiWmiMethodRequest frozen,
            IWsabiWmiExchangeGate exchangeGate, TimeSpan acquireTimeout, TimeSpan responseTimeout, CancellationToken token)
        {
            // Getters may block or enter SDK code. Stop intent does not end this
            // worker; no input ownership or observer registration exists yet.
            var sdkStatus = await Task.Run(() => binding.ValidateTarget()).ConfigureAwait(false);
            if (sdkStatus != WsabiWmiWindowsSdkBindingStatus.Ready)
                return new WsabiWmiSingleReadPreparationResult(WsabiWmiSingleReadPreparationStatus.SdkBindingNotReady,
                    sdkStatus: sdkStatus);
            if (token.IsCancellationRequested)
                return new WsabiWmiSingleReadPreparationResult(WsabiWmiSingleReadPreparationStatus.PreparationNotReady,
                    WsabiWmiWindowsPreparationStatus.Cancelled, sdkStatus: sdkStatus);
            return await PopulateAndPrepareAsync(plan, trialBinding, frozen, binding.Parameters, binding.Buffer,
                exchangeGate, acquireTimeout, responseTimeout, token, binding.Target, sdkStatus).ConfigureAwait(false);
        }

        private static void ValidateArguments(WsabiWmiWindowsReadTrialBinding binding,
            IWsabiWmiExchangeGate exchangeGate, TimeSpan acquireTimeout, TimeSpan responseTimeout)
        {
            if (binding == null) throw new ArgumentNullException(nameof(binding));
            if (exchangeGate == null) throw new ArgumentNullException(nameof(exchangeGate));
            if (acquireTimeout <= TimeSpan.Zero || acquireTimeout > WsabiWmiCooperativeFrameChannel.MaximumAcquireTimeout)
                throw new ArgumentOutOfRangeException(nameof(acquireTimeout));
            if (responseTimeout <= TimeSpan.Zero || responseTimeout > WsabiWmiFrameExchange.MaximumTimeout)
                throw new ArgumentOutOfRangeException(nameof(responseTimeout));
        }

        private static WsabiWmiSingleReadPreparationStatus Begin(WsabiWmiSingleReadPlan plan,
            WsabiWmiWindowsReadTrialBinding binding, WsabiWmiMethodRequest fixedRequest, out WsabiWmiMethodRequest frozen)
        {
            frozen = null;
            if (plan == null) return WsabiWmiSingleReadPreparationStatus.PlanMissing;
            Attempt attempt = Attempts.GetValue(plan, _ => new Attempt());
            // Consume before target/request validation, cancellation or SDK
            // registration. Failure cannot rearm this same plan via a wrapper.
            if (Interlocked.CompareExchange(ref attempt.Claimed, 1, 0) != 0)
                return WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed;
            if (!plan.MatchesTarget(binding.Target)) return WsabiWmiSingleReadPreparationStatus.TargetMismatch;
            if (!plan.TryFreezeRequest(fixedRequest, out frozen)) return WsabiWmiSingleReadPreparationStatus.RequestMismatch;
            return WsabiWmiSingleReadPreparationStatus.Ready;
        }

        private static async Task<WsabiWmiSingleReadPreparationResult> PopulateAndPrepareAsync(WsabiWmiSingleReadPlan plan,
            WsabiWmiWindowsReadTrialBinding binding, WsabiWmiMethodRequest frozen,
            ManagementBaseObject parameters, ManagementBaseObject buffer, IWsabiWmiExchangeGate exchangeGate,
            TimeSpan acquireTimeout, TimeSpan responseTimeout, CancellationToken token,
            ManagementBaseObject borrowedTarget = null, WsabiWmiWindowsSdkBindingStatus? sdkStatus = null)
        {
            WsabiWmiWindowsOwnedInputPair owned = null;
            // Do not cancel this worker or dispose its inputs while SDK property
            // access is in progress. Cancellation is observed after it settles.
            var inputStatus = await Task.Run(() => WsabiWmiWindowsInputPreparation.PopulateOwned(
                plan, frozen, parameters, buffer, out owned, borrowedTarget)).ConfigureAwait(false);
            if (inputStatus != WsabiWmiWindowsInputPreparationStatus.Populated)
                return new WsabiWmiSingleReadPreparationResult(WsabiWmiSingleReadPreparationStatus.InputNotReady,
                    inputStatus: inputStatus, inputOwnershipTransferred: owned != null,
                    inputCleanupStatus: owned == null ? (WsabiWmiWindowsCleanupStatus?)null
                        : await owned.ReleaseAsync().ConfigureAwait(false), sdkStatus: sdkStatus);
            var guarded = new WsabiWmiSingleReadDispatch(binding, frozen);
            return await PrepareCoreAsync(plan, guarded, frozen, exchangeGate, acquireTimeout, responseTimeout, token, owned, sdkStatus)
                .ConfigureAwait(false);
        }

        private static async Task<WsabiWmiSingleReadPreparationResult> PrepareCoreAsync(WsabiWmiSingleReadPlan plan,
            WsabiWmiSingleReadDispatch guarded, WsabiWmiMethodRequest frozen,
            IWsabiWmiExchangeGate exchangeGate, TimeSpan acquireTimeout, TimeSpan responseTimeout, CancellationToken token,
            WsabiWmiWindowsOwnedInputPair owned = null, WsabiWmiWindowsSdkBindingStatus? sdkStatus = null)
        {
            var preparation = owned == null
                ? WsabiWmiWindowsPreparation.PrepareAsync(guarded.Observer, guarded.Invoke,
                    plan.Binder, exchangeGate, acquireTimeout, responseTimeout, token)
                : WsabiWmiWindowsPreparation.PrepareWithProtectedInputsAsync(guarded.Observer, guarded.Invoke,
                    plan.Binder, exchangeGate, acquireTimeout, responseTimeout, owned, token);
            var prepared = await preparation.ConfigureAwait(false);
            WsabiWmiWindowsCleanupStatus? inputCleanup = null;
            if (!prepared.IsReady && owned != null) inputCleanup = await owned.ReleaseAsync().ConfigureAwait(false);
            return new WsabiWmiSingleReadPreparationResult(prepared.IsReady
                ? WsabiWmiSingleReadPreparationStatus.Ready : WsabiWmiSingleReadPreparationStatus.PreparationNotReady,
                prepared.Status, prepared.IsReady ? new WsabiWmiWindowsSingleReadInvocation(prepared.Invocation, frozen, owned) : null,
                owned == null ? (WsabiWmiWindowsInputPreparationStatus?)null : WsabiWmiWindowsInputPreparationStatus.Populated,
                owned != null, inputCleanup, sdkStatus);
        }

        private static Task<WsabiWmiSingleReadPreparationResult> Rejected(WsabiWmiSingleReadPreparationStatus status)
            => Task.FromResult(new WsabiWmiSingleReadPreparationResult(status));

        private static WsabiWmiSingleReadPreparationResult SdkRejected(WsabiWmiWindowsSdkBindingStatus status)
            => new WsabiWmiSingleReadPreparationResult(WsabiWmiSingleReadPreparationStatus.SdkBindingNotReady,
                sdkStatus: status);

        private sealed class Attempt { internal int Claimed; }
    }

    // Deliberately no command, payload, target, variant or retry argument at Run.
    public sealed class WsabiWmiWindowsSingleReadInvocation
    {
        private readonly WsabiWmiWindowsPreparedInvocation prepared;
        private readonly int command;
        private readonly byte[] payload;
        private readonly WsabiWmiWindowsOwnedInputPair inputs;
        private readonly object closeGate = new object();
        private Task<WsabiWmiWindowsCleanupStatus> close;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        internal WsabiWmiWindowsSingleReadInvocation(WsabiWmiWindowsPreparedInvocation prepared, WsabiWmiMethodRequest request,
            WsabiWmiWindowsOwnedInputPair inputs = null)
        {
            this.prepared = prepared; this.inputs = inputs;
            command = request.FirmwareCommand;
            byte[] frame = request.Frame;
            payload = new byte[WsabiWmiRequestEncoder.PayloadBytes];
            Array.Copy(frame, 5, payload, 0, payload.Length);
        }

        public Task<WsabiWmiFrameExchangeResult> RunAndCloseAsync(Action<WsabiWmiFrameExchangeResult> publishResult,
            CancellationToken cancellationToken = default(CancellationToken))
        {
            // Preserve synchronous argument/admission failures: a losing Run
            // must not request close of another Run that already owns inputs.
            var run = prepared.RunAndCloseAsync(command, (byte[])payload.Clone(), publishResult, cancellationToken);
            return inputs == null ? run : RunWithInputsAsync(run);
        }

        private async Task<WsabiWmiFrameExchangeResult> RunWithInputsAsync(Task<WsabiWmiFrameExchangeResult> run)
        {
            try { return await run.ConfigureAwait(false); }
            finally
            {
                if (await RequestCloseAsync().ConfigureAwait(false) == WsabiWmiWindowsCleanupStatus.Failed)
                    throw new InvalidOperationException("The fixed WMI attempt or its input objects did not close successfully.");
            }
        }

        public Task<WsabiWmiWindowsCleanupStatus> RequestCloseAsync()
        {
            if (inputs == null) return prepared.RequestCloseAsync();
            lock (closeGate)
            {
                if (close == null) close = CloseWithInputsAsync();
                return close;
            }
        }

        private async Task<WsabiWmiWindowsCleanupStatus> CloseWithInputsAsync()
        {
            // Unknown leaves this first await pending. Neither a UI result nor
            // caller cancellation is permission to release input wrappers.
            var innerStatus = await prepared.RequestCloseAsync().ConfigureAwait(false);
            var inputStatus = await inputs.ReleaseAsync().ConfigureAwait(false);
            return innerStatus == WsabiWmiWindowsCleanupStatus.Failed || inputStatus == WsabiWmiWindowsCleanupStatus.Failed
                ? WsabiWmiWindowsCleanupStatus.Failed : WsabiWmiWindowsCleanupStatus.Complete;
        }
    }

    internal sealed class WsabiWmiSingleReadDispatch
    {
        private readonly WsabiWmiWindowsReadTrialBinding binding;
        private readonly byte[] frame;
        private readonly uint methodId;
        private readonly ushort command;
        private int entered;
        internal ManagementOperationObserver Observer => binding.Observer;

        internal WsabiWmiSingleReadDispatch(WsabiWmiWindowsReadTrialBinding binding, WsabiWmiMethodRequest request)
        {
            this.binding = binding; frame = request.Frame; methodId = request.ObservedMethodId; command = request.FirmwareCommand;
        }

        internal void Invoke(ManagementOperationObserver observer, WsabiWmiMethodRequest request)
        {
            if (Interlocked.CompareExchange(ref entered, 1, 0) != 0 || !ReferenceEquals(observer, binding.Observer) ||
                request == null || request.ObservedMethodId != methodId || request.FirmwareCommand != command)
                throw Failure();
            byte[] supplied = request.Frame;
            if (supplied.Length != frame.Length) throw Failure();
            for (int index = 0; index < frame.Length; index++) if (supplied[index] != frame[index]) throw Failure();
            binding.Dispatch(observer, request);
        }

        private static InvalidOperationException Failure()
            => new InvalidOperationException("The supplied request did not match its single-use frozen trial binding.");
    }
}
