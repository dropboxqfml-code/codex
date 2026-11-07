using System;
using System.Collections.Generic;
using System.Management;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.WmiInterop;

internal static partial class Program
{
    private static void RegisterWsabiWmiWindowsPreparationTests()
    {
        AddAsync("Windows preparation validates dependencies before registration and pre cancellation exposes no invocation", async () =>
        {
            var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate();
            Action<ManagementOperationObserver, WsabiWmiMethodRequest> dispatch = (observer, request) => { };
            TimeSpan wait = TimeSpan.FromMilliseconds(200);
            BatteryThrows<ArgumentNullException>(() => WsabiWmiWindowsPreparation.PrepareAsync(null, dispatch, BoundChannelBinder(), gate, wait, wait));
            BatteryThrows<ArgumentNullException>(() => WsabiWmiWindowsPreparation.PrepareAsync(sdk, null, BoundChannelBinder(), gate, wait, wait));
            BatteryThrows<ArgumentNullException>(() => WsabiWmiWindowsPreparation.PrepareAsync(sdk, dispatch, null, gate, wait, wait));
            BatteryThrows<ArgumentNullException>(() => WsabiWmiWindowsPreparation.PrepareAsync(sdk, dispatch, BoundChannelBinder(), null, wait, wait));
            BatteryThrows<ArgumentOutOfRangeException>(() => WsabiWmiWindowsPreparation.PrepareAsync(sdk, dispatch, BoundChannelBinder(), gate, TimeSpan.Zero, wait));
            BatteryThrows<ArgumentOutOfRangeException>(() => WsabiWmiWindowsPreparation.PrepareAsync(sdk, dispatch, BoundChannelBinder(), gate, wait, TimeSpan.Zero));
            int adds = 0; sdk.BeforeAdd = name => adds++;
            using (var caller = new CancellationTokenSource())
            {
                caller.Cancel();
                var cancelled = await PrepareWindowsTest(sdk, dispatch, gate, caller.Token);
                AssertWindowsPreparationFailure(cancelled, WsabiWmiWindowsPreparationStatus.Cancelled);
                Equal(0, adds); Equal(0, gate.Calls);
            }
            // Cancellation before registration did not claim this observer.
            var ready = await PrepareWindowsTest(sdk, dispatch, gate);
            Check(ready.IsReady, "pre-cancelled or invalid input consumed registration");
            Equal(WsabiWmiWindowsCleanupStatus.Complete, await ready.Invocation.RequestCloseAsync());
            Equal(2, adds); Equal(0, gate.Calls);
        });

        AddAsync("Windows preparation cleans both attempted adds including mutate then throw without dispatch", async () =>
        {
            foreach (string failingName in new[] { "ObjectReady", "Completed" })
            foreach (bool afterMutation in new[] { false, true })
            {
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate();
                var removals = new List<string>(); int adds = 0, calls = 0;
                sdk.BeforeAdd = name =>
                {
                    adds++; if (!afterMutation && name == failingName) throw new InvalidOperationException("PRIVATE-SDK before-add detail");
                };
                sdk.AfterAdd = name => { if (afterMutation && name == failingName) throw new InvalidOperationException("PRIVATE-SDK after-add detail"); };
                sdk.BeforeRemove = name => removals.Add(name);
                var result = await PrepareWindowsTest(sdk, (observer, request) => calls++, gate);
                AssertWindowsPreparationFailure(result, WsabiWmiWindowsPreparationStatus.RegistrationFailed);
                Equal(failingName == "ObjectReady" ? 1 : 2, adds); Equal(adds, removals.Count);
                Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
                Equal(0, calls); Equal(0, gate.Calls);
                int previousAdds = adds;
                var again = await PrepareWindowsTest(sdk, (observer, request) => calls++, gate);
                AssertWindowsPreparationFailure(again, WsabiWmiWindowsPreparationStatus.ObserverUnavailable);
                Equal(previousAdds, adds); Equal(0, calls);
            }
        });

        AddAsync("Windows preparation cancellation waits for an in flight add before removing its registration", async () =>
        {
            using (var release = new ManualResetEventSlim())
            using (var caller = new CancellationTokenSource())
            {
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate();
                var entered = CooperativeCompletion(); int removals = 0, calls = 0;
                sdk.AfterAdd = name => { if (name == "ObjectReady") { entered.TrySetResult(true); WindowsBindingWait(release); } };
                sdk.BeforeRemove = name => Interlocked.Increment(ref removals);
                var pending = PrepareWindowsTest(sdk, (observer, request) => calls++, gate, caller.Token);
                try
                {
                    await CooperativeAwait(entered.Task); caller.Cancel();
                    Check(!pending.IsCompleted, "preparation returned while add could still install a handler");
                    Equal(1, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
                    Equal(0, Volatile.Read(ref removals)); Equal(0, calls); Equal(0, gate.Calls);
                    release.Set();
                    var result = await pending;
                    AssertWindowsPreparationFailure(result, WsabiWmiWindowsPreparationStatus.Cancelled);
                    Equal(1, removals); Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
                }
                finally { release.Set(); await CooperativeAwait(pending); }
            }
        });

        AddAsync("Windows preparation cleanup failure dominates registration error and cancellation and prevents observer reuse", async () =>
        {
            using (var caller = new CancellationTokenSource())
            {
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); int calls = 0, removes = 0;
                sdk.AfterAdd = name => { caller.Cancel(); throw new InvalidOperationException("PRIVATE-SDK registration detail"); };
                sdk.BeforeRemove = name => { removes++; throw new InvalidOperationException("PRIVATE-SDK cleanup detail"); };
                var result = await PrepareWindowsTest(sdk, (observer, request) => calls++, gate, caller.Token);
                AssertWindowsPreparationFailure(result, WsabiWmiWindowsPreparationStatus.CleanupFailed);
                Equal(0, calls); Equal(0, gate.Calls); Equal(1, removes); Equal(1, sdk.ObjectReadySubscriberCount);
                AssertWindowsPreparationFailure(await PrepareWindowsTest(sdk, (observer, request) => calls++, gate), WsabiWmiWindowsPreparationStatus.ObserverUnavailable);
                Equal(1, removes); Equal(0, calls);
            }
        });

        AddAsync("Windows preparation rejects early objects and statuses without replay reading output or inventing terminal", async () =>
        {
            foreach (bool objectEvent in new[] { false, true })
            foreach (bool cancelAlso in new[] { false, true })
            using (var caller = new CancellationTokenSource())
            {
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); int calls = 0;
                var raw = new ManagementBaseObject { OnGetProperties = () => throw new InvalidOperationException("PRIVATE-SDK early output must stay unread") };
                var completed = new CompletedEventArgs(ManagementStatus.NoError)
                {
                    OnGetStatus = () => throw new InvalidOperationException("PRIVATE-SDK early status must stay unread")
                };
                sdk.AfterAdd = name =>
                {
                    if (objectEvent && name == "ObjectReady")
                    {
                        if (cancelAlso) caller.Cancel();
                        sdk.EmitObjectReady(raw); sdk.EmitObjectReady(raw);
                    }
                    if (!objectEvent && name == "Completed")
                    {
                        if (cancelAlso) caller.Cancel();
                        sdk.EmitCompleted(completed);
                    }
                };
                var result = await PrepareWindowsTest(sdk, (observer, request) => calls++, gate, caller.Token);
                AssertWindowsPreparationFailure(result, WsabiWmiWindowsPreparationStatus.UnexpectedCallback);
                Equal(objectEvent ? 1 : 0, raw.ConcreteDisposeCalls); Equal(0, completed.StatusReads);
                Equal(0, calls); Equal(0, gate.Calls); Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
            }
        });

