using System.Collections.Generic;

namespace ATIVBatteryGuard.Core.Services
{
    public enum WsabiWmiProtectionDisableStage { PreMode, SemanticSet0, PostMode }
    public enum WsabiWmiProtectionDisableEvidence
    { Unknown, HistoricalRead, Rejected, BoundReadCandidate, SetterReceiptAcceptedForReadback }
    public enum WsabiWmiProtectionDisableReviewStatus
    { AwaitingObservation, Stopped, StoredReadbackMatchedCandidate }
    public enum WsabiWmiProtectionDisableDecisionStatus
    {
        Advanced, StoredReadbackMatchedCandidate, MissingObservation, UnexpectedStage,
        HistoricalObservationNotAdmissible, ObservationRejected, ObservationUnknown,
        UnexpectedEvidence, InvalidByteValue, PreModeNotOne, AlreadyDisabledCandidate,
        PostModeMismatch, AlreadyTerminal
    }

    // Caller-normalized evidence categories only. No historical text, receipt,
    // role, numeric candidate or local binding authenticates a current device.
    public sealed class WsabiWmiProtectionDisableObservation
    {
        public WsabiWmiProtectionDisableStage Role { get; }
        public WsabiWmiProtectionDisableEvidence Evidence { get; }
        public int? ByteValue { get; }
        public bool IsExecutable => false;
        public bool IsHardwareObservation => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;
        public WsabiWmiProtectionDisableObservation(WsabiWmiProtectionDisableStage role,
            WsabiWmiProtectionDisableEvidence evidence, int? byteValue = null)
        { Role = role; Evidence = evidence; ByteValue = byteValue; }
    }

    public sealed class WsabiWmiProtectionDisableSnapshot
    {
        public WsabiWmiProtectionDisableReviewStatus Status { get; }
        public WsabiWmiProtectionDisableStage? NextStage { get; }
        public int AcceptedStages { get; }
        public int ExpectedPreModeByte => 1;
        public int ExpectedPostModeByte => 0;
        public int? ObservedPreModeByte { get; }
        public int? ObservedPostModeByte { get; }
        public bool SetterAcknowledged => false;
        public bool SetterReceiptAccepted { get; }
        public int BoundReadCandidateCount { get; }
        public bool IsStoredReadbackMatchedCandidate => Status == WsabiWmiProtectionDisableReviewStatus.StoredReadbackMatchedCandidate;
        public bool IsExecutable => false;
        public bool IsHardwareObservation => false;
        public bool IsChargeLimitConfirmed => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;
        internal WsabiWmiProtectionDisableSnapshot(WsabiWmiProtectionDisableReviewStatus status,
            WsabiWmiProtectionDisableStage? nextStage, int acceptedStages, int? pre, int? post,
            bool receipt, int readCandidates)
        {
            Status = status; NextStage = nextStage; AcceptedStages = acceptedStages;
            ObservedPreModeByte = pre; ObservedPostModeByte = post;
            SetterReceiptAccepted = receipt; BoundReadCandidateCount = readCandidates;
        }
    }

    public sealed class WsabiWmiProtectionDisableDecision
    {
        public WsabiWmiProtectionDisableDecisionStatus Status { get; }
        public WsabiWmiProtectionDisableSnapshot Snapshot { get; }
        public WsabiWmiProtectionDisableStage? NextStage => Snapshot.NextStage;
        public bool IsAccepted => Status == WsabiWmiProtectionDisableDecisionStatus.Advanced ||
            Status == WsabiWmiProtectionDisableDecisionStatus.StoredReadbackMatchedCandidate;
        public bool IsTerminal => Snapshot.Status != WsabiWmiProtectionDisableReviewStatus.AwaitingObservation;
        public bool IsExecutable => false;
        public bool IsHardwareObservation => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;
        internal WsabiWmiProtectionDisableDecision(WsabiWmiProtectionDisableDecisionStatus status,
            WsabiWmiProtectionDisableSnapshot snapshot) { Status = status; Snapshot = snapshot; }
    }

    // Pure, fixed 1-to-0 decision model. Actual call, output and input closure
    // must be enforced by the separate owner before the next stage is entered.
    public sealed class WsabiWmiProtectionDisableReview
    {
        public const int MaximumStages = 3;
        public const int MaximumSemanticSettingOperations = 1;
        public const int DeclaredRetries = 0;
        private static readonly IReadOnlyList<WsabiWmiProtectionDisableStage> stages =
            System.Array.AsReadOnly(new[] { WsabiWmiProtectionDisableStage.PreMode,
                WsabiWmiProtectionDisableStage.SemanticSet0, WsabiWmiProtectionDisableStage.PostMode });
        private readonly object sync = new object();
        private int acceptedStages, boundReadCandidateCount;
        private int? preMode, postMode;
        private bool setterReceiptAccepted;
        private WsabiWmiProtectionDisableReviewStatus status;
        public static IReadOnlyList<WsabiWmiProtectionDisableStage> StageOrder => stages;
        public bool IsExecutable => false;
        public bool IsHardwareObservation => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;
        public WsabiWmiProtectionDisableReviewStatus Status { get { lock (sync) return status; } }
        public WsabiWmiProtectionDisableStage? NextStage { get { lock (sync) return NextStageCore(); } }
        public WsabiWmiProtectionDisableSnapshot Snapshot { get { lock (sync) return SnapshotCore(); } }

