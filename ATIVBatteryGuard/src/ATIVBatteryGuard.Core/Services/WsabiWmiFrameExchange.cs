using System;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Coordinates a supplied channel only. It is not registered in the app and
    // has no live hardware backend, battery commands or privilege mechanism.
    public sealed class WsabiWmiFrameExchange
    {
        public static readonly TimeSpan MaximumTimeout = TimeSpan.FromSeconds(10);
        private static readonly ConditionalWeakTable<object, ExchangeSlot> Slots =
            new ConditionalWeakTable<object, ExchangeSlot>();
        private readonly IWsabiWmiFrameChannel channel;
        private readonly TimeSpan timeout;
        private readonly ExchangeSlot slot;
        public bool IsBusy => Volatile.Read(ref slot.Active) != 0;

        public WsabiWmiFrameExchange(IWsabiWmiFrameChannel channel, TimeSpan timeout)
        {
            if (channel == null) throw new ArgumentNullException(nameof(channel));
            if (timeout <= TimeSpan.Zero || timeout > MaximumTimeout)
                throw new ArgumentOutOfRangeException(nameof(timeout));
            this.channel = channel;
            this.timeout = timeout;
            // A second coordinator must not bypass unfinished work on the same
            // supplied channel. Bound wrappers share their transport reference;
            // other channels share only their own object identity. This is an
            // in-process scope, not an OS/OEM mutex or a live transport lease.
            object identity = (channel as WsabiWmiBoundFrameChannel)?.ExchangeIdentity ?? channel;
            slot = Slots.GetValue(identity, _ => new ExchangeSlot());
        }

        public async Task<WsabiWmiFrameExchangeResult> ExchangeAsync(int command, object payload,
            CancellationToken cancellationToken = default(CancellationToken))
        {
            if (cancellationToken.IsCancellationRequested) return Result(WsabiWmiFrameExchangeStatus.Cancelled);
            byte[] request;
            if (!WsabiWmiRequestEncoder.TryEncode(command, payload, out request))
                return Result(WsabiWmiFrameExchangeStatus.InvalidRequest);
            if (Interlocked.CompareExchange(ref slot.Active, 1, 0) != 0)
                return Result(WsabiWmiFrameExchangeStatus.Busy);

            Task<WsabiWmiReplyResult> pending = null;
            Task cancellation = null;
            var operation = new CancellationTokenSource();
            var deadline = new CancellationTokenSource();
            var cancelled = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            CancellationTokenRegistration registration = default(CancellationTokenRegistration);
            try
            {
                // The caller's Cancel never runs channel cancellation callbacks.
                registration = cancellationToken.Register(() => cancelled.TrySetResult(true));
                if (cancellationToken.IsCancellationRequested) return Result(WsabiWmiFrameExchangeStatus.Cancelled);
                pending = Task.Run(async () =>
                {
                    operation.Token.ThrowIfCancellationRequested();
                    Task<WsabiWmiReplyResult> task = channel.ExchangeAsync(request, operation.Token);
                    if (task == null) throw new InvalidOperationException();
                    return await task.ConfigureAwait(false);
                });
                Task delay = Task.Delay(timeout, deadline.Token);
                Task winner = await Task.WhenAny(pending, delay, cancelled.Task).ConfigureAwait(false);
                if (cancellationToken.IsCancellationRequested)
                {
                    cancellation = CancelChannelOffThread(operation);
                    return Result(WsabiWmiFrameExchangeStatus.Cancelled);
                }
                if (!ReferenceEquals(winner, pending))
                {
                    cancellation = CancelChannelOffThread(operation);
                    // Only cancellation already observed before publishing wins.
                    // Never wait for channel callbacks to create cancellation.
                    return Result(cancellationToken.IsCancellationRequested
                        ? WsabiWmiFrameExchangeStatus.Cancelled : WsabiWmiFrameExchangeStatus.TimedOut);
                }
                WsabiWmiReplyResult reply = await pending.ConfigureAwait(false);
                // Cancellation observed before publishing the result wins.
                if (cancellationToken.IsCancellationRequested)
                    return Result(WsabiWmiFrameExchangeStatus.Cancelled);
                return reply == null ? Result(WsabiWmiFrameExchangeStatus.TransportFailure)
                    : new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived, reply);
            }
            catch
            {
                return Result(cancellationToken.IsCancellationRequested
                    ? WsabiWmiFrameExchangeStatus.Cancelled : WsabiWmiFrameExchangeStatus.TransportFailure);
            }
            finally
            {
                registration.Dispose();
                TryCancel(deadline);
                deadline.Dispose();
                if (pending == null)
                {
                    operation.Dispose();
                    Interlocked.Exchange(ref slot.Active, 0);
                }
                else
                {
                    // Neither channel completion nor a published timeout proves
                    // that cancellation callbacks have stopped. Retain the source
                    // and slot until both finish, observing any late channel fault.
                    Task cleanup = cancellation == null ? pending : Task.WhenAll(pending, cancellation);
                    _ = cleanup.ContinueWith(completed =>
                    {
                        _ = completed.Exception;
                        operation.Dispose();
                        Interlocked.Exchange(ref slot.Active, 0);
                    }, CancellationToken.None, TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
                }
            }
        }

        // Cooperative wait/cancellation only, not hard native termination.
        // A future live channel must impose its own independent process limit.
        private static Task CancelChannelOffThread(CancellationTokenSource source)
            => Task.Run(() => TryCancel(source));

        // Only the private deadline source is cancelled on the returning path.
        // Channel cancellation can run arbitrary blocking callbacks, so it must
        // always use the worker above and participate in deferred cleanup.
        private static void TryCancel(CancellationTokenSource source)
        {
            try { source.Cancel(); } catch { }
        }

        private static WsabiWmiFrameExchangeResult Result(WsabiWmiFrameExchangeStatus status)
            => new WsabiWmiFrameExchangeResult(status);

        private sealed class ExchangeSlot
        {
            internal int Active;
        }
    }
}
