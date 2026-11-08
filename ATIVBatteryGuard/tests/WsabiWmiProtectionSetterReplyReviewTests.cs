using System;
using System.Linq;
using System.Reflection;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiProtectionSetterReplyReviewTests()
    {
        Add("setter reply review accepts only semantic input one and bounded detached comparison cells", () =>
        {
            foreach (int mode in new[] { int.MinValue, -1, 0, 2, 255, int.MaxValue })
                BatteryThrows<ArgumentOutOfRangeException>(() => new WsabiWmiProtectionSetterReplyReview(mode, 42, ProtectionSetterComparison()));
            foreach (int second in new[] { -1, 256, int.MaxValue })
                BatteryThrows<ArgumentOutOfRangeException>(() => new WsabiWmiProtectionSetterReplyReview(1, second, ProtectionSetterComparison()));
            foreach (object content in new object[] { null, "private input", new byte[7], new byte[9], new byte[8], new int[8],
                new byte[1, 8], Array.CreateInstance(typeof(byte), new[] { 8 }, new[] { 1 }), new ArraySegment<byte>(new byte[8]) })
                BatteryThrows<ArgumentException>(() => new WsabiWmiProtectionSetterReplyReview(1, 42, content));
            foreach (int second in new[] { 0, 255 })
                Check(new WsabiWmiProtectionSetterReplyReview(1, second, ProtectionSetterComparison()) != null,
                    "bounded preserved message component was rejected");
            for (int index = 0; index < 8; index++)
            {
                var singleNonzero = new byte[8]; singleNonzero[index] = 1;
                Check(new WsabiWmiProtectionSetterReplyReview(1, 42, singleNonzero) != null,
                    "comparison validation accidentally required every cell to be nonzero");
            }
        });

        Add("setter normal preserved input is receipt only and never setter execution or changed stored state", () =>
        {
            var result = ProtectionSetterReview().Evaluate(ProtectionSetterExchange(ProtectionSetterReply()));
            ProtectionSetterAssert(result, WsabiWmiProtectionSetterReplyReviewStatus.ReceiptOnly);
            Check(result.IsReceiptOnly, "normal echo was rejected using the reader anti-echo rule");
            Equal(WsabiWmiProtectionTransitionStage.SemanticSet1, result.Role);
            // The same detached tuple can arise after normal handling or after
            // upload-only echo. The reviewer cannot observe which event ran.
            var indistinguishable = ProtectionSetterReview().Evaluate(ProtectionSetterExchange(ProtectionSetterReply()));
            Equal(result.Status, indistinguishable.Status);
            Check(!result.HasSemanticAcknowledgement && !result.IsSetterExecutionConfirmed &&
                !result.IsStoredChangeConfirmed && !result.IsActualCloseConfirmed,
                "transport echo was promoted into execution, state or lifetime evidence");
        });

        Add("setter reply first message byte must remain input one and is not an independent stored mode", () =>
        {
            for (int sample = 0; sample <= 255; sample++)
            {
                var reply = ProtectionSetterReply(); reply[7] = (byte)sample;
                ProtectionSetterAssert(ProtectionSetterReview().Evaluate(ProtectionSetterExchange(reply)), sample == 1
                    ? WsabiWmiProtectionSetterReplyReviewStatus.ReceiptOnly : WsabiWmiProtectionSetterReplyReviewStatus.UnexpectedInputEcho);
            }
        });

        Add("setter reply rejects the common failure even when outer ACK and sample zero are present", () =>
        {
            var raw = new byte[21]; raw[4] = 0xaa; raw[5] = 0xff;
            var exchange = ProtectionSetterExchange(raw);
            Check(exchange.IsValidFrame && exchange.Payload[2] == 0, "fixture did not exercise structurally normal failure zero");
            ProtectionSetterAssert(ProtectionSetterReview().Evaluate(exchange), WsabiWmiProtectionSetterReplyReviewStatus.DispatchFailurePrefix);
        });

        Add("setter reply checks every control and cleared tail cell before trusting a receipt shape", () =>
        {
            foreach (int index in new[] { 5, 6, 17, 18, 19, 20 })
            foreach (byte value in new byte[] { 1, 255 })
            {
                var raw = ProtectionSetterReply(); raw[index] = value;
                ProtectionSetterAssert(ProtectionSetterReview().Evaluate(ProtectionSetterExchange(raw)), index < 7
                    ? WsabiWmiProtectionSetterReplyReviewStatus.UnexpectedControlPrefix : WsabiWmiProtectionSetterReplyReviewStatus.UnexpectedClearedTail);
            }
        });

        Add("setter reply preserves the second message component and every comparison cell", () =>
        {
            for (int index = 8; index <= 16; index++)
            {
                var raw = ProtectionSetterReply(); raw[index] ^= 1;
                ProtectionSetterAssert(ProtectionSetterReview().Evaluate(ProtectionSetterExchange(raw)), index == 8
                    ? WsabiWmiProtectionSetterReplyReviewStatus.PreservedSecondComponentMismatch
                    : WsabiWmiProtectionSetterReplyReviewStatus.PreservedContentMismatch);
            }
        });

        Add("setter no copy and previous comparison mismatches do not become receipt or changed state", () =>
        {
            var zero = new byte[21]; zero[4] = 0xaa;
            ProtectionSetterAssert(ProtectionSetterReview().Evaluate(ProtectionSetterExchange(zero)), WsabiWmiProtectionSetterReplyReviewStatus.UnexpectedInputEcho);
            zero[7] = 1; zero[8] = 42;
            ProtectionSetterAssert(ProtectionSetterReview().Evaluate(ProtectionSetterExchange(zero)), WsabiWmiProtectionSetterReplyReviewStatus.PreservedContentMismatch);
            var other = ProtectionSetterComparison(); other[7] ^= 1;
            var review = new WsabiWmiProtectionSetterReplyReview(1, 42, other);
            ProtectionSetterAssert(review.Evaluate(ProtectionSetterExchange(ProtectionSetterReply())), WsabiWmiProtectionSetterReplyReviewStatus.PreservedContentMismatch);
        });

        Add("setter reply rejects missing malformed bounds and ACK without inspecting an apparent input echo", () =>
        {
            foreach (object raw in new object[] { null, new byte[20], new byte[22], new byte[1, 21], new int[21],
                Array.CreateInstance(typeof(byte), new[] { 21 }, new[] { -1 }), new ArraySegment<byte>(ProtectionSetterReply()) })
                ProtectionSetterAssert(ProtectionSetterReview().Evaluate(ProtectionSetterExchange(raw)), WsabiWmiProtectionSetterReplyReviewStatus.FrameRejected);
            var wrongAck = ProtectionSetterReply(); wrongAck[4] = 0;
            ProtectionSetterAssert(ProtectionSetterReview().Evaluate(ProtectionSetterExchange(wrongAck)), WsabiWmiProtectionSetterReplyReviewStatus.FrameRejected);
        });

        Add("setter API and method envelope failures cannot be hidden by well formed receipt bytes", () =>
        {
            foreach (var status in Enum.GetValues(typeof(WsabiWmiMethodReplyStatus)).Cast<WsabiWmiMethodReplyStatus>())
            {
                if (status == WsabiWmiMethodReplyStatus.FrameChecked) continue;
                var reply = WsabiWmiReplyResult.FromMethodReply(new WsabiWmiMethodReplyResult(status));
                ProtectionSetterAssert(ProtectionSetterReview().Evaluate(new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived, reply)),
                    WsabiWmiProtectionSetterReplyReviewStatus.MethodEnvelopeRejected);
            }
            var binder = OneShotExperimentBinder(1);
            foreach (int api in new[] { 1, -1, int.MinValue, int.MaxValue })
            {
                var reply = WsabiWmiReplyResult.FromMethodReply(binder.DecodeOutput(api, OneShotExperimentOutput(ProtectionSetterReply())));
                ProtectionSetterAssert(ProtectionSetterReview().Evaluate(new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived, reply)),
                    WsabiWmiProtectionSetterReplyReviewStatus.MethodEnvelopeRejected);
            }
            var unbound = WsabiWmiReplyDecoder.Decode(0, ProtectionSetterReply());
            ProtectionSetterAssert(ProtectionSetterReview().Evaluate(new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived, unbound)),
                WsabiWmiProtectionSetterReplyReviewStatus.MethodEnvelopeRejected);
        });

        Add("setter exchange failures retain their sanitized distinction without changed or unchanged claims", () =>
        {
            var review = ProtectionSetterReview();
            ProtectionSetterAssert(review.Evaluate(null), WsabiWmiProtectionSetterReplyReviewStatus.MissingExchange);
            var expected = new[] { WsabiWmiProtectionSetterReplyReviewStatus.ExchangeInvalidRequest, WsabiWmiProtectionSetterReplyReviewStatus.ExchangeCancelled,
                WsabiWmiProtectionSetterReplyReviewStatus.ExchangeBusy, WsabiWmiProtectionSetterReplyReviewStatus.ExchangeTimedOut,
                WsabiWmiProtectionSetterReplyReviewStatus.ExchangeTransportFailure };
            int index = 0;
            foreach (var status in new[] { WsabiWmiFrameExchangeStatus.InvalidRequest, WsabiWmiFrameExchangeStatus.Cancelled,
                WsabiWmiFrameExchangeStatus.Busy, WsabiWmiFrameExchangeStatus.TimedOut, WsabiWmiFrameExchangeStatus.TransportFailure })
                ProtectionSetterAssert(review.Evaluate(new WsabiWmiFrameExchangeResult(status)), expected[index++]);
        });

        Add("setter comparison and detached response snapshots cannot be mutated through caller arrays", () =>
        {
            var comparison = ProtectionSetterComparison();
            var review = new WsabiWmiProtectionSetterReplyReview(1, 42, comparison);
            Array.Clear(comparison, 0, comparison.Length);
            var raw = ProtectionSetterReply(); var exchange = ProtectionSetterExchange(raw);
            Array.Clear(raw, 0, raw.Length);
            var leakedCopy = exchange.Payload; Array.Clear(leakedCopy, 0, leakedCopy.Length);
            ProtectionSetterAssert(review.Evaluate(exchange), WsabiWmiProtectionSetterReplyReviewStatus.ReceiptOnly);
            ProtectionSetterAssert(review.Evaluate(exchange), WsabiWmiProtectionSetterReplyReviewStatus.ReceiptOnly);
            var modified = ProtectionSetterReply(); modified[10] ^= 1;
            ProtectionSetterAssert(review.Evaluate(ProtectionSetterExchange(modified)), WsabiWmiProtectionSetterReplyReviewStatus.PreservedContentMismatch);
            ProtectionSetterAssert(review.Evaluate(exchange), WsabiWmiProtectionSetterReplyReviewStatus.ReceiptOnly);
        });

        Add("setter detached reviewer has no public execution or automatic transition conversion surface", () =>
        {
            var type = typeof(WsabiWmiProtectionSetterReplyReview);
            Check(!type.IsPublic && !typeof(WsabiWmiProtectionSetterReplyReviewResult).IsPublic, "internal review became a public control API");
            foreach (var method in type.GetMethods(BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly))
                Check(method.ReturnType != typeof(WsabiWmiProtectionTransitionObservation) && method.ReturnType != typeof(WsabiWmiMethodRequest),
                    "receipt review automatically supplied a current observation or a request");
            foreach (var property in typeof(WsabiWmiProtectionSetterReplyReviewResult).GetProperties(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                Check((property.PropertyType.IsEnum || property.PropertyType == typeof(bool)) && !property.CanWrite,
                    "sanitized receipt exposed mutable or raw private data");
            var review = ProtectionSetterReview();
            Check(!review.IsExecutable && !review.CanInvokeMethods && !review.CanReadHardware && !review.CanWriteHardware, "review enabled hardware access");
        });
    }

    private static byte[] ProtectionSetterComparison() => new byte[] { 11, 22, 33, 44, 55, 66, 77, 88 };
    private static WsabiWmiProtectionSetterReplyReview ProtectionSetterReview()
        => new WsabiWmiProtectionSetterReplyReview(1, 42, ProtectionSetterComparison());
    private static byte[] ProtectionSetterReply()
    {
        // Synthetic RESPONSE with zero header, never an executable request.
        var raw = new byte[21]; raw[4] = 0xaa; raw[7] = 1; raw[8] = 42;
        Array.Copy(ProtectionSetterComparison(), 0, raw, 9, 8); return raw;
    }
    private static WsabiWmiFrameExchangeResult ProtectionSetterExchange(object raw)
        => new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived,
            WsabiWmiReplyResult.FromMethodReply(new WsabiWmiMethodReplyResult(WsabiWmiMethodReplyStatus.FrameChecked,
                WsabiWmiReplyDecoder.Decode(0, raw))));
    private static void ProtectionSetterAssert(WsabiWmiProtectionSetterReplyReviewResult result, WsabiWmiProtectionSetterReplyReviewStatus expected)
    {
        Equal(expected, result.Status); Equal(expected == WsabiWmiProtectionSetterReplyReviewStatus.ReceiptOnly, result.IsReceiptOnly);
        Check(!result.IsSetterExecutionConfirmed && !result.HasSemanticAcknowledgement && !result.IsStoredChangeConfirmed &&
            !result.IsActualCloseConfirmed && !result.IsChargeLimitConfirmed && !result.CanSupplyTransitionObservation &&
            !result.IsHardwareObservation && !result.IsExecutable && !result.CanInvokeMethods && !result.CanReadHardware && !result.CanWriteHardware,
            "detached receipt became execution, state, lifetime or charging authority");
    }
}
