using System;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // All identities are local references, never device identifiers. These
    // bindings protect routing of supplied fake sources; they cannot verify
    // the physical target, frozen request, firmware execution or freshness.
    internal sealed class WsabiWmiProtectionStageBinding
    {
        internal WsabiWmiProtectionTransitionStage Role { get; }
        internal object Procedure { get; }
        internal object Target { get; }
        private readonly object[] resources;
        internal object[] Resources => (object[])resources.Clone();
        internal WsabiWmiProtectionStageBinding(WsabiWmiProtectionTransitionStage role,
            object procedure, object target, object source, object input, object observer, object capture)
        {
            if (!Enum.IsDefined(typeof(WsabiWmiProtectionTransitionStage), role)) throw new ArgumentOutOfRangeException(nameof(role));
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

    internal enum WsabiWmiBoundStageCleanupStatus { Complete, Failed, Unknown }
    internal enum WsabiWmiBoundStageReviewStatus { NotReviewed, MissingReply, BindingMismatch, ReadRejected, ReceiptRejected, ReadCandidate, ReceiptOnly }

    internal sealed class WsabiWmiProtectionBoundReply
    {
        internal WsabiWmiProtectionStageBinding Binding { get; }
        internal WsabiWmiFrameExchangeResult Exchange { get; }
        internal WsabiWmiProtectionBoundReply(WsabiWmiProtectionStageBinding binding, WsabiWmiFrameExchangeResult exchange)
        { Binding = binding ?? throw new ArgumentNullException(nameof(binding)); Exchange = exchange; }
    }

    // Prototype leaf: no source work/resources may exist before Start. The
    // three preprovided completion tasks are promises about work started there,
    // not evidence created by this adapter. A future SDK leaf must preserve
    // cleanup result statuses rather than erase failure into a completed Task.
    internal sealed class WsabiWmiProtectionBoundStage
    {
        private readonly Func<WsabiWmiSevenStageStopView, Task<WsabiWmiProtectionBoundReply>> start;
        private readonly Task invocationEnd;
        private readonly Task<WsabiWmiBoundStageCleanupStatus> outputClose, inputClose;
        private readonly WsabiWmiProtectionReadReplyReview readReview;
        private readonly WsabiWmiProtectionSetterReplyReview setterReview;
        private readonly byte[] comparison;
        private int started, reviewStatus;
        internal WsabiWmiProtectionStageBinding Binding { get; }
        internal WsabiWmiSevenStageOperation Operation { get; }
        internal WsabiWmiBoundStageReviewStatus ReviewStatus => (WsabiWmiBoundStageReviewStatus)Volatile.Read(ref reviewStatus);
        internal bool IsExecutable => false;
        internal bool IsHardwareObservation => false;
        internal bool IsFreshnessProven => false;
        internal bool IsSetterExecutionConfirmed => false;
        internal bool CanWriteHardware => false;

        internal WsabiWmiProtectionBoundStage(WsabiWmiProtectionStageBinding binding,
            int inputFirstComponent, int preservedSecondComponent, object comparisonContent,
            Func<WsabiWmiSevenStageStopView, Task<WsabiWmiProtectionBoundReply>> start,
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
            if (binding.Role == WsabiWmiProtectionTransitionStage.SemanticSet1)
                setterReview = new WsabiWmiProtectionSetterReplyReview(inputFirstComponent, preservedSecondComponent, comparison);
            else readReview = new WsabiWmiProtectionReadReplyReview(binding.Role, inputFirstComponent, preservedSecondComponent, comparison);
            var identities = binding.Resources;
            // Claim the shared procedure once, through its unique first role.
            bool firstRole = binding.Role == WsabiWmiProtectionTransitionStage.PreMode;
            var claimed = new object[identities.Length + (firstRole ? 2 : 1)]; claimed[0] = binding;
            Array.Copy(identities, 0, claimed, 1, identities.Length);
            if (firstRole) claimed[claimed.Length - 1] = binding.Procedure;
            Operation = new WsabiWmiSevenStageOperation(binding.Role, Start,
                new WsabiWmiSevenStageLifetime(), claimed);
        }

        internal bool SharesComparison(WsabiWmiProtectionBoundStage other)
        {
            int difference = 0;
            for (int i = 0; i < comparison.Length; i++) difference |= comparison[i] ^ other.comparison[i];
            return difference == 0;
        }

        private Task<WsabiWmiProtectionTransitionObservation> Start(WsabiWmiSevenStageStopView stop)
        {
            if (Interlocked.CompareExchange(ref started, 1, 0) != 0) throw new InvalidOperationException("The bound leaf is single-use.");
            Task<WsabiWmiProtectionBoundReply> pending;
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

        private async Task<WsabiWmiProtectionTransitionObservation> ReviewAsync(Task<WsabiWmiProtectionBoundReply> pending)
        {
            var reply = await pending.ConfigureAwait(false);
            if (reply == null) return Reject(WsabiWmiBoundStageReviewStatus.MissingReply);
            if (!ReferenceEquals(reply.Binding, Binding)) return Reject(WsabiWmiBoundStageReviewStatus.BindingMismatch);
            if (setterReview != null)
            {
                var result = setterReview.Evaluate(reply.Exchange);
                if (!result.IsReceiptOnly) return Reject(WsabiWmiBoundStageReviewStatus.ReceiptRejected);
                Volatile.Write(ref reviewStatus, (int)WsabiWmiBoundStageReviewStatus.ReceiptOnly);
                return new WsabiWmiProtectionTransitionObservation(Binding.Role,
                    WsabiWmiProtectionTransitionEvidence.SetterReceiptAcceptedForReadback);
            }
            var read = readReview.Evaluate(reply.Exchange);
            if (!read.IsCorrelatedStoredByteCandidate) return Reject(WsabiWmiBoundStageReviewStatus.ReadRejected);
            Volatile.Write(ref reviewStatus, (int)WsabiWmiBoundStageReviewStatus.ReadCandidate);
            return new WsabiWmiProtectionTransitionObservation(Binding.Role,
                WsabiWmiProtectionTransitionEvidence.BoundReadCandidate, read.Candidate);
        }

        private WsabiWmiProtectionTransitionObservation Reject(WsabiWmiBoundStageReviewStatus status)
        {
            Volatile.Write(ref reviewStatus, (int)status);
            return new WsabiWmiProtectionTransitionObservation(Binding.Role, WsabiWmiProtectionTransitionEvidence.Rejected);
        }
    }

    internal static class WsabiWmiProtectionBindingPlan
    {
        internal static WsabiWmiSevenStageCoordinator Create(IWsabiWmiExchangeGate gate,
            WsabiWmiProtectionBoundStage[] stages, TimeSpan acquireTimeout, TimeSpan displayTimeout)
        {
            if (stages == null || stages.Length != 7) throw new ArgumentException("Exactly seven bound stages are required.", nameof(stages));
            stages = (WsabiWmiProtectionBoundStage[])stages.Clone();
            var operations = new WsabiWmiSevenStageOperation[7];
            for (int i = 0; i < stages.Length; i++)
            {
                var stage = stages[i];
                if (stage == null || stage.Binding.Role != WsabiWmiProtectionTransitionReview.StageOrder[i])
                    throw new ArgumentException("The fixed role order is required.", nameof(stages));
                if (!ReferenceEquals(stage.Binding.Procedure, stages[0].Binding.Procedure) ||
                    !ReferenceEquals(stage.Binding.Target, stages[0].Binding.Target))
                    throw new ArgumentException("A procedure must retain the same target identity.", nameof(stages));
                for (int j = 0; j < i; j++)
                    if (stage.SharesComparison(stages[j])) throw new ArgumentException("Stage comparison tuples must differ.", nameof(stages));
                operations[i] = stage.Operation;
            }
            return new WsabiWmiSevenStageCoordinator(gate, operations, acquireTimeout, displayTimeout);
        }
    }
}
