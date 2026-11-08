using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiProtectionTransitionReviewTests()
    {
        Add("protection transition review declares only the fixed seven evidence stages", () =>
        {
            var expected = new[]
            {
                WsabiWmiProtectionTransitionStage.PreMode, WsabiWmiProtectionTransitionStage.PreUpper,
                WsabiWmiProtectionTransitionStage.PreLower, WsabiWmiProtectionTransitionStage.SemanticSet1,
                WsabiWmiProtectionTransitionStage.PostMode, WsabiWmiProtectionTransitionStage.PostUpper,
                WsabiWmiProtectionTransitionStage.PostLower
            };
            Check(expected.SequenceEqual(WsabiWmiProtectionTransitionReview.StageOrder), "fixed evidence stages changed");
            Equal(7, WsabiWmiProtectionTransitionReview.MaximumStages);
            Equal(1, WsabiWmiProtectionTransitionReview.MaximumSemanticSettingOperations);
            Equal(0, WsabiWmiProtectionTransitionReview.DeclaredRetries);
            var list = (IList<WsabiWmiProtectionTransitionStage>)WsabiWmiProtectionTransitionReview.StageOrder;
            BatteryThrows<NotSupportedException>(() => list[0] = WsabiWmiProtectionTransitionStage.SemanticSet1);
            var review = new WsabiWmiProtectionTransitionReview(); var snapshot = review.Snapshot;
            Equal(WsabiWmiProtectionTransitionReviewStatus.AwaitingObservation, review.Status);
            Equal((WsabiWmiProtectionTransitionStage?)WsabiWmiProtectionTransitionStage.PreMode, review.NextStage);
            Equal(0, snapshot.AcceptedStages);
            Equal(0, snapshot.ExpectedPreModeByte); Equal(1, snapshot.ExpectedPostModeByte);
            Equal(80, snapshot.ExpectedPostUpperByte); Equal(75, snapshot.ExpectedPostLowerByte);
            ProtectionReviewAssertNoObservedBytes(snapshot);
            Check(!snapshot.SetterAcknowledged && !snapshot.IsStoredReadbackMatchedCandidate, "expectations became observations");
            ProtectionReviewAssertNoCapability(review); ProtectionReviewAssertNoCapability(snapshot);
        });

        Add("protection transition review accepts raw pre thresholds without assuming eighty seventy five or ordering", () =>
        {
            foreach (var pair in new[] { new[] { 0, 0 }, new[] { 255, 0 }, new[] { 0, 255 }, new[] { 75, 80 }, new[] { 80, 75 } })
            {
                var review = new WsabiWmiProtectionTransitionReview();
                ProtectionReviewAdvance(review, WsabiWmiProtectionTransitionStage.PreMode, 0);
                ProtectionReviewAdvance(review, WsabiWmiProtectionTransitionStage.PreUpper, pair[0]);
                var pre = ProtectionReviewAdvance(review, WsabiWmiProtectionTransitionStage.PreLower, pair[1]);
                Equal((int?)pair[0], pre.Snapshot.ObservedPreUpperByte);
                Equal((int?)pair[1], pre.Snapshot.ObservedPreLowerByte);
                Equal((WsabiWmiProtectionTransitionStage?)WsabiWmiProtectionTransitionStage.SemanticSet1, pre.NextStage);
                Equal(3, pre.Snapshot.AcceptedStages);
            }
        });

        Add("protection transition review requires all post readbacks after the setter acknowledgement", () =>
        {
            var review = ProtectionReviewAtSetter();
            var ack = review.Observe(new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.SemanticSet1,
                WsabiWmiProtectionTransitionEvidence.SetterAcknowledged));
            Equal(WsabiWmiProtectionTransitionDecisionStatus.Advanced, ack.Status);
            Equal(4, ack.Snapshot.AcceptedStages); Check(ack.Snapshot.SetterAcknowledged, "setter acknowledgement was lost");
            Check(!ack.IsTerminal && !ack.Snapshot.IsStoredReadbackMatchedCandidate, "acknowledgement became state proof");
            Check(!ack.Snapshot.ObservedPostModeByte.HasValue && !ack.Snapshot.ObservedPostUpperByte.HasValue &&
                !ack.Snapshot.ObservedPostLowerByte.HasValue, "acknowledgement invented readbacks");
            ProtectionReviewAdvance(review, WsabiWmiProtectionTransitionStage.PostMode, 1);
            var upper = ProtectionReviewAdvance(review, WsabiWmiProtectionTransitionStage.PostUpper, 80);
            Check(!upper.IsTerminal && !upper.Snapshot.IsStoredReadbackMatchedCandidate, "partial readback completed the review");
            var lower = review.Observe(ProtectionReviewRead(WsabiWmiProtectionTransitionStage.PostLower, 75));
            Equal(WsabiWmiProtectionTransitionDecisionStatus.StoredReadbackMatchedCandidate, lower.Status);
            Equal(WsabiWmiProtectionTransitionReviewStatus.StoredReadbackMatchedCandidate, review.Status);
            Equal(7, lower.Snapshot.AcceptedStages); Check(lower.IsAccepted && lower.IsTerminal, "complete readback did not finish");
            Check(lower.Snapshot.IsStoredReadbackMatchedCandidate && !lower.Snapshot.IsChargeLimitConfirmed,
                "candidate comparison was promoted to charge control");
            Equal((WsabiWmiProtectionTransitionStage?)null, review.NextStage);
            ProtectionReviewAssertNoCapability(lower); ProtectionReviewAssertNoCapability(lower.Snapshot);
        });

        Add("protection transition review stops every nonzero pre mode before threshold or setter evidence", () =>
        {
            for (int mode = 1; mode <= 255; mode++)
            {
                var review = new WsabiWmiProtectionTransitionReview();
                var decision = review.Observe(ProtectionReviewRead(WsabiWmiProtectionTransitionStage.PreMode, mode));
                ProtectionReviewAssertStopped(decision, WsabiWmiProtectionTransitionDecisionStatus.PreModeNotZero);
                Equal((int?)mode, decision.Snapshot.ObservedPreModeByte);
                Equal(0, decision.Snapshot.AcceptedStages); Check(!decision.Snapshot.SetterAcknowledged, "nonzero pre mode reached setter");
                Equal(WsabiWmiProtectionTransitionDecisionStatus.AlreadyTerminal,
                    review.Observe(ProtectionReviewRead(WsabiWmiProtectionTransitionStage.PreMode, 0)).Status);
            }
        });

        Add("protection transition review refuses historical Access1 zero rather than admitting its old observation", () =>
        {
            var review = new WsabiWmiProtectionTransitionReview();
            var decision = review.Observe(new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.PreMode,
                WsabiWmiProtectionTransitionEvidence.HistoricalRead, 0));
            ProtectionReviewAssertStopped(decision, WsabiWmiProtectionTransitionDecisionStatus.HistoricalObservationNotAdmissible);
            ProtectionReviewAssertNoObservedBytes(decision.Snapshot);
            Equal(0, decision.Snapshot.AcceptedStages);
            Equal(WsabiWmiProtectionTransitionDecisionStatus.AlreadyTerminal,
                review.Observe(ProtectionReviewRead(WsabiWmiProtectionTransitionStage.PreMode, 0)).Status);
        });

        Add("protection transition review enforces evidence kind and null byte on the setter stage", () =>
        {
            var readInstead = ProtectionReviewAtSetter();
            ProtectionReviewAssertStopped(readInstead.Observe(ProtectionReviewRead(WsabiWmiProtectionTransitionStage.SemanticSet1, 1)),
                WsabiWmiProtectionTransitionDecisionStatus.UnexpectedEvidence);
            foreach (int value in new[] { int.MinValue, -1, 0, 1, 255, 256, int.MaxValue })
            {
                var review = ProtectionReviewAtSetter();
                var decision = review.Observe(new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.SemanticSet1,
                    WsabiWmiProtectionTransitionEvidence.SetterAcknowledged, value));
                ProtectionReviewAssertStopped(decision, WsabiWmiProtectionTransitionDecisionStatus.InvalidByteValue);
                Check(!decision.Snapshot.SetterAcknowledged, "a valued setter echo became an accepted acknowledgement");
            }
        });

        Add("protection transition review every read stage requires a present bounded byte and accepted current read kind", () =>
        {
            foreach (int stageIndex in new[] { 0, 1, 2, 4, 5, 6 })
            {
                var role = WsabiWmiProtectionTransitionReview.StageOrder[stageIndex];
                foreach (int? value in new int?[] { null, int.MinValue, -1, 256, int.MaxValue })
                {
                    var review = ProtectionReviewBefore(stageIndex);
                    var decision = review.Observe(new WsabiWmiProtectionTransitionObservation(role,
                        WsabiWmiProtectionTransitionEvidence.AcceptedCurrentRead, value));
                    ProtectionReviewAssertStopped(decision, WsabiWmiProtectionTransitionDecisionStatus.InvalidByteValue);
                    Equal(stageIndex, decision.Snapshot.AcceptedStages);
                }
                foreach (var evidence in new[] { WsabiWmiProtectionTransitionEvidence.SetterAcknowledged,
                    (WsabiWmiProtectionTransitionEvidence)(-1), (WsabiWmiProtectionTransitionEvidence)999 })
                {
                    var review = ProtectionReviewBefore(stageIndex);
                    ProtectionReviewAssertStopped(review.Observe(new WsabiWmiProtectionTransitionObservation(role, evidence)),
                        WsabiWmiProtectionTransitionDecisionStatus.UnexpectedEvidence);
                }
            }
        });

        Add("protection transition review rejects unknown rejected and historical evidence at every stage", () =>
        {
            var evidence = new[] { WsabiWmiProtectionTransitionEvidence.Unknown, WsabiWmiProtectionTransitionEvidence.Rejected,
                WsabiWmiProtectionTransitionEvidence.HistoricalRead };
            var expected = new[] { WsabiWmiProtectionTransitionDecisionStatus.ObservationUnknown,
                WsabiWmiProtectionTransitionDecisionStatus.ObservationRejected,
                WsabiWmiProtectionTransitionDecisionStatus.HistoricalObservationNotAdmissible };
            for (int stageIndex = 0; stageIndex < 7; stageIndex++)
            {
                for (int evidenceIndex = 0; evidenceIndex < evidence.Length; evidenceIndex++)
                {
                    var review = ProtectionReviewBefore(stageIndex);
                    var decision = review.Observe(new WsabiWmiProtectionTransitionObservation(
                        WsabiWmiProtectionTransitionReview.StageOrder[stageIndex], evidence[evidenceIndex], 0));
                    ProtectionReviewAssertStopped(decision, expected[evidenceIndex]);
                    Equal(stageIndex, decision.Snapshot.AcceptedStages);
                }
            }
        });

        Add("protection transition review refuses missing reordered repeated and undefined roles without advancing", () =>
        {
            for (int stageIndex = 0; stageIndex < 7; stageIndex++)
            {
                var missing = ProtectionReviewBefore(stageIndex);
                ProtectionReviewAssertStopped(missing.Observe(null), WsabiWmiProtectionTransitionDecisionStatus.MissingObservation);
                foreach (var wrong in WsabiWmiProtectionTransitionReview.StageOrder.Concat(new[] {
                    (WsabiWmiProtectionTransitionStage)(-1), (WsabiWmiProtectionTransitionStage)99 }))
                {
                    if (wrong == WsabiWmiProtectionTransitionReview.StageOrder[stageIndex]) continue;
                    var review = ProtectionReviewBefore(stageIndex);
                    var decision = review.Observe(ProtectionReviewRead(wrong, 0));
                    ProtectionReviewAssertStopped(decision, WsabiWmiProtectionTransitionDecisionStatus.UnexpectedStage);
                    Equal(stageIndex, decision.Snapshot.AcceptedStages);
                }
            }
        });

        Add("protection transition review each post mismatch is terminal and keeps expected distinct from observed", () =>
        {
            var expected = new[] { 1, 80, 75 };
            var statuses = new[] { WsabiWmiProtectionTransitionDecisionStatus.PostModeMismatch,
                WsabiWmiProtectionTransitionDecisionStatus.PostUpperMismatch,
                WsabiWmiProtectionTransitionDecisionStatus.PostLowerMismatch };
            for (int offset = 0; offset < 3; offset++)
            {
                for (int value = 0; value <= 255; value++)
                {
                    if (value == expected[offset]) continue;
                    var review = ProtectionReviewBefore(offset + 4);
                    var decision = review.Observe(ProtectionReviewRead(WsabiWmiProtectionTransitionReview.StageOrder[offset + 4], value));
                    ProtectionReviewAssertStopped(decision, statuses[offset]);
                    var snapshot = decision.Snapshot;
                    int? observed = offset == 0 ? snapshot.ObservedPostModeByte : offset == 1
                        ? snapshot.ObservedPostUpperByte : snapshot.ObservedPostLowerByte;
                    Equal((int?)value, observed);
                    Equal(1, snapshot.ExpectedPostModeByte); Equal(80, snapshot.ExpectedPostUpperByte); Equal(75, snapshot.ExpectedPostLowerByte);
                    Check(snapshot.SetterAcknowledged && !snapshot.IsStoredReadbackMatchedCandidate,
                        "a post mismatch forgot acknowledgement or claimed a match");
                }
            }
        });

        Add("protection transition review old decisions and snapshots remain detached from later observations", () =>
        {
            var review = new WsabiWmiProtectionTransitionReview(); var initial = review.Snapshot;
            var first = ProtectionReviewAdvance(review, WsabiWmiProtectionTransitionStage.PreMode, 0);
            var before = first.Snapshot;
            ProtectionReviewAdvance(review, WsabiWmiProtectionTransitionStage.PreUpper, 255);
            Equal(0, initial.AcceptedStages); ProtectionReviewAssertNoObservedBytes(initial);
            Equal(1, before.AcceptedStages); Equal((int?)0, before.ObservedPreModeByte);
            Check(!before.ObservedPreUpperByte.HasValue, "later evidence mutated an earlier snapshot");
            Equal((WsabiWmiProtectionTransitionStage?)WsabiWmiProtectionTransitionStage.PreUpper, first.NextStage);
            Equal((int?)255, review.Snapshot.ObservedPreUpperByte);
            foreach (var property in typeof(WsabiWmiProtectionTransitionSnapshot).GetProperties())
                Check(!property.CanWrite && property.PropertyType != typeof(int?[]), "snapshot exposes writable state");
        });

        Add("protection transition review setter acknowledgement followed by unknown never claims unchanged or retries", () =>
        {
            var review = ProtectionReviewBefore(4);
            var decision = review.Observe(new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.PostMode,
                WsabiWmiProtectionTransitionEvidence.Unknown));
            ProtectionReviewAssertStopped(decision, WsabiWmiProtectionTransitionDecisionStatus.ObservationUnknown);
            Check(decision.Snapshot.SetterAcknowledged && !decision.Snapshot.ObservedPostModeByte.HasValue,
                "unknown after acknowledgement fabricated final state");
            Equal(WsabiWmiProtectionTransitionDecisionStatus.AlreadyTerminal,
                review.Observe(ProtectionReviewRead(WsabiWmiProtectionTransitionStage.PostMode, 1)).Status);
            Equal(4, review.Snapshot.AcceptedStages);
            Check(!review.Snapshot.IsStoredReadbackMatchedCandidate, "late evidence retried a stopped review");
        });

        Add("protection transition review completion is single use with no reverse transition or reset", () =>
        {
            var review = ProtectionReviewBefore(7); var complete = review.Snapshot;
            for (int index = 0; index < 7; index++)
            {
                var decision = review.Observe(ProtectionReviewRead(WsabiWmiProtectionTransitionReview.StageOrder[index], 0));
                Equal(WsabiWmiProtectionTransitionDecisionStatus.AlreadyTerminal, decision.Status);
                Check(!decision.IsAccepted && decision.IsTerminal, "completed review accepted another stage");
                Equal(7, decision.Snapshot.AcceptedStages);
                Equal(WsabiWmiProtectionTransitionReviewStatus.StoredReadbackMatchedCandidate, decision.Snapshot.Status);
            }
            Check(complete.IsStoredReadbackMatchedCandidate && !complete.IsChargeLimitConfirmed, "comparison gained charge-control meaning");
        });

        AddAsync("protection transition review concurrent duplicate evidence cannot spend a stage twice", async () =>
        {
            var review = new WsabiWmiProtectionTransitionReview();
            var evidence = ProtectionReviewRead(WsabiWmiProtectionTransitionStage.PreMode, 0);
            var tasks = Enumerable.Range(0, 24).Select(index => Task.Run(() => review.Observe(evidence))).ToArray();
            var decisions = await Task.WhenAll(tasks);
            Equal(1, decisions.Count(value => value.IsAccepted));
            Equal(1, decisions.Count(value => value.Status == WsabiWmiProtectionTransitionDecisionStatus.UnexpectedStage));
            Equal(22, decisions.Count(value => value.Status == WsabiWmiProtectionTransitionDecisionStatus.AlreadyTerminal));
            Equal(1, review.Snapshot.AcceptedStages); Equal(WsabiWmiProtectionTransitionReviewStatus.Stopped, review.Status);
            Check(!review.Snapshot.SetterAcknowledged, "duplicate evidence reached setter acknowledgement");
        });

        Add("protection transition review API contains only fixed evidence roles and numeric facts", () =>
        {
            var method = typeof(WsabiWmiProtectionTransitionReview).GetMethod("Observe");
            Equal(typeof(WsabiWmiProtectionTransitionObservation), method.GetParameters().Single().ParameterType);
            Equal(1, typeof(WsabiWmiProtectionTransitionReview).GetConstructors().Length);
            Equal(0, typeof(WsabiWmiProtectionTransitionReview).GetConstructors()[0].GetParameters().Length);
            var observation = ProtectionReviewRead(WsabiWmiProtectionTransitionStage.PreMode, 0);
            ProtectionReviewAssertNoCapability(observation);
            foreach (var property in typeof(WsabiWmiProtectionTransitionObservation).GetProperties())
                Check(property.PropertyType.IsEnum || property.PropertyType == typeof(int?) || property.PropertyType == typeof(bool),
                    "observation accepts a runtime object or raw identifying text");
            var publicNames = typeof(WsabiWmiProtectionTransitionReview).GetMethods(BindingFlags.Public | BindingFlags.Instance)
                .Where(value => value.DeclaringType == typeof(WsabiWmiProtectionTransitionReview) && !value.IsSpecialName)
                .Select(value => value.Name).ToArray();
            Check(!publicNames.Any(name => name.Contains("Reset") || name.Contains("Dispatch") || name.Contains("Rollback") ||
                name.Contains("Execute") || name.Contains("Invoke")), "pure review exposes a runtime operation");
        });
    }

    private static WsabiWmiProtectionTransitionObservation ProtectionReviewRead(WsabiWmiProtectionTransitionStage role, int value)
        => new WsabiWmiProtectionTransitionObservation(role, WsabiWmiProtectionTransitionEvidence.AcceptedCurrentRead, value);

    private static WsabiWmiProtectionTransitionDecision ProtectionReviewAdvance(WsabiWmiProtectionTransitionReview review,
        WsabiWmiProtectionTransitionStage role, int value)
    {
        var decision = review.Observe(ProtectionReviewRead(role, value));
        Equal(WsabiWmiProtectionTransitionDecisionStatus.Advanced, decision.Status);
        Check(decision.IsAccepted && !decision.IsTerminal, "accepted stage did not wait for later evidence");
        return decision;
    }

    private static WsabiWmiProtectionTransitionReview ProtectionReviewAtSetter() => ProtectionReviewBefore(3);

    private static WsabiWmiProtectionTransitionReview ProtectionReviewBefore(int stageIndex)
    {
        var review = new WsabiWmiProtectionTransitionReview();
        int[] values = { 0, 0, 255, 0, 1, 80, 75 };
        for (int index = 0; index < stageIndex; index++)
        {
            var role = WsabiWmiProtectionTransitionReview.StageOrder[index];
            var observation = role == WsabiWmiProtectionTransitionStage.SemanticSet1
                ? new WsabiWmiProtectionTransitionObservation(role, WsabiWmiProtectionTransitionEvidence.SetterAcknowledged)
                : ProtectionReviewRead(role, values[index]);
            var decision = review.Observe(observation);
            Equal(index == 6 ? WsabiWmiProtectionTransitionDecisionStatus.StoredReadbackMatchedCandidate
                : WsabiWmiProtectionTransitionDecisionStatus.Advanced, decision.Status);
        }
        return review;
    }

    private static void ProtectionReviewAssertStopped(WsabiWmiProtectionTransitionDecision decision,
        WsabiWmiProtectionTransitionDecisionStatus expected)
    {
        Equal(expected, decision.Status);
        Equal(WsabiWmiProtectionTransitionReviewStatus.Stopped, decision.Snapshot.Status);
        Check(!decision.IsAccepted && decision.IsTerminal && !decision.NextStage.HasValue &&
            !decision.Snapshot.IsStoredReadbackMatchedCandidate, "failed evidence can continue a transition");
        ProtectionReviewAssertNoCapability(decision); ProtectionReviewAssertNoCapability(decision.Snapshot);
    }

    private static void ProtectionReviewAssertNoObservedBytes(WsabiWmiProtectionTransitionSnapshot snapshot)
    {
        Check(!snapshot.ObservedPreModeByte.HasValue && !snapshot.ObservedPreUpperByte.HasValue &&
            !snapshot.ObservedPreLowerByte.HasValue && !snapshot.ObservedPostModeByte.HasValue &&
            !snapshot.ObservedPostUpperByte.HasValue && !snapshot.ObservedPostLowerByte.HasValue,
            "expected or historical values became current observations");
    }

    private static void ProtectionReviewAssertNoCapability(object value)
    {
        foreach (var property in value.GetType().GetProperties())
            if (property.Name == "IsExecutable" || property.Name == "IsHardwareObservation" ||
                property.Name == "IsChargeLimitConfirmed" || property.Name.StartsWith("Can", StringComparison.Ordinal))
                Equal(false, (bool)property.GetValue(value));
    }
}
