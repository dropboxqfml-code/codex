using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    // Inert bindings and detached synthetic RESPONSES only. There is no SDK,
    // request header, selector, address, RNG, marker or public execution path.
    private static void RegisterWsabiWmiProtectionStageBindingTests()
    {
        AddAsync("bound protection stages preserve one owner and distinguish receipt from acknowledgement and six read candidates", async () =>
        {
            var fixture = new StageBindingFixture();
            foreach (var node in fixture.Nodes) Array.Clear(node.ComparisonInput, 0, node.ComparisonInput.Length);
            fixture.Stages[0] = null; // Construction must retain its own stage snapshot.
            try
            {
                var outcome = await StageBindingOutcome(fixture.Coordinator.RunAsync());
                SevenStageAssertStatus(outcome, WsabiWmiSevenStageStatus.StoredReadbackMatchedCandidate, 7);
                Check(outcome.Snapshot.SetterReceiptAccepted && !outcome.Snapshot.SetterAcknowledged,
                    "receipt-only output was promoted to a semantic setter acknowledgement");
                Equal(6, outcome.Snapshot.BoundReadCandidateCount);
                Check(fixture.Order.SequenceEqual(WsabiWmiProtectionTransitionReview.StageOrder), "bound role order changed");
                Check(fixture.Nodes.All(node => node.Calls == 1 && node.CallThread == fixture.Gate.AcquireThread), "bound stages changed owner or retried");
                foreach (var node in fixture.Nodes)
                {
                    Equal(node.Role == WsabiWmiProtectionTransitionStage.SemanticSet1
                        ? WsabiWmiBoundStageReviewStatus.ReceiptOnly : WsabiWmiBoundStageReviewStatus.ReadCandidate, node.Stage.ReviewStatus);
                    Check(!node.Stage.IsExecutable && !node.Stage.IsHardwareObservation && !node.Stage.IsFreshnessProven &&
                        !node.Stage.IsSetterExecutionConfirmed && !node.Stage.CanWriteHardware, "local binding became physical evidence or write authority");
                    byte[] raw = node.Raw();
                    Check(raw.Take(4).All(value => value == 0) && raw[4] == 0xaa, "fixture acquired an executable request header");
                }
                await StageBindingAssertClosed(fixture); Equal(1, fixture.Gate.Calls);
            }
            finally { await StageBindingFinish(fixture); }
        });

        Add("protection binding identities are required distinct local references without provider equality or formatting", () =>
        {
            var procedure = new StageBindingPoisonIdentity(); var target = new StageBindingPoisonIdentity();
            var resources = Enumerable.Range(0, 4).Select(index => (object)new StageBindingPoisonIdentity()).ToArray();
            var binding = new WsabiWmiProtectionStageBinding(WsabiWmiProtectionTransitionStage.PreMode,
                procedure, target, resources[0], resources[1], resources[2], resources[3]);
            binding.Resources[0] = new object();
            Check(ReferenceEquals(resources[0], binding.Resources[0]), "resource identity array escaped its binding");
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiProtectionStageBinding(WsabiWmiProtectionTransitionStage.PreMode,
                null, target, resources[0], resources[1], resources[2], resources[3]));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiProtectionStageBinding(WsabiWmiProtectionTransitionStage.PreMode,
                procedure, null, resources[0], resources[1], resources[2], resources[3]));
            BatteryThrows<ArgumentException>(() => new WsabiWmiProtectionStageBinding(WsabiWmiProtectionTransitionStage.PreMode,
                procedure, procedure, resources[0], resources[1], resources[2], resources[3]));
            for (int index = 0; index < 4; index++)
            {
                var absent = (object[])resources.Clone(); absent[index] = null;
                BatteryThrows<ArgumentException>(() => new WsabiWmiProtectionStageBinding(WsabiWmiProtectionTransitionStage.PreMode,
                    procedure, target, absent[0], absent[1], absent[2], absent[3]));
                var alias = (object[])resources.Clone(); alias[index] = procedure;
                BatteryThrows<ArgumentException>(() => new WsabiWmiProtectionStageBinding(WsabiWmiProtectionTransitionStage.PreMode,
                    procedure, target, alias[0], alias[1], alias[2], alias[3]));
            }
            BatteryThrows<ArgumentException>(() => new WsabiWmiProtectionStageBinding(WsabiWmiProtectionTransitionStage.PreMode,
                procedure, target, resources[0], resources[0], resources[2], resources[3]));
            Check(!typeof(WsabiWmiProtectionStageBinding).IsPublic && !typeof(WsabiWmiProtectionBoundStage).IsPublic &&
                !typeof(WsabiWmiProtectionBindingPlan).IsPublic, "fake binding machinery became public");
        });

        Add("protection binding plan rejects role procedure target and duplicate comparison mismatches before acquiring a gate", () =>
        {
            for (int variant = 0; variant < 4; variant++)
            {
                var procedure = new StageBindingPoisonIdentity(); var target = new StageBindingPoisonIdentity();
                var nodes = StageBindingNodes(procedure, target);
                int index = variant == 0 ? 0 : 4;
                nodes[index] = new StageBindingNode(variant == 0 ? WsabiWmiProtectionTransitionStage.PreUpper : WsabiWmiProtectionTransitionStage.PostMode,
                    index, variant == 1 ? new StageBindingPoisonIdentity() : procedure,
                    variant == 2 ? new StageBindingPoisonIdentity() : target,
                    comparison: variant == 3 ? nodes[0].ComparisonInput : null);
                var gate = new CooperativeTestGate();
                BatteryThrows<ArgumentException>(() => StageBindingPlan(gate, nodes.Select(node => node.Stage).ToArray()));
                Equal(0, gate.Calls); Check(nodes.All(node => node.Calls == 0), "invalid binding plan entered a leaf");
            }
        });

        Add("protection binding plan rejects every cross-role resource alias before gate acquisition", () =>
        {
            for (int resource = 0; resource < 4; resource++)
            {
                var procedure = new StageBindingPoisonIdentity(); var target = new StageBindingPoisonIdentity();
                var nodes = StageBindingNodes(procedure, target);
                var identities = nodes[1].Binding.Resources; identities[resource] = nodes[0].Binding.Resources[resource];
                nodes[1] = new StageBindingNode(WsabiWmiProtectionTransitionStage.PreUpper, 1, procedure, target, resources: identities);
                var gate = new CooperativeTestGate();
                BatteryThrows<ArgumentException>(() => StageBindingPlan(gate, nodes.Select(node => node.Stage).ToArray()));
                Equal(0, gate.Calls); Check(nodes.All(node => node.Calls == 0), "aliased resource acquired the owner");
            }
        });

        AddAsync("protection binding resources and procedure cannot be repackaged into another plan after use", async () =>
        {
            var first = new StageBindingFixture();
            try
            {
                await StageBindingOutcome(first.Coordinator.RunAsync()); await StageBindingAssertClosed(first);
                for (int alias = 0; alias < 5; alias++)
                {
                    var procedure = alias == 4 ? first.Procedure : new StageBindingPoisonIdentity();
                    var target = new StageBindingPoisonIdentity(); var nodes = StageBindingNodes(procedure, target);
                    if (alias < 4)
                    {
                        var identities = nodes[0].Binding.Resources; identities[alias] = first.Nodes[0].Binding.Resources[alias];
                        nodes[0] = new StageBindingNode(WsabiWmiProtectionTransitionStage.PreMode, 0, procedure, target, resources: identities);
                    }
                    var gate = new CooperativeTestGate(); var coordinator = StageBindingPlan(gate, nodes.Select(node => node.Stage).ToArray());
                    try
                    {
                        var rejected = await StageBindingOutcome(coordinator.RunAsync());
                        SevenStageAssertStatus(rejected, WsabiWmiSevenStageStatus.AlreadyUsed, 0);
                        await CooperativeAwait(coordinator.ActualCompletion);
                        Equal(0, gate.Calls); Check(nodes.All(node => node.Calls == 0), "resource rewrapping started another procedure");
                    }
                    finally { await StageBindingFinish(coordinator, nodes); }
                }
            }
            finally { await StageBindingFinish(first); }
        });

        AddAsync("bound replies require their exact stage binding and missing replies fail without later roles", async () =>
        {
            foreach (int index in new[] { 0, 3 })
            for (int variant = 0; variant < 5; variant++)
            {
                var fixture = new StageBindingFixture(index); var node = fixture.Nodes[index]; int mismatch = variant;
                node.Handler = stop =>
                {
                    WsabiWmiProtectionBoundReply reply = null;
                    if (mismatch != 4)
                    {
                        var ids = node.Binding.Resources;
                        var other = new WsabiWmiProtectionStageBinding(mismatch == 0
                            ? (node.Role == WsabiWmiProtectionTransitionStage.PreMode ? WsabiWmiProtectionTransitionStage.PreUpper : WsabiWmiProtectionTransitionStage.PreMode)
                            : node.Role, mismatch == 1 ? new StageBindingPoisonIdentity() : fixture.Procedure,
                            mismatch == 2 ? new StageBindingPoisonIdentity() : fixture.Target, ids[0], ids[1], ids[2], ids[3]);
                        reply = new WsabiWmiProtectionBoundReply(other, StageBindingExchange(node.Raw()));
                    }
                    node.Detach(); return Task.FromResult(reply);
                };
                try
                {
                    var rejected = await StageBindingOutcome(fixture.Coordinator.RunAsync());
                    SevenStageAssertStatus(rejected, WsabiWmiSevenStageStatus.StageRejected, index + 1);
                    Equal(mismatch == 4 ? WsabiWmiBoundStageReviewStatus.MissingReply : WsabiWmiBoundStageReviewStatus.BindingMismatch, node.Stage.ReviewStatus);
                    StageBindingAssertPrefix(fixture, index + 1); await StageBindingAssertClosed(fixture);
                }
                finally { await StageBindingFinish(fixture); }
            }
        });

        AddAsync("bound read receipt and final read each wait for invocation output and input close independently", async () =>
        {
            foreach (int index in new[] { 0, 3, 6 })
            for (int component = 0; component < 3; component++)
            {
                var fixture = new StageBindingFixture(index); var node = fixture.Nodes[index];
                var run = fixture.Coordinator.RunAsync();
                try
                {
                    await CooperativeAwait(node.Entered.Task); node.SupplyReply();
                    for (int other = 0; other < 3; other++) if (other != component) node.CompleteComponent(other);
                    await InvocationEventually(() => node.Stage.ReviewStatus == (index == 3
                        ? WsabiWmiBoundStageReviewStatus.ReceiptOnly : WsabiWmiBoundStageReviewStatus.ReadCandidate));
                    Check(!node.Stage.Operation.Lifetime.ActualClose.IsCompleted && !fixture.Coordinator.ActualCompletion.IsCompleted && fixture.Gate.LastLease.IsHeld,
                        "one pending close component was erased into an actual-close witness");
                    StageBindingAssertPrefix(fixture, index + 1);
                    var close = fixture.Coordinator.RequestCloseAsync();
                    var stopped = await StageBindingOutcome(run);
                    SevenStageAssertStatus(stopped, WsabiWmiSevenStageStatus.Cancelled, index + 1);
                    Check(!close.IsCompleted, "stop bypassed a bound input/output/invocation close");
                    node.Detach(); await StageBindingAssertClosed(fixture); StageBindingAssertPrefix(fixture, index + 1);
                }
                finally { await StageBindingFinish(fixture); }
            }
        });

        AddAsync("bound close failure unknown fault or cancellation reports uncertainty while other cleanup is still pending", async () =>
        {
            for (int component = 0; component < 3; component++)
            for (int variant = 0; variant < (component == 0 ? 2 : 4); variant++)
            {
                var fixture = new StageBindingFixture(3); var node = fixture.Nodes[3];
                var run = fixture.Coordinator.RunAsync();
                try
                {
                    await CooperativeAwait(node.Entered.Task); node.SupplyReply(); node.FailComponent(component, variant);
                    var rejected = await StageBindingOutcome(run);
                    SevenStageAssertStatus(rejected, WsabiWmiSevenStageStatus.CompletionUnknown, 4);
                    Check(!node.Stage.Operation.Lifetime.ActualClose.IsCompleted && !fixture.Coordinator.ActualCompletion.IsCompleted && fixture.Gate.LastLease.IsHeld,
                        "failed close status was converted into actual termination");
                    Check(node.Stage.Operation.Lifetime.Uncertainty.IsCompleted, "early close failure was hidden behind another pending component");
                    StageBindingAssertPrefix(fixture, 4);
                    await node.DetachAndConfirmForTest(); // Explicit fake teardown evidence, never production recovery.
                    await StageBindingAssertClosed(fixture); StageBindingAssertPrefix(fixture, 4);
                }
                finally { await StageBindingFinish(fixture); }
            }
        });

        AddAsync("bound early replies cannot resume later roles after caller stop or display timeout", async () =>
        {
            foreach (int index in new[] { 3, 6 })
            foreach (bool timeout in new[] { false, true })
            using (var caller = new CancellationTokenSource())
            {
                var fixture = new StageBindingFixture(index, timeout ? TimeSpan.FromMilliseconds(500) : TimeSpan.FromSeconds(3));
                var node = fixture.Nodes[index]; var run = fixture.Coordinator.RunAsync(caller.Token);
                try
                {
                    await CooperativeAwait(node.Entered.Task); node.SupplyReply();
                    if (!timeout) caller.Cancel();
                    var outcome = await StageBindingOutcome(run);
                    SevenStageAssertStatus(outcome, timeout ? WsabiWmiSevenStageStatus.TimedOut : WsabiWmiSevenStageStatus.Cancelled, index + 1);
                    Check(!fixture.Coordinator.ActualCompletion.IsCompleted && fixture.Gate.LastLease.IsHeld, "display completion released the bound resources");
                    node.Detach(); await StageBindingAssertClosed(fixture); StageBindingAssertPrefix(fixture, index + 1);
                }
                finally { await StageBindingFinish(fixture); }
            }
        });

        AddAsync("bound direct start throw and null task preserve unknown ownership until all source resources close", async () =>
        {
            foreach (int index in new[] { 0, 3 })
            foreach (bool throws in new[] { false, true })
            {
                var fixture = new StageBindingFixture(index); var node = fixture.Nodes[index];
                node.Handler = stop => { if (throws) throw new InvalidOperationException("Unreported fake bound source detail."); return null; };
                try
                {
                    var outcome = await StageBindingOutcome(fixture.Coordinator.RunAsync());
                    SevenStageAssertStatus(outcome, WsabiWmiSevenStageStatus.CompletionUnknown, index + 1);
                    Equal(WsabiWmiBoundStageReviewStatus.NotReviewed, node.Stage.ReviewStatus);
                    Check(!fixture.Coordinator.ActualCompletion.IsCompleted && fixture.Gate.LastLease.IsHeld, "direct source failure manufactured completion");
                    node.Detach(); await StageBindingAssertClosed(fixture); StageBindingAssertPrefix(fixture, index + 1);
                }
                finally { await StageBindingFinish(fixture); }
            }
        });

        AddAsync("bound mismatching post values ambiguous reads and common failure replies stop at the first rejected role", async () =>
        {
            for (int index = 0; index < 7; index++)
            for (int variant = 0; variant < (index == 3 ? 1 : 2); variant++)
            {
                var fixture = new StageBindingFixture(index); var node = fixture.Nodes[index]; int rejection = variant;
                node.RawChange = raw =>
                {
                    if (rejection == 0) { Array.Clear(raw, 5, 16); raw[5] = 0xff; }
                    else raw[7] = 173;
                };
                node.AutoComplete = true;
                try
                {
                    var outcome = await StageBindingOutcome(fixture.Coordinator.RunAsync());
                    SevenStageAssertStatus(outcome, WsabiWmiSevenStageStatus.StageRejected, index + 1);
                    Equal(index == 3 ? WsabiWmiBoundStageReviewStatus.ReceiptRejected : WsabiWmiBoundStageReviewStatus.ReadRejected, node.Stage.ReviewStatus);
                    StageBindingAssertPrefix(fixture, index + 1); await StageBindingAssertClosed(fixture);
                }
                finally { await StageBindingFinish(fixture); }
            }
            for (int index = 4; index < 7; index++)
            {
                var fixture = new StageBindingFixture(index); var node = fixture.Nodes[index];
                node.RawChange = raw => raw[7] = (byte)(index == 4 ? 0 : index == 5 ? 79 : 74); node.AutoComplete = true;
                try
                {
                    var outcome = await StageBindingOutcome(fixture.Coordinator.RunAsync());
                    SevenStageAssertStatus(outcome, WsabiWmiSevenStageStatus.StageRejected, index + 1);
                    Equal(WsabiWmiBoundStageReviewStatus.ReadCandidate, node.Stage.ReviewStatus);
                    Check(outcome.Snapshot.SetterReceiptAccepted && !outcome.Snapshot.SetterAcknowledged,
                        "post mismatch altered receipt/acknowledgement semantics"); StageBindingAssertPrefix(fixture, index + 1);
                }
                finally { await StageBindingFinish(fixture); }
            }
        });

        AddAsync("bound actual cleanup may precede a lost detached reply and caller stop still releases without later roles", async () =>
        {
            foreach (int index in new[] { 0, 3, 6 })
            using (var caller = new CancellationTokenSource())
            {
                var fixture = new StageBindingFixture(index); var node = fixture.Nodes[index];
                var run = fixture.Coordinator.RunAsync(caller.Token);
                try
                {
                    await CooperativeAwait(node.Entered.Task); node.Detach();
                    await CooperativeAwait(node.Stage.Operation.Lifetime.ActualClose);
                    Check(!node.Reply.Task.IsCompleted, "fixture did not preserve its missing-reply case");
                    caller.Cancel(); SevenStageAssertStatus(await StageBindingOutcome(run), WsabiWmiSevenStageStatus.Cancelled, index + 1);
                    await StageBindingAssertClosed(fixture); StageBindingAssertPrefix(fixture, index + 1);
                    node.SupplyReply(); // Immutable detached fake data after resources are done.
                }
                finally { await StageBindingFinish(fixture); }
            }
        });
    }

    private static WsabiWmiSevenStageCoordinator StageBindingPlan(CooperativeTestGate gate,
        WsabiWmiProtectionBoundStage[] stages, TimeSpan? display = null)
        => WsabiWmiProtectionBindingPlan.Create(gate, stages, TimeSpan.FromMilliseconds(200), display ?? TimeSpan.FromSeconds(3));

    private static StageBindingNode[] StageBindingNodes(object procedure, object target, int pendingIndex = -1)
        => WsabiWmiProtectionTransitionReview.StageOrder.Select((role, index) =>
            new StageBindingNode(role, index, procedure, target, autoComplete: index != pendingIndex)).ToArray();

    private static WsabiWmiFrameExchangeResult StageBindingExchange(byte[] response)
        => new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived,
            WsabiWmiReplyResult.FromMethodReply(new WsabiWmiMethodReplyResult(WsabiWmiMethodReplyStatus.FrameChecked,
                WsabiWmiReplyDecoder.Decode(0, response))));

    private static async Task<WsabiWmiSevenStageOutcome> StageBindingOutcome(Task<WsabiWmiSevenStageOutcome> run)
    { await CooperativeAwait(run); return await run; }

    private static void StageBindingAssertPrefix(StageBindingFixture fixture, int count)
    { for (int index = 0; index < fixture.Nodes.Length; index++) Equal(index < count ? 1 : 0, fixture.Nodes[index].Calls); }

    private static async Task StageBindingAssertClosed(StageBindingFixture fixture)
    {
        await CooperativeAwait(fixture.Coordinator.ActualCompletion);
        Equal(WsabiWmiSevenStageCleanupStatus.Complete, await fixture.Coordinator.ActualCompletion);
        Check(fixture.Gate.LastLease != null && !fixture.Gate.LastLease.IsHeld, "bound close completed before lease release");
        Equal(1, fixture.Gate.LastLease.DisposeCalls); Equal(fixture.Gate.AcquireThread, fixture.Gate.LastLease.DisposeThread);
    }

    private static Task StageBindingFinish(StageBindingFixture fixture) => StageBindingFinish(fixture.Coordinator, fixture.Nodes);
    private static async Task StageBindingFinish(WsabiWmiSevenStageCoordinator coordinator, StageBindingNode[] nodes)
    {
        var close = coordinator.RequestCloseAsync();
        foreach (var node in nodes) await node.DetachAndConfirmForTest();
        await CooperativeAwait(close);
    }

    private sealed class StageBindingFixture
    {
        internal readonly object Procedure = new StageBindingPoisonIdentity(), Target = new StageBindingPoisonIdentity();
        internal readonly CooperativeTestGate Gate = new CooperativeTestGate();
        internal readonly StageBindingNode[] Nodes;
        internal readonly WsabiWmiProtectionBoundStage[] Stages;
        internal readonly WsabiWmiSevenStageCoordinator Coordinator;
        internal readonly List<WsabiWmiProtectionTransitionStage> Order = new List<WsabiWmiProtectionTransitionStage>();
        internal StageBindingFixture(int pendingIndex = -1, TimeSpan? display = null)
        {
            Nodes = StageBindingNodes(Procedure, Target, pendingIndex);
            foreach (var node in Nodes) node.Order = Order;
            Stages = Nodes.Select(node => node.Stage).ToArray(); Coordinator = StageBindingPlan(Gate, Stages, display);
        }
    }

    private sealed class StageBindingNode
    {
        internal readonly WsabiWmiProtectionTransitionStage Role;
        internal readonly WsabiWmiProtectionStageBinding Binding;
        internal readonly WsabiWmiProtectionBoundStage Stage;
        internal readonly byte[] ComparisonInput;
        private readonly byte[] responseComparison;
        internal readonly TaskCompletionSource<WsabiWmiProtectionBoundReply> Reply = new TaskCompletionSource<WsabiWmiProtectionBoundReply>(TaskCreationOptions.RunContinuationsAsynchronously);
        internal readonly TaskCompletionSource<bool> InvocationEnd = CooperativeCompletion(), Entered = CooperativeCompletion();
        internal readonly TaskCompletionSource<WsabiWmiBoundStageCleanupStatus> OutputClose = new TaskCompletionSource<WsabiWmiBoundStageCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
        internal readonly TaskCompletionSource<WsabiWmiBoundStageCleanupStatus> InputClose = new TaskCompletionSource<WsabiWmiBoundStageCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
        internal bool AutoComplete;
        internal Func<WsabiWmiSevenStageStopView, Task<WsabiWmiProtectionBoundReply>> Handler;
        internal Action<byte[]> RawChange;
        internal List<WsabiWmiProtectionTransitionStage> Order;
        private int calls;
        internal int Calls => Volatile.Read(ref calls);
        internal int CallThread;
        private bool invocationDetached, outputDetached, inputDetached;

        internal StageBindingNode(WsabiWmiProtectionTransitionStage role, int index, object procedure, object target,
            bool autoComplete = true, object[] resources = null, byte[] comparison = null)
        {
            Role = role; AutoComplete = autoComplete;
            var ids = resources ?? Enumerable.Range(0, 4).Select(item => (object)new StageBindingPoisonIdentity()).ToArray();
            Binding = new WsabiWmiProtectionStageBinding(role, procedure, target, ids[0], ids[1], ids[2], ids[3]);
            ComparisonInput = comparison == null ? new byte[] { (byte)(11 + index), 22, 33, 44, 55, 66, 77, 88 } : (byte[])comparison.Clone();
            responseComparison = (byte[])ComparisonInput.Clone();
            Stage = new WsabiWmiProtectionBoundStage(Binding, role == WsabiWmiProtectionTransitionStage.SemanticSet1 ? 1 : 173,
                91, ComparisonInput, Start, InvocationEnd.Task, OutputClose.Task, InputClose.Task);
        }
        private Task<WsabiWmiProtectionBoundReply> Start(WsabiWmiSevenStageStopView stop)
        {
            Interlocked.Increment(ref calls); CallThread = Thread.CurrentThread.ManagedThreadId; Order?.Add(Role); Entered.TrySetResult(true);
            if (Handler != null) return Handler(stop);
            if (AutoComplete) { SupplyReply(); Detach(); }
            return Reply.Task;
        }
        internal byte[] Raw()
        {
            var raw = new byte[21]; raw[4] = 0xaa;
            raw[7] = (byte)(Role == WsabiWmiProtectionTransitionStage.PreMode ? 0 : Role == WsabiWmiProtectionTransitionStage.PreUpper ? 44
                : Role == WsabiWmiProtectionTransitionStage.PreLower ? 33 : Role == WsabiWmiProtectionTransitionStage.PostUpper ? 80
                : Role == WsabiWmiProtectionTransitionStage.PostLower ? 75 : 1);
            raw[8] = 91; Array.Copy(responseComparison, 0, raw, 9, 8); RawChange?.Invoke(raw); return raw;
        }
        internal void SupplyReply() => Reply.TrySetResult(new WsabiWmiProtectionBoundReply(Binding, StageBindingExchange(Raw())));
        internal void CompleteComponent(int component)
        {
            if (component == 0) { invocationDetached = true; InvocationEnd.TrySetResult(true); }
            else if (component == 1) { outputDetached = true; OutputClose.TrySetResult(WsabiWmiBoundStageCleanupStatus.Complete); }
            else { inputDetached = true; InputClose.TrySetResult(WsabiWmiBoundStageCleanupStatus.Complete); }
        }
        internal void FailComponent(int component, int variant)
        {
            var error = new InvalidOperationException("Unreported fake cleanup failure.");
            if (component == 0) { if (variant == 0) InvocationEnd.TrySetException(error); else InvocationEnd.TrySetCanceled(); }
            else
            {
                var task = component == 1 ? OutputClose : InputClose;
                if (variant == 0) task.TrySetResult(WsabiWmiBoundStageCleanupStatus.Failed);
                else if (variant == 1) task.TrySetResult(WsabiWmiBoundStageCleanupStatus.Unknown);
                else if (variant == 2) task.TrySetException(error);
                else task.TrySetCanceled();
            }
        }
        internal void Detach() { CompleteComponent(0); CompleteComponent(1); CompleteComponent(2); }
        internal async Task DetachAndConfirmForTest()
        {
            Detach(); SupplyReply();
            try { await Task.WhenAll(InvocationEnd.Task, OutputClose.Task, InputClose.Task); } catch { }
            Check(invocationDetached && outputDetached && inputDetached, "test teardown has not detached every fake resource");
            // Failed promises remain failed. Only this explicitly detached fake
            // producer can supply new genuine-end evidence for test teardown.
            Stage.Operation.Lifetime.ConfirmActualClose();
        }
    }

    private sealed class StageBindingPoisonIdentity
    {
        public override bool Equals(object value) => throw new InvalidOperationException("Local binding identity must not call provider equality.");
        public override int GetHashCode() => throw new InvalidOperationException("Local binding identity must not call provider hashing.");
        public override string ToString() => throw new InvalidOperationException("Local binding identity must not call provider formatting.");
    }
}
