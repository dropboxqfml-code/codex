using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Manual-purpose request. Neutral leaf and stop contracts are shared,
    // while original one-shot attempt types cannot be supplied here.
    public sealed class ManualProtectionLeafRequest
    {
        private readonly ManualProtectionAttempt attempt;
        public ManualProtectionRole Role { get; }
        public int Index => attempt.GetIndex(Role);
        public bool IsSettingRole => attempt.IsSettingRole(Role);
        public bool BelongsTo(ManualProtectionAttempt candidate) => ReferenceEquals(attempt, candidate);
        public WsabiWmiMethodRequest Request => attempt.GetRequest(Role);
        internal ManualProtectionLeafRequest(ManualProtectionAttempt attempt,
            ManualProtectionRole role)
        { this.attempt = attempt; Role = role; }
        public bool Matches(WsabiWmiMethodRequest supplied) => attempt.ValidateRoleRequest(Role, supplied);
    }

    public interface IManualProtectionLeafFactory
    {
        object TargetIdentity { get; }
        Task<WsabiWmiProtectionLeaf> PrepareAsync(ManualProtectionLeafRequest request,
            WsabiWmiProtectionStop stop);
    }
}
