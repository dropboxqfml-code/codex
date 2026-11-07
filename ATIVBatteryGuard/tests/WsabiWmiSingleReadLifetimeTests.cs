using System;
using System.Collections.Generic;
using System.Linq;
using System.Management;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.WmiInterop;

internal static partial class Program
{
    // Public single-read policy/preparation/host flow with SDK stand-ins and
    // the existing synthetic request. No real template or SDK call is used.
    private static void RegisterWsabiWmiSingleReadLifetimeTests()
    {
        AddAsync("single read lifetime concurrent wrappers consume one plan before observer registration", async () =>
        {
            {
                var start = CooperativeCompletion();
                var arrived = CooperativeCompletion();
                int waiting = 0;
                var target = SingleReadTarget(new object());
                var plan = SingleReadPlanCreate(target);
                var sdk = new[] { new ManagementOperationObserver(), new ManagementOperationObserver() };
                var gates = new[] { new CooperativeTestGate(), new CooperativeTestGate() };
                var adds = new int[2]; var dispatches = new int[2];
                var bindings = new WsabiWmiWindowsReadTrialBinding[2];
                for (int index = 0; index < 2; index++)
                {
                    int selected = index;
                    sdk[index].BeforeAdd = name => Interlocked.Increment(ref adds[selected]);
                    bindings[index] = new WsabiWmiWindowsReadTrialBinding(target, sdk[index], (observer, request) =>
                    {
                        Interlocked.Increment(ref dispatches[selected]);
                        ManagementBaseObject embedded;
                        var root = WindowsOutputFixture(BoundChannelReply(), out embedded);
                        observer.EmitObjectReady(root); observer.EmitCompleted(ManagementStatus.NoError);
                    });
                }
                var first = Task.Run(async () =>
                {
                    if (Interlocked.Increment(ref waiting) == 2) arrived.TrySetResult(true);
                    await start.Task;
                    return await SingleReadLifePrepare(plan, bindings[0], gates[0]);
                });
                var second = Task.Run(async () =>
                {
                    if (Interlocked.Increment(ref waiting) == 2) arrived.TrySetResult(true);
                    await start.Task;
                    return await SingleReadLifePrepare(plan, bindings[1], gates[1]);
                });
                try
                {
                    await CooperativeAwait(arrived.Task);
                    start.TrySetResult(true);
                    var results = await Task.WhenAll(first, second);
                    int winner = results[0].IsReady ? 0 : 1, loser = 1 - winner;
                    Equal(WsabiWmiSingleReadPreparationStatus.Ready, results[winner].Status);
                    Equal(WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed, results[loser].Status);
                    Check(results[loser].Invocation == null && results[loser].RegistrationStatus == null,
                        "same plan loser reached Windows preparation");
                    Equal(2, adds[winner]); Equal(0, adds[loser]);
                    Equal(1, sdk[winner].ObjectReadySubscriberCount); Equal(1, sdk[winner].CompletedSubscriberCount);
                    SingleReadLifeAssertUnsubscribed(sdk[loser]);
                    Equal(0, gates[0].Calls); Equal(0, gates[1].Calls);
                    int publications = 0;
                    var result = await results[winner].Invocation.RunAndCloseAsync(value => Interlocked.Increment(ref publications));
                    Check(result.IsValidFrame, "winning frozen policy request did not reach existing reply validation");
                    Equal(1, publications); Equal(1, dispatches[winner]); Equal(0, dispatches[loser]);
                    Equal(1, gates[winner].Calls); Equal(0, gates[loser].Calls);
                    Equal(1, gates[winner].LastLease.DisposeCalls);
                    Equal(gates[winner].AcquireThread, gates[winner].LastLease.DisposeThread);
                    BatteryThrows<InvalidOperationException>(() => results[winner].Invocation.RunAndCloseAsync(value => { }));
                    SingleReadLifeAssertUnsubscribed(sdk[0]); SingleReadLifeAssertUnsubscribed(sdk[1]);
                }
                finally
                {
                    start.TrySetResult(true);
                    try { await SingleReadLifeClosePreparation(first); }
                    finally { await SingleReadLifeClosePreparation(second); }
                }
            }
        });

        AddAsync("single read lifetime preparation cancellation or registration failure never rearms the same plan", async () =>
        {
            foreach (bool cancelPreparation in new[] { true, false })
            using (var caller = new CancellationTokenSource())
            {
                var identity = new object();
                var target = SingleReadTarget(identity);
                var plan = SingleReadPlanCreate(target);
                var sdk = new ManagementOperationObserver(); var aliasSdk = new ManagementOperationObserver();
                var gate = new CooperativeTestGate(); var aliasGate = new CooperativeTestGate();
                int dispatches = 0, aliasDispatches = 0, adds = 0, aliasAdds = 0;
                sdk.BeforeAdd = name =>
                {
                    Interlocked.Increment(ref adds);
                    if (!cancelPreparation && name == "Completed") throw new InvalidOperationException("PRIVATE-SDK trial registration detail");
                };
                aliasSdk.BeforeAdd = name => Interlocked.Increment(ref aliasAdds);
                if (cancelPreparation) caller.Cancel();
                var first = SingleReadLifePrepare(plan,
                    new WsabiWmiWindowsReadTrialBinding(target, sdk, (observer, request) => Interlocked.Increment(ref dispatches)),
                    gate, preparationToken: caller.Token);
                Task<WsabiWmiSingleReadPreparationResult> second = null;
                try
                {
                    var failed = await first;
                    Equal(WsabiWmiSingleReadPreparationStatus.PreparationNotReady, failed.Status);
                    Equal((WsabiWmiWindowsPreparationStatus?)(cancelPreparation
                        ? WsabiWmiWindowsPreparationStatus.Cancelled : WsabiWmiWindowsPreparationStatus.RegistrationFailed), failed.RegistrationStatus);
                    Check(!failed.IsReady && failed.Invocation == null, "failed preparation returned a runnable fixed-read handle");
                    second = SingleReadLifePrepare(plan,
                        new WsabiWmiWindowsReadTrialBinding(SingleReadTarget(identity), aliasSdk,
                            (observer, request) => Interlocked.Increment(ref aliasDispatches)), aliasGate);
                    var retry = await second;
                    Equal(WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed, retry.Status);
                    Check(retry.Invocation == null && retry.RegistrationStatus == null, "failed plan was rearmed by another binding");
                    Equal(cancelPreparation ? 0 : 2, adds); Equal(0, aliasAdds);
                    Equal(0, gate.Calls); Equal(0, aliasGate.Calls); Equal(0, dispatches); Equal(0, aliasDispatches);
                    SingleReadLifeAssertUnsubscribed(sdk); SingleReadLifeAssertUnsubscribed(aliasSdk);
                }
                finally
                {
                    try { await SingleReadLifeClosePreparation(first); }
                    finally { if (second != null) await SingleReadLifeClosePreparation(second); }
                }
            }
        });

        AddAsync("single read lifetime unused close wins before a runtime request can be selected or dispatched", async () =>
        {
            var target = SingleReadTarget(new object()); var plan = SingleReadPlanCreate(target);
            var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); int calls = 0;
            var invocation = await SingleReadLifeReady(SingleReadLifePrepare(plan,
                new WsabiWmiWindowsReadTrialBinding(target, sdk, (observer, request) => Interlocked.Increment(ref calls)), gate));
            try
            {
                Check(!invocation.CanInvokeMethods && !invocation.CanReadHardware && !invocation.CanWriteHardware,
                    "single-read policy granted hardware authority");
                var close = invocation.RequestCloseAsync();
                Check(ReferenceEquals(close, invocation.RequestCloseAsync()), "fixed-read close allocated another cleanup");
                BatteryThrows<InvalidOperationException>(() => invocation.RunAndCloseAsync(value => { }));
                Equal(WsabiWmiWindowsCleanupStatus.Complete, await close);
                Equal(0, gate.Calls); Equal(0, calls);
                SingleReadLifeAssertUnsubscribed(sdk);
            }
            finally { await CooperativeAwait(invocation.RequestCloseAsync()); }
        });

