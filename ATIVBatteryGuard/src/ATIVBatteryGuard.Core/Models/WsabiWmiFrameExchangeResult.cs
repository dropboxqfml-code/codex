using System;

namespace ATIVBatteryGuard.Core.Models
{
    public enum WsabiWmiFrameExchangeStatus
    {
        ReplyReceived, InvalidRequest, Cancelled, Busy, TimedOut, TransportFailure
    }

    // Receiving a structurally valid frame does not establish its battery
    // meaning, a hardware observation, or authorization to issue a command.
    public sealed class WsabiWmiFrameExchangeResult
    {
        public WsabiWmiFrameExchangeStatus Status { get; }
        public WsabiWmiReplyResult Reply { get; }
        public bool IsValidFrame => Status == WsabiWmiFrameExchangeStatus.ReplyReceived && Reply.IsValidFrame;
        public byte[] Payload => IsValidFrame ? Reply.Payload : new byte[0];
        public bool IsHardwareObservation => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;
        public bool CanInvokeMethods => false;

        internal WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus status, WsabiWmiReplyResult reply = null)
        {
            if (!Enum.IsDefined(typeof(WsabiWmiFrameExchangeStatus), status))
                throw new ArgumentOutOfRangeException(nameof(status));
            if (status == WsabiWmiFrameExchangeStatus.ReplyReceived && reply == null)
                throw new ArgumentNullException(nameof(reply));
            Status = status;
            Reply = status == WsabiWmiFrameExchangeStatus.ReplyReceived ? reply : null;
        }
    }
}
