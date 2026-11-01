namespace ATIVBatteryGuard.Core.Services
{
    // Sizes observed by static inspection of this exact DLL; no native calls.
    public static class Sabi3X64Abi
    {
        public const string AnalyzedSha256 = "09a9714f0e11734872d60f2966edf8590ca721f0c05b2ca852a0bf20d6c006ae";
        public const int PayloadBytes = 11;
        public const int DriverRequestBytes = 26;
        public const int DriverReplyBytes = 16;

        public static byte[] CreateProtectionStatusBuffer()
        {
            var result = new byte[PayloadBytes];
            result[0] = 0x80;
            return result;
        }

        public static bool TryExtractDriverPayload(bool succeeded, int returnedBytes, byte[] response, out byte[] payload)
        {
            payload = new byte[0];
            if (!succeeded || returnedBytes != DriverReplyBytes || response == null ||
                response.Length != DriverReplyBytes || response[4] != 0xaa) return false;
            payload = new byte[PayloadBytes];
            System.Array.Copy(response, 5, payload, 0, PayloadBytes);
            return true;
        }
    }
}
