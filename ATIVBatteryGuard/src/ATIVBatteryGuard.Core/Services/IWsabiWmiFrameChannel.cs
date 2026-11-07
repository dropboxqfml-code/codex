using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // A supplied channel owns its request array and must complete its task only
    // after its work has stopped, including fault/cancel completion. A sync
    // throw or null task must leave no running, untracked operation. A provider
    // that cannot honor this contract cannot be made safe by a lease wrapper.
    // Cooperative wrapping also requires all shared preparation/staging and
    // detached reply cleanup to occur within this call/task's lifetime.
    // Cancellation callbacks must be nonblocking.
    // No Windows/OEM implementation or default channel is provided here.
    public interface IWsabiWmiFrameChannel
    {
        Task<WsabiWmiReplyResult> ExchangeAsync(byte[] request, CancellationToken cancellationToken);
    }
}
