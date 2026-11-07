using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Explicitly supplied boundary for offline snapshots only. No native or
    // Windows implementation, default transport or application registration is
    // provided. The returned output must have detached, bounded memory lookups.
    // Its task completes only after actual work stops, including fault/cancel;
    // sync throw/null must leave no running untracked work. Cancellation
    // callbacks must be nonblocking. A future live adapter needs its own
    // independently reviewed provider-completion/process-lifetime contract.
    public interface IWsabiWmiMethodSnapshotTransport
    {
        Task<WsabiWmiMethodSnapshot> ExchangeAsync(WsabiWmiMethodRequest request,
            CancellationToken cancellationToken);
    }
}
