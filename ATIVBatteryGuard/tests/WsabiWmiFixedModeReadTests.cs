using System;
using System.Linq;
using System.Reflection;
using ATIVBatteryGuard.Core.Hardware;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiFixedModeReadTests()
    {
        Add("fixed mode A request matches independently recovered selector branch address order and byte roles", () =>
        {
            var attempt = FixedModeAttemptCreate();
            // Independent literal expectation from the selected registration,
            // callback and EC reader, not another use of the production encoder.
            byte[] expected =
            {
                0x43, 0x58, 0x7a, 0x00, 0x00, 0x82, 0x80, 0xf0, 0x4f,
                0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0, 0, 0, 0
            };
            Check(attempt.Request.Frame.SequenceEqual(expected), "fixed request differs from the independently recovered roles");
            Equal((uint)1, attempt.Request.ObservedMethodId);
            Equal((ushort)0x7a, attempt.Request.FirmwareCommand);
            Equal(WsabiWmiFixedReadProfile.P05AcjStoredModeReadA, attempt.Profile);
            Check(!attempt.Request.CanInvokeMethods && !attempt.Request.CanReadHardware &&
                !attempt.Request.CanWriteHardware, "request construction grants device access");
            WsabiWmiMethodRequest frozen;
            Check(SingleReadPlanCreate(SingleReadTarget(new object())).TryFreezeRequest(attempt.Request, out frozen),
                "fixed request does not match the existing single-read envelope contract");
            Check(frozen.Frame.SequenceEqual(expected), "plan changed the fixed request");
        });

        Add("fixed mode A random fill is exactly eight bytes once with a detached cleared temporary", () =>
        {
            int calls = 0; byte[] temporary = null; WsabiWmiFixedModeReadAttempt attempt;
            var creation = WsabiWmiFixedModeReadAttempt.TryCreateWithRandom(bytes =>
            {
                calls++; Equal(8, bytes.Length); temporary = bytes;
                bytes[7] = 0x9a;
            }, out attempt);
            Equal(WsabiWmiFixedReadCreationStatus.Created, creation); Equal(1, calls);
            Check(attempt != null && temporary.All(value => value == 0), "random temporary not cleared");
            Equal((byte)0x9a, attempt.Request.Frame[16]);
            temporary[7] = 0x33;
            Equal((byte)0x9a, attempt.Request.Frame[16]);
            var response = FixedModeResponse(attempt, 1);
            Equal(WsabiWmiFixedReadStatus.StoredModeCandidate, attempt.Evaluate(FixedModeExchange(response)).Status);
        });

        Add("fixed mode A zero random content aborts without a retry or request", () =>
        {
            int calls = 0; WsabiWmiFixedModeReadAttempt attempt;
            Equal(WsabiWmiFixedReadCreationStatus.ZeroComparisonContent,
                WsabiWmiFixedModeReadAttempt.TryCreateWithRandom(bytes => { calls++; }, out attempt));
            Equal(1, calls); Check(attempt == null, "zero comparison created a request");
        });

        Add("fixed mode A random failure is sanitized with no request and no retry", () =>
        {
            int calls = 0; byte[] temporary = null; WsabiWmiFixedModeReadAttempt attempt;
            Equal(WsabiWmiFixedReadCreationStatus.RandomSourceUnavailable,
                WsabiWmiFixedModeReadAttempt.TryCreateWithRandom(bytes =>
                {
                    calls++; temporary = bytes; bytes[0] = 1;
                    throw new InvalidOperationException("PRIVATE-RNG path user identifier");
                }, out attempt));
            Equal(1, calls); Check(attempt == null, "random failure created a request");
            Check(temporary.All(value => value == 0), "failed random temporary not cleared");
            Equal(WsabiWmiFixedReadCreationStatus.RandomSourceUnavailable,
                WsabiWmiFixedModeReadAttempt.TryCreateWithRandom(null, out attempt));
            Check(attempt == null, "missing random source created a request");
        });

        Add("fixed mode A request clones cannot modify the retained comparison or selected target", () =>
        {
            var attempt = FixedModeAttemptCreate(); var frame = attempt.Request.Frame;
            var input = (System.Collections.Generic.IReadOnlyDictionary<string, object>)attempt.Request.Arguments["inData"];
            var argument = (byte[])input["Bytes"];
            for (int index = 0; index < frame.Length; index++) { frame[index] ^= 0xff; argument[index] ^= 0xff; }
            Check(attempt.Request.Frame.SequenceEqual(FixedModeAttemptCreate().Request.Frame), "public clone mutated the request");
            FixedModeAssertCandidate(attempt.Evaluate(FixedModeExchange(FixedModeResponse(attempt, 0))), 0);
        });

        Add("fixed mode A accepts only the two stored candidates with every fixed return role preserved", () =>
        {
            var attempt = FixedModeAttemptCreate();
            foreach (byte candidate in new byte[] { 0, 1 })
                FixedModeAssertCandidate(attempt.Evaluate(FixedModeExchange(FixedModeResponse(attempt, candidate))), candidate);
        });

        Add("fixed mode A refuses every sample outside the candidate domain including input echo", () =>
        {
            var attempt = FixedModeAttemptCreate();
            for (int sample = 2; sample <= byte.MaxValue; sample++)
            {
                var result = attempt.Evaluate(FixedModeExchange(FixedModeResponse(attempt, (byte)sample)));
                FixedModeAssertRejected(result, sample == 0xf0 ? WsabiWmiFixedReadStatus.InputEcho
                    : WsabiWmiFixedReadStatus.CandidateOutsideDomain);
            }
        });

        Add("fixed mode A common failure remains rejected even with valid ACK and a zero sample slot", () =>
        {
            var attempt = FixedModeAttemptCreate(); var raw = new byte[21]; raw[4] = 0xaa; raw[5] = 0xff;
            var exchange = FixedModeExchange(raw);
            Check(exchange.IsValidFrame, "fixture did not pass the existing structural decoder");
            Equal((byte)0, exchange.Payload[2]);
            FixedModeAssertRejected(attempt.Evaluate(exchange), WsabiWmiFixedReadStatus.DispatchFailurePrefix);
        });

        Add("fixed mode A every control prefix and cleared tail byte is checked", () =>
        {
            var attempt = FixedModeAttemptCreate();
            foreach (int index in new[] { 5, 6, 17, 18, 19, 20 })
            {
                var raw = FixedModeResponse(attempt, 0); raw[index] = 1;
                FixedModeAssertRejected(attempt.Evaluate(FixedModeExchange(raw)), index < 7
                    ? WsabiWmiFixedReadStatus.UnexpectedControlPrefix : WsabiWmiFixedReadStatus.UnexpectedClearedTail);
            }
            var failureWithPreservedBytes = FixedModeResponse(attempt, 0); failureWithPreservedBytes[5] = 0xff;
            FixedModeAssertRejected(attempt.Evaluate(FixedModeExchange(failureWithPreservedBytes)),
                WsabiWmiFixedReadStatus.UnexpectedControlPrefix);
        });

        Add("fixed mode A retained low address and each of eight comparison cells are mandatory", () =>
        {
            var attempt = FixedModeAttemptCreate();
            for (int index = 8; index <= 16; index++)
            {
                var raw = FixedModeResponse(attempt, 1); raw[index] ^= 1;
                FixedModeAssertRejected(attempt.Evaluate(FixedModeExchange(raw)), index == 8
                    ? WsabiWmiFixedReadStatus.PreservedAddressMismatch : WsabiWmiFixedReadStatus.PreservedContentMismatch);
            }
        });

        Add("fixed mode A no copy zero response cannot become protection off", () =>
        {
            var attempt = FixedModeAttemptCreate(); var raw = new byte[21]; raw[4] = 0xaa;
            FixedModeAssertRejected(attempt.Evaluate(FixedModeExchange(raw)), WsabiWmiFixedReadStatus.PreservedAddressMismatch);
            // Even supplying the retained address cannot replace the nonzero
            // eight-cell comparison with command-only/no-copy zero content.
            raw[8] = 0x4f;
            FixedModeAssertRejected(attempt.Evaluate(FixedModeExchange(raw)), WsabiWmiFixedReadStatus.PreservedContentMismatch);
        });

        Add("fixed mode A another attempt content is not accepted as this attempt response", () =>
        {
            var first = FixedModeAttemptCreate(); var second = FixedModeAttemptCreate(0x22);
            var raw = FixedModeResponse(first, 1);
            FixedModeAssertCandidate(first.Evaluate(FixedModeExchange(raw)), 1);
            FixedModeAssertRejected(second.Evaluate(FixedModeExchange(raw)), WsabiWmiFixedReadStatus.PreservedContentMismatch);
        });

        Add("fixed mode A failures in shape ACK envelope and API cannot yield candidates", () =>
        {
            var attempt = FixedModeAttemptCreate(); var raw = FixedModeResponse(attempt, 0);
            object[] malformed = { null, new byte[20], new byte[22], new byte[1, 21], new int[21] };
            foreach (object response in malformed)
                FixedModeAssertRejected(attempt.Evaluate(FixedModeExchange(response)), WsabiWmiFixedReadStatus.FrameRejected);
            raw[4] = 0;
            FixedModeAssertRejected(attempt.Evaluate(FixedModeExchange(raw)), WsabiWmiFixedReadStatus.FrameRejected);
            foreach (var status in Enum.GetValues(typeof(WsabiWmiMethodReplyStatus)).Cast<WsabiWmiMethodReplyStatus>())
            {
                if (status == WsabiWmiMethodReplyStatus.FrameChecked) continue;
                var reply = WsabiWmiReplyResult.FromMethodReply(new WsabiWmiMethodReplyResult(status));
                FixedModeAssertRejected(attempt.Evaluate(new WsabiWmiFrameExchangeResult(
                    WsabiWmiFrameExchangeStatus.ReplyReceived, reply)), WsabiWmiFixedReadStatus.MethodEnvelopeRejected);
            }
            var detached = WsabiWmiReplyDecoder.Decode(0, FixedModeResponse(attempt, 0));
            FixedModeAssertRejected(attempt.Evaluate(new WsabiWmiFrameExchangeResult(
                WsabiWmiFrameExchangeStatus.ReplyReceived, detached)), WsabiWmiFixedReadStatus.MethodEnvelopeRejected);
        });

        Add("fixed mode A transport failures keep their sanitized distinction and no candidate", () =>
        {
            var attempt = FixedModeAttemptCreate();
            FixedModeAssertRejected(attempt.Evaluate(null), WsabiWmiFixedReadStatus.MissingExchange);
            var expected = new[]
            {
                WsabiWmiFixedReadStatus.ExchangeInvalidRequest, WsabiWmiFixedReadStatus.ExchangeCancelled,
                WsabiWmiFixedReadStatus.ExchangeBusy, WsabiWmiFixedReadStatus.ExchangeTimedOut,
                WsabiWmiFixedReadStatus.ExchangeTransportFailure
            };
            int index = 0;
            foreach (var status in new[] { WsabiWmiFrameExchangeStatus.InvalidRequest, WsabiWmiFrameExchangeStatus.Cancelled,
                WsabiWmiFrameExchangeStatus.Busy, WsabiWmiFrameExchangeStatus.TimedOut, WsabiWmiFrameExchangeStatus.TransportFailure })
                FixedModeAssertRejected(attempt.Evaluate(new WsabiWmiFrameExchangeResult(status)), expected[index++]);
        });

        Add("fixed mode A public input and sanitized output cannot carry arbitrary commands or raw private data", () =>
        {
            var type = typeof(WsabiWmiFixedModeReadAttempt);
            Check(type.IsSealed && type.GetConstructors().Length == 0, "fixed attempt allows public construction");
            var creators = type.GetMethods(BindingFlags.Public | BindingFlags.Static);
            Equal(1, creators.Length); Equal("TryCreate", creators[0].Name);
            Equal(1, creators[0].GetParameters().Length);
            Check(creators[0].GetParameters()[0].IsOut, "public factory accepts request input");
            foreach (var property in typeof(WsabiWmiFixedReadResult).GetProperties())
                Check(property.PropertyType.IsEnum || property.PropertyType == typeof(bool) ||
                    property.PropertyType == typeof(int?), "sanitized result exposes raw or identifying data");
            var controller = new UnsupportedChargeLimitController();
            Check(!controller.GetCapabilities().CanRead && !controller.GetCapabilities().CanWrite, "candidate enabled charge control");
            Check(!controller.SetMode(ChargeMode.Protection80).Success, "fixed read enabled a setting write");
        });
    }

    private static WsabiWmiFixedModeReadAttempt FixedModeAttemptCreate(byte first = 0x11)
    {
        WsabiWmiFixedModeReadAttempt attempt;
        Equal(WsabiWmiFixedReadCreationStatus.Created, WsabiWmiFixedModeReadAttempt.TryCreateWithRandom(bytes =>
        {
            for (int i = 0; i < bytes.Length; i++) bytes[i] = (byte)(first + i * 0x11);
        }, out attempt));
        Check(attempt != null, "deterministic fixed attempt was not created");
        return attempt;
    }

    private static byte[] FixedModeResponse(WsabiWmiFixedModeReadAttempt attempt, byte sample)
    {
        var raw = attempt.Request.Frame;
        raw[4] = 0xaa; raw[5] = 0; raw[6] = 0; raw[7] = sample;
        return raw;
    }

    private static WsabiWmiFrameExchangeResult FixedModeExchange(object raw)
    {
        var frame = WsabiWmiReplyDecoder.Decode(0, raw);
        var method = new WsabiWmiMethodReplyResult(WsabiWmiMethodReplyStatus.FrameChecked, frame);
        return new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived,
            WsabiWmiReplyResult.FromMethodReply(method));
    }

    private static void FixedModeAssertRejected(WsabiWmiFixedReadResult result, WsabiWmiFixedReadStatus expected)
    {
        Equal(expected, result.Status);
        Check(!result.StoredModeCandidate.HasValue && !result.IsStoredModeCandidate, "rejected response retained a candidate");
        Check(!result.IsChargeLimitConfirmed && !result.CanWriteHardware, "rejected response enabled charge control");
    }

    private static void FixedModeAssertCandidate(WsabiWmiFixedReadResult result, int candidate)
    {
        Equal(WsabiWmiFixedReadStatus.StoredModeCandidate, result.Status);
        Equal((int?)candidate, result.StoredModeCandidate);
        Check(result.IsStoredModeCandidate && !result.IsChargeLimitConfirmed && !result.CanWriteHardware,
            "stored candidate was presented as actual charge-limit enforcement");
        Equal(WsabiWmiFixedReadProfile.P05AcjStoredModeReadA, result.Profile);
    }
}
