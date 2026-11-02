using System;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Pure decoding of supplied bytes for one statically inspected service wsabi.
    // A valid frame is not a hardware read, an interpreted battery value, proof
    // of command support, or permission to invoke a method.
    public static class WsabiWmiReplyDecoder
    {
        public const string AnalyzedSha256 = WsabiWmiReplyValidator.AnalyzedSha256;
        public const int PayloadBytes = WsabiWmiReplyValidator.PayloadBytes;
        public const int AcceptedReplyBytes = WsabiWmiReplyValidator.AcceptedReplyBytes;

        public static WsabiWmiReplyResult Decode(int apiReturnCode, object bytes)
        {
            // Require S_OK before inspecting any response. S_FALSE can mean that
            // enumeration ended without an instance or a copied reply.
            if (apiReturnCode != 0) return Result(WsabiWmiReplyStatus.ApiNotSuccessful);
            if (bytes == null) return Result(WsabiWmiReplyStatus.MissingResponse);
            var array = bytes as Array;
            if (array == null || bytes.GetType().GetElementType() != typeof(byte))
                return Result(WsabiWmiReplyStatus.InvalidType);
            if (array.Rank != 1 || array.GetLowerBound(0) != 0)
                return Result(WsabiWmiReplyStatus.InvalidShape);
            // Do not coerce a SAFEARRAY, collection, view or a different CLR array.
            // This retains the original validator's exact acceptance boundary.
            if (bytes.GetType() != typeof(byte[])) return Result(WsabiWmiReplyStatus.InvalidType);
            var response = (byte[])bytes;
            // Exactly 21 is a conservative supported subset, not a claim about
            // the untested provider's actual reply length.
            if (response.Length != AcceptedReplyBytes) return Result(WsabiWmiReplyStatus.UnsupportedLength);
            if (response[4] != 0xaa) return Result(WsabiWmiReplyStatus.InvalidAcknowledgement);
            var payload = new byte[PayloadBytes];
            Array.Copy(response, 5, payload, 0, PayloadBytes);
            return new WsabiWmiReplyResult(WsabiWmiReplyStatus.ValidFrame, payload);
        }

        private static WsabiWmiReplyResult Result(WsabiWmiReplyStatus status)
            => new WsabiWmiReplyResult(status);
    }
}
