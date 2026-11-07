using System;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    // These are managed source/session lifetime tests with synthetic callbacks
    // and detached fixtures. They exercise no SDK, native object or device.
    private static void RegisterWsabiWmiCallbackSourceLifetimeTests()
    {
        AddAsync("callback source dispatch throw without terminal keeps host ownership after timeout and caller stop", async () =>
        {
            foreach (bool callerStops in new[] { false, true })
            using (var caller = new CancellationTokenSource())
            {
                var callbacks = new CallbackLifetimeCallbacks();
                var selected = new CallbackLifetimeObject();
                int reads = 0;
                var source = new WsabiWmiCallbackInvocationSource<CallbackLifetimeObject>((request, accept, terminal) =>
                {
                    callbacks.Bind(accept, terminal);
                    accept(selected);
                    throw new InvalidOperationException("Unreported synthetic dispatch detail.");
                }, value => { Interlocked.Increment(ref reads); return BoundChannelReply(); });
                var gate = new CooperativeTestGate();
                var session = CallbackLifetimeSession(source, gate,
                    callerStops ? TimeSpan.FromSeconds(3) : TimeSpan.FromMilliseconds(500));
                var published = CooperativeCompletion();
                int reports = 0;
                WsabiWmiFrameExchangeResult reported = null;
                var run = session.RunAndCloseAsync(0x34, BoundChannelPayload(), result =>
                {
                    reports++; reported = result; published.TrySetResult(true);
                }, caller.Token);
                try
                {
                    await CooperativeAwait(callbacks.Ready.Task);
                    await InvocationEventually(() => session.IsCompletionUnknown);
                    if (callerStops) caller.Cancel();
                    await CooperativeAwait(published.Task);
                    AssertFrameExchangeFailure(reported, callerStops
                        ? WsabiWmiFrameExchangeStatus.Cancelled : WsabiWmiFrameExchangeStatus.TimedOut);
                    Check(!run.IsCompleted && !session.IsCloseReady && gate.LastLease.IsHeld,
                        "dispatch throw or bounded result ended unknown source ownership");
                    Equal(0, reads); Equal(0, selected.DisposeCalls);
                    caller.Cancel(); caller.Cancel();
                    Check(!run.IsCompleted && !session.RequestCloseAsync().IsCompleted,
                        "caller cancellation bypassed missing method terminal");
                    callbacks.Terminal(1); // Explicit fake completion, never SDK evidence.
                    await CooperativeAwait(run);
                    Check(ReferenceEquals(reported, await run) && session.IsCloseReady && !gate.LastLease.IsHeld,
                        "late fake completion rewrote the report or skipped cleanup");
                    Equal(1, callbacks.Calls); Equal(1, reports); Equal(0, reads);
                    Equal(1, selected.DisposeCalls); Equal(1, gate.LastLease.DisposeCalls);
                    Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                }
                finally
                {
                    callbacks.Terminal?.Invoke(1);
                    await CooperativeAwait(session.RequestCloseAsync());
                    await CooperativeAwait(run);
                }
            }
        });

        AddAsync("callback source early terminal followed by dispatch throw is a settled failure", async () =>
        {
            var selected = new CallbackLifetimeObject();
            int reads = 0, dispatches = 0, reports = 0;
            var source = new WsabiWmiCallbackInvocationSource<CallbackLifetimeObject>((request, accept, terminal) =>
            {
                Interlocked.Increment(ref dispatches);
                accept(selected); terminal(0);
                throw new InvalidOperationException("Unreported post-terminal detail.");
            }, value => { Interlocked.Increment(ref reads); return BoundChannelReply(); });
            var gate = new CooperativeTestGate();
            var session = CallbackLifetimeSession(source, gate);
            var run = session.RunAndCloseAsync(0x34, BoundChannelPayload(), result => reports++);
            try
            {
                await CooperativeAwait(run);
                AssertFrameExchangeFailure(await run, WsabiWmiFrameExchangeStatus.TransportFailure);
                Check(session.IsCloseReady && !session.IsCompletionUnknown && !gate.LastLease.IsHeld,
                    "known terminal plus call exit remained unknown or escaped cleanup");
                Equal(1, dispatches); Equal(1, reports); Equal(1, reads);
                Equal(1, selected.DisposeCalls); Equal(1, gate.LastLease.DisposeCalls);
                Check(!source.CanInvokeMethods && !source.CanReadHardware && !source.CanWriteHardware,
                    "callback completion granted hardware permission");
            }
            finally { await CooperativeAwait(session.RequestCloseAsync()); await CooperativeAwait(run); }
        });

        AddAsync("callback source protects the same late object while selected reader and host close remain pending", async () =>
        {
            using (var releaseReader = new ManualResetEventSlim())
            {
                var callbacks = new CallbackLifetimeCallbacks();
                var selected = new CallbackLifetimeObject();
                var readerEntered = CooperativeCompletion();
                int reads = 0;
                var source = CallbackLifetimeSource(callbacks, value =>
                {
                    Interlocked.Increment(ref reads); readerEntered.TrySetResult(true);
                    CallbackLifetimeWait(releaseReader); return BoundChannelReply();
                });
                var gate = new CooperativeTestGate();
                var session = CallbackLifetimeSession(source, gate);
                var published = CooperativeCompletion();
                var run = session.RunAndCloseAsync(0x34, BoundChannelPayload(), result => published.TrySetResult(true));
                Task terminal = null;
                try
                {
                    await CallbackLifetimeCloseAfterDispatch(session, callbacks, published.Task);
                    callbacks.Object(selected);
                    terminal = Task.Run(() => callbacks.Terminal(0));
                    await CooperativeAwait(readerEntered.Task);
                    await CooperativeAwait(Task.Run(() => callbacks.Object(selected)));
                    Equal(1, reads); Equal(0, selected.DisposeCalls);
                    Check(!terminal.IsCompleted && !run.IsCompleted && !session.IsCloseReady && gate.LastLease.IsHeld,
                        "same-object late callback disposed the selected reader or ended the host");
                    releaseReader.Set();
                    await CooperativeAwait(terminal); await CooperativeAwait(run);
                    AssertFrameExchangeFailure(await run, WsabiWmiFrameExchangeStatus.Cancelled);
                    Equal(1, selected.DisposeCalls); Equal(1, gate.LastLease.DisposeCalls);
                    Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                    Check(session.IsCloseReady && !gate.LastLease.IsHeld, "reader release did not join host close");
                }
                finally
                {
                    releaseReader.Set();
                    if (terminal == null) callbacks.Terminal?.Invoke(1);
                    else await CooperativeAwait(terminal);
                    await CooperativeAwait(session.RequestCloseAsync()); await CooperativeAwait(run);
                }
            }
        });

        AddAsync("callback source selected disposal remains part of host close after dispatch has exited", async () =>
        {
            using (var releaseDisposal = new ManualResetEventSlim())
            {
                var callbacks = new CallbackLifetimeCallbacks();
                var selected = new CallbackLifetimeObject { OnDispose = () => CallbackLifetimeWait(releaseDisposal) };
                int reads = 0;
                var source = CallbackLifetimeSource(callbacks, value =>
                {
                    Interlocked.Increment(ref reads); return BoundChannelReply();
                });
                var gate = new CooperativeTestGate();
                var session = CallbackLifetimeSession(source, gate);
                var published = CooperativeCompletion();
                var run = session.RunAndCloseAsync(0x34, BoundChannelPayload(), result => published.TrySetResult(true));
                Task terminal = null;
                try
                {
                    await CallbackLifetimeCloseAfterDispatch(session, callbacks, published.Task);
                    callbacks.Object(selected);
                    terminal = Task.Run(() => callbacks.Terminal(0));
                    await CooperativeAwait(selected.DisposeEntered.Task);
                    Equal(1, reads); Equal(1, selected.DisposeCalls);
                    Check(!selected.IsDisposed && !terminal.IsCompleted && !run.IsCompleted &&
                        !session.IsCloseReady && gate.LastLease.IsHeld, "selected Dispose was detached from host lifetime");
                    releaseDisposal.Set();
                    await CooperativeAwait(terminal); await CooperativeAwait(run);
                    AssertFrameExchangeFailure(await run, WsabiWmiFrameExchangeStatus.Cancelled);
                    Check(selected.IsDisposed && session.IsCloseReady && !gate.LastLease.IsHeld,
                        "host returned before selected disposal finished");
                    Equal(1, selected.DisposeCalls); Equal(1, gate.LastLease.DisposeCalls);
                    Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                }
                finally
                {
                    releaseDisposal.Set();
                    if (terminal == null) callbacks.Terminal?.Invoke(1);
                    else await CooperativeAwait(terminal);
                    await CooperativeAwait(session.RequestCloseAsync()); await CooperativeAwait(run);
                }
            }
        });

        AddAsync("callback source joins late object disposal admitted between terminal and capture publication", async () =>
        {
            using (var allowTerminal = new ManualResetEventSlim())
            using (var releaseLateDisposal = new ManualResetEventSlim())
            {
                var callbacks = new CallbackLifetimeCallbacks();
                var selected = new CallbackLifetimeObject();
                var late = new CallbackLifetimeObject { OnDispose = () => CallbackLifetimeWait(releaseLateDisposal) };
                int reads = 0;
                var inner = CallbackLifetimeSource(callbacks, value =>
                {
                    Interlocked.Increment(ref reads); return BoundChannelReply();
                });
                var source = new CallbackLifetimeTerminalGateSource(inner, allowTerminal);
                var gate = new CooperativeTestGate();
                var session = CallbackLifetimeSession(source, gate);
                var published = CooperativeCompletion();
                var run = session.RunAndCloseAsync(0x34, BoundChannelPayload(), result => published.TrySetResult(true));
                Task terminal = null, lateCallback = null;
                try
                {
                    await CallbackLifetimeCloseAfterDispatch(session, callbacks, published.Task);
                    callbacks.Object(selected);
                    terminal = Task.Run(() => callbacks.Terminal(0));
                    await CooperativeAwait(source.TerminalForwarded.Task);
                    Equal(0, reads); Equal(0, selected.DisposeCalls);
                    lateCallback = Task.Run(() => callbacks.Object(late));
                    await CooperativeAwait(late.DisposeEntered.Task);
                    allowTerminal.Set();
                    await CooperativeAwait(terminal);
                    Equal(1, reads); Equal(1, selected.DisposeCalls);
                    Check(!lateCallback.IsCompleted && !late.IsDisposed && !run.IsCompleted &&
                        !session.IsCloseReady && gate.LastLease.IsHeld,
                        "capture publication omitted a pre-publication late disposal");
                    releaseLateDisposal.Set();
                    await CooperativeAwait(lateCallback); await CooperativeAwait(run);
                    AssertFrameExchangeFailure(await run, WsabiWmiFrameExchangeStatus.Cancelled);
                    Check(session.IsCloseReady && late.IsDisposed && !gate.LastLease.IsHeld,
                        "late cleanup was not joined before host exit");
                    Equal(1, late.DisposeCalls); Equal(1, selected.DisposeCalls); Equal(1, gate.LastLease.DisposeCalls);
                    Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                }
                finally
                {
                    allowTerminal.Set(); releaseLateDisposal.Set();
                    if (terminal == null) callbacks.Terminal?.Invoke(1);
                    else await CooperativeAwait(terminal);
                    if (lateCallback != null) await CooperativeAwait(lateCallback);
                    await CooperativeAwait(session.RequestCloseAsync()); await CooperativeAwait(run);
                }
            }
        });

        AddAsync("callback source terminal reentry from duplicate disposal does not deadlock and still joins that disposal", async () =>
        {
            using (var releaseDuplicate = new ManualResetEventSlim())
            {
                var callbacks = new CallbackLifetimeCallbacks();
                var selected = new CallbackLifetimeObject();
                var reentryReturned = CooperativeCompletion();
                int reads = 0;
                var duplicate = new CallbackLifetimeObject { OnDispose = () =>
                {
                    callbacks.Terminal(0);
                    reentryReturned.TrySetResult(true);
                    CallbackLifetimeWait(releaseDuplicate);
                }};
                var source = CallbackLifetimeSource(callbacks, value =>
                {
                    Interlocked.Increment(ref reads); return BoundChannelReply();
                });
                var gate = new CooperativeTestGate();
                var session = CallbackLifetimeSession(source, gate);
                var published = CooperativeCompletion();
                var run = session.RunAndCloseAsync(0x34, BoundChannelPayload(), result => published.TrySetResult(true));
                Task discarded = null;
                try
                {
                    await CallbackLifetimeCloseAfterDispatch(session, callbacks, published.Task);
                    callbacks.Object(selected);
                    discarded = Task.Run(() => callbacks.Object(duplicate));
                    await CooperativeAwait(reentryReturned.Task);
                    Equal(0, reads); Equal(1, selected.DisposeCalls); Equal(1, duplicate.DisposeCalls);
                    Check(!discarded.IsCompleted && !run.IsCompleted && !session.IsCloseReady && gate.LastLease.IsHeld,
                        "terminal reentry skipped active duplicate cleanup");
                    releaseDuplicate.Set();
                    await CooperativeAwait(discarded); await CooperativeAwait(run);
                    AssertFrameExchangeFailure(await run, WsabiWmiFrameExchangeStatus.Cancelled);
                    Check(session.IsCloseReady && duplicate.IsDisposed && !gate.LastLease.IsHeld,
                        "reentrant completion did not release the managed host");
                    Equal(1, selected.DisposeCalls); Equal(1, duplicate.DisposeCalls); Equal(1, gate.LastLease.DisposeCalls);
                    Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                }
                finally
                {
                    releaseDuplicate.Set();
                    if (discarded != null) await CooperativeAwait(discarded);
                    callbacks.Terminal?.Invoke(1);
                    await CooperativeAwait(session.RequestCloseAsync()); await CooperativeAwait(run);
                }
            }
        });
    }

    private static WsabiWmiInvocationSession CallbackLifetimeSession(IWsabiWmiInvocationSource source,
        CooperativeTestGate gate, TimeSpan? timeout = null)
        => new WsabiWmiInvocationSession(BoundChannelBinder(), source, gate, TimeSpan.FromMilliseconds(200),
            timeout ?? TimeSpan.FromSeconds(3));

    private static WsabiWmiCallbackInvocationSource<CallbackLifetimeObject> CallbackLifetimeSource(
        CallbackLifetimeCallbacks callbacks, Func<CallbackLifetimeObject, byte[]> reader)
        => new WsabiWmiCallbackInvocationSource<CallbackLifetimeObject>(
            (request, accept, terminal) => callbacks.Bind(accept, terminal), reader);

    private static async Task CallbackLifetimeCloseAfterDispatch(WsabiWmiInvocationSession session,
        CallbackLifetimeCallbacks callbacks, Task published)
    {
        await CooperativeAwait(callbacks.Ready.Task);
        _ = session.RequestCloseAsync();
        // Closing requests stop. Unknown then proves the transport's Invoke
        // stack has exited without a terminal; callback tasks cannot hold it.
        await InvocationEventually(() => session.IsCompletionUnknown);
        await CooperativeAwait(published);
    }

    private static void CallbackLifetimeWait(ManualResetEventSlim release)
    {
        if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("Synthetic callback gate was not released.");
    }

    private sealed class CallbackLifetimeCallbacks
    {
        private int calls;
        internal int Calls => Volatile.Read(ref calls);
        internal Action<CallbackLifetimeObject> Object;
        internal Action<int> Terminal;
        internal readonly TaskCompletionSource<bool> Ready = CooperativeCompletion();

        internal void Bind(Action<CallbackLifetimeObject> accept, Action<int> terminal)
        {
            Interlocked.Increment(ref calls); Object = accept; Terminal = terminal;
            Ready.TrySetResult(true);
        }
    }

    private sealed class CallbackLifetimeObject : IDisposable
    {
        private int disposeCalls, disposed;
        internal int DisposeCalls => Volatile.Read(ref disposeCalls);
        internal bool IsDisposed => Volatile.Read(ref disposed) != 0;
        internal Action OnDispose;
        internal readonly TaskCompletionSource<bool> DisposeEntered = CooperativeCompletion();

        public void Dispose()
        {
            Interlocked.Increment(ref disposeCalls); DisposeEntered.TrySetResult(true);
            try { OnDispose?.Invoke(); }
            finally { Interlocked.Exchange(ref disposed, 1); }
        }
    }

    private sealed class CallbackLifetimeTerminalGateSource : IWsabiWmiInvocationSource
    {
        private readonly IWsabiWmiInvocationSource source;
        private readonly ManualResetEventSlim allowTerminal;
        internal readonly TaskCompletionSource<bool> TerminalForwarded = CooperativeCompletion();

        internal CallbackLifetimeTerminalGateSource(IWsabiWmiInvocationSource source, ManualResetEventSlim allowTerminal)
        {
            this.source = source; this.allowTerminal = allowTerminal;
        }

        public void Invoke(WsabiWmiMethodRequest request, IWsabiWmiInvocationObserver observer)
            => source.Invoke(request, new CallbackLifetimeTerminalGateObserver(observer, this));

        private sealed class CallbackLifetimeTerminalGateObserver : IWsabiWmiInvocationObserver
        {
            private readonly IWsabiWmiInvocationObserver observer;
            private readonly CallbackLifetimeTerminalGateSource owner;
            internal CallbackLifetimeTerminalGateObserver(IWsabiWmiInvocationObserver observer, CallbackLifetimeTerminalGateSource owner)
            {
                this.observer = observer; this.owner = owner;
            }
            public bool IsStopRequested => observer.IsStopRequested;
            public bool ReportTerminal(int status)
            {
                bool accepted = observer.ReportTerminal(status);
                owner.TerminalForwarded.TrySetResult(true);
                CallbackLifetimeWait(owner.allowTerminal);
                return accepted;
            }
            public bool SettleCapture(byte[] bytes) => observer.SettleCapture(bytes);
            public bool FailCapture() => observer.FailCapture();
        }
    }
}
