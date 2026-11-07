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
    // Owned production input/host flow with SDK stand-ins and existing
    // synthetic framing only. All terminal cleanup in these tests is fake.
    private static void RegisterWsabiWmiOwnedInputLifetimeTests()
    {
        AddAsync("owned inputs cancellation cannot return or dispose before the populator worker settles", async () =>
        {
            using (var releaseMetadata = new ManualResetEventSlim())
            using (var caller = new CancellationTokenSource())
            {
                var target = SingleReadTarget(new object()); var plan = SingleReadPlanCreate(target);
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate();
                var pair = InputPreparationPair.Create(); var entered = CooperativeCompletion();
                var path = pair.Buffer.ClassPath;
                pair.Buffer.OnGetClassPath = () =>
                {
                    entered.TrySetResult(true); OwnedInputLifeWait(releaseMetadata); return path;
                };
                int adds = 0, dispatches = 0;
                sdk.BeforeAdd = name => Interlocked.Increment(ref adds);
                var preparing = OwnedInputLifePrepare(plan, target, sdk, (observer, request) =>
                    Interlocked.Increment(ref dispatches), pair, gate, token: caller.Token);
                try
                {
                    await CooperativeAwait(entered.Task);
                    caller.Cancel(); caller.Cancel();
                    Check(!preparing.IsCompleted, "cancel returned while the input populator still held SDK objects");
                    OwnedInputLifeAssertPairDisposes(pair, 0);
                    Equal(0, adds); Equal(0, gate.Calls); Equal(0, dispatches);
                    Equal(0, pair.Bytes.ValueWrites); Equal(0, pair.Input.ValueWrites);
                    releaseMetadata.Set();
                    await CooperativeAwait(preparing);
                    var result = await preparing;
                    Equal(WsabiWmiSingleReadPreparationStatus.PreparationNotReady, result.Status);
                    Equal((WsabiWmiWindowsPreparationStatus?)WsabiWmiWindowsPreparationStatus.Cancelled, result.RegistrationStatus);
                    Equal((WsabiWmiWindowsInputPreparationStatus?)WsabiWmiWindowsInputPreparationStatus.Populated, result.InputStatus);
                    Check(result.InputOwnershipTransferred && result.Invocation == null, "claimed inputs were not reported as transferred on cancellation");
                    Equal((WsabiWmiWindowsCleanupStatus?)WsabiWmiWindowsCleanupStatus.Complete, result.InputCleanupStatus);
                    // Cancellation is observed after this worker, not treated
                    // as proof that its local setters never ran.
                    Equal(1, pair.Bytes.ValueWrites); Equal(1, pair.Input.ValueWrites);
                    OwnedInputLifeAssertPairDisposes(pair, 1);
                    Equal(0, adds); Equal(0, gate.Calls); Equal(0, dispatches);
                    OwnedInputLifeAssertUnsubscribed(sdk);
                }
                finally
                {
                    releaseMetadata.Set();
                    await OwnedInputLifeClosePreparation(preparing);
                }
            }
        });

        AddAsync("owned inputs survive an early terminal until the admitted dispatch stack returns", async () =>
        {
            using (var releaseDispatch = new ManualResetEventSlim())
            {
                var target = SingleReadTarget(new object()); var plan = SingleReadPlanCreate(target);
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate();
                var pair = InputPreparationPair.Create(); var terminalSent = CooperativeCompletion(); var published = CooperativeCompletion();
                ManagementBaseObject embedded; var output = WindowsOutputFixture(BoundChannelReply(), out embedded);
                int calls = 0, reports = 0; WsabiWmiFrameExchangeResult shown = null;
                var prepared = await OwnedInputLifeReady(OwnedInputLifePrepare(plan, target, sdk, (observer, request) =>
                {
                    Interlocked.Increment(ref calls);
                    observer.EmitObjectReady(output); observer.EmitCompleted(ManagementStatus.NoError);
                    terminalSent.TrySetResult(true); OwnedInputLifeWait(releaseDispatch);
                }, pair, gate, TimeSpan.FromMilliseconds(500)));
                var invocation = prepared.Invocation;
                var run = invocation.RunAndCloseAsync(value =>
                {
                    Interlocked.Increment(ref reports); shown = value; published.TrySetResult(true);
                });
                try
                {
                    await CooperativeAwait(terminalSent.Task); await CooperativeAwait(published.Task);
                    AssertFrameExchangeFailure(shown, WsabiWmiFrameExchangeStatus.TimedOut);
                    var close = invocation.RequestCloseAsync();
                    Check(!run.IsCompleted && !close.IsCompleted && gate.LastLease.IsHeld,
                        "early terminal released owned inputs while dispatch was still on stack");
                    Equal(1, output.ConcreteDisposeCalls); Equal(1, embedded.ConcreteDisposeCalls);
                    OwnedInputLifeAssertPairDisposes(pair, 0);
                    releaseDispatch.Set(); await CooperativeAwait(run);
                    Check(ReferenceEquals(shown, await run), "late dispatch return replaced the bounded report");
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await close);
                    Equal(1, calls); Equal(1, reports); Equal(1, gate.LastLease.DisposeCalls);
                    Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                    OwnedInputLifeAssertPairDisposes(pair, 1); OwnedInputLifeAssertUnsubscribed(sdk);
                    Check(prepared.InputCleanupStatus == null, "Ready preparation snapshot changed into a later cleanup result");
                }
                finally
                {
                    var close = invocation.RequestCloseAsync(); releaseDispatch.Set();
                    try { await CooperativeAwait(close); }
                    finally { await CooperativeAwait(run); }
                }
            }
        });

        AddAsync("owned inputs and subscriptions stay held after unknown timeout or caller stop", async () =>
        {
            foreach (bool callerStops in new[] { false, true })
            using (var caller = new CancellationTokenSource())
            {
                var target = SingleReadTarget(new object()); var plan = SingleReadPlanCreate(target);
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate();
                var pair = InputPreparationPair.Create(); var entered = CooperativeCompletion(); var published = CooperativeCompletion();
                var output = new ManagementBaseObject();
                int calls = 0, reports = 0, reads = 0; WsabiWmiFrameExchangeResult shown = null;
                output.OnGetProperties = () => { Interlocked.Increment(ref reads); throw new InvalidOperationException("PRIVATE-SDK unknown output"); };
                var prepared = await OwnedInputLifeReady(OwnedInputLifePrepare(plan, target, sdk, (observer, request) =>
                {
                    Interlocked.Increment(ref calls); observer.EmitObjectReady(output); entered.TrySetResult(true);
                    throw new InvalidOperationException("PRIVATE-SDK owned dispatch detail");
                }, pair, gate, callerStops ? TimeSpan.FromSeconds(3) : TimeSpan.FromMilliseconds(500)));
                var invocation = prepared.Invocation;
                var run = invocation.RunAndCloseAsync(value =>
                {
                    Interlocked.Increment(ref reports); shown = value; published.TrySetResult(true);
                }, caller.Token);
                try
                {
                    await CooperativeAwait(entered.Task); if (callerStops) caller.Cancel();
                    await CooperativeAwait(published.Task);
                    AssertFrameExchangeFailure(shown, callerStops ? WsabiWmiFrameExchangeStatus.Cancelled : WsabiWmiFrameExchangeStatus.TimedOut);
                    var close = invocation.RequestCloseAsync();
                    Check(!run.IsCompleted && !close.IsCompleted && gate.LastLease.IsHeld,
                        "unknown UI result authorized input disposal");
                    OwnedInputLifeAssertPairDisposes(pair, 0);
                    Equal(0, output.ConcreteDisposeCalls); Equal(0, reads);
                    Equal(1, sdk.ObjectReadySubscriberCount); Equal(1, sdk.CompletedSubscriberCount);
                    caller.Cancel(); caller.Cancel();
                    Check(!run.IsCompleted && !close.IsCompleted, "repeated stop manufactured owned-input lifetime end");
                    BatteryThrows<InvalidOperationException>(() => invocation.RunAndCloseAsync(value => { }));
                    Equal(1, calls);
                    sdk.EmitCompleted(ManagementStatus.AccessDenied); // Explicit fake final, not provider evidence.
                    await CooperativeAwait(run);
                    Check(ReferenceEquals(shown, await run), "fake final replaced the already shown diagnostic");
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await close);
                    OwnedInputLifeAssertPairDisposes(pair, 1);
                    Equal(1, output.ConcreteDisposeCalls); Equal(0, reads); Equal(1, reports); Equal(1, calls);
                    Equal(1, gate.LastLease.DisposeCalls); Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                    OwnedInputLifeAssertUnsubscribed(sdk);
                }
                finally
                {
                    var close = invocation.RequestCloseAsync();
                    try
                    {
                        if (Volatile.Read(ref calls) == 0 && !run.IsCompleted)
                            await CooperativeAwait(Task.WhenAny(entered.Task, run));
                    }
                    finally
                    {
                        try { if (Volatile.Read(ref calls) != 0) sdk.EmitCompleted(ManagementStatus.AccessDenied); }
                        finally
                        {
                            try { await CooperativeAwait(close); }
                            finally { await CooperativeAwait(run); }
                        }
                    }
                }
            }
        });

        AddAsync("owned inputs report failure waits for Core lease cleanup and then input cleanup", async () =>
        {
            using (var releaseLease = new ManualResetEventSlim())
            using (var releaseInput = new ManualResetEventSlim())
            {
                var target = SingleReadTarget(new object()); var plan = SingleReadPlanCreate(target);
                var sdk = new ManagementOperationObserver(); var pair = InputPreparationPair.Create();
                var lease = new CooperativeTestLease { OnDispose = () => OwnedInputLifeWait(releaseLease) };
                var gate = new CooperativeTestGate { Handler = (timeout, stop) =>
                    new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired, lease) };
                var inputEntered = CooperativeCompletion(); var published = CooperativeCompletion();
                pair.Parameters.OnDispose = () => { inputEntered.TrySetResult(true); OwnedInputLifeWait(releaseInput); };
                ManagementBaseObject embedded; var output = WindowsOutputFixture(BoundChannelReply(), out embedded);
                int calls = 0, reports = 0;
                var prepared = await OwnedInputLifeReady(OwnedInputLifePrepare(plan, target, sdk, (observer, request) =>
                {
                    Interlocked.Increment(ref calls); observer.EmitObjectReady(output); observer.EmitCompleted(ManagementStatus.NoError);
                }, pair, gate));
                var invocation = prepared.Invocation;
                var run = invocation.RunAndCloseAsync(value =>
                {
                    Interlocked.Increment(ref reports); published.TrySetResult(true); throw new OwnedInputLifeReportException();
                });
                try
                {
                    await CooperativeAwait(lease.DisposeEntered.Task);
                    OwnedInputLifeAssertPairDisposes(pair, 0);
                    Equal(1, output.ConcreteDisposeCalls); Equal(1, embedded.ConcreteDisposeCalls);
                    OwnedInputLifeAssertUnsubscribed(sdk);
                    var close = invocation.RequestCloseAsync();
                    await CooperativeAwait(published.Task);
                    Check(!run.IsCompleted && !close.IsCompleted && lease.IsHeld, "report exception bypassed the blocked Core lease");
                    OwnedInputLifeAssertPairDisposes(pair, 0);
                    releaseLease.Set(); await CooperativeAwait(inputEntered.Task);
                    Check(!lease.IsHeld && !run.IsCompleted && !close.IsCompleted, "report fault bypassed the second input cleanup stage");
                    Equal(1, pair.Parameters.ConcreteDisposeCalls); Equal(0, pair.Buffer.ConcreteDisposeCalls);
                    releaseInput.Set(); await OwnedInputLifeExpectReportFailure(run);
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await close);
                    OwnedInputLifeAssertPairDisposes(pair, 1);
                    Equal(1, lease.DisposeCalls); Equal(gate.AcquireThread, lease.DisposeThread);
                    Equal(1, calls); Equal(1, reports);
                }
                finally
                {
                    var close = invocation.RequestCloseAsync(); releaseLease.Set(); releaseInput.Set();
                    try { await CooperativeAwait(close); }
                    finally { await OwnedInputLifeExpectReportFailure(run); }
                }
            }
        });

        AddAsync("owned inputs unused close joins ordered concrete disposal even when the first disposal fails", async () =>
        {
            foreach (bool failFirst in new[] { false, true })
            using (var releaseFirst = new ManualResetEventSlim())
            using (var releaseSecond = new ManualResetEventSlim())
            {
                var target = SingleReadTarget(new object()); var plan = SingleReadPlanCreate(target);
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); var pair = InputPreparationPair.Create();
                var firstEntered = CooperativeCompletion(); var secondEntered = CooperativeCompletion(); var order = new List<string>();
                pair.Parameters.OnDispose = () =>
                {
                    order.Add("parameters"); firstEntered.TrySetResult(true); OwnedInputLifeWait(releaseFirst);
                    if (failFirst) throw new InvalidOperationException("PRIVATE-SDK first owned disposal");
                };
                pair.Buffer.OnDispose = () =>
                {
                    order.Add("buffer"); secondEntered.TrySetResult(true); OwnedInputLifeWait(releaseSecond);
                };
                int calls = 0;
                var prepared = await OwnedInputLifeReady(OwnedInputLifePrepare(plan, target, sdk,
                    (observer, request) => Interlocked.Increment(ref calls), pair, gate));
                var invocation = prepared.Invocation;
                var close = invocation.RequestCloseAsync();
                try
                {
                    Check(ReferenceEquals(close, invocation.RequestCloseAsync()), "owned inputs created two close operations");
                    await CooperativeAwait(firstEntered.Task);
                    Check(!close.IsCompleted, "close returned while first input Dispose was blocked");
                    Equal(1, pair.Parameters.ConcreteDisposeCalls); Equal(0, pair.Buffer.ConcreteDisposeCalls);
                    OwnedInputLifeAssertUnsubscribed(sdk); Equal(0, calls); Equal(0, gate.Calls);
                    releaseFirst.Set(); await CooperativeAwait(secondEntered.Task);
                    Check(!close.IsCompleted && order.SequenceEqual(new[] { "parameters", "buffer" }),
                        "first failure skipped second input disposal or changed its order");
                    Equal(1, pair.Parameters.ConcreteDisposeCalls); Equal(1, pair.Buffer.ConcreteDisposeCalls);
                    releaseSecond.Set();
                    Equal(failFirst ? WsabiWmiWindowsCleanupStatus.Failed : WsabiWmiWindowsCleanupStatus.Complete, await close);
                    Check(ReferenceEquals(close, invocation.RequestCloseAsync()), "finished failed cleanup was retried");
                    OwnedInputLifeAssertPairDisposes(pair, 1);
                    BatteryThrows<InvalidOperationException>(() => invocation.RunAndCloseAsync(value => { }));
                }
                finally
                {
                    releaseFirst.Set(); releaseSecond.Set(); await CooperativeAwait(close);
                }
            }
        });

        AddAsync("owned inputs cleanup failure faults Run only after the second concrete disposal completes", async () =>
        {
            using (var releaseSecond = new ManualResetEventSlim())
            {
                var target = SingleReadTarget(new object()); var plan = SingleReadPlanCreate(target);
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); var pair = InputPreparationPair.Create();
                var secondEntered = CooperativeCompletion(); var published = CooperativeCompletion();
                pair.Parameters.OnDispose = () => throw new InvalidOperationException("PRIVATE-SDK cleanup detail");
                pair.Buffer.OnDispose = () => { secondEntered.TrySetResult(true); OwnedInputLifeWait(releaseSecond); };
                ManagementBaseObject embedded; var output = WindowsOutputFixture(BoundChannelReply(), out embedded);
                int calls = 0, reports = 0;
                var prepared = await OwnedInputLifeReady(OwnedInputLifePrepare(plan, target, sdk, (observer, request) =>
                {
                    Interlocked.Increment(ref calls); observer.EmitObjectReady(output); observer.EmitCompleted(ManagementStatus.NoError);
                }, pair, gate));
                var invocation = prepared.Invocation;
                var run = invocation.RunAndCloseAsync(value =>
                {
                    Check(value.IsValidFrame, "successful inner result was replaced before input cleanup");
                    Interlocked.Increment(ref reports); published.TrySetResult(true);
                });
                try
                {
                    await CooperativeAwait(published.Task); await CooperativeAwait(secondEntered.Task);
                    var close = invocation.RequestCloseAsync();
                    Check(!run.IsCompleted && !close.IsCompleted, "first cleanup error escaped before the second attempt ended");
                    Equal(1, pair.Parameters.ConcreteDisposeCalls); Equal(1, pair.Buffer.ConcreteDisposeCalls);
                    Equal(1, gate.LastLease.DisposeCalls); Check(!gate.LastLease.IsHeld, "input cleanup began before Core owner release");
                    releaseSecond.Set(); await OwnedInputLifeExpectFixedFailure(run);
                    Equal(WsabiWmiWindowsCleanupStatus.Failed, await close);
                    Check(ReferenceEquals(close, invocation.RequestCloseAsync()), "failed pair cleanup was repeated");
                    OwnedInputLifeAssertPairDisposes(pair, 1); OwnedInputLifeAssertUnsubscribed(sdk);
                    Equal(1, calls); Equal(1, reports); Equal(1, output.ConcreteDisposeCalls); Equal(1, embedded.ConcreteDisposeCalls);
                    Check(prepared.InputCleanupStatus == null, "Ready snapshot falsely tracked later cleanup status");
                }
                finally
                {
                    var close = invocation.RequestCloseAsync(); releaseSecond.Set();
                    try { await CooperativeAwait(close); }
                    finally { await OwnedInputLifeExpectFixedFailure(run); }
                }
            }
        });

        AddAsync("owned inputs exact output roots are unread and released only by their pair including queued aliases", async () =>
        {
            foreach (bool returnsParameters in new[] { true, false })
            using (var releaseDispatch = new ManualResetEventSlim())
            {
                var target = SingleReadTarget(new object()); var plan = SingleReadPlanCreate(target);
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); var pair = InputPreparationPair.Create();
                var terminalSent = CooperativeCompletion(); bool guard = false; int reads = 0, calls = 0;
                OwnedInputLifeGuardPairAccess(pair, () => guard, () => Interlocked.Increment(ref reads));
                ObjectReadyEventHandler queued = null;
                var prepared = await OwnedInputLifeReady(OwnedInputLifePrepare(plan, target, sdk, (observer, request) =>
                {
                    Interlocked.Increment(ref calls); queued = observer.ObjectReadySnapshot; guard = true;
                    observer.EmitObjectReady(returnsParameters ? pair.Parameters : pair.Buffer);
                    observer.EmitCompleted(ManagementStatus.NoError); terminalSent.TrySetResult(true);
                    OwnedInputLifeWait(releaseDispatch);
                }, pair, gate));
                var invocation = prepared.Invocation;
                var run = invocation.RunAndCloseAsync(value => { });
                try
                {
                    await CooperativeAwait(terminalSent.Task);
                    Equal(0, reads); OwnedInputLifeAssertPairDisposes(pair, 0);
                    Check(!run.IsCompleted && gate.LastLease.IsHeld, "known output alias bypassed invocation stack ownership");
                    releaseDispatch.Set(); await CooperativeAwait(run);
                    AssertFrameExchangeFailure(await run, WsabiWmiFrameExchangeStatus.TransportFailure);
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await invocation.RequestCloseAsync());
                    OwnedInputLifeAssertPairDisposes(pair, 1); Equal(0, reads); Equal(1, calls);
                    queued(sdk, new ObjectReadyEventArgs(pair.Parameters)); queued(sdk, new ObjectReadyEventArgs(pair.Buffer));
                    queued(sdk, new ObjectReadyEventArgs(pair.Parameters));
                    OwnedInputLifeAssertPairDisposes(pair, 1); Equal(0, reads);
                    OwnedInputLifeAssertUnsubscribed(sdk);
                }
                finally
                {
                    var close = invocation.RequestCloseAsync(); releaseDispatch.Set();
                    try { await CooperativeAwait(close); }
                    finally { await CooperativeAwait(run); }
                }
            }
        });

        AddAsync("owned inputs embedded exact aliases are rejected before embedded getters or disposal", async () =>
        {
            foreach (bool embedsParameters in new[] { true, false })
            using (var releaseDispatch = new ManualResetEventSlim())
            {
                var target = SingleReadTarget(new object()); var plan = SingleReadPlanCreate(target);
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); var pair = InputPreparationPair.Create();
                var terminalSent = CooperativeCompletion(); bool guard = false; int reads = 0;
                OwnedInputLifeGuardPairAccess(pair, () => guard, () => Interlocked.Increment(ref reads));
                var output = WindowsOutputRoot(embedsParameters ? pair.Parameters : pair.Buffer);
                ObjectReadyEventHandler queued = null;
                var prepared = await OwnedInputLifeReady(OwnedInputLifePrepare(plan, target, sdk, (observer, request) =>
                {
                    queued = observer.ObjectReadySnapshot; guard = true;
                    observer.EmitObjectReady(output); observer.EmitCompleted(ManagementStatus.NoError);
                    terminalSent.TrySetResult(true); OwnedInputLifeWait(releaseDispatch);
                }, pair, gate));
                var invocation = prepared.Invocation;
                var run = invocation.RunAndCloseAsync(value => { });
                try
                {
                    await CooperativeAwait(terminalSent.Task);
                    Equal(1, output.Properties["outData"].ValueReads); Equal(1, output.ConcreteDisposeCalls);
                    Equal(0, reads); OwnedInputLifeAssertPairDisposes(pair, 0);
                    Check(!run.IsCompleted && gate.LastLease.IsHeld, "embedded alias cleanup bypassed the active invocation stack");
                    releaseDispatch.Set(); await CooperativeAwait(run);
                    AssertFrameExchangeFailure(await run, WsabiWmiFrameExchangeStatus.TransportFailure);
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await invocation.RequestCloseAsync());
                    OwnedInputLifeAssertPairDisposes(pair, 1); Equal(1, output.ConcreteDisposeCalls); Equal(0, reads);
                    queued(sdk, new ObjectReadyEventArgs(pair.Parameters)); queued(sdk, new ObjectReadyEventArgs(pair.Buffer));
                    OwnedInputLifeAssertPairDisposes(pair, 1); Equal(0, reads);
                    OwnedInputLifeAssertUnsubscribed(sdk);
                }
                finally
                {
                    var close = invocation.RequestCloseAsync(); releaseDispatch.Set();
                    try { await CooperativeAwait(close); }
                    finally { await CooperativeAwait(run); }
                }
            }
        });
    }

    private static Task<WsabiWmiSingleReadPreparationResult> OwnedInputLifePrepare(WsabiWmiSingleReadPlan plan,
        WsabiWmiSingleReadTarget target, ManagementOperationObserver sdk,
        Action<ManagementOperationObserver, WsabiWmiMethodRequest> dispatch,
        InputPreparationPair pair, CooperativeTestGate gate, TimeSpan? responseTimeout = null,
        CancellationToken token = default(CancellationToken))
        => WsabiWmiWindowsSingleReadPreparation.PrepareWithInputsAsync(plan,
            new WsabiWmiWindowsReadTrialBinding(target, sdk, dispatch), InputPreparationRequest(),
            pair.Parameters, pair.Buffer, gate, TimeSpan.FromMilliseconds(200), responseTimeout ?? TimeSpan.FromSeconds(3), token);

    private static async Task<WsabiWmiSingleReadPreparationResult> OwnedInputLifeReady(Task<WsabiWmiSingleReadPreparationResult> preparing)
    {
        await CooperativeAwait(preparing); var result = await preparing;
        Equal(WsabiWmiSingleReadPreparationStatus.Ready, result.Status);
        Equal((WsabiWmiWindowsInputPreparationStatus?)WsabiWmiWindowsInputPreparationStatus.Populated, result.InputStatus);
        Check(result.IsReady && result.InputOwnershipTransferred && result.Invocation != null && result.InputCleanupStatus == null,
            "owned input fixture did not transfer a pending prepared input pair");
        return result;
    }

    private static async Task OwnedInputLifeClosePreparation(Task<WsabiWmiSingleReadPreparationResult> preparing)
    {
        await CooperativeAwait(preparing); var result = await preparing;
        if (result.Invocation != null) await CooperativeAwait(result.Invocation.RequestCloseAsync());
    }

    private static void OwnedInputLifeAssertPairDisposes(InputPreparationPair pair, int expected)
    {
        Equal(expected, pair.Parameters.ConcreteDisposeCalls); Equal(expected, pair.Buffer.ConcreteDisposeCalls);
        Equal(0, pair.Parameters.ComponentDisposeCalls); Equal(0, pair.Buffer.ComponentDisposeCalls);
    }

    private static void OwnedInputLifeAssertUnsubscribed(ManagementOperationObserver sdk)
    {
        Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
    }

    private static void OwnedInputLifeWait(ManualResetEventSlim release)
    {
        if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("Owned-input lifetime fake gate was not released.");
    }

    private static void OwnedInputLifeGuardPairAccess(InputPreparationPair pair, Func<bool> guarded, Action touched)
    {
        var properties = pair.Parameters.Properties; var bufferProperties = pair.Buffer.Properties;
        var path = pair.Parameters.ClassPath; var bufferPath = pair.Buffer.ClassPath;
        pair.Parameters.OnGetProperties = () => { if (guarded()) { touched(); throw new InvalidOperationException("PRIVATE-SDK input output alias"); } return properties; };
        pair.Buffer.OnGetProperties = () => { if (guarded()) { touched(); throw new InvalidOperationException("PRIVATE-SDK buffer output alias"); } return bufferProperties; };
        pair.Parameters.OnGetClassPath = () => { if (guarded()) { touched(); throw new InvalidOperationException("PRIVATE-SDK input alias class"); } return path; };
        pair.Buffer.OnGetClassPath = () => { if (guarded()) { touched(); throw new InvalidOperationException("PRIVATE-SDK buffer alias class"); } return bufferPath; };
    }

    private static async Task OwnedInputLifeExpectFixedFailure(Task run)
    {
        try { await CooperativeAwait(run); }
        catch (InvalidOperationException error)
        {
            Check(error.InnerException == null && error.Message.IndexOf("PRIVATE-SDK", StringComparison.Ordinal) < 0,
                "owned-input cleanup exposed a source exception");
            return;
        }
        throw new InvalidOperationException("Expected a fixed owned-input cleanup failure.");
    }

    private static async Task OwnedInputLifeExpectReportFailure(Task run)
    {
        try { await CooperativeAwait(run); }
        catch (OwnedInputLifeReportException) { return; }
        throw new InvalidOperationException("Owned-input host did not preserve its report exception.");
    }

    private sealed class OwnedInputLifeReportException : Exception
    {
        internal OwnedInputLifeReportException() : base("Fixed owned-input report failure.") { }
    }
}
