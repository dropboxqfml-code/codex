using System;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    public enum WsabiWmiProtectionCleanupStatus { Complete, Failed, Unknown }

    // Read-only intent. No SDK cancellation or source callbacks run on Cancel.
    public sealed class WsabiWmiProtectionStop
    {
        private readonly Func<bool> requested;
        public bool IsRequested => requested();
        public Task Notification { get; }
        internal WsabiWmiProtectionStop(Func<bool> requested, Task notification)
        { this.requested = requested; Notification = notification; }
    }

    public sealed class WsabiWmiProtectionLeafRequest
    {
        private readonly WsabiWmiProtectionTransitionAttempt attempt;
        public WsabiWmiProtectionTransitionStage Role { get; }
        public WsabiWmiMethodRequest Request => attempt.GetRequest(Role);
        internal WsabiWmiProtectionLeafRequest(WsabiWmiProtectionTransitionAttempt attempt, WsabiWmiProtectionTransitionStage role)
        { this.attempt = attempt; Role = role; }
        public bool Matches(WsabiWmiMethodRequest supplied) => attempt.ValidateRoleRequest(Role, supplied);
    }

    // A leaf never owns the gate and must not dispatch during preparation.
    // A not-ready leaf still owns and joins any partially prepared resources.
    public sealed class WsabiWmiProtectionLeaf
    {
        private readonly Func<Task<WsabiWmiProtectionCleanupStatus>> closeOutput, closeInputs;
        public bool IsReady { get; }
        public IWsabiWmiInvocationSource Source { get; }
        public WsabiWmiProtectionLeaf(bool isReady, IWsabiWmiInvocationSource source,
            Func<Task<WsabiWmiProtectionCleanupStatus>> closeOutput,
            Func<Task<WsabiWmiProtectionCleanupStatus>> closeInputs)
        {
            if (isReady && source == null) throw new ArgumentNullException(nameof(source));
            IsReady = isReady; Source = source;
            this.closeOutput = closeOutput ?? throw new ArgumentNullException(nameof(closeOutput));
            this.closeInputs = closeInputs ?? throw new ArgumentNullException(nameof(closeInputs));
        }
        public Task<WsabiWmiProtectionCleanupStatus> CloseOutputAsync() => closeOutput();
        public Task<WsabiWmiProtectionCleanupStatus> CloseInputsAsync() => closeInputs();
    }

    public interface IWsabiWmiProtectionLeafFactory
    {
        object TargetIdentity { get; }
        Task<WsabiWmiProtectionLeaf> PrepareAsync(WsabiWmiProtectionLeafRequest request, WsabiWmiProtectionStop stop);
    }
}
