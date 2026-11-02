using System;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Core.Models
{
    // Structural outcomes only. None of these states describes battery protection.
    public enum WsabiWmiReplyStatus
    {
        ValidFrame, ApiNotSuccessful, MissingResponse, InvalidType, InvalidShape,
        UnsupportedLength, InvalidAcknowledgement
    }

    public sealed class WsabiWmiReplyResult
    {
        private readonly byte[] payload;
        public WsabiWmiReplyStatus Status { get; }
        public bool IsValidFrame => Status == WsabiWmiReplyStatus.ValidFrame;
        public byte[] Payload => (byte[])payload.Clone();
        public bool IsHardwareObservation => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        internal WsabiWmiReplyResult(WsabiWmiReplyStatus status, byte[] payload = null)
        {
            if (!Enum.IsDefined(typeof(WsabiWmiReplyStatus), status))
                throw new ArgumentOutOfRangeException(nameof(status));
            if (status == WsabiWmiReplyStatus.ValidFrame &&
                (payload == null || payload.Length != WsabiWmiReplyDecoder.PayloadBytes))
                throw new ArgumentException("A valid frame requires the complete bounded payload.", nameof(payload));
            Status = status;
            this.payload = status == WsabiWmiReplyStatus.ValidFrame ? (byte[])payload.Clone() : new byte[0];
        }
    }
}
