using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    // Deliberately artificial expectation components, not firmware targets.
    private const int ProtectionReadReviewSyntheticFirst = 173;
    private const int ProtectionReadReviewSyntheticSecond = 91;

    private static void RegisterWsabiWmiProtectionReadReplyReviewTests()
    {
        Add("protection read reply expectation rejects nonread roles malformed components and nonexact comparison arrays", () =>
        {
            foreach (var role in new[] { WsabiWmiProtectionTransitionStage.SemanticSet1,
                (WsabiWmiProtectionTransitionStage)(-1), (WsabiWmiProtectionTransitionStage)99 })
                BatteryThrows<ArgumentOutOfRangeException>(() => new WsabiWmiProtectionReadReplyReview(role, 0, 0, ProtectionReadReviewComparison()));
            foreach (int invalid in new[] { -1, 256, int.MinValue, int.MaxValue })
            {
                BatteryThrows<ArgumentOutOfRangeException>(() => new WsabiWmiProtectionReadReplyReview(WsabiWmiProtectionTransitionStage.PreUpper,
                    invalid, 0, ProtectionReadReviewComparison()));
                BatteryThrows<ArgumentOutOfRangeException>(() => new WsabiWmiProtectionReadReplyReview(WsabiWmiProtectionTransitionStage.PreUpper,
                    0, invalid, ProtectionReadReviewComparison()));
            }
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiProtectionReadReplyReview(WsabiWmiProtectionTransitionStage.PreUpper, 0, 0, null));
            object[] invalidComparison =
            {
                new byte[0], new byte[7], new byte[9], new byte[8], new int[8], new byte[1, 8],
                new List<byte>(ProtectionReadReviewComparison()), new ArraySegment<byte>(ProtectionReadReviewComparison()),
                Array.CreateInstance(typeof(byte), new[] { 8 }, new[] { 1 }),
                Array.CreateInstance(typeof(byte), new[] { 8 }, new[] { -1 })
            };
            foreach (object malformed in invalidComparison)
                BatteryThrows<ArgumentException>(() => new WsabiWmiProtectionReadReplyReview(WsabiWmiProtectionTransitionStage.PreUpper, 0, 0, malformed));
            var oneNonzero = new byte[8]; oneNonzero[7] = 1;
            var boundary = new WsabiWmiProtectionReadReplyReview(WsabiWmiProtectionTransitionStage.PreUpper, 255, 255, oneNonzero);
            var raw = ProtectionReadReviewRaw(254, 255, oneNonzero);
            ProtectionReadReviewAssert(boundary.Evaluate(ProtectionReadReviewExchange(raw)),
                WsabiWmiProtectionTransitionStage.PreUpper, WsabiWmiProtectionReadReplyReviewStatus.CorrelatedStoredByteCandidate, 254);
        });

        Add("protection read reply all six roles classify every byte with threshold domain distinct from mode and echo", () =>
        {
            foreach (var role in ProtectionReadReviewRoles())
            {
                var review = ProtectionReadReviewCreate(role);
                for (int candidate = 0; candidate <= 255; candidate++)
                {
                    bool mode = role == WsabiWmiProtectionTransitionStage.PreMode || role == WsabiWmiProtectionTransitionStage.PostMode;
                    var status = candidate == ProtectionReadReviewSyntheticFirst ? WsabiWmiProtectionReadReplyReviewStatus.AmbiguousInputEcho
                        : mode && candidate > 1 ? WsabiWmiProtectionReadReplyReviewStatus.CandidateOutsideDomain
                        : WsabiWmiProtectionReadReplyReviewStatus.CorrelatedStoredByteCandidate;
                    ProtectionReadReviewAssert(review.Evaluate(ProtectionReadReviewExchange(ProtectionReadReviewRaw((byte)candidate))),
                        role, status, status == WsabiWmiProtectionReadReplyReviewStatus.CorrelatedStoredByteCandidate ? (int?)candidate : null);
                }
            }
        });

        Add("protection read reply equal input component is ambiguous even when it is a legitimate mode or threshold byte", () =>
        {
            foreach (var role in ProtectionReadReviewRoles())
            foreach (int first in new[] { 0, 1, 75, 80, 173, 255 })
            {
                var review = new WsabiWmiProtectionReadReplyReview(role, first, ProtectionReadReviewSyntheticSecond, ProtectionReadReviewComparison());
                ProtectionReadReviewAssert(review.Evaluate(ProtectionReadReviewExchange(ProtectionReadReviewRaw((byte)first))),
                    role, WsabiWmiProtectionReadReplyReviewStatus.AmbiguousInputEcho);
            }
        });

        Add("protection read reply each control and cleared tail cell is required for every read role", () =>
        {
            foreach (var role in ProtectionReadReviewRoles())
            foreach (int index in new[] { 5, 6, 17, 18, 19, 20 })
            foreach (byte wrong in new byte[] { 1, 127, 255 })
            {
                var raw = ProtectionReadReviewRaw(1); raw[index] = wrong;
                ProtectionReadReviewAssert(ProtectionReadReviewCreate(role).Evaluate(ProtectionReadReviewExchange(raw)), role,
                    index < 7 ? WsabiWmiProtectionReadReplyReviewStatus.UnexpectedControlPrefix
                        : WsabiWmiProtectionReadReplyReviewStatus.UnexpectedClearedTail);
            }
        });

        Add("protection read reply common dispatcher failure cannot become a zero candidate despite valid envelope ACK and sample", () =>
        {
            foreach (var role in ProtectionReadReviewRoles())
            {
                var raw = new byte[21]; raw[4] = 0xaa; raw[5] = 0xff;
                var exchange = ProtectionReadReviewExchange(raw);
                Check(exchange.IsValidFrame && exchange.Payload[2] == 0, "failure fixture did not contain the misleading zero sample");
                ProtectionReadReviewAssert(ProtectionReadReviewCreate(role).Evaluate(exchange), role,
                    WsabiWmiProtectionReadReplyReviewStatus.DispatchFailurePrefix);
            }
        });

        Add("protection read reply retained second component and every comparison cell must match the expectation", () =>
        {
            foreach (var role in ProtectionReadReviewRoles())
            foreach (int index in Enumerable.Range(8, 9))
            {
                var raw = ProtectionReadReviewRaw(1); raw[index] ^= 1;
                ProtectionReadReviewAssert(ProtectionReadReviewCreate(role).Evaluate(ProtectionReadReviewExchange(raw)), role,
                    index == 8 ? WsabiWmiProtectionReadReplyReviewStatus.PreservedSecondComponentMismatch
                        : WsabiWmiProtectionReadReplyReviewStatus.PreservedContentMismatch);
            }
        });

        Add("protection read reply no-copy zero content remains rejected with or without the preserved second component", () =>
        {
            foreach (var role in ProtectionReadReviewRoles())
            {
                var review = ProtectionReadReviewCreate(role); var raw = new byte[21]; raw[4] = 0xaa;
                ProtectionReadReviewAssert(review.Evaluate(ProtectionReadReviewExchange(raw)), role,
                    WsabiWmiProtectionReadReplyReviewStatus.PreservedSecondComponentMismatch);
                raw[8] = ProtectionReadReviewSyntheticSecond;
                ProtectionReadReviewAssert(review.Evaluate(ProtectionReadReviewExchange(raw)), role,
                    WsabiWmiProtectionReadReplyReviewStatus.PreservedContentMismatch);
            }
        });

        Add("protection read reply method field failures and detached frame-only results cannot supply candidates", () =>
        {
            foreach (var role in ProtectionReadReviewRoles())
            {
                var review = ProtectionReadReviewCreate(role);
                foreach (var status in Enum.GetValues(typeof(WsabiWmiMethodReplyStatus)).Cast<WsabiWmiMethodReplyStatus>())
                {
                    if (status == WsabiWmiMethodReplyStatus.FrameChecked) continue;
                    var reply = WsabiWmiReplyResult.FromMethodReply(new WsabiWmiMethodReplyResult(status));
                    ProtectionReadReviewAssert(review.Evaluate(new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived, reply)),
                        role, WsabiWmiProtectionReadReplyReviewStatus.MethodEnvelopeRejected);
                }
                var detached = WsabiWmiReplyDecoder.Decode(0, ProtectionReadReviewRaw(1));
                ProtectionReadReviewAssert(review.Evaluate(new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived, detached)),
                    role, WsabiWmiProtectionReadReplyReviewStatus.MethodEnvelopeRejected);
            }
        });

        Add("protection read reply raw response type shape length API and ACK failures remain frame rejections", () =>
        {
            object[] malformed =
            {
                null, new byte[0], new byte[20], new byte[22], new byte[1, 21], new int[21],
                new ArraySegment<byte>(ProtectionReadReviewRaw(1)), new List<byte>(ProtectionReadReviewRaw(1)),
                Array.CreateInstance(typeof(byte), new[] { 21 }, new[] { 1 }),
                Array.CreateInstance(typeof(byte), new[] { 21 }, new[] { -1 })
            };
            foreach (var role in ProtectionReadReviewRoles())
            {
                var review = ProtectionReadReviewCreate(role);
                foreach (object raw in malformed)
                    ProtectionReadReviewAssert(review.Evaluate(ProtectionReadReviewExchange(raw)), role,
                        WsabiWmiProtectionReadReplyReviewStatus.FrameRejected);
                foreach (int api in new[] { 1, -1, int.MinValue, int.MaxValue })
                    ProtectionReadReviewAssert(review.Evaluate(ProtectionReadReviewExchange(ProtectionReadReviewRaw(1), api)), role,
                        WsabiWmiProtectionReadReplyReviewStatus.FrameRejected);
                var invalidAck = ProtectionReadReviewRaw(1); invalidAck[4] = 0;
                ProtectionReadReviewAssert(review.Evaluate(ProtectionReadReviewExchange(invalidAck)), role,
                    WsabiWmiProtectionReadReplyReviewStatus.FrameRejected);
            }
        });

        Add("protection read reply missing cancelled busy timed-out and transport-failed exchanges stay distinct with no candidate", () =>
        {
            var expected = new[]
            {
                WsabiWmiProtectionReadReplyReviewStatus.ExchangeInvalidRequest, WsabiWmiProtectionReadReplyReviewStatus.ExchangeCancelled,
                WsabiWmiProtectionReadReplyReviewStatus.ExchangeBusy, WsabiWmiProtectionReadReplyReviewStatus.ExchangeTimedOut,
                WsabiWmiProtectionReadReplyReviewStatus.ExchangeTransportFailure
            };
            var statuses = new[] { WsabiWmiFrameExchangeStatus.InvalidRequest, WsabiWmiFrameExchangeStatus.Cancelled,
                WsabiWmiFrameExchangeStatus.Busy, WsabiWmiFrameExchangeStatus.TimedOut, WsabiWmiFrameExchangeStatus.TransportFailure };
            foreach (var role in ProtectionReadReviewRoles())
            {
                var review = ProtectionReadReviewCreate(role);
                ProtectionReadReviewAssert(review.Evaluate(null), role, WsabiWmiProtectionReadReplyReviewStatus.MissingExchange);
                for (int i = 0; i < statuses.Length; i++)
                    ProtectionReadReviewAssert(review.Evaluate(new WsabiWmiFrameExchangeResult(statuses[i])), role, expected[i]);
            }
        });

        Add("protection read reply expectation owns its comparison snapshot and does not modify the caller arrays or exchange payload", () =>
        {
            var comparison = ProtectionReadReviewComparison(); var original = (byte[])comparison.Clone();
            var review = new WsabiWmiProtectionReadReplyReview(WsabiWmiProtectionTransitionStage.PreUpper,
                ProtectionReadReviewSyntheticFirst, ProtectionReadReviewSyntheticSecond, comparison);
            Check(comparison.SequenceEqual(original), "construction changed supplied comparison cells");
            comparison[0] ^= 1;
            var raw = ProtectionReadReviewRaw(80, ProtectionReadReviewSyntheticSecond, original); var savedRaw = (byte[])raw.Clone();
            var exchange = ProtectionReadReviewExchange(raw); var before = exchange.Payload;
            var result = review.Evaluate(exchange);
            ProtectionReadReviewAssert(result, WsabiWmiProtectionTransitionStage.PreUpper,
                WsabiWmiProtectionReadReplyReviewStatus.CorrelatedStoredByteCandidate, 80);
            Check(raw.SequenceEqual(savedRaw) && exchange.Payload.SequenceEqual(before), "evaluation modified supplied raw or retained reply data");
            var changed = ProtectionReadReviewRaw(80, ProtectionReadReviewSyntheticSecond, comparison);
            ProtectionReadReviewAssert(review.Evaluate(ProtectionReadReviewExchange(changed)), WsabiWmiProtectionTransitionStage.PreUpper,
                WsabiWmiProtectionReadReplyReviewStatus.PreservedContentMismatch);
        });

        Add("protection read reply another comparison expectation cannot silently relabel the same preserved response", () =>
        {
            var comparison = ProtectionReadReviewComparison(); comparison[7] ^= 1;
            var first = ProtectionReadReviewCreate(WsabiWmiProtectionTransitionStage.PostUpper);
            var second = new WsabiWmiProtectionReadReplyReview(WsabiWmiProtectionTransitionStage.PostUpper,
                ProtectionReadReviewSyntheticFirst, ProtectionReadReviewSyntheticSecond, comparison);
            var exchange = ProtectionReadReviewExchange(ProtectionReadReviewRaw(80));
            ProtectionReadReviewAssert(first.Evaluate(exchange), WsabiWmiProtectionTransitionStage.PostUpper,
                WsabiWmiProtectionReadReplyReviewStatus.CorrelatedStoredByteCandidate, 80);
            ProtectionReadReviewAssert(second.Evaluate(exchange), WsabiWmiProtectionTransitionStage.PostUpper,
                WsabiWmiProtectionReadReplyReviewStatus.PreservedContentMismatch);
        });

        Add("protection read reply role is an expectation label and matching data never authenticates target freshness or a transition stage", () =>
        {
            var exchange = ProtectionReadReviewExchange(ProtectionReadReviewRaw(80));
            var upper = ProtectionReadReviewCreate(WsabiWmiProtectionTransitionStage.PostUpper).Evaluate(exchange);
            var lower = ProtectionReadReviewCreate(WsabiWmiProtectionTransitionStage.PostLower).Evaluate(exchange);
            ProtectionReadReviewAssert(upper, WsabiWmiProtectionTransitionStage.PostUpper,
                WsabiWmiProtectionReadReplyReviewStatus.CorrelatedStoredByteCandidate, 80);
            ProtectionReadReviewAssert(lower, WsabiWmiProtectionTransitionStage.PostLower,
                WsabiWmiProtectionReadReplyReviewStatus.CorrelatedStoredByteCandidate, 80);
            // The same data fits both supplied labels. A target adapter and
            // attribution contract do not exist in this detached reviewer.
            var numericReview = new WsabiWmiProtectionTransitionReview();
            Equal(0, numericReview.Snapshot.AcceptedStages);
            Equal(WsabiWmiProtectionTransitionReviewStatus.AwaitingObservation, numericReview.Status);
            foreach (var method in typeof(WsabiWmiProtectionReadReplyReview).GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly))
                Check(method.ReturnType != typeof(WsabiWmiProtectionTransitionObservation), "reply review automatically promotes its numeric result to current evidence");
        });

        Add("protection read reply results remain immutable and detached across later evaluation and caller mutation", () =>
        {
            var review = ProtectionReadReviewCreate(WsabiWmiProtectionTransitionStage.PreUpper);
            var raw = ProtectionReadReviewRaw(75); var exchange = ProtectionReadReviewExchange(raw);
            var first = review.Evaluate(exchange);
            Array.Clear(raw, 0, raw.Length);
            ProtectionReadReviewAssert(first, WsabiWmiProtectionTransitionStage.PreUpper,
                WsabiWmiProtectionReadReplyReviewStatus.CorrelatedStoredByteCandidate, 75);
            ProtectionReadReviewAssert(review.Evaluate(ProtectionReadReviewExchange(ProtectionReadReviewRaw(173))),
                WsabiWmiProtectionTransitionStage.PreUpper, WsabiWmiProtectionReadReplyReviewStatus.AmbiguousInputEcho);
            ProtectionReadReviewAssert(first, WsabiWmiProtectionTransitionStage.PreUpper,
                WsabiWmiProtectionReadReplyReviewStatus.CorrelatedStoredByteCandidate, 75);
            foreach (var property in typeof(WsabiWmiProtectionReadReplyReviewResult).GetProperties(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
            {
                Check(!property.CanWrite, "reply result has a mutable property");
                Check(property.PropertyType.IsEnum || property.PropertyType == typeof(bool) || property.PropertyType == typeof(int?),
                    "sanitized result carries raw context or identifying data");
            }
        });

        Add("protection read reply internal API offers only detached evaluation and cannot enable any hardware capability", () =>
        {
            var type = typeof(WsabiWmiProtectionReadReplyReview);
            Check(type.IsSealed && !type.IsPublic && !typeof(WsabiWmiProtectionReadReplyReviewResult).IsPublic,
                "detached reply review became a public execution entry");
            Equal(0, type.GetConstructors().Length);
            var review = ProtectionReadReviewCreate(WsabiWmiProtectionTransitionStage.PreUpper);
            Check(!review.IsExecutable && !review.IsHardwareObservation && !review.IsCurrentRead && !review.IsFreshnessProven &&
                !review.IsChargeLimitConfirmed && !review.CanInvokeMethods && !review.CanReadHardware && !review.CanWriteHardware,
                "expectation construction granted hardware or evidence authority");
            foreach (var property in type.GetProperties(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                Check(property.PropertyType.IsEnum || property.PropertyType == typeof(bool), "expectation exposes raw inputs or an execution handle");
            var result = review.Evaluate(ProtectionReadReviewExchange(ProtectionReadReviewRaw(80)));
            ProtectionReadReviewAssert(result, WsabiWmiProtectionTransitionStage.PreUpper,
                WsabiWmiProtectionReadReplyReviewStatus.CorrelatedStoredByteCandidate, 80);
        });
    }

    private static IEnumerable<WsabiWmiProtectionTransitionStage> ProtectionReadReviewRoles()
        => WsabiWmiProtectionTransitionReview.StageOrder.Where(role => role != WsabiWmiProtectionTransitionStage.SemanticSet1);

    private static byte[] ProtectionReadReviewComparison() => new byte[] { 3, 17, 29, 41, 53, 67, 79, 97 };

    private static WsabiWmiProtectionReadReplyReview ProtectionReadReviewCreate(WsabiWmiProtectionTransitionStage role)
        => new WsabiWmiProtectionReadReplyReview(role, ProtectionReadReviewSyntheticFirst,
            ProtectionReadReviewSyntheticSecond, ProtectionReadReviewComparison());

    private static byte[] ProtectionReadReviewRaw(byte candidate, int second = ProtectionReadReviewSyntheticSecond, byte[] comparison = null)
    {
        // Synthetic detached response only: no request, target or encoder.
        var raw = new byte[21]; raw[4] = 0xaa; raw[7] = candidate; raw[8] = (byte)second;
        Array.Copy(comparison ?? ProtectionReadReviewComparison(), 0, raw, 9, 8);
        return raw;
    }

    private static WsabiWmiFrameExchangeResult ProtectionReadReviewExchange(object raw, int api = 0)
    {
        var frame = WsabiWmiReplyDecoder.Decode(api, raw);
        var method = new WsabiWmiMethodReplyResult(WsabiWmiMethodReplyStatus.FrameChecked, frame);
        return new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived, WsabiWmiReplyResult.FromMethodReply(method));
    }

    private static void ProtectionReadReviewAssert(WsabiWmiProtectionReadReplyReviewResult result,
        WsabiWmiProtectionTransitionStage role, WsabiWmiProtectionReadReplyReviewStatus status, int? candidate = null)
    {
        Equal(role, result.Role); Equal(status, result.Status); Equal(candidate, result.Candidate);
        Equal(status == WsabiWmiProtectionReadReplyReviewStatus.CorrelatedStoredByteCandidate, result.IsCorrelatedStoredByteCandidate);
        Check(!result.IsExecutable && !result.IsHardwareObservation && !result.IsCurrentRead && !result.IsFreshnessProven && !result.CanSupplyTransitionObservation &&
            !result.IsChargeLimitConfirmed && !result.CanInvokeMethods && !result.CanReadHardware && !result.CanWriteHardware,
            "detached response classification granted hardware, freshness or charge authority");
    }
}
