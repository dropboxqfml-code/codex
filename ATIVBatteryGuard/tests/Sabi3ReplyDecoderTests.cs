using System;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterSabi3ReplyDecoderTests()
    {
        Add("Sabi3 x64 query data uses eleven independent bytes without invoking native code", () =>
        {
            byte[] buffer = Sabi3X64Abi.CreateProtectionStatusBuffer();
            Equal(11, buffer.Length); Equal((byte)0x80, buffer[0]);
            for (int i=1;i<buffer.Length;i++) Equal((byte)0,buffer[i]);
            buffer[0]=0;
            Equal((byte)0x80,Sabi3X64Abi.CreateProtectionStatusBuffer()[0]);
            Equal(Sabi3ReplyState.Unknown,Sabi3ReplyDecoder.Decode(0,Sabi3X64Abi.CreateProtectionStatusBuffer()).State);
        });
        Add("Sabi3 driver reply requires full length and acknowledgement before copying all eleven bytes", () =>
        {
            byte[] reply=new byte[16]; reply[4]=0xaa;
            for(int i=0;i<11;i++)reply[5+i]=(byte)(i+1);
            byte[] payload;
            Check(Sabi3X64Abi.TryExtractDriverPayload(true,16,reply,out payload),"valid reply rejected");
            Equal(11,payload.Length);Equal((byte)1,payload[0]);Equal((byte)11,payload[10]);
            reply[5]=0;
            Equal((byte)1,payload[0]);
        });
        Add("Sabi3 short failed or unacknowledged driver replies discard stale payload", () =>
        {
            byte[] reply=new byte[16];reply[4]=0xaa;
            foreach(int returned in new[]{0,4,5,15,17,int.MaxValue})
            {
                byte[] payload={1};
                Check(!Sabi3X64Abi.TryExtractDriverPayload(true,returned,reply,out payload),"short count accepted");Equal(0,payload.Length);
            }
            foreach(byte[] data in new[]{null,new byte[0],new byte[15],new byte[17]})
            {
                byte[] payload={1};
                Check(!Sabi3X64Abi.TryExtractDriverPayload(true,16,data,out payload),"wrong reply accepted");Equal(0,payload.Length);
            }
            for(int marker=0;marker<256;marker++)
            {
                if(marker==0xaa)continue;reply[4]=(byte)marker;
                byte[] payload={1};
                Check(!Sabi3X64Abi.TryExtractDriverPayload(true,16,reply,out payload),"wrong acknowledgement accepted");Equal(0,payload.Length);
            }
            reply[4]=0xaa;byte[] failed={1};
            Check(!Sabi3X64Abi.TryExtractDriverPayload(false,16,reply,out failed),"failed request accepted");Equal(0,failed.Length);
        });
        Add("Sabi3 unsupported reply is distinct from disabled protection", () =>
        {
            var unsupported = Sabi3ReplyDecoder.Decode(0, SabiPayload(255));
            Equal(Sabi3ReplyState.Unsupported, unsupported.State); Equal<bool?>(null, unsupported.ProtectionEnabled);
            var off = Sabi3ReplyDecoder.Decode(0, new byte[Sabi3X64Abi.PayloadBytes]);
            Equal(Sabi3ReplyState.ProtectionDisabled, off.State); Equal<bool?>(false, off.ProtectionEnabled);
            var on = Sabi3ReplyDecoder.Decode(0, SabiPayload(1));
            Equal(Sabi3ReplyState.ProtectionEnabled, on.State); Equal<bool?>(true, on.ProtectionEnabled);
        });
        Add("Sabi3 unrecognized byte values never become disabled", () =>
        {
            Equal(Sabi3ReplyState.Unknown, new Sabi3ReplyInterpretation((Sabi3ReplyState)999).State);
            for (int state = 2; state < 255; state++)
            {
                var result = Sabi3ReplyDecoder.Decode(0, SabiPayload((byte)state));
                Equal(Sabi3ReplyState.Unknown, result.State); Equal<bool?>(null, result.ProtectionEnabled);
            }
        });
        Add("Sabi3 API failure takes precedence over plausible or stale buffer", () =>
        {
            foreach (int code in new[] { -1, 1, int.MinValue, int.MaxValue })
            foreach (byte[] data in new[] { null, new byte[Sabi3X64Abi.PayloadBytes], SabiPayload(1), SabiPayload(255) })
            {
                var result = Sabi3ReplyDecoder.Decode(code, data);
                Equal(Sabi3ReplyState.ApiError, result.State); Equal<bool?>(null, result.ProtectionEnabled);
            }
        });
        Add("Sabi3 x64 buffer requires eleven bytes and rejects the old four byte example", () =>
        {
            foreach (byte[] data in new[] { null, new byte[0], new byte[1], new byte[3], new byte[4], new byte[5], new byte[10], new byte[12], new byte[4096] })
                Equal(Sabi3ReplyState.InvalidResponse, Sabi3ReplyDecoder.Decode(0, data).State);
        });
        Add("Sabi3 decoded toggle never asserts a percent limit hardware read or write support", () =>
        {
            for (int state = 0; state < 256; state++)
            {
                var result = Sabi3ReplyDecoder.Decode(0, SabiPayload((byte)state));
                Equal<int?>(null, result.ChargeLimitPercent);
                Check(!result.IsVerifiedHardwareObservation && !result.HardwareWriteAllowed, "interpreted bytes promoted to verified device state");
            }
        });
        Add("Sabi3 reply decoding does not mutate input or retain a live buffer", () =>
        {
            byte[] buffer = SabiPayload(1); buffer[1] = 20; buffer[10] = 40;
            var result = Sabi3ReplyDecoder.Decode(0, buffer);
            Equal((byte)1, buffer[0]); Equal((byte)20, buffer[1]);
            buffer[0] = 0;
            Equal(Sabi3ReplyState.ProtectionEnabled, result.State);
        });
    }
    private static byte[] SabiPayload(byte first)
    {
        var result = new byte[Sabi3X64Abi.PayloadBytes]; result[0] = first; return result;
    }

}
