using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    // All factory/source/cleanup work below is an inert managed fake. The
    // sealed approved attempt supplies bytes, but none is sent to an SDK.
    private static void RegisterWsabiWmiProtectionDisableSessionTests()
    {
        AddAsync("disable facade validates dependencies and target identity and unused close creates no leaf", async () =>
        {
            var fixture = new DisableSessionFixture();
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiProtectionDisableSession(null, fixture.Factory, fixture.Gate));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiProtectionDisableSession(fixture.Attempt, null, fixture.Gate));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiProtectionDisableSession(fixture.Attempt, fixture.Factory, null));
            var wrong = new DisableSessionFactory(new SingleReadPoisonIdentity());
            BatteryThrows<ArgumentException>(() => new WsabiWmiProtectionDisableSession(fixture.Attempt, wrong, fixture.Gate));
            Equal(0, wrong.Calls);
            Equal(WsabiWmiProtectionCleanupStatus.Complete, await fixture.Session.RequestCloseAsync());
            Equal(WsabiWmiProtectionDisableStatus.AlreadyUsed, (await fixture.Session.RunAsync()).Status);
            Equal(0, fixture.Factory.Calls); Equal(0, fixture.Gate.Calls);
            Check(!fixture.Session.CanWriteHardware && !fixture.Session.IsChargeLimitConfirmed,
                "construction or unused close granted charge authority");
        });

        AddAsync("disable facade lazily prepares the three exact requests under one owner and preserves receipt semantics", async () =>
        {
            var fixture = new DisableSessionFixture();
            Equal(0, fixture.Factory.Calls); Check(fixture.Factory.Nodes.All(node => node.Invocations == 0), "leaf work existed before Run");
            try
            {
                var outcome = await DisableSessionOutcome(fixture.Session.RunAsync());
                DisableSessionAssert(outcome, WsabiWmiProtectionDisableStatus.StoredReadbackMatchedCandidate, 3);
                Equal(2, outcome.Snapshot.BoundReadCandidateCount);
                Check(outcome.Snapshot.SetterReceiptAccepted && !outcome.Snapshot.SetterAcknowledged,
                    "receipt was promoted to a semantic setter acknowledgement");
                Check(fixture.Factory.Order.SequenceEqual(WsabiWmiProtectionDisableReview.StageOrder), "facade changed fixed stage order");
                Equal(3, fixture.Factory.Calls);
                Check(fixture.Factory.Nodes.All(node => node.Invocations == 1 && node.OutputCalls == 1 && node.InputCalls == 1),
                    "facade retried, skipped or leaked a normal leaf");
                Check(fixture.Factory.PrepareThreads.All(thread => thread == fixture.Gate.AcquireThread), "leaf admission left the owner thread");
                await DisableSessionClosed(fixture); Equal(1, fixture.Gate.Calls);
            }
            finally { await DisableSessionFinish(fixture); }
        });

        AddAsync("disable facade gate rejection and pre cancellation create no SDK leaf or invocation", async () =>
        {
            foreach (bool cancelled in new[] { false, true })
            {
                var gate = new CooperativeTestGate { Handler = (timeout, signal) =>
                    new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.AccessDenied) };
                var fixture = new DisableSessionFixture(gate: gate);
                try
                {
                    var outcome = await DisableSessionOutcome(fixture.Session.RunAsync(new CancellationToken(cancelled)));
                    DisableSessionAssert(outcome, cancelled ? WsabiWmiProtectionDisableStatus.Cancelled : WsabiWmiProtectionDisableStatus.GateRejected, 0);
                    await CooperativeAwait(fixture.Session.RequestCloseAsync());
                    Equal(0, fixture.Factory.Calls); Check(fixture.Factory.Nodes.All(node => node.Invocations == 0), "no-owner path entered a source");
                    Equal(cancelled ? 0 : 1, gate.Calls);
                }
                finally { await DisableSessionFinish(fixture); }
            }
        });

        AddAsync("disable facade pre mode rejection post mismatch and ambiguous reads stop at their fixed budgets", async () =>
        {
            foreach (bool failure in new[] { false, true })
            {
                var fixture = new DisableSessionFixture();
                fixture.Factory.Nodes[0].ChangeReply = bytes =>
                { if (failure) { Array.Clear(bytes, 5, 16); bytes[5] = 0xff; } else bytes[7] = 0; };
                try
                {
                    var outcome = await DisableSessionOutcome(fixture.Session.RunAsync());
                    DisableSessionAssert(outcome, WsabiWmiProtectionDisableStatus.StageRejected, 1);
                    Check(!outcome.SetterRoleStarted && !outcome.Snapshot.SetterReceiptAccepted, "invalid pre mode entered setting stage");
                    if (!failure)
                    {
                        Equal(WsabiWmiProtectionDisableDecisionStatus.AlreadyDisabledCandidate, outcome.LastDecisionStatus.Value);
                        Equal<int?>(0, outcome.Snapshot.ObservedPreModeByte);
                    }
                    Equal(1, fixture.Factory.Calls); DisableSessionPrefix(fixture, 1);
                    await DisableSessionClosed(fixture);
                }
                finally { await DisableSessionFinish(fixture); }
            }
            foreach (int index in new[] { 1, 2 })
            {
                var fixture = new DisableSessionFixture(); var node = fixture.Factory.Nodes[index];
                node.ChangeReply = bytes => bytes[7] = 1;
                try
                {
                    var outcome = await DisableSessionOutcome(fixture.Session.RunAsync());
                    DisableSessionAssert(outcome, WsabiWmiProtectionDisableStatus.StageRejected, index + 1);
                    Equal(index >= 2, outcome.Snapshot.SetterReceiptAccepted);
                    Check(!outcome.Snapshot.SetterAcknowledged, "post failure fabricated setter acknowledgement");
                    DisableSessionPrefix(fixture, index + 1); await DisableSessionClosed(fixture);
                }
                finally { await DisableSessionFinish(fixture); }
            }
        });

        AddAsync("disable facade cannot rewrap a consumed attempt into another factory and gate", async () =>
        {
            var fixture = new DisableSessionFixture();
            try
            {
                await DisableSessionOutcome(fixture.Session.RunAsync()); await DisableSessionClosed(fixture);
                var factory = new DisableSessionFactory(fixture.Factory.TargetIdentity); var gate = new CooperativeTestGate();
                var peer = new WsabiWmiProtectionDisableSession(fixture.Attempt, factory, gate);
                Equal(WsabiWmiProtectionDisableStatus.AlreadyUsed, (await peer.RunAsync()).Status);
                Equal(WsabiWmiProtectionCleanupStatus.Complete, await peer.RequestCloseAsync());
                Equal(0, factory.Calls); Equal(0, gate.Calls);
            }
            finally { await DisableSessionFinish(fixture); }
        });

        AddAsync("disable facade not ready partial preparation closes output then inputs without invoking the source", async () =>
        {
            var fixture = new DisableSessionFixture(); fixture.Factory.Nodes[0].Ready = false;
            try
            {
                var outcome = await DisableSessionOutcome(fixture.Session.RunAsync());
                DisableSessionAssert(outcome, WsabiWmiProtectionDisableStatus.StageRejected, 1);
                var node = fixture.Factory.Nodes[0];
                Equal(0, node.Invocations); Equal(1, node.OutputCalls); Equal(1, node.InputCalls);
                Check(node.CleanupOrder.SequenceEqual(new[] { "output", "input" }), "partial preparation cleanup order changed");
                Equal(1, fixture.Factory.Calls); await DisableSessionClosed(fixture);
            }
            finally { await DisableSessionFinish(fixture); }
        });

        AddAsync("disable facade early terminal and capture cannot close outputs while Invoke still owns its stack", async () =>
        {
            using (var release = new ManualResetEventSlim())
            {
                var fixture = new DisableSessionFixture(); var node = fixture.Factory.Nodes[0];
                var reported = CooperativeCompletion();
                node.Invoke = (request, observer) =>
                {
                    node.SupplyFinal(); reported.TrySetResult(true);
                    Check(release.Wait(TimeSpan.FromSeconds(5)), "fake invocation stack was never released");
                };
                var run = fixture.Session.RunAsync();
                try
                {
                    await CooperativeAwait(reported.Task);
                    Equal(0, node.OutputCalls); Equal(0, node.InputCalls);
                    var close = fixture.Session.RequestCloseAsync();
                    Equal(WsabiWmiProtectionDisableStatus.Cancelled, (await DisableSessionOutcome(run)).Status);
                    Check(!close.IsCompleted && fixture.Gate.LastLease.IsHeld, "stop released an active invocation stack");
                    release.Set(); await CooperativeAwait(close); DisableSessionPrefix(fixture, 1);
                    await DisableSessionClosed(fixture);
                }
                finally { release.Set(); await DisableSessionFinish(fixture); }
            }
        });

        AddAsync("disable facade serializes output and input close and neither pending cleanup permits the next role", async () =>
        {
            foreach (bool outputPending in new[] { false, true })
            {
                var fixture = new DisableSessionFixture(); var node = fixture.Factory.Nodes[0];
                var cleanup = new TaskCompletionSource<WsabiWmiProtectionCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
                if (outputPending) node.Output = () => cleanup.Task; else node.Input = () => cleanup.Task;
                var run = fixture.Session.RunAsync();
                try
                {
                    await InvocationEventually(() => outputPending ? node.OutputCalls == 1 : node.InputCalls == 1);
                    Check(!run.IsCompleted && fixture.Gate.LastLease.IsHeld, "pending close was erased before the next role");
                    Equal(outputPending ? 0 : 1, node.InputCalls); Equal(1, fixture.Factory.Calls);
                    var closing = fixture.Session.RequestCloseAsync();
                    DisableSessionAssert(await DisableSessionOutcome(run), WsabiWmiProtectionDisableStatus.Cancelled, 1);
                    Check(!closing.IsCompleted, "caller close bypassed a pending cleanup");
                    cleanup.TrySetResult(WsabiWmiProtectionCleanupStatus.Complete);
                    await CooperativeAwait(closing); DisableSessionPrefix(fixture, 1);
                    await DisableSessionClosed(fixture);
                }
                finally { cleanup.TrySetResult(WsabiWmiProtectionCleanupStatus.Complete); await DisableSessionFinish(fixture); }
            }
        });

        AddAsync("disable facade failed unknown faulted cancelled or missing output cleanup never releases inputs", async () =>
        {
            for (int variant = 0; variant < 5; variant++)
            {
                var fixture = new DisableSessionFixture(); var node = fixture.Factory.Nodes[0]; int selected = variant;
                node.Output = () => selected == 0 ? Task.FromResult(WsabiWmiProtectionCleanupStatus.Failed)
                    : selected == 1 ? Task.FromResult(WsabiWmiProtectionCleanupStatus.Unknown)
                    : selected == 2 ? Task.FromException<WsabiWmiProtectionCleanupStatus>(new InvalidOperationException("Unreported fake close detail."))
                    : selected == 3 ? Task.FromCanceled<WsabiWmiProtectionCleanupStatus>(new CancellationToken(true)) : null;
                try
                {
                    DisableSessionAssert(await DisableSessionOutcome(fixture.Session.RunAsync()), WsabiWmiProtectionDisableStatus.CompletionUnknown, 1);
                    Equal(1, node.OutputCalls); Equal(0, node.InputCalls); Equal(1, fixture.Factory.Calls);
                    Check(fixture.Gate.LastLease.IsHeld && !fixture.Session.RequestCloseAsync().IsCompleted,
                        "unproven output ownership released its inputs or lease");
                }
                finally { await DisableSessionFinish(fixture); }
            }
        });

        AddAsync("disable facade failed input close keeps the procedure unknown despite a complete output cleanup", async () =>
        {
            foreach (var status in new[] { WsabiWmiProtectionCleanupStatus.Failed, WsabiWmiProtectionCleanupStatus.Unknown })
            {
                var fixture = new DisableSessionFixture(); var node = fixture.Factory.Nodes[1];
                node.Input = () => Task.FromResult(status);
                try
                {
                    var outcome = await DisableSessionOutcome(fixture.Session.RunAsync());
                    DisableSessionAssert(outcome, WsabiWmiProtectionDisableStatus.CompletionUnknown, 2);
                    Equal(1, node.OutputCalls); Equal(1, node.InputCalls);
                    Check(fixture.Gate.LastLease.IsHeld && !fixture.Session.RequestCloseAsync().IsCompleted,
                        "input disposal failure became a successful actual-close witness");
                    DisableSessionPrefix(fixture, 2);
                }
                finally { await DisableSessionFinish(fixture); }
            }
        });

        AddAsync("disable facade late prepared leaf is retired without invocation after stop or display timeout", async () =>
        {
            foreach (bool timeout in new[] { false, true })
            using (var stop = new CancellationTokenSource())
            {
                var fixture = new DisableSessionFixture(display: timeout ? TimeSpan.FromMilliseconds(500) : TimeSpan.FromSeconds(3));
                var node = fixture.Factory.Nodes[0]; node.Preparation = new TaskCompletionSource<WsabiWmiProtectionLeaf>(TaskCreationOptions.RunContinuationsAsynchronously);
                var run = fixture.Session.RunAsync(stop.Token);
                try
                {
                    await CooperativeAwait(node.Prepared.Task); if (!timeout) stop.Cancel();
                    DisableSessionAssert(await DisableSessionOutcome(run), timeout ? WsabiWmiProtectionDisableStatus.TimedOut : WsabiWmiProtectionDisableStatus.Cancelled, 1);
                    Equal(0, node.Invocations); Check(fixture.Gate.LastLease.IsHeld && !fixture.Session.RequestCloseAsync().IsCompleted,
                        "pending SDK preparation was abandoned at the display boundary");
                    node.Preparation.TrySetResult(node.MakeLeaf());
                    await DisableSessionClosed(fixture); Equal(0, node.Invocations);
                    Equal(1, node.OutputCalls); Equal(1, node.InputCalls); DisableSessionPrefix(fixture, 1, noInvocationAt: 0);
                }
                finally { await DisableSessionFinish(fixture); }
            }
        });

        AddAsync("disable facade source throw without a terminal remains pending until late applicable termination and capture", async () =>
        {
            var fixture = new DisableSessionFixture(display: TimeSpan.FromMilliseconds(500)); var node = fixture.Factory.Nodes[0];
            node.Invoke = (request, observer) => { throw new InvalidOperationException("Unreported fake invocation detail."); };
            var run = fixture.Session.RunAsync();
            try
            {
                await CooperativeAwait(node.Returned.Task);
                DisableSessionAssert(await DisableSessionOutcome(run), WsabiWmiProtectionDisableStatus.TimedOut, 1);
                Equal(0, node.OutputCalls); Equal(0, node.InputCalls);
                Check(fixture.Gate.LastLease.IsHeld && !fixture.Session.RequestCloseAsync().IsCompleted, "throw manufactured provider termination");
                node.SupplyFinal(); await DisableSessionClosed(fixture);
                DisableSessionPrefix(fixture, 1); Equal(WsabiWmiProtectionDisableStatus.TimedOut, (await run).Status);
            }
            finally { await DisableSessionFinish(fixture); }
        });

        AddAsync("disable facade reporting exception still joins pending input cleanup and cannot restart later roles", async () =>
        {
            var fixture = new DisableSessionFixture(display: TimeSpan.FromMilliseconds(500)); var node = fixture.Factory.Nodes[1];
            var input = new TaskCompletionSource<WsabiWmiProtectionCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
            node.Input = () => input.Task;
            var published = CooperativeCompletion(); var error = new DisableSessionReportException();
            var run = fixture.Session.RunAndCloseAsync(outcome => { published.TrySetResult(true); throw error; });
            try
            {
                await CooperativeAwait(published.Task);
                Check(!run.IsCompleted && fixture.Gate.LastLease.IsHeld && node.InputCalls == 1,
                    "reporter exception escaped the actual cleanup barrier");
                input.TrySetResult(WsabiWmiProtectionCleanupStatus.Complete);
                try { await CooperativeAwait(run); throw new InvalidOperationException("Expected fake reporting failure."); }
                catch (DisableSessionReportException observed) { Check(ReferenceEquals(error, observed), "reporting error changed during join"); }
                await DisableSessionClosed(fixture); DisableSessionPrefix(fixture, 2);
            }
            finally
            {
                input.TrySetResult(WsabiWmiProtectionCleanupStatus.Complete); await DisableSessionFinish(fixture);
                try { await CooperativeAwait(run); } catch (DisableSessionReportException) { }
            }
        });

        AddAsync("disable mode reads reject unchanged input echo before or after the one setter", async () =>
        {
            foreach (int index in new[] { 0, 2 })
            {
                var fixture = new DisableSessionFixture();
                fixture.Factory.Nodes[index].ChangeReply = bytes => bytes[7] = 0xf0;
                try
                {
                    var result = await DisableSessionOutcome(fixture.Session.RunAsync());
                    DisableSessionAssert(result, WsabiWmiProtectionDisableStatus.StageRejected, index + 1);
                    Equal(index == 2, result.SetterRoleStarted);
                    Equal(index == 2, result.Snapshot.SetterReceiptAccepted);
                    Equal("AmbiguousInputEcho", fixture.Session.GetStageDiagnostics()[index].ReadVerdict);
                    DisableSessionPrefix(fixture, index + 1); await DisableSessionClosed(fixture);
                }
                finally { await DisableSessionFinish(fixture); }
            }
        });

        AddAsync("disable and original transition owners share sticky gate quarantine across purposes", async () =>
        {
            var oldOwner = new SevenStageFixture();
            oldOwner.Nodes[0].Lifetime.ReportUncertainClose();
            try
            {
                SevenStageAssertStatus(await SevenStageOutcome(oldOwner.Coordinator.RunAsync()), WsabiWmiSevenStageStatus.CompletionUnknown, 0);
                var blocked = new DisableSessionFixture(gate: oldOwner.Gate);
                try
                {
                    DisableSessionAssert(await DisableSessionOutcome(blocked.Session.RunAsync()), WsabiWmiProtectionDisableStatus.GateRejected, 0);
                    await CooperativeAwait(blocked.Session.RequestCloseAsync());
                    Equal(0, blocked.Factory.Calls); Equal(1, oldOwner.Gate.Calls);
                }
                finally { await DisableSessionFinish(blocked); }
            }
            finally { await SevenStageFinish(oldOwner); }

            var current = new DisableSessionFixture();
            current.Factory.Nodes[0].Output = () => Task.FromResult(WsabiWmiProtectionCleanupStatus.Unknown);
            try
            {
                DisableSessionAssert(await DisableSessionOutcome(current.Session.RunAsync()), WsabiWmiProtectionDisableStatus.CompletionUnknown, 1);
                var blocked = new SevenStageFixture(gate: current.Gate);
                try
                {
                    SevenStageAssertStatus(await SevenStageOutcome(blocked.Coordinator.RunAsync()), WsabiWmiSevenStageStatus.GateRejected, 0);
                    await CooperativeAwait(blocked.Coordinator.RequestCloseAsync());
                    Check(blocked.Nodes.All(node => node.Calls == 0), "old purpose bypassed disable quarantine");
                    Equal(1, current.Gate.Calls);
                }
                finally { await SevenStageFinish(blocked); }
            }
            finally { await DisableSessionFinish(current); }
        });

    }

    private static async Task<WsabiWmiProtectionDisableOutcome> DisableSessionOutcome(Task<WsabiWmiProtectionDisableOutcome> run)
    { await CooperativeAwait(run); return await run; }
    private static void DisableSessionAssert(WsabiWmiProtectionDisableOutcome result, WsabiWmiProtectionDisableStatus status, int stages)
    {
        Equal(status, result.Status); Equal(stages, result.StartedStages);
        Check(!result.CanWriteHardware && !result.IsChargeLimitConfirmed && !result.Snapshot.IsHardwareObservation &&
            !result.Snapshot.IsChargeLimitConfirmed, "fake facade result became charge-control evidence");
    }
    private static void DisableSessionPrefix(DisableSessionFixture fixture, int count, int noInvocationAt = -1)
    {
        for (int i = 0; i < 3; i++) Equal(i < count && i != noInvocationAt ? 1 : 0, fixture.Factory.Nodes[i].Invocations);
        Equal(count, fixture.Factory.Calls);
    }
    private static async Task DisableSessionClosed(DisableSessionFixture fixture)
    {
        await CooperativeAwait(fixture.Session.RequestCloseAsync());
        Equal(WsabiWmiProtectionCleanupStatus.Complete, await fixture.Session.RequestCloseAsync());
        Check(fixture.Gate.LastLease != null && !fixture.Gate.LastLease.IsHeld, "facade close completed before its lease was released");
        Equal(1, fixture.Gate.LastLease.DisposeCalls); Equal(fixture.Gate.AcquireThread, fixture.Gate.LastLease.DisposeThread);
    }
    private static async Task DisableSessionFinish(DisableSessionFixture fixture)
    {
        var close = fixture.Session.RequestCloseAsync();
        foreach (var node in fixture.Factory.Nodes)
        {
            node.Preparation?.TrySetResult(node.MakeLeaf());
            node.SupplyFinal();
            if (node.Invocations != 0) await CooperativeAwait(node.Returned.Task);
        }
        foreach (var node in fixture.Factory.Nodes)
        {
            if (node.Request == null) continue; // Unused handle owned no work.
            await InvocationEventually(() => node.OutputCalls != 0);
            await CooperativeAwait(node.OutputFinished.Task);
            if (node.OutputSucceeded)
            {
                await InvocationEventually(() => node.InputCalls != 0);
                await CooperativeAwait(node.InputFinished.Task);
            }
        }
        // Every source here is an explicitly detached fake; no SDK resource
        // exists. Failed cleanup promises stay failed and are never repaired.
        fixture.Session.ConfirmDetachedForTests();
        await CooperativeAwait(close);
    }

    private sealed class DisableSessionFixture
    {
        internal readonly WsabiWmiProtectionDisableAttempt Attempt;
        internal readonly DisableSessionFactory Factory;
        internal readonly CooperativeTestGate Gate;
        internal readonly WsabiWmiProtectionDisableSession Session;
        internal DisableSessionFixture(CooperativeTestGate gate = null, TimeSpan? display = null)
        {
            var identity = new SingleReadPoisonIdentity(); Attempt = DisableOwnerAttemptCreate(identity);
            Factory = new DisableSessionFactory(identity); Gate = gate ?? new CooperativeTestGate();
            Session = new WsabiWmiProtectionDisableSession(Attempt, Factory, Gate, TimeSpan.FromMilliseconds(200), display ?? TimeSpan.FromSeconds(3));
        }
    }
    private sealed class DisableSessionFactory : IWsabiWmiProtectionDisableLeafFactory
    {
        public object TargetIdentity { get; }
        internal readonly DisableSessionNode[] Nodes = Enumerable.Range(0, 3).Select(index => new DisableSessionNode(index)).ToArray();
        internal readonly List<WsabiWmiProtectionDisableStage> Order = new List<WsabiWmiProtectionDisableStage>();
        internal readonly List<int> PrepareThreads = new List<int>();
        private int calls;
        internal int Calls => Volatile.Read(ref calls);
        internal DisableSessionFactory(object target) { TargetIdentity = target; }
        public Task<WsabiWmiProtectionLeaf> PrepareAsync(WsabiWmiProtectionDisableLeafRequest request, WsabiWmiProtectionStop stop)
        {
            Interlocked.Increment(ref calls); Order.Add(request.Role); PrepareThreads.Add(Thread.CurrentThread.ManagedThreadId);
            var node = Nodes[(int)request.Role]; node.Request = request; node.Stop = stop; node.Prepared.TrySetResult(true);
            return node.Preparation == null ? Task.FromResult(node.MakeLeaf()) : node.Preparation.Task;
        }
    }
    private sealed class DisableSessionNode : IWsabiWmiInvocationSource
    {
        private readonly int index;
        private int invocations, outputs, inputs;
        internal int Invocations => Volatile.Read(ref invocations);
        internal int OutputCalls => Volatile.Read(ref outputs);
        internal int InputCalls => Volatile.Read(ref inputs);
        internal bool Ready = true;
        internal WsabiWmiProtectionDisableLeafRequest Request;
        internal WsabiWmiProtectionStop Stop;
        internal IWsabiWmiInvocationObserver Observer;
        internal TaskCompletionSource<WsabiWmiProtectionLeaf> Preparation;
        internal readonly TaskCompletionSource<bool> Prepared = CooperativeCompletion(), Returned = CooperativeCompletion();
        internal readonly TaskCompletionSource<bool> OutputFinished = CooperativeCompletion(), InputFinished = CooperativeCompletion();
        internal bool OutputSucceeded;
        internal readonly List<string> CleanupOrder = new List<string>();
        internal Action<WsabiWmiMethodRequest, IWsabiWmiInvocationObserver> Invoke;
        internal Action<byte[]> ChangeReply;
        internal Func<Task<WsabiWmiProtectionCleanupStatus>> Output = () => Task.FromResult(WsabiWmiProtectionCleanupStatus.Complete);
        internal Func<Task<WsabiWmiProtectionCleanupStatus>> Input = () => Task.FromResult(WsabiWmiProtectionCleanupStatus.Complete);
        internal DisableSessionNode(int index) { this.index = index; }
        void IWsabiWmiInvocationSource.Invoke(WsabiWmiMethodRequest request, IWsabiWmiInvocationObserver observer)
        {
            Interlocked.Increment(ref invocations); Observer = observer;
            try
            {
                Check(Request.Matches(request), "source received bytes different from its exact fixed leaf request");
                if (Invoke == null) SupplyFinal(); else Invoke(request, observer);
            }
            finally { Returned.TrySetResult(true); }
        }
        internal WsabiWmiProtectionLeaf MakeLeaf() => new WsabiWmiProtectionLeaf(Ready, this, CloseOutput, CloseInput);
        private Task<WsabiWmiProtectionCleanupStatus> CloseOutput()
        {
            try
            {
                Interlocked.Increment(ref outputs); CleanupOrder.Add("output");
                Check(Invocations == 0 || Returned.Task.IsCompleted, "output cleanup preceded invoke stack exit");
                var task = Output();
                if (task == null) { OutputFinished.TrySetResult(true); return null; }
                _ = task.ContinueWith(done =>
                {
                    OutputSucceeded = done.Status == TaskStatus.RanToCompletion && done.Result == WsabiWmiProtectionCleanupStatus.Complete;
                    _ = done.Exception; OutputFinished.TrySetResult(true);
                }, CancellationToken.None, TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
                return task;
            }
            catch { OutputFinished.TrySetResult(true); throw; }
        }
        private Task<WsabiWmiProtectionCleanupStatus> CloseInput()
        {
            try
            {
                Interlocked.Increment(ref inputs); CleanupOrder.Add("input");
                Check(OutputCalls == 1, "input cleanup preceded output cleanup");
                var task = Input();
                if (task == null) { InputFinished.TrySetResult(true); return null; }
                _ = task.ContinueWith(done => { _ = done.Exception; InputFinished.TrySetResult(true); },
                    CancellationToken.None, TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
                return task;
            }
            catch { InputFinished.TrySetResult(true); throw; }
        }
        internal void SupplyFinal()
        {
            var observer = Observer;
            if (observer == null || Request == null) return;
            var frame = Request.Request.Frame;
            var raw = new byte[21]; raw[4] = 0xaa;
            raw[7] = (byte)(index == 0 ? 1 : 0);
            raw[8] = frame[8]; Array.Copy(frame, 9, raw, 9, 8); ChangeReply?.Invoke(raw);
            observer.ReportTerminal(0); observer.SettleCapture(raw);
        }
    }
    private static WsabiWmiProtectionDisableAttempt DisableOwnerAttemptCreate(object identity)
    {
        WsabiWmiProtectionDisableAttempt attempt; WsabiWmiProtectionDisableAttemptIssue issue;
        Check(WsabiWmiProtectionDisableAttempt.TryCreateWithRandom(SingleReadTarget(identity), BinderCompleteMetadata(1), bytes =>
        { for (int index = 0; index < bytes.Length; index++) bytes[index] = (byte)(index + 1); }, out attempt, out issue),
            "fixed disable attempt fixture creation failed");
        Equal(WsabiWmiProtectionDisableAttemptIssue.None, issue); return attempt;
    }
    private sealed class DisableSessionReportException : Exception { }
}
