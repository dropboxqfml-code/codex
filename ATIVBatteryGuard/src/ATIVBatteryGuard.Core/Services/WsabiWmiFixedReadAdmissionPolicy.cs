using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    public enum WsabiWmiFixedReadAdmissionStatus
    {
        ElevationUnknown = 0, NotElevated = 1, Ready = 2
    }

    // Local admission classification for the separate fixed-read tool only.
    // Ready does not establish WMI access, firmware support, a new reservation
    // or permission to repeat a consumed trial. No token changes occur here.
    public static class WsabiWmiFixedReadAdmissionPolicy
    {
        public static WsabiWmiFixedReadAdmissionStatus Evaluate(ProcessElevationState elevation)
        {
            switch (elevation)
            {
                case ProcessElevationState.Elevated:
                    return WsabiWmiFixedReadAdmissionStatus.Ready;
                case ProcessElevationState.NotElevated:
                    return WsabiWmiFixedReadAdmissionStatus.NotElevated;
                default:
                    return WsabiWmiFixedReadAdmissionStatus.ElevationUnknown;
            }
        }
    }
}
