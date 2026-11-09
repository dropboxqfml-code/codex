using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Distinct purpose-bound request. The neutral leaf and stop contracts are
    // shared; a disable request cannot be supplied to the old setting1 factory.
    public sealed class WsabiWmiProtectionDisableLeafRequest
    {
        private readonly WsabiWmiProtectionDisableAttempt attempt;
        public WsabiWmiProtectionDisableStage Role { get; }
        public WsabiWmiMethodRequest Request => attempt.GetRequest(Role);
        internal WsabiWmiProtectionDisableLeafRequest(WsabiWmiProtectionDisableAttempt attempt,
            WsabiWmiProtectionDisableStage role)
        { this.attempt = attempt; Role = role; }
        public bool Matches(WsabiWmiMethodRequest supplied) => attempt.ValidateRoleRequest(Role, supplied);
    }

    public interface IWsabiWmiProtectionDisableLeafFactory
    {
        object TargetIdentity { get; }
        Task<WsabiWmiProtectionLeaf> PrepareAsync(WsabiWmiProtectionDisableLeafRequest request,
            WsabiWmiProtectionStop stop);
    }
}