        AddAsync("single read lifetime unknown dispatch retains fixed request ownership after timeout or caller stop", async () =>
        {
            foreach (bool callerStops in new[] { false, true })
            using (var caller = new CancellationTokenSource())
            {
                var target = SingleReadTarget(new object()); var plan = SingleReadPlanCreate(target);
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate();
                var entered = CooperativeCompletion(); var published = CooperativeCompletion();
                int dispatches = 0, publications = 0, outputReads = 0;
                WsabiWmiFrameExchangeResult shown = null;
                var root = new ManagementBaseObject { OnGetProperties = () =>
                {
                    Interlocked.Increment(ref outputReads);
                    throw new InvalidOperationException("PRIVATE-SDK unknown trial output must stay unread");
                }};
                var invocation = await SingleReadLifeReady(SingleReadLifePrepare(plan,
                    new WsabiWmiWindowsReadTrialBinding(target, sdk, (observer, request) =>
                    {
                        Interlocked.Increment(ref dispatches);
                        observer.EmitObjectReady(root); entered.TrySetResult(true);
                        throw new InvalidOperationException("PRIVATE-SDK trial dispatch detail");
                    }), gate, responseTimeout: callerStops ? TimeSpan.FromSeconds(3) : TimeSpan.FromMilliseconds(500)));
                var run = invocation.RunAndCloseAsync(value =>
                {
                    Interlocked.Increment(ref publications); shown = value; published.TrySetResult(true);
                }, caller.Token);
                try
                {
                    await CooperativeAwait(entered.Task);
                    if (callerStops) caller.Cancel();
                    await CooperativeAwait(published.Task);
                    AssertFrameExchangeFailure(shown, callerStops ? WsabiWmiFrameExchangeStatus.Cancelled : WsabiWmiFrameExchangeStatus.TimedOut);
                    var close = invocation.RequestCloseAsync();
                    Check(!run.IsCompleted && !close.IsCompleted && gate.LastLease.IsHeld,
                        "fixed-read policy ended unknown lifetime at the bounded UI result");
                    Equal(0, root.ConcreteDisposeCalls); Equal(0, outputReads);
                    Equal(1, sdk.ObjectReadySubscriberCount); Equal(1, sdk.CompletedSubscriberCount);
                    caller.Cancel(); caller.Cancel();
                    Check(!run.IsCompleted && !close.IsCompleted, "repeated fixed-read stop created a terminal");
                    BatteryThrows<InvalidOperationException>(() => invocation.RunAndCloseAsync(value => { }));
                    Equal(1, dispatches);
                    sdk.EmitCompleted(ManagementStatus.AccessDenied); // Explicit fake terminal, not SDK evidence.
                    await CooperativeAwait(run);
                    Check(ReferenceEquals(shown, await run), "late cleanup replaced the fixed-read UI result");
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await close);
                    Equal(1, publications); Equal(1, dispatches); Equal(0, outputReads);
                    Equal(1, root.ConcreteDisposeCalls); Equal(1, gate.LastLease.DisposeCalls);
                    Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                    Check(!gate.LastLease.IsHeld, "fixed-read unknown cleanup skipped owner release");
                    SingleReadLifeAssertUnsubscribed(sdk);
                }
                finally
                {
                    var cleanup = invocation.RequestCloseAsync();
                    try
                    {
                        if (Volatile.Read(ref dispatches) == 0 && !run.IsCompleted)
                            await CooperativeAwait(Task.WhenAny(entered.Task, run));
                    }
                    finally
                    {
                        try
                        {
                            if (Volatile.Read(ref dispatches) != 0) sdk.EmitCompleted(ManagementStatus.AccessDenied);
                        }
                        finally
                        {
                            try { await CooperativeAwait(cleanup); }
                            finally { await CooperativeAwait(run); }
                        }
                    }
                }
            }
        });

        AddAsync("single read lifetime close joins an admitted gate before removing unused fixed-read subscriptions", async () =>
        {
            using (var releaseAcquire = new ManualResetEventSlim())
            {
                var target = SingleReadTarget(new object()); var plan = SingleReadPlanCreate(target);
                var sdk = new ManagementOperationObserver(); var entered = CooperativeCompletion(); var published = CooperativeCompletion();
                var lease = new CooperativeTestLease();
                var gate = new CooperativeTestGate { Handler = (timeout, stop) =>
                {
                    entered.TrySetResult(true); SingleReadLifeWait(releaseAcquire);
                    return new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired, lease);
                }};
                int dispatches = 0, publications = 0; WsabiWmiFrameExchangeResult shown = null;
                var invocation = await SingleReadLifeReady(SingleReadLifePrepare(plan,
                    new WsabiWmiWindowsReadTrialBinding(target, sdk, (observer, request) =>
                    {
                        Interlocked.Increment(ref dispatches); observer.EmitCompleted(ManagementStatus.AccessDenied);
                    }), gate));
                var run = invocation.RunAndCloseAsync(value =>
                {
                    Interlocked.Increment(ref publications); shown = value; published.TrySetResult(true);
                });
                try
                {
                    await CooperativeAwait(entered.Task);
                    var close = invocation.RequestCloseAsync();
                    await CooperativeAwait(published.Task);
                    AssertFrameExchangeFailure(shown, WsabiWmiFrameExchangeStatus.Cancelled);
                    Check(!run.IsCompleted && !close.IsCompleted, "fixed-read close skipped blocked acquisition cleanup");
                    Equal(1, sdk.ObjectReadySubscriberCount); Equal(1, sdk.CompletedSubscriberCount);
                    Equal(0, dispatches); Equal(0, lease.DisposeCalls);
                    releaseAcquire.Set();
                    await CooperativeAwait(run);
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await close);
                    Equal(0, dispatches); Equal(1, publications); Equal(1, gate.Calls);
                    Equal(1, lease.DisposeCalls); Equal(gate.AcquireThread, lease.DisposeThread);
                    Check(!lease.IsHeld, "fixed-read close ended before acquired lease release");
                    SingleReadLifeAssertUnsubscribed(sdk);
                }
                finally
                {
                    var close = invocation.RequestCloseAsync();
                    try
                    {
                        try { await CooperativeAwait(published.Task); }
                        finally { releaseAcquire.Set(); }
                    }
                    finally
                    {
                        try { await CooperativeAwait(close); }
                        finally { await CooperativeAwait(run); }
                    }
                }
            }
        });

        AddAsync("single read lifetime freezes caller request copies and waits for cleanup after reporting throws", async () =>
        {
            using (var preparation = new CancellationTokenSource())
            using (var releaseLease = new ManualResetEventSlim())
            {
                var target = SingleReadTarget(new object()); var originalTarget = target;
                var plan = SingleReadPlanCreate(target);
                var sdk = new ManagementOperationObserver(); var published = CooperativeCompletion();
                var lease = new CooperativeTestLease { OnDispose = () => SingleReadLifeWait(releaseLease) };
                var gate = new CooperativeTestGate { Handler = (timeout, stop) =>
                    new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired, lease) };
                byte[] original = BoundChannelRequest();
                WsabiWmiMethodRequest request = SingleReadLifeRequest(plan, original);
                ManagementBaseObject embedded; var root = WindowsOutputFixture(BoundChannelReply(), out embedded);
                byte[] observed = null; int dispatches = 0, publications = 0;
                var invocation = await SingleReadLifeReady(SingleReadLifePrepare(plan,
                    new WsabiWmiWindowsReadTrialBinding(target, sdk, (observer, supplied) =>
                    {
                        Interlocked.Increment(ref dispatches); observed = supplied.Frame;
                        observer.EmitObjectReady(root); observer.EmitCompleted(ManagementStatus.NoError);
                    }), gate, request, preparationToken: preparation.Token));
                original[5] ^= 0xff;
                byte[] view = request.Frame; view[6] ^= 0xff;
                var arguments = (IReadOnlyDictionary<string, object>)request.Arguments["inData"];
                ((byte[])arguments["Bytes"])[7] ^= 0xff;
                target = SingleReadTarget(new object(), bios: "OtherBIOS");
                preparation.Cancel(); // Ready is already committed; this token no longer revokes it.
                var run = invocation.RunAndCloseAsync(value =>
                {
                    Interlocked.Increment(ref publications); published.TrySetResult(true);
                    throw new SingleReadLifeReportException();
                });
                try
                {
                    await CooperativeAwait(lease.DisposeEntered.Task);
                    Check(observed != null && observed.SequenceEqual(BoundChannelRequest()) && request.Frame.SequenceEqual(BoundChannelRequest()),
                        "caller copies changed the request after policy validation");
                    Check(plan.MatchesTarget(originalTarget) && !plan.MatchesTarget(target), "caller target reassignment changed the immutable plan");
                    Equal(1, dispatches); Equal(1, root.ConcreteDisposeCalls); Equal(1, embedded.ConcreteDisposeCalls);
                    SingleReadLifeAssertUnsubscribed(sdk);
                    var close = invocation.RequestCloseAsync();
                    await CooperativeAwait(published.Task);
                    Check(!run.IsCompleted && !close.IsCompleted && lease.IsHeld,
                        "report exception bypassed the fixed-read owner cleanup");
                    releaseLease.Set();
                    await SingleReadLifeExpectReportFailure(run);
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await close);
                    Equal(1, publications); Equal(1, dispatches); Equal(1, lease.DisposeCalls);
                    Equal(gate.AcquireThread, lease.DisposeThread); Check(!lease.IsHeld, "report fault escaped before lease release");
                }
                finally
                {
                    var close = invocation.RequestCloseAsync(); releaseLease.Set();
                    try { await CooperativeAwait(close); }
                    finally { await SingleReadLifeExpectReportFailure(run); }
                }
            }
        });
    }

    private static Task<WsabiWmiSingleReadPreparationResult> SingleReadLifePrepare(WsabiWmiSingleReadPlan plan,
        WsabiWmiWindowsReadTrialBinding binding, CooperativeTestGate gate,
        WsabiWmiMethodRequest request = null, TimeSpan? responseTimeout = null,
        CancellationToken preparationToken = default(CancellationToken))
        => WsabiWmiWindowsSingleReadPreparation.PrepareAsync(plan, binding, request ?? SingleReadLifeRequest(plan), gate,
            TimeSpan.FromMilliseconds(200), responseTimeout ?? TimeSpan.FromSeconds(3), preparationToken);

    private static WsabiWmiMethodRequest SingleReadLifeRequest(WsabiWmiSingleReadPlan plan, byte[] original = null)
    {
        WsabiWmiMethodRequest request;
        Check(plan.Binder.TryWrapFrame(original ?? BoundChannelRequest(), out request), "existing synthetic fixed-read fixture was rejected");
        return request;
    }

    private static async Task<WsabiWmiWindowsSingleReadInvocation> SingleReadLifeReady(Task<WsabiWmiSingleReadPreparationResult> preparation)
    {
        var result = await preparation;
        Equal(WsabiWmiSingleReadPreparationStatus.Ready, result.Status);
        Check(result.IsReady && result.Invocation != null, "fixed-read fixture did not produce a ready handle");
        return result.Invocation;
    }

    private static async Task SingleReadLifeClosePreparation(Task<WsabiWmiSingleReadPreparationResult> preparation)
    {
        var result = await preparation;
        if (result.Invocation != null) await CooperativeAwait(result.Invocation.RequestCloseAsync());
    }

    private static void SingleReadLifeAssertUnsubscribed(ManagementOperationObserver sdk)
    {
        Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
    }

    private static void SingleReadLifeWait(ManualResetEventSlim release)
    {
        if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("Fixed-read lifetime fake gate was not released.");
    }

    private static async Task SingleReadLifeExpectReportFailure(Task run)
    {
        try { await CooperativeAwait(run); }
        catch (SingleReadLifeReportException) { return; }
        throw new InvalidOperationException("The fixed-read reporter failure was not retained.");
    }

    private sealed class SingleReadLifeReportException : Exception
    {
        internal SingleReadLifeReportException() : base("Fixed single-read lifetime report failure.") { }
    }
}
