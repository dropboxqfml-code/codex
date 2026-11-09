using System;
using System.Linq;
using System.Reflection;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiProtectionDisableSetterReplyReviewTests()
    {
        Add("disable setter reply review accepts only semantic input zero and bounded detached comparison cells", () =>
        {
            foreach (int mode in new[] { int.MinValue, -1, 1, 2, 255, int.MaxValue })
                BatteryThrows<ArgumentOutOfRangeException>(() => new WsabiWmiProtectionDisableSetterReplyReview(mode, 42, DisableSetterComparison()));
            foreach (int second in new[] { -1, 256, int.MaxValue })
                BatteryThrows<ArgumentOutOfRangeException>(() => new WsabiWmiProtectionDisableSetterReplyReview(0, second, DisableSetterComparison()));
            foreach (object content in new object[] { null, "private input", new byte[7], new byte[9], new byte[8], new int[8],
                new byte[1, 8], Array.CreateInstance(typeof(byte), new[] { 8 }, new[] { 1 }), new ArraySegment<byte>(new byte[8]) })
                BatteryThrows<ArgumentException>(() => new WsabiWmiProtectionDisableSetterReplyReview(0, 42, content));
            foreach (int second in new[] { 0, 255 })
                Check(new WsabiWmiProtectionDisableSetterReplyReview(0, second, DisableSetterComparison()) != null,
                    "bounded preserved message component was rejected");
            for (int index = 0; index < 8; index++)
            {
                var singleNonzero = new byte[8]; singleNonzero[index] = 1;
                Check(new WsabiWmiProtectionDisableSetterReplyReview(0, 42, singleNonzero) != null,
                    "comparison validation accidentally required every cell to be nonzero");
            }
        });

        Add("disable setter normal preserved input is receipt only and never setter execution or changed stored state", () =>
        {
            var result = DisableSetterReview().Evaluate(DisableSetterExchange(DisableSetterReply()));
            DisableSetterAssert(result, WsabiWmiProtectionDisableSetterReplyReviewStatus.ReceiptOnly);
            Check(result.IsReceiptOnly, "normal echo was rejected using the reader anti-echo rule");
            Equal(WsabiWmiProtectionDisableStage.SemanticSet0, result.Role);
            // The same detached tuple can arise after normal handling or after
            // upload-only echo. The reviewer cannot observe which event ran.
            var indistinguishable = DisableSetterReview().Evaluate(DisableSetterExchange(DisableSetterReply()));
            Equal(result.Status, indistinguishable.Status);
            Check(!result.HasSemanticAcknowledgement && !result.IsSetterExecutionConfirmed &&
                !result.IsStoredChangeConfirmed && !result.IsActualCloseConfirmed,
                "transport echo was promoted into execution, state or lifetime evidence");
        });

        Add("disable setter reply first message byte must remain input zero and is not an independent stored mode", () =>
        {
            for (int sample = 0; sample <= 255; sample++)
            {
                var reply = DisableSetterReply(); reply[7] = (byte)sample;
                DisableSetterAssert(DisableSetterReview().Evaluate(DisableSetterExchange(reply)), sample == 0
                    ? WsabiWmiProtectionDisableSetterReplyReviewStatus.ReceiptOnly : WsabiWmiProtectionDisableSetterReplyReviewStatus.UnexpectedInputEcho);
            }
        });

        Add("disable setter reply rejects the common failure even when outer ACK and sample zero are present", () =>
        {
            var raw = new byte[21]; raw[4] = 0xaa; raw[5] = 0xff;
            var exchange = DisableSetterExchange(raw);
            Check(exchange.IsValidFrame && exchange.Payload[2] == 0, "fixture did not exercise structurally normal failure zero");
            DisableSetterAssert(DisableSetterReview().Evaluate(exchange), WsabiWmiProtectionDisableSetterReplyReviewStatus.DispatchFailurePrefix);
        });

        Add("disable setter reply checks every control and cleared tail cell before trusting a receipt shape", () =>
        {
            foreach (int index in new[] { 5, 6, 17, 18, 19, 20 })
            foreach (byte value in new byte[] { 1, 255 })
            {
                var raw = DisableSetterReply(); raw[index] = value;
                DisableSetterAssert(DisableSetterReview().Evaluate(DisableSetterExchange(raw)), index < 7
                    ? WsabiWmiProtectionDisableSetterReplyReviewStatus.UnexpectedControlPrefix : WsabiWmiProtectionDisableSetterReplyReviewStatus.UnexpectedClearedTail);
            }
        });

        Add("disable setter reply preserves the second message component and every comparison cell", () =>
        {
            for (int index = 8; index <= 16; index++)
            {
                var raw = DisableSetterReply(); raw[index] ^= 1;
                DisableSetterAssert(DisableSetterReview().Evaluate(DisableSetterExchange(raw)), index == 8
                    ? WsabiWmiProtectionDisableSetterReplyReviewStatus.PreservedSecondComponentMismatch
                    : WsabiWmiProtectionDisableSetterReplyReviewStatus.PreservedContentMismatch);
            }
        });

        Add("disable setter no copy and previous comparison mismatches do not become receipt or changed state", () =>
        {
            var zero = new byte[21]; zero[4] = 0xaa;
            DisableSetterAssert(DisableSetterReview().Evaluate(DisableSetterExchange(zero)), WsabiWmiProtectionDisableSetterReplyReviewStatus.PreservedSecondComponentMismatch);
            zero[7] = 0; zero[8] = 42;
            DisableSetterAssert(DisableSetterReview().Evaluate(DisableSetterExchange(zero)), WsabiWmiProtectionDisableSetterReplyReviewStatus.PreservedContentMismatch);
            var other = DisableSetterComparison(); other[7] ^= 1;
            var review = new WsabiWmiProtectionDisableSetterReplyReview(0, 42, other);
            DisableSetterAssert(review.Evaluate(DisableSetterExchange(DisableSetterReply())), WsabiWmiProtectionDisableSetterReplyReviewStatus.PreservedContentMismatch);
        });

        Add("disable setter reply rejects missing malformed bounds and ACK without inspecting an apparent input echo", () =>
        {
            foreach (object raw in new object[] { null, new byte[20], new byte[22], new byte[1, 21], new int[21],
                Array.CreateInstance(typeof(byte), new[] { 21 }, new[] { -1 }), new ArraySegment<byte>(DisableSetterReply()) })
                DisableSetterAssert(DisableSetterReview().Evaluate(DisableSetterExchange(raw)), WsabiWmiProtectionDisableSetterReplyReviewStatus.FrameRejected);
            var wrongAck = DisableSetterReply(); wrongAck[4] = 0;
            DisableSetterAssert(DisableSetterReview().Evaluate(DisableSetterExchange(wrongAck)), WsabiWmiProtectionDisableSetterReplyReviewStatus.FrameRejected);
        });

        Add("disable setter API and method envelope failures cannot be hidden by well formed receipt bytes", () =>
        {
            foreach (var status in Enum.GetValues(typeof(WsabiWmiMethodReplyStatus)).Cast<WsabiWmiMethodReplyStatus>())
            {
                if (status == WsabiWmiMethodReplyStatus.FrameChecked) continue;
                var reply = WsabiWmiReplyResult.FromMethodReply(new WsabiWmiMethodReplyResult(status));
                DisableSetterAssert(DisableSetterReview().Evaluate(new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived, reply)),
                    WsabiWmiProtectionDisableSetterReplyReviewStatus.MethodEnvelopeRejected);
            }
            var binder = OneShotExperimentBinder(1);
            foreach (int api in new[] { 1, -1, int.MinValue, int.MaxValue })
            {
                var reply = WsabiWmiReplyResult.FromMethodReply(binder.DecodeOutput(api, OneShotExperimentOutput(DisableSetterReply())));
                DisableSetterAssert(DisableSetterReview().Evaluate(new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived, reply)),
                    WsabiWmiProtectionDisableSetterReplyReviewStatus.MethodEnvelopeRejected);
            }
            var unbound = WsabiWmiReplyDecoder.Decode(0, DisableSetterReply());
            DisableSetterAssert(DisableSetterReview().Evaluate(new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived, unbound)),
                WsabiWmiProtectionDisableSetterReplyReviewStatus.MethodEnvelopeRejected);
        });

        Add("disable setter exchange failures retain their sanitized distinction without changed or unchanged claims", () =>
        {
            var review = DisableSetterReview();
            DisableSetterAssert(review.Evaluate(null), WsabiWmiProtectionDisableSetterReplyReviewStatus.MissingExchange);
            var expected = new[] { WsabiWmiProtectionDisableSetterReplyReviewStatus.ExchangeInvalidRequest, WsabiWmiProtectionDisableSetterReplyReviewStatus.ExchangeCancelled,
                WsabiWmiProtectionDisableSetterReplyReviewStatus.ExchangeBusy, WsabiWmiProtectionDisableSetterReplyReviewStatus.ExchangeTimedOut,
                WsabiWmiProtectionDisableSetterReplyReviewStatus.ExchangeTransportFailure };
            int index = 0;
            foreach (var status in new[] { WsabiWmiFrameExchangeStatus.InvalidRequest, WsabiWmiFrameExchangeStatus.Cancelled,
                WsabiWmiFrameExchangeStatus.Busy, WsabiWmiFrameExchangeStatus.TimedOut, WsabiWmiFrameExchangeStatus.TransportFailure })
                DisableSetterAssert(review.Evaluate(new WsabiWmiFrameExchangeResult(status)), expected[index++]);
        });

        Add("disable setter comparison and detached response snapshots cannot be mutated through caller arrays", () =>
        {
            var comparison = DisableSetterComparison();
            var review = new WsabiWmiProtectionDisableSetterReplyReview(0, 42, comparison);
            Array.Clear(comparison, 0, comparison.Length);
            var raw = DisableSetterReply(); var exchange = DisableSetterExchange(raw);
            Array.Clear(raw, 0, raw.Length);
            var leakedCopy = exchange.Payload; Array.Clear(leakedCopy, 0, leakedCopy.Length);
            DisableSetterAssert(review.Evaluate(exchange), WsabiWmiProtectionDisableSetterReplyReviewStatus.ReceiptOnly);
            DisableSetterAssert(review.Evaluate(exchange), WsabiWmiProtectionDisableSetterReplyReviewStatus.ReceiptOnly);
            var modified = DisableSetterReply(); modified[10] ^= 1;
            DisableSetterAssert(review.Evaluate(DisableSetterExchange(modified)), WsabiWmiProtectionDisableSetterReplyReviewStatus.PreservedContentMismatch);
            DisableSetterAssert(review.Evaluate(exchange), WsabiWmiProtectionDisableSetterReplyReviewStatus.ReceiptOnly);
        });

        Add("disable setter detached reviewer has no public execution or automatic transition conversion surface", () =>
        {
            var type = typeof(WsabiWmiProtectionDisableSetterReplyReview);
            Check(!type.IsPublic && !typeof(WsabiWmiProtectionDisableSetterReplyReviewResult).IsPublic, "internal review became a public control API");
            foreach (var method in type.GetMethods(BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly))
                Check(method.ReturnType != typeof(WsabiWmiProtectionDisableObservation) && method.ReturnType != typeof(WsabiWmiMethodRequest),
                    "receipt review automatically supplied a current observation or a request");
            foreach (var property in typeof(WsabiWmiProtectionDisableSetterReplyReviewResult).GetProperties(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                Check((property.PropertyType.IsEnum || property.PropertyType == typeof(bool)) && !property.CanWrite,
                    "sanitized receipt exposed mutable or raw private data");
            var review = DisableSetterReview();
            Check(!review.IsExecutable && !review.CanInvokeMethods && !review.CanReadHardware && !review.CanWriteHardware, "review enabled hardware access");
        });
    }

    private static byte[] DisableSetterComparison() => new byte[] { 11, 22, 33, 44, 55, 66, 77, 88 };
    private static WsabiWmiProtectionDisableSetterReplyReview DisableSetterReview()
        => new WsabiWmiProtectionDisableSetterReplyReview(0, 42, DisableSetterComparison());
    private static byte[] DisableSetterReply()
    {
        // Synthetic RESPONSE with zero header, never an executable request.
        var raw = new byte[21]; raw[4] = 0xaa; raw[7] = 0; raw[8] = 42;
        Array.Copy(DisableSetterComparison(), 0, raw, 9, 8); return raw;
    }
    private static WsabiWmiFrameExchangeResult DisableSetterExchange(object raw)
        => new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived,
            WsabiWmiReplyResult.FromMethodReply(new WsabiWmiMethodReplyResult(WsabiWmiMethodReplyStatus.FrameChecked,
                WsabiWmiReplyDecoder.Decode(0, raw))));
    private static void DisableSetterAssert(WsabiWmiProtectionDisableSetterReplyReviewResult result, WsabiWmiProtectionDisableSetterReplyReviewStatus expected)
    {
        Equal(expected, result.Status); Equal(expected == WsabiWmiProtectionDisableSetterReplyReviewStatus.ReceiptOnly, result.IsReceiptOnly);
        Check(!result.IsSetterExecutionConfirmed && !result.HasSemanticAcknowledgement && !result.IsStoredChangeConfirmed &&
            !result.IsActualCloseConfirmed && !result.IsChargeLimitConfirmed && !result.CanSupplyTransitionObservation &&
            !result.IsHardwareObservation && !result.IsExecutable && !result.CanInvokeMethods && !result.CanReadHardware && !result.CanWriteHardware,
            "detached receipt became execution, state, lifetime or charging authority");
    }
}
