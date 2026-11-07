using System;
using System.Security;
using System.Threading;

namespace ATIVBatteryGuard.Core.Services
{
    // Explicit opt-in only. Construction opens nothing. Acquire uses the one
    // source-confirmed cooperative name and normal OS permissions; no fallback,
    // ACL edit, privilege change, OEM invocation or retry exists here.
    public sealed class WsabiWmiWindowsMutexGate : IWsabiWmiExchangeGate
    {
        private const string FixedName = @"Global\WmiAcpiInterfaceMutex";
        private static readonly object GlobalIdentity = new object();
        private readonly Func<Mutex> open;
        private readonly bool requireWindows;
        private readonly bool ownsHandle = true;
        internal object CoordinationIdentity { get; }

        public WsabiWmiWindowsMutexGate()
        {
            open = () => new Mutex(false, FixedName);
            requireWindows = true;
            CoordinationIdentity = GlobalIdentity;
        }

        // Offline tests supply an unnamed mutex and a private identity. There
        // is no public arbitrary-name or platform-bypass constructor.
        internal WsabiWmiWindowsMutexGate(Func<Mutex> open, object identity, bool ownsHandle = true)
        {
            this.open = open ?? throw new ArgumentNullException(nameof(open));
            CoordinationIdentity = identity ?? throw new ArgumentNullException(nameof(identity));
            this.ownsHandle = ownsHandle;
        }

        public WsabiWmiExchangeGateAttempt Acquire(TimeSpan timeout, WaitHandle cancellationSignal)
        {
            if (timeout <= TimeSpan.Zero || timeout > WsabiWmiCooperativeFrameChannel.MaximumAcquireTimeout)
                throw new ArgumentOutOfRangeException(nameof(timeout));
            if (cancellationSignal == null) throw new ArgumentNullException(nameof(cancellationSignal));
            if (requireWindows && Environment.OSVersion.Platform != PlatformID.Win32NT)
                return NotOwned(WsabiWmiExchangeGateStatus.UnsupportedPlatform);
            var scope = WsabiWmiExchangeResource.For(CoordinationIdentity);
            if (scope.IsQuarantined) return NotOwned(WsabiWmiExchangeGateStatus.Unavailable);
            if (cancellationSignal.WaitOne(0)) return NotOwned(WsabiWmiExchangeGateStatus.Cancelled);
            MutexLease lease = null;
            bool transferred = false;
            try
            {
                Mutex mutex = open();
                if (mutex == null) return NotOwned(WsabiWmiExchangeGateStatus.Unavailable);
                lease = new MutexLease(mutex, scope, ownsHandle);
                int winner;
                bool abandoned = false;
                try { winner = WaitHandle.WaitAny(new WaitHandle[] { cancellationSignal, mutex }, timeout); }
                catch (AbandonedMutexException error)
                {
                    if (error.MutexIndex != 1) throw;
                    winner = 1;
                    abandoned = true;
                }
                if (winner == WaitHandle.WaitTimeout) return NotOwned(WsabiWmiExchangeGateStatus.TimedOut);
                if (winner == 0) return NotOwned(WsabiWmiExchangeGateStatus.Cancelled);
                lease.Owned = true;
                if (abandoned) scope.Quarantine();
                var attempt = new WsabiWmiExchangeGateAttempt(abandoned
                    ? WsabiWmiExchangeGateStatus.Abandoned : WsabiWmiExchangeGateStatus.Acquired, lease);
                transferred = true;
                return attempt;
            }
            catch (UnauthorizedAccessException) { return NotOwned(WsabiWmiExchangeGateStatus.AccessDenied); }
            catch (SecurityException) { return NotOwned(WsabiWmiExchangeGateStatus.AccessDenied); }
            finally { if (!transferred && lease != null) lease.Dispose(); }
        }

        private static WsabiWmiExchangeGateAttempt NotOwned(WsabiWmiExchangeGateStatus status)
            => new WsabiWmiExchangeGateAttempt(status);

        private sealed class MutexLease : IWsabiWmiExchangeLease
        {
            private readonly Mutex mutex;
            private readonly WsabiWmiExchangeResource scope;
            private readonly bool ownsHandle;
            private readonly int ownerThread = Thread.CurrentThread.ManagedThreadId;
            private bool disposed;
            internal bool Owned;
            internal MutexLease(Mutex mutex, WsabiWmiExchangeResource scope, bool ownsHandle)
            { this.mutex = mutex; this.scope = scope; this.ownsHandle = ownsHandle; }
            public void Dispose()
            {
                if (Thread.CurrentThread.ManagedThreadId != ownerThread)
                {
                    scope.Quarantine();
                    throw new SynchronizationLockException();
                }
                if (disposed) return;
                disposed = true;
                try { if (Owned) mutex.ReleaseMutex(); }
                catch { scope.Quarantine(); throw; }
                finally { if (ownsHandle) mutex.Dispose(); }
            }
        }
    }
}
