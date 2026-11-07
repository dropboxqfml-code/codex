using System;
using System.Threading;

namespace ATIVBatteryGuard.Core.Services
{
    public enum WsabiWmiExchangeGateStatus
    {
        Acquired, TimedOut, Cancelled, Abandoned, AccessDenied, Unavailable, UnsupportedPlatform
    }

    // Acquire and the returned lease's Dispose run on the same owner thread.
    // Wait only up to timeout or cancellationSignal. Never invoke OEM work here.
    // Return ownership explicitly, including acquired-but-disallowed abandonment.
    public interface IWsabiWmiExchangeGate
    {
        WsabiWmiExchangeGateAttempt Acquire(TimeSpan timeout, WaitHandle cancellationSignal);
    }

    public interface IWsabiWmiExchangeLease : IDisposable { }

    public sealed class WsabiWmiExchangeGateAttempt
    {
        public WsabiWmiExchangeGateStatus Status { get; }
        public IWsabiWmiExchangeLease Lease { get; }

        public WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus status, IWsabiWmiExchangeLease lease = null)
        {
            if (!Enum.IsDefined(typeof(WsabiWmiExchangeGateStatus), status)) throw new ArgumentOutOfRangeException(nameof(status));
            bool owned = status == WsabiWmiExchangeGateStatus.Acquired || status == WsabiWmiExchangeGateStatus.Abandoned;
            if (owned != (lease != null)) throw new ArgumentException("The gate must report ownership explicitly.", nameof(lease));
            Status = status;
            Lease = lease;
        }
    }

    public enum WsabiWmiCooperativeExchangeFailure
    {
        GateTimedOut, GateAbandoned, GateAccessDenied, GateUnavailable,
        UnsupportedPlatform, OwnershipUncertain, ChannelFailure, ReleaseFailure
    }

    public sealed class WsabiWmiCooperativeExchangeException : Exception
    {
        public WsabiWmiCooperativeExchangeFailure Failure { get; }

        internal WsabiWmiCooperativeExchangeException(WsabiWmiCooperativeExchangeFailure failure)
            : base("The cooperative exchange did not complete safely.") { Failure = failure; }
    }
}
