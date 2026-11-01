using System;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterSabi3ReplyDecoderTests()
    {
        Add("Sabi3 unsupported reply is distinct from disabled protection", () =>
        {
            var unsupported = Sabi3ReplyDecoder.Decode(0, new byte[] { 255, 0, 0, 0 });
            Equal(Sabi3ReplyState.Unsupported, unsupported.State); Equal<bool?>(null, unsupported.ProtectionEnabled);
            var off = Sabi3ReplyDecoder.Decode(0, new byte[4]);
            Equal(Sabi3ReplyState.ProtectionDisabled, off.State); Equal<bool?>(false, off.ProtectionEnabled);
            var on = Sabi3ReplyDecoder.Decode(0, new byte[] { 1, 0, 0, 0 });
            Equal(Sabi3ReplyState.ProtectionEnabled, on.State); Equal<bool?>(true, on.ProtectionEnabled);
        });
        Add("Sabi3 unrecognized byte values never become disabled", () =>
        {
            Equal(Sabi3ReplyState.Unknown, new Sabi3ReplyInterpretation((Sabi3ReplyState)999).State);
            for (int state = 2; state < 255; state++)
            {
                var result = Sabi3ReplyDecoder.Decode(0, new byte[] { (byte)state, 0, 0, 0 });
                Equal(Sabi3ReplyState.Unknown, result.State); Equal<bool?>(null, result.ProtectionEnabled);
            }
        });
        Add("Sabi3 API failure takes precedence over plausible or stale buffer", () =>
        {
            foreach (int code in new[] { -1, 1, int.MinValue, int.MaxValue })
            foreach (byte[] data in new[] { null, new byte[4], new byte[] { 1,0,0,0 }, new byte[] { 255,0,0,0 } })
            {
                var result = Sabi3ReplyDecoder.Decode(code, data);
                Equal(Sabi3ReplyState.ApiError, result.State); Equal<bool?>(null, result.ProtectionEnabled);
            }
        });
        Add("Sabi3 buffer shape must match the reference contract", () =>
        {
            foreach (byte[] data in new[] { null, new byte[0], new byte[1], new byte[3], new byte[5], new byte[4096] })
                Equal(Sabi3ReplyState.InvalidResponse, Sabi3ReplyDecoder.Decode(0, data).State);
        });
        Add("Sabi3 decoded toggle never asserts a percent limit hardware read or write support", () =>
        {
            for (int state = 0; state < 256; state++)
            {
                var result = Sabi3ReplyDecoder.Decode(0, new byte[] { (byte)state, 0, 0, 0 });
                Equal<int?>(null, result.ChargeLimitPercent);
                Check(!result.IsVerifiedHardwareObservation && !result.HardwareWriteAllowed, "interpreted bytes promoted to verified device state");
            }
        });
        Add("Sabi3 reply decoding does not mutate input or retain a live buffer", () =>
        {
            byte[] buffer = { 1, 20, 30, 40 };
            var result = Sabi3ReplyDecoder.Decode(0, buffer);
            Equal((byte)1, buffer[0]); Equal((byte)20, buffer[1]);
            buffer[0] = 0;
            Equal(Sabi3ReplyState.ProtectionEnabled, result.State);
        });
    }
}
