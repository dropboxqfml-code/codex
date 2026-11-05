using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // The inspected x64 3.2.0.0 DLL reads/writes eleven caller bytes. Public
    // four-byte examples are insufficient. Length/API checks do not establish
    // this model's battery command semantics. No DLL or device is invoked here.
    public static class Sabi3ReplyDecoder
    {
        public static Sabi3ReplyInterpretation Decode(int apiReturnCode, byte[] response)
        {
            if (apiReturnCode != 0) return Result(Sabi3ReplyState.ApiError);
            if (response == null || response.Length != Sabi3X64Abi.PayloadBytes) return Result(Sabi3ReplyState.InvalidResponse);
            return Sabi3ReplyInterpretation.FromPayload(response[0]);
        }

        private static Sabi3ReplyInterpretation Result(Sabi3ReplyState state) => new Sabi3ReplyInterpretation(state);
    }
}
