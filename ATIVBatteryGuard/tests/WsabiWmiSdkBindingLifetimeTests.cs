using System;
using System.Linq;
using System.Management;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.WmiInterop;

internal static partial class Program
{
    // Production typed SDK binding compiled against test-only SDK stand-ins.
    // Internal mechanical seam only, not permission for a real read trial.
    // No System.Management runtime, discovery, device or reservation executes.
    private static void RegisterWsabiWmiSdkBindingLifetimeTests()
    {
        AddAsync("SDK binding lifetime cancellation waits for target validation before refusing input ownership", async () =>
        {
            using (var releaseValidation = new ManualResetEventSlim())
            using (var caller = new CancellationTokenSource())
            {
                var target = new ManagementObject(); var facts = SingleReadTarget(target); var plan = SingleReadPlanCreate(facts);
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); var pair = InputPreparationPair.Create();
                var entered = CooperativeCompletion(); int adds = 0;
                target.Scope.OnGetIsConnected = () =>
                {
                    entered.TrySetResult(true); SdkLifeWait(releaseValidation); return true;
                };
                sdk.BeforeAdd = name => Interlocked.Increment(ref adds);
                var preparing = SdkLifePrepare(plan, facts, target, sdk, pair, gate, token: caller.Token);
                try
                {
                    await CooperativeAwait(entered.Task); caller.Cancel(); caller.Cancel();
                    Check(!preparing.IsCompleted, "cancellation ended the active target-validation worker");
                    Equal(0, adds); Equal(0, gate.Calls); Equal(0, target.InvokeCalls);
                    Equal(0, pair.Input.ValueWrites); Equal(0, pair.Bytes.ValueWrites);
                    SdkLifeAssertPairDisposes(pair, 0); SdkLifeAssertBorrowedTarget(target);
                    releaseValidation.Set(); await CooperativeAwait(preparing);
                    var result = await preparing;
                    Equal(WsabiWmiSingleReadPreparationStatus.PreparationNotReady, result.Status);
                    Equal((WsabiWmiWindowsPreparationStatus?)WsabiWmiWindowsPreparationStatus.Cancelled, result.RegistrationStatus);
                    Equal((WsabiWmiWindowsSdkBindingStatus?)WsabiWmiWindowsSdkBindingStatus.Ready, result.SdkStatus);
                    Check(result.Invocation == null && !result.InputOwnershipTransferred && result.InputStatus == null && result.InputCleanupStatus == null,
                        "cancelled validation transferred or reported an unstarted input stage");
                    Equal(0, adds); Equal(0, target.InvokeCalls); Equal(0, gate.Calls);
                    SdkLifeAssertPairDisposes(pair, 0); SdkLifeAssertBorrowedTarget(target); SdkLifeAssertUnsubscribed(sdk);
                    // Ownership stayed with the caller, and the shared input
                    // registry was never claimed by this cancelled stage.
                    Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                        WsabiWmiWindowsInputPreparation.Populate(plan, InputPreparationRequest(), pair.Parameters, pair.Buffer));
                    SdkLifeAssertPairDisposes(pair, 0); SdkLifeAssertBorrowedTarget(target);
                }
                finally
                {
                    releaseValidation.Set(); await SdkLifeClosePreparation(preparing);
                }
            }
        });

        AddAsync("SDK binding lifetime pins the target input and observer while early completion waits for SDK return", async () =>
        {
            using (var releaseInvoke = new ManualResetEventSlim())
            using (var preparation = new CancellationTokenSource())
            {
                var target = new ManagementObject(); var sdk = new ManagementOperationObserver(); var pair = InputPreparationPair.Create();
                var facts = SingleReadTarget(target); var plan = SingleReadPlanCreate(facts); var gate = new CooperativeTestGate();
                var terminalSent = CooperativeCompletion(); var published = CooperativeCompletion();
                ManagementBaseObject embedded; var output = WindowsOutputFixture(BoundChannelReply(), out embedded);
                int reports = 0; WsabiWmiFrameExchangeResult shown = null;
                target.OnInvoke = (observer, method, input, options) =>
                {
                    Check(ReferenceEquals(observer, sdk) && ReferenceEquals(input, pair.Parameters), "typed binding substituted pinned SDK objects");
                    Equal("CallSabiFunction", method); Check(options != null, "typed binding omitted explicit method options");
                    Check(ReferenceEquals(input.Properties["inData"].Value, pair.Buffer), "stand-in SDK did not receive its prepared embedded input");
                    Check(((byte[])pair.Bytes.Value).SequenceEqual(BoundChannelRequest()), "stand-in SDK input differs from the frozen synthetic request");
                    observer.EmitObjectReady(output); observer.EmitCompleted(ManagementStatus.NoError);
                    terminalSent.TrySetResult(true); SdkLifeWait(releaseInvoke);
                };
                var prepared = await SdkLifeReady(SdkLifePrepare(plan, facts, target, sdk, pair, gate,
                    TimeSpan.FromMilliseconds(500), preparation.Token));
                preparation.Cancel(); // A completed prepare token no longer controls Run.
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
                    Check(!run.IsCompleted && !close.IsCompleted && gate.LastLease.IsHeld, "early SDK terminal ended the invocation stack lifetime");
                    Equal(1, target.InvokeCalls); Equal(1, output.ConcreteDisposeCalls); Equal(1, embedded.ConcreteDisposeCalls);
                    SdkLifeAssertPairDisposes(pair, 0); SdkLifeAssertBorrowedTarget(target);
                    releaseInvoke.Set(); await CooperativeAwait(run);
                    Check(ReferenceEquals(shown, await run), "late SDK return replaced the bounded report");
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await close);
                    Equal(1, target.InvokeCalls); Equal(1, reports); Equal(1, gate.LastLease.DisposeCalls);
                    Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                    SdkLifeAssertPairDisposes(pair, 1); SdkLifeAssertBorrowedTarget(target); SdkLifeAssertUnsubscribed(sdk);
                    Check(prepared.InputCleanupStatus == null, "Ready snapshot claimed to be a live cleanup status");
                    BatteryThrows<InvalidOperationException>(() => invocation.RunAndCloseAsync(value => { }));
                    Equal(1, target.InvokeCalls);
                }
                finally
                {
                    var close = invocation.RequestCloseAsync(); releaseInvoke.Set();
                    try
                    {
                        if (!terminalSent.Task.IsCompleted && target.InvokeCalls != 0)
                            sdk.EmitCompleted(ManagementStatus.AccessDenied);
                    }
                    finally
                    {
                        try { await CooperativeAwait(close); }
                        finally { await CooperativeAwait(run); }
                    }
                }
            }
        });

        AddAsync("SDK binding lifetime keeps borrowed target and owned inputs after unknown timeout or caller stop", async () =>
        {
            foreach (bool callerStops in new[] { false, true })
            using (var caller = new CancellationTokenSource())
            {
                var target = new ManagementObject(); var facts = SingleReadTarget(target); var plan = SingleReadPlanCreate(facts);
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); var pair = InputPreparationPair.Create();
                var entered = CooperativeCompletion(); var published = CooperativeCompletion();
                var output = new ManagementBaseObject(); int reads = 0, reports = 0; WsabiWmiFrameExchangeResult shown = null;
                output.OnGetProperties = () => { Interlocked.Increment(ref reads); throw new InvalidOperationException("PRIVATE-SDK unknown output"); };
                target.OnInvoke = (observer, method, input, options) =>
                {
                    observer.EmitObjectReady(output); entered.TrySetResult(true);
                    throw new InvalidOperationException("PRIVATE-SDK actual entry detail");
                };
                var prepared = await SdkLifeReady(SdkLifePrepare(plan, facts, target, sdk, pair, gate,
                    callerStops ? TimeSpan.FromSeconds(3) : TimeSpan.FromMilliseconds(500)));
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
                    Check(!run.IsCompleted && !close.IsCompleted && gate.LastLease.IsHeld, "SDK throw or UI result released unknown inputs");
                    Equal(1, sdk.ObjectReadySubscriberCount); Equal(1, sdk.CompletedSubscriberCount);
                    SdkLifeAssertPairDisposes(pair, 0); SdkLifeAssertBorrowedTarget(target);
                    Equal(0, output.ConcreteDisposeCalls); Equal(0, reads); Equal(1, target.InvokeCalls);
                    caller.Cancel(); caller.Cancel();
                    Check(!run.IsCompleted && !close.IsCompleted, "repeated SDK stop invented final completion");
                    BatteryThrows<InvalidOperationException>(() => invocation.RunAndCloseAsync(value => { }));
                    sdk.EmitCompleted(ManagementStatus.AccessDenied); // Explicit fake final only.
                    await CooperativeAwait(run);
                    Check(ReferenceEquals(shown, await run), "late SDK cleanup replaced an already displayed result");
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await close);
                    SdkLifeAssertPairDisposes(pair, 1); SdkLifeAssertBorrowedTarget(target); SdkLifeAssertUnsubscribed(sdk);
                    Equal(1, target.InvokeCalls); Equal(1, reports); Equal(1, output.ConcreteDisposeCalls); Equal(0, reads);
                    Equal(1, gate.LastLease.DisposeCalls); Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                }
                finally
                {
                    var close = invocation.RequestCloseAsync();
                    try
                    {
                        if (target.InvokeCalls == 0 && !run.IsCompleted)
                            await CooperativeAwait(Task.WhenAny(entered.Task, run));
                    }
                    finally
                    {
                        try { if (target.InvokeCalls != 0) sdk.EmitCompleted(ManagementStatus.AccessDenied); }
                        finally
                        {
                            try { await CooperativeAwait(close); }
                            finally { await CooperativeAwait(run); }
                        }
                    }
                }
            }
        });

        AddAsync("SDK binding lifetime report exception joins the owner lease and then the owned input cleanup", async () =>
        {
            using (var releaseLease = new ManualResetEventSlim())
            using (var releaseInput = new ManualResetEventSlim())
            {
                var target = new ManagementObject(); var facts = SingleReadTarget(target); var plan = SingleReadPlanCreate(facts);
                var sdk = new ManagementOperationObserver(); var pair = InputPreparationPair.Create();
                var lease = new CooperativeTestLease { OnDispose = () => SdkLifeWait(releaseLease) };
                var gate = new CooperativeTestGate { Handler = (timeout, stop) =>
                    new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired, lease) };
                var inputEntered = CooperativeCompletion(); var published = CooperativeCompletion();
                pair.Parameters.OnDispose = () => { inputEntered.TrySetResult(true); SdkLifeWait(releaseInput); };
                ManagementBaseObject embedded; var output = WindowsOutputFixture(BoundChannelReply(), out embedded);
                target.OnInvoke = (observer, method, input, options) =>
                {
                    observer.EmitObjectReady(output); observer.EmitCompleted(ManagementStatus.NoError);
                };
                var prepared = await SdkLifeReady(SdkLifePrepare(plan, facts, target, sdk, pair, gate));
                var invocation = prepared.Invocation; int reports = 0;
                var run = invocation.RunAndCloseAsync(value =>
                {
                    Interlocked.Increment(ref reports); published.TrySetResult(true); throw new SdkLifeReportException();
                });
                try
                {
                    await CooperativeAwait(lease.DisposeEntered.Task);
                    SdkLifeAssertPairDisposes(pair, 0); SdkLifeAssertBorrowedTarget(target); SdkLifeAssertUnsubscribed(sdk);
                    var close = invocation.RequestCloseAsync(); await CooperativeAwait(published.Task);
                    Check(!run.IsCompleted && !close.IsCompleted && lease.IsHeld, "report fault bypassed SDK owner cleanup");
                    SdkLifeAssertPairDisposes(pair, 0);
                    releaseLease.Set(); await CooperativeAwait(inputEntered.Task);
                    Check(!lease.IsHeld && !run.IsCompleted && !close.IsCompleted, "report fault bypassed SDK input cleanup");
                    Equal(1, pair.Parameters.ConcreteDisposeCalls); Equal(0, pair.Buffer.ConcreteDisposeCalls);
                    SdkLifeAssertBorrowedTarget(target);
                    releaseInput.Set(); await SdkLifeExpectReportFailure(run);
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await close);
                    SdkLifeAssertPairDisposes(pair, 1); SdkLifeAssertBorrowedTarget(target);
                    Equal(1, target.InvokeCalls); Equal(1, reports); Equal(1, lease.DisposeCalls);
                    Equal(gate.AcquireThread, lease.DisposeThread);
                    Equal(1, output.ConcreteDisposeCalls); Equal(1, embedded.ConcreteDisposeCalls);
                }
                finally
                {
                    var close = invocation.RequestCloseAsync(); releaseLease.Set(); releaseInput.Set();
                    try { await CooperativeAwait(close); }
                    finally { await SdkLifeExpectReportFailure(run); }
                }
            }
        });

        AddAsync("SDK binding lifetime borrowed target output roots and queued aliases never read or dispose the target", async () =>
        {
            using (var releaseInvoke = new ManualResetEventSlim())
            {
                var target = new ManagementObject(); var facts = SingleReadTarget(target); var plan = SingleReadPlanCreate(facts);
                var sdk = new ManagementOperationObserver(); var pair = InputPreparationPair.Create(); var gate = new CooperativeTestGate();
                var terminalSent = CooperativeCompletion(); bool guarded = false; int targetReads = 0;
                SdkLifeGuardTarget(target, () => guarded, () => Interlocked.Increment(ref targetReads));
                ObjectReadyEventHandler queued = null;
                target.OnInvoke = (observer, method, input, options) =>
                {
                    queued = observer.ObjectReadySnapshot; guarded = true;
                    observer.EmitObjectReady(target); observer.EmitCompleted(ManagementStatus.NoError);
                    terminalSent.TrySetResult(true); SdkLifeWait(releaseInvoke);
                };
                var prepared = await SdkLifeReady(SdkLifePrepare(plan, facts, target, sdk, pair, gate));
                var invocation = prepared.Invocation; var run = invocation.RunAndCloseAsync(value => { });
                try
                {
                    await CooperativeAwait(terminalSent.Task);
                    Equal(0, targetReads); SdkLifeAssertBorrowedTarget(target); SdkLifeAssertPairDisposes(pair, 0);
                    Check(!run.IsCompleted && gate.LastLease.IsHeld, "borrowed target root escaped the live SDK stack boundary");
                    releaseInvoke.Set(); await CooperativeAwait(run);
                    AssertFrameExchangeFailure(await run, WsabiWmiFrameExchangeStatus.TransportFailure);
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await invocation.RequestCloseAsync());
                    SdkLifeAssertPairDisposes(pair, 1); SdkLifeAssertBorrowedTarget(target); Equal(0, targetReads);
                    queued(sdk, new ObjectReadyEventArgs(target)); queued(sdk, new ObjectReadyEventArgs(target));
                    SdkLifeAssertBorrowedTarget(target); Equal(0, targetReads); Equal(1, target.InvokeCalls);
                    SdkLifeAssertPairDisposes(pair, 1); SdkLifeAssertUnsubscribed(sdk);
                }
                finally
                {
                    var close = invocation.RequestCloseAsync(); releaseInvoke.Set();
                    try { await CooperativeAwait(close); }
                    finally { await CooperativeAwait(run); }
                }
            }
        });

        AddAsync("SDK binding lifetime borrowed target embedded output is rejected before metadata or disposal", async () =>
        {
            using (var releaseInvoke = new ManualResetEventSlim())
            {
                var target = new ManagementObject(); var facts = SingleReadTarget(target); var plan = SingleReadPlanCreate(facts);
                var sdk = new ManagementOperationObserver(); var pair = InputPreparationPair.Create(); var gate = new CooperativeTestGate();
                var terminalSent = CooperativeCompletion(); bool guarded = false; int targetReads = 0;
                SdkLifeGuardTarget(target, () => guarded, () => Interlocked.Increment(ref targetReads));
                var output = WindowsOutputRoot(target); ObjectReadyEventHandler queued = null;
                target.OnInvoke = (observer, method, input, options) =>
                {
                    queued = observer.ObjectReadySnapshot; guarded = true;
                    observer.EmitObjectReady(output); observer.EmitCompleted(ManagementStatus.NoError);
                    terminalSent.TrySetResult(true); SdkLifeWait(releaseInvoke);
                };
                var prepared = await SdkLifeReady(SdkLifePrepare(plan, facts, target, sdk, pair, gate));
                var invocation = prepared.Invocation; var run = invocation.RunAndCloseAsync(value => { });
                try
                {
                    await CooperativeAwait(terminalSent.Task);
                    Equal(1, output.Properties["outData"].ValueReads); Equal(1, output.ConcreteDisposeCalls);
                    Equal(0, targetReads); SdkLifeAssertBorrowedTarget(target); SdkLifeAssertPairDisposes(pair, 0);
                    Check(!run.IsCompleted && gate.LastLease.IsHeld, "embedded borrowed target escaped the SDK invocation lifetime");
                    releaseInvoke.Set(); await CooperativeAwait(run);
                    AssertFrameExchangeFailure(await run, WsabiWmiFrameExchangeStatus.TransportFailure);
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await invocation.RequestCloseAsync());
                    SdkLifeAssertPairDisposes(pair, 1); SdkLifeAssertBorrowedTarget(target); Equal(1, output.ConcreteDisposeCalls);
                    queued(sdk, new ObjectReadyEventArgs(target)); queued(sdk, new ObjectReadyEventArgs(target));
                    SdkLifeAssertBorrowedTarget(target); Equal(0, targetReads); Equal(1, target.InvokeCalls);
                    SdkLifeAssertPairDisposes(pair, 1); SdkLifeAssertUnsubscribed(sdk);
                }
                finally
                {
                    var close = invocation.RequestCloseAsync(); releaseInvoke.Set();
                    try { await CooperativeAwait(close); }
                    finally { await CooperativeAwait(run); }
                }
            }
        });

        AddAsync("SDK binding lifetime input cleanup failure never consumes borrowed target ownership", async () =>
        {
            using (var releaseBuffer = new ManualResetEventSlim())
            {
                var target = new ManagementObject(); var facts = SingleReadTarget(target); var plan = SingleReadPlanCreate(facts);
                var sdk = new ManagementOperationObserver(); var pair = InputPreparationPair.Create(); var gate = new CooperativeTestGate();
                var bufferEntered = CooperativeCompletion(); var published = CooperativeCompletion();
                pair.Parameters.OnDispose = () => throw new InvalidOperationException("PRIVATE-SDK owned cleanup failure");
                pair.Buffer.OnDispose = () => { bufferEntered.TrySetResult(true); SdkLifeWait(releaseBuffer); };
                target.OnDispose = () => throw new InvalidOperationException("PRIVATE-SDK borrowed target must not be disposed");
                ManagementBaseObject embedded; var output = WindowsOutputFixture(BoundChannelReply(), out embedded);
                target.OnInvoke = (observer, method, input, options) =>
                {
                    observer.EmitObjectReady(output); observer.EmitCompleted(ManagementStatus.NoError);
                };
                var prepared = await SdkLifeReady(SdkLifePrepare(plan, facts, target, sdk, pair, gate));
                var invocation = prepared.Invocation; int reports = 0;
                var run = invocation.RunAndCloseAsync(value =>
                {
                    Check(value.IsValidFrame, "inner SDK result was replaced before input cleanup");
                    Interlocked.Increment(ref reports); published.TrySetResult(true);
                });
                try
                {
                    await CooperativeAwait(published.Task); await CooperativeAwait(bufferEntered.Task);
                    var close = invocation.RequestCloseAsync();
                    Check(!run.IsCompleted && !close.IsCompleted, "input cleanup failure escaped before the second cleanup ended");
                    SdkLifeAssertPairDisposes(pair, 1); SdkLifeAssertBorrowedTarget(target);
                    Equal(1, gate.LastLease.DisposeCalls); Check(!gate.LastLease.IsHeld, "input cleanup began before SDK owner release");
                    releaseBuffer.Set(); await SdkLifeExpectFixedFailure(run);
                    Equal(WsabiWmiWindowsCleanupStatus.Failed, await close);
                    Check(ReferenceEquals(close, invocation.RequestCloseAsync()), "failed SDK input cleanup was retried");
                    SdkLifeAssertPairDisposes(pair, 1); SdkLifeAssertBorrowedTarget(target); SdkLifeAssertUnsubscribed(sdk);
                    Equal(1, target.InvokeCalls); Equal(1, reports); Equal(1, output.ConcreteDisposeCalls); Equal(1, embedded.ConcreteDisposeCalls);
                    Check(prepared.InputCleanupStatus == null, "Ready snapshot incorrectly reported final input cleanup");
                }
                finally
                {
                    var close = invocation.RequestCloseAsync(); releaseBuffer.Set();
                    try { await CooperativeAwait(close); }
                    finally { await SdkLifeExpectFixedFailure(run); }
                }
            }
        });
    }

    private static Task<WsabiWmiSingleReadPreparationResult> SdkLifePrepare(WsabiWmiSingleReadPlan plan,
        WsabiWmiSingleReadTarget facts, ManagementObject target, ManagementOperationObserver sdk,
        InputPreparationPair pair, CooperativeTestGate gate, TimeSpan? responseTimeout = null,
        CancellationToken token = default(CancellationToken))
        => WsabiWmiWindowsSingleReadPreparation.PrepareSdkBindingAsync(plan,
            new WsabiWmiWindowsSdkBinding(facts, target, sdk, pair.Parameters, pair.Buffer), InputPreparationRequest(),
            gate, TimeSpan.FromMilliseconds(200), responseTimeout ?? TimeSpan.FromSeconds(3), token);

    private static async Task<WsabiWmiSingleReadPreparationResult> SdkLifeReady(Task<WsabiWmiSingleReadPreparationResult> preparing)
    {
        await CooperativeAwait(preparing); var result = await preparing;
        Equal(WsabiWmiSingleReadPreparationStatus.Ready, result.Status);
        Equal((WsabiWmiWindowsSdkBindingStatus?)WsabiWmiWindowsSdkBindingStatus.Ready, result.SdkStatus);
        Equal((WsabiWmiWindowsInputPreparationStatus?)WsabiWmiWindowsInputPreparationStatus.Populated, result.InputStatus);
        Check(result.IsReady && result.Invocation != null && result.InputOwnershipTransferred && result.InputCleanupStatus == null,
            "SDK lifetime fixture did not transfer a prepared input pair");
        return result;
    }

    private static async Task SdkLifeClosePreparation(Task<WsabiWmiSingleReadPreparationResult> preparing)
    {
        await CooperativeAwait(preparing); var result = await preparing;
        if (result.Invocation != null) await CooperativeAwait(result.Invocation.RequestCloseAsync());
    }

    private static void SdkLifeAssertPairDisposes(InputPreparationPair pair, int expected)
    {
        Equal(expected, pair.Parameters.ConcreteDisposeCalls); Equal(expected, pair.Buffer.ConcreteDisposeCalls);
        Equal(0, pair.Parameters.ComponentDisposeCalls); Equal(0, pair.Buffer.ComponentDisposeCalls);
    }

    private static void SdkLifeAssertBorrowedTarget(ManagementObject target)
    {
        Equal(0, target.ConcreteDisposeCalls); Equal(0, target.ComponentDisposeCalls);
    }

    private static void SdkLifeAssertUnsubscribed(ManagementOperationObserver sdk)
    {
        Equal(0, sdk.ObjectReadySubscriberCount); Equal(0, sdk.CompletedSubscriberCount);
    }

    private static void SdkLifeWait(ManualResetEventSlim release)
    {
        if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("SDK lifetime stand-in gate was not released.");
    }

    private static void SdkLifeGuardTarget(ManagementObject target, Func<bool> guarded, Action touched)
    {
        var scope = target.Scope; var path = target.Path; var properties = target.Properties; var classPath = target.ClassPath;
        target.OnGetScope = () => { if (guarded()) { touched(); throw new InvalidOperationException("PRIVATE-SDK borrowed target scope"); } return scope; };
        target.OnGetPath = () => { if (guarded()) { touched(); throw new InvalidOperationException("PRIVATE-SDK borrowed target path"); } return path; };
        target.OnGetProperties = () => { if (guarded()) { touched(); throw new InvalidOperationException("PRIVATE-SDK borrowed target properties"); } return properties; };
        target.OnGetClassPath = () => { if (guarded()) { touched(); throw new InvalidOperationException("PRIVATE-SDK borrowed target class"); } return classPath; };
    }

    private static async Task SdkLifeExpectFixedFailure(Task run)
    {
        try { await CooperativeAwait(run); }
        catch (InvalidOperationException error)
        {
            Check(error.InnerException == null && error.Message.IndexOf("PRIVATE-SDK", StringComparison.Ordinal) < 0,
                "SDK binding exposed a source or cleanup exception");
            return;
        }
        throw new InvalidOperationException("Expected a fixed SDK binding cleanup failure.");
    }

    private static async Task SdkLifeExpectReportFailure(Task run)
    {
        try { await CooperativeAwait(run); }
        catch (SdkLifeReportException) { return; }
        throw new InvalidOperationException("SDK host did not preserve its report exception.");
    }

    private sealed class SdkLifeReportException : Exception
    {
        internal SdkLifeReportException() : base("Fixed SDK lifetime report failure.") { }
    }
}
