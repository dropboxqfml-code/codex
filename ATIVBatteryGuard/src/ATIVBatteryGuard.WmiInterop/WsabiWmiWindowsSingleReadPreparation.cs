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
        Ready, PlanMissing, AttemptAlreadyUsed, TargetMismatch, RequestMismatch, PreparationNotReady
    }

    public sealed class WsabiWmiSingleReadPreparationResult
    {
        public WsabiWmiSingleReadPreparationStatus Status { get; }
        public WsabiWmiWindowsPreparationStatus? RegistrationStatus { get; }
        public WsabiWmiWindowsSingleReadInvocation Invocation { get; }
        public bool IsReady => Status == WsabiWmiSingleReadPreparationStatus.Ready && Invocation != null;

        internal WsabiWmiSingleReadPreparationResult(WsabiWmiSingleReadPreparationStatus status,
            WsabiWmiWindowsPreparationStatus? registrationStatus = null,
            WsabiWmiWindowsSingleReadInvocation invocation = null)
        {
            Status = status; RegistrationStatus = registrationStatus; Invocation = invocation;
        }
    }

    public static class WsabiWmiWindowsSingleReadPreparation
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
            if (binding == null) throw new ArgumentNullException(nameof(binding));
            if (exchangeGate == null) throw new ArgumentNullException(nameof(exchangeGate));
            if (acquireTimeout <= TimeSpan.Zero || acquireTimeout > WsabiWmiCooperativeFrameChannel.MaximumAcquireTimeout)
                throw new ArgumentOutOfRangeException(nameof(acquireTimeout));
            if (responseTimeout <= TimeSpan.Zero || responseTimeout > WsabiWmiFrameExchange.MaximumTimeout)
                throw new ArgumentOutOfRangeException(nameof(responseTimeout));
            if (plan == null) return Rejected(WsabiWmiSingleReadPreparationStatus.PlanMissing);
            Attempt attempt = Attempts.GetValue(plan, _ => new Attempt());
            // Consume before target/request validation, cancellation or SDK
            // registration. Failure cannot rearm this same plan via a wrapper.
            if (Interlocked.CompareExchange(ref attempt.Claimed, 1, 0) != 0)
                return Rejected(WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
            if (!plan.MatchesTarget(binding.Target)) return Rejected(WsabiWmiSingleReadPreparationStatus.TargetMismatch);
            WsabiWmiMethodRequest frozen;
            if (!plan.TryFreezeRequest(fixedRequest, out frozen)) return Rejected(WsabiWmiSingleReadPreparationStatus.RequestMismatch);
            var guarded = new WsabiWmiSingleReadDispatch(binding, frozen);
            return PrepareCoreAsync(plan, guarded, frozen, exchangeGate, acquireTimeout, responseTimeout, cancellationToken);
        }

        private static async Task<WsabiWmiSingleReadPreparationResult> PrepareCoreAsync(WsabiWmiSingleReadPlan plan,
            WsabiWmiSingleReadDispatch guarded, WsabiWmiMethodRequest frozen,
            IWsabiWmiExchangeGate exchangeGate, TimeSpan acquireTimeout, TimeSpan responseTimeout, CancellationToken token)
        {
            var prepared = await WsabiWmiWindowsPreparation.PrepareAsync(guarded.Observer, guarded.Invoke,
                plan.Binder, exchangeGate, acquireTimeout, responseTimeout, token).ConfigureAwait(false);
            return new WsabiWmiSingleReadPreparationResult(prepared.IsReady
                ? WsabiWmiSingleReadPreparationStatus.Ready : WsabiWmiSingleReadPreparationStatus.PreparationNotReady,
                prepared.Status, prepared.IsReady ? new WsabiWmiWindowsSingleReadInvocation(prepared.Invocation, frozen) : null);
        }

        private static Task<WsabiWmiSingleReadPreparationResult> Rejected(WsabiWmiSingleReadPreparationStatus status)
            => Task.FromResult(new WsabiWmiSingleReadPreparationResult(status));

        private sealed class Attempt { internal int Claimed; }
    }

    // Deliberately no command, payload, target, variant or retry argument at Run.
    public sealed class WsabiWmiWindowsSingleReadInvocation
    {
        private readonly WsabiWmiWindowsPreparedInvocation prepared;
        private readonly int command;
        private readonly byte[] payload;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        internal WsabiWmiWindowsSingleReadInvocation(WsabiWmiWindowsPreparedInvocation prepared, WsabiWmiMethodRequest request)
        {
            this.prepared = prepared;
            command = request.FirmwareCommand;
            byte[] frame = request.Frame;
            payload = new byte[WsabiWmiRequestEncoder.PayloadBytes];
            Array.Copy(frame, 5, payload, 0, payload.Length);
        }

        public Task<WsabiWmiFrameExchangeResult> RunAndCloseAsync(Action<WsabiWmiFrameExchangeResult> publishResult,
            CancellationToken cancellationToken = default(CancellationToken))
            => prepared.RunAndCloseAsync(command, (byte[])payload.Clone(), publishResult, cancellationToken);

        public Task<WsabiWmiWindowsCleanupStatus> RequestCloseAsync() => prepared.RequestCloseAsync();
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
