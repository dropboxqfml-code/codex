using System;

namespace ATIVBatteryGuard.Core.Models
{
    public enum WsabiWmiMethodReplyStatus
    {
        ApiNotSuccessful, MissingOutput, InvalidOutputType, MissingOutData,
        InvalidOutDataType, MissingBytes, PropertyReadFailure, FrameChecked
    }

    // Field extraction and structural decoding only. No output object, raw
    // error, battery interpretation or hardware authorization is retained.
    public sealed class WsabiWmiMethodReplyResult
    {
        public WsabiWmiMethodReplyStatus Status { get; }
        public WsabiWmiReplyResult FrameReply { get; }
        public bool IsValidFrame => Status == WsabiWmiMethodReplyStatus.FrameChecked && FrameReply.IsValidFrame;
        public byte[] Payload => IsValidFrame ? FrameReply.Payload : new byte[0];
        public bool IsHardwareObservation => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        internal WsabiWmiMethodReplyResult(WsabiWmiMethodReplyStatus status, WsabiWmiReplyResult frameReply = null)
        {
            if (!Enum.IsDefined(typeof(WsabiWmiMethodReplyStatus), status))
                throw new ArgumentOutOfRangeException(nameof(status));
            if (status == WsabiWmiMethodReplyStatus.FrameChecked && frameReply == null)
                throw new ArgumentNullException(nameof(frameReply));
            Status = status;
            FrameReply = status == WsabiWmiMethodReplyStatus.FrameChecked ? frameReply : null;
        }
    }
}
