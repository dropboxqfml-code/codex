using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // A supplied channel owns its request array and must complete its task only
    // after its work has stopped. Cancellation callbacks must be nonblocking.
    // No Windows/OEM implementation or default channel is provided here.
    public interface IWsabiWmiFrameChannel
    {
        Task<WsabiWmiReplyResult> ExchangeAsync(byte[] request, CancellationToken cancellationToken);
    }
}