        AddAsync("Windows preparation joins an entered early object's disposal before failure cleanup finishes", async () =>
        {
            using (var entered = new ManualResetEventSlim())
            using (var release = new ManualResetEventSlim())
            {
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate();
                int calls = 0, removes = 0; Task callback = null;
                var callbackScheduled = CooperativeCompletion();
                var raw = new ManagementBaseObject { OnDispose = () => { entered.Set(); WindowsBindingWait(release); } };
                sdk.AfterAdd = name =>
                {
                    if (name != "ObjectReady") return;
                    callback = Task.Run(() => sdk.EmitObjectReady(raw));
                    callbackScheduled.TrySetResult(true);
                    if (!entered.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException();
                };
                sdk.BeforeRemove = name => Interlocked.Increment(ref removes);
                var pending = PrepareWindowsTest(sdk, (observer, request) => calls++, gate);
                try
                {
                    await CooperativeAwait(callbackScheduled.Task);
                    await InvocationEventually(() => entered.IsSet);
                    Check(!pending.IsCompleted && !callback.IsCompleted, "preparation ignored an entered early object's cleanup");
                    Equal(0, Volatile.Read(ref removes)); Equal(0, calls); Equal(0, gate.Calls);
                    release.Set(); await CooperativeAwait(callback);
                    AssertWindowsPreparationFailure(await pending, WsabiWmiWindowsPreparationStatus.UnexpectedCallback);
                    Equal(1, raw.ConcreteDisposeCalls); Equal(1, removes); Equal(0, sdk.ObjectReadySubscriberCount);
                }
                finally { release.Set(); if (callback != null) await CooperativeAwait(callback); await CooperativeAwait(pending); }
            }
        });

        AddAsync("Windows preparation invalidated while ready rejects run and cleans registration before any exchange", async () =>
        {
            var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); int calls = 0, reports = 0;
            var result = await PrepareWindowsTest(sdk, (observer, request) => calls++, gate);
            Check(result.IsReady, "registration was not initially ready");
            var raw = new ManagementBaseObject { OnGetProperties = () => throw new InvalidOperationException("PRIVATE-SDK early output must stay unread") };
            sdk.EmitObjectReady(raw);
            await InvocationFailure(result.Invocation.RunAndCloseAsync(0x34, BoundChannelPayload(), value => reports++));
            Equal(1, raw.ConcreteDisposeCalls); Equal(0, calls); Equal(0, reports); Equal(0, gate.Calls);
            Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
            Equal(WsabiWmiWindowsCleanupStatus.Complete, await result.Invocation.RequestCloseAsync());
        });

