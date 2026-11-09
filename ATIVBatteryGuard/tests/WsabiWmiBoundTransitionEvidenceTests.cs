using System;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiBoundTransitionEvidenceTests()
    {
        Add("bound transition review completes six bound candidates and a receipt without fabricating semantic acknowledgement", () =>
        {
            var review = BoundTransitionBefore(3);
            var beforeReceipt = review.Snapshot;
            Equal(3, beforeReceipt.BoundReadCandidateCount);
            Check(!beforeReceipt.SetterAcknowledged && !beforeReceipt.SetterReceiptAccepted,
                "pre reads invented a setter response");
            var receipt = review.Observe(BoundTransitionReceipt());
            Equal(WsabiWmiProtectionTransitionDecisionStatus.Advanced, receipt.Status);
            Check(receipt.Snapshot.SetterReceiptAccepted && !receipt.Snapshot.SetterAcknowledged,
                "receipt was renamed as a semantic setter acknowledgement");
            Equal(3, receipt.Snapshot.BoundReadCandidateCount);
            Check(!receipt.Snapshot.ObservedPostModeByte.HasValue && !receipt.Snapshot.ObservedPostUpperByte.HasValue &&
                !receipt.Snapshot.ObservedPostLowerByte.HasValue && !receipt.Snapshot.IsStoredReadbackMatchedCandidate,
                "receipt invented independently observed stored values");
            review.Observe(BoundTransitionRead(WsabiWmiProtectionTransitionStage.PostMode, 1));
            review.Observe(BoundTransitionRead(WsabiWmiProtectionTransitionStage.PostUpper, 80));
            var final = review.Observe(BoundTransitionRead(WsabiWmiProtectionTransitionStage.PostLower, 75));
            Equal(WsabiWmiProtectionTransitionDecisionStatus.StoredReadbackMatchedCandidate, final.Status);
            Equal(7, final.Snapshot.AcceptedStages); Equal(6, final.Snapshot.BoundReadCandidateCount);
            Check(final.Snapshot.SetterReceiptAccepted && !final.Snapshot.SetterAcknowledged,
                "post reads retroactively converted receipt into semantic acknowledgement");
            Check(!beforeReceipt.SetterReceiptAccepted && !receipt.Snapshot.ObservedPostModeByte.HasValue &&
                receipt.Snapshot.BoundReadCandidateCount == 3, "new categories broke immutable earlier snapshots");
            ProtectionReviewAssertNoCapability(review); ProtectionReviewAssertNoCapability(final);
            ProtectionReviewAssertNoCapability(final.Snapshot);
        });

        Add("bound transition receipt belongs only to the setter and never contains an observed byte", () =>
        {
            foreach (int stageIndex in new[] { 0, 1, 2, 4, 5, 6 })
            {
                var review = BoundTransitionBefore(stageIndex);
                var role = WsabiWmiProtectionTransitionReview.StageOrder[stageIndex];
                var decision = review.Observe(new WsabiWmiProtectionTransitionObservation(role,
                    WsabiWmiProtectionTransitionEvidence.SetterReceiptAcceptedForReadback));
                ProtectionReviewAssertStopped(decision, WsabiWmiProtectionTransitionDecisionStatus.UnexpectedEvidence);
                Equal(stageIndex, decision.Snapshot.AcceptedStages);
                Equal(stageIndex < 4 ? stageIndex : stageIndex - 1, decision.Snapshot.BoundReadCandidateCount);
            }
            foreach (int value in new[] { int.MinValue, -1, 0, 1, 255, 256, int.MaxValue })
            {
                var review = BoundTransitionBefore(3);
                var decision = review.Observe(new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.SemanticSet1,
                    WsabiWmiProtectionTransitionEvidence.SetterReceiptAcceptedForReadback, value));
                ProtectionReviewAssertStopped(decision, WsabiWmiProtectionTransitionDecisionStatus.InvalidByteValue);
                Equal(3, decision.Snapshot.BoundReadCandidateCount);
                Check(!decision.Snapshot.SetterReceiptAccepted && !decision.Snapshot.SetterAcknowledged,
                    "a valued input echo was accepted as a setter receipt");
            }
            ProtectionReviewAssertStopped(BoundTransitionBefore(3).Observe(
                BoundTransitionRead(WsabiWmiProtectionTransitionStage.SemanticSet1, 1)),
                WsabiWmiProtectionTransitionDecisionStatus.UnexpectedEvidence);
        });

        Add("bound transition evidence preserves legacy enum numbers acknowledgement semantics and mixed read accounting", () =>
        {
            Equal(0, (int)WsabiWmiProtectionTransitionEvidence.Unknown);
            Equal(1, (int)WsabiWmiProtectionTransitionEvidence.AcceptedCurrentRead);
            Equal(2, (int)WsabiWmiProtectionTransitionEvidence.SetterAcknowledged);
            Equal(3, (int)WsabiWmiProtectionTransitionEvidence.HistoricalRead);
            Equal(4, (int)WsabiWmiProtectionTransitionEvidence.Rejected);
            Equal(5, (int)WsabiWmiProtectionTransitionEvidence.BoundReadCandidate);
            Equal(6, (int)WsabiWmiProtectionTransitionEvidence.SetterReceiptAcceptedForReadback);
            var legacy = ProtectionReviewBefore(7).Snapshot;
            Check(legacy.SetterAcknowledged && !legacy.SetterReceiptAccepted, "legacy acknowledgement changed meaning");
            Equal(0, legacy.BoundReadCandidateCount); Equal(7, legacy.AcceptedStages);
            var mixed = ProtectionReviewBefore(1);
            mixed.Observe(BoundTransitionRead(WsabiWmiProtectionTransitionStage.PreUpper, 255));
            mixed.Observe(ProtectionReviewRead(WsabiWmiProtectionTransitionStage.PreLower, 0));
            mixed.Observe(BoundTransitionReceipt());
            mixed.Observe(BoundTransitionRead(WsabiWmiProtectionTransitionStage.PostMode, 1));
            mixed.Observe(ProtectionReviewRead(WsabiWmiProtectionTransitionStage.PostUpper, 80));
            var final = mixed.Observe(BoundTransitionRead(WsabiWmiProtectionTransitionStage.PostLower, 75));
            Equal(WsabiWmiProtectionTransitionDecisionStatus.StoredReadbackMatchedCandidate, final.Status);
            Equal(3, final.Snapshot.BoundReadCandidateCount);
            Check(final.Snapshot.SetterReceiptAccepted && !final.Snapshot.SetterAcknowledged,
                "mixed read categories changed the independent setter receipt category");
        });

        Add("bound transition receipt followed by unknown keeps effect unknown and cannot resume with late success", () =>
        {
            var review = BoundTransitionBefore(4);
            var decision = review.Observe(new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.PostMode,
                WsabiWmiProtectionTransitionEvidence.Unknown));
            ProtectionReviewAssertStopped(decision, WsabiWmiProtectionTransitionDecisionStatus.ObservationUnknown);
            Check(decision.Snapshot.SetterReceiptAccepted && !decision.Snapshot.SetterAcknowledged &&
                !decision.Snapshot.ObservedPostModeByte.HasValue && !decision.Snapshot.IsStoredReadbackMatchedCandidate,
                "unknown post state became either setter success or unchanged state");
            Equal(3, decision.Snapshot.BoundReadCandidateCount); Equal(4, decision.Snapshot.AcceptedStages);
            Equal(WsabiWmiProtectionTransitionDecisionStatus.AlreadyTerminal,
                review.Observe(BoundTransitionRead(WsabiWmiProtectionTransitionStage.PostMode, 1)).Status);
            Equal(3, review.Snapshot.BoundReadCandidateCount);
            ProtectionReviewAssertNoCapability(decision); ProtectionReviewAssertNoCapability(decision.Snapshot);
        });

        Add("bound transition each post mismatch remains terminal without counting the rejected candidate or promoting receipt", () =>
        {
            int[] expected = { 1, 80, 75 };
            var failures = new[] { WsabiWmiProtectionTransitionDecisionStatus.PostModeMismatch,
                WsabiWmiProtectionTransitionDecisionStatus.PostUpperMismatch, WsabiWmiProtectionTransitionDecisionStatus.PostLowerMismatch };
            for (int offset = 0; offset < 3; offset++)
            for (int value = 0; value <= 255; value++)
            {
                if (value == expected[offset]) continue;
                int index = offset + 4;
                var review = BoundTransitionBefore(index);
                var decision = review.Observe(BoundTransitionRead(WsabiWmiProtectionTransitionReview.StageOrder[index], value));
                ProtectionReviewAssertStopped(decision, failures[offset]);
                Equal(index, decision.Snapshot.AcceptedStages); Equal(offset + 3, decision.Snapshot.BoundReadCandidateCount);
                Check(decision.Snapshot.SetterReceiptAccepted && !decision.Snapshot.SetterAcknowledged,
                    "mismatch confused receipt and semantic acknowledgement");
                Equal(1, decision.Snapshot.ExpectedPostModeByte); Equal(80, decision.Snapshot.ExpectedPostUpperByte);
                Equal(75, decision.Snapshot.ExpectedPostLowerByte);
                int? observed = offset == 0 ? decision.Snapshot.ObservedPostModeByte : offset == 1
                    ? decision.Snapshot.ObservedPostUpperByte : decision.Snapshot.ObservedPostLowerByte;
                Equal((int?)value, observed);
                Equal(WsabiWmiProtectionTransitionDecisionStatus.AlreadyTerminal,
                    review.Observe(BoundTransitionRead(WsabiWmiProtectionTransitionReview.StageOrder[index], expected[offset])).Status);
            }
        });

        Add("bound transition candidate still requires a bounded byte and nonzero pre mode never reaches receipt", () =>
        {
            foreach (int index in new[] { 0, 1, 2, 4, 5, 6 })
            foreach (int? value in new int?[] { null, int.MinValue, -1, 256, int.MaxValue })
            {
                var review = BoundTransitionBefore(index);
                var decision = review.Observe(new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionReview.StageOrder[index],
                    WsabiWmiProtectionTransitionEvidence.BoundReadCandidate, value));
                ProtectionReviewAssertStopped(decision, WsabiWmiProtectionTransitionDecisionStatus.InvalidByteValue);
                Equal(index, decision.Snapshot.AcceptedStages);
                Equal(index < 4 ? index : index - 1, decision.Snapshot.BoundReadCandidateCount);
            }
            for (int value = 1; value <= 255; value++)
            {
                var review = new WsabiWmiProtectionTransitionReview();
                var decision = review.Observe(BoundTransitionRead(WsabiWmiProtectionTransitionStage.PreMode, value));
                ProtectionReviewAssertStopped(decision, WsabiWmiProtectionTransitionDecisionStatus.PreModeNotZero);
                Equal(0, decision.Snapshot.BoundReadCandidateCount); Equal(0, decision.Snapshot.AcceptedStages);
                Check(!decision.Snapshot.SetterReceiptAccepted && !decision.Snapshot.SetterAcknowledged,
                    "a rejected pre mode reached a setter category");
            }
        });
    }

    private static WsabiWmiProtectionTransitionObservation BoundTransitionRead(WsabiWmiProtectionTransitionStage role, int value)
        => new WsabiWmiProtectionTransitionObservation(role, WsabiWmiProtectionTransitionEvidence.BoundReadCandidate, value);

    private static WsabiWmiProtectionTransitionObservation BoundTransitionReceipt()
        => new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.SemanticSet1,
            WsabiWmiProtectionTransitionEvidence.SetterReceiptAcceptedForReadback);

    private static WsabiWmiProtectionTransitionReview BoundTransitionBefore(int index)
    {
        int[] values = { 0, 255, 0, 0, 1, 80, 75 };
        var review = new WsabiWmiProtectionTransitionReview();
        for (int i = 0; i < index; i++)
        {
            var role = WsabiWmiProtectionTransitionReview.StageOrder[i];
            var decision = review.Observe(i == 3 ? BoundTransitionReceipt() : BoundTransitionRead(role, values[i]));
            Equal(i == 6 ? WsabiWmiProtectionTransitionDecisionStatus.StoredReadbackMatchedCandidate
                : WsabiWmiProtectionTransitionDecisionStatus.Advanced, decision.Status);
        }
        return review;
    }
}
