using System;
using System.Collections.Generic;

namespace ATIVBatteryGuard.Core.Services
{
    public enum WsabiWmiProtectionTransitionStage
    {
        PreMode, PreUpper, PreLower, SemanticSet1, PostMode, PostUpper, PostLower
    }

    public enum WsabiWmiProtectionTransitionEvidence
    {
        Unknown, AcceptedCurrentRead, SetterAcknowledged, HistoricalRead, Rejected
    }

    public enum WsabiWmiProtectionTransitionReviewStatus
    {
        AwaitingObservation, Stopped, StoredReadbackMatchedCandidate
    }

    public enum WsabiWmiProtectionTransitionDecisionStatus
    {
        Advanced, StoredReadbackMatchedCandidate, MissingObservation, UnexpectedStage,
        HistoricalObservationNotAdmissible, ObservationRejected, ObservationUnknown,
        UnexpectedEvidence, InvalidByteValue, PreModeNotZero, PostModeMismatch,
        PostUpperMismatch, PostLowerMismatch, AlreadyTerminal
    }

    // A caller-normalized fact for this pure review. AcceptedCurrentRead is not
    // a freshness validator, SDK completion, hardware permission or approval.
    // In particular, a historical Access1 result cannot be admitted as a current
    // observation merely because its numeric candidate was zero.
    public sealed class WsabiWmiProtectionTransitionObservation
    {
        public WsabiWmiProtectionTransitionStage Role { get; }
        public WsabiWmiProtectionTransitionEvidence Evidence { get; }
        public int? ByteValue { get; }
        public bool IsExecutable => false;
        public bool IsHardwareObservation => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        public WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage role,
            WsabiWmiProtectionTransitionEvidence evidence, int? byteValue = null)
        {
            Role = role; Evidence = evidence; ByteValue = byteValue;
        }
    }

    // Expected source-contract values and accepted caller observations remain
    // separate. No value is a measured charger state or a promoted actualMode.
    public sealed class WsabiWmiProtectionTransitionSnapshot
    {
        public WsabiWmiProtectionTransitionReviewStatus Status { get; }
        public WsabiWmiProtectionTransitionStage? NextStage { get; }
        public int AcceptedStages { get; }
        public int ExpectedPreModeByte => 0;
        public int ExpectedPostModeByte => 1;
        public int ExpectedPostUpperByte => 80;
        public int ExpectedPostLowerByte => 75;
        public int? ObservedPreModeByte { get; }
        public int? ObservedPreUpperByte { get; }
        public int? ObservedPreLowerByte { get; }
        public bool SetterAcknowledged { get; }
        public int? ObservedPostModeByte { get; }
        public int? ObservedPostUpperByte { get; }
        public int? ObservedPostLowerByte { get; }
        public bool IsStoredReadbackMatchedCandidate => Status == WsabiWmiProtectionTransitionReviewStatus.StoredReadbackMatchedCandidate;
        public bool IsExecutable => false;
        public bool IsHardwareObservation => false;
        public bool IsChargeLimitConfirmed => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        internal WsabiWmiProtectionTransitionSnapshot(WsabiWmiProtectionTransitionReviewStatus status,
            WsabiWmiProtectionTransitionStage? nextStage, int acceptedStages, int?[] observations,
            bool setterAcknowledged)
        {
            Status = status; NextStage = nextStage; AcceptedStages = acceptedStages;
            ObservedPreModeByte = observations[0]; ObservedPreUpperByte = observations[1];
            ObservedPreLowerByte = observations[2]; SetterAcknowledged = setterAcknowledged;
            ObservedPostModeByte = observations[4]; ObservedPostUpperByte = observations[5];
            ObservedPostLowerByte = observations[6];
        }
    }

    public sealed class WsabiWmiProtectionTransitionDecision
    {
        public WsabiWmiProtectionTransitionDecisionStatus Status { get; }
        public WsabiWmiProtectionTransitionSnapshot Snapshot { get; }
        public WsabiWmiProtectionTransitionStage? NextStage => Snapshot.NextStage;
        public bool IsAccepted => Status == WsabiWmiProtectionTransitionDecisionStatus.Advanced ||
            Status == WsabiWmiProtectionTransitionDecisionStatus.StoredReadbackMatchedCandidate;
        public bool IsTerminal => Snapshot.Status != WsabiWmiProtectionTransitionReviewStatus.AwaitingObservation;
        public bool IsExecutable => false;
        public bool IsHardwareObservation => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        internal WsabiWmiProtectionTransitionDecision(WsabiWmiProtectionTransitionDecisionStatus status,
            WsabiWmiProtectionTransitionSnapshot snapshot)
        {
            Status = status; Snapshot = snapshot;
        }
    }

    // Fixed 0-to-1 specification and decision model only. There is no selector,
    // address, frame, nonce, dispatcher, SDK object, marker or hardware adapter.
    // A future coordinator must separately enforce actual completion, source
    // attribution and ownership; these numeric decisions cannot authorize it.
    public sealed class WsabiWmiProtectionTransitionReview
    {
        public const int MaximumStages = 7;
        public const int MaximumSemanticSettingOperations = 1;
        public const int DeclaredRetries = 0;
        private static readonly IReadOnlyList<WsabiWmiProtectionTransitionStage> stages =
            Array.AsReadOnly(new[]
            {
                WsabiWmiProtectionTransitionStage.PreMode,
                WsabiWmiProtectionTransitionStage.PreUpper,
                WsabiWmiProtectionTransitionStage.PreLower,
                WsabiWmiProtectionTransitionStage.SemanticSet1,
                WsabiWmiProtectionTransitionStage.PostMode,
                WsabiWmiProtectionTransitionStage.PostUpper,
                WsabiWmiProtectionTransitionStage.PostLower
            });
        private readonly object sync = new object();
        private readonly int?[] observations = new int?[MaximumStages];
        private int acceptedStages;
        private bool setterAcknowledged;
        private WsabiWmiProtectionTransitionReviewStatus status = WsabiWmiProtectionTransitionReviewStatus.AwaitingObservation;

        // Required evidence order only, never an executable dispatch schedule.
        public static IReadOnlyList<WsabiWmiProtectionTransitionStage> StageOrder => stages;
        public bool IsExecutable => false;
        public bool IsHardwareObservation => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;
        public WsabiWmiProtectionTransitionReviewStatus Status { get { lock (sync) return status; } }
        public WsabiWmiProtectionTransitionStage? NextStage { get { lock (sync) return NextStageCore(); } }
        public WsabiWmiProtectionTransitionSnapshot Snapshot { get { lock (sync) return SnapshotCore(); } }

        public WsabiWmiProtectionTransitionDecision Observe(WsabiWmiProtectionTransitionObservation observation)
        {
            lock (sync)
            {
                if (status != WsabiWmiProtectionTransitionReviewStatus.AwaitingObservation)
                    return Decision(WsabiWmiProtectionTransitionDecisionStatus.AlreadyTerminal);
                if (observation == null) return Stop(WsabiWmiProtectionTransitionDecisionStatus.MissingObservation);
                if (observation.Role != stages[acceptedStages])
                    return Stop(WsabiWmiProtectionTransitionDecisionStatus.UnexpectedStage);
                if (observation.Evidence == WsabiWmiProtectionTransitionEvidence.HistoricalRead)
                    return Stop(WsabiWmiProtectionTransitionDecisionStatus.HistoricalObservationNotAdmissible);
                if (observation.Evidence == WsabiWmiProtectionTransitionEvidence.Rejected)
                    return Stop(WsabiWmiProtectionTransitionDecisionStatus.ObservationRejected);
                if (observation.Evidence == WsabiWmiProtectionTransitionEvidence.Unknown)
                    return Stop(WsabiWmiProtectionTransitionDecisionStatus.ObservationUnknown);

                if (observation.Role == WsabiWmiProtectionTransitionStage.SemanticSet1)
                {
                    if (observation.Evidence != WsabiWmiProtectionTransitionEvidence.SetterAcknowledged)
                        return Stop(WsabiWmiProtectionTransitionDecisionStatus.UnexpectedEvidence);
                    if (observation.ByteValue.HasValue)
                        return Stop(WsabiWmiProtectionTransitionDecisionStatus.InvalidByteValue);
                    // The acknowledgement merely permits considering the next
                    // review stage. It is never interpreted as stored state.
                    setterAcknowledged = true;
                }
                else
                {
                    if (observation.Evidence != WsabiWmiProtectionTransitionEvidence.AcceptedCurrentRead)
                        return Stop(WsabiWmiProtectionTransitionDecisionStatus.UnexpectedEvidence);
                    if (!observation.ByteValue.HasValue || observation.ByteValue.Value < 0 || observation.ByteValue.Value > 255)
                        return Stop(WsabiWmiProtectionTransitionDecisionStatus.InvalidByteValue);
                    int value = observation.ByteValue.Value;
                    observations[acceptedStages] = value;
                    switch (observation.Role)
                    {
                        case WsabiWmiProtectionTransitionStage.PreMode:
                            if (value != 0) return Stop(WsabiWmiProtectionTransitionDecisionStatus.PreModeNotZero);
                            break;
                        case WsabiWmiProtectionTransitionStage.PostMode:
                            if (value != 1) return Stop(WsabiWmiProtectionTransitionDecisionStatus.PostModeMismatch);
                            break;
                        case WsabiWmiProtectionTransitionStage.PostUpper:
                            if (value != 80) return Stop(WsabiWmiProtectionTransitionDecisionStatus.PostUpperMismatch);
                            break;
                        case WsabiWmiProtectionTransitionStage.PostLower:
                            if (value != 75) return Stop(WsabiWmiProtectionTransitionDecisionStatus.PostLowerMismatch);
                            break;
                    }
                }

                acceptedStages++;
                if (acceptedStages == MaximumStages)
                {
                    status = WsabiWmiProtectionTransitionReviewStatus.StoredReadbackMatchedCandidate;
                    return Decision(WsabiWmiProtectionTransitionDecisionStatus.StoredReadbackMatchedCandidate);
                }
                return Decision(WsabiWmiProtectionTransitionDecisionStatus.Advanced);
            }
        }

        private WsabiWmiProtectionTransitionStage? NextStageCore()
            => status == WsabiWmiProtectionTransitionReviewStatus.AwaitingObservation
                ? (WsabiWmiProtectionTransitionStage?)stages[acceptedStages] : null;

        private WsabiWmiProtectionTransitionSnapshot SnapshotCore()
            => new WsabiWmiProtectionTransitionSnapshot(status, NextStageCore(), acceptedStages, observations, setterAcknowledged);

        private WsabiWmiProtectionTransitionDecision Decision(WsabiWmiProtectionTransitionDecisionStatus decision)
            => new WsabiWmiProtectionTransitionDecision(decision, SnapshotCore());

        private WsabiWmiProtectionTransitionDecision Stop(WsabiWmiProtectionTransitionDecisionStatus reason)
        {
            status = WsabiWmiProtectionTransitionReviewStatus.Stopped;
            return Decision(reason);
        }
    }
}
