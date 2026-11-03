using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // The separately approved experiment supplies its own backend. The main
    // application does not register one. Prepare must not execute OEM methods.
    public interface IWsabiWmiOneShotBackend : IWsabiWmiMethodSnapshotTransport
    {
        ProcessElevationState ReadElevation();
        WsabiWmiOneShotPreflight Prepare();
    }
}
