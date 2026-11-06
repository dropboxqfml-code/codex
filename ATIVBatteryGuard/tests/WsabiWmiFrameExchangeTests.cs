using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiFrameExchangeTests()
    {
        Add("frame exchange requires an explicit channel and a finite bounded timeout", () =>
        {
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiFrameExchange(null, TimeSpan.FromSeconds(1)));
            var channel = new FakeFrameChannel();
            foreach (var timeout in new[] { TimeSpan.Zero, TimeSpan.FromTicks(-1), TimeSpan.MaxValue,
                WsabiWmiFrameExchange.MaximumTimeout + TimeSpan.FromTicks(1) })
                BatteryThrows<ArgumentOutOfRangeException>(() => new WsabiWmiFrameExchange(channel, timeout));
            Check(!new WsabiWmiFrameExchange(channel, WsabiWmiFrameExchange.MaximumTimeout).IsBusy, "new exchange busy");
            Equal(0, channel.Calls);
        });
        AddAsync("frame exchange encodes a fresh request and returns isolated structural payload", async () =>
        {
            var channel = new FakeFrameChannel();
            var exchange = new WsabiWmiFrameExchange(channel, TimeSpan.FromSeconds(2));
            byte[] payload = FrameExchangePayload();
            Task<WsabiWmiFrameExchangeResult> pending = exchange.ExchangeAsync(0x34, payload);
            payload[0] = 255;
            var result = await pending;
            Equal(WsabiWmiFrameExchangeStatus.ReplyReceived, result.Status);
            Check(result.IsValidFrame && !result.IsHardwareObservation && !result.CanInvokeMethods &&
                !result.CanReadHardware && !result.CanWriteHardware, "structural reply enabled hardware");
            byte[] firstRequest = channel.LastRequest;
            Equal(21, firstRequest.Length);
            Equal((byte)0x43, firstRequest[0]); Equal((byte)0x58, firstRequest[1]);
            Equal((byte)0x34, firstRequest[2]); Equal((byte)0, firstRequest[3]); Equal((byte)0, firstRequest[4]);
            for (int i = 0; i < 16; i++) Equal((byte)(i * 17), firstRequest[i + 5]);
            byte[] copy = result.Payload; copy[0] = 255;
            Equal((byte)3, result.Payload[0]);
            await FrameExchangeIdle(exchange);
            var second = await exchange.ExchangeAsync(0xff, FrameExchangePayload());
            Check(second.IsValidFrame && !ReferenceEquals(firstRequest, channel.LastRequest), "request buffers reused");
            firstRequest[20] = 0;
            Equal((byte)255, channel.LastRequest[20]);
            Equal(2, channel.Calls);
        });
        AddAsync("invalid and already-cancelled frame exchanges never enter a channel", async () =>
        {
            var channel = new FakeFrameChannel();
            var exchange = new WsabiWmiFrameExchange(channel, TimeSpan.FromSeconds(2));
            foreach (int command in new[] { -1, 0x100, 0x165, 0xffff, 65536, int.MinValue, int.MaxValue })
                AssertFrameExchangeFailure(await exchange.ExchangeAsync(command, FrameExchangePayload()), WsabiWmiFrameExchangeStatus.InvalidRequest);
            foreach (object payload in new object[] { null, new byte[0], new byte[11], new byte[15], new byte[17],
                new byte[21], new sbyte[16], new byte[1, 16], "private payload" })
                AssertFrameExchangeFailure(await exchange.ExchangeAsync(0x34, payload), WsabiWmiFrameExchangeStatus.InvalidRequest);
            using (var caller = new CancellationTokenSource())
            {
                caller.Cancel();
                AssertFrameExchangeFailure(await exchange.ExchangeAsync(0x34, FrameExchangePayload(), caller.Token), WsabiWmiFrameExchangeStatus.Cancelled);
            }
            Equal(0, channel.Calls); Check(!exchange.IsBusy, "invalid request retained slot");
        });
        AddAsync("channel throws null tasks null replies and unsolicited cancellation remain transport failures", async () =>
        {
            var channel = new FakeFrameChannel();
            var exchange = new WsabiWmiFrameExchange(channel, TimeSpan.FromSeconds(2));
            Func<byte[], CancellationToken, Task<WsabiWmiReplyResult>>[] failures =
            {
                (request, token) => { throw new InvalidOperationException(@"C:\Users\PrivateName"); },
                (request, token) => Task.FromException<WsabiWmiReplyResult>(new Exception("private response")),
                (request, token) => null,
                (request, token) => Task.FromResult<WsabiWmiReplyResult>(null),
                (request, token) => Task.FromCanceled<WsabiWmiReplyResult>(new CancellationToken(true))
            };
            foreach (var failure in failures)
            {
                channel.Handler = failure;
                AssertFrameExchangeFailure(await exchange.ExchangeAsync(0x34, FrameExchangePayload()), WsabiWmiFrameExchangeStatus.TransportFailure);
                await FrameExchangeIdle(exchange);
            }
            channel.Handler = (request, token) => Task.FromResult(FrameExchangeReply());
            Check((await exchange.ExchangeAsync(0x34, FrameExchangePayload())).IsValidFrame, "failure poisoned future call");
        });
        AddAsync("all structural reply outcomes are retained without stale payload or hardware meaning", async () =>
        {
            byte[] wrongAck = WsabiReply(); wrongAck[4] = 0;
            WsabiWmiReplyResult[] replies =
            {
                FrameExchangeReply(), WsabiWmiReplyDecoder.Decode(1, WsabiReply()),
                WsabiWmiReplyDecoder.Decode(0, null), WsabiWmiReplyDecoder.Decode(0, "private response"),
                WsabiWmiReplyDecoder.Decode(0, new byte[1, 21]), WsabiWmiReplyDecoder.Decode(0, new byte[20]),
                WsabiWmiReplyDecoder.Decode(0, wrongAck)
            };
            var channel = new FakeFrameChannel();
            var exchange = new WsabiWmiFrameExchange(channel, TimeSpan.FromSeconds(2));
            foreach (var reply in replies)
            {
                channel.Handler = (request, token) => Task.FromResult(reply);
                var result = await exchange.ExchangeAsync(0x34, FrameExchangePayload());
                Equal(WsabiWmiFrameExchangeStatus.ReplyReceived, result.Status);
                Equal(reply.Status, result.Reply.Status); Equal(reply.IsValidFrame, result.IsValidFrame);
                Equal(reply.IsValidFrame ? 16 : 0, result.Payload.Length);
                Check(!result.IsHardwareObservation && !result.CanInvokeMethods && !result.CanWriteHardware, "reply interpreted as capability");
                await FrameExchangeIdle(exchange);
            }
        });
        AddAsync("caller cancellation retains a busy slot until an uncooperative channel ends", async () =>
        {
            var completion = FrameExchangeCompletion();
            var channel = new FakeFrameChannel { Handler = (request, token) => completion.Task };
            var exchange = new WsabiWmiFrameExchange(channel, TimeSpan.FromSeconds(2));
            using (var caller = new CancellationTokenSource())
            {
                try
                {
                    Task<WsabiWmiFrameExchangeResult> pending = exchange.ExchangeAsync(0x34, FrameExchangePayload(), caller.Token);
                    await channel.Entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
                    caller.Cancel();
                    var cancelled = await pending;
                    AssertFrameExchangeFailure(cancelled, WsabiWmiFrameExchangeStatus.Cancelled);
                    await FrameExchangeCancellationRequested(channel);
                    Check(channel.LastToken.IsCancellationRequested && exchange.IsBusy, "channel cancellation or retained slot missing");
                    AssertFrameExchangeFailure(await exchange.ExchangeAsync(0x34, FrameExchangePayload()), WsabiWmiFrameExchangeStatus.Busy);
                    Equal(1, channel.Calls);
                    completion.SetResult(FrameExchangeReply());
                    await FrameExchangeIdle(exchange);
                    AssertFrameExchangeFailure(cancelled, WsabiWmiFrameExchangeStatus.Cancelled);
                    channel.Handler = (request, token) => Task.FromResult(FrameExchangeReply());
                    Check((await exchange.ExchangeAsync(0x34, FrameExchangePayload())).IsValidFrame, "cancelled slot never released");
                }
                finally { completion.TrySetResult(FrameExchangeReply()); }
            }
        });
        AddAsync("deadline retains busy state observes late faults and never resurrects a reply", async () =>
        {
            var completion = FrameExchangeCompletion();
            var channel = new FakeFrameChannel { Handler = (request, token) => completion.Task };
            var exchange = new WsabiWmiFrameExchange(channel, TimeSpan.FromMilliseconds(100));
            try
            {
                var pending = exchange.ExchangeAsync(0x34, FrameExchangePayload());
                await channel.Entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
                var expired = await pending.WaitAsync(TimeSpan.FromSeconds(2));
                AssertFrameExchangeFailure(expired, WsabiWmiFrameExchangeStatus.TimedOut);
                await FrameExchangeCancellationRequested(channel);
                Check(channel.LastToken.IsCancellationRequested && exchange.IsBusy, "timeout did not retain operation");
                AssertFrameExchangeFailure(await exchange.ExchangeAsync(0x34, FrameExchangePayload()), WsabiWmiFrameExchangeStatus.Busy);
                Equal(1, channel.Calls);
                completion.SetException(new Exception("private late fault"));
                await FrameExchangeIdle(exchange);
                AssertFrameExchangeFailure(expired, WsabiWmiFrameExchangeStatus.TimedOut);
                channel.Handler = (request, token) => Task.FromResult(FrameExchangeReply());
                Check((await exchange.ExchangeAsync(0x34, FrameExchangePayload())).IsValidFrame, "late fault poisoned next operation");
            }
            finally { completion.TrySetResult(FrameExchangeReply()); }
        });
        AddAsync("throwing channel cancellation callbacks do not escape caller cancellation or timeout", async () =>
        {
            foreach (bool callerCancels in new[] { true, false })
            {
                var registered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                var completion = FrameExchangeCompletion();
                var channel = new FakeFrameChannel { Handler = (request, token) =>
                {
                    token.Register(() => { throw new Exception("private cancellation callback"); });
                    registered.TrySetResult(true);
                    return completion.Task;
                }};
                var exchange = new WsabiWmiFrameExchange(channel, callerCancels ? TimeSpan.FromSeconds(2) : TimeSpan.FromMilliseconds(100));
                using (var caller = new CancellationTokenSource())
                {
                    try
                    {
                        var pending = exchange.ExchangeAsync(0x34, FrameExchangePayload(), caller.Token);
                        await registered.Task.WaitAsync(TimeSpan.FromSeconds(2));
                        if (callerCancels) caller.Cancel();
                        AssertFrameExchangeFailure(await pending.WaitAsync(TimeSpan.FromSeconds(2)),
                            callerCancels ? WsabiWmiFrameExchangeStatus.Cancelled : WsabiWmiFrameExchangeStatus.TimedOut);
                        await FrameExchangeCancellationRequested(channel);
                        Check(exchange.IsBusy && channel.LastToken.IsCancellationRequested, "callback error released active work");
                        completion.SetResult(FrameExchangeReply());
                        await FrameExchangeIdle(exchange);
                    }
                    finally { completion.TrySetResult(FrameExchangeReply()); }
                }
            }
        });
        AddAsync("blocking cancellation callbacks do not delay results or release the operation slot", async () =>
        {
            foreach (bool callerCancels in new[] { true, false })
            using (var caller = new CancellationTokenSource())
            using (var release = new ManualResetEventSlim())
            {
                var registered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                var cancelling = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                var channelFinished = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                var completion = FrameExchangeCompletion();
                var channel = new FakeFrameChannel { Handler = async (request, token) =>
                {
                    token.Register(() =>
                    {
                        cancelling.TrySetResult(true);
                        release.Wait();
                    });
                    registered.TrySetResult(true);
                    var reply = await completion.Task.ConfigureAwait(false);
                    channelFinished.TrySetResult(true);
                    return reply;
                }};
                var exchange = new WsabiWmiFrameExchange(channel,
                    callerCancels ? TimeSpan.FromSeconds(2) : TimeSpan.FromMilliseconds(100));
                try
                {
                    var pending = exchange.ExchangeAsync(0x34, FrameExchangePayload(), caller.Token);
                    await registered.Task.WaitAsync(TimeSpan.FromSeconds(2));
                    if (callerCancels) caller.Cancel();
                    await cancelling.Task.WaitAsync(TimeSpan.FromSeconds(2));
                    var result = await pending.WaitAsync(TimeSpan.FromSeconds(2));
                    var expected = callerCancels ? WsabiWmiFrameExchangeStatus.Cancelled : WsabiWmiFrameExchangeStatus.TimedOut;
                    AssertFrameExchangeFailure(result, expected);

                    // Ending the channel alone must not dispose its token source
                    // or admit work while the old cancellation callback is active.
                    completion.SetResult(FrameExchangeReply());
                    await channelFinished.Task.WaitAsync(TimeSpan.FromSeconds(2));
                    await Task.Delay(50);
                    AssertFrameExchangeFailure(await exchange.ExchangeAsync(0x34, FrameExchangePayload()), WsabiWmiFrameExchangeStatus.Busy);
                    Equal(1, channel.Calls);
                    release.Set();
                    await FrameExchangeIdle(exchange);
                    AssertFrameExchangeFailure(result, expected);
                    channel.Handler = (request, token) => Task.FromResult(FrameExchangeReply());
                    Check((await exchange.ExchangeAsync(0x34, FrameExchangePayload())).IsValidFrame,
                        "completed cancellation callback retained the operation slot");
                }
                finally
                {
                    release.Set();
                    completion.TrySetResult(FrameExchangeReply());
                    await FrameExchangeIdle(exchange);
                }
            }
        });
        AddAsync("late caller cancellation from a blocked timeout callback cannot change a published result", async () =>
        {
            using (var caller = new CancellationTokenSource())
            using (var release = new ManualResetEventSlim())
            {
                var registered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                var cancelling = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                var completion = FrameExchangeCompletion();
                var channel = new FakeFrameChannel { Handler = (request, token) =>
                {
                    token.Register(() =>
                    {
                        cancelling.TrySetResult(true);
                        release.Wait();
                        caller.Cancel();
                        throw new Exception("private late cancellation failure");
                    });
                    registered.TrySetResult(true);
                    return completion.Task;
                }};
                var exchange = new WsabiWmiFrameExchange(channel, TimeSpan.FromMilliseconds(100));
                try
                {
                    var pending = exchange.ExchangeAsync(0x34, FrameExchangePayload(), caller.Token);
                    await registered.Task.WaitAsync(TimeSpan.FromSeconds(2));
                    await cancelling.Task.WaitAsync(TimeSpan.FromSeconds(2));
                    var expired = await pending.WaitAsync(TimeSpan.FromSeconds(2));
                    AssertFrameExchangeFailure(expired, WsabiWmiFrameExchangeStatus.TimedOut);
                    Check(!caller.IsCancellationRequested && exchange.IsBusy, "result waited for a blocked cancellation side effect");
                    release.Set();
                    await FrameExchangeCancellationRequestedBy(caller);
                    Check(exchange.IsBusy, "callback completion released an unfinished channel");
                    completion.SetResult(FrameExchangeReply());
                    await FrameExchangeIdle(exchange);
                    AssertFrameExchangeFailure(expired, WsabiWmiFrameExchangeStatus.TimedOut);
                }
                finally
                {
                    release.Set();
                    completion.TrySetResult(FrameExchangeReply());
                    await FrameExchangeIdle(exchange);
                }
            }
        });
        AddAsync("synchronously blocking channel entry stays off the caller and retains its slot", async () =>
        {
            using (var release = new ManualResetEventSlim())
            {
                var channel = new FakeFrameChannel { Handler = (request, token) =>
                {
                    release.Wait();
                    return Task.FromResult(FrameExchangeReply());
                }};
                var exchange = new WsabiWmiFrameExchange(channel, TimeSpan.FromMilliseconds(100));
                try
                {
                    var pending = exchange.ExchangeAsync(0x34, FrameExchangePayload());
                    await channel.Entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
                    AssertFrameExchangeFailure(await pending.WaitAsync(TimeSpan.FromSeconds(2)), WsabiWmiFrameExchangeStatus.TimedOut);
                    AssertFrameExchangeFailure(await exchange.ExchangeAsync(0x34, FrameExchangePayload()), WsabiWmiFrameExchangeStatus.Busy);
                    Equal(1, channel.Calls);
                }
                finally { release.Set(); }
                await FrameExchangeIdle(exchange);
            }
        });
        AddAsync("observed caller cancellation wins over a concurrently completed reply", async () =>
        {
            using (var caller = new CancellationTokenSource())
            {
                var channel = new FakeFrameChannel { Handler = (request, token) =>
                {
                    caller.Cancel();
                    return Task.FromResult(FrameExchangeReply());
                }};
                var exchange = new WsabiWmiFrameExchange(channel, TimeSpan.FromSeconds(2));
                AssertFrameExchangeFailure(await exchange.ExchangeAsync(0x34, FrameExchangePayload(), caller.Token),
                    WsabiWmiFrameExchangeStatus.Cancelled);
                await FrameExchangeIdle(exchange);
                Equal(1, channel.Calls);
            }
        });
        AddAsync("frame exchange instances have independent operation slots", async () =>
        {
            var completion = FrameExchangeCompletion();
            var firstChannel = new FakeFrameChannel { Handler = (request, token) => completion.Task };
            var first = new WsabiWmiFrameExchange(firstChannel, TimeSpan.FromSeconds(2));
            var secondChannel = new FakeFrameChannel();
            var second = new WsabiWmiFrameExchange(secondChannel, TimeSpan.FromSeconds(2));
            try
            {
                var pending = first.ExchangeAsync(0x34, FrameExchangePayload());
                await firstChannel.Entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
                Check((await second.ExchangeAsync(0x34, FrameExchangePayload())).IsValidFrame, "unrelated exchange was globally blocked");
                Check(first.IsBusy, "first operation disappeared");
                completion.SetResult(FrameExchangeReply());
                Check((await pending).IsValidFrame, "first operation failed");
                await FrameExchangeIdle(first);
            }
            finally { completion.TrySetResult(FrameExchangeReply()); }
        });
    }

    private static byte[] FrameExchangePayload()
    {
        var bytes = new byte[16];
        for (int i = 0; i < bytes.Length; i++) bytes[i] = (byte)(i * 17);
        return bytes;
    }

    private static WsabiWmiReplyResult FrameExchangeReply() => WsabiWmiReplyDecoder.Decode(0, WsabiReply());
    private static TaskCompletionSource<WsabiWmiReplyResult> FrameExchangeCompletion()
        => new TaskCompletionSource<WsabiWmiReplyResult>(TaskCreationOptions.RunContinuationsAsynchronously);

    private static void AssertFrameExchangeFailure(WsabiWmiFrameExchangeResult result, WsabiWmiFrameExchangeStatus expected)
    {
        Equal(expected, result.Status); Equal(null, result.Reply); Equal(0, result.Payload.Length);
        Check(!result.IsValidFrame && !result.IsHardwareObservation && !result.CanInvokeMethods &&
            !result.CanReadHardware && !result.CanWriteHardware, "failed exchange promoted to capability");
    }

    private static async Task FrameExchangeIdle(WsabiWmiFrameExchange exchange)
    {
        var elapsed = Stopwatch.StartNew();
        while (exchange.IsBusy)
        {
            if (elapsed.Elapsed > TimeSpan.FromSeconds(2)) throw new Exception("exchange slot did not become idle");
            await Task.Yield();
        }
    }

    private static async Task FrameExchangeCancellationRequested(FakeFrameChannel channel)
    {
        var elapsed = Stopwatch.StartNew();
        while (!channel.LastToken.IsCancellationRequested)
        {
            if (elapsed.Elapsed > TimeSpan.FromSeconds(2)) throw new Exception("channel cancellation was not requested");
            await Task.Yield();
        }
    }

    private static async Task FrameExchangeCancellationRequestedBy(CancellationTokenSource caller)
    {
        var elapsed = Stopwatch.StartNew();
        while (!caller.IsCancellationRequested)
        {
            if (elapsed.Elapsed > TimeSpan.FromSeconds(2)) throw new Exception("caller cancellation side effect was not observed");
            await Task.Yield();
        }
    }

    private sealed class FakeFrameChannel : IWsabiWmiFrameChannel
    {
        private int calls;
        internal int Calls => Volatile.Read(ref calls);
        internal byte[] LastRequest;
        internal CancellationToken LastToken;
        internal readonly TaskCompletionSource<bool> Entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        internal Func<byte[], CancellationToken, Task<WsabiWmiReplyResult>> Handler =
            (request, token) => Task.FromResult(FrameExchangeReply());

        public Task<WsabiWmiReplyResult> ExchangeAsync(byte[] request, CancellationToken cancellationToken)
        {
            Interlocked.Increment(ref calls);
            LastRequest = request; LastToken = cancellationToken;
            Entered.TrySetResult(true);
            return Handler(request, cancellationToken);
        }
    }
}
