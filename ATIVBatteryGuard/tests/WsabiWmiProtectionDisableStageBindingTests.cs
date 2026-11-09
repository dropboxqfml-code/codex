using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    // Supplied detached synthetic replies and explicitly ended fake resources.
    // No SDK, request construction, reservation or real device is used here.
    private static void RegisterWsabiWmiProtectionDisableStageBindingTests()
    {
        AddAsync("disable binding keeps three exact roles one owner and receipt separate from two read candidates", async () =>
        {
            var fixture = new DisableBindingFixture();
            fixture.Stages[0] = null;
            foreach (var node in fixture.Nodes) Array.Clear(node.Comparison, 0, node.Comparison.Length);
            try
            {
                var result = await DisableBindingOutcome(fixture.Coordinator.RunAsync());
                DisableBindingAssert(result, WsabiWmiThreeStageStatus.StoredReadbackMatchedCandidate, 3);
                Equal<int?>(1, result.Snapshot.ObservedPreModeByte); Equal<int?>(0, result.Snapshot.ObservedPostModeByte);
                Equal(2, result.Snapshot.BoundReadCandidateCount);
                Check(result.Snapshot.SetterReceiptAccepted && !result.Snapshot.SetterAcknowledged, "receipt became an independent setter acknowledgement");
                Check(fixture.Order.SequenceEqual(WsabiWmiProtectionDisableReview.StageOrder), "disable bound role order changed");
                Check(fixture.Nodes.All(node => node.Calls == 1 && node.Thread == fixture.Gate.AcquireThread), "bound role escaped the one owner or retried");
                Check(fixture.Nodes.All(node => !node.Stage.IsExecutable && !node.Stage.IsHardwareObservation &&
                    !node.Stage.IsFreshnessProven && !node.Stage.IsSetterExecutionConfirmed && !node.Stage.CanWriteHardware),
                    "bound report granted physical evidence or authority");
                await DisableBindingClosed(fixture); Equal(1, fixture.Gate.Calls);
            }
            finally { await DisableBindingFinish(fixture); }
        });

        Add("disable binding requires distinct local identities without provider equality or formatting", () =>
        {
            var procedure = new DisableBindingIdentity(); var target = new DisableBindingIdentity();
            var ids = Enumerable.Range(0, 4).Select(index => (object)new DisableBindingIdentity()).ToArray();
            var binding = new WsabiWmiProtectionDisableStageBinding(WsabiWmiProtectionDisableStage.PreMode,
                procedure, target, ids[0], ids[1], ids[2], ids[3]);
            binding.Resources[0] = new object(); Check(ReferenceEquals(ids[0], binding.Resources[0]), "binding leaked mutable identities");
            BatteryThrows<ArgumentOutOfRangeException>(() => new WsabiWmiProtectionDisableStageBinding((WsabiWmiProtectionDisableStage)3,
                procedure, target, ids[0], ids[1], ids[2], ids[3]));
            BatteryThrows<ArgumentException>(() => new WsabiWmiProtectionDisableStageBinding(WsabiWmiProtectionDisableStage.PreMode,
                procedure, procedure, ids[0], ids[1], ids[2], ids[3]));
            BatteryThrows<ArgumentException>(() => new WsabiWmiProtectionDisableStageBinding(WsabiWmiProtectionDisableStage.PreMode,
                procedure, target, ids[0], ids[0], ids[2], ids[3]));
            BatteryThrows<ArgumentException>(() => new WsabiWmiProtectionDisableStageBinding(WsabiWmiProtectionDisableStage.PreMode,
                procedure, target, procedure, ids[1], ids[2], ids[3]));
            BatteryThrows<ArgumentException>(() => new WsabiWmiProtectionDisableStageBinding(WsabiWmiProtectionDisableStage.PreMode,
                procedure, target, ids[0], null, ids[2], ids[3]));
        });

        Add("disable plan rejects wrong lengths roles targets procedures comparisons and shared resources before owner entry", () =>
        {
            for (int variant = 0; variant < 6; variant++)
            {
                var procedure = new DisableBindingIdentity(); var target = new DisableBindingIdentity();
                var nodes = DisableBindingNodes(procedure, target);
                if (variant == 0) nodes = nodes.Take(2).ToArray();
                else if (variant == 1) { var first = nodes[0]; nodes[0] = nodes[1]; nodes[1] = first; }
                else nodes[2] = new DisableBindingNode(WsabiWmiProtectionDisableStage.PostMode, 2,
                    variant == 2 ? new DisableBindingIdentity() : procedure,
                    variant == 3 ? new DisableBindingIdentity() : target,
                    comparison: variant == 4 ? nodes[0].Comparison : null,
                    identities: variant == 5 ? nodes[0].Binding.Resources : null);
                var gate = new CooperativeTestGate();
                BatteryThrows<ArgumentException>(() => DisableBindingPlan(gate, nodes.Select(node => node.Stage).ToArray()));
                Equal(0, gate.Calls); Check(nodes.All(node => node.Calls == 0), "invalid fixed plan started work");
            }
            var valid = DisableBindingNodes(new DisableBindingIdentity(), new DisableBindingIdentity()).Select(node => node.Stage).ToArray();
            BatteryThrows<ArgumentOutOfRangeException>(() => WsabiWmiProtectionDisableBindingPlan.Create(new CooperativeTestGate(), valid, TimeSpan.Zero, TimeSpan.FromSeconds(3)));
            BatteryThrows<ArgumentOutOfRangeException>(() => WsabiWmiProtectionDisableBindingPlan.Create(new CooperativeTestGate(), valid, TimeSpan.FromMilliseconds(200), TimeSpan.Zero));
            BatteryThrows<ArgumentOutOfRangeException>(() => WsabiWmiProtectionDisableBindingPlan.Create(new CooperativeTestGate(), valid, TimeSpan.FromSeconds(3), TimeSpan.FromSeconds(3)));
        });

        AddAsync("disable bound responses from another role or binding are rejected before every later role", async () =>
        {
            foreach (int index in new[] { 0, 1, 2 })
            {
                var fixture = new DisableBindingFixture(); var node = fixture.Nodes[index];
                node.Handler = stop =>
                {
                    var other = new DisableBindingNode(node.Role, index, fixture.Procedure, fixture.Target);
                    node.Detach();
                    return Task.FromResult(new WsabiWmiProtectionDisableBoundReply(other.Binding, DisableBindingExchange(node.Raw())));
                };
                try
                {
                    DisableBindingAssert(await DisableBindingOutcome(fixture.Coordinator.RunAsync()), WsabiWmiThreeStageStatus.StageRejected, index + 1);
                    Equal(WsabiWmiBoundStageReviewStatus.BindingMismatch, node.Stage.ReviewStatus);
                    DisableBindingPrefix(fixture, index + 1); await DisableBindingClosed(fixture);
                }
                finally { await DisableBindingFinish(fixture); }
            }
        });

        AddAsync("disable bound pre receipt and post each require invocation output and input completion independently", async () =>
        {
            foreach (int index in new[] { 0, 1, 2 })
            for (int component = 0; component < 3; component++)
            {
                var fixture = new DisableBindingFixture(index); var node = fixture.Nodes[index];
                var run = fixture.Coordinator.RunAsync();
                try
                {
                    await CooperativeAwait(node.Entered.Task); node.SupplyReply();
                    for (int other = 0; other < 3; other++) if (other != component) node.Complete(other);
                    await InvocationEventually(() => node.Stage.ReviewStatus == (index == 1
                        ? WsabiWmiBoundStageReviewStatus.ReceiptOnly : WsabiWmiBoundStageReviewStatus.ReadCandidate));
                    Check(!node.Stage.Operation.Lifetime.ActualClose.IsCompleted && fixture.Gate.LastLease.IsHeld,
                        "a pending close promise was dropped after detached reply review");
                    DisableBindingPrefix(fixture, index + 1);
                    var close = fixture.Coordinator.RequestCloseAsync();
                    DisableBindingAssert(await DisableBindingOutcome(run), WsabiWmiThreeStageStatus.Cancelled, index + 1);
                    Check(!close.IsCompleted, "stop bypassed a remaining related-close component");
                    node.Detach(); await DisableBindingClosed(fixture); DisableBindingPrefix(fixture, index + 1);
                }
                finally { await DisableBindingFinish(fixture); }
            }
        });

        AddAsync("disable bound direct throw or null task retains unknown ownership until related resources end", async () =>
        {
            foreach (int index in new[] { 0, 1 })
            foreach (bool throws in new[] { false, true })
            {
                var fixture = new DisableBindingFixture(index); var node = fixture.Nodes[index];
                node.Handler = stop => { if (throws) throw new InvalidOperationException("Unreported fake dispatch detail."); return null; };
                try
                {
                    DisableBindingAssert(await DisableBindingOutcome(fixture.Coordinator.RunAsync()), WsabiWmiThreeStageStatus.CompletionUnknown, index + 1);
                    Check(fixture.Gate.LastLease.IsHeld && !fixture.Coordinator.ActualCompletion.IsCompleted,
                        "untracked start manufactured actual termination");
                    node.Detach(); await DisableBindingClosed(fixture); DisableBindingPrefix(fixture, index + 1);
                }
                finally { await DisableBindingFinish(fixture); }
            }
        });

        AddAsync("disable procedure and bound resource identities cannot be rewrapped after one use", async () =>
        {
            var fixture = new DisableBindingFixture();
            try
            {
                await DisableBindingOutcome(fixture.Coordinator.RunAsync()); await DisableBindingClosed(fixture);
                var gate = new CooperativeTestGate();
                var fresh = DisableBindingNodes(fixture.Procedure, fixture.Target);
                var peer = DisableBindingPlan(gate, fresh.Select(node => node.Stage).ToArray());
                DisableBindingAssert(await DisableBindingOutcome(peer.RunAsync()), WsabiWmiThreeStageStatus.AlreadyUsed, 0);
                await CooperativeAwait(peer.RequestCloseAsync()); Equal(0, gate.Calls);
                Check(fresh.All(node => node.Calls == 0), "procedure rewrap restarted consumed work");
            }
            finally { await DisableBindingFinish(fixture); }
        });
    }

    private static WsabiWmiThreeStageCoordinator DisableBindingPlan(CooperativeTestGate gate,
        WsabiWmiProtectionDisableBoundStage[] stages)
        => WsabiWmiProtectionDisableBindingPlan.Create(gate, stages, TimeSpan.FromMilliseconds(200), TimeSpan.FromSeconds(3));
    private static DisableBindingNode[] DisableBindingNodes(object procedure, object target, int pendingIndex = -1)
        => WsabiWmiProtectionDisableReview.StageOrder.Select((role, index) => new DisableBindingNode(role, index, procedure, target,
            auto: index != pendingIndex)).ToArray();
    private static WsabiWmiFrameExchangeResult DisableBindingExchange(byte[] raw)
        => new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived,
            WsabiWmiReplyResult.FromMethodReply(new WsabiWmiMethodReplyResult(WsabiWmiMethodReplyStatus.FrameChecked,
                WsabiWmiReplyDecoder.Decode(0, raw))));
    private static async Task<WsabiWmiThreeStageOutcome> DisableBindingOutcome(Task<WsabiWmiThreeStageOutcome> result)
    { await CooperativeAwait(result); return await result; }
    private static void DisableBindingAssert(WsabiWmiThreeStageOutcome result, WsabiWmiThreeStageStatus status, int stages)
    {
        Equal(status, result.Status); Equal(stages, result.StartedStages);
        Check(!result.IsExecutable && !result.CanInvokeMethods && !result.CanReadHardware && !result.CanWriteHardware &&
            !result.Snapshot.IsHardwareObservation && !result.Snapshot.IsChargeLimitConfirmed, "fake binding became hardware authority");
    }
    private static void DisableBindingPrefix(DisableBindingFixture fixture, int count)
    { for (int index = 0; index < fixture.Nodes.Length; index++) Equal(index < count ? 1 : 0, fixture.Nodes[index].Calls); }
    private static async Task DisableBindingClosed(DisableBindingFixture fixture)
    {
        await CooperativeAwait(fixture.Coordinator.ActualCompletion);
        Check(fixture.Gate.LastLease != null && !fixture.Gate.LastLease.IsHeld, "completion preceded owner release");
        Equal(1, fixture.Gate.LastLease.DisposeCalls); Equal(fixture.Gate.AcquireThread, fixture.Gate.LastLease.DisposeThread);
    }
    private static async Task DisableBindingFinish(DisableBindingFixture fixture)
    {
        var close = fixture.Coordinator.RequestCloseAsync();
        foreach (var node in fixture.Nodes) { node.Detach(); node.SupplyReply(); }
        await CooperativeAwait(close);
    }

    private sealed class DisableBindingFixture
    {
        internal readonly object Procedure = new DisableBindingIdentity(), Target = new DisableBindingIdentity();
        internal readonly CooperativeTestGate Gate = new CooperativeTestGate();
        internal readonly List<WsabiWmiProtectionDisableStage> Order = new List<WsabiWmiProtectionDisableStage>();
        internal readonly DisableBindingNode[] Nodes;
        internal readonly WsabiWmiProtectionDisableBoundStage[] Stages;
        internal readonly WsabiWmiThreeStageCoordinator Coordinator;
        internal DisableBindingFixture(int pendingIndex = -1)
        {
            Nodes = DisableBindingNodes(Procedure, Target, pendingIndex);
            foreach (var node in Nodes) node.Order = Order;
            Stages = Nodes.Select(node => node.Stage).ToArray(); Coordinator = DisableBindingPlan(Gate, Stages);
        }
    }
    private sealed class DisableBindingNode
    {
        internal readonly WsabiWmiProtectionDisableStage Role;
        internal readonly WsabiWmiProtectionDisableStageBinding Binding;
        internal readonly WsabiWmiProtectionDisableBoundStage Stage;
        internal readonly byte[] Comparison;
        private readonly byte[] responseComparison;
        internal readonly TaskCompletionSource<WsabiWmiProtectionDisableBoundReply> Reply = new TaskCompletionSource<WsabiWmiProtectionDisableBoundReply>(TaskCreationOptions.RunContinuationsAsynchronously);
        internal readonly TaskCompletionSource<bool> Entered = CooperativeCompletion(), InvocationEnd = CooperativeCompletion();
        internal readonly TaskCompletionSource<WsabiWmiBoundStageCleanupStatus> OutputClose = NewCleanup(), InputClose = NewCleanup();
        internal List<WsabiWmiProtectionDisableStage> Order;
        internal Func<WsabiWmiThreeStageStopView, Task<WsabiWmiProtectionDisableBoundReply>> Handler;
        private readonly bool auto;
        private int calls;
        internal int Calls => Volatile.Read(ref calls);
        internal int Thread;
        internal DisableBindingNode(WsabiWmiProtectionDisableStage role, int index, object procedure, object target,
            bool auto = true, byte[] comparison = null, object[] identities = null)
        {
            Role = role; this.auto = auto;
            var ids = identities ?? Enumerable.Range(0, 4).Select(item => (object)new DisableBindingIdentity()).ToArray();
            Binding = new WsabiWmiProtectionDisableStageBinding(role, procedure, target, ids[0], ids[1], ids[2], ids[3]);
            Comparison = comparison == null ? new byte[] { (byte)(11 + index), 22, 33, 44, 55, 66, 77, 88 } : (byte[])comparison.Clone();
            responseComparison = (byte[])Comparison.Clone();
            Stage = new WsabiWmiProtectionDisableBoundStage(Binding, role == WsabiWmiProtectionDisableStage.SemanticSet0 ? 0 : 173,
                91, Comparison, Start, InvocationEnd.Task, OutputClose.Task, InputClose.Task);
        }
        private Task<WsabiWmiProtectionDisableBoundReply> Start(WsabiWmiThreeStageStopView stop)
        {
            Interlocked.Increment(ref calls); Thread = System.Threading.Thread.CurrentThread.ManagedThreadId; Order?.Add(Role); Entered.TrySetResult(true);
            if (Handler != null) return Handler(stop);
            if (auto) { SupplyReply(); Detach(); }
            return Reply.Task;
        }
        internal byte[] Raw()
        {
            var raw = new byte[21]; raw[4] = 0xaa; raw[7] = Role == WsabiWmiProtectionDisableStage.PreMode ? (byte)1 : (byte)0;
            raw[8] = 91; Array.Copy(responseComparison, 0, raw, 9, 8); return raw;
        }
        internal void SupplyReply() => Reply.TrySetResult(new WsabiWmiProtectionDisableBoundReply(Binding, DisableBindingExchange(Raw())));
        internal void Complete(int component)
        {
            if (component == 0) InvocationEnd.TrySetResult(true);
            else (component == 1 ? OutputClose : InputClose).TrySetResult(WsabiWmiBoundStageCleanupStatus.Complete);
        }
        internal void Detach() { Complete(0); Complete(1); Complete(2); }
        private static TaskCompletionSource<WsabiWmiBoundStageCleanupStatus> NewCleanup()
            => new TaskCompletionSource<WsabiWmiBoundStageCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
    }
    private sealed class DisableBindingIdentity
    {
        public override bool Equals(object value) => throw new InvalidOperationException("Provider identity equality must not run.");
        public override int GetHashCode() => throw new InvalidOperationException("Provider identity hashing must not run.");
        public override string ToString() => throw new InvalidOperationException("Provider identity formatting must not run.");
    }
}
