using System;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiReplyValidatorTests()
    {
        Add("wsabi WMI copies all sixteen payload bytes without sharing caller storage", () =>
        {
            byte[] reply = WsabiReply();
            reply[0] = 9; reply[1] = 8; reply[2] = 7; reply[3] = 6;
            byte[] payload;
            Check(WsabiWmiReplyValidator.TryExtractPayload(0, reply, out payload), "valid WMI frame rejected");
            Equal(16, payload.Length);
            for (int i = 0; i < payload.Length; i++) Equal((byte)(i * 13 + 3), payload[i]);
            Check(!ReferenceEquals(reply, payload), "response storage retained");
            reply[5] = 255;
            Equal((byte)3, payload[0]);
            payload[15] = 255;
            Equal((byte)198, reply[20]);
        });

        Add("wsabi WMI rejects S_FALSE errors and malformed array shapes while clearing stale data", () =>
        {
            foreach (int code in new[] { 1, 2, -1, int.MinValue, int.MaxValue, unchecked((int)0x8fff0004) })
            {
                byte[] payload = { 42 };
                Check(!WsabiWmiReplyValidator.TryExtractPayload(code, WsabiReply(), out payload), "non-S_OK accepted");
                Equal(0, payload.Length);
            }
            object[] invalid =
            {
                null, new object(), "bytes", new byte[0], new byte[11], new byte[16], new byte[20], new byte[22],
                new int[21], new object[21], new byte[21][], new byte[3, 7], new byte[1, 21], new byte[1, 1, 21],
                Array.CreateInstance(typeof(byte), new[] { 21 }, new[] { 1 }),
                Array.CreateInstance(typeof(byte), new[] { 21 }, new[] { -1 })
            };
            foreach (object bytes in invalid)
            {
                byte[] payload = { 42 };
                Check(!WsabiWmiReplyValidator.TryExtractPayload(0, bytes, out payload), "malformed byte array accepted");
                Equal(0, payload.Length);
            }
        });

        Add("wsabi WMI rejects every acknowledgement other than AA", () =>
        {
            byte[] reply = WsabiReply();
            for (int marker = 0; marker < 256; marker++)
            {
                if (marker == 0xaa) continue;
                reply[4] = (byte)marker;
                byte[] payload = { 42 };
                Check(!WsabiWmiReplyValidator.TryExtractPayload(0, reply, out payload), "wrong acknowledgement accepted");
                Equal(0, payload.Length);
                Equal((byte)marker, reply[4]);
            }
        });

        Add("wsabi WMI and Sabi3 x64 payload and frame dimensions remain separate", () =>
        {
            byte[] nativeReply = new byte[Sabi3X64Abi.DriverReplyBytes]; nativeReply[4] = 0xaa;
            byte[] nativePayload;
            Check(Sabi3X64Abi.TryExtractDriverPayload(true, nativeReply.Length, nativeReply, out nativePayload), "valid native frame rejected");
            Equal(11, nativePayload.Length);
            byte[] wmiReply = WsabiReply();
            byte[] wmiPayload;
            Check(WsabiWmiReplyValidator.TryExtractPayload(0, wmiReply, out wmiPayload), "valid WMI frame rejected");
            Equal(16, wmiPayload.Length);

            byte[] rejected = { 42 };
            Check(!WsabiWmiReplyValidator.TryExtractPayload(0, nativeReply, out rejected), "native frame treated as WMI frame");
            Equal(0, rejected.Length);
            Check(!WsabiWmiReplyValidator.TryExtractPayload(0, nativePayload, out rejected), "native payload treated as WMI frame");
            Equal(0, rejected.Length);
            Check(!Sabi3X64Abi.TryExtractDriverPayload(true, wmiReply.Length, wmiReply, out rejected), "WMI frame treated as native frame");
            Equal(0, rejected.Length);
            Equal(Sabi3ReplyState.InvalidResponse, Sabi3ReplyDecoder.Decode(0, wmiPayload).State);
        });
    }

    private static byte[] WsabiReply()
    {
        var reply = new byte[21]; reply[4] = 0xaa;
        for (int i = 0; i < 16; i++) reply[5 + i] = (byte)(i * 13 + 3);
        return reply;
    }
}
