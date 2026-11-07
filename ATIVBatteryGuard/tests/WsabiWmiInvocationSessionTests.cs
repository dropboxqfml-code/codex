using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    // Prepared fakes and existing synthetic framing fixtures only. No SDK,
    // hardware, OEM Global object, device profile or reservation is used.
    private static void RegisterWsabiWmiInvocationSessionTests()
    {
        AddAsync("managed invocation session requires supplied dependencies and close prevents first start", async () =>
        {
            var source = new InvocationTestSource();
            var gate = new CooperativeTestGate();
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiInvocationSnapshotTransport(null));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiInvocationSession(null, source, gate, TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(1)));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiInvocationSession(BoundChannelBinder(), null, gate, TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(1)));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiInvocationSession(BoundChannelBinder(), source, null, TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(1)));
            var session = InvocationSession(source, gate);
            Check(!session.CanInvokeMethods && !session.CanReadHardware && !session.CanWriteHardware && !session.IsCloseReady,
                "unconnected session became hardware permission or an uncommitted close barrier");
            Task close = session.RequestCloseAsync();
            Check(ReferenceEquals(close, session.RequestCloseAsync()), "close allocated a second lifecycle");
            await CooperativeAwait(close);
            Check(session.IsCloseReady, "no-start session did not close");
            AssertFrameExchangeFailure(await session.ExchangeAsync(0x34, BoundChannelPayload()), WsabiWmiFrameExchangeStatus.Cancelled);
            Equal(0, source.Calls); Equal(0, gate.Calls);
        });

        AddAsync("managed invocation copies detached byte output and never replays a single use source", async () =>
        {
            byte[] bytes = BoundChannelReply();
            byte expected = bytes[5];
            var source = new InvocationTestSource { Handler = (request, observer) =>
            {
                observer.ReportTerminal(0);
                observer.SettleCapture(bytes);
                bytes[5] ^= 255;
            }};
            var gate = new CooperativeTestGate();
            var session = InvocationSession(source, gate);
            var result = await session.ExchangeAsync(0x34, BoundChannelPayload());
            Check(result.IsValidFrame, "detached source reply was rejected");
            Equal(expected, result.Payload[0]);
            AssertFrameExchangeFailure(await session.ExchangeAsync(0x34, BoundChannelPayload()), WsabiWmiFrameExchangeStatus.Busy);
            await CooperativeAwait(session.RequestCloseAsync());
            var alias = new WsabiWmiInvocationSnapshotTransport(source);
            await InvocationFailure(alias.ExchangeAsync(InvocationRequest(), CancellationToken.None));
            Equal(1, source.Calls); Equal(1, gate.LastLease.DisposeCalls);
        });

        AddAsync("managed invocation final and capture cannot release a blocked source call", async () =>
        {
            using (var release = new ManualResetEventSlim())
            {
                var captured = CooperativeCompletion();
                var source = new InvocationTestSource { Handler = (request, observer) =>
                {
                    observer.ReportTerminal(0); observer.SettleCapture(BoundChannelReply());
                    captured.TrySetResult(true);
                    if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException();
                }};
                var gate = new CooperativeTestGate();
                var session = InvocationSession(source, gate);
                var pending = session.ExchangeAsync(0x34, BoundChannelPayload());
                try
                {
                    await CooperativeAwait(captured.Task);
                    Check(!pending.IsCompleted && gate.LastLease.IsHeld, "early callback ended an active source stack");
                    Task close = session.RequestCloseAsync();
                    Check(!close.IsCompleted && !session.IsCloseReady && gate.LastLease.IsHeld, "close forced a blocked invocation to end");
                    release.Set();
                    await CooperativeAwait(close);
                    AssertFrameExchangeFailure(await pending, WsabiWmiFrameExchangeStatus.Cancelled);
                    Equal(1, gate.LastLease.DisposeCalls); Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                }
                finally { release.Set(); await InvocationClose(session, source); }
            }
        });

        AddAsync("managed invocation call exit and terminal wait for final selected capture", async () =>
        {
            var source = new InvocationTestSource { Handler = (request, observer) => observer.ReportTerminal(0) };
            var gate = new CooperativeTestGate();
            var session = InvocationSession(source, gate);
            var pending = session.ExchangeAsync(0x34, BoundChannelPayload());
            try
            {
                await CooperativeAwait(source.Returned.Task);
                Check(!pending.IsCompleted && gate.LastLease.IsHeld, "terminal published before capture settlement");
                source.Observer.SettleCapture(BoundChannelReply());
                Check((await pending).IsValidFrame, "late selected capture did not finish");
                await CooperativeAwait(session.RequestCloseAsync());
                Equal(1, gate.LastLease.DisposeCalls);
            }
            finally { await InvocationClose(session, source); }
        });

        AddAsync("managed invocation unknown throw retains ownership after UI timeout", () => InvocationUnknown(false));
        AddAsync("managed invocation unknown throw retains ownership after caller cancellation", () => InvocationUnknown(true));
        AddAsync("managed invocation missing terminal after normal dispatch is unknown on close", () => InvocationUnknown(false, false));

        AddAsync("managed invocation throw after known final is failure with a settled lifetime", async () =>
        {
            var source = new InvocationTestSource { Handler = (request, observer) =>
            {
                observer.ReportTerminal(0); observer.SettleCapture(BoundChannelReply());
                throw new InvalidOperationException("private source error must not escape");
            }};
            var gate = new CooperativeTestGate();
            var session = InvocationSession(source, gate);
            AssertFrameExchangeFailure(await session.ExchangeAsync(0x34, BoundChannelPayload()), WsabiWmiFrameExchangeStatus.TransportFailure);
            await CooperativeAwait(session.RequestCloseAsync());
            Check(session.IsCloseReady && !session.IsCompletionUnknown, "known final failure retained an unknown lifetime");
            Equal(1, source.Calls); Equal(1, gate.LastLease.DisposeCalls);
        });

        AddAsync("managed invocation invalid report order cannot end the operation early", async () =>
        {
            bool accepted = true;
            var source = new InvocationTestSource { Handler = (request, observer) => accepted = observer.SettleCapture(BoundChannelReply()) };
            var transport = new WsabiWmiInvocationSnapshotTransport(source);
            var pending = transport.ExchangeAsync(InvocationRequest(), CancellationToken.None);
            try
            {
                await CooperativeAwait(source.Returned.Task);
                Check(!accepted && !pending.IsCompleted, "out of order report manufactured completion");
                source.Observer.ReportTerminal(0);
                Check(!pending.IsCompleted, "protocol error bypassed final capture");
                source.Observer.SettleCapture(BoundChannelReply());
                await InvocationFailure(pending);
                await CooperativeAwait(transport.InvocationCompletion);
                Check(transport.IsInvocationSettled, "settled protocol failure did not finish its worker");
            }
            finally { InvocationSupplyFinal(source); await InvocationSettled(pending); }
        });

        AddAsync("managed invocation conflicting terminal and duplicate capture fail only after call exit", async () =>
        {
            foreach (bool terminalConflict in new[] { true, false })
            using (var release = new ManualResetEventSlim())
            {
                var reports = CooperativeCompletion();
                var source = new InvocationTestSource { Handler = (request, observer) =>
                {
                    observer.ReportTerminal(0);
                    if (terminalConflict) observer.ReportTerminal(1);
                    observer.SettleCapture(BoundChannelReply());
                    if (!terminalConflict) observer.SettleCapture(BoundChannelReply());
                    reports.TrySetResult(true);
                    if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException();
                }};
                var transport = new WsabiWmiInvocationSnapshotTransport(source);
                var pending = transport.ExchangeAsync(InvocationRequest(), CancellationToken.None);
                try
                {
                    await CooperativeAwait(reports.Task);
                    Check(!pending.IsCompleted, "protocol failure ended a source stack still consuming input");
                    release.Set();
                    await InvocationFailure(pending);
                }
                finally { release.Set(); InvocationSupplyFinal(source); await InvocationSettled(pending); }
            }
        });

        AddAsync("managed invocation terminal status is authoritative and capture is bounded without repair", async () =>
        {
            var errorSource = new InvocationTestSource { Handler = (request, observer) =>
            {
                observer.ReportTerminal(7); observer.SettleCapture(new byte[4097]);
            }};
            var errorTransport = new WsabiWmiInvocationSnapshotTransport(errorSource);
            var snapshot = await errorTransport.ExchangeAsync(InvocationRequest(), CancellationToken.None);
            Equal(7, snapshot.ApiResult); Check(snapshot.Output == null, "terminal error retained or inspected output shape");
            foreach (byte[] invalid in new byte[][] { null, new byte[4097] })
            {
                var source = new InvocationTestSource { Handler = (request, observer) =>
                {
                    observer.ReportTerminal(0); observer.SettleCapture(invalid);
                }};
                await InvocationFailure(new WsabiWmiInvocationSnapshotTransport(source).ExchangeAsync(InvocationRequest(), CancellationToken.None));
            }
            var shortSource = new InvocationTestSource { Handler = (request, observer) =>
            {
                observer.ReportTerminal(0); observer.SettleCapture(new byte[20]);
            }};
            var session = InvocationSession(shortSource, new CooperativeTestGate());
            var result = await session.ExchangeAsync(0x34, BoundChannelPayload());
            Check(!result.IsValidFrame && result.Payload.Length == 0, "short output was padded into a valid reply");
            await CooperativeAwait(session.RequestCloseAsync());
        });

        AddAsync("managed invocation same terminal duplicate is harmless but late signals cannot replace a result", async () =>
        {
            bool duplicate = true;
            var source = new InvocationTestSource { Handler = (request, observer) =>
            {
                observer.ReportTerminal(0); duplicate = observer.ReportTerminal(0);
                observer.SettleCapture(BoundChannelReply());
            }};
            var transport = new WsabiWmiInvocationSnapshotTransport(source);
            var snapshot = await transport.ExchangeAsync(InvocationRequest(), CancellationToken.None);
            Check(!duplicate && snapshot.ApiResult == 0, "same terminal duplicate replaced the authoritative status");
            Check(!source.Observer.ReportTerminal(1) && !source.Observer.FailCapture(), "late report reopened a published result");
            Equal(0, snapshot.ApiResult); Equal(1, source.Calls);
        });

        AddAsync("managed invocation source identity blocks another session before gate acquisition", async () =>
        {
            var source = new InvocationTestSource { Handler = (request, observer) => { } };
            var gate = new CooperativeTestGate();
            var first = InvocationSession(source, gate);
            var peerGate = new CooperativeTestGate();
            var peer = InvocationSession(source, peerGate);
            var pending = first.ExchangeAsync(0x34, BoundChannelPayload());
            try
            {
                await CooperativeAwait(source.Entered.Task);
                AssertFrameExchangeFailure(await peer.ExchangeAsync(0x34, BoundChannelPayload()), WsabiWmiFrameExchangeStatus.Busy);
                Equal(0, peerGate.Calls); Equal(1, source.Calls);
            }
            finally
            {
                var close = first.RequestCloseAsync();
                InvocationSupplyFinal(source);
                await CooperativeAwait(close);
                await CooperativeAwait(peer.RequestCloseAsync());
                await CooperativeAwait(pending);
            }
        });

        AddAsync("managed invocation peer close joins the shared source owner cleanup", async () =>
        {
            using (var release = new ManualResetEventSlim())
            {
                var source = new InvocationTestSource();
                var lease = new CooperativeTestLease { OnDispose = () =>
                {
                    if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException();
                }};
                var firstGate = new CooperativeTestGate { Handler = (timeout, signal) =>
                    new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired, lease) };
                var first = InvocationSession(source, firstGate);
                var peerGate = new CooperativeTestGate();
                var peer = InvocationSession(source, peerGate);
                var pending = first.ExchangeAsync(0x34, BoundChannelPayload());
                try
                {
                    await CooperativeAwait(lease.DisposeEntered.Task);
                    AssertFrameExchangeFailure(await peer.ExchangeAsync(0x34, BoundChannelPayload()), WsabiWmiFrameExchangeStatus.Busy);
                    Task close = peer.RequestCloseAsync();
                    Check(!close.IsCompleted && !peer.IsCloseReady && lease.IsHeld,
                        "peer close ignored its shared source owner's pending lease cleanup");
                    Equal(0, peerGate.Calls); Equal(1, source.Calls);
                    release.Set();
                    await CooperativeAwait(close);
                    await CooperativeAwait(first.RequestCloseAsync());
                    await CooperativeAwait(pending);
                    Check(peer.IsCloseReady && first.IsCloseReady && !lease.IsHeld, "shared owner release did not finish both close barriers");
                }
                finally
                {
                    release.Set();
                    await InvocationClose(first, source);
                    await InvocationClose(peer, source);
                }
            }
        });

        AddAsync("managed invocation close joins owner lease release after transport settles", async () =>
        {
            using (var release = new ManualResetEventSlim())
            {
                var source = new InvocationTestSource();
                var alias = new WsabiWmiInvocationSnapshotTransport(source);
                var lease = new CooperativeTestLease { OnDispose = () =>
                {
                    if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException();
                }};
                var gate = new CooperativeTestGate { Handler = (timeout, signal) =>
                    new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired, lease) };
                var session = InvocationSession(source, gate);
                var pending = session.ExchangeAsync(0x34, BoundChannelPayload());
                try
                {
                    await CooperativeAwait(lease.DisposeEntered.Task);
                    await CooperativeAwait(alias.InvocationCompletion);
                    Task close = session.RequestCloseAsync();
                    Check(alias.IsInvocationSettled && !close.IsCompleted && !session.IsCloseReady && lease.IsHeld,
                        "transport completion released the host before its owner lease");
                    release.Set();
                    await CooperativeAwait(close);
                    Check(session.IsCloseReady && !lease.IsHeld, "released owner did not finish close");
                    Equal(1, lease.DisposeCalls); Equal(gate.AcquireThread, lease.DisposeThread);
                    await CooperativeAwait(pending);
                }
                finally { release.Set(); await InvocationClose(session, source); }
            }
        });
    }

    private static WsabiWmiInvocationSession InvocationSession(InvocationTestSource source, CooperativeTestGate gate,
        TimeSpan? timeout = null)
        => new WsabiWmiInvocationSession(BoundChannelBinder(), source, gate, TimeSpan.FromMilliseconds(200),
            timeout ?? TimeSpan.FromSeconds(3));

    private static WsabiWmiMethodRequest InvocationRequest()
    {
        WsabiWmiMethodRequest request;
        Check(BoundChannelBinder().TryWrapFrame(BoundChannelRequest(), out request), "existing synthetic invocation fixture was rejected");
        return request;
    }

    private static async Task InvocationUnknown(bool callerStops, bool sourceThrows = true)
    {
        using (var caller = new CancellationTokenSource())
        {
            var source = new InvocationTestSource { Handler = (request, observer) =>
            {
                if (sourceThrows) throw new InvalidOperationException("private source path");
            }};
            var gate = new CooperativeTestGate();
            var session = InvocationSession(source, gate, callerStops ? TimeSpan.FromSeconds(3) : TimeSpan.FromMilliseconds(500));
            var pending = session.ExchangeAsync(0x34, BoundChannelPayload(), caller.Token);
            try
            {
                await CooperativeAwait(source.Returned.Task);
                if (sourceThrows) await InvocationEventually(() => session.IsCompletionUnknown);
                if (callerStops) caller.Cancel();
                AssertFrameExchangeFailure(await pending, callerStops ? WsabiWmiFrameExchangeStatus.Cancelled : WsabiWmiFrameExchangeStatus.TimedOut);
                Task close = session.RequestCloseAsync();
                Check(session.IsCompletionUnknown && !close.IsCompleted && !session.IsCloseReady && gate.LastLease.IsHeld && session.IsBusy,
                    "missing terminal was not classified unknown or ownership ended after UI return/close");
                AssertFrameExchangeFailure(await session.ExchangeAsync(0x34, BoundChannelPayload()), WsabiWmiFrameExchangeStatus.Cancelled);
                Equal(1, source.Calls);
            }
            finally { await InvocationClose(session, source); }
            Check(session.IsCloseReady && !gate.LastLease.IsHeld, "explicit fake final did not close an unknown session");
            Equal(1, gate.LastLease.DisposeCalls); Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
        }
    }

    private static void InvocationSupplyFinal(InvocationTestSource source)
    {
        var observer = source.Observer;
        if (observer == null) return;
        observer.ReportTerminal(1);
        observer.FailCapture();
    }

    private static async Task InvocationClose(WsabiWmiInvocationSession session, InvocationTestSource source)
    {
        Task close = session.RequestCloseAsync();
        InvocationSupplyFinal(source); // Synthetic test cleanup, never SDK evidence.
        await CooperativeAwait(close);
    }

    private static async Task InvocationSettled(Task task)
    {
        try { await CooperativeAwait(task); } catch (InvalidOperationException) { } catch (OperationCanceledException) { }
    }

    private static async Task InvocationFailure(Task task)
    {
        try { await CooperativeAwait(task); }
        catch (InvalidOperationException error)
        {
            Check(error.InnerException == null && !error.Message.Contains("private"), "source details escaped a managed result");
            return;
        }
        throw new InvalidOperationException("Expected a fixed managed invocation failure.");
    }

    private static async Task InvocationEventually(Func<bool> condition)
    {
        var watch = Stopwatch.StartNew();
        while (!condition())
        {
            if (watch.Elapsed > TimeSpan.FromSeconds(3)) throw new TimeoutException("Invocation state was not observed.");
            await Task.Yield();
        }
    }

    private sealed class InvocationTestSource : IWsabiWmiInvocationSource
    {
        private int calls;
        internal int Calls => Volatile.Read(ref calls);
        internal IWsabiWmiInvocationObserver Observer;
        internal readonly TaskCompletionSource<bool> Entered = CooperativeCompletion();
        internal readonly TaskCompletionSource<bool> Returned = CooperativeCompletion();
        internal Action<WsabiWmiMethodRequest, IWsabiWmiInvocationObserver> Handler = (request, observer) =>
        {
            observer.ReportTerminal(0); observer.SettleCapture(BoundChannelReply());
        };

        public void Invoke(WsabiWmiMethodRequest request, IWsabiWmiInvocationObserver observer)
        {
            Interlocked.Increment(ref calls);
            Observer = observer;
            Entered.TrySetResult(true);
            try { Handler(request, observer); }
            finally { Returned.TrySetResult(true); }
        }
    }
}