        public WsabiWmiProtectionDisableDecision Observe(WsabiWmiProtectionDisableObservation observation)
        {
            lock (sync)
            {
                if (status != WsabiWmiProtectionDisableReviewStatus.AwaitingObservation)
                    return Decision(WsabiWmiProtectionDisableDecisionStatus.AlreadyTerminal);
                if (observation == null) return Stop(WsabiWmiProtectionDisableDecisionStatus.MissingObservation);
                if (observation.Role != stages[acceptedStages]) return Stop(WsabiWmiProtectionDisableDecisionStatus.UnexpectedStage);
                switch (observation.Evidence)
                {
                    case WsabiWmiProtectionDisableEvidence.HistoricalRead: return Stop(WsabiWmiProtectionDisableDecisionStatus.HistoricalObservationNotAdmissible);
                    case WsabiWmiProtectionDisableEvidence.Rejected: return Stop(WsabiWmiProtectionDisableDecisionStatus.ObservationRejected);
                    case WsabiWmiProtectionDisableEvidence.Unknown: return Stop(WsabiWmiProtectionDisableDecisionStatus.ObservationUnknown);
                }
                if (observation.Role == WsabiWmiProtectionDisableStage.SemanticSet0)
                {
                    if (observation.Evidence != WsabiWmiProtectionDisableEvidence.SetterReceiptAcceptedForReadback)
                        return Stop(WsabiWmiProtectionDisableDecisionStatus.UnexpectedEvidence);
                    if (observation.ByteValue.HasValue) return Stop(WsabiWmiProtectionDisableDecisionStatus.InvalidByteValue);
                    setterReceiptAccepted = true;
                }
                else
                {
                    if (observation.Evidence != WsabiWmiProtectionDisableEvidence.BoundReadCandidate)
                        return Stop(WsabiWmiProtectionDisableDecisionStatus.UnexpectedEvidence);
                    if (!observation.ByteValue.HasValue || observation.ByteValue.Value < 0 || observation.ByteValue.Value > 255)
                        return Stop(WsabiWmiProtectionDisableDecisionStatus.InvalidByteValue);
                    int value = observation.ByteValue.Value;
                    if (observation.Role == WsabiWmiProtectionDisableStage.PreMode)
                    {
                        preMode = value;
                        if (value == 0) return Stop(WsabiWmiProtectionDisableDecisionStatus.AlreadyDisabledCandidate);
                        if (value != 1) return Stop(WsabiWmiProtectionDisableDecisionStatus.PreModeNotOne);
                    }
                    else
                    {
                        postMode = value;
                        if (value != 0) return Stop(WsabiWmiProtectionDisableDecisionStatus.PostModeMismatch);
                    }
                    boundReadCandidateCount++;
                }
                acceptedStages++;
                if (acceptedStages == MaximumStages)
                {
                    status = WsabiWmiProtectionDisableReviewStatus.StoredReadbackMatchedCandidate;
                    return Decision(WsabiWmiProtectionDisableDecisionStatus.StoredReadbackMatchedCandidate);
                }
                return Decision(WsabiWmiProtectionDisableDecisionStatus.Advanced);
            }
        }
        private WsabiWmiProtectionDisableStage? NextStageCore()
            => status == WsabiWmiProtectionDisableReviewStatus.AwaitingObservation
                ? (WsabiWmiProtectionDisableStage?)stages[acceptedStages] : null;
        private WsabiWmiProtectionDisableSnapshot SnapshotCore()
            => new WsabiWmiProtectionDisableSnapshot(status, NextStageCore(), acceptedStages,
                preMode, postMode, setterReceiptAccepted, boundReadCandidateCount);
        private WsabiWmiProtectionDisableDecision Decision(WsabiWmiProtectionDisableDecisionStatus decision)
            => new WsabiWmiProtectionDisableDecision(decision, SnapshotCore());
        private WsabiWmiProtectionDisableDecision Stop(WsabiWmiProtectionDisableDecisionStatus reason)
        { status = WsabiWmiProtectionDisableReviewStatus.Stopped; return Decision(reason); }
    }
}
