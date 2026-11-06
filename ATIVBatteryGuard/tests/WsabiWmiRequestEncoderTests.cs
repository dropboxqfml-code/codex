using System;
using ATIVBatteryGuard.Core.Hardware;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiRequestEncoderTests()
    {
        Add("wsabi request encodes exact header little-endian command and sixteen payload bytes", () =>
        {
            var payload = WsabiRequestPayload();
            foreach (int command in new[] { 0, 1, 0x34, 0x65, 0x7f, 0x80, 0xff })
            {
                byte[] request;
                Check(WsabiWmiRequestEncoder.TryEncode(command, payload, out request), "valid framing rejected");
                Equal(21, request.Length);
                Equal((byte)0x43, request[0]); Equal((byte)0x58, request[1]);
                Equal((byte)(command & 0xff), request[2]); Equal((byte)(command >> 8), request[3]);
                Equal((byte)0, request[4]);
                for (int i = 0; i < payload.Length; i++) Equal(payload[i], request[i + 5]);
            }
        });
        Add("wsabi request refuses out-of-range commands without truncating or retaining prior output", () =>
        {
            var payload = WsabiRequestPayload();
            byte[] request;
            foreach (int command in new[] { int.MinValue, -65536, -1, 0x100, 0x165, 0xffff, 65536, 65537, int.MaxValue })
            {
                Check(WsabiWmiRequestEncoder.TryEncode(0xff, payload, out request), "setup frame rejected");
                Check(!WsabiWmiRequestEncoder.TryEncode(command, payload, out request), "command truncated");
                Equal(0, request.Length);
            }
            for (int i = 0; i < payload.Length; i++) Equal((byte)(i * 17), payload[i]);
        });
        Add("wsabi request rejects every nearby wrong length and non-byte zero-based vector shapes", () =>
        {
            for (int length = 0; length <= 32; length++)
            {
                if (length == 16) continue;
                byte[] request = { 42 };
                Check(!WsabiWmiRequestEncoder.TryEncode(0, new byte[length], out request), "wrong payload length accepted");
                Equal(0, request.Length);
            }
            object[] invalid =
            {
                null, new object(), "0123456789abcdef", new int[16], new object[16], new sbyte[16],
                new byte[16][], new byte[1, 16], new byte[2, 8], new byte[1, 1, 16],
                Array.CreateInstance(typeof(byte), new[] { 16 }, new[] { 1 }),
                Array.CreateInstance(typeof(byte), new[] { 16 }, new[] { -1 })
            };
            foreach (object payload in invalid)
            {
                byte[] request = { 42 };
                Check(!WsabiWmiRequestEncoder.TryEncode(0, payload, out request), "payload type or shape coerced");
                Equal(0, request.Length);
            }
        });
        Add("wsabi request snapshots payload and allocates independent output on every success", () =>
        {
            byte[] payload = WsabiRequestPayload();
            byte[] first, second;
            Check(WsabiWmiRequestEncoder.TryEncode(0x34, payload, out first), "first frame rejected");
            Check(WsabiWmiRequestEncoder.TryEncode(0x34, payload, out second), "second frame rejected");
            Check(!ReferenceEquals(first, second) && !ReferenceEquals(first, payload), "shared output storage");
            first[5] = 19;
            Equal((byte)0, payload[0]); Equal((byte)0, second[5]);
            payload[15] = 0;
            Equal((byte)255, first[20]); Equal((byte)255, second[20]);
            second[0] = 0;
            Equal((byte)0x43, first[0]);
        });
        Add("wsabi request framing retains separate ABI and grants no command or hardware access", () =>
        {
            Equal(WsabiWmiReplyValidator.AnalyzedSha256, WsabiWmiRequestEncoder.AnalyzedSha256);
            Equal(0xff, WsabiWmiRequestEncoder.MaximumSupportedCommand);
            Equal(16, WsabiWmiRequestEncoder.PayloadBytes);
            Equal(21, WsabiWmiRequestEncoder.FrameBytes);
            byte[] request;
            Check(!WsabiWmiRequestEncoder.TryEncode(0, new byte[Sabi3X64Abi.PayloadBytes], out request), "native eleven-byte payload accepted");
            Check(!WsabiWmiRequestEncoder.TryEncode(0, new byte[WsabiWmiRequestEncoder.FrameBytes], out request), "frame reused as payload");
            Check(!WsabiWmiRequestEncoder.CanInvokeMethods && !WsabiWmiRequestEncoder.CanReadHardware &&
                !WsabiWmiRequestEncoder.CanWriteHardware, "framing permits hardware access");
            var controller = new UnsupportedChargeLimitController();
            Check(!controller.GetCapabilities().CanRead && !controller.GetCapabilities().CanWrite, "capability changed");
            Check(!controller.SetMode(ChargeMode.Protection80).Success, "framing enables protection");
        });
    }

    private static byte[] WsabiRequestPayload()
    {
        var payload = new byte[16];
        for (int i = 0; i < payload.Length; i++) payload[i] = (byte)(i * 17);
        return payload;
    }
}
