using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    // Internal role/int-only coordinator, fake gates and explicit fake end
    // evidence. No SDK, frame, address, nonce, file or Global object is used.
    private static void RegisterWsabiWmiSevenStageCoordinatorTests()
    {
        Add("seven stage coordinator validates fixed distinct operations and lifetimes before starting work", () =>
        {
            var nodes = SevenStageNodes(); var operations = nodes.Select(node => node.Operation).ToArray();
            var gate = new CooperativeTestGate();
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiSevenStageCoordinator(null, operations, TimeSpan.FromMilliseconds(100), TimeSpan.FromSeconds(3)));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiSevenStageCoordinator(gate, null, TimeSpan.FromMilliseconds(100), TimeSpan.FromSeconds(3)));
            BatteryThrows<ArgumentException>(() => new WsabiWmiSevenStageCoordinator(gate, new WsabiWmiSevenStageOperation[6], TimeSpan.FromMilliseconds(100), TimeSpan.FromSeconds(3)));
            BatteryThrows<ArgumentException>(() => new WsabiWmiSevenStageCoordinator(gate, new WsabiWmiSevenStageOperation[7], TimeSpan.FromMilliseconds(100), TimeSpan.FromSeconds(3)));
            var wrongOrder = (WsabiWmiSevenStageOperation[])operations.Clone();
            wrongOrder[0] = operations[1]; wrongOrder[1] = operations[0];
            BatteryThrows<ArgumentException>(() => new WsabiWmiSevenStageCoordinator(gate, wrongOrder, TimeSpan.FromMilliseconds(100), TimeSpan.FromSeconds(3)));
            var alias = (WsabiWmiSevenStageOperation[])operations.Clone();
            alias[1] = new WsabiWmiSevenStageOperation(WsabiWmiProtectionTransitionStage.PreUpper,
                stop => Task.FromResult(SevenStageObservation(WsabiWmiProtectionTransitionStage.PreUpper)), nodes[0].Lifetime);
            BatteryThrows<ArgumentException>(() => new WsabiWmiSevenStageCoordinator(gate, alias, TimeSpan.FromMilliseconds(100), TimeSpan.FromSeconds(3)));
            BatteryThrows<ArgumentOutOfRangeException>(() => new WsabiWmiSevenStageCoordinator(gate, operations, TimeSpan.Zero, TimeSpan.FromSeconds(3)));
            BatteryThrows<ArgumentOutOfRangeException>(() => new WsabiWmiSevenStageCoordinator(gate, operations, TimeSpan.FromMilliseconds(100), TimeSpan.Zero));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiSevenStageOperation(WsabiWmiProtectionTransitionStage.PreMode, null, new WsabiWmiSevenStageLifetime()));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiSevenStageOperation(WsabiWmiProtectionTransitionStage.PreMode, stop => null, null));
            Equal(0, gate.Calls); Check(nodes.All(node => node.Calls == 0), "constructor validation entered a stage");
            Check(!typeof(WsabiWmiSevenStageCoordinator).IsPublic && !typeof(WsabiWmiSevenStageOperation).IsPublic &&
                !typeof(WsabiWmiSevenStageLifetime).IsPublic, "mechanical coordinator became a public execution path");
            Check(!typeof(IDisposable).IsAssignableFrom(typeof(WsabiWmiSevenStageStopView)) &&
                !typeof(WsabiWmiSevenStageStopView).GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly)
                    .Any(method => method.Name == "Request" || method.Name == "Dispose") &&
                typeof(WsabiWmiSevenStageStopView).GetProperty("WaitHandle", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic) == null,
                "stage delegates received a mutable stop source");
        });

        AddAsync("seven stage coordinator runs one fixed role sequence under one same-thread owner", async () =>
        {
            var fixture = new SevenStageFixture();
            fixture.Operations[0] = null; // The constructor must own its array snapshot.
            var run = fixture.Coordinator.RunAsync();
            try
            {
                var outcome = await SevenStageOutcome(run);
                SevenStageAssertStatus(outcome, WsabiWmiSevenStageStatus.StoredReadbackMatchedCandidate, 7);
                Check(outcome.SetterRoleStarted && outcome.Snapshot.SetterAcknowledged, "semantic role acknowledgement was lost");
                Equal<int?>(0, outcome.Snapshot.ObservedPreModeByte);
                Equal<int?>(44, outcome.Snapshot.ObservedPreUpperByte); Equal<int?>(33, outcome.Snapshot.ObservedPreLowerByte);
                Equal<int?>(1, outcome.Snapshot.ObservedPostModeByte);
                Equal<int?>(80, outcome.Snapshot.ObservedPostUpperByte); Equal<int?>(75, outcome.Snapshot.ObservedPostLowerByte);
                Check(fixture.Order.SequenceEqual(WsabiWmiProtectionTransitionReview.StageOrder), "role order changed");
                await SevenStageAssertClosed(fixture);
                Equal(1, fixture.Gate.Calls); Check(fixture.Nodes.All(node => node.Calls == 1), "a role was retried or skipped");
                Check(fixture.Nodes.All(node => node.CallThread == fixture.Gate.AcquireThread), "a stage escaped the whole owner thread");
                var retry = await fixture.Coordinator.RunAsync();
                Equal(WsabiWmiSevenStageStatus.AlreadyUsed, retry.Status);
                Equal(1, fixture.Gate.Calls); Check(fixture.Nodes.All(node => node.Calls == 1), "a completed coordinator was rearmed");
            }
            finally { await SevenStageFinish(fixture); }
        });

        AddAsync("seven stage observation rejection at every role prevents every subsequent role", async () =>
        {
            for (int index = 0; index < 7; index++)
            {
                var fixture = new SevenStageFixture(index);
                var failed = fixture.Nodes[index];
                failed.Handler = stop => SevenStageClosedResult(failed,
                    new WsabiWmiProtectionTransitionObservation(failed.Role, WsabiWmiProtectionTransitionEvidence.Rejected));
                try
                {
                    var outcome = await SevenStageOutcome(fixture.Coordinator.RunAsync());
                    SevenStageAssertStatus(outcome, WsabiWmiSevenStageStatus.StageRejected, index + 1);
                    Equal(WsabiWmiProtectionTransitionDecisionStatus.ObservationRejected, outcome.LastDecision.Status);
                    SevenStageAssertPrefix(fixture, index + 1); Equal(index >= 3, outcome.SetterRoleStarted);
                    await SevenStageAssertClosed(fixture);
                }
                finally { await SevenStageFinish(fixture); }
            }
            foreach (int mode in new[] { 1, 255 })
            {
                var fixture = new SevenStageFixture(0);
                fixture.Nodes[0].Handler = stop => SevenStageClosedResult(fixture.Nodes[0], ProtectionReviewRead(WsabiWmiProtectionTransitionStage.PreMode, mode));
                try
                {
                    var outcome = await SevenStageOutcome(fixture.Coordinator.RunAsync());
                    SevenStageAssertStatus(outcome, WsabiWmiSevenStageStatus.StageRejected, 1);
                    Equal(WsabiWmiProtectionTransitionDecisionStatus.PreModeNotZero, outcome.LastDecision.Status);
                    Check(!outcome.SetterRoleStarted, "nonzero pre mode entered the semantic role"); SevenStageAssertPrefix(fixture, 1);
                }
                finally { await SevenStageFinish(fixture); }
            }
            for (int index = 4; index < 7; index++)
            {
                var fixture = new SevenStageFixture(index); var node = fixture.Nodes[index];
                node.Handler = stop => SevenStageClosedResult(node, ProtectionReviewRead(node.Role, index == 4 ? 0 : index == 5 ? 79 : 74));
                try
                {
                    var outcome = await SevenStageOutcome(fixture.Coordinator.RunAsync());
                    SevenStageAssertStatus(outcome, WsabiWmiSevenStageStatus.StageRejected, index + 1);
                    Check(outcome.SetterRoleStarted && !outcome.IsStoredReadbackMatchedCandidate,
                        "a setter acknowledgement substituted for mismatching post reads"); SevenStageAssertPrefix(fixture, index + 1);
                }
                finally { await SevenStageFinish(fixture); }
            }
        });

        AddAsync("seven stage known task fault cancellation and missing observation stop the sequence after actual close", async () =>
        {
            for (int index = 0; index < 7; index++)
            for (int variant = 0; variant < 3; variant++)
            {
                var fixture = new SevenStageFixture(index); var node = fixture.Nodes[index];
                int kind = variant;
                node.Handler = stop =>
                {
                    Task<WsabiWmiProtectionTransitionObservation> result = kind == 0
                        ? Task.FromException<WsabiWmiProtectionTransitionObservation>(new InvalidOperationException("Unreported fake stage detail."))
                        : kind == 1 ? Task.FromCanceled<WsabiWmiProtectionTransitionObservation>(new CancellationToken(true))
                        : Task.FromResult<WsabiWmiProtectionTransitionObservation>(null);
                    node.Lifetime.ConfirmActualClose(); return result;
                };
                try
                {
                    var outcome = await SevenStageOutcome(fixture.Coordinator.RunAsync());
                    SevenStageAssertStatus(outcome, kind == 2 ? WsabiWmiSevenStageStatus.StageRejected : WsabiWmiSevenStageStatus.StageFailed, index + 1);
                    SevenStageAssertPrefix(fixture, index + 1); await SevenStageAssertClosed(fixture);
                }
                finally { await SevenStageFinish(fixture); }
            }
        });

        AddAsync("seven stage start throw or null result task preserves unknown ownership until independent actual-close evidence", async () =>
        {
            foreach (int index in new[] { 0, 3, 6 })
            foreach (bool throws in new[] { false, true })
            {
                var fixture = new SevenStageFixture(index); var node = fixture.Nodes[index];
                node.Handler = stop => { if (throws) throw new InvalidOperationException("Unreported fake start detail."); return null; };
                try
                {
                    var outcome = await SevenStageOutcome(fixture.Coordinator.RunAsync());
                    SevenStageAssertStatus(outcome, WsabiWmiSevenStageStatus.CompletionUnknown, index + 1);
                    Check(fixture.Coordinator.IsCompletionUnknown && !fixture.Coordinator.ActualCompletion.IsCompleted && fixture.Gate.LastLease.IsHeld,
                        "failed start fabricated actual closure"); SevenStageAssertPrefix(fixture, index + 1);
                    node.Complete(); await SevenStageAssertClosed(fixture);
                    SevenStageAssertPrefix(fixture, index + 1);
                    Check(fixture.Coordinator.IsCompletionUnknown, "late cleanup silently removed quarantine");
                }
                finally { await SevenStageFinish(fixture); }
            }
        });

        AddAsync("seven stage uncertain-close diagnostics stop later roles but cannot release the owner before genuine fake closure", async () =>
        {
            foreach (int index in new[] { 0, 3, 6 })
            {
                var fixture = new SevenStageFixture(index); var node = fixture.Nodes[index];
                var run = fixture.Coordinator.RunAsync();
                try
                {
                    await CooperativeAwait(node.Entered.Task); node.Lifetime.ReportUncertainClose();
                    var outcome = await SevenStageOutcome(run);
                    SevenStageAssertStatus(outcome, WsabiWmiSevenStageStatus.CompletionUnknown, index + 1);
                    Check(!node.Lifetime.ActualClose.IsCompleted && !fixture.Coordinator.ActualCompletion.IsCompleted && fixture.Gate.LastLease.IsHeld,
                        "uncertain-close diagnostic was treated as resource termination");
                    node.SupplyResult(); Check(!fixture.Coordinator.ActualCompletion.IsCompleted, "late data replaced actual-close evidence");
                    node.Lifetime.ConfirmActualClose(); await SevenStageAssertClosed(fixture); SevenStageAssertPrefix(fixture, index + 1);
                }
                finally { await SevenStageFinish(fixture); }
            }
        });

        AddAsync("seven stage early successful result cannot advance or release before actual close and a display deadline stays terminal", async () =>
        {
            for (int index = 0; index < 7; index++)
            {
                var fixture = new SevenStageFixture(index, TimeSpan.FromMilliseconds(500)); var node = fixture.Nodes[index];
                var run = fixture.Coordinator.RunAsync();
                try
                {
                    await CooperativeAwait(node.Entered.Task); node.SupplyResult();
                    var outcome = await SevenStageOutcome(run);
                    SevenStageAssertStatus(outcome, WsabiWmiSevenStageStatus.TimedOut, index + 1);
                    Check(node.Stop.IsRequested && fixture.Gate.LastLease.IsHeld && !fixture.Coordinator.ActualCompletion.IsCompleted,
                        "early detached data or display timeout released the whole owner"); SevenStageAssertPrefix(fixture, index + 1);
                    node.Lifetime.ConfirmActualClose(); await SevenStageAssertClosed(fixture);
                    SevenStageAssertPrefix(fixture, index + 1); Equal(WsabiWmiSevenStageStatus.TimedOut, (await run).Status);
                }
                finally { await SevenStageFinish(fixture); }
            }
        });

        AddAsync("seven stage caller stop at every role prevents later roles while late result and cleanup are joined", async () =>
        {
            for (int index = 0; index < 7; index++)
            using (var caller = new CancellationTokenSource())
            {
                var fixture = new SevenStageFixture(index); var node = fixture.Nodes[index];
                var run = fixture.Coordinator.RunAsync(caller.Token);
                try
                {
                    await CooperativeAwait(node.Entered.Task); caller.Cancel();
                    var outcome = await SevenStageOutcome(run);
                    SevenStageAssertStatus(outcome, WsabiWmiSevenStageStatus.Cancelled, index + 1);
                    caller.Cancel(); caller.Cancel();
                    Check(node.Stop.IsRequested && !fixture.Coordinator.RequestCloseAsync().IsCompleted && fixture.Gate.LastLease.IsHeld,
                        "repeated stop bypassed actual closure");
                    node.SupplyResult(); Check(!fixture.Coordinator.ActualCompletion.IsCompleted, "late success completed ownership before actual close");
                    node.Lifetime.ConfirmActualClose(); await SevenStageAssertClosed(fixture);
                    SevenStageAssertPrefix(fixture, index + 1); Equal(WsabiWmiSevenStageStatus.Cancelled, (await run).Status);
                }
                finally { await SevenStageFinish(fixture); }
            }
        });

        AddAsync("seven stage actual close with lost result lets stop or deadline finish without a permanent result wait", async () =>
        {
            foreach (int index in new[] { 0, 3, 6 })
            foreach (bool callerStops in new[] { false, true })
            using (var caller = new CancellationTokenSource())
            {
                var fixture = new SevenStageFixture(index, callerStops ? TimeSpan.FromSeconds(3) : TimeSpan.FromMilliseconds(500));
                var node = fixture.Nodes[index]; var run = fixture.Coordinator.RunAsync(caller.Token);
                try
                {
                    await CooperativeAwait(node.Entered.Task); node.Lifetime.ConfirmActualClose();
                    if (callerStops) caller.Cancel();
                    var outcome = await SevenStageOutcome(run);
                    SevenStageAssertStatus(outcome, callerStops ? WsabiWmiSevenStageStatus.Cancelled : WsabiWmiSevenStageStatus.TimedOut, index + 1);
                    await SevenStageAssertClosed(fixture);
                    Check(!node.Result.Task.IsCompleted, "test did not preserve its lost-result counterexample");
                    SevenStageAssertPrefix(fixture, index + 1);
                    node.SupplyResult(); // Detached fake-only teardown after proven closure.
                }
                finally { await SevenStageFinish(fixture); }
            }
        });

        AddAsync("seven stage concurrent losers cannot stop or close the sole admitted sequence", async () =>
        {
            var fixture = new SevenStageFixture(0); var run = fixture.Coordinator.RunAsync();
            try
            {
                await CooperativeAwait(fixture.Nodes[0].Entered.Task);
                var losers = Enumerable.Range(0, 8).Select(index => Task.Run(() => fixture.Coordinator.RunAsync(new CancellationToken(true)))).ToArray();
                var all = Task.WhenAll(losers); await CooperativeAwait(all);
                Check((await all).All(result => result.Status == WsabiWmiSevenStageStatus.AlreadyUsed), "a concurrent Run bypassed single-use admission");
                int loserReports = 0;
                var losingHost = fixture.Coordinator.RunAndCloseAsync(outcome => loserReports++);
                Equal(WsabiWmiSevenStageStatus.AlreadyUsed, (await SevenStageOutcome(losingHost)).Status);
                Equal(1, loserReports);
                var loserFailure = new SevenStageReportException();
                var losingReporter = fixture.Coordinator.RunAndCloseAsync(outcome => { throw loserFailure; });
                await SevenStageExpectReportFailure(losingReporter, loserFailure);
                Check(!fixture.Nodes[0].Stop.IsRequested && !run.IsCompleted && fixture.Gate.LastLease.IsHeld,
                    "a losing Run cancelled the winner's work or ownership");
                fixture.Nodes[0].Complete();
                SevenStageAssertStatus(await SevenStageOutcome(run), WsabiWmiSevenStageStatus.StoredReadbackMatchedCandidate, 7);
                await SevenStageAssertClosed(fixture); Equal(1, fixture.Gate.Calls);
                Check(fixture.Nodes.All(node => node.Calls == 1), "concurrent Run repeated a role");
            }
            finally { await SevenStageFinish(fixture); }
        });

        AddAsync("seven stage whole-owner fake gate excludes a peer sequence until release on the acquiring thread", async () =>
        {
            using (var available = new SemaphoreSlim(1, 1))
            {
                var gate = new CooperativeTestGate { Handler = (timeout, cancellation) =>
                {
                    int signalled = WaitHandle.WaitAny(new[] { cancellation, available.AvailableWaitHandle }, timeout);
                    if (signalled == 0) return new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Cancelled);
                    if (signalled == WaitHandle.WaitTimeout || !available.Wait(0))
                        return new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.TimedOut);
                    return new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired,
                        new CooperativeTestLease { OnDispose = () => available.Release() });
                }};
                var first = new SevenStageFixture(2, gate: gate); var peer = new SevenStageFixture(gate: gate, acquireTimeout: TimeSpan.FromMilliseconds(30));
                var run = first.Coordinator.RunAsync();
                try
                {
                    await CooperativeAwait(first.Nodes[2].Entered.Task);
                    var lease = gate.LastLease; int ownerThread = gate.AcquireThread;
                    var rejected = await SevenStageOutcome(peer.Coordinator.RunAsync());
                    SevenStageAssertStatus(rejected, WsabiWmiSevenStageStatus.GateRejected, 0);
                    Equal<WsabiWmiExchangeGateStatus?>(WsabiWmiExchangeGateStatus.TimedOut, rejected.GateStatus);
                    Check(peer.Nodes.All(node => node.Calls == 0) && lease.IsHeld && !first.Nodes[2].Stop.IsRequested,
                        "a contending peer entered roles or disturbed the current owner");
                    await CooperativeAwait(peer.Coordinator.ActualCompletion);
                    first.Nodes[2].Complete();
                    SevenStageAssertStatus(await SevenStageOutcome(run), WsabiWmiSevenStageStatus.StoredReadbackMatchedCandidate, 7);
                    await CooperativeAwait(first.Coordinator.ActualCompletion);
                    Equal(1, lease.DisposeCalls); Equal(ownerThread, lease.DisposeThread);
                    Check(first.Nodes.All(node => node.CallThread == ownerThread), "whole sequence changed owner threads"); Equal(2, gate.Calls);
                }
                finally { await SevenStageFinish(first); await SevenStageFinish(peer); }
            }
        });

        AddAsync("seven stage explicit nonowned gate rejection starts no role and completes without fabricating a lease", async () =>
        {
            foreach (var status in new[] { WsabiWmiExchangeGateStatus.TimedOut, WsabiWmiExchangeGateStatus.Cancelled,
                WsabiWmiExchangeGateStatus.AccessDenied, WsabiWmiExchangeGateStatus.Unavailable, WsabiWmiExchangeGateStatus.UnsupportedPlatform })
            {
                var gate = new CooperativeTestGate { Handler = (timeout, signal) => new WsabiWmiExchangeGateAttempt(status) };
                var fixture = new SevenStageFixture(gate: gate);
                try
                {
                    var outcome = await SevenStageOutcome(fixture.Coordinator.RunAsync());
                    SevenStageAssertStatus(outcome, status == WsabiWmiExchangeGateStatus.Cancelled
                        ? WsabiWmiSevenStageStatus.Cancelled : WsabiWmiSevenStageStatus.GateRejected, 0);
                    Equal<WsabiWmiExchangeGateStatus?>(status, outcome.GateStatus);
                    await CooperativeAwait(fixture.Coordinator.ActualCompletion);
                    Check(gate.LastLease == null && fixture.Nodes.All(node => node.Calls == 0), "nonowned gate response entered a role or fabricated ownership");
                }
                finally { await SevenStageFinish(fixture); }
            }
            var abandonedGate = new CooperativeTestGate { Handler = (timeout, signal) =>
                new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Abandoned, new CooperativeTestLease()) };
            var abandoned = new SevenStageFixture(gate: abandonedGate);
            try
            {
                var outcome = await SevenStageOutcome(abandoned.Coordinator.RunAsync());
                SevenStageAssertStatus(outcome, WsabiWmiSevenStageStatus.GateRejected, 0);
                Equal<WsabiWmiExchangeGateStatus?>(WsabiWmiExchangeGateStatus.Abandoned, outcome.GateStatus);
                Check(abandoned.Coordinator.IsCompletionUnknown && abandoned.Nodes.All(node => node.Calls == 0),
                    "abandoned ownership entered a role or lost its quarantine");
                await SevenStageAssertClosed(abandoned);
            }
            finally { await SevenStageFinish(abandoned); }
        });

        AddAsync("seven stage deadline during final lease release cannot promote a matching numeric snapshot into a successful outcome", async () =>
        {
            using (var releaseLease = new ManualResetEventSlim())
            {
                var releaseEntered = CooperativeCompletion();
                var lease = new CooperativeTestLease { OnDispose = () =>
                {
                    releaseEntered.TrySetResult(true); releaseLease.Wait();
                }};
                var gate = new CooperativeTestGate { Handler = (timeout, signal) =>
                    new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired, lease) };
                var fixture = new SevenStageFixture(displayTimeout: TimeSpan.FromMilliseconds(500), gate: gate);
                var run = fixture.Coordinator.RunAsync();
                try
                {
                    await CooperativeAwait(releaseEntered.Task);
                    var outcome = await SevenStageOutcome(run);
                    SevenStageAssertStatus(outcome, WsabiWmiSevenStageStatus.TimedOut, 7);
                    Check(outcome.Snapshot.IsStoredReadbackMatchedCandidate && !outcome.IsStoredReadbackMatchedCandidate,
                        "numeric completion overrode the whole-procedure timeout");
                    Check(lease.IsHeld && !fixture.Coordinator.ActualCompletion.IsCompleted,
                        "display completion fabricated final lease release");
                    releaseLease.Set(); await SevenStageAssertClosed(fixture);
                    Equal(WsabiWmiSevenStageStatus.TimedOut, (await run).Status);
                    Check(fixture.Nodes.All(node => node.Calls == 1), "late cleanup restarted a role");
                }
                finally { releaseLease.Set(); await SevenStageFinish(fixture); }
            }
        });

        AddAsync("seven stage reporting failure cannot bypass actual-close join or start later roles", async () =>
        {
            var fixture = new SevenStageFixture(3, TimeSpan.FromMilliseconds(500));
            var published = CooperativeCompletion(); var failure = new SevenStageReportException();
            WsabiWmiSevenStageOutcome reported = null;
            var run = fixture.Coordinator.RunAndCloseAsync(outcome =>
            {
                reported = outcome; published.TrySetResult(true); throw failure;
            });
            try
            {
                await CooperativeAwait(fixture.Nodes[3].Entered.Task); await CooperativeAwait(published.Task);
                SevenStageAssertStatus(reported, WsabiWmiSevenStageStatus.TimedOut, 4);
                Check(!run.IsCompleted && !fixture.Coordinator.ActualCompletion.IsCompleted && fixture.Gate.LastLease.IsHeld,
                    "reporting failure escaped before actual cleanup");
                fixture.Nodes[3].Complete(); await SevenStageExpectReportFailure(run, failure);
                await SevenStageAssertClosed(fixture); SevenStageAssertPrefix(fixture, 4);
            }
            finally { await SevenStageFinish(fixture); await SevenStageExpectReportFailure(run, failure); }
        });

        AddAsync("seven stage pre cancellation unused close and shared lifetime reuse never start another sequence", async () =>
        {
            var cancelled = new SevenStageFixture();
            SevenStageAssertStatus(await SevenStageOutcome(cancelled.Coordinator.RunAsync(new CancellationToken(true))), WsabiWmiSevenStageStatus.Cancelled, 0);
            await CooperativeAwait(cancelled.Coordinator.ActualCompletion); Equal(0, cancelled.Gate.Calls);
            var unused = new SevenStageFixture();
            await CooperativeAwait(unused.Coordinator.RequestCloseAsync());
            Equal(WsabiWmiSevenStageStatus.AlreadyUsed, (await unused.Coordinator.RunAsync()).Status);
            Equal(0, unused.Gate.Calls); Check(unused.Nodes.All(node => node.Calls == 0), "unused close started work");

            var first = new SevenStageFixture();
            try
            {
                await SevenStageOutcome(first.Coordinator.RunAsync()); await SevenStageAssertClosed(first);
                int wrapperCalls = 0;
                var wrappers = first.Nodes.Select(node => new WsabiWmiSevenStageOperation(node.Role,
                    stop => { Interlocked.Increment(ref wrapperCalls); return Task.FromResult(SevenStageObservation(node.Role)); }, node.Lifetime)).ToArray();
                var gate = new CooperativeTestGate();
                var reused = new WsabiWmiSevenStageCoordinator(gate, wrappers, TimeSpan.FromMilliseconds(100), TimeSpan.FromSeconds(3));
                SevenStageAssertStatus(await SevenStageOutcome(reused.RunAsync()), WsabiWmiSevenStageStatus.AlreadyUsed, 0);
                await CooperativeAwait(reused.ActualCompletion); Equal(0, wrapperCalls); Equal(0, gate.Calls);
            }
            finally { await SevenStageFinish(first); }
        });

        AddAsync("seven stage preclosed or preuncertain lifetime never starts its role and uncertainty retains ownership", async () =>
        {
            foreach (bool uncertain in new[] { false, true })
            {
                var fixture = new SevenStageFixture(0);
                if (uncertain) fixture.Nodes[0].Lifetime.ReportUncertainClose(); else fixture.Nodes[0].Lifetime.ConfirmActualClose();
                try
                {
                    var outcome = await SevenStageOutcome(fixture.Coordinator.RunAsync());
                    SevenStageAssertStatus(outcome, uncertain ? WsabiWmiSevenStageStatus.CompletionUnknown : WsabiWmiSevenStageStatus.StageFailed, 0);
                    Check(fixture.Nodes.All(node => node.Calls == 0), "invalid lifetime was replayed as a new role");
                    if (uncertain)
                        Check(fixture.Gate.LastLease.IsHeld && !fixture.Coordinator.ActualCompletion.IsCompleted,
                            "preuncertain lifetime was treated as safely closed");
                    fixture.Nodes[0].Lifetime.ConfirmActualClose(); await SevenStageAssertClosed(fixture);
                }
                finally { await SevenStageFinish(fixture); }
            }
        });

        AddAsync("seven stage stop or deadline displays while synchronous Start is blocked and still waits for stack and actual close", async () =>
        {
            foreach (bool deadline in new[] { false, true })
            using (var returnFromStart = new ManualResetEventSlim())
            using (var caller = new CancellationTokenSource())
            {
                var fixture = new SevenStageFixture(0, deadline ? TimeSpan.FromMilliseconds(500) : TimeSpan.FromSeconds(3));
                var node = fixture.Nodes[0];
                node.Handler = stop =>
                {
                    if (!returnFromStart.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("Synthetic Start was not released.");
                    return node.Result.Task;
                };
                var run = fixture.Coordinator.RunAsync(caller.Token);
                try
                {
                    await CooperativeAwait(node.Entered.Task); if (!deadline) caller.Cancel();
                    var outcome = await SevenStageOutcome(run);
                    SevenStageAssertStatus(outcome, deadline ? WsabiWmiSevenStageStatus.TimedOut : WsabiWmiSevenStageStatus.Cancelled, 1);
                    Check(fixture.Gate.LastLease.IsHeld && !fixture.Coordinator.ActualCompletion.IsCompleted,
                        "synchronous Start blocked the display deadline or released before its real end");
                    returnFromStart.Set(); node.Complete(); await SevenStageAssertClosed(fixture); SevenStageAssertPrefix(fixture, 1);
                }
                finally { returnFromStart.Set(); await SevenStageFinish(fixture); }
            }
        });
    }

    private static SevenStageNode[] SevenStageNodes(int pendingIndex = -1, List<WsabiWmiProtectionTransitionStage> order = null)
        => WsabiWmiProtectionTransitionReview.StageOrder.Select((role, index) => new SevenStageNode(role, index != pendingIndex, order)).ToArray();

    private static WsabiWmiProtectionTransitionObservation SevenStageObservation(WsabiWmiProtectionTransitionStage role)
    {
        if (role == WsabiWmiProtectionTransitionStage.SemanticSet1)
            return new WsabiWmiProtectionTransitionObservation(role, WsabiWmiProtectionTransitionEvidence.SetterAcknowledged);
        int value = role == WsabiWmiProtectionTransitionStage.PreMode ? 0 : role == WsabiWmiProtectionTransitionStage.PreUpper ? 44
            : role == WsabiWmiProtectionTransitionStage.PreLower ? 33 : role == WsabiWmiProtectionTransitionStage.PostMode ? 1
            : role == WsabiWmiProtectionTransitionStage.PostUpper ? 80 : 75;
        return ProtectionReviewRead(role, value);
    }

    private static Task<WsabiWmiProtectionTransitionObservation> SevenStageClosedResult(SevenStageNode node,
        WsabiWmiProtectionTransitionObservation observation)
    {
        var result = Task.FromResult(observation); node.Lifetime.ConfirmActualClose(); return result;
    }

    private static async Task<WsabiWmiSevenStageOutcome> SevenStageOutcome(Task<WsabiWmiSevenStageOutcome> run)
    { await CooperativeAwait(run); return await run; }

    private static void SevenStageAssertStatus(WsabiWmiSevenStageOutcome outcome, WsabiWmiSevenStageStatus status, int started)
    {
        Equal(status, outcome.Status); Equal(started, outcome.StartedStages);
        Check(!outcome.IsExecutable && !outcome.CanInvokeMethods && !outcome.CanReadHardware && !outcome.CanWriteHardware &&
            !outcome.Snapshot.IsHardwareObservation && !outcome.Snapshot.IsChargeLimitConfirmed,
            "mechanical role evidence became hardware or charging authority");
    }

    private static void SevenStageAssertPrefix(SevenStageFixture fixture, int started)
    {
        for (int index = 0; index < fixture.Nodes.Length; index++) Equal(index < started ? 1 : 0, fixture.Nodes[index].Calls);
    }

    private static async Task SevenStageAssertClosed(SevenStageFixture fixture)
    {
        await CooperativeAwait(fixture.Coordinator.ActualCompletion);
        Equal(WsabiWmiSevenStageCleanupStatus.Complete, await fixture.Coordinator.ActualCompletion);
        var lease = fixture.Gate.LastLease;
        Check(lease != null && !lease.IsHeld, "actual completion preceded owner release");
        Equal(1, lease.DisposeCalls); Equal(fixture.Gate.AcquireThread, lease.DisposeThread);
    }

    private static async Task SevenStageFinish(SevenStageFixture fixture)
    {
        var close = fixture.Coordinator.RequestCloseAsync();
        // Explicit fake evidence only: every entered or unused fake object is
        // now detached and done. No real source has this test cleanup switch.
        foreach (var node in fixture.Nodes) node.Complete();
        await CooperativeAwait(close);
    }

    private static async Task SevenStageExpectReportFailure(Task task, SevenStageReportException expected)
    {
        try { await CooperativeAwait(task); }
        catch (SevenStageReportException error) { Check(ReferenceEquals(error, expected), "report exception changed during close join"); return; }
        throw new InvalidOperationException("Expected the fake reporter failure after actual close.");
    }

    private sealed class SevenStageFixture
    {
        internal readonly List<WsabiWmiProtectionTransitionStage> Order = new List<WsabiWmiProtectionTransitionStage>();
        internal readonly SevenStageNode[] Nodes;
        internal readonly WsabiWmiSevenStageOperation[] Operations;
        internal readonly CooperativeTestGate Gate;
        internal readonly WsabiWmiSevenStageCoordinator Coordinator;

        internal SevenStageFixture(int pendingIndex = -1, TimeSpan? displayTimeout = null,
            CooperativeTestGate gate = null, TimeSpan? acquireTimeout = null)
        {
            Gate = gate ?? new CooperativeTestGate(); Nodes = SevenStageNodes(pendingIndex, Order);
            Operations = Nodes.Select(node => node.Operation).ToArray();
            Coordinator = new WsabiWmiSevenStageCoordinator(Gate, Operations, acquireTimeout ?? TimeSpan.FromMilliseconds(200),
                displayTimeout ?? TimeSpan.FromSeconds(3));
        }
    }

    private sealed class SevenStageNode
    {
        internal readonly WsabiWmiProtectionTransitionStage Role;
        internal readonly WsabiWmiSevenStageLifetime Lifetime = new WsabiWmiSevenStageLifetime();
        internal readonly TaskCompletionSource<WsabiWmiProtectionTransitionObservation> Result =
            new TaskCompletionSource<WsabiWmiProtectionTransitionObservation>(TaskCreationOptions.RunContinuationsAsynchronously);
        internal readonly TaskCompletionSource<bool> Entered = CooperativeCompletion();
        internal readonly WsabiWmiSevenStageOperation Operation;
        internal readonly bool AutoComplete;
        private readonly List<WsabiWmiProtectionTransitionStage> order;
        private int calls;
        internal int Calls => Volatile.Read(ref calls);
        internal int CallThread;
        internal WsabiWmiSevenStageStopView Stop;
        internal Func<WsabiWmiSevenStageStopView, Task<WsabiWmiProtectionTransitionObservation>> Handler;

        internal SevenStageNode(WsabiWmiProtectionTransitionStage role, bool autoComplete,
            List<WsabiWmiProtectionTransitionStage> order)
        {
            Role = role; AutoComplete = autoComplete; this.order = order;
            Operation = new WsabiWmiSevenStageOperation(role, Start, Lifetime);
        }
        private Task<WsabiWmiProtectionTransitionObservation> Start(WsabiWmiSevenStageStopView stop)
        {
            Interlocked.Increment(ref calls); CallThread = Thread.CurrentThread.ManagedThreadId; Stop = stop;
            order?.Add(Role); Entered.TrySetResult(true);
            if (Handler != null) return Handler(stop);
            if (AutoComplete) Complete();
            return Result.Task;
        }
        internal void SupplyResult() => Result.TrySetResult(SevenStageObservation(Role));
        internal void Complete() { SupplyResult(); Lifetime.ConfirmActualClose(); }
    }

    private sealed class SevenStageReportException : Exception { }
}
