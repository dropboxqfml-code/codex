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
    private static void RegisterWsabiWmiProtectionTransitionSessionTests()
    {
        AddAsync("protection facade validates dependencies and target identity and unused close creates no leaf", async () =>
        {
            var fixture = new ProtectionSessionFixture();
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiProtectionTransitionSession(null, fixture.Factory, fixture.Gate));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiProtectionTransitionSession(fixture.Attempt, null, fixture.Gate));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiProtectionTransitionSession(fixture.Attempt, fixture.Factory, null));
            var wrong = new ProtectionSessionFactory(new SingleReadPoisonIdentity());
            BatteryThrows<ArgumentException>(() => new WsabiWmiProtectionTransitionSession(fixture.Attempt, wrong, fixture.Gate));
            Equal(0, wrong.Calls);
            Equal(WsabiWmiProtectionCleanupStatus.Complete, await fixture.Session.RequestCloseAsync());
            Equal(WsabiWmiProtectionTransitionStatus.AlreadyUsed, (await fixture.Session.RunAsync()).Status);
            Equal(0, fixture.Factory.Calls); Equal(0, fixture.Gate.Calls);
            Check(!fixture.Session.CanWriteHardware && !fixture.Session.IsChargeLimitConfirmed,
                "construction or unused close granted charge authority");
        });

        AddAsync("protection facade lazily prepares the seven exact requests under one owner and preserves receipt semantics", async () =>
        {
            var fixture = new ProtectionSessionFixture();
            Equal(0, fixture.Factory.Calls); Check(fixture.Factory.Nodes.All(node => node.Invocations == 0), "leaf work existed before Run");
            try
            {
                var outcome = await ProtectionSessionOutcome(fixture.Session.RunAsync());
                ProtectionSessionAssert(outcome, WsabiWmiProtectionTransitionStatus.StoredReadbackMatchedCandidate, 7);
                Equal(6, outcome.Snapshot.BoundReadCandidateCount);
                Check(outcome.Snapshot.SetterReceiptAccepted && !outcome.Snapshot.SetterAcknowledged,
                    "receipt was promoted to a semantic setter acknowledgement");
                Check(fixture.Factory.Order.SequenceEqual(WsabiWmiProtectionTransitionReview.StageOrder), "facade changed fixed stage order");
                Equal(7, fixture.Factory.Calls);
                Check(fixture.Factory.Nodes.All(node => node.Invocations == 1 && node.OutputCalls == 1 && node.InputCalls == 1),
                    "facade retried, skipped or leaked a normal leaf");
                Check(fixture.Factory.PrepareThreads.All(thread => thread == fixture.Gate.AcquireThread), "leaf admission left the owner thread");
                await ProtectionSessionClosed(fixture); Equal(1, fixture.Gate.Calls);
            }
            finally { await ProtectionSessionFinish(fixture); }
        });

        AddAsync("protection facade gate rejection and pre cancellation create no SDK leaf or invocation", async () =>
        {
            foreach (bool cancelled in new[] { false, true })
            {
                var gate = new CooperativeTestGate { Handler = (timeout, signal) =>
                    new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.AccessDenied) };
                var fixture = new ProtectionSessionFixture(gate: gate);
                try
                {
                    var outcome = await ProtectionSessionOutcome(fixture.Session.RunAsync(new CancellationToken(cancelled)));
                    ProtectionSessionAssert(outcome, cancelled ? WsabiWmiProtectionTransitionStatus.Cancelled : WsabiWmiProtectionTransitionStatus.GateRejected, 0);
                    await CooperativeAwait(fixture.Session.RequestCloseAsync());
                    Equal(0, fixture.Factory.Calls); Check(fixture.Factory.Nodes.All(node => node.Invocations == 0), "no-owner path entered a source");
                    Equal(cancelled ? 0 : 1, gate.Calls);
                }
                finally { await ProtectionSessionFinish(fixture); }
            }
        });

        AddAsync("protection facade pre mode rejection post mismatch and ambiguous thresholds stop at their fixed budgets", async () =>
        {
            foreach (bool failure in new[] { false, true })
            {
                var fixture = new ProtectionSessionFixture();
                fixture.Factory.Nodes[0].ChangeReply = bytes =>
                { if (failure) { Array.Clear(bytes, 5, 16); bytes[5] = 0xff; } else bytes[7] = 1; };
                try
                {
                    var outcome = await ProtectionSessionOutcome(fixture.Session.RunAsync());
                    ProtectionSessionAssert(outcome, WsabiWmiProtectionTransitionStatus.StageRejected, 1);
                    Check(!outcome.SetterRoleStarted && !outcome.Snapshot.SetterReceiptAccepted, "invalid pre mode entered setting stage");
                    Equal(1, fixture.Factory.Calls); ProtectionSessionPrefix(fixture, 1);
                    await ProtectionSessionClosed(fixture);
                }
                finally { await ProtectionSessionFinish(fixture); }
            }
            foreach (int index in new[] { 1, 4, 5, 6 })
            {
                var fixture = new ProtectionSessionFixture(); var node = fixture.Factory.Nodes[index];
                node.ChangeReply = bytes => bytes[7] = (byte)(index == 1 ? 0xf0 : index == 4 ? 0 : index == 5 ? 79 : 74);
                try
                {
                    var outcome = await ProtectionSessionOutcome(fixture.Session.RunAsync());
                    ProtectionSessionAssert(outcome, WsabiWmiProtectionTransitionStatus.StageRejected, index + 1);
                    Equal(index >= 4, outcome.Snapshot.SetterReceiptAccepted);
                    Check(!outcome.Snapshot.SetterAcknowledged, "post failure fabricated setter acknowledgement");
                    ProtectionSessionPrefix(fixture, index + 1); await ProtectionSessionClosed(fixture);
                }
                finally { await ProtectionSessionFinish(fixture); }
            }
        });

        AddAsync("protection facade cannot rewrap a consumed attempt into another factory and gate", async () =>
        {
            var fixture = new ProtectionSessionFixture();
            try
            {
                await ProtectionSessionOutcome(fixture.Session.RunAsync()); await ProtectionSessionClosed(fixture);
                var factory = new ProtectionSessionFactory(fixture.Factory.TargetIdentity); var gate = new CooperativeTestGate();
                var peer = new WsabiWmiProtectionTransitionSession(fixture.Attempt, factory, gate);
                Equal(WsabiWmiProtectionTransitionStatus.AlreadyUsed, (await peer.RunAsync()).Status);
                Equal(WsabiWmiProtectionCleanupStatus.Complete, await peer.RequestCloseAsync());
                Equal(0, factory.Calls); Equal(0, gate.Calls);
            }
            finally { await ProtectionSessionFinish(fixture); }
        });

        AddAsync("protection facade not ready partial preparation closes output then inputs without invoking the source", async () =>
        {
            var fixture = new ProtectionSessionFixture(); fixture.Factory.Nodes[0].Ready = false;
            try
            {
                var outcome = await ProtectionSessionOutcome(fixture.Session.RunAsync());
                ProtectionSessionAssert(outcome, WsabiWmiProtectionTransitionStatus.StageRejected, 1);
                var node = fixture.Factory.Nodes[0];
                Equal(0, node.Invocations); Equal(1, node.OutputCalls); Equal(1, node.InputCalls);
                Check(node.CleanupOrder.SequenceEqual(new[] { "output", "input" }), "partial preparation cleanup order changed");
                Equal(1, fixture.Factory.Calls); await ProtectionSessionClosed(fixture);
            }
            finally { await ProtectionSessionFinish(fixture); }
        });

        AddAsync("protection facade early terminal and capture cannot close outputs while Invoke still owns its stack", async () =>
        {
            using (var release = new ManualResetEventSlim())
            {
                var fixture = new ProtectionSessionFixture(); var node = fixture.Factory.Nodes[0];
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
                    Equal(WsabiWmiProtectionTransitionStatus.Cancelled, (await ProtectionSessionOutcome(run)).Status);
                    Check(!close.IsCompleted && fixture.Gate.LastLease.IsHeld, "stop released an active invocation stack");
                    release.Set(); await CooperativeAwait(close); ProtectionSessionPrefix(fixture, 1);
                    await ProtectionSessionClosed(fixture);
                }
                finally { release.Set(); await ProtectionSessionFinish(fixture); }
            }
        });

        AddAsync("protection facade serializes output and input close and neither pending cleanup permits the next role", async () =>
        {
            foreach (bool outputPending in new[] { false, true })
            {
                var fixture = new ProtectionSessionFixture(); var node = fixture.Factory.Nodes[0];
                var cleanup = new TaskCompletionSource<WsabiWmiProtectionCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
                if (outputPending) node.Output = () => cleanup.Task; else node.Input = () => cleanup.Task;
                var run = fixture.Session.RunAsync();
                try
                {
                    await InvocationEventually(() => outputPending ? node.OutputCalls == 1 : node.InputCalls == 1);
                    Check(!run.IsCompleted && fixture.Gate.LastLease.IsHeld, "pending close was erased before the next role");
                    Equal(outputPending ? 0 : 1, node.InputCalls); Equal(1, fixture.Factory.Calls);
                    var closing = fixture.Session.RequestCloseAsync();
                    ProtectionSessionAssert(await ProtectionSessionOutcome(run), WsabiWmiProtectionTransitionStatus.Cancelled, 1);
                    Check(!closing.IsCompleted, "caller close bypassed a pending cleanup");
                    cleanup.TrySetResult(WsabiWmiProtectionCleanupStatus.Complete);
                    await CooperativeAwait(closing); ProtectionSessionPrefix(fixture, 1);
                    await ProtectionSessionClosed(fixture);
                }
                finally { cleanup.TrySetResult(WsabiWmiProtectionCleanupStatus.Complete); await ProtectionSessionFinish(fixture); }
            }
        });

        AddAsync("protection facade failed unknown faulted cancelled or missing output cleanup never releases inputs", async () =>
        {
            for (int variant = 0; variant < 5; variant++)
            {
                var fixture = new ProtectionSessionFixture(); var node = fixture.Factory.Nodes[0]; int selected = variant;
                node.Output = () => selected == 0 ? Task.FromResult(WsabiWmiProtectionCleanupStatus.Failed)
                    : selected == 1 ? Task.FromResult(WsabiWmiProtectionCleanupStatus.Unknown)
                    : selected == 2 ? Task.FromException<WsabiWmiProtectionCleanupStatus>(new InvalidOperationException("Unreported fake close detail."))
                    : selected == 3 ? Task.FromCanceled<WsabiWmiProtectionCleanupStatus>(new CancellationToken(true)) : null;
                try
                {
                    ProtectionSessionAssert(await ProtectionSessionOutcome(fixture.Session.RunAsync()), WsabiWmiProtectionTransitionStatus.CompletionUnknown, 1);
                    Equal(1, node.OutputCalls); Equal(0, node.InputCalls); Equal(1, fixture.Factory.Calls);
                    Check(fixture.Gate.LastLease.IsHeld && !fixture.Session.RequestCloseAsync().IsCompleted,
                        "unproven output ownership released its inputs or lease");
                }
                finally { await ProtectionSessionFinish(fixture); }
            }
        });

        AddAsync("protection facade failed input close keeps the procedure unknown despite a complete output cleanup", async () =>
        {
            foreach (var status in new[] { WsabiWmiProtectionCleanupStatus.Failed, WsabiWmiProtectionCleanupStatus.Unknown })
            {
                var fixture = new ProtectionSessionFixture(); var node = fixture.Factory.Nodes[3];
                node.Input = () => Task.FromResult(status);
                try
                {
                    var outcome = await ProtectionSessionOutcome(fixture.Session.RunAsync());
                    ProtectionSessionAssert(outcome, WsabiWmiProtectionTransitionStatus.CompletionUnknown, 4);
                    Equal(1, node.OutputCalls); Equal(1, node.InputCalls);
                    Check(fixture.Gate.LastLease.IsHeld && !fixture.Session.RequestCloseAsync().IsCompleted,
                        "input disposal failure became a successful actual-close witness");
                    ProtectionSessionPrefix(fixture, 4);
                }
                finally { await ProtectionSessionFinish(fixture); }
            }
        });

        AddAsync("protection facade late prepared leaf is retired without invocation after stop or display timeout", async () =>
        {
            foreach (bool timeout in new[] { false, true })
            using (var stop = new CancellationTokenSource())
            {
                var fixture = new ProtectionSessionFixture(display: timeout ? TimeSpan.FromMilliseconds(500) : TimeSpan.FromSeconds(3));
                var node = fixture.Factory.Nodes[0]; node.Preparation = new TaskCompletionSource<WsabiWmiProtectionLeaf>(TaskCreationOptions.RunContinuationsAsynchronously);
                var run = fixture.Session.RunAsync(stop.Token);
                try
                {
                    await CooperativeAwait(node.Prepared.Task); if (!timeout) stop.Cancel();
                    ProtectionSessionAssert(await ProtectionSessionOutcome(run), timeout ? WsabiWmiProtectionTransitionStatus.TimedOut : WsabiWmiProtectionTransitionStatus.Cancelled, 1);
                    Equal(0, node.Invocations); Check(fixture.Gate.LastLease.IsHeld && !fixture.Session.RequestCloseAsync().IsCompleted,
                        "pending SDK preparation was abandoned at the display boundary");
                    node.Preparation.TrySetResult(node.MakeLeaf());
                    await ProtectionSessionClosed(fixture); Equal(0, node.Invocations);
                    Equal(1, node.OutputCalls); Equal(1, node.InputCalls); ProtectionSessionPrefix(fixture, 1, noInvocationAt: 0);
                }
                finally { await ProtectionSessionFinish(fixture); }
            }
        });

        AddAsync("protection facade source throw without a terminal remains pending until late applicable termination and capture", async () =>
        {
            var fixture = new ProtectionSessionFixture(display: TimeSpan.FromMilliseconds(500)); var node = fixture.Factory.Nodes[0];
            node.Invoke = (request, observer) => { throw new InvalidOperationException("Unreported fake invocation detail."); };
            var run = fixture.Session.RunAsync();
            try
            {
                await CooperativeAwait(node.Returned.Task);
                ProtectionSessionAssert(await ProtectionSessionOutcome(run), WsabiWmiProtectionTransitionStatus.TimedOut, 1);
                Equal(0, node.OutputCalls); Equal(0, node.InputCalls);
                Check(fixture.Gate.LastLease.IsHeld && !fixture.Session.RequestCloseAsync().IsCompleted, "throw manufactured provider termination");
                node.SupplyFinal(); await ProtectionSessionClosed(fixture);
                ProtectionSessionPrefix(fixture, 1); Equal(WsabiWmiProtectionTransitionStatus.TimedOut, (await run).Status);
            }
            finally { await ProtectionSessionFinish(fixture); }
        });

        AddAsync("protection facade reporting exception still joins pending input cleanup and cannot restart later roles", async () =>
        {
            var fixture = new ProtectionSessionFixture(display: TimeSpan.FromMilliseconds(500)); var node = fixture.Factory.Nodes[3];
            var input = new TaskCompletionSource<WsabiWmiProtectionCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
            node.Input = () => input.Task;
            var published = CooperativeCompletion(); var error = new ProtectionSessionReportException();
            var run = fixture.Session.RunAndCloseAsync(outcome => { published.TrySetResult(true); throw error; });
            try
            {
                await CooperativeAwait(published.Task);
                Check(!run.IsCompleted && fixture.Gate.LastLease.IsHeld && node.InputCalls == 1,
                    "reporter exception escaped the actual cleanup barrier");
                input.TrySetResult(WsabiWmiProtectionCleanupStatus.Complete);
                try { await CooperativeAwait(run); throw new InvalidOperationException("Expected fake reporting failure."); }
                catch (ProtectionSessionReportException observed) { Check(ReferenceEquals(error, observed), "reporting error changed during join"); }
                await ProtectionSessionClosed(fixture); ProtectionSessionPrefix(fixture, 4);
            }
            finally
            {
                input.TrySetResult(WsabiWmiProtectionCleanupStatus.Complete); await ProtectionSessionFinish(fixture);
                try { await CooperativeAwait(run); } catch (ProtectionSessionReportException) { }
            }
        });

    }

    private static async Task<WsabiWmiProtectionTransitionOutcome> ProtectionSessionOutcome(Task<WsabiWmiProtectionTransitionOutcome> run)
    { await CooperativeAwait(run); return await run; }
    private static void ProtectionSessionAssert(WsabiWmiProtectionTransitionOutcome result, WsabiWmiProtectionTransitionStatus status, int stages)
    {
        Equal(status, result.Status); Equal(stages, result.StartedStages);
        Check(!result.CanWriteHardware && !result.IsChargeLimitConfirmed && !result.Snapshot.IsHardwareObservation &&
            !result.Snapshot.IsChargeLimitConfirmed, "fake facade result became charge-control evidence");
    }
    private static void ProtectionSessionPrefix(ProtectionSessionFixture fixture, int count, int noInvocationAt = -1)
    {
        for (int i = 0; i < 7; i++) Equal(i < count && i != noInvocationAt ? 1 : 0, fixture.Factory.Nodes[i].Invocations);
        Equal(count, fixture.Factory.Calls);
    }
    private static async Task ProtectionSessionClosed(ProtectionSessionFixture fixture)
    {
        await CooperativeAwait(fixture.Session.RequestCloseAsync());
        Equal(WsabiWmiProtectionCleanupStatus.Complete, await fixture.Session.RequestCloseAsync());
        Check(fixture.Gate.LastLease != null && !fixture.Gate.LastLease.IsHeld, "facade close completed before its lease was released");
        Equal(1, fixture.Gate.LastLease.DisposeCalls); Equal(fixture.Gate.AcquireThread, fixture.Gate.LastLease.DisposeThread);
    }
    private static async Task ProtectionSessionFinish(ProtectionSessionFixture fixture)
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

    private sealed class ProtectionSessionFixture
    {
        internal readonly WsabiWmiProtectionTransitionAttempt Attempt;
        internal readonly ProtectionSessionFactory Factory;
        internal readonly CooperativeTestGate Gate;
        internal readonly WsabiWmiProtectionTransitionSession Session;
        internal ProtectionSessionFixture(CooperativeTestGate gate = null, TimeSpan? display = null)
        {
            var identity = new SingleReadPoisonIdentity(); Attempt = ProtectionAttemptCreate(identity);
            Factory = new ProtectionSessionFactory(identity); Gate = gate ?? new CooperativeTestGate();
            Session = new WsabiWmiProtectionTransitionSession(Attempt, Factory, Gate, TimeSpan.FromMilliseconds(200), display ?? TimeSpan.FromSeconds(3));
        }
    }
    private sealed class ProtectionSessionFactory : IWsabiWmiProtectionLeafFactory
    {
        public object TargetIdentity { get; }
        internal readonly ProtectionSessionNode[] Nodes = Enumerable.Range(0, 7).Select(index => new ProtectionSessionNode(index)).ToArray();
        internal readonly List<WsabiWmiProtectionTransitionStage> Order = new List<WsabiWmiProtectionTransitionStage>();
        internal readonly List<int> PrepareThreads = new List<int>();
        private int calls;
        internal int Calls => Volatile.Read(ref calls);
        internal ProtectionSessionFactory(object target) { TargetIdentity = target; }
        public Task<WsabiWmiProtectionLeaf> PrepareAsync(WsabiWmiProtectionLeafRequest request, WsabiWmiProtectionStop stop)
        {
            Interlocked.Increment(ref calls); Order.Add(request.Role); PrepareThreads.Add(Thread.CurrentThread.ManagedThreadId);
            var node = Nodes[(int)request.Role]; node.Request = request; node.Stop = stop; node.Prepared.TrySetResult(true);
            return node.Preparation == null ? Task.FromResult(node.MakeLeaf()) : node.Preparation.Task;
        }
    }
    private sealed class ProtectionSessionNode : IWsabiWmiInvocationSource
    {
        private readonly int index;
        private int invocations, outputs, inputs;
        internal int Invocations => Volatile.Read(ref invocations);
        internal int OutputCalls => Volatile.Read(ref outputs);
        internal int InputCalls => Volatile.Read(ref inputs);
        internal bool Ready = true;
        internal WsabiWmiProtectionLeafRequest Request;
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
        internal ProtectionSessionNode(int index) { this.index = index; }
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
            raw[7] = (byte)(index == 0 ? 0 : index == 1 ? 44 : index == 2 ? 33 : index == 5 ? 80 : index == 6 ? 75 : 1);
            raw[8] = frame[8]; Array.Copy(frame, 9, raw, 9, 8); ChangeReply?.Invoke(raw);
            observer.ReportTerminal(0); observer.SettleCapture(raw);
        }
    }
    private sealed class ProtectionSessionReportException : Exception { }
}
