using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Core.Models
{
    // An offline request envelope, not a ManagementBaseObject or an invocation.
    // The caller chooses a generic command for framing; no battery command is
    // selected, approved or sent by this model.
    public sealed class WsabiWmiMethodRequest
    {
        private readonly byte[] frame;
        public uint ObservedMethodId { get; }
        public ushort FirmwareCommand { get; }
        public byte[] Frame => (byte[])frame.Clone();
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        public IReadOnlyDictionary<string, object> Arguments
        {
            get
            {
                // Both maps are detached and read-only. A byte[] remains a
                // mutable CLR value, so every access receives its own copy.
                var buffer = new ReadOnlyDictionary<string, object>(new Dictionary<string, object>(StringComparer.Ordinal)
                {
                    { WsabiWmiMethodBinder.BufferPropertyName, (byte[])frame.Clone() }
                });
                return new ReadOnlyDictionary<string, object>(new Dictionary<string, object>(StringComparer.Ordinal)
                {
                    { WsabiWmiMethodBinder.InputPropertyName, buffer }
                });
            }
        }

        internal WsabiWmiMethodRequest(uint observedMethodId, ushort firmwareCommand, byte[] frame)
        {
            if (frame == null || frame.Length != WsabiWmiRequestEncoder.FrameBytes)
                throw new ArgumentException("A request requires the complete bounded frame.", nameof(frame));
            ObservedMethodId = observedMethodId;
            FirmwareCommand = firmwareCommand;
            this.frame = (byte[])frame.Clone();
        }
    }
}
