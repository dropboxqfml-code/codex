using System;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiWindowsMutexGateTests()
    {
        Add("fixed Windows mutex adapters are lazy and share one gate identity", () =>
        {
            var first = new WsabiWmiWindowsMutexGate();
            var second = new WsabiWmiWindowsMutexGate();
            Check(ReferenceEquals(first.CoordinationIdentity, second.CoordinationIdentity), "fixed adapter identity changed");
            // Never acquire the actual OEM Global object, including on Windows.
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
            using (var stop = new ManualResetEvent(false))
                Equal(WsabiWmiExchangeGateStatus.UnsupportedPlatform, first.Acquire(TimeSpan.FromMilliseconds(20), stop).Status);
        });
        Add("mutex wait validation and precancellation do not open a mutex", () =>
        {
            int opens = 0;
            var gate = new WsabiWmiWindowsMutexGate(() => { opens++; return new Mutex(); }, new object());
            using (var stop = new ManualResetEvent(true))
            {
                BatteryThrows<ArgumentOutOfRangeException>(() => gate.Acquire(TimeSpan.Zero, stop));
                BatteryThrows<ArgumentOutOfRangeException>(() => gate.Acquire(TimeSpan.MaxValue, stop));
                BatteryThrows<ArgumentNullException>(() => gate.Acquire(TimeSpan.FromMilliseconds(20), null));
                var result = gate.Acquire(TimeSpan.FromMilliseconds(20), stop);
                Equal(WsabiWmiExchangeGateStatus.Cancelled, result.Status);
                Check(result.Lease == null, "cancelled wait acquired ownership");
            }
            Equal(0, opens);
        });
        Add("mutex access and unavailable failures return no ownership or original error text", () =>
        {
            using (var stop = new ManualResetEvent(false))
            {
                foreach (Func<Mutex> open in new Func<Mutex>[] {
                    () => { throw new UnauthorizedAccessException("private access text"); },
                    () => { throw new System.Security.SecurityException("private security text"); },
                    () => null })
                {
                    var result = new WsabiWmiWindowsMutexGate(open, new object()).Acquire(TimeSpan.FromMilliseconds(20), stop);
                    Check(result.Status == WsabiWmiExchangeGateStatus.AccessDenied || result.Status == WsabiWmiExchangeGateStatus.Unavailable,
                        "open failure classified as acquired");
                    Check(result.Lease == null, "failed open returned ownership");
                }
            }
        });
        Add("unnamed mutex contention has a finite wait and cancellation does not release another owner", () =>
        {
            using (var mutex = new Mutex())
            using (var holding = new ManualResetEventSlim())
            using (var release = new ManualResetEventSlim())
            using (var stop = new ManualResetEvent(false))
            {
                Exception holderFailure = null;
                var holder = new Thread(() =>
                {
                    try { mutex.WaitOne(); holding.Set(); release.Wait(); mutex.ReleaseMutex(); }
                    catch (Exception error) { holderFailure = error; holding.Set(); }
                }) { IsBackground = true };
                holder.Start();
                try
                {
                    Check(holding.Wait(2000), "test owner did not enter");
                    var gate = new WsabiWmiWindowsMutexGate(() => mutex, new object(), ownsHandle: false);
                    Equal(WsabiWmiExchangeGateStatus.TimedOut, gate.Acquire(TimeSpan.FromMilliseconds(30), stop).Status);
                    stop.Set();
                    Equal(WsabiWmiExchangeGateStatus.Cancelled, gate.Acquire(TimeSpan.FromMilliseconds(30), stop).Status);
                    Check(holder.IsAlive, "failed acquisition stopped another owner");
                }
                finally { release.Set(); Check(holder.Join(2000), "test owner did not stop"); }
                Check(holderFailure == null, "failed wait damaged the original mutex handle");
            }
        });
        Add("unnamed abandoned ownership is reported explicitly and quarantines fresh adapters", () =>
        {
            using (var mutex = new Mutex())
            using (var stop = new ManualResetEvent(false))
            {
                var previousOwner = new Thread(() => mutex.WaitOne()) { IsBackground = true };
                previousOwner.Start();
                Check(previousOwner.Join(2000), "abandoned test owner did not exit");
                var identity = new object();
                var gate = new WsabiWmiWindowsMutexGate(() => mutex, identity, ownsHandle: false);
                var attempt = gate.Acquire(TimeSpan.FromMilliseconds(200), stop);
                try
                {
                    Equal(WsabiWmiExchangeGateStatus.Abandoned, attempt.Status);
                    Check(attempt.Lease != null, "abandoned owner was not captured for cleanup");
                }
                finally { attempt.Lease?.Dispose(); }
                int opens = 0;
                var fresh = new WsabiWmiWindowsMutexGate(() => { opens++; return mutex; }, identity, ownsHandle: false);
                Equal(WsabiWmiExchangeGateStatus.Unavailable, fresh.Acquire(TimeSpan.FromMilliseconds(20), stop).Status);
                Equal(0, opens);
            }
        });
        Add("unnamed mutex lease rejects a foreign release and allows its owner to clean up", () =>
        {
            using (var mutex = new Mutex())
            using (var stop = new ManualResetEvent(false))
            {
                var identity = new object();
                var gate = new WsabiWmiWindowsMutexGate(() => mutex, identity, ownsHandle: false);
                var attempt = gate.Acquire(TimeSpan.FromMilliseconds(20), stop);
                Equal(WsabiWmiExchangeGateStatus.Acquired, attempt.Status);
                Exception foreignFailure = null;
                var other = new Thread(() => { try { attempt.Lease.Dispose(); } catch (Exception error) { foreignFailure = error; } });
                try { other.Start(); Check(other.Join(2000), "foreign release did not finish"); }
                finally { attempt.Lease.Dispose(); }
                Check(foreignFailure is SynchronizationLockException, "foreign thread released the lease");
                Equal(WsabiWmiExchangeGateStatus.Unavailable, gate.Acquire(TimeSpan.FromMilliseconds(20), stop).Status);
            }
        });
        AddAsync("cooperative owner keeps a real unnamed mutex across an asynchronous reply", async () =>
        {
            var completion = FrameExchangeCompletion();
            var channel = new FakeFrameChannel { Handler = (request, token) => completion.Task };
            var gate = new WsabiWmiWindowsMutexGate(() => new Mutex(), new object());
            var owner = new WsabiWmiCooperativeFrameChannel(channel, gate, TimeSpan.FromMilliseconds(100));
            var exchange = new WsabiWmiFrameExchange(owner, TimeSpan.FromSeconds(2));
            try
            {
                var pending = exchange.ExchangeAsync(0x34, FrameExchangePayload());
                await channel.Entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
                completion.SetResult(FrameExchangeReply());
                Check((await pending).IsValidFrame, "unnamed mutex release lost thread ownership after await");
                await FrameExchangeIdle(exchange);
                Check(!owner.IsOwnershipUncertain, "normal unnamed ownership quarantined");
                Equal(1, channel.Calls);
            }
            finally { completion.TrySetResult(FrameExchangeReply()); }
        });
    }
}
