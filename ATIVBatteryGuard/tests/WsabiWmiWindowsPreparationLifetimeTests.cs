using System;
using System.Management;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.WmiInterop;

internal static partial class Program
{
    // Production preparation/host code with test-only SDK stand-ins and the
    // existing synthetic framing fixtures. No SDK/provider or device executes.
    private static void RegisterWsabiWmiWindowsPreparationLifetimeTests()
    {
        AddAsync("prepared invocation unused close prevents first run and shares one cleanup", async () =>
        {
            using (var releaseRemove = new ManualResetEventSlim())
            {
                var sdk = new ManagementOperationObserver();
                var gate = new CooperativeTestGate();
                var removing = CooperativeCompletion();
                int dispatches = 0;
                var invocation = await PrepLifetimePrepare(sdk, (observer, request) =>
                    Interlocked.Increment(ref dispatches), gate);
                sdk.BeforeRemove = name =>
                {
                    if (name == "ObjectReady") { removing.TrySetResult(true); PrepLifetimeWait(releaseRemove); }
                };
                Task<WsabiWmiWindowsCleanupStatus> close = null;
                try
                {
                    Check(!invocation.CanInvokeMethods && !invocation.CanReadHardware && !invocation.CanWriteHardware,
                        "prepared registration became hardware authority");
                    close = invocation.RequestCloseAsync();
                    Check(ReferenceEquals(close, invocation.RequestCloseAsync()), "unused close allocated a second cleanup");
                    await CooperativeAwait(removing.Task);
                    Check(!close.IsCompleted, "unused close ended before its unsubscribe attempt");
                    BatteryThrows<InvalidOperationException>(() => invocation.RunAndCloseAsync(
                        0x34, BoundChannelPayload(), result => { }));
                    Equal(0, gate.Calls); Equal(0, Volatile.Read(ref dispatches));
                    releaseRemove.Set();
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await close);
                    PrepLifetimeAssertUnsubscribed(sdk);
                    Check(ReferenceEquals(close, invocation.RequestCloseAsync()), "completed close did not stay single use");
                }
                finally
                {
                    releaseRemove.Set();
                    await CooperativeAwait(invocation.RequestCloseAsync());
                }
            }
        });

