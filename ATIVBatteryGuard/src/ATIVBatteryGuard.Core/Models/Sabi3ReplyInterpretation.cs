namespace ATIVBatteryGuard.Core.Models
{
    // An interpretation of supplied bytes, not evidence of a hardware read.
    public enum Sabi3ReplyState
    {
        Unknown, ProtectionDisabled, ProtectionEnabled, Unsupported, ApiError, InvalidResponse
    }

    public sealed class Sabi3ReplyInterpretation
    {
        public Sabi3ReplyState State { get; }
        public bool? ProtectionEnabled => State == Sabi3ReplyState.ProtectionEnabled ? true
            : State == Sabi3ReplyState.ProtectionDisabled ? (bool?)false : null;
        public int? ChargeLimitPercent => null;
        public bool HardwareWriteAllowed => false;
        public bool IsVerifiedHardwareObservation => false;

        public Sabi3ReplyInterpretation(Sabi3ReplyState state)
        {
            State = System.Enum.IsDefined(typeof(Sabi3ReplyState), state) ? state : Sabi3ReplyState.Unknown;
        }
    }
}
