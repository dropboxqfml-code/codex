using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // The user's approval is limited to this candidate experiment. These
    // constants do not establish its firmware meaning or permission to write.
    public static class WsabiWmiOneShotPolicy
    {
        public const ushort CandidateCommand = 0x65;
        public const uint RequiredMethodId = 1;
        public const int PayloadBytes = 16;
        public const int FrameBytes = 21;
        public const int MaximumInvocations = 1;
        public const byte FirstPayloadByte = 0x80;
        public static bool CanWriteHardware => false;

        public static byte[] CreatePayload()
        {
            var result = new byte[PayloadBytes];
            result[0] = FirstPayloadByte;
            return result;
        }

        public static bool IsApprovedRequest(WsabiWmiMethodRequest request)
        {
            if (request == null || request.ObservedMethodId != RequiredMethodId ||
                request.FirmwareCommand != CandidateCommand) return false;
            byte[] frame = request.Frame;
            if (frame.Length != FrameBytes || frame[0] != 0x43 || frame[1] != 0x58 ||
                frame[2] != CandidateCommand || frame[3] != 0 || frame[4] != 0 ||
                frame[5] != FirstPayloadByte) return false;
            for (int index = 6; index < frame.Length; index++)
                if (frame[index] != 0) return false;
            return true;
        }
    }
}
