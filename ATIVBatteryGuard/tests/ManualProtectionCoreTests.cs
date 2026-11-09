using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static readonly ManualProtectionOperation[] ManualCoreOperations = {
        ManualProtectionOperation.ReadState, ManualProtectionOperation.Enable80, ManualProtectionOperation.DisableProtection };

    private static void RegisterManualProtectionCoreTests()
    {
        Add("manual attempts freeze the three separately bounded literal operation schedules", () =>
        {
            foreach (var op in ManualCoreOperations)
            {
                var attempt = ManualCoreAttempt(op, new object());
                Equal("ManualProtection-v1", ManualProtectionAttempt.Purpose);
                Equal(0, ManualProtectionAttempt.DeclaredRetries);
                Equal(ManualProtectionLimits.MaximumSdkEntries(op), attempt.MaximumMethodEntries);
                Equal(ManualProtectionLimits.MaximumReadCandidates(op), attempt.MaximumReadCandidates);
                Equal(ManualProtectionLimits.MaximumSetterEntries(op), attempt.MaximumSettingEntries);
                var expected = op == ManualProtectionOperation.Enable80 ? new[] {0,1,2,3,4,5,6}
                    : op == ManualProtectionOperation.DisableProtection ? new[] {0,3,4} : new[] {0,1,2};
                Check(attempt.StageOrder.Select(role => (int)role).SequenceEqual(expected), "manual schedule changed");
                for (int slot = 0; slot < expected.Length; slot++)
                {
                    var role = attempt.GetRole(slot); bool setter = expected[slot] == 3;
                    byte[] literal = {0x43,0x58,0x7a,0,0,0x82,0x80,0xf0,0x4f,0,0,0,0,0,0,0,0,0,0,0,0};
                    if (setter) { literal[6] = 0xe3; literal[7] = (byte)(op == ManualProtectionOperation.Enable80 ? 1 : 0); literal[8] = 0; }
                    else if (expected[slot] == 1 || expected[slot] == 5) literal[8] = 0x50;
                    else if (expected[slot] == 2 || expected[slot] == 6) literal[8] = 0x51;
                    for (int cell = 0; cell < 8; cell++) literal[9+cell] = (byte)(slot*8+cell+1);
                    Check(attempt.GetRequest(role).Frame.SequenceEqual(literal), "request differed from literal saved correspondence");
                    Equal(slot, attempt.GetIndex(role)); Equal(setter, attempt.IsSettingRole(role));
                    Check(attempt.ValidateRoleRequest(role, attempt.GetRequest(role)), "own fixed request rejected");
                    var altered = (byte[])literal.Clone(); altered[8] ^= 1;
                    Check(!attempt.ValidateRoleRequest(role, new WsabiWmiMethodRequest(1, 0x7a, altered)), "alternate component admitted");
                }
                BatteryThrows<ArgumentOutOfRangeException>(() => attempt.GetRole(-1));
                BatteryThrows<ArgumentOutOfRangeException>(() => attempt.GetRole(expected.Length));
                foreach (ManualProtectionRole role in Enum.GetValues(typeof(ManualProtectionRole)))
                    if (!expected.Contains((int)role))
                    {
                        BatteryThrows<ArgumentOutOfRangeException>(() => attempt.GetRequest(role));
                        Check(!attempt.ValidateRoleRequest(role, attempt.GetRequest(ManualProtectionRole.PreMode)), "unused role became executable");
                    }
            }
        });
        Add("manual attempts use one operation-sized fill and retain no mutable caller aliases", () =>
        {
            foreach (var op in ManualCoreOperations)
            {
                int calls = 0; byte[] temporary = null; ManualProtectionAttempt attempt; ManualProtectionAttemptIssue issue;
                Check(ManualProtectionAttempt.TryCreateWithRandom(op, SingleReadTarget(new object()), BinderCompleteMetadata(1), bytes =>
                { calls++; temporary = bytes; Equal(op == ManualProtectionOperation.Enable80 ? 56 : 24, bytes.Length); ManualCoreFill(bytes); }, out attempt, out issue), "manual fill failed");
                Equal(1, calls); Equal(ManualProtectionAttemptIssue.None, issue);
                Check(temporary.All(cell => cell == 0), "entropy temporary was retained"); temporary[0] = 255;
                var frame = attempt.GetRequest(ManualProtectionRole.PreMode).Frame; frame[9] = 0;
                var comparison = attempt.GetComparison(ManualProtectionRole.PreMode); comparison[0] = 0;
                Equal((byte)1, attempt.GetRequest(ManualProtectionRole.PreMode).Frame[9]);
                Equal((byte)1, attempt.GetComparison(ManualProtectionRole.PreMode)[0]);
                var peer = ManualCoreAttempt(op, new object());
                var request = new ManualProtectionLeafRequest(attempt, ManualProtectionRole.PreMode);
                Check(request.BelongsTo(attempt) && !request.BelongsTo(peer), "attempt identity reduced to byte equality");
            }
        });
        Add("manual zero and duplicate comparison tuples abort each operation without resampling", () =>
        {
            foreach (var op in ManualCoreOperations)
            for (int variant = 0; variant < 2; variant++)
            {
                int calls = 0; byte[] temporary = null; ManualProtectionAttempt attempt; ManualProtectionAttemptIssue issue;
                int selected = variant;
                Check(!ManualProtectionAttempt.TryCreateWithRandom(op, SingleReadTarget(new object()), BinderCompleteMetadata(1), bytes =>
                { calls++; temporary = bytes; ManualCoreFill(bytes); if (selected == 0) Array.Clear(bytes, 8, 8); else Array.Copy(bytes, 0, bytes, 8, 8); }, out attempt, out issue), "bad tuple produced an attempt");
                Equal(selected == 0 ? ManualProtectionAttemptIssue.ZeroComparisonContent : ManualProtectionAttemptIssue.DuplicateComparisonContent, issue);
                Equal(1, calls); Check(attempt == null && temporary.All(cell => cell == 0), "abort retained entropy or an attempt");
            }
        });
        Add("manual invalid operation platform profile enumeration and metadata are rejected before random generation", () =>
        {
            int calls = 0; ManualProtectionAttempt attempt; ManualProtectionAttemptIssue issue;
            Action<byte[]> fill = bytes => { calls++; ManualCoreFill(bytes); };
            Check(!ManualProtectionAttempt.TryCreateWithRandom((ManualProtectionOperation)9, SingleReadTarget(new object()), BinderCompleteMetadata(1), fill, out attempt, out issue), "unknown operation admitted");
            Equal(ManualProtectionAttemptIssue.InvalidOperation, issue);
            foreach (var op in ManualCoreOperations)
            {
                foreach (var target in new[] { SingleReadTarget(new object(), windows10X64: false), SingleReadTarget(new object(), model: "OtherModel"),
                    SingleReadTarget(new object(), bios: "OtherBios"), SingleReadTarget(new object(), namespaceName: @"\\remote\root\WMI"),
                    SingleReadTarget(new object(), instanceCount: 2), SingleReadTarget(new object(), active: false) })
                    Check(!ManualProtectionAttempt.TryCreateWithRandom(op, target, BinderCompleteMetadata(1), fill, out attempt, out issue), "out of scope target admitted");
                Check(!ManualProtectionAttempt.TryCreateWithRandom(op, SingleReadTarget(new object()), null, fill, out attempt, out issue), "missing metadata admitted");
            }
            Equal(0, calls);
        });
        Add("manual numeric review separates read snapshots writes and already desired no-op state", () =>
        {
            foreach (var op in ManualCoreOperations)
            {
                var review = new ManualProtectionReview(op);
                foreach (var role in ManualProtectionAttempt.Schedule(op))
                {
                    var next = review.Observe(role == ManualProtectionRole.SemanticSet
                        ? new ManualProtectionObservation(role, ManualProtectionEvidence.SetterReceipt)
                        : new ManualProtectionObservation(role, ManualProtectionEvidence.ReadCandidate, ManualCoreValue(op, role)));
                    Check(next.IsAccepted, "normal fixed evidence rejected");
                }
                var value = review.Snapshot;
                Equal(op == ManualProtectionOperation.ReadState ? ManualProtectionStatus.StateRead : ManualProtectionStatus.ChangedCandidate, value.Status);
                Equal(ManualProtectionLimits.MaximumReadCandidates(op), value.ReadCandidates);
                Equal<int?>(op == ManualProtectionOperation.DisableProtection ? 0 : 1, value.ModeCandidate);
                Equal(op != ManualProtectionOperation.ReadState, value.SetterReceiptAccepted);
                if (op == ManualProtectionOperation.ReadState) { Equal<int?>(64, value.UpperCandidate); Equal<int?>(32, value.LowerCandidate); }
                if (op == ManualProtectionOperation.Enable80) { Equal<int?>(80, value.UpperCandidate); Equal<int?>(75, value.LowerCandidate); }
                if (op == ManualProtectionOperation.DisableProtection) { Check(!value.UpperCandidate.HasValue && !value.LowerCandidate.HasValue, "disable fabricated thresholds"); }
            }
            foreach (var op in new[] { ManualProtectionOperation.Enable80, ManualProtectionOperation.DisableProtection })
            {
                var review = new ManualProtectionReview(op);
                var decision = review.Observe(new ManualProtectionObservation(ManualProtectionRole.PreMode, ManualProtectionEvidence.ReadCandidate, op == ManualProtectionOperation.Enable80 ? 1 : 0));
                Check(decision.IsAccepted && decision.IsTerminal, "desired mode did not terminate before setter");
                Equal(ManualProtectionStatus.AlreadyDesiredCandidate, decision.Snapshot.Status); Equal(1, decision.Snapshot.ReadCandidates);
                Check(!decision.Snapshot.SetterReceiptAccepted && !decision.Snapshot.UpperCandidate.HasValue && !decision.Snapshot.LowerCandidate.HasValue, "no-op inferred a setter or thresholds");
            }
        });
        Add("manual review rejects missing historical wrong-stage and receipt-on-reader without known state", () =>
        {
            foreach (var op in ManualCoreOperations)
            foreach (var bad in new[] { (ManualProtectionObservation)null,
                new ManualProtectionObservation(ManualProtectionRole.PostMode, ManualProtectionEvidence.ReadCandidate, 0),
                new ManualProtectionObservation(ManualProtectionRole.PreMode, ManualProtectionEvidence.Historical, 1),
                new ManualProtectionObservation(ManualProtectionRole.PreMode, ManualProtectionEvidence.SetterReceipt),
                new ManualProtectionObservation(ManualProtectionRole.PreMode, ManualProtectionEvidence.ReadCandidate, 2) })
            {
                var review = new ManualProtectionReview(op); Check(!review.Observe(bad).IsAccepted, "bad evidence admitted");
                Equal(ManualProtectionStatus.Rejected, review.Snapshot.Status);
                Check(!review.Snapshot.ModeCandidate.HasValue, "rejection published current mode");
            }
        });
        AddAsync("manual sessions validate dependencies and unused close creates no source", async () =>
        {
            var f = new ManualCoreFixture(ManualProtectionOperation.ReadState);
            BatteryThrows<ArgumentNullException>(() => new ManualProtectionSession(null, f.Factory, f.Gate));
            BatteryThrows<ArgumentNullException>(() => new ManualProtectionSession(f.Attempt, null, f.Gate));
            BatteryThrows<ArgumentNullException>(() => new ManualProtectionSession(f.Attempt, f.Factory, null));
            var wrongIdentity = new object();
            BatteryThrows<ArgumentException>(() => new ManualProtectionSession(f.Attempt,
                new ManualCoreFactory(ManualCoreAttempt(ManualProtectionOperation.ReadState, wrongIdentity), wrongIdentity), f.Gate));
            await CooperativeAwait(f.Session.RequestCloseAsync()); Equal(ManualProtectionStatus.Busy, (await f.Session.RunAsync()).Status);
            Equal(0, f.Factory.Calls); Equal(0, f.Gate.Calls);
        });
        AddAsync("manual sessions execute only the exact lazy three seven three schedules under one owner", async () =>
        {
            foreach (var op in ManualCoreOperations)
            {
                var f = new ManualCoreFixture(op);
                try
                {
                    Equal(0, f.Factory.Calls);
                    var result = await ManualCoreOutcome(f.Session.RunAsync());
                    Equal(op == ManualProtectionOperation.ReadState ? ManualProtectionStatus.StateRead : ManualProtectionStatus.ChangedCandidate, result.Status);
                    Equal(f.Attempt.MaximumMethodEntries, result.StartedStages); Equal(f.Attempt.MaximumReadCandidates, result.ReadCandidates);
                    Equal(f.Attempt.MaximumMethodEntries, f.Factory.Calls);
                    Check(f.Factory.Nodes.All(n => n.Invocations == 1 && n.OutputCalls == 1 && n.InputCalls == 1), "normal manual path retried or leaked a leaf");
                    Check(f.Factory.Order.SequenceEqual(f.Attempt.StageOrder), "manual order changed");
                    Check(f.Factory.Threads.All(id => id == f.Gate.AcquireThread), "role preparation left the one owner thread");
                    await ManualCoreClosed(f); Equal(1, f.Gate.Calls);
                }
                finally { await ManualCoreFinish(f); }
            }
        });
        AddAsync("manual desired-mode operations stop after one mode read without threshold assumptions", async () =>
        {
            foreach (var op in new[] { ManualProtectionOperation.Enable80, ManualProtectionOperation.DisableProtection })
            {
                var f = new ManualCoreFixture(op); f.Factory.Nodes[0].ChangeReply = raw => raw[7] = (byte)(op == ManualProtectionOperation.Enable80 ? 1 : 0);
                try
                {
                    var result = await ManualCoreOutcome(f.Session.RunAsync());
                    Equal(ManualProtectionStatus.AlreadyDesiredCandidate, result.Status); Equal(1, result.StartedStages); Equal(1, result.ReadCandidates);
                    Check(!result.SetterRoleStarted && !result.SetterReceiptAccepted && !result.UpperCandidate.HasValue && !result.LowerCandidate.HasValue, "desired-mode path wrote or fabricated thresholds");
                    ManualCorePrefix(f, 1); await ManualCoreClosed(f);
                }
                finally { await ManualCoreFinish(f); }
            }
        });
        AddAsync("manual consumed attempt cannot be rewrapped while a new explicit attempt remains independent", async () =>
        {
            var f = new ManualCoreFixture(ManualProtectionOperation.ReadState);
            try
            {
                await ManualCoreOutcome(f.Session.RunAsync()); await ManualCoreClosed(f);
                var secondFactory = new ManualCoreFactory(f.Attempt, f.Factory.TargetIdentity); var secondGate = new CooperativeTestGate();
                var peer = new ManualProtectionSession(f.Attempt, secondFactory, secondGate);
                var busy = await peer.RunAsync(); Equal(ManualProtectionStatus.Busy, busy.Status);
                Equal(0, busy.StartedStages); Equal(0, busy.ReadCandidates); Check(!busy.PreModeCandidate.HasValue, "busy request reused previous state");
                await CooperativeAwait(peer.RequestCloseAsync()); Equal(0, secondFactory.Calls); Equal(0, secondGate.Calls);
                var next = new ManualCoreFixture(ManualProtectionOperation.ReadState, identity: f.Factory.TargetIdentity);
                try { Equal(ManualProtectionStatus.StateRead, (await ManualCoreOutcome(next.Session.RunAsync())).Status); await ManualCoreClosed(next); }
                finally { await ManualCoreFinish(next); }
            }
            finally { await ManualCoreFinish(f); }
        });
        AddAsync("manual rejected replies and post mismatch stop without exposing a new current snapshot", async () =>
        {
            foreach (var op in ManualCoreOperations)
            {
                var f = new ManualCoreFixture(op); f.Factory.Nodes[0].ChangeReply = raw => raw[7] = 0xf0;
                try { var result = await ManualCoreOutcome(f.Session.RunAsync()); Equal(ManualProtectionStatus.Rejected, result.Status); ManualCorePrefix(f, 1); Check(!result.ModeCandidate.HasValue, "echo became current state"); await ManualCoreClosed(f); }
                finally { await ManualCoreFinish(f); }
            }
            foreach (var op in new[] { ManualProtectionOperation.Enable80, ManualProtectionOperation.DisableProtection })
            {
                var f = new ManualCoreFixture(op); int index = f.Attempt.GetIndex(ManualProtectionRole.PostMode);
                f.Factory.Nodes[index].ChangeReply = raw => raw[7] = (byte)(op == ManualProtectionOperation.Enable80 ? 0 : 1);
                try
                {
                    var result = await ManualCoreOutcome(f.Session.RunAsync()); Equal(ManualProtectionStatus.Rejected, result.Status);
                    Check(result.SetterReceiptAccepted && !result.ModeCandidate.HasValue && !result.UpperCandidate.HasValue && !result.LowerCandidate.HasValue, "failed readback displayed expected values");
                    ManualCorePrefix(f, index+1); await ManualCoreClosed(f);
                }
                finally { await ManualCoreFinish(f); }
            }
        });
        AddAsync("manual gate refusal and caller cancellation before admission create no SDK leaf", async () =>
        {
            foreach (bool cancelled in new[] { false, true })
            {
                var gate = new CooperativeTestGate { Handler = (timeout, signal) => new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.AccessDenied) };
                var f = new ManualCoreFixture(ManualProtectionOperation.Enable80, gate: gate);
                try
                {
                    var result = await ManualCoreOutcome(f.Session.RunAsync(new CancellationToken(cancelled)));
                    Equal(cancelled ? ManualProtectionStatus.Cancelled : ManualProtectionStatus.Rejected, result.Status);
                    Equal(0, f.Factory.Calls); await CooperativeAwait(f.Session.RequestCloseAsync());
                }
                finally { await ManualCoreFinish(f); }
            }
        });
        AddAsync("manual partial preparation closes output before inputs without invoking a source", async () =>
        {
            var f = new ManualCoreFixture(ManualProtectionOperation.Enable80); f.Factory.Nodes[0].Ready = false;
            try
            {
                Equal(ManualProtectionStatus.Rejected, (await ManualCoreOutcome(f.Session.RunAsync())).Status);
                var node = f.Factory.Nodes[0]; Equal(0, node.Invocations); Equal(1, node.OutputCalls); Equal(1, node.InputCalls);
                Check(node.CleanupOrder.SequenceEqual(new[] {"output", "input"}), "partial ownership cleanup reordered");
                ManualCorePrefix(f, 1); await ManualCoreClosed(f);
            }
            finally { await ManualCoreFinish(f); }
        });
        AddAsync("manual early source output cannot release an invocation stack and cancellation becomes unknown", async () =>
        {
            using (var release = new ManualResetEventSlim())
            {
                var f = new ManualCoreFixture(ManualProtectionOperation.DisableProtection); var node = f.Factory.Nodes[0];
                var reported = CooperativeCompletion(); node.Invoke = () => { node.SupplyFinal(); reported.TrySetResult(true); Check(release.Wait(TimeSpan.FromSeconds(5)), "fake stack not released"); };
                var run = f.Session.RunAsync();
                try
                {
                    await CooperativeAwait(reported.Task); Equal(0, node.OutputCalls); Equal(0, node.InputCalls);
                    var close = f.Session.RequestCloseAsync(); var result = await ManualCoreOutcome(run);
                    Equal(ManualProtectionStatus.Unknown, result.Status); Check(!close.IsCompleted && f.Gate.LastLease.IsHeld, "active stack released its owner");
                    release.Set(); await CooperativeAwait(close); ManualCorePrefix(f, 1);
                }
                finally { release.Set(); await ManualCoreFinish(f); }
            }
        });
        AddAsync("manual output and input pending cleanup each prevent the next role for every operation", async () =>
        {
            foreach (var op in ManualCoreOperations)
            foreach (bool pendingOutput in new[] { false, true })
            {
                var f = new ManualCoreFixture(op); int index = op == ManualProtectionOperation.ReadState ? 0 : f.Attempt.GetIndex(ManualProtectionRole.SemanticSet);
                var node = f.Factory.Nodes[index]; var pending = new TaskCompletionSource<WsabiWmiProtectionCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
                if (pendingOutput) node.Output = () => pending.Task; else node.Input = () => pending.Task;
                var run = f.Session.RunAsync();
                try
                {
                    await InvocationEventually(() => pendingOutput ? node.OutputCalls == 1 : node.InputCalls == 1);
                    Equal(index+1, f.Factory.Calls); Check(f.Gate.LastLease.IsHeld && !run.IsCompleted, "pending cleanup permitted another role");
                    if (pendingOutput) Equal(0, node.InputCalls);
                    pending.TrySetResult(WsabiWmiProtectionCleanupStatus.Complete);
                    Equal(op == ManualProtectionOperation.ReadState ? ManualProtectionStatus.StateRead : ManualProtectionStatus.ChangedCandidate, (await ManualCoreOutcome(run)).Status);
                    await ManualCoreClosed(f);
                }
                finally { pending.TrySetResult(WsabiWmiProtectionCleanupStatus.Complete); await ManualCoreFinish(f); }
            }
        });
        AddAsync("manual uncertain output retains inputs owner and all later roles until explicit fake detach", async () =>
        {
            foreach (var status in new[] { WsabiWmiProtectionCleanupStatus.Failed, WsabiWmiProtectionCleanupStatus.Unknown })
            {
                var f = new ManualCoreFixture(ManualProtectionOperation.DisableProtection); var node = f.Factory.Nodes[0]; node.Output = () => Task.FromResult(status);
                try
                {
                    Equal(ManualProtectionStatus.Unknown, (await ManualCoreOutcome(f.Session.RunAsync())).Status);
                    var close = f.Session.RequestCloseAsync(); Equal(0, node.InputCalls);
                    Check(!close.IsCompleted && f.Gate.LastLease.IsHeld && f.Session.IsCompletionUnknown, "uncertain output released related ownership");
                    ManualCorePrefix(f, 1);
                }
                finally { await ManualCoreFinish(f); }
            }
        });
        AddAsync("manual late capture after display timeout joins actual closure without entering another role", async () =>
        {
            var f = new ManualCoreFixture(ManualProtectionOperation.Enable80, display: TimeSpan.FromSeconds(1)); var node = f.Factory.Nodes[0]; node.Invoke = () => { };
            var run = f.Session.RunAsync();
            try
            {
                await CooperativeAwait(node.Returned.Task);
                Equal(ManualProtectionStatus.TimedOut, (await ManualCoreOutcome(run)).Status);
                var close = f.Session.RequestCloseAsync(); Check(!close.IsCompleted && f.Gate.LastLease.IsHeld, "display deadline forced actual closure");
                node.SupplyFinal(); await CooperativeAwait(close); ManualCorePrefix(f, 1);
            }
            finally { await ManualCoreFinish(f); }
        });
        AddAsync("manual incomplete preparation remains owned through stop until its actual leaf is returned", async () =>
        {
            var f = new ManualCoreFixture(ManualProtectionOperation.ReadState); var node = f.Factory.Nodes[0];
            node.Preparation = new TaskCompletionSource<WsabiWmiProtectionLeaf>(TaskCreationOptions.RunContinuationsAsynchronously);
            var run = f.Session.RunAsync();
            try
            {
                await CooperativeAwait(node.Prepared.Task); var close = f.Session.RequestCloseAsync();
                Equal(ManualProtectionStatus.Unknown, (await ManualCoreOutcome(run)).Status);
                Check(!close.IsCompleted && f.Gate.LastLease.IsHeld, "pending preparation dropped owner");
                node.Preparation.TrySetResult(node.MakeLeaf()); await CooperativeAwait(close);
                Equal(0, node.Invocations); Equal(1, node.OutputCalls); Equal(1, node.InputCalls); ManualCorePrefix(f, 1);
            }
            finally { await ManualCoreFinish(f); }
        });
        AddAsync("manual reporting exception still joins pending actual input cleanup", async () =>
        {
            var f = new ManualCoreFixture(ManualProtectionOperation.ReadState); var node = f.Factory.Nodes[0];
            var input = new TaskCompletionSource<WsabiWmiProtectionCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously); node.Input = () => input.Task;
            var run = f.Session.RunAndCloseAsync(result => { throw new InvalidOperationException("fake report failure"); });
            try
            {
                await InvocationEventually(() => node.InputCalls == 1); var close = f.Session.RequestCloseAsync();
                await Task.Yield(); Check(!run.IsCompleted && !close.IsCompleted, "report failure skipped actual join");
                input.TrySetResult(WsabiWmiProtectionCleanupStatus.Complete);
                try { await CooperativeAwait(run); throw new Exception("report failure erased"); } catch (InvalidOperationException) { }
                await CooperativeAwait(close); ManualCorePrefix(f, 1);
            }
            finally { input.TrySetResult(WsabiWmiProtectionCleanupStatus.Complete); await ManualCoreFinish(f); }
        });
        AddAsync("manual purpose cannot bypass existing common gate quarantine and preserves it for original tools", async () =>
        {
            var gate = new CooperativeTestGate(); WsabiWmiExchangeResource.For(gate).Quarantine();
            var f = new ManualCoreFixture(ManualProtectionOperation.ReadState, gate: gate);
            try
            {
                Equal(ManualProtectionStatus.Unknown, (await ManualCoreOutcome(f.Session.RunAsync())).Status);
                Check(f.Session.IsCompletionUnknown, "manual purpose lost common quarantine");
                Equal(0, f.Factory.Calls); Equal(0, gate.Calls); await CooperativeAwait(f.Session.RequestCloseAsync());
                var original = new DisableSessionFixture(gate: gate);
                try { Equal(WsabiWmiProtectionDisableStatus.GateRejected, (await DisableSessionOutcome(original.Session.RunAsync())).Status); Equal(0, original.Factory.Calls); }
                finally { await DisableSessionFinish(original); }
            }
            finally { await ManualCoreFinish(f); }
        });
    }

    private static int ManualCoreValue(ManualProtectionOperation op, ManualProtectionRole role)
    {
        switch (role)
        {
            case ManualProtectionRole.PreMode: return op == ManualProtectionOperation.Enable80 ? 0 : 1;
            case ManualProtectionRole.PreUpper: return 64;
            case ManualProtectionRole.PreLower: return 32;
            case ManualProtectionRole.PostMode: return op == ManualProtectionOperation.Enable80 ? 1 : 0;
            case ManualProtectionRole.PostUpper: return 80;
            case ManualProtectionRole.PostLower: return 75;
            default: return op == ManualProtectionOperation.Enable80 ? 1 : 0;
        }
    }
    private static ManualProtectionAttempt ManualCoreAttempt(ManualProtectionOperation op, object identity)
    {
        ManualProtectionAttempt attempt; ManualProtectionAttemptIssue issue;
        Check(ManualProtectionAttempt.TryCreateWithRandom(op, SingleReadTarget(identity), BinderCompleteMetadata(1), ManualCoreFill, out attempt, out issue), "manual attempt fixture failed");
        Equal(ManualProtectionAttemptIssue.None, issue); return attempt;
    }
    private static void ManualCoreFill(byte[] bytes) { for (int i = 0; i < bytes.Length; i++) bytes[i] = (byte)(i+1); }
    private static async Task<ManualProtectionOutcome> ManualCoreOutcome(Task<ManualProtectionOutcome> task) { await CooperativeAwait(task); return await task; }
    private static void ManualCorePrefix(ManualCoreFixture f, int count)
    { Equal(count, f.Factory.Calls); for (int i = count; i < f.Factory.Nodes.Length; i++) Equal(0, f.Factory.Nodes[i].Invocations); }
    private static async Task ManualCoreClosed(ManualCoreFixture f)
    {
        await CooperativeAwait(f.Session.RequestCloseAsync());
        Check(f.Gate.LastLease != null && !f.Gate.LastLease.IsHeld, "owner close preceded lease release");
        Equal(1, f.Gate.LastLease.DisposeCalls); Equal(f.Gate.AcquireThread, f.Gate.LastLease.DisposeThread);
    }
    private static async Task ManualCoreFinish(ManualCoreFixture f)
    {
        var close = f.Session.RequestCloseAsync();
        foreach (var node in f.Factory.Nodes)
        {
            node.Preparation?.TrySetResult(node.MakeLeaf()); node.SupplyFinal();
            if (node.Invocations != 0) await CooperativeAwait(node.Returned.Task);
        }
        foreach (var node in f.Factory.Nodes)
        {
            if (node.Request == null) continue;
            await InvocationEventually(() => node.OutputCalls != 0); await CooperativeAwait(node.OutputFinished.Task);
            if (node.OutputSucceeded) { await InvocationEventually(() => node.InputCalls != 0); await CooperativeAwait(node.InputFinished.Task); }
        }
        f.Session.ConfirmDetachedForTests(); await CooperativeAwait(close);
    }
    private sealed class ManualCoreFixture
    {
        internal readonly ManualProtectionAttempt Attempt;
        internal readonly ManualCoreFactory Factory;
        internal readonly CooperativeTestGate Gate;
        internal readonly ManualProtectionSession Session;
        internal ManualCoreFixture(ManualProtectionOperation op, CooperativeTestGate gate = null, TimeSpan? display = null, object identity = null)
        {
            object target = identity ?? new SingleReadPoisonIdentity();
            Attempt = ManualCoreAttempt(op, target); Factory = new ManualCoreFactory(Attempt, target);
            Gate = gate ?? new CooperativeTestGate();
            Session = new ManualProtectionSession(Attempt, Factory, Gate, TimeSpan.FromMilliseconds(200), display ?? TimeSpan.FromSeconds(3));
        }
    }
    private sealed class ManualCoreFactory : IManualProtectionLeafFactory
    {
        private readonly ManualProtectionAttempt attempt;
        public object TargetIdentity { get; }
        internal readonly ManualCoreNode[] Nodes;
        internal readonly List<ManualProtectionRole> Order = new List<ManualProtectionRole>();
        internal readonly List<int> Threads = new List<int>();
        internal int Calls;
        internal ManualCoreFactory(ManualProtectionAttempt attempt, object target)
        {
            this.attempt = attempt;
            TargetIdentity = target;
            Nodes = attempt.StageOrder.Select(role => new ManualCoreNode(attempt.Operation, role)).ToArray();
        }
        public Task<WsabiWmiProtectionLeaf> PrepareAsync(ManualProtectionLeafRequest request, WsabiWmiProtectionStop stop)
        {
            Check(request.BelongsTo(attempt), "factory received a peer attempt");
            Calls++; Order.Add(request.Role); Threads.Add(Thread.CurrentThread.ManagedThreadId);
            var node = Nodes[request.Index]; node.Request = request; node.Prepared.TrySetResult(true);
            return node.Preparation == null ? Task.FromResult(node.MakeLeaf()) : node.Preparation.Task;
        }
    }
    private sealed class ManualCoreNode : IWsabiWmiInvocationSource
    {
        private readonly ManualProtectionOperation operation;
        private readonly ManualProtectionRole role;
        internal int Invocations, OutputCalls, InputCalls;
        internal bool Ready = true, OutputSucceeded;
        internal ManualProtectionLeafRequest Request;
        internal IWsabiWmiInvocationObserver Observer;
        internal TaskCompletionSource<WsabiWmiProtectionLeaf> Preparation;
        internal readonly TaskCompletionSource<bool> Prepared = CooperativeCompletion(), Returned = CooperativeCompletion();
        internal readonly TaskCompletionSource<bool> OutputFinished = CooperativeCompletion(), InputFinished = CooperativeCompletion();
        internal readonly List<string> CleanupOrder = new List<string>();
        internal Action Invoke;
        internal Action<byte[]> ChangeReply;
        internal Func<Task<WsabiWmiProtectionCleanupStatus>> Output = () => Task.FromResult(WsabiWmiProtectionCleanupStatus.Complete);
        internal Func<Task<WsabiWmiProtectionCleanupStatus>> Input = () => Task.FromResult(WsabiWmiProtectionCleanupStatus.Complete);
        internal ManualCoreNode(ManualProtectionOperation op, ManualProtectionRole role) { operation = op; this.role = role; }
        void IWsabiWmiInvocationSource.Invoke(WsabiWmiMethodRequest request, IWsabiWmiInvocationObserver observer)
        {
            Interlocked.Increment(ref Invocations); Observer = observer;
            try { Check(Request.Matches(request), "source fixed frame mismatch"); if (Invoke == null) SupplyFinal(); else Invoke(); }
            finally { Returned.TrySetResult(true); }
        }
        internal WsabiWmiProtectionLeaf MakeLeaf() => new WsabiWmiProtectionLeaf(Ready, this, CloseOutput, CloseInput);
        private Task<WsabiWmiProtectionCleanupStatus> CloseOutput()
        {
            try
            {
                Interlocked.Increment(ref OutputCalls); CleanupOrder.Add("output");
                Check(Invocations == 0 || Returned.Task.IsCompleted, "output closed before invocation stack return");
                var task = Output();
                if (task == null) { OutputFinished.TrySetResult(true); return null; }
                _ = task.ContinueWith(done => { OutputSucceeded = done.Status == TaskStatus.RanToCompletion && done.Result == WsabiWmiProtectionCleanupStatus.Complete; _ = done.Exception; OutputFinished.TrySetResult(true); }, CancellationToken.None, TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
                return task;
            }
            catch { OutputFinished.TrySetResult(true); throw; }
        }
        private Task<WsabiWmiProtectionCleanupStatus> CloseInput()
        {
            try
            {
                Interlocked.Increment(ref InputCalls); CleanupOrder.Add("input"); Check(OutputCalls == 1, "input preceded output");
                var task = Input();
                if (task == null) { InputFinished.TrySetResult(true); return null; }
                _ = task.ContinueWith(done => { _ = done.Exception; InputFinished.TrySetResult(true); }, CancellationToken.None, TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
                return task;
            }
            catch { InputFinished.TrySetResult(true); throw; }
        }
        internal void SupplyFinal()
        {
            if (Observer == null || Request == null) return;
            var frame = Request.Request.Frame; var raw = new byte[21]; raw[4] = 0xaa;
            raw[7] = (byte)(role == ManualProtectionRole.SemanticSet ? frame[7] : ManualCoreValue(operation, role));
            raw[8] = frame[8]; Array.Copy(frame, 9, raw, 9, 8); ChangeReply?.Invoke(raw);
            Observer.ReportTerminal(0); Observer.SettleCapture(raw);
        }
    }
}
