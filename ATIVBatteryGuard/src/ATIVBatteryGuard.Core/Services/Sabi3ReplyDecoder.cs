using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // The inspected x64 3.2.0.0 DLL reads/writes eleven caller bytes. Public
    // four-byte examples are insufficient. No DLL or device is invoked here.
    public static class Sabi3ReplyDecoder
    {
        public static Sabi3ReplyInterpretation Decode(int apiReturnCode, byte[] response)
        {
            if (apiReturnCode != 0) return Result(Sabi3ReplyState.ApiError);
            if (response == null || response.Length != Sabi3X64Abi.PayloadBytes) return Result(Sabi3ReplyState.InvalidResponse);
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
