using System;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Opt-in ownership boundary for an explicitly supplied channel and gate.
    // No WMI backend, battery request, app registration or retry is provided.
    public sealed class WsabiWmiCooperativeFrameChannel : IWsabiWmiFrameChannel
    {
        public static readonly TimeSpan MaximumAcquireTimeout = TimeSpan.FromSeconds(2);
        private readonly IWsabiWmiFrameChannel channel;
        private readonly IWsabiWmiExchangeGate gate;
        private readonly TimeSpan acquireTimeout;
        private readonly WsabiWmiExchangeResource resource;
        private readonly WsabiWmiExchangeResource gateResource;
        internal object ExchangeIdentity { get; }
        public bool IsOwnershipUncertain => resource.IsQuarantined || gateResource.IsQuarantined;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        public WsabiWmiCooperativeFrameChannel(IWsabiWmiFrameChannel channel,
            IWsabiWmiExchangeGate gate, TimeSpan acquireTimeout)
        {
            this.channel = channel ?? throw new ArgumentNullException(nameof(channel));
            this.gate = gate ?? throw new ArgumentNullException(nameof(gate));
            if (acquireTimeout <= TimeSpan.Zero || acquireTimeout > MaximumAcquireTimeout)
                throw new ArgumentOutOfRangeException(nameof(acquireTimeout));
            if (channel is WsabiWmiCooperativeFrameChannel)
                throw new ArgumentException("Nested cooperative owners are not supported.", nameof(channel));
            this.acquireTimeout = acquireTimeout;
            ExchangeIdentity = WsabiWmiExchangeResource.Identity(channel);
            resource = WsabiWmiExchangeResource.For(ExchangeIdentity);
            gateResource = WsabiWmiExchangeResource.For(
                (gate as WsabiWmiWindowsMutexGate)?.CoordinationIdentity ?? gate);
        }

        public Task<WsabiWmiReplyResult> ExchangeAsync(byte[] request, CancellationToken cancellationToken)
            => Start(request, cancellationToken, null);

        internal Task<WsabiWmiReplyResult> ExchangeAsync(byte[] request,
            CancellationToken cancellationToken, WsabiWmiExchangeStopSignal stop)
            => Start(request, cancellationToken, stop);

        private Task<WsabiWmiReplyResult> Start(byte[] request, CancellationToken cancellationToken,
            WsabiWmiExchangeStopSignal suppliedStop)
        {
            if (request == null) throw new ArgumentNullException(nameof(request));
            if (request.Length != 21) throw new ArgumentException("A fixed-size frame is required.", nameof(request));
            if (cancellationToken.IsCancellationRequested) return Task.FromCanceled<WsabiWmiReplyResult>(cancellationToken);
            byte[] ownedRequest = (byte[])request.Clone();
            var completion = new TaskCompletionSource<WsabiWmiReplyResult>(TaskCreationOptions.RunContinuationsAsynchronously);
            var owner = new Thread(() =>
            {
                try { Run(ownedRequest, cancellationToken, suppliedStop, completion); }
                catch
                {
                    Quarantine();
                    completion.TrySetException(Failure(WsabiWmiCooperativeExchangeFailure.OwnershipUncertain));
                }
            })
                { IsBackground = true, Name = "ATIV cooperative exchange owner" };
            try { owner.Start(); }
            catch { completion.TrySetException(Failure(WsabiWmiCooperativeExchangeFailure.GateUnavailable)); }
            return completion.Task;
        }

        private void Run(byte[] request, CancellationToken cancellationToken,
            WsabiWmiExchangeStopSignal suppliedStop, TaskCompletionSource<WsabiWmiReplyResult> completion)
        {
            var stop = suppliedStop ?? new WsabiWmiExchangeStopSignal();
            var cancellation = new CancellationTokenSource();
            CancellationTokenRegistration registration = default(CancellationTokenRegistration);
            IWsabiWmiExchangeLease lease = null;
            WsabiWmiReplyResult reply = null;
            Exception failure = null;
            bool acquiring = false;
            try
            {
                registration = cancellationToken.Register(stop.Request);
                if (IsOwnershipUncertain)
                {
                    Quarantine();
                    throw Failure(WsabiWmiCooperativeExchangeFailure.OwnershipUncertain);
                }
                if (stop.IsRequested) throw new OperationCanceledException();
                acquiring = true;
                WsabiWmiExchangeGateAttempt attempt = gate.Acquire(acquireTimeout, stop.WaitHandle);
                if (attempt == null) throw Failure(WsabiWmiCooperativeExchangeFailure.OwnershipUncertain);
                acquiring = false;
                lease = attempt.Lease;
                if (attempt.Status == WsabiWmiExchangeGateStatus.Abandoned)
                {
                    Quarantine();
                    throw Failure(WsabiWmiCooperativeExchangeFailure.GateAbandoned);
                }
                if (attempt.Status == WsabiWmiExchangeGateStatus.Cancelled) throw new OperationCanceledException();
                if (attempt.Status != WsabiWmiExchangeGateStatus.Acquired) throw GateFailure(attempt.Status);
                if (IsOwnershipUncertain)
                {
                    Quarantine();
                    throw Failure(WsabiWmiCooperativeExchangeFailure.OwnershipUncertain);
                }
                if (!stop.TryBeginDispatch()) throw new OperationCanceledException();
                Task<WsabiWmiReplyResult> pending;
                try { pending = channel.ExchangeAsync(request, cancellation.Token); }
                catch { Quarantine(); throw Failure(WsabiWmiCooperativeExchangeFailure.ChannelFailure); }
                if (pending == null)
                {
                    Quarantine();
                    throw Failure(WsabiWmiCooperativeExchangeFailure.ChannelFailure);
                }
                Task.WhenAny(pending, stop.Notification).GetAwaiter().GetResult();
                if (stop.IsRequested && !pending.IsCompleted)
                {
                    // Only this owner runs lower cancellation callbacks. If
                    // one blocks, the owner and lease remain held until it ends.
                    try { cancellation.Cancel(); } catch { }
                }
                // Observe late faults even when stop already won. Completion
                // must mean the supplied channel's actual work has stopped.
                reply = pending.GetAwaiter().GetResult();
                if (stop.IsRequested) throw new OperationCanceledException();
                if (reply == null) throw Failure(WsabiWmiCooperativeExchangeFailure.ChannelFailure);
            }
            catch (Exception error)
            {
                if (acquiring)
                {
                    Quarantine();
                    failure = Failure(WsabiWmiCooperativeExchangeFailure.OwnershipUncertain);
                }
                else if (error is WsabiWmiUntrackedDispatchException)
                {
                    // An async bound wrapper must not hide the direct-call
                    // failure policy. Quarantine is not provider termination.
                    Quarantine();
                    failure = Failure(WsabiWmiCooperativeExchangeFailure.ChannelFailure);
                }
                else if (error is OperationCanceledException) failure = new OperationCanceledException();
                else failure = error as WsabiWmiCooperativeExchangeException ??
                    Failure(WsabiWmiCooperativeExchangeFailure.ChannelFailure);
            }
            finally
            {
                registration.Dispose();
                cancellation.Dispose();
                if (lease != null)
                {
                    try { lease.Dispose(); }
                    catch
                    {
                        Quarantine();
                        failure = Failure(WsabiWmiCooperativeExchangeFailure.ReleaseFailure);
                    }
                }
                if (suppliedStop == null) stop.Dispose();
            }
            if (failure is OperationCanceledException) completion.TrySetCanceled();
            else if (failure != null) completion.TrySetException(failure);
            else completion.TrySetResult(reply);
        }

        private void Quarantine() { resource.Quarantine(); gateResource.Quarantine(); }
        private static WsabiWmiCooperativeExchangeException Failure(WsabiWmiCooperativeExchangeFailure failure)
            => new WsabiWmiCooperativeExchangeException(failure);
        private static Exception GateFailure(WsabiWmiExchangeGateStatus status)
        {
            switch (status)
            {
                case WsabiWmiExchangeGateStatus.TimedOut: return Failure(WsabiWmiCooperativeExchangeFailure.GateTimedOut);
                case WsabiWmiExchangeGateStatus.AccessDenied: return Failure(WsabiWmiCooperativeExchangeFailure.GateAccessDenied);
                case WsabiWmiExchangeGateStatus.UnsupportedPlatform: return Failure(WsabiWmiCooperativeExchangeFailure.UnsupportedPlatform);
                default: return Failure(WsabiWmiCooperativeExchangeFailure.GateUnavailable);
            }
        }
    }
}
