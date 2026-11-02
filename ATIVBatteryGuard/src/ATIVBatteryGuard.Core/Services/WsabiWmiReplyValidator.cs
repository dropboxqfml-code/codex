namespace ATIVBatteryGuard.Core.Services
{
    // Pure structural validation for the previously inspected x86 service wsabi.
    // Its 16-byte WMI payload is a separate contract from Sabi3 x64's 11 bytes.
    // No request is constructed or sent, and valid structure does not establish
    // battery support, a hardware observation, or permission to change settings.
    public static class WsabiWmiReplyValidator
    {
        public const string AnalyzedSha256 = "564b640d62db2a4e4b56c6331e0e526bad2ac1fcf438a41a9e5241551f457b6e";
        public const int PayloadBytes = 16;
        public const int InputFrameBytes = 21;
        public const int MinimumReplyBytesAccessed = 21;

        // The DLL accesses at least 21 reply bytes without inspecting SAFEARRAY
        // bounds. Accepting exactly 21 is our conservative supported subset;
        // it is not evidence that the actual provider always returns this size.
        public const int AcceptedReplyBytes = 21;

        public static bool TryExtractPayload(int apiReturnCode, object bytes, out byte[] payload)
        {
            var result = WsabiWmiReplyDecoder.Decode(apiReturnCode, bytes);
            payload = result.Payload;
            return result.IsValidFrame;
        }
    }
}
