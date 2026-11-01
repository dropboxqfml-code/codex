using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // The public wrapper expects a four-byte BLE response. This decoder does
    // not load a DLL, initialize an interface, or authorize a device request.
    public static class Sabi3ReplyDecoder
    {
        public static Sabi3ReplyInterpretation Decode(int apiReturnCode, byte[] response)
        {
            if (apiReturnCode != 0) return Result(Sabi3ReplyState.ApiError);
            if (response == null || response.Length != 4) return Result(Sabi3ReplyState.InvalidResponse);
            switch (response[0])
            {
                case 0: return Result(Sabi3ReplyState.ProtectionDisabled);
                case 1: return Result(Sabi3ReplyState.ProtectionEnabled);
                case 0xff: return Result(Sabi3ReplyState.Unsupported);
                default: return Result(Sabi3ReplyState.Unknown);
            }
        }

        private static Sabi3ReplyInterpretation Result(Sabi3ReplyState state) => new Sabi3ReplyInterpretation(state);
    }
}
