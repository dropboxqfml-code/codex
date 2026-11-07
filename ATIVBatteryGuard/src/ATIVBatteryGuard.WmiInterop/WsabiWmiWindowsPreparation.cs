using System;
using System.Management;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.WmiInterop
{
    public enum WsabiWmiWindowsPreparationStatus
    {
        Ready, Cancelled, ObserverUnavailable, RegistrationFailed, UnexpectedCallback, CleanupFailed
    }

    public enum WsabiWmiWindowsCleanupStatus { Complete, Failed }

    // A local preparation result, never a provider terminal or hardware fact.
    public sealed class WsabiWmiWindowsPreparationResult
    {
        public WsabiWmiWindowsPreparationStatus Status { get; }
        public WsabiWmiWindowsPreparedInvocation Invocation { get; }
        public bool IsReady => Status == WsabiWmiWindowsPreparationStatus.Ready && Invocation != null;
        internal WsabiWmiWindowsPreparationResult(WsabiWmiWindowsPreparationStatus status,
            WsabiWmiWindowsPreparedInvocation invocation = null)
        {
            Status = status;
            Invocation = invocation;
        }
    }

    public static class WsabiWmiWindowsPreparation
    {
        // Registration runs outside Core and before any session is constructed.
        // No SDK method implementation, endpoint or hardware request is supplied.
        public static Task<WsabiWmiWindowsPreparationResult> PrepareAsync(
            ManagementOperationObserver dedicatedObserver,
            Action<ManagementOperationObserver, WsabiWmiMethodRequest> dispatch,
            WsabiWmiMethodBinder binder, IWsabiWmiExchangeGate exchangeGate,
            TimeSpan acquireTimeout, TimeSpan responseTimeout,
            CancellationToken cancellationToken = default(CancellationToken))
        {
            if (dedicatedObserver == null) throw new ArgumentNullException(nameof(dedicatedObserver));
            if (dispatch == null) throw new ArgumentNullException(nameof(dispatch));
            if (binder == null) throw new ArgumentNullException(nameof(binder));
            if (exchangeGate == null) throw new ArgumentNullException(nameof(exchangeGate));
            if (acquireTimeout <= TimeSpan.Zero || acquireTimeout > WsabiWmiCooperativeFrameChannel.MaximumAcquireTimeout)
                throw new ArgumentOutOfRangeException(nameof(acquireTimeout));
            if (responseTimeout <= TimeSpan.Zero || responseTimeout > WsabiWmiFrameExchange.MaximumTimeout)
                throw new ArgumentOutOfRangeException(nameof(responseTimeout));
            if (cancellationToken.IsCancellationRequested)
                return Task.FromResult(new WsabiWmiWindowsPreparationResult(WsabiWmiWindowsPreparationStatus.Cancelled));
            WsabiWmiWindowsCallbackSource source;
            try { source = new WsabiWmiWindowsCallbackSource(dedicatedObserver, dispatch); }
            catch (ArgumentException)
            {
                return Task.FromResult(new WsabiWmiWindowsPreparationResult(WsabiWmiWindowsPreparationStatus.ObserverUnavailable));
            }
            return PrepareCoreAsync(source, binder, exchangeGate, acquireTimeout, responseTimeout, cancellationToken);
        }

        private static async Task<WsabiWmiWindowsPreparationResult> PrepareCoreAsync(
            WsabiWmiWindowsCallbackSource source, WsabiWmiMethodBinder binder,
            IWsabiWmiExchangeGate exchangeGate, TimeSpan acquireTimeout,
            TimeSpan responseTimeout, CancellationToken token)
        {
            var status = await source.PrepareAsync(token).ConfigureAwait(false);
            return new WsabiWmiWindowsPreparationResult(status,
                status == WsabiWmiWindowsPreparationStatus.Ready
                    ? new WsabiWmiWindowsPreparedInvocation(source, binder, exchangeGate, acquireTimeout, responseTimeout)
                    : null);
        }
    }

    // Owns the only route from a successful preparation to a Core session.
    // Run and unused-close are one decision; the raw source is never exposed.
    public sealed class WsabiWmiWindowsPreparedInvocation
    {
        private readonly object gate = new object();
        private readonly WsabiWmiWindowsCallbackSource source;
        private readonly WsabiWmiMethodBinder binder;
        private readonly IWsabiWmiExchangeGate exchangeGate;
        private readonly TimeSpan acquireTimeout, responseTimeout;
        private WsabiWmiInvocationSession session;
        private bool started;
        private Task<WsabiWmiWindowsCleanupStatus> close;

        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        internal WsabiWmiWindowsPreparedInvocation(WsabiWmiWindowsCallbackSource source,
            WsabiWmiMethodBinder binder, IWsabiWmiExchangeGate exchangeGate,
            TimeSpan acquireTimeout, TimeSpan responseTimeout)
        {
            this.source = source; this.binder = binder; this.exchangeGate = exchangeGate;
            this.acquireTimeout = acquireTimeout; this.responseTimeout = responseTimeout;
        }

        public Task<WsabiWmiFrameExchangeResult> RunAndCloseAsync(int command, object payload,
            Action<WsabiWmiFrameExchangeResult> publishResult,
            CancellationToken cancellationToken = default(CancellationToken))
        {
            if (publishResult == null) throw new ArgumentNullException(nameof(publishResult));
            bool rejected;
            lock (gate)
            {
                if (started || close != null) throw Failure();
                started = true;
                rejected = !source.TryReserve();
                if (!rejected)
                {
                    try
                    {
                        // Core construction is local and uses only validated
                        // dependencies. Publish it before close can observe Run.
                        session = new WsabiWmiInvocationSession(binder, source, exchangeGate, acquireTimeout, responseTimeout);
                    }
                    catch { rejected = true; }
                }
            }
            return RunCoreAsync(rejected, command, payload, publishResult, cancellationToken);
        }

        private async Task<WsabiWmiFrameExchangeResult> RunCoreAsync(bool rejected,
            int command, object payload, Action<WsabiWmiFrameExchangeResult> publish, CancellationToken token)
        {
            try
            {
                if (rejected) throw Failure();
                return await session.RunAndCloseAsync(command, payload, publish, token).ConfigureAwait(false);
            }
            finally
            {
                if (await RequestCloseAsync().ConfigureAwait(false) == WsabiWmiWindowsCleanupStatus.Failed)
                    throw Failure();
            }
        }

        public Task<WsabiWmiWindowsCleanupStatus> RequestCloseAsync()
        {
            lock (gate)
            {
                if (close != null) return close;
                WsabiWmiInvocationSession selected = session;
                // SDK event cleanup never executes on the caller or under this
                // gate. A started unknown session remains pending here.
                close = Task.Run(async () =>
                {
                    if (selected != null) await selected.RequestCloseAsync().ConfigureAwait(false);
                    return await source.CloseUnusedAsync().ConfigureAwait(false);
                });
                return close;
            }
        }

        private static InvalidOperationException Failure()
            => new InvalidOperationException("The prepared WMI registration is no longer usable or did not close successfully.");
    }
}
