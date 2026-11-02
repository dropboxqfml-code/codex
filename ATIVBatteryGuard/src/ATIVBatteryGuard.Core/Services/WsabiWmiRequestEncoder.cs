namespace ATIVBatteryGuard.Core.Services
{
    // Pure framing for the previously inspected x86 service wsabi, not an OEM
    // transport. Encoding a command does not authorize it, establish its meaning,
    // or identify a battery query. No command is selected, sent or executed here.
    public static class WsabiWmiRequestEncoder
    {
        public const string AnalyzedSha256 = WsabiWmiReplyValidator.AnalyzedSha256;
        public const ushort HeaderMagic = 0x5843;
        public const int PayloadBytes = WsabiWmiReplyValidator.PayloadBytes;
        public const int FrameBytes = WsabiWmiReplyValidator.InputFrameBytes;
        public static bool CanInvokeMethods => false;
        public static bool CanReadHardware => false;
        public static bool CanWriteHardware => false;

        public static bool TryEncode(int command, object payload, out byte[] request)
        {
            request = new byte[0];
            // The inspected DLL truncates its caller's command to UInt16.
            // Reject out-of-range input instead of silently choosing another command.
            if (command < 0 || command > ushort.MaxValue || payload == null ||
                payload.GetType() != typeof(byte[])) return false;
            var bytes = (byte[])payload;
            if (bytes.Rank != 1 || bytes.GetLowerBound(0) != 0 || bytes.Length != PayloadBytes) return false;

            var encoded = new byte[FrameBytes];
            encoded[0] = (byte)(HeaderMagic & 0xff);
            encoded[1] = (byte)(HeaderMagic >> 8);
            encoded[2] = (byte)(command & 0xff);
            encoded[3] = (byte)(command >> 8);
            encoded[4] = 0;
            System.Array.Copy(bytes, 0, encoded, 5, PayloadBytes);
            request = encoded;
            return true;
        }
    }
}