        AddAsync("prepared invocation successful run survives cancellation of its completed preparation token", async () =>
        {
            using (var preparation = new CancellationTokenSource())
            {
                var sdk = new ManagementOperationObserver();
                var gate = new CooperativeTestGate();
                ManagementBaseObject embedded;
                var root = WindowsOutputFixture(BoundChannelReply(), out embedded);
                int dispatches = 0, publications = 0;
                WsabiWmiFrameExchangeResult shown = null;
                var invocation = await PrepLifetimePrepare(sdk, (observer, request) =>
                {
                    Interlocked.Increment(ref dispatches);
                    observer.EmitObjectReady(root);
                    observer.EmitCompleted(ManagementStatus.NoError);
                }, gate, preparationToken: preparation.Token);
                preparation.Cancel();
                try
                {
                    var result = await invocation.RunAndCloseAsync(0x34, BoundChannelPayload(), value =>
                    {
                        Interlocked.Increment(ref publications); shown = value;
                    });
                    Check(result.IsValidFrame && ReferenceEquals(result, shown), "Ready token cancellation invalidated or replaced the run result");
                    Equal(1, Volatile.Read(ref dispatches)); Equal(1, Volatile.Read(ref publications)); Equal(1, gate.Calls);
                    Equal(1, root.ConcreteDisposeCalls); Equal(1, embedded.ConcreteDisposeCalls);
                    Equal(1, gate.LastLease.DisposeCalls); Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                    Check(!gate.LastLease.IsHeld, "successful prepared host returned before owner cleanup");
                    PrepLifetimeAssertUnsubscribed(sdk);
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await invocation.RequestCloseAsync());
                    BatteryThrows<InvalidOperationException>(() => invocation.RunAndCloseAsync(
                        0x34, BoundChannelPayload(), value => { }));
                    Equal(1, Volatile.Read(ref dispatches));
                }
                finally { await CooperativeAwait(invocation.RequestCloseAsync()); }
            }
        });

        AddAsync("prepared invocation local request cancellation and denied gate avoid source dispatch and release registrations", async () =>
        {
            for (int scenario = 0; scenario < 3; scenario++)
            using (var caller = new CancellationTokenSource())
            {
                var sdk = new ManagementOperationObserver();
                var gate = new CooperativeTestGate();
                if (scenario == 2) gate.Handler = (timeout, stop) =>
                    new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.AccessDenied);
                int dispatches = 0, publications = 0;
                var invocation = await PrepLifetimePrepare(sdk, (observer, request) =>
                {
                    Interlocked.Increment(ref dispatches);
                    observer.EmitCompleted(ManagementStatus.AccessDenied);
                }, gate);
                if (scenario == 1) caller.Cancel();
                try
                {
                    var result = await invocation.RunAndCloseAsync(0x34,
                        scenario == 0 ? new byte[15] : BoundChannelPayload(),
                        value => Interlocked.Increment(ref publications), caller.Token);
                    AssertFrameExchangeFailure(result, scenario == 0 ? WsabiWmiFrameExchangeStatus.InvalidRequest
                        : scenario == 1 ? WsabiWmiFrameExchangeStatus.Cancelled : WsabiWmiFrameExchangeStatus.TransportFailure);
                    Equal(0, Volatile.Read(ref dispatches)); Equal(1, Volatile.Read(ref publications));
                    Equal(scenario == 2 ? 1 : 0, gate.Calls); Check(gate.LastLease == null, "pre-source refusal acquired an unreported lease");
                    PrepLifetimeAssertUnsubscribed(sdk);
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await invocation.RequestCloseAsync());
                }
                finally { await CooperativeAwait(invocation.RequestCloseAsync()); }
            }
        });

        AddAsync("prepared invocation unknown dispatch keeps registrations owner and host pending after timeout or stop", async () =>
        {
            foreach (bool callerStops in new[] { false, true })
            using (var caller = new CancellationTokenSource())
            {
                var sdk = new ManagementOperationObserver();
                var gate = new CooperativeTestGate();
                var entered = CooperativeCompletion();
                var published = CooperativeCompletion();
                var root = new ManagementBaseObject
                {
                    OnGetProperties = () => throw new InvalidOperationException("PRIVATE-SDK unknown output must stay unread")
                };
                int dispatches = 0, publications = 0;
                WsabiWmiFrameExchangeResult shown = null;
                var invocation = await PrepLifetimePrepare(sdk, (observer, request) =>
                {
                    Interlocked.Increment(ref dispatches);
                    observer.EmitObjectReady(root);
                    entered.TrySetResult(true);
                    throw new InvalidOperationException("PRIVATE-SDK prepared dispatch detail");
                }, gate, callerStops ? TimeSpan.FromSeconds(3) : TimeSpan.FromMilliseconds(500));
                var run = invocation.RunAndCloseAsync(0x34, BoundChannelPayload(), value =>
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
                        "prepared bounded result or close forced unknown work to end");
                    Equal(1, sdk.ObjectReadySubscriberCount); Equal(1, sdk.CompletedSubscriberCount);
                    Equal(0, root.ConcreteDisposeCalls); Equal(0, gate.LastLease.DisposeCalls);
                    caller.Cancel(); caller.Cancel();
                    Check(!run.IsCompleted && !close.IsCompleted, "repeated caller stop bypassed a missing terminal");
                    BatteryThrows<InvalidOperationException>(() => invocation.RunAndCloseAsync(0x34, BoundChannelPayload(), value => { }));
                    Equal(1, Volatile.Read(ref dispatches));
                    sdk.EmitCompleted(ManagementStatus.AccessDenied); // Explicit fake final, not SDK evidence.
                    await CooperativeAwait(run);
                    Check(ReferenceEquals(shown, await run), "late fake terminal replaced the already published result");
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await close);
                    Equal(1, Volatile.Read(ref publications)); Equal(1, root.ConcreteDisposeCalls);
                    Equal(1, gate.LastLease.DisposeCalls); Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                    Check(!gate.LastLease.IsHeld, "known late final did not finish prepared owner cleanup");
                    PrepLifetimeAssertUnsubscribed(sdk);
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
                            // Delegate entry proves callbacks were armed. A
                            // local no-dispatch failure gets no fake terminal.
                            if (Volatile.Read(ref dispatches) != 0)
                                sdk.EmitCompleted(ManagementStatus.AccessDenied);
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

        AddAsync("prepared invocation run close race joins a blocked gate before unused source cleanup", async () =>
        {
            using (var releaseAcquire = new ManualResetEventSlim())
            {
                var sdk = new ManagementOperationObserver();
                var entered = CooperativeCompletion();
                var published = CooperativeCompletion();
                var lease = new CooperativeTestLease();
                var gate = new CooperativeTestGate { Handler = (timeout, stop) =>
                {
                    entered.TrySetResult(true); PrepLifetimeWait(releaseAcquire);
                    return new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired, lease);
                }};
                int dispatches = 0, publications = 0;
                WsabiWmiFrameExchangeResult shown = null;
                var invocation = await PrepLifetimePrepare(sdk, (observer, request) =>
                {
                    // A broken stop/admission path can still finish this fake
                    // instead of leaking an owner when the assertion fails.
                    Interlocked.Increment(ref dispatches); observer.EmitCompleted(ManagementStatus.AccessDenied);
                }, gate);
                var run = invocation.RunAndCloseAsync(0x34, BoundChannelPayload(), value =>
                {
                    Interlocked.Increment(ref publications); shown = value; published.TrySetResult(true);
                });
                Task<WsabiWmiWindowsCleanupStatus> close = null;
                try
                {
                    await CooperativeAwait(entered.Task);
                    close = invocation.RequestCloseAsync();
                    await CooperativeAwait(published.Task); // Core stop has won before the gate is released.
                    AssertFrameExchangeFailure(shown, WsabiWmiFrameExchangeStatus.Cancelled);
                    Check(!run.IsCompleted && !close.IsCompleted, "prepared close skipped blocked Core acquisition cleanup");
                    Equal(1, sdk.ObjectReadySubscriberCount); Equal(1, sdk.CompletedSubscriberCount);
                    Equal(0, Volatile.Read(ref dispatches)); Equal(0, lease.DisposeCalls);
                    releaseAcquire.Set();
                    await CooperativeAwait(run);
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await close);
                    Equal(0, Volatile.Read(ref dispatches)); Equal(1, Volatile.Read(ref publications));
                    Equal(1, gate.Calls); Equal(1, lease.DisposeCalls); Equal(gate.AcquireThread, lease.DisposeThread);
                    Check(!lease.IsHeld, "prepared close returned before stopped acquired lease release");
                    PrepLifetimeAssertUnsubscribed(sdk);
                }
                finally
                {
                    close = invocation.RequestCloseAsync();
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

        AddAsync("prepared invocation report exception propagates only after unused or started cleanup", async () =>
        {
            foreach (bool startsSource in new[] { false, true })
            using (var releaseRemove = new ManualResetEventSlim())
            {
                var sdk = new ManagementOperationObserver();
                var gate = new CooperativeTestGate();
                var removing = CooperativeCompletion();
                var reported = CooperativeCompletion();
                ManagementBaseObject embedded;
                var root = WindowsOutputFixture(BoundChannelReply(), out embedded);
                int dispatches = 0, publications = 0;
                var invocation = await PrepLifetimePrepare(sdk, (observer, request) =>
                {
                    Interlocked.Increment(ref dispatches);
                    observer.EmitObjectReady(root); observer.EmitCompleted(ManagementStatus.NoError);
                }, gate);
                if (!startsSource) sdk.BeforeRemove = name =>
                {
                    if (name == "ObjectReady") { removing.TrySetResult(true); PrepLifetimeWait(releaseRemove); }
                };
                var run = invocation.RunAndCloseAsync(0x34,
                    startsSource ? BoundChannelPayload() : new byte[15], value =>
                    {
                        Interlocked.Increment(ref publications); reported.TrySetResult(true);
                        throw new PrepLifetimeReportException();
                    });
                try
                {
                    await CooperativeAwait(reported.Task);
                    if (!startsSource)
                    {
                        await CooperativeAwait(removing.Task);
                        Check(!run.IsCompleted, "report failure escaped before unused subscription cleanup");
                        Equal(0, gate.Calls); Equal(0, Volatile.Read(ref dispatches));
                        releaseRemove.Set();
                    }
                    await PrepLifetimeExpectReportFailure(run);
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await invocation.RequestCloseAsync());
                    Equal(1, Volatile.Read(ref publications)); Equal(startsSource ? 1 : 0, Volatile.Read(ref dispatches));
                    Equal(startsSource ? 1 : 0, gate.Calls);
                    if (startsSource)
                    {
                        Equal(1, root.ConcreteDisposeCalls); Equal(1, embedded.ConcreteDisposeCalls);
                        Equal(1, gate.LastLease.DisposeCalls); Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                        Check(!gate.LastLease.IsHeld, "report fault escaped before started owner cleanup");
                    }
                    PrepLifetimeAssertUnsubscribed(sdk);
                }
                finally
                {
                    releaseRemove.Set();
                    try { await CooperativeAwait(invocation.RequestCloseAsync()); }
                    finally { await PrepLifetimeExpectReportFailure(run); }
                }
            }
        });
    }

    private static async Task<WsabiWmiWindowsPreparedInvocation> PrepLifetimePrepare(
        ManagementOperationObserver sdk, Action<ManagementOperationObserver, WsabiWmiMethodRequest> dispatch,
        CooperativeTestGate gate, TimeSpan? responseTimeout = null,
        CancellationToken preparationToken = default(CancellationToken))
    {
        var result = await WsabiWmiWindowsPreparation.PrepareAsync(sdk, dispatch, BoundChannelBinder(), gate,
            TimeSpan.FromMilliseconds(200), responseTimeout ?? TimeSpan.FromSeconds(3), preparationToken);
        Equal(WsabiWmiWindowsPreparationStatus.Ready, result.Status);
        Check(result.IsReady && result.Invocation != null, "prepared lifetime fixture did not produce a ready handle");
        return result.Invocation;
    }

    private static void PrepLifetimeAssertUnsubscribed(ManagementOperationObserver sdk)
    {
        Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
    }

    private static void PrepLifetimeWait(ManualResetEventSlim release)
    {
        if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("Prepared lifetime fake gate was not released.");
    }

    private static async Task PrepLifetimeExpectReportFailure(Task run)
    {
        try { await CooperativeAwait(run); }
        catch (PrepLifetimeReportException) { return; }
        throw new InvalidOperationException("The prepared reporter failure was not retained.");
    }

    private sealed class PrepLifetimeReportException : Exception
    {
        internal PrepLifetimeReportException() : base("Fixed prepared lifetime report failure.") { }
    }
}
