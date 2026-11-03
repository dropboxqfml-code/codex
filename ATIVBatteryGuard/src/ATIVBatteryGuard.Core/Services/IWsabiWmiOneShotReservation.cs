using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    public interface IWsabiWmiOneShotReservation
    {
        // A successful claim must be durable before the candidate is requested.
        // An existing or uncertain claim is never reset or automatically retried.
        WsabiWmiOneShotReservationStatus TryClaim();
    }
}
