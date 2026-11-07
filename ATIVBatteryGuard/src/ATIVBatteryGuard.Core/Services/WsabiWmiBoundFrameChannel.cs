using System;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Connects pure framing, fixed method binding and an explicitly supplied
    // snapshot source. No WMI connection, native object or OEM call exists here.
    // Shared-resource concurrency and cooperative deadlines belong to FrameExchange.
    public sealed class WsabiWmiBoundFrameChannel : IWsabiWmiFrameChannel
    {
        private readonly WsabiWmiMethodBinder binder;
        private readonly IWsabiWmiMethodSnapshotTransport transport;
        // FrameExchange coordinates known wrappers through the supplied source.
        // No external key, OS object or hardware capability is exposed.
        internal object ExchangeIdentity => (transport as WsabiWmiInvocationSnapshotTransport)?.ExchangeIdentity ?? transport;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        public WsabiWmiBoundFrameChannel(WsabiWmiMethodBinder binder,
            IWsabiWmiMethodSnapshotTransport transport)
        {
            this.binder = binder ?? throw new ArgumentNullException(nameof(binder));
            this.transport = transport ?? throw new ArgumentNullException(nameof(transport));
        }

        public async Task<WsabiWmiReplyResult> ExchangeAsync(byte[] request,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            WsabiWmiMethodRequest envelope;
            if (!binder.TryWrapFrame(request, out envelope))
                throw new ArgumentException("A supported request frame is required.", nameof(request));
            cancellationToken.ThrowIfCancellationRequested();
            Task<WsabiWmiMethodSnapshot> pending;
            // Catch only the invocation itself. Fault/cancel of a returned task
            // still follows the supplied transport's normal completion contract.
            try { pending = transport.ExchangeAsync(envelope, cancellationToken); }
            catch { throw new WsabiWmiUntrackedDispatchException(); }
            if (pending == null) throw new WsabiWmiUntrackedDispatchException();
            WsabiWmiMethodSnapshot snapshot = await pending.ConfigureAwait(false);
            cancellationToken.ThrowIfCancellationRequested();
            if (snapshot == null) throw new InvalidOperationException("The snapshot was not supplied.");
            WsabiWmiMethodReplyResult reply = binder.DecodeOutput(snapshot.ApiResult, snapshot.Output);
            cancellationToken.ThrowIfCancellationRequested();
            return WsabiWmiReplyResult.FromMethodReply(reply);
        }
    }
}
