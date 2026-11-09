using System;
using System.Linq;
using System.Reflection;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiProtectionDisableReviewTests()
    {
        Add("disable review fixes three roles and keeps expected values separate from all empty observations", () =>
        {
            Check(WsabiWmiProtectionDisableReview.StageOrder.SequenceEqual(new[] { WsabiWmiProtectionDisableStage.PreMode,
                WsabiWmiProtectionDisableStage.SemanticSet0, WsabiWmiProtectionDisableStage.PostMode }), "disable order changed");
            Equal(3, WsabiWmiProtectionDisableReview.MaximumStages);
            Equal(1, WsabiWmiProtectionDisableReview.MaximumSemanticSettingOperations);
            Equal(0, WsabiWmiProtectionDisableReview.DeclaredRetries);
            var review = new WsabiWmiProtectionDisableReview(); var snapshot = review.Snapshot;
            Equal(1, snapshot.ExpectedPreModeByte); Equal(0, snapshot.ExpectedPostModeByte);
            Check(!snapshot.ObservedPreModeByte.HasValue && !snapshot.ObservedPostModeByte.HasValue &&
                !snapshot.SetterReceiptAccepted && !snapshot.SetterAcknowledged, "expectation became observed state");
            Equal(0, snapshot.AcceptedStages); Equal(0, snapshot.BoundReadCandidateCount);
            DisableReviewNoAuthority(review); DisableReviewNoAuthority(snapshot);
        });

        Add("disable review needs pre one receipt and independently supplied post zero without semantic success ACK", () =>
        {
            var review = new WsabiWmiProtectionDisableReview(); var empty = review.Snapshot;
            var pre = review.Observe(DisableReviewRead(WsabiWmiProtectionDisableStage.PreMode, 1));
            Equal(WsabiWmiProtectionDisableDecisionStatus.Advanced, pre.Status);
            var receipt = review.Observe(DisableReviewReceipt());
            Equal(WsabiWmiProtectionDisableDecisionStatus.Advanced, receipt.Status);
            Check(receipt.Snapshot.SetterReceiptAccepted && !receipt.Snapshot.SetterAcknowledged &&
                !receipt.Snapshot.ObservedPostModeByte.HasValue && !receipt.Snapshot.IsStoredReadbackMatchedCandidate,
                "receipt became execution acknowledgement or independent post state");
            var final = review.Observe(DisableReviewRead(WsabiWmiProtectionDisableStage.PostMode, 0));
            Equal(WsabiWmiProtectionDisableDecisionStatus.StoredReadbackMatchedCandidate, final.Status);
            Equal(3, final.Snapshot.AcceptedStages); Equal(2, final.Snapshot.BoundReadCandidateCount);
            Equal((int?)1, final.Snapshot.ObservedPreModeByte); Equal((int?)0, final.Snapshot.ObservedPostModeByte);
            Check(final.IsTerminal && final.IsAccepted && final.Snapshot.IsStoredReadbackMatchedCandidate,
                "complete numeric comparison missing");
            Check(!empty.ObservedPreModeByte.HasValue && !pre.Snapshot.SetterReceiptAccepted &&
                !receipt.Snapshot.ObservedPostModeByte.HasValue, "later evidence mutated an earlier snapshot");
            Check(!final.NextStage.HasValue, "matched trial exposed a further stage");
            DisableReviewNoAuthority(final); DisableReviewNoAuthority(final.Snapshot);
        });

        Add("disable pre zero is a terminal already-disabled candidate with no setter or post state", () =>
        {
            var review = new WsabiWmiProtectionDisableReview();
            var decision = review.Observe(DisableReviewRead(WsabiWmiProtectionDisableStage.PreMode, 0));
            Equal(WsabiWmiProtectionDisableDecisionStatus.AlreadyDisabledCandidate, decision.Status);
            Equal((int?)0, decision.Snapshot.ObservedPreModeByte);
            Check(decision.IsTerminal && !decision.IsAccepted && !decision.NextStage.HasValue,
                "already-disabled candidate admitted setting");
            Check(!decision.Snapshot.SetterReceiptAccepted && !decision.Snapshot.ObservedPostModeByte.HasValue,
                "pre zero fabricated setting or post state");
            Equal(0, decision.Snapshot.AcceptedStages); Equal(0, decision.Snapshot.BoundReadCandidateCount);
            Equal(WsabiWmiProtectionDisableDecisionStatus.AlreadyTerminal, review.Observe(DisableReviewReceipt()).Status);
        });

        Add("disable all other pre values reject without authorizing a setting and preserve the supplied mismatch", () =>
        {
            for (int value = 2; value <= 255; value++)
            {
                var review = new WsabiWmiProtectionDisableReview();
                var decision = review.Observe(DisableReviewRead(WsabiWmiProtectionDisableStage.PreMode, value));
                Equal(WsabiWmiProtectionDisableDecisionStatus.PreModeNotOne, decision.Status);
                Equal((int?)value, decision.Snapshot.ObservedPreModeByte);
                Equal(0, decision.Snapshot.AcceptedStages); Equal(0, decision.Snapshot.BoundReadCandidateCount);
                Check(decision.IsTerminal && !decision.Snapshot.SetterReceiptAccepted, "pre mismatch reached setting");
            }
        });

        Add("disable all nonzero post values stop with unknown effect without late repair or reverse transition", () =>
        {
            for (int value = 1; value <= 255; value++)
            {
                var review = DisableReviewBefore(2);
                var decision = review.Observe(DisableReviewRead(WsabiWmiProtectionDisableStage.PostMode, value));
                Equal(WsabiWmiProtectionDisableDecisionStatus.PostModeMismatch, decision.Status);
                Equal((int?)value, decision.Snapshot.ObservedPostModeByte);
                Equal(2, decision.Snapshot.AcceptedStages); Equal(1, decision.Snapshot.BoundReadCandidateCount);
                Check(decision.Snapshot.SetterReceiptAccepted && !decision.Snapshot.IsStoredReadbackMatchedCandidate,
                    "post mismatch fabricated unchanged state or success");
                Equal(WsabiWmiProtectionDisableDecisionStatus.AlreadyTerminal,
                    review.Observe(DisableReviewRead(WsabiWmiProtectionDisableStage.PostMode, 0)).Status);
            }
        });

        Add("disable read candidates require bounded bytes while receipt accepts no byte even zero", () =>
        {
            foreach (int index in new[] { 0, 2 })
            foreach (int? value in new int?[] { null, -1, 256, int.MinValue, int.MaxValue })
            {
                var decision = DisableReviewBefore(index).Observe(new WsabiWmiProtectionDisableObservation(
                    WsabiWmiProtectionDisableReview.StageOrder[index], WsabiWmiProtectionDisableEvidence.BoundReadCandidate, value));
                Equal(WsabiWmiProtectionDisableDecisionStatus.InvalidByteValue, decision.Status);
                Check(decision.IsTerminal, "invalid read did not stop");
            }
            foreach (int value in new[] { int.MinValue, -1, 0, 1, 255, 256, int.MaxValue })
            {
                var decision = DisableReviewBefore(1).Observe(new WsabiWmiProtectionDisableObservation(
                    WsabiWmiProtectionDisableStage.SemanticSet0,
                    WsabiWmiProtectionDisableEvidence.SetterReceiptAcceptedForReadback, value));
                Equal(WsabiWmiProtectionDisableDecisionStatus.InvalidByteValue, decision.Status);
                Check(!decision.Snapshot.SetterReceiptAccepted, "input zero was accepted as observed stored mode");
            }
        });

        Add("disable unknown rejected historical missing and unrecognized evidence stop every stage", () =>
        {
            for (int index = 0; index < 3; index++)
            {
                var role = WsabiWmiProtectionDisableReview.StageOrder[index];
                foreach (var pair in new[] {
                    Tuple.Create(WsabiWmiProtectionDisableEvidence.Unknown, WsabiWmiProtectionDisableDecisionStatus.ObservationUnknown),
                    Tuple.Create(WsabiWmiProtectionDisableEvidence.Rejected, WsabiWmiProtectionDisableDecisionStatus.ObservationRejected),
                    Tuple.Create(WsabiWmiProtectionDisableEvidence.HistoricalRead, WsabiWmiProtectionDisableDecisionStatus.HistoricalObservationNotAdmissible),
                    Tuple.Create((WsabiWmiProtectionDisableEvidence)999, WsabiWmiProtectionDisableDecisionStatus.UnexpectedEvidence) })
                {
                    var review = DisableReviewBefore(index);
                    var decision = review.Observe(new WsabiWmiProtectionDisableObservation(role, pair.Item1, index == 0 ? (int?)1 : null));
                    Equal(pair.Item2, decision.Status); Check(decision.IsTerminal, "non-evidence did not stop");
                    Equal(WsabiWmiProtectionDisableDecisionStatus.AlreadyTerminal,
                        review.Observe(index == 1 ? DisableReviewReceipt() : DisableReviewRead(role, index == 0 ? 1 : 0)).Status);
                }
                Equal(WsabiWmiProtectionDisableDecisionStatus.MissingObservation, DisableReviewBefore(index).Observe(null).Status);
            }
        });

        Add("disable order role evidence and terminal bounds reject duplicates skips and setter receipts on reads", () =>
        {
            for (int index = 0; index < 3; index++)
            foreach (var role in new[] { (WsabiWmiProtectionDisableStage)(-1), WsabiWmiProtectionDisableStage.PreMode,
                WsabiWmiProtectionDisableStage.SemanticSet0, WsabiWmiProtectionDisableStage.PostMode, (WsabiWmiProtectionDisableStage)3 })
            {
                if (role == WsabiWmiProtectionDisableReview.StageOrder[index]) continue;
                Equal(WsabiWmiProtectionDisableDecisionStatus.UnexpectedStage, DisableReviewBefore(index).Observe(
                    new WsabiWmiProtectionDisableObservation(role, WsabiWmiProtectionDisableEvidence.BoundReadCandidate, 1)).Status);
            }
            foreach (int index in new[] { 0, 2 })
                Equal(WsabiWmiProtectionDisableDecisionStatus.UnexpectedEvidence, DisableReviewBefore(index).Observe(
                    new WsabiWmiProtectionDisableObservation(WsabiWmiProtectionDisableReview.StageOrder[index],
                        WsabiWmiProtectionDisableEvidence.SetterReceiptAcceptedForReadback)).Status);
            Equal(WsabiWmiProtectionDisableDecisionStatus.UnexpectedEvidence, DisableReviewBefore(1).Observe(
                DisableReviewRead(WsabiWmiProtectionDisableStage.SemanticSet0, 0)).Status);
            Equal(WsabiWmiProtectionDisableDecisionStatus.AlreadyTerminal, DisableReviewBefore(3).Observe(null).Status);
        });

        Add("disable specification exposes no thresholds or semantic acknowledgement evidence or execution authority", () =>
        {
            Check(!Enum.GetNames(typeof(WsabiWmiProtectionDisableEvidence)).Contains("SetterAcknowledged"), "disable admits semantic ACK evidence");
            foreach (var property in typeof(WsabiWmiProtectionDisableSnapshot).GetProperties())
                Check(property.Name.IndexOf("Upper", StringComparison.Ordinal) < 0 && property.Name.IndexOf("Lower", StringComparison.Ordinal) < 0,
                    "disable inferred unobserved threshold state");
            DisableReviewNoAuthority(new WsabiWmiProtectionDisableReview());
            DisableReviewNoAuthority(DisableReviewRead(WsabiWmiProtectionDisableStage.PreMode, 1));
            DisableReviewNoAuthority(DisableReviewBefore(3).Snapshot);
            Equal(7, WsabiWmiProtectionTransitionReview.MaximumStages);
            Equal(0, new WsabiWmiProtectionTransitionReview().Snapshot.ExpectedPreModeByte);
            Equal(1, new WsabiWmiProtectionTransitionReview().Snapshot.ExpectedPostModeByte);
        });
    }

    private static WsabiWmiProtectionDisableObservation DisableReviewRead(WsabiWmiProtectionDisableStage role, int value)
        => new WsabiWmiProtectionDisableObservation(role, WsabiWmiProtectionDisableEvidence.BoundReadCandidate, value);
    private static WsabiWmiProtectionDisableObservation DisableReviewReceipt()
        => new WsabiWmiProtectionDisableObservation(WsabiWmiProtectionDisableStage.SemanticSet0,
            WsabiWmiProtectionDisableEvidence.SetterReceiptAcceptedForReadback);
    private static WsabiWmiProtectionDisableReview DisableReviewBefore(int index)
    {
        var review = new WsabiWmiProtectionDisableReview();
        for (int i = 0; i < index; i++) review.Observe(i == 1 ? DisableReviewReceipt()
            : DisableReviewRead(WsabiWmiProtectionDisableReview.StageOrder[i], i == 0 ? 1 : 0));
        return review;
    }
    private static void DisableReviewNoAuthority(object value)
    {
        foreach (string name in new[] { "IsExecutable", "IsHardwareObservation", "IsChargeLimitConfirmed",
            "CanInvokeMethods", "CanReadHardware", "CanWriteHardware" })
        {
            var property = value.GetType().GetProperty(name, BindingFlags.Instance | BindingFlags.Public);
            if (property != null) Equal(false, (bool)property.GetValue(value));
        }
    }
}
