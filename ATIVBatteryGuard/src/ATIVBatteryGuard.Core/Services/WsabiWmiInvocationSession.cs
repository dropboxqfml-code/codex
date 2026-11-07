using System;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Single-use managed host for explicitly supplied dependencies only. No SDK,
    // OEM implementation, trial profile, reservation or app registration exists
    // here. A future host must await RequestCloseAsync instead of treating the
    // bounded UI result as permission to exit. Forced process death is outside
    // this contract and never establishes provider termination.
    public sealed class WsabiWmiInvocationSession
    {
        private readonly object gate = new object();
        private readonly WsabiWmiInvocationSnapshotTransport transport;
        private readonly WsabiWmiFrameExchange exchange;
        private readonly CancellationTokenSource closeCancellation = new CancellationTokenSource();
        private CancellationTokenSource invocationCancellation;
        private Task closeCompletion;
        private bool started;
        private bool closing;

        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;
        public bool IsBusy => exchange.IsBusy;
        public bool IsCompletionUnknown => transport.IsCompletionUnknown;
        public bool IsCloseReady
        {
            get { lock (gate) { return closeCompletion != null && closeCompletion.IsCompleted; } }
        }

        public WsabiWmiInvocationSession(WsabiWmiMethodBinder binder,
            IWsabiWmiInvocationSource source, IWsabiWmiExchangeGate exchangeGate,
            TimeSpan acquireTimeout, TimeSpan responseTimeout)
        {
            if (binder == null) throw new ArgumentNullException(nameof(binder));
            if (source == null) throw new ArgumentNullException(nameof(source));
            if (exchangeGate == null) throw new ArgumentNullException(nameof(exchangeGate));
            transport = new WsabiWmiInvocationSnapshotTransport(source);
            var bound = new WsabiWmiBoundFrameChannel(binder, transport);
            var owner = new WsabiWmiCooperativeFrameChannel(bound, exchangeGate, acquireTimeout);
            exchange = new WsabiWmiFrameExchange(owner, responseTimeout);
        }

        public Task<WsabiWmiFrameExchangeResult> ExchangeAsync(int command, object payload,
            CancellationToken cancellationToken = default(CancellationToken))
        {
            lock (gate)
            {
                if (closing || started)
                    return Task.FromResult(new WsabiWmiFrameExchangeResult(closing
                        ? WsabiWmiFrameExchangeStatus.Cancelled : WsabiWmiFrameExchangeStatus.Busy));
                started = true;
                invocationCancellation = CancellationTokenSource.CreateLinkedTokenSource(
                    cancellationToken, closeCancellation.Token);
                // Initialization through the first await is under the host gate,
                // so close cannot observe an uninitialized cleanup boundary.
                return exchange.ExchangeAsync(command, payload, invocationCancellation.Token);
            }
        }

        public Task RequestCloseAsync()
        {
            TaskCompletionSource<bool> closed;
            CancellationTokenSource linked;
            Task cleanup;
            Task sharedCleanup;
            lock (gate)
            {
                if (closeCompletion != null) return closeCompletion;
                closing = true;
                closed = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                closeCompletion = closed.Task;
                linked = invocationCancellation;
                sharedCleanup = exchange.StopAdmissionAndGetCleanup();
                cleanup = exchange.CleanupCompletion;
            }

            // These are stop intents only. No provider cancellation, forced
            // completion, mutex release or termination is requested here.
            transport.RequestStop();
            try { closeCancellation.Cancel(); } catch { }
            _ = Task.WhenAll(transport.InvocationCompletion, cleanup, sharedCleanup).ContinueWith(completed =>
            {
                _ = completed.Exception;
                linked?.Dispose();
                closeCancellation.Dispose();
                closed.TrySetResult(true);
            }, CancellationToken.None, TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
            return closed.Task;
        }
    }
}
