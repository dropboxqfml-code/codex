using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiCallbackSourceTests()
    {
        AddAsync("typed callback source requires explicit dependencies and direct invocation is single use", async () =>
        {
            Action<WsabiWmiMethodRequest, Action<CallbackTestObject>, Action<int>> dispatch = (request, onObject, terminal) => terminal(7);
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiCallbackInvocationSource<CallbackTestObject>(null, value => value.Bytes));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiCallbackInvocationSource<CallbackTestObject>(dispatch, null));
            int calls = 0;
            var source = new WsabiWmiCallbackInvocationSource<CallbackTestObject>((request, onObject, terminal) =>
            {
                calls++; terminal(7);
            }, value => value.Bytes);
            BatteryThrows<ArgumentNullException>(() => source.Invoke(null, new CallbackRecordingObserver()));
            BatteryThrows<ArgumentNullException>(() => source.Invoke(InvocationRequest(), null));
            Check(!source.CanReadHardware && !source.CanWriteHardware && !source.CanInvokeMethods, "callback dependency became hardware authority");
            Equal(0, calls);
            var transport = new WsabiWmiInvocationSnapshotTransport(source);
            var snapshot = await transport.ExchangeAsync(InvocationRequest(), CancellationToken.None);
            Equal(7, snapshot.ApiResult); Check(snapshot.Output == null, "error source returned output");
            BatteryThrows<InvalidOperationException>(() => source.Invoke(InvocationRequest(), new CallbackRecordingObserver()));
            await InvocationFailure(new WsabiWmiInvocationSnapshotTransport(source).ExchangeAsync(InvocationRequest(), CancellationToken.None));
            Equal(1, calls);
        });

        AddAsync("typed callback source copies bytes before selected disposal can mutate their original view", async () =>
        {
            byte[] bytes = BoundChannelReply(); byte expected = bytes[5];
            var value = new CallbackTestObject(bytes) { OnDispose = () => bytes[5] ^= 255 };
            int reads = 0;
            Action<CallbackTestObject> callback = null; Action<int> terminal = null;
            var source = new WsabiWmiCallbackInvocationSource<CallbackTestObject>((request, onObject, onTerminal) =>
            {
                callback = onObject; terminal = onTerminal; onObject(value); onTerminal(0);
            }, selected => { reads++; return selected.Bytes; });
            var channel = new WsabiWmiBoundFrameChannel(BoundChannelBinder(), new WsabiWmiInvocationSnapshotTransport(source));
            var reply = await channel.ExchangeAsync(BoundChannelRequest(), CancellationToken.None);
            Check(reply.IsValidFrame, "copied callback reply was rejected"); Equal(expected, reply.Payload[0]);
            Equal(1, reads); Equal(1, value.DisposeCalls);
            callback(value); callback(value); terminal(0);
            Equal(1, reads); Equal(1, value.DisposeCalls); Equal(expected, reply.Payload[0]);
        });

        AddAsync("typed callback source counts notifications and rejects absent null repeated or multiple results", async () =>
        {
            for (int shape = 0; shape < 5; shape++)
            {
                var first = new CallbackTestObject(BoundChannelReply());
                var second = new CallbackTestObject(BoundChannelReply());
                int reads = 0; int selectedShape = shape;
                var source = new WsabiWmiCallbackInvocationSource<CallbackTestObject>((request, onObject, terminal) =>
                {
                    if (selectedShape == 4) { terminal(0); onObject(first); return; }
                    if (selectedShape == 1) onObject(null);
                    if (selectedShape >= 2) { onObject(first); onObject(selectedShape == 2 ? first : second); }
                    terminal(0);
                }, selected => { reads++; return selected.Bytes; });
                await InvocationFailure(new WsabiWmiInvocationSnapshotTransport(source).ExchangeAsync(InvocationRequest(), CancellationToken.None));
                Equal(0, reads); Equal(shape >= 2 ? 1 : 0, first.DisposeCalls); Equal(shape == 3 ? 1 : 0, second.DisposeCalls);
            }
        });

        AddAsync("typed callback source preserves nonzero terminal without reading output", async () =>
        {
            var value = new CallbackTestObject(new byte[4097]);
            int reads = 0;
            var source = new WsabiWmiCallbackInvocationSource<CallbackTestObject>((request, onObject, terminal) =>
            {
                onObject(value); terminal(7);
            }, selected => { reads++; throw new InvalidOperationException("Unreported output getter detail."); });
            var snapshot = await new WsabiWmiInvocationSnapshotTransport(source).ExchangeAsync(InvocationRequest(), CancellationToken.None);
            Equal(7, snapshot.ApiResult); Check(snapshot.Output == null, "terminal error retained raw output");
            Equal(0, reads); Equal(1, value.DisposeCalls);
        });

        AddAsync("typed callback source settles reader and selected disposal failures without source details", async () =>
        {
            for (int fault = 0; fault < 5; fault++)
            {
                var value = new CallbackTestObject(fault == 2 ? null : fault == 3 ? new byte[4097] : BoundChannelReply());
                if (fault == 4) value.OnDispose = () => { throw new InvalidOperationException("Unreported disposal detail."); };
                int reads = 0; int selectedFault = fault;
                var source = new WsabiWmiCallbackInvocationSource<CallbackTestObject>((request, onObject, terminal) =>
                {
                    onObject(value); terminal(0);
                }, selected =>
                {
                    reads++;
                    if (selectedFault == 0) throw new InvalidOperationException("Unreported reader detail.");
                    if (selectedFault == 1) throw new OperationCanceledException("Unreported reader cancellation.");
                    return selected.Bytes;
                });
                var transport = new WsabiWmiInvocationSnapshotTransport(source);
                await InvocationFailure(transport.ExchangeAsync(InvocationRequest(), CancellationToken.None));
                await CooperativeAwait(transport.InvocationCompletion);
                Check(transport.IsInvocationSettled && !transport.IsCompletionUnknown, "known-terminal capture failure became lost completion");
                Equal(1, reads); Equal(1, value.DisposeCalls);
            }
        });

        AddAsync("typed callback source retention limit does not pad truncate or approve decoder lengths", async () =>
        {
            foreach (int length in new[] { 20, 4096 })
            {
                var value = new CallbackTestObject(new byte[length]);
                var source = new WsabiWmiCallbackInvocationSource<CallbackTestObject>((request, onObject, terminal) =>
                {
                    onObject(value); terminal(0);
                }, selected => selected.Bytes);
                var snapshot = await new WsabiWmiInvocationSnapshotTransport(source).ExchangeAsync(InvocationRequest(), CancellationToken.None);
                var outer = (IReadOnlyDictionary<string, object>)snapshot.Output;
                var inner = (IReadOnlyDictionary<string, object>)outer["outData"];
                var detached = (byte[])inner["Bytes"];
                Equal(length, detached.Length); Check(!ReferenceEquals(value.Bytes, detached), "source output retained reader storage");
                Check(!BoundChannelBinder().DecodeOutput(snapshot.ApiResult, snapshot.Output).IsValidFrame,
                    "retention cap repaired an unsupported frame");
                Equal(1, value.DisposeCalls);
            }
        });

        AddAsync("typed callback source preserves first terminal and fails conflicting reports without a second capture", async () =>
        {
            foreach (bool conflict in new[] { false, true })
            {
                var value = new CallbackTestObject(BoundChannelReply()); int reads = 0;
                var source = new WsabiWmiCallbackInvocationSource<CallbackTestObject>((request, onObject, terminal) =>
                {
                    onObject(value); terminal(0); terminal(conflict ? 7 : 0);
                }, selected => { reads++; return selected.Bytes; });
                var transport = new WsabiWmiInvocationSnapshotTransport(source);
                var pending = transport.ExchangeAsync(InvocationRequest(), CancellationToken.None);
                if (conflict) await InvocationFailure(pending);
                else
                {
                    var snapshot = await pending;
                    Equal(0, snapshot.ApiResult);
                }
                await CooperativeAwait(transport.InvocationCompletion);
                Equal(1, reads); Equal(1, value.DisposeCalls);
            }
        });

        Add("typed callback source late local cleanup never reopens or replaces a published capture", () =>
        {
            Action<CallbackTestObject> onObject = null; Action<int> onTerminal = null;
            var selected = new CallbackTestObject(BoundChannelReply());
            var late = new CallbackTestObject(BoundChannelReply());
            late.OnDispose = () => { onObject(late); onObject(selected); onTerminal(0); };
            int reads = 0;
            var observer = new CallbackRecordingObserver();
            var source = new WsabiWmiCallbackInvocationSource<CallbackTestObject>((request, accept, terminal) =>
            {
                onObject = accept; onTerminal = terminal; accept(selected); terminal(0);
            }, value => { reads++; return value.Bytes; });
            source.Invoke(InvocationRequest(), observer);
            onObject(late); onObject(late); onObject(selected); onTerminal(0);
            Equal(1, reads); Equal(1, selected.DisposeCalls); Equal(1, late.DisposeCalls);
            Equal(1, observer.Captures); Equal(0, observer.Failures);
            Equal(1, observer.Terminals.Count); Equal(0, observer.Terminals[0]);
        });

        AddAsync("typed callback source concurrent terminal conflict cannot overtake the first forwarded status", async () =>
        {
            using (var release = new ManualResetEventSlim())
            {
                var entered = CooperativeCompletion();
                var selected = new CallbackTestObject(BoundChannelReply());
                Action<int> terminal = null;
                var observer = new CallbackRecordingObserver { OnTerminal = status =>
                {
                    if (status != 0) return;
                    entered.TrySetResult(true);
                    if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException();
                }};
                var source = new WsabiWmiCallbackInvocationSource<CallbackTestObject>((request, accept, report) =>
                {
                    accept(selected); terminal = report;
                }, value => value.Bytes);
                source.Invoke(InvocationRequest(), observer);
                var first = Task.Run(() => terminal(0));
                try
                {
                    await CooperativeAwait(entered.Task);
                    await CooperativeAwait(Task.Run(() => terminal(7)));
                    Equal(1, observer.Terminals.Count); Equal(0, observer.Terminals[0]);
                    Equal(0, observer.Captures); Equal(0, observer.Failures); Equal(0, selected.DisposeCalls);
                    release.Set(); await CooperativeAwait(first);
                    Equal(2, observer.Terminals.Count); Equal(0, observer.Terminals[0]); Equal(7, observer.Terminals[1]);
                    Equal(0, observer.Captures); Equal(1, observer.Failures); Equal(1, selected.DisposeCalls);
                }
                finally { release.Set(); await CooperativeAwait(first); }
            }
        });
    }

    private sealed class CallbackTestObject : IDisposable
    {
        internal readonly byte[] Bytes;
        internal Action OnDispose;
        internal int DisposeCalls;
        internal CallbackTestObject(byte[] bytes) { Bytes = bytes; }
        public void Dispose() { Interlocked.Increment(ref DisposeCalls); OnDispose?.Invoke(); }
        public override bool Equals(object other) => throw new InvalidOperationException("Provider equality must not run.");
        public override int GetHashCode() => throw new InvalidOperationException("Provider hashing must not run.");
        public override string ToString() => throw new InvalidOperationException("Provider text must not run.");
    }

    private sealed class CallbackRecordingObserver : IWsabiWmiInvocationObserver
    {
        public bool IsStopRequested => false;
        internal readonly List<int> Terminals = new List<int>();
        internal int Captures;
        internal int Failures;
        internal Action<int> OnTerminal;
        public bool ReportTerminal(int status) { Terminals.Add(status); OnTerminal?.Invoke(status); return true; }
        public bool SettleCapture(byte[] bytes)
        {
            Check(Terminals.Count > 0, "capture preceded terminal forwarding"); Captures++; return true;
        }
        public bool FailCapture()
        {
            Check(Terminals.Count > 0, "failure capture preceded terminal forwarding"); Failures++; return true;
        }
    }
}
