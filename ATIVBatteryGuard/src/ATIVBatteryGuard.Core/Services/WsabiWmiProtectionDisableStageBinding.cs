using System;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // All identities are local references, never device identifiers. These
    // bindings protect routing of supplied sources; they cannot verify
    // the physical target, frozen request, firmware execution or freshness.
    internal sealed class WsabiWmiProtectionDisableStageBinding
    {
        internal WsabiWmiProtectionDisableStage Role { get; }
        internal object Procedure { get; }
        internal object Target { get; }
        private readonly object[] resources;
        internal object[] Resources => (object[])resources.Clone();
        internal WsabiWmiProtectionDisableStageBinding(WsabiWmiProtectionDisableStage role,
            object procedure, object target, object source, object input, object observer, object capture)
        {
            if (!Enum.IsDefined(typeof(WsabiWmiProtectionDisableStage), role)) throw new ArgumentOutOfRangeException(nameof(role));
            Procedure = procedure ?? throw new ArgumentNullException(nameof(procedure));
            Target = target ?? throw new ArgumentNullException(nameof(target));
            if (ReferenceEquals(procedure, target)) throw new ArgumentException("Procedure and target identities must differ.");
            resources = new[] { source, input, observer, capture };
            for (int i = 0; i < resources.Length; i++)
            {
                if (resources[i] == null) throw new ArgumentException("Every stage resource identity is required.");
                if (ReferenceEquals(resources[i], procedure) || ReferenceEquals(resources[i], target))
                    throw new ArgumentException("Stage resources cannot alias the procedure or target.");
                for (int j = 0; j < i; j++)
                    if (ReferenceEquals(resources[i], resources[j])) throw new ArgumentException("Stage resources must differ.");
            }
            Role = role;
        }
    }
    internal sealed class WsabiWmiProtectionDisableBoundReply
    {
        internal WsabiWmiProtectionDisableStageBinding Binding { get; }
        internal WsabiWmiFrameExchangeResult Exchange { get; }
        internal WsabiWmiProtectionDisableBoundReply(WsabiWmiProtectionDisableStageBinding binding, WsabiWmiFrameExchangeResult exchange)
        { Binding = binding ?? throw new ArgumentNullException(nameof(binding)); Exchange = exchange; }
    }

    // Fixed disable leaf: no source work/resources may exist before Start. The
    // three preprovided completion tasks are promises about work started there,
    // not evidence created by this adapter. The SDK leaf must preserve
    // cleanup result statuses rather than erase failure into a completed Task.
    internal sealed class WsabiWmiProtectionDisableBoundStage
    {
        private readonly Func<WsabiWmiThreeStageStopView, Task<WsabiWmiProtectionDisableBoundReply>> start;
        private readonly Task invocationEnd;
        private readonly Task<WsabiWmiBoundStageCleanupStatus> outputClose, inputClose;
        private readonly WsabiWmiProtectionReadReplyReview readReview;
        private readonly WsabiWmiProtectionDisableSetterReplyReview setterReview;
        private readonly byte[] comparison;
        private int started, reviewStatus;
        private int readReplyStatus = -1, setterReplyStatus = -1;
        internal WsabiWmiProtectionDisableStageBinding Binding { get; }
        internal WsabiWmiThreeStageOperation Operation { get; }
        internal WsabiWmiBoundStageReviewStatus ReviewStatus => (WsabiWmiBoundStageReviewStatus)Volatile.Read(ref reviewStatus);
        internal string ReadVerdict => Volatile.Read(ref readReplyStatus) < 0 ? "NotReviewed"
            : ((WsabiWmiProtectionReadReplyReviewStatus)Volatile.Read(ref readReplyStatus)).ToString();
        internal string SetterVerdict => Volatile.Read(ref setterReplyStatus) < 0 ? "NotReviewed"
            : ((WsabiWmiProtectionDisableSetterReplyReviewStatus)Volatile.Read(ref setterReplyStatus)).ToString();
        internal bool IsExecutable => false;
        internal bool IsHardwareObservation => false;
        internal bool IsFreshnessProven => false;
        internal bool IsSetterExecutionConfirmed => false;
        internal bool CanWriteHardware => false;

        internal WsabiWmiProtectionDisableBoundStage(WsabiWmiProtectionDisableStageBinding binding,
            int inputFirstComponent, int preservedSecondComponent, object comparisonContent,
            Func<WsabiWmiThreeStageStopView, Task<WsabiWmiProtectionDisableBoundReply>> start,
            Task invocationEnd, Task<WsabiWmiBoundStageCleanupStatus> outputClose,
            Task<WsabiWmiBoundStageCleanupStatus> inputClose)
        {
            Binding = binding ?? throw new ArgumentNullException(nameof(binding));
            this.start = start ?? throw new ArgumentNullException(nameof(start));
            this.invocationEnd = invocationEnd ?? throw new ArgumentNullException(nameof(invocationEnd));
            this.outputClose = outputClose ?? throw new ArgumentNullException(nameof(outputClose));
            this.inputClose = inputClose ?? throw new ArgumentNullException(nameof(inputClose));
            // Snapshot once before giving independent owned copies to reviews.
            if (comparisonContent == null || comparisonContent.GetType() != typeof(byte[]))
                throw new ArgumentException("An ordinary comparison array is required.", nameof(comparisonContent));
            comparison = (byte[])((byte[])comparisonContent).Clone();
            if (binding.Role == WsabiWmiProtectionDisableStage.SemanticSet0)
                setterReview = new WsabiWmiProtectionDisableSetterReplyReview(inputFirstComponent, preservedSecondComponent, comparison);
            else readReview = new WsabiWmiProtectionReadReplyReview(
                binding.Role == WsabiWmiProtectionDisableStage.PreMode ? WsabiWmiProtectionTransitionStage.PreMode
                    : WsabiWmiProtectionTransitionStage.PostMode,
                inputFirstComponent, preservedSecondComponent, comparison);
            var identities = binding.Resources;
            // Claim the shared procedure once, through its unique first role.
            bool firstRole = binding.Role == WsabiWmiProtectionDisableStage.PreMode;
            var claimed = new object[identities.Length + (firstRole ? 2 : 1)]; claimed[0] = binding;
            Array.Copy(identities, 0, claimed, 1, identities.Length);
            if (firstRole) claimed[claimed.Length - 1] = binding.Procedure;
            Operation = new WsabiWmiThreeStageOperation(binding.Role, Start,
                new WsabiWmiThreeStageLifetime(), claimed);
        }

        internal bool SharesComparison(WsabiWmiProtectionDisableBoundStage other)
        {
            int difference = 0;
            for (int i = 0; i < comparison.Length; i++) difference |= comparison[i] ^ other.comparison[i];
            return difference == 0;
        }

        private Task<WsabiWmiProtectionDisableObservation> Start(WsabiWmiThreeStageStopView stop)
        {
            if (Interlocked.CompareExchange(ref started, 1, 0) != 0) throw new InvalidOperationException("The bound leaf is single-use.");
            Task<WsabiWmiProtectionDisableBoundReply> pending;
            // Invoke directly on the owner thread. Do not hide direct throw or
            // null-task uncertainty inside an async state machine.
            try { pending = start(stop); }
            finally { _ = ObserveCloseAsync(); }
            return pending == null ? null : ReviewAsync(pending);
        }

        private async Task ObserveCloseAsync()
        {
            _ = ObserveInvocationFailureAsync();
            _ = ObserveCleanupFailureAsync(outputClose);
            _ = ObserveCleanupFailureAsync(inputClose);
            try
            {
                await Task.WhenAll(invocationEnd, outputClose, inputClose).ConfigureAwait(false);
                if (await outputClose.ConfigureAwait(false) != WsabiWmiBoundStageCleanupStatus.Complete ||
                    await inputClose.ConfigureAwait(false) != WsabiWmiBoundStageCleanupStatus.Complete)
                { Operation.Lifetime.ReportUncertainClose(); return; }
                Operation.Lifetime.ConfirmActualClose();
            }
            catch { Operation.Lifetime.ReportUncertainClose(); }
        }

        private async Task ObserveInvocationFailureAsync()
        {
            try { await invocationEnd.ConfigureAwait(false); }
            catch { Operation.Lifetime.ReportUncertainClose(); }
        }

        private async Task ObserveCleanupFailureAsync(Task<WsabiWmiBoundStageCleanupStatus> cleanup)
        {
            try
            {
                if (await cleanup.ConfigureAwait(false) != WsabiWmiBoundStageCleanupStatus.Complete)
                    Operation.Lifetime.ReportUncertainClose();
            }
            catch { Operation.Lifetime.ReportUncertainClose(); }
        }

        private async Task<WsabiWmiProtectionDisableObservation> ReviewAsync(Task<WsabiWmiProtectionDisableBoundReply> pending)
        {
            var reply = await pending.ConfigureAwait(false);
            if (reply == null) return Reject(WsabiWmiBoundStageReviewStatus.MissingReply);
            if (!ReferenceEquals(reply.Binding, Binding)) return Reject(WsabiWmiBoundStageReviewStatus.BindingMismatch);
            if (setterReview != null)
            {
                var result = setterReview.Evaluate(reply.Exchange);
                Volatile.Write(ref setterReplyStatus, (int)result.Status);
                if (!result.IsReceiptOnly) return Reject(WsabiWmiBoundStageReviewStatus.ReceiptRejected);
                Volatile.Write(ref reviewStatus, (int)WsabiWmiBoundStageReviewStatus.ReceiptOnly);
                return new WsabiWmiProtectionDisableObservation(Binding.Role,
                    WsabiWmiProtectionDisableEvidence.SetterReceiptAcceptedForReadback);
            }
            var read = readReview.Evaluate(reply.Exchange);
            Volatile.Write(ref readReplyStatus, (int)read.Status);
            if (!read.IsCorrelatedStoredByteCandidate) return Reject(WsabiWmiBoundStageReviewStatus.ReadRejected);
            Volatile.Write(ref reviewStatus, (int)WsabiWmiBoundStageReviewStatus.ReadCandidate);
            return new WsabiWmiProtectionDisableObservation(Binding.Role,
                WsabiWmiProtectionDisableEvidence.BoundReadCandidate, read.Candidate);
        }

        private WsabiWmiProtectionDisableObservation Reject(WsabiWmiBoundStageReviewStatus status)
        {
            Volatile.Write(ref reviewStatus, (int)status);
            return new WsabiWmiProtectionDisableObservation(Binding.Role, WsabiWmiProtectionDisableEvidence.Rejected);
        }
    }

    internal static class WsabiWmiProtectionDisableBindingPlan
    {
        internal static WsabiWmiThreeStageCoordinator Create(IWsabiWmiExchangeGate gate,
            WsabiWmiProtectionDisableBoundStage[] stages, TimeSpan acquireTimeout, TimeSpan displayTimeout)
        {
            if (stages == null || stages.Length != 3) throw new ArgumentException("Exactly three bound stages are required.", nameof(stages));
            stages = (WsabiWmiProtectionDisableBoundStage[])stages.Clone();
            var operations = new WsabiWmiThreeStageOperation[3];
            for (int i = 0; i < stages.Length; i++)
            {
                var stage = stages[i];
                if (stage == null || stage.Binding.Role != WsabiWmiProtectionDisableReview.StageOrder[i])
                    throw new ArgumentException("The fixed role order is required.", nameof(stages));
                if (!ReferenceEquals(stage.Binding.Procedure, stages[0].Binding.Procedure) ||
                    !ReferenceEquals(stage.Binding.Target, stages[0].Binding.Target))
                    throw new ArgumentException("A procedure must retain the same target identity.", nameof(stages));
                for (int j = 0; j < i; j++)
                    if (stage.SharesComparison(stages[j])) throw new ArgumentException("Stage comparison tuples must differ.", nameof(stages));
                operations[i] = stage.Operation;
            }
            return new WsabiWmiThreeStageCoordinator(gate, operations, acquireTimeout, displayTimeout);
        }
    }
}
