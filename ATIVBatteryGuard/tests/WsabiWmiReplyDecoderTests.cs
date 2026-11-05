using System;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiReplyDecoderTests()
    {
        Add("P05ACJ failure prefix comparison retains structural frame status and grants no hardware meaning", () =>
        {
            var bytes = new byte[21]; bytes[4] = 0xaa; bytes[5] = 0xff;
            var result = WsabiWmiReplyDecoder.Decode(0, bytes);
            Equal(WsabiWmiReplyStatus.ValidFrame, result.Status);
            Equal(WsabiWmiDispatchFailurePrefix.MatchesAnalyzedP05AcjPrefix, result.DispatchFailurePrefix);
            Check(!result.IsHardwareObservation && !result.CanReadHardware && !result.CanWriteHardware && !result.CanInvokeMethods,
                "a source pattern granted a hardware claim");
            Equal((byte)0xff, result.Payload[0]);
            Equal("2795669f18e3fb787d908ba00e2e9da7ab7d398ee599f27aa2f068129b46f310",
                WsabiWmiReplyResult.AnalyzedDispatchModuleSha256);
        });
        Add("P05ACJ failure prefix requires every supported payload byte rather than its first marker", () =>
        {
            var bytes = new byte[21]; bytes[4] = 0xaa;
            for (int first = 0; first < 255; first++)
            {
                bytes[5] = (byte)first;
                var result = WsabiWmiReplyDecoder.Decode(0, bytes);
                Equal(WsabiWmiReplyStatus.ValidFrame, result.Status);
                Equal(WsabiWmiDispatchFailurePrefix.DiffersFromAnalyzedP05AcjPrefix, result.DispatchFailurePrefix);
                Check(!result.CanReadHardware && !result.CanWriteHardware, "a different pattern granted capabilities");
            }
            bytes[5] = 0xff;
            for (int offset = 6; offset < bytes.Length; offset++)
            for (int value = 1; value < 256; value++)
            {
                bytes[offset] = (byte)value;
                var result = WsabiWmiReplyDecoder.Decode(0, bytes);
                Equal(WsabiWmiDispatchFailurePrefix.DiffersFromAnalyzedP05AcjPrefix, result.DispatchFailurePrefix);
                Equal(WsabiWmiReplyStatus.ValidFrame, result.Status);
                bytes[offset] = 0;
            }
        });
        Add("P05ACJ failure prefix is not inspected for failed frames or rejected envelopes", () =>
        {
            var bytes = new byte[21]; bytes[4] = 0xaa; bytes[5] = 0xff;
            foreach (var result in new[] {
                WsabiWmiReplyDecoder.Decode(1, bytes), WsabiWmiReplyDecoder.Decode(0, null),
                WsabiWmiReplyDecoder.Decode(0, new byte[20]), WsabiWmiReplyDecoder.Decode(0, new byte[21]),
                WsabiWmiReplyDecoder.Decode(0, new byte[1, 21]), WsabiWmiReplyDecoder.Decode(0, "private") })
                Equal(WsabiWmiDispatchFailurePrefix.NotInspected, result.DispatchFailurePrefix);
            var binder = OneShotExperimentBinder(1);
            var rejected = WsabiWmiReplyResult.FromMethodReply(binder.DecodeOutput(0, null));
            Equal(WsabiWmiDispatchFailurePrefix.NotInspected, rejected.DispatchFailurePrefix);
            var checkedReply = WsabiWmiReplyResult.FromMethodReply(binder.DecodeOutput(0, OneShotExperimentOutput(bytes)));
            Equal<WsabiWmiMethodReplyStatus?>(WsabiWmiMethodReplyStatus.FrameChecked, checkedReply.MethodReplyStatus);
            Equal(WsabiWmiDispatchFailurePrefix.MatchesAnalyzedP05AcjPrefix, checkedReply.DispatchFailurePrefix);
        });
        Add("P05ACJ failure prefix uses isolated validated payload snapshots", () =>
        {
            var bytes = new byte[21]; bytes[4] = 0xaa; bytes[5] = 0xff;
            var result = WsabiWmiReplyDecoder.Decode(0, bytes);
            bytes[5] = 1;
            var copy = result.Payload; copy[1] = 1;
            Equal(WsabiWmiDispatchFailurePrefix.MatchesAnalyzedP05AcjPrefix, result.DispatchFailurePrefix);
            Equal((byte)0xff, result.Payload[0]); Equal((byte)0, result.Payload[1]);
        });
        Add("historical FF review explains the firmware source without inventing a complete failure pattern", () =>
        {
            var result = WsabiWmiExperimentReviewParser.Parse(ExperimentReviewFixture(0xff));
            Equal(WsabiWmiExperimentReviewStatus.ValidatedFrameMeaningUnknown, result.Status);
            string text = result.ToDisplayText();
            Check(text.Contains("공통 실패 응답 경로") && text.Contains("첫 바이트만") &&
                text.Contains("실패 원인을 확정할 수 없습니다"), "incomplete historical evidence became a definitive failure");
            foreach (byte marker in new byte[] { 0, 1, 0x42 })
                Check(!WsabiWmiExperimentReviewParser.Parse(ExperimentReviewFixture(marker)).ToDisplayText().Contains("공통 실패 응답 경로"),
                    "an unrelated marker was described as firmware failure evidence");
            Check(!WsabiWmiExperimentReviewParser.Parse("후보 표식: FF").ToDisplayText().Contains("공통 실패 응답 경로"),
                "unvalidated historical text gained firmware evidence");
        });
        Add("wsabi typed reply distinguishes API non-success before every response condition", () =>
        {
            object[] responses = { null, new object(), "private response", new byte[0], WsabiReply() };
            foreach (int code in new[] { 1, 2, -1, int.MinValue, int.MaxValue, unchecked((int)0x80041003) })
            foreach (object response in responses)
            {
                var result = WsabiWmiReplyDecoder.Decode(code, response);
                Equal(WsabiWmiReplyStatus.ApiNotSuccessful, result.Status);
                AssertWsabiTypedFailure(result, code, response);
            }
            var missing = WsabiWmiReplyDecoder.Decode(0, null);
            Equal(WsabiWmiReplyStatus.MissingResponse, missing.Status);
            AssertWsabiTypedFailure(missing, 0, null);
        });
        Add("wsabi typed reply separates element type from rank and lower-bound errors", () =>
        {
            object[] types = {
                new object(), "private bytes", new int[21], new sbyte[21], new object[21],
                new byte[21][], new ArraySegment<byte>(new byte[21])
            };
            foreach (object response in types)
            {
                var result = WsabiWmiReplyDecoder.Decode(0, response);
                Equal(WsabiWmiReplyStatus.InvalidType, result.Status);
                AssertWsabiTypedFailure(result, 0, response);
            }
            object[] shapes = {
                new byte[1, 21], new byte[3, 7], new byte[1, 1, 21],
                Array.CreateInstance(typeof(byte), new[] { 21 }, new[] { 1 }),
                Array.CreateInstance(typeof(byte), new[] { 21 }, new[] { -1 })
            };
            foreach (object response in shapes)
            {
                var result = WsabiWmiReplyDecoder.Decode(0, response);
                Equal(WsabiWmiReplyStatus.InvalidShape, result.Status);
                AssertWsabiTypedFailure(result, 0, response);
            }
        });
        Add("wsabi typed reply refuses all nearby and oversized unsupported frame lengths", () =>
        {
            for (int length = 0; length <= 64; length++)
            {
                if (length == 21) continue;
                var response = new byte[length];
                if (length > 4) response[4] = 0xaa;
                var result = WsabiWmiReplyDecoder.Decode(0, response);
                Equal(WsabiWmiReplyStatus.UnsupportedLength, result.Status);
                AssertWsabiTypedFailure(result, 0, response);
            }
            var large = new byte[65536]; large[4] = 0xaa;
            Equal(WsabiWmiReplyStatus.UnsupportedLength, WsabiWmiReplyDecoder.Decode(0, large).Status);
        });
        Add("wsabi typed reply classifies every acknowledgement without inventing header requirements", () =>
        {
            for (int marker = 0; marker < 256; marker++)
            {
                byte[] response = WsabiReply();
                response[0] = 0xff; response[1] = 0; response[2] = 0x65; response[3] = 0x66;
                response[4] = (byte)marker;
                var result = WsabiWmiReplyDecoder.Decode(0, response);
                Equal(marker == 0xaa ? WsabiWmiReplyStatus.ValidFrame : WsabiWmiReplyStatus.InvalidAcknowledgement, result.Status);
                Equal<WsabiWmiMethodReplyStatus?>(null, result.MethodReplyStatus);
                Equal(marker == 0xaa, result.IsValidFrame);
                byte[] legacy;
                Equal(result.IsValidFrame, WsabiWmiReplyValidator.TryExtractPayload(0, response, out legacy));
                Equal(marker == 0xaa ? 16 : 0, legacy.Length);
                Equal((byte)marker, response[4]);
                if (marker != 0xaa) AssertWsabiTypedFailure(result, 0, response);
            }
        });
        Add("wsabi typed reply snapshots all payload bytes and returns independent caller copies", () =>
        {
            byte[] response = WsabiReply();
            var first = WsabiWmiReplyDecoder.Decode(0, response);
            var second = WsabiWmiReplyDecoder.Decode(0, response);
            Equal(WsabiWmiReplyStatus.ValidFrame, first.Status);
            Equal<WsabiWmiMethodReplyStatus?>(null, first.MethodReplyStatus);
            byte[] copy = first.Payload;
            Equal(16, copy.Length);
            for (int i = 0; i < copy.Length; i++) Equal((byte)(i * 13 + 3), copy[i]);
            response[5] = 255; copy[1] = 255;
            Equal((byte)3, first.Payload[0]);
            Equal((byte)16, first.Payload[1]);
            Equal((byte)3, second.Payload[0]);
            Check(!ReferenceEquals(copy, first.Payload) && !ReferenceEquals(first.Payload, second.Payload), "payload storage shared");
            byte[] legacy;
            Check(WsabiWmiReplyValidator.TryExtractPayload(0, WsabiReply(), out legacy), "legacy valid frame rejected");
            legacy[15] = 0;
            Equal((byte)198, first.Payload[15]);
            var failure = WsabiWmiReplyDecoder.Decode(1, response);
            Equal(0, failure.Payload.Length);
            Equal((byte)3, first.Payload[0]);
        });
        Add("wsabi typed reply leaves every payload marker opaque and grants no hardware observation", () =>
        {
            Equal(WsabiWmiReplyValidator.AnalyzedSha256, WsabiWmiReplyDecoder.AnalyzedSha256);
            Equal(21, WsabiWmiReplyDecoder.AcceptedReplyBytes);
            Equal(16, WsabiWmiReplyDecoder.PayloadBytes);
            foreach (byte marker in new byte[] { 0, 1, 0xff })
            {
                byte[] response = WsabiReply();
                for (int i = 5; i < response.Length; i++) response[i] = marker;
                var result = WsabiWmiReplyDecoder.Decode(0, response);
                Check(result.IsValidFrame && !result.IsHardwareObservation && !result.CanReadHardware && !result.CanWriteHardware, "frame promoted to hardware capability");
                foreach (byte value in result.Payload) Equal(marker, value);
            }
            byte[] native = new byte[Sabi3X64Abi.DriverReplyBytes]; native[4] = 0xaa;
            Equal(WsabiWmiReplyStatus.UnsupportedLength, WsabiWmiReplyDecoder.Decode(0, native).Status);
        });
    }

    private static void AssertWsabiTypedFailure(WsabiWmiReplyResult result, int code, object response)
    {
        Equal<WsabiWmiMethodReplyStatus?>(null, result.MethodReplyStatus);
        Check(!result.IsValidFrame && !result.IsHardwareObservation && !result.CanReadHardware && !result.CanWriteHardware, "failed frame promoted to observation");
        Equal(0, result.Payload.Length);
        byte[] legacy = { 42 };
        Check(!WsabiWmiReplyValidator.TryExtractPayload(code, response, out legacy), "legacy acceptance boundary widened");
        Equal(0, legacy.Length);
    }
}
