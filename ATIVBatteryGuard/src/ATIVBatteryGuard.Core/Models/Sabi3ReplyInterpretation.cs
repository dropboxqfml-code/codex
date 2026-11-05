namespace ATIVBatteryGuard.Core.Models
{
    // Retain the old enum values for source/numeric compatibility. The three
    // protection/support values are no longer produced or accepted as evidence.
    public enum Sabi3ReplyState
    {
        Unknown, ProtectionDisabled, ProtectionEnabled, Unsupported, ApiError, InvalidResponse,
        UninterpretedPayload
    }

    public enum Sabi3ReplyMarker
    {
        NotInspected, Zero, One, FF, Other
    }

    public sealed class Sabi3ReplyInterpretation
    {
        public Sabi3ReplyState State { get; }
        public Sabi3ReplyMarker Marker { get; }
        public bool? ProtectionEnabled => null;
        public int? ChargeLimitPercent => null;
        public bool HardwareWriteAllowed => false;
        public bool IsVerifiedHardwareObservation => false;

        public Sabi3ReplyInterpretation(Sabi3ReplyState state)
        {
            // A caller-selected enum cannot stand in for checked payload bytes
            // or a model-specific firmware contract.
            State = state == Sabi3ReplyState.ApiError || state == Sabi3ReplyState.InvalidResponse
                ? state : Sabi3ReplyState.Unknown;
            Marker = Sabi3ReplyMarker.NotInspected;
        }

        private Sabi3ReplyInterpretation(byte marker)
        {
            State = Sabi3ReplyState.UninterpretedPayload;
            Marker = marker == 0 ? Sabi3ReplyMarker.Zero : marker == 1 ? Sabi3ReplyMarker.One :
                marker == 0xff ? Sabi3ReplyMarker.FF : Sabi3ReplyMarker.Other;
        }

        internal static Sabi3ReplyInterpretation FromPayload(byte marker) => new Sabi3ReplyInterpretation(marker);
    }
}
