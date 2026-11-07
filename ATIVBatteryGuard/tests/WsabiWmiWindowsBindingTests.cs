using System;
using System.Management;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.WmiInterop;

internal static partial class Program
{
    // Compiles the production SDK shell against test-only type stand-ins.
    // It does not instantiate System.Management or exercise a Windows provider.
    private static void RegisterWsabiWmiWindowsBindingTests()
    {
        AddAsync("Windows event binding requires dedicated dependencies and registered handlers before one dispatch", async () =>
        {
            var sdk = new ManagementOperationObserver();
            Action<ManagementOperationObserver, WsabiWmiMethodRequest> dispatch = (observer, request) => { };
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiWindowsCallbackSource(null, dispatch));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiWindowsCallbackSource(sdk, null));
            ManagementBaseObject embedded;
            var root = WindowsOutputFixture(BoundChannelReply(), out embedded);
            int calls = 0;
            var source = new WsabiWmiWindowsCallbackSource(sdk, (observer, request) =>
            {
                calls++; Check(ReferenceEquals(sdk, observer), "binding substituted its supplied observer");
                Equal(1, observer.ObjectReadySubscriberCount); Equal(1, observer.CompletedSubscriberCount);
                observer.EmitObjectReady(root); observer.EmitCompleted(ManagementStatus.NoError);
            });
            Equal(0, calls); Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
            BatteryThrows<ArgumentException>(() => new WsabiWmiWindowsCallbackSource(sdk, dispatch));
            BatteryThrows<ArgumentNullException>(() => source.Invoke(null, new CallbackRecordingObserver()));
            BatteryThrows<ArgumentNullException>(() => source.Invoke(InvocationRequest(), null));
            Check(!source.CanReadHardware && !source.CanWriteHardware && !source.CanInvokeMethods, "binding became hardware authority");
            await WindowsPrepareRawSource(source);
            var channel = new WsabiWmiBoundFrameChannel(BoundChannelBinder(), new WsabiWmiInvocationSnapshotTransport(source));
            Check((await channel.ExchangeAsync(BoundChannelRequest(), CancellationToken.None)).IsValidFrame, "valid stand-in output did not reach the existing decoder");
            Equal(1, calls); Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
            Equal(1, root.ConcreteDisposeCalls); Equal(1, embedded.ConcreteDisposeCalls);
            Equal(0, root.ComponentDisposeCalls); // Stand-in distinguishes the inherited interface map.
            BatteryThrows<InvalidOperationException>(() => source.Invoke(InvocationRequest(), new CallbackRecordingObserver()));
            Equal(1, calls);
        });

        AddAsync("Windows event binding preserves nonzero status without output Context or StatusObject access", async () =>
        {
            var sdk = new ManagementOperationObserver();
            var root = new ManagementBaseObject { OnGetProperties = () => throw new InvalidOperationException("PRIVATE-SDK output getter") };
            var objectArgs = new ObjectReadyEventArgs(root) { OnGetContext = () => throw new InvalidOperationException("PRIVATE-SDK context") };
            var completedArgs = new CompletedEventArgs(ManagementStatus.AccessDenied)
            {
                OnGetContext = () => throw new InvalidOperationException("PRIVATE-SDK context"),
                OnGetStatusObject = () => throw new InvalidOperationException("PRIVATE-SDK status object")
            };
            var source = new WsabiWmiWindowsCallbackSource(sdk, (observer, request) =>
            {
                observer.EmitObjectReady(objectArgs); observer.EmitCompleted(completedArgs);
            });
            await WindowsPrepareRawSource(source);
            var snapshot = await new WsabiWmiInvocationSnapshotTransport(source).ExchangeAsync(InvocationRequest(), CancellationToken.None);
            Equal((int)ManagementStatus.AccessDenied, snapshot.ApiResult); Check(snapshot.Output == null, "error status retained output");
            Equal(0, objectArgs.ContextReads); Equal(0, completedArgs.ContextReads); Equal(0, completedArgs.StatusObjectReads);
            Equal(1, root.ConcreteDisposeCalls); Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
        });

        AddAsync("Windows event binding retains subscriptions and selected output after unknown dispatch timeout or stop", async () =>
        {
            foreach (bool callerStops in new[] { false, true })
            using (var caller = new CancellationTokenSource())
            {
                var sdk = new ManagementOperationObserver();
                var root = new ManagementBaseObject { OnGetProperties = () => throw new InvalidOperationException("PRIVATE-SDK output must remain unread") };
                var entered = CooperativeCompletion(); int calls = 0;
                var source = new WsabiWmiWindowsCallbackSource(sdk, (observer, request) =>
                {
                    calls++; observer.EmitObjectReady(root); entered.TrySetResult(true);
                    throw new InvalidOperationException("PRIVATE-SDK dispatch detail");
                });
                await WindowsPrepareRawSource(source);
                var gate = new CooperativeTestGate();
                var session = WindowsBindingSession(source, gate, callerStops ? TimeSpan.FromSeconds(3) : TimeSpan.FromMilliseconds(500));
                var published = CooperativeCompletion(); WsabiWmiFrameExchangeResult shown = null;
                var run = session.RunAndCloseAsync(0x34, BoundChannelPayload(), value => { shown = value; published.TrySetResult(true); }, caller.Token);
                try
                {
                    await CooperativeAwait(entered.Task); await InvocationEventually(() => session.IsCompletionUnknown);
                    if (callerStops) caller.Cancel();
                    await CooperativeAwait(published.Task);
                    AssertFrameExchangeFailure(shown, callerStops ? WsabiWmiFrameExchangeStatus.Cancelled : WsabiWmiFrameExchangeStatus.TimedOut);
                    Check(!run.IsCompleted && !session.IsCloseReady && gate.LastLease.IsHeld, "unknown SDK shell ended host ownership");
                    Equal(1, sdk.ObjectReadySubscriberCount); Equal(1, sdk.CompletedSubscriberCount); Equal(0, root.ConcreteDisposeCalls);
                    caller.Cancel(); caller.Cancel();
                    Check(!run.IsCompleted, "repeated stop closed unknown event binding");
                    sdk.EmitCompleted(ManagementStatus.AccessDenied); // Explicit stand-in terminal, not SDK evidence.
                    await CooperativeAwait(run);
                    Check(ReferenceEquals(shown, await run) && session.IsCloseReady && !gate.LastLease.IsHeld, "late cleanup rewrote result or skipped owner release");
                    Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
                    Equal(1, root.ConcreteDisposeCalls); Equal(1, calls); Equal(1, gate.LastLease.DisposeCalls);
                }
                finally
                {
                    sdk.EmitCompleted(ManagementStatus.AccessDenied);
                    await CooperativeAwait(session.RequestCloseAsync()); await CooperativeAwait(run);
                }
            }
        });

        AddAsync("Windows event binding joins entered raw object getter and rejects terminal overtaking its handoff", async () =>
        {
            using (var release = new ManualResetEventSlim())
            {
                var sdk = new ManagementOperationObserver(); var ready = CooperativeCompletion(); var getter = CooperativeCompletion();
                ManagementBaseObject embedded; var root = WindowsOutputFixture(BoundChannelReply(), out embedded);
                var source = new WsabiWmiWindowsCallbackSource(sdk, (observer, request) => ready.TrySetResult(true));
                await WindowsPrepareRawSource(source);
                var transport = new WsabiWmiInvocationSnapshotTransport(source);
                var pending = transport.ExchangeAsync(InvocationRequest(), CancellationToken.None);
                Task objectHandler = null;
                try
                {
                    await CooperativeAwait(ready.Task); transport.RequestStop(); await InvocationEventually(() => transport.IsCompletionUnknown);
                    objectHandler = Task.Run(() => sdk.EmitObjectReady(new ObjectReadyEventArgs(root) { OnGetNewObject = () =>
                    {
                        getter.TrySetResult(true); WindowsBindingWait(release); return root;
                    }}));
                    await CooperativeAwait(getter.Task);
                    await CooperativeAwait(Task.Run(() => sdk.EmitCompleted(ManagementStatus.NoError)));
                    Check(!pending.IsCompleted, "terminal omitted an entered raw object handoff");
                    Equal(1, sdk.ObjectReadySubscriberCount); Equal(1, sdk.CompletedSubscriberCount); Equal(0, root.ConcreteDisposeCalls);
                    release.Set(); await CooperativeAwait(objectHandler); await InvocationFailure(pending);
                    Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
                    Equal(1, root.ConcreteDisposeCalls); Equal(0, embedded.ConcreteDisposeCalls); Equal(0, embedded.Properties["Bytes"].ValueReads);
                }
                finally
                {
                    release.Set(); if (objectHandler != null) await CooperativeAwait(objectHandler);
                    sdk.EmitCompleted(ManagementStatus.AccessDenied); await InvocationSettled(pending);
                }
            }
        });

        AddAsync("Windows event binding converts raw object getter failure to fixed capture failure", async () =>
        {
            var sdk = new ManagementOperationObserver();
            var source = new WsabiWmiWindowsCallbackSource(sdk, (observer, request) =>
            {
                observer.EmitObjectReady(new ObjectReadyEventArgs(null) { OnGetNewObject = () => throw new InvalidOperationException("PRIVATE-SDK event getter") });
                observer.EmitCompleted(ManagementStatus.NoError);
            });
            await WindowsPrepareRawSource(source);
            await InvocationFailure(new WsabiWmiInvocationSnapshotTransport(source).ExchangeAsync(InvocationRequest(), CancellationToken.None));
            Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
        });

        AddAsync("Windows event binding never invents terminal status when the SDK status getter fails", async () =>
        {
            var sdk = new ManagementOperationObserver(); var ready = CooperativeCompletion();
            var source = new WsabiWmiWindowsCallbackSource(sdk, (observer, request) => ready.TrySetResult(true));
            await WindowsPrepareRawSource(source);
            var transport = new WsabiWmiInvocationSnapshotTransport(source);
            var pending = transport.ExchangeAsync(InvocationRequest(), CancellationToken.None);
            try
            {
                await CooperativeAwait(ready.Task); transport.RequestStop(); await InvocationEventually(() => transport.IsCompletionUnknown);
                sdk.EmitCompleted(new CompletedEventArgs(ManagementStatus.NoError) { OnGetStatus = () => throw new InvalidOperationException("PRIVATE-SDK status getter") });
                Check(!pending.IsCompleted && transport.IsCompletionUnknown, "status getter error synthesized method completion");
                Equal(1, sdk.ObjectReadySubscriberCount); Equal(1, sdk.CompletedSubscriberCount);
                sdk.EmitCompleted(ManagementStatus.AccessDenied);
                await InvocationFailure(pending);
                Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
            }
            finally { sdk.EmitCompleted(ManagementStatus.AccessDenied); await InvocationSettled(pending); }
        });

        AddAsync("Windows event binding keeps host ownership until unsubscribe attempts finish", async () =>
        {
            using (var release = new ManualResetEventSlim())
            {
                var sdk = new ManagementOperationObserver(); var ready = CooperativeCompletion(); var removing = CooperativeCompletion();
                sdk.BeforeRemove = name => { if (name == "ObjectReady") { removing.TrySetResult(true); WindowsBindingWait(release); } };
                ManagementBaseObject embedded; var root = WindowsOutputFixture(BoundChannelReply(), out embedded);
                var source = new WsabiWmiWindowsCallbackSource(sdk, (observer, request) => ready.TrySetResult(true));
                await WindowsPrepareRawSource(source);
                var gate = new CooperativeTestGate(); var session = WindowsBindingSession(source, gate);
                var published = CooperativeCompletion();
                var run = session.RunAndCloseAsync(0x34, BoundChannelPayload(), value => published.TrySetResult(true));
                Task terminal = null;
                try
                {
                    await CooperativeAwait(ready.Task); _ = session.RequestCloseAsync();
                    await InvocationEventually(() => session.IsCompletionUnknown); await CooperativeAwait(published.Task);
                    sdk.EmitObjectReady(root); terminal = Task.Run(() => sdk.EmitCompleted(ManagementStatus.NoError));
                    await CooperativeAwait(removing.Task);
                    Check(!run.IsCompleted && !session.IsCloseReady && gate.LastLease.IsHeld, "unsubscribe was detached from host lifetime");
                    Equal(1, root.ConcreteDisposeCalls); Equal(1, embedded.ConcreteDisposeCalls);
                    release.Set(); await CooperativeAwait(terminal); await CooperativeAwait(run);
                    AssertFrameExchangeFailure(await run, WsabiWmiFrameExchangeStatus.Cancelled);
                    Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
                    Check(session.IsCloseReady && !gate.LastLease.IsHeld, "owner exited before binding cleanup");
                    Equal(1, gate.LastLease.DisposeCalls); Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                }
                finally
                {
                    release.Set(); if (terminal == null) sdk.EmitCompleted(ManagementStatus.AccessDenied); else await CooperativeAwait(terminal);
                    await CooperativeAwait(session.RequestCloseAsync()); await CooperativeAwait(run);
                }
            }
        });

        AddAsync("Windows event binding unsubscribe failure is fixed failure and queued callbacks remain local", async () =>
        {
            var sdk = new ManagementOperationObserver();
            ManagementBaseObject embedded; var root = WindowsOutputFixture(BoundChannelReply(), out embedded);
            ObjectReadyEventHandler queued = null; int removals = 0;
            sdk.BeforeRemove = name => { removals++; if (name == "ObjectReady") throw new InvalidOperationException("PRIVATE-SDK remove detail"); };
            var source = new WsabiWmiWindowsCallbackSource(sdk, (observer, request) =>
            {
                queued = observer.ObjectReadySnapshot; observer.EmitObjectReady(root); observer.EmitCompleted(ManagementStatus.NoError);
            });
            await WindowsPrepareRawSource(source);
            await InvocationFailure(new WsabiWmiInvocationSnapshotTransport(source).ExchangeAsync(InvocationRequest(), CancellationToken.None));
            Equal(2, removals); Equal(1, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
            queued(sdk, new ObjectReadyEventArgs(root));
            Equal(1, root.ConcreteDisposeCalls); Equal(1, embedded.ConcreteDisposeCalls);
            var late = new ManagementBaseObject { OnGetProperties = () => throw new InvalidOperationException("PRIVATE-SDK late data must remain unread") };
            queued(sdk, new ObjectReadyEventArgs(late)); queued(sdk, new ObjectReadyEventArgs(late));
            Equal(1, late.ConcreteDisposeCalls); Equal(2, removals);
        });

        AddAsync("Windows event binding cleans partial subscription preparation failure before dispatch or synthetic terminal", async () =>
        {
            var sdk = new ManagementOperationObserver(); int calls = 0;
            sdk.BeforeAdd = name => { if (name == "Completed") throw new InvalidOperationException("PRIVATE-SDK subscribe detail"); };
            var source = new WsabiWmiWindowsCallbackSource(sdk, (observer, request) => calls++);
            var output = new CallbackRecordingObserver();
            Equal(WsabiWmiWindowsPreparationStatus.RegistrationFailed, await source.PrepareAsync(CancellationToken.None));
            Check(!source.TryReserve(), "failed preparation admitted a Core invocation");
            Equal(WsabiWmiWindowsCleanupStatus.Complete, await source.CloseUnusedAsync());
            Equal(0, calls); Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
            Equal(0, output.Terminals.Count); Equal(0, output.Captures); Equal(0, output.Failures);
        });

        AddAsync("Windows event binding canonical raw wrapper protects a selected reader from the same queued object", async () =>
        {
            using (var release = new ManualResetEventSlim())
            {
                var sdk = new ManagementOperationObserver(); var ready = CooperativeCompletion(); var reading = CooperativeCompletion();
                byte[] bytes = BoundChannelReply(); ManagementBaseObject embedded; var root = WindowsOutputFixture(bytes, out embedded);
                embedded.Properties["Bytes"].OnGetValue = () => { reading.TrySetResult(true); WindowsBindingWait(release); return bytes; };
                ObjectReadyEventHandler queued = null;
                var source = new WsabiWmiWindowsCallbackSource(sdk, (observer, request) => { queued = observer.ObjectReadySnapshot; ready.TrySetResult(true); });
                await WindowsPrepareRawSource(source);
                var transport = new WsabiWmiInvocationSnapshotTransport(source);
                var pending = transport.ExchangeAsync(InvocationRequest(), CancellationToken.None);
                Task terminal = null;
                try
                {
                    await CooperativeAwait(ready.Task); sdk.EmitObjectReady(root);
                    terminal = Task.Run(() => sdk.EmitCompleted(ManagementStatus.NoError));
                    await CooperativeAwait(reading.Task);
                    queued(sdk, new ObjectReadyEventArgs(root));
                    Equal(0, root.ConcreteDisposeCalls); Equal(0, embedded.ConcreteDisposeCalls);
                    Check(!pending.IsCompleted, "same raw SDK wrapper disposed selected output during read");
                    release.Set(); await CooperativeAwait(terminal);
                    // A raw handler admitted after Completed starts is an
                    // overlapping handoff, even if its reference is familiar.
                    await InvocationFailure(pending);
                    queued(sdk, new ObjectReadyEventArgs(root)); queued(sdk, new ObjectReadyEventArgs(root));
                    Equal(1, root.ConcreteDisposeCalls); Equal(1, embedded.ConcreteDisposeCalls);
                    Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
                }
                finally
                {
                    release.Set(); if (terminal == null) sdk.EmitCompleted(ManagementStatus.AccessDenied); else await CooperativeAwait(terminal);
                    await InvocationSettled(pending);
                }
            }
        });

        AddAsync("Windows event binding rejects an object admitted after completion inspection but before generic capture claim", async () =>
        {
            using (var allowTerminal = new ManualResetEventSlim())
            using (var allowObject = new ManualResetEventSlim())
            {
                var sdk = new ManagementOperationObserver(); var forwarding = CooperativeCompletion(); var readingObject = CooperativeCompletion();
                ManagementBaseObject embeddedA, embeddedB;
                var rootA = WindowsOutputFixture(BoundChannelReply(), out embeddedA);
                var rootB = WindowsOutputFixture(BoundChannelReply(), out embeddedB);
                var output = new CallbackRecordingObserver { OnTerminal = status =>
                {
                    if (status == 0) { forwarding.TrySetResult(true); WindowsBindingWait(allowTerminal); }
                }};
                var source = new WsabiWmiWindowsCallbackSource(sdk, (observer, request) => { });
                await WindowsPrepareRawSource(source);
                // Invoke really returned before the independent event tasks.
                source.Invoke(InvocationRequest(), output);
                sdk.EmitObjectReady(rootA);
                var terminal = Task.Run(() => sdk.EmitCompleted(ManagementStatus.NoError));
                Task arriving = null;
                try
                {
                    await CooperativeAwait(forwarding.Task);
                    arriving = Task.Run(() => sdk.EmitObjectReady(new ObjectReadyEventArgs(rootB) { OnGetNewObject = () =>
                    {
                        readingObject.TrySetResult(true); WindowsBindingWait(allowObject); return rootB;
                    }}));
                    await CooperativeAwait(readingObject.Task);
                    allowTerminal.Set(); await CooperativeAwait(terminal);
                    Equal(0, output.Captures); Equal(0, output.Failures);
                    Equal(1, sdk.ObjectReadySubscriberCount); Equal(1, sdk.CompletedSubscriberCount);
                    allowObject.Set(); await CooperativeAwait(arriving);
                    Equal(0, output.Captures); Equal(1, output.Failures);
                    Equal(1, rootA.ConcreteDisposeCalls); Equal(1, rootB.ConcreteDisposeCalls);
                    Equal(1, embeddedA.ConcreteDisposeCalls); Equal(0, embeddedB.ConcreteDisposeCalls);
                    Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
                }
                finally
                {
                    allowTerminal.Set(); allowObject.Set();
                    await CooperativeAwait(terminal); if (arriving != null) await CooperativeAwait(arriving);
                }
            }
        });

        AddAsync("Windows event binding terminal then dispatch throw preserves known cleanup and failed result", async () =>
        {
            var sdk = new ManagementOperationObserver(); int calls = 0;
            ManagementBaseObject embedded; var root = WindowsOutputFixture(BoundChannelReply(), out embedded);
            var source = new WsabiWmiWindowsCallbackSource(sdk, (observer, request) =>
            {
                calls++; observer.EmitObjectReady(root); observer.EmitCompleted(ManagementStatus.NoError);
                throw new InvalidOperationException("PRIVATE-SDK throw after final");
            });
            await WindowsPrepareRawSource(source);
            var gate = new CooperativeTestGate(); var session = WindowsBindingSession(source, gate);
            var result = await session.RunAndCloseAsync(0x34, BoundChannelPayload(), value => { });
            AssertFrameExchangeFailure(result, WsabiWmiFrameExchangeStatus.TransportFailure);
            Check(session.IsCloseReady && !session.IsCompletionUnknown && !gate.LastLease.IsHeld, "known terminal failure became unknown or skipped cleanup");
            Equal(1, calls); Equal(1, root.ConcreteDisposeCalls); Equal(1, embedded.ConcreteDisposeCalls);
            Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
            Equal(1, gate.LastLease.DisposeCalls); Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
        });
    }

    private static async Task WindowsPrepareRawSource(WsabiWmiWindowsCallbackSource source)
    {
        Equal(WsabiWmiWindowsPreparationStatus.Ready, await source.PrepareAsync(CancellationToken.None));
        Check(source.TryReserve(), "successful registration could not reserve its first invocation");
        Check(!source.TryReserve(), "registration allowed more than one invocation reservation");
    }

    private static WsabiWmiInvocationSession WindowsBindingSession(IWsabiWmiInvocationSource source,
        CooperativeTestGate gate, TimeSpan? timeout = null)
        => new WsabiWmiInvocationSession(BoundChannelBinder(), source, gate, TimeSpan.FromMilliseconds(200), timeout ?? TimeSpan.FromSeconds(3));

    private static void WindowsBindingWait(ManualResetEventSlim release)
    {
        if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("Stand-in event gate was not released.");
    }
}
