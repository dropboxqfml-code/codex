using System;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // All identities are local references, never device identifiers. These
    // bindings protect routing of supplied sources; they cannot verify
    // the physical target, frozen request, firmware execution or freshness.
    internal sealed class ManualProtectionStageBinding
    {
        internal ManualProtectionRole Role { get; }
        internal ManualProtectionAttempt Attempt { get; }
        internal object Procedure => Attempt;
        internal object Target { get; }
        private readonly object[] resources;
        internal object[] Resources => (object[])resources.Clone();
        internal ManualProtectionStageBinding(ManualProtectionAttempt attempt, ManualProtectionRole role,
            object target, object source, object input, object observer, object capture)
        {
            if (!Enum.IsDefined(typeof(ManualProtectionRole), role)) throw new ArgumentOutOfRangeException(nameof(role));
            Attempt = attempt ?? throw new ArgumentNullException(nameof(attempt));
            attempt.GetIndex(role);
            object procedure = attempt;
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
    internal sealed class ManualProtectionBoundReply
    {
        internal ManualProtectionStageBinding Binding { get; }
        internal WsabiWmiFrameExchangeResult Exchange { get; }
        internal ManualProtectionBoundReply(ManualProtectionStageBinding binding, WsabiWmiFrameExchangeResult exchange)
        { Binding = binding ?? throw new ArgumentNullException(nameof(binding)); Exchange = exchange; }
    }

    // Fixed manual leaf: no source work/resources may exist before Start. The
    // three preprovided completion tasks are promises about work started there,
    // not evidence created by this adapter. The SDK leaf must preserve
    // cleanup result statuses rather than erase failure into a completed Task.
    internal sealed class ManualProtectionBoundStage
    {
        private readonly Func<WsabiWmiThreeStageStopView, Task<ManualProtectionBoundReply>> start;
        private readonly Task invocationEnd;
        private readonly Task<WsabiWmiBoundStageCleanupStatus> outputClose, inputClose;
        private readonly WsabiWmiProtectionReadReplyReview readReview;
        private readonly WsabiWmiProtectionDisableSetterReplyReview setterZeroReview;
        private readonly WsabiWmiProtectionSetterReplyReview setterOneReview;
        private readonly byte[] comparison;
        private int started, reviewStatus;
        private int readReplyStatus = -1, setterReplyStatus = -1;
        internal ManualProtectionStageBinding Binding { get; }
        internal ManualProtectionStageOperation Operation { get; }
        internal WsabiWmiBoundStageReviewStatus ReviewStatus => (WsabiWmiBoundStageReviewStatus)Volatile.Read(ref reviewStatus);
        internal string ReadVerdict => Volatile.Read(ref readReplyStatus) < 0 ? "NotReviewed"
            : ((WsabiWmiProtectionReadReplyReviewStatus)Volatile.Read(ref readReplyStatus)).ToString();
        internal string SetterVerdict => Volatile.Read(ref setterReplyStatus) < 0 ? "NotReviewed"
            : Binding.Attempt.Operation == ManualProtectionOperation.Enable80
                ? ((WsabiWmiProtectionSetterReplyReviewStatus)Volatile.Read(ref setterReplyStatus)).ToString()
                : ((WsabiWmiProtectionDisableSetterReplyReviewStatus)Volatile.Read(ref setterReplyStatus)).ToString();
        internal bool IsExecutable => false;
        internal bool IsHardwareObservation => false;
        internal bool IsFreshnessProven => false;
        internal bool IsSetterExecutionConfirmed => false;
        internal bool CanWriteHardware => false;

        internal ManualProtectionBoundStage(ManualProtectionStageBinding binding,
            int inputFirstComponent, int preservedSecondComponent, object comparisonContent,
            Func<WsabiWmiThreeStageStopView, Task<ManualProtectionBoundReply>> start,
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
            if (binding.Role == ManualProtectionRole.SemanticSet)
            {
                if (binding.Attempt.Operation == ManualProtectionOperation.Enable80)
                    setterOneReview = new WsabiWmiProtectionSetterReplyReview(inputFirstComponent, preservedSecondComponent, comparison);
                else setterZeroReview = new WsabiWmiProtectionDisableSetterReplyReview(inputFirstComponent, preservedSecondComponent, comparison);
            }
            else readReview = new WsabiWmiProtectionReadReplyReview(ReadRole(binding.Role),
                inputFirstComponent, preservedSecondComponent, comparison);
            var identities = binding.Resources;
            // Claim the shared procedure once, through its unique first role.
            bool firstRole = binding.Role == ManualProtectionRole.PreMode;
            var claimed = new object[identities.Length + (firstRole ? 2 : 1)]; claimed[0] = binding;
            Array.Copy(identities, 0, claimed, 1, identities.Length);
            if (firstRole) claimed[claimed.Length - 1] = binding.Procedure;
            Operation = new ManualProtectionStageOperation(binding.Role, Start,
                new WsabiWmiThreeStageLifetime(), claimed);
        }

        internal bool SharesComparison(ManualProtectionBoundStage other)
        {
            int difference = 0;
            for (int i = 0; i < comparison.Length; i++) difference |= comparison[i] ^ other.comparison[i];
            return difference == 0;
        }

        private Task<ManualProtectionObservation> Start(WsabiWmiThreeStageStopView stop)
        {
            if (Interlocked.CompareExchange(ref started, 1, 0) != 0) throw new InvalidOperationException("The bound leaf is single-use.");
            Task<ManualProtectionBoundReply> pending;
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

        private async Task<ManualProtectionObservation> ReviewAsync(Task<ManualProtectionBoundReply> pending)
        {
            var reply = await pending.ConfigureAwait(false);
            if (reply == null) return Reject(WsabiWmiBoundStageReviewStatus.MissingReply);
            if (!ReferenceEquals(reply.Binding, Binding)) return Reject(WsabiWmiBoundStageReviewStatus.BindingMismatch);
            if (setterOneReview != null || setterZeroReview != null)
            {
                bool accepted;
                if (setterOneReview != null)
                {
                    var result = setterOneReview.Evaluate(reply.Exchange);
                    Volatile.Write(ref setterReplyStatus, (int)result.Status); accepted = result.IsReceiptOnly;
                }
                else
                {
                    var result = setterZeroReview.Evaluate(reply.Exchange);
                    Volatile.Write(ref setterReplyStatus, (int)result.Status); accepted = result.IsReceiptOnly;
                }
                if (!accepted) return Reject(WsabiWmiBoundStageReviewStatus.ReceiptRejected);
                Volatile.Write(ref reviewStatus, (int)WsabiWmiBoundStageReviewStatus.ReceiptOnly);
                return new ManualProtectionObservation(Binding.Role, ManualProtectionEvidence.SetterReceipt);
            }
            var read = readReview.Evaluate(reply.Exchange);
            Volatile.Write(ref readReplyStatus, (int)read.Status);
            if (!read.IsCorrelatedStoredByteCandidate) return Reject(WsabiWmiBoundStageReviewStatus.ReadRejected);
            Volatile.Write(ref reviewStatus, (int)WsabiWmiBoundStageReviewStatus.ReadCandidate);
            return new ManualProtectionObservation(Binding.Role,
                ManualProtectionEvidence.ReadCandidate, read.Candidate);
        }

        private static WsabiWmiProtectionTransitionStage ReadRole(ManualProtectionRole role)
        {
            switch (role)
            {
                case ManualProtectionRole.PreMode: return WsabiWmiProtectionTransitionStage.PreMode;
                case ManualProtectionRole.PreUpper: return WsabiWmiProtectionTransitionStage.PreUpper;
                case ManualProtectionRole.PreLower: return WsabiWmiProtectionTransitionStage.PreLower;
                case ManualProtectionRole.PostMode: return WsabiWmiProtectionTransitionStage.PostMode;
                case ManualProtectionRole.PostUpper: return WsabiWmiProtectionTransitionStage.PostUpper;
                case ManualProtectionRole.PostLower: return WsabiWmiProtectionTransitionStage.PostLower;
                default: throw new ArgumentOutOfRangeException(nameof(role));
            }
        }

        private ManualProtectionObservation Reject(WsabiWmiBoundStageReviewStatus status)
        {
            Volatile.Write(ref reviewStatus, (int)status);
            return new ManualProtectionObservation(Binding.Role, ManualProtectionEvidence.Rejected);
        }
    }

    internal static class ManualProtectionBindingPlan
    {
        internal static ManualProtectionCoordinator Create(ManualProtectionAttempt attempt, IWsabiWmiExchangeGate gate,
            ManualProtectionBoundStage[] stages, TimeSpan acquireTimeout, TimeSpan displayTimeout)
        {
            if (attempt == null) throw new ArgumentNullException(nameof(attempt));
            if (stages == null || stages.Length != attempt.StageOrder.Count) throw new ArgumentException("The fixed manual stages are required.", nameof(stages));
            stages = (ManualProtectionBoundStage[])stages.Clone();
            var operations = new ManualProtectionStageOperation[stages.Length];
            for (int i = 0; i < stages.Length; i++)
            {
                var stage = stages[i];
                if (stage == null || stage.Binding.Role != attempt.StageOrder[i])
                    throw new ArgumentException("The fixed role order is required.", nameof(stages));
                if (!ReferenceEquals(stage.Binding.Attempt, attempt) || !ReferenceEquals(stage.Binding.Procedure, stages[0].Binding.Procedure) ||
                    !ReferenceEquals(stage.Binding.Target, stages[0].Binding.Target))
                    throw new ArgumentException("A procedure must retain the same target identity.", nameof(stages));
                for (int j = 0; j < i; j++)
                    if (stage.SharesComparison(stages[j])) throw new ArgumentException("Stage comparison tuples must differ.", nameof(stages));
                operations[i] = stage.Operation;
            }
            return new ManualProtectionCoordinator(attempt, gate, operations, acquireTimeout, displayTimeout);
        }
    }
}