        AddAsync("Windows prepared unused close reports failed cleanup once and refuses later run", async () =>
        {
            var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); int calls = 0, removes = 0;
            var result = await PrepareWindowsTest(sdk, (observer, request) => calls++, gate);
            sdk.BeforeRemove = name => { removes++; if (name == "ObjectReady") throw new InvalidOperationException("PRIVATE-SDK unused cleanup detail"); };
            var close = result.Invocation.RequestCloseAsync();
            Check(ReferenceEquals(close, result.Invocation.RequestCloseAsync()), "unused close created a second cleanup");
            Equal(WsabiWmiWindowsCleanupStatus.Failed, await close);
            BatteryThrows<InvalidOperationException>(() => result.Invocation.RunAndCloseAsync(0x34, BoundChannelPayload(), value => { }));
            Equal(0, calls); Equal(0, gate.Calls); Equal(2, removes);
            Equal(1, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
        });

        AddAsync("Windows preparation preserves registration error over a simultaneous cancellation", async () =>
        {
            using (var caller = new CancellationTokenSource())
            {
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); int calls = 0;
                sdk.AfterAdd = name => { caller.Cancel(); throw new InvalidOperationException("PRIVATE-SDK registration detail"); };
                var result = await PrepareWindowsTest(sdk, (observer, request) => calls++, gate, caller.Token);
                AssertWindowsPreparationFailure(result, WsabiWmiWindowsPreparationStatus.RegistrationFailed);
                Equal(0, calls); Equal(0, gate.Calls); Equal(0, sdk.ObjectReadySubscriberCount);
            }
        });
    }

    private static Task<WsabiWmiWindowsPreparationResult> PrepareWindowsTest(ManagementOperationObserver sdk,
        Action<ManagementOperationObserver, WsabiWmiMethodRequest> dispatch, CooperativeTestGate gate,
        CancellationToken token = default(CancellationToken), TimeSpan? responseTimeout = null)
        => WsabiWmiWindowsPreparation.PrepareAsync(sdk, dispatch, BoundChannelBinder(), gate,
            TimeSpan.FromMilliseconds(200), responseTimeout ?? TimeSpan.FromSeconds(3), token);

    private static void AssertWindowsPreparationFailure(WsabiWmiWindowsPreparationResult result, WsabiWmiWindowsPreparationStatus expected)
    {
        Equal(expected, result.Status);
        Check(!result.IsReady && result.Invocation == null, "failed preparation exposed a runnable invocation");
    }
}
