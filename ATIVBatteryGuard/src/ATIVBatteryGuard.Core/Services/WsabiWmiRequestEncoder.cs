namespace ATIVBatteryGuard.Core.Services
{
    // Pure framing for the previously inspected x86 service wsabi, not an OEM
    // transport. Encoding a command does not authorize it, establish its meaning,
    // or identify a battery query. No command is selected, sent or executed here.
    public static class WsabiWmiRequestEncoder
    {
        public const string AnalyzedSha256 = WsabiWmiReplyValidator.AnalyzedSha256;
        public const ushort HeaderMagic = 0x5843;
        // Retain the UInt16 wire field, but support a conservative subset here.
        // The inspected P05ACJ lookup indexes a 256-slot group using the command
        // word without checking that bound. This is not the general wsabi ABI
        // range or approval/safety evidence for any individual command.
        public const int MaximumSupportedCommand = 0xff;
        public const int PayloadBytes = WsabiWmiReplyValidator.PayloadBytes;
        public const int FrameBytes = WsabiWmiReplyValidator.InputFrameBytes;
        public static bool CanInvokeMethods => false;
        public static bool CanReadHardware => false;
        public static bool CanWriteHardware => false;

        public static bool TryEncode(int command, object payload, out byte[] request)
        {
            request = new byte[0];
            // Reject unsupported input instead of truncating it to another command.
            if (command < 0 || command > MaximumSupportedCommand || payload == null ||
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
