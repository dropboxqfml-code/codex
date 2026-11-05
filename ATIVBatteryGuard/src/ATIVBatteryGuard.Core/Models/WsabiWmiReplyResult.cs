using System;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Core.Models
{
    // Structural outcomes only. None of these states describes battery protection.
    public enum WsabiWmiReplyStatus
    {
        ValidFrame, ApiNotSuccessful, MissingResponse, InvalidType, InvalidShape,
        UnsupportedLength, InvalidAcknowledgement, InvalidEnvelope
    }

    // A byte-pattern comparison only: matching does not identify the firmware,
    // prove which branch ran, or distinguish missing callbacks from EFI errors.
    public enum WsabiWmiDispatchFailurePrefix
    {
        NotInspected, MatchesAnalyzedP05AcjPrefix, DiffersFromAnalyzedP05AcjPrefix
    }

    public sealed class WsabiWmiReplyResult
    {
        public const string AnalyzedDispatchModuleSha256 =
            "2795669f18e3fb787d908ba00e2e9da7ab7d398ee599f27aa2f068129b46f310";
        private readonly byte[] payload;
        public WsabiWmiReplyStatus Status { get; }
        public WsabiWmiMethodReplyStatus? MethodReplyStatus { get; }
        public bool IsValidFrame => Status == WsabiWmiReplyStatus.ValidFrame;
        public WsabiWmiDispatchFailurePrefix DispatchFailurePrefix { get; }
        public byte[] Payload => (byte[])payload.Clone();
        public bool IsHardwareObservation => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        internal WsabiWmiReplyResult(WsabiWmiReplyStatus status, byte[] payload = null)
            : this(status, payload, null)
        {
        }

        private WsabiWmiReplyResult(WsabiWmiReplyStatus status, byte[] payload,
            WsabiWmiMethodReplyStatus? methodReplyStatus)
        {
            if (!Enum.IsDefined(typeof(WsabiWmiReplyStatus), status))
                throw new ArgumentOutOfRangeException(nameof(status));
            if (methodReplyStatus.HasValue && !Enum.IsDefined(typeof(WsabiWmiMethodReplyStatus), methodReplyStatus.Value))
                throw new ArgumentOutOfRangeException(nameof(methodReplyStatus));
            if (status == WsabiWmiReplyStatus.InvalidEnvelope &&
                (!methodReplyStatus.HasValue || methodReplyStatus == WsabiWmiMethodReplyStatus.FrameChecked ||
                 methodReplyStatus == WsabiWmiMethodReplyStatus.ApiNotSuccessful))
                throw new ArgumentException("An invalid envelope requires its specific field failure.", nameof(methodReplyStatus));
            if (status == WsabiWmiReplyStatus.ValidFrame &&
                (payload == null || payload.Length != WsabiWmiReplyDecoder.PayloadBytes))
                throw new ArgumentException("A valid frame requires the complete bounded payload.", nameof(payload));
            Status = status;
            MethodReplyStatus = methodReplyStatus;
            this.payload = status == WsabiWmiReplyStatus.ValidFrame ? (byte[])payload.Clone() : new byte[0];
            DispatchFailurePrefix = WsabiWmiDispatchFailurePrefix.NotInspected;
            if (status == WsabiWmiReplyStatus.ValidFrame)
            {
                // The analyzed dispatcher clears 20 bytes from +5, then writes
                // FF at +5 and AA at +4 on several failure paths. Only the first
                // 16 data bytes are available in our supported WMI frame.
                bool matches = this.payload[0] == 0xff;
                for (int i = 1; i < this.payload.Length; i++) matches &= this.payload[i] == 0;
                DispatchFailurePrefix = matches ? WsabiWmiDispatchFailurePrefix.MatchesAnalyzedP05AcjPrefix :
                    WsabiWmiDispatchFailurePrefix.DiffersFromAnalyzedP05AcjPrefix;
            }
        }

        internal static WsabiWmiReplyResult FromMethodReply(WsabiWmiMethodReplyResult reply)
        {
            if (reply == null) throw new ArgumentNullException(nameof(reply));
            if (reply.Status == WsabiWmiMethodReplyStatus.FrameChecked)
            {
                // The method binder supplies an ordinary byte-decoder result.
                // Do not wrap a previously failed envelope as a checked frame.
                if (reply.FrameReply.Status == WsabiWmiReplyStatus.InvalidEnvelope || reply.FrameReply.MethodReplyStatus.HasValue)
                    throw new ArgumentException("A checked frame requires a byte-decoder result.", nameof(reply));
                return new WsabiWmiReplyResult(reply.FrameReply.Status, reply.FrameReply.Payload, reply.Status);
            }
            return new WsabiWmiReplyResult(reply.Status == WsabiWmiMethodReplyStatus.ApiNotSuccessful
                ? WsabiWmiReplyStatus.ApiNotSuccessful : WsabiWmiReplyStatus.InvalidEnvelope, null, reply.Status);
        }
    }
}
