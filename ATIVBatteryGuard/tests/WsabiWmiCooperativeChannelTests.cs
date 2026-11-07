using System;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    // Supplied fakes and the existing synthetic 0x34 fixture only. These tests
    // never construct the Windows/global gate or access WMI, OEM or reservations.
    private static void RegisterWsabiWmiCooperativeChannelTests()
    {
        Add("cooperative owner requires explicit dependencies finite admission and honest ownership", () =>
        {
            var channel = new CooperativeTestChannel();
            var gate = new CooperativeTestGate();
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiCooperativeFrameChannel(null, gate, TimeSpan.FromSeconds(1)));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiCooperativeFrameChannel(channel, null, TimeSpan.FromSeconds(1)));
            foreach (var timeout in new[] { TimeSpan.Zero, TimeSpan.FromTicks(-1), TimeSpan.MaxValue,
                WsabiWmiCooperativeFrameChannel.MaximumAcquireTimeout + TimeSpan.FromTicks(1) })
                BatteryThrows<ArgumentOutOfRangeException>(() => new WsabiWmiCooperativeFrameChannel(channel, gate, timeout));
            var owner = new WsabiWmiCooperativeFrameChannel(channel, gate, TimeSpan.FromSeconds(1));
            BatteryThrows<ArgumentException>(() => new WsabiWmiCooperativeFrameChannel(owner, gate, TimeSpan.FromSeconds(1)));
            BatteryThrows<ArgumentException>(() => new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired));
            BatteryThrows<ArgumentException>(() => new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Abandoned));
            BatteryThrows<ArgumentException>(() => new WsabiWmiExchangeGateAttempt(
                WsabiWmiExchangeGateStatus.TimedOut, new CooperativeTestLease()));
            BatteryThrows<ArgumentOutOfRangeException>(() => new WsabiWmiExchangeGateAttempt((WsabiWmiExchangeGateStatus)999));
            Check(!owner.CanInvokeMethods && !owner.CanReadHardware && !owner.CanWriteHardware,
                "cooperative software ownership enabled hardware");
            Equal(0, gate.Calls); Equal(0, channel.Calls);
        });

        AddAsync("already cancelled cooperative work creates no owner acquisition or lower call", async () =>
        {
            var channel = new CooperativeTestChannel();
            var gate = new CooperativeTestGate();
            var owner = CooperativeOwner(channel, gate);
            using (var caller = new CancellationTokenSource())
            {
                caller.Cancel();
                await CooperativeCancelled(owner.ExchangeAsync(BoundChannelRequest(), caller.Token));
            }
            Equal(0, gate.Calls); Equal(0, channel.Calls);
            Check(!owner.IsOwnershipUncertain, "pre-admission cancellation quarantined an unused gate");
        });

        AddAsync("cooperative reply waits for same thread release before success publication", async () =>
        {
            using (var allowRelease = new ManualResetEventSlim(false))
            {
                var expected = FrameExchangeReply();
                var channel = new CooperativeTestChannel { Handler = (request, token) => Task.FromResult(expected) };
                var lease = new CooperativeTestLease
                {
                    OnDispose = () => Check(allowRelease.Wait(TimeSpan.FromSeconds(5)), "test release was never allowed")
                };
                var gate = new CooperativeTestGate
                {
                    Handler = (timeout, signal) =>
                    {
                        Check(signal != null && !signal.WaitOne(0), "normal admission received stop");
                        return new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired, lease);
                    }
                };
                var budget = TimeSpan.FromMilliseconds(123);
                var owner = new WsabiWmiCooperativeFrameChannel(channel, gate, budget);
                Task<WsabiWmiReplyResult> pending = owner.ExchangeAsync(BoundChannelRequest(), CancellationToken.None);
                try
                {
                    await CooperativeAwait(lease.DisposeEntered.Task);
                    Equal(budget, gate.LastTimeout);
                    Equal(gate.AcquireThread, channel.CallThread);
                    Equal(gate.AcquireThread, lease.DisposeThread);
                    Check(gate.AcquireThread != 0 && lease.IsHeld && !pending.IsCompleted,
                        "reply was published before the owning thread completed release");
                    allowRelease.Set();
                    Check(ReferenceEquals(expected, await pending.WaitAsync(TimeSpan.FromSeconds(3))), "reply changed during ownership cleanup");
                    Equal(1, lease.DisposeCalls);
                    Check(!lease.IsHeld && !owner.IsOwnershipUncertain, "normal release retained ownership uncertainty");
                }
                finally
                {
                    allowRelease.Set();
                    await CooperativeAwait(pending);
                }
            }
        });

        AddAsync("finite gate refusal statuses never invoke the lower supplied channel", async () =>
        {
            var statuses = new[] { WsabiWmiExchangeGateStatus.TimedOut, WsabiWmiExchangeGateStatus.AccessDenied,
                WsabiWmiExchangeGateStatus.Unavailable, WsabiWmiExchangeGateStatus.UnsupportedPlatform };
            var failures = new[] { WsabiWmiCooperativeExchangeFailure.GateTimedOut, WsabiWmiCooperativeExchangeFailure.GateAccessDenied,
                WsabiWmiCooperativeExchangeFailure.GateUnavailable, WsabiWmiCooperativeExchangeFailure.UnsupportedPlatform };
            for (int i = 0; i < statuses.Length; i++)
            {
                WsabiWmiExchangeGateStatus status = statuses[i];
                var channel = new CooperativeTestChannel();
                var gate = new CooperativeTestGate { Handler = (timeout, signal) => new WsabiWmiExchangeGateAttempt(status) };
                var owner = CooperativeOwner(channel, gate);
                await CooperativeFailure(owner.ExchangeAsync(BoundChannelRequest(), CancellationToken.None), failures[i]);
                Equal(1, gate.Calls); Equal(0, channel.Calls);
                Check(gate.LastTimeout > TimeSpan.Zero && gate.LastTimeout <= WsabiWmiCooperativeFrameChannel.MaximumAcquireTimeout,
                    "the gate received an infinite or invalid acquisition budget");
                Check(gate.LastLease == null && !owner.IsOwnershipUncertain, "an unowned refusal was released or quarantined");
            }
        });

        AddAsync("a stop after gate ownership but before dispatch CAS admits no lower call", async () =>
        {
            var channel = new CooperativeTestChannel();
            var lease = new CooperativeTestLease();
            using (var stop = new WsabiWmiExchangeStopSignal())
            {
                var gate = new CooperativeTestGate
                {
                    Handler = (timeout, signal) =>
                    {
                        // The fake already owns its lease, then stop wins before
                        // returning to the owner's dispatch-admission CAS.
                        Check(lease.IsHeld, "fake did not acquire ownership");
                        stop.Request();
                        return new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired, lease);
                    }
                };
                var owner = CooperativeOwner(channel, gate);
                await CooperativeCancelled(owner.ExchangeAsync(BoundChannelRequest(), CancellationToken.None, stop));
                Equal(0, channel.Calls); Equal(1, lease.DisposeCalls);
                Equal(gate.AcquireThread, lease.DisposeThread);
                Check(!lease.IsHeld && !owner.IsOwnershipUncertain, "pre-CAS stop leaked or poisoned a valid lease");
            }
        });

        AddAsync("outer timeout and caller stop prevent dispatch after a late gate acquisition", async () =>
        {
            foreach (bool callerStops in new[] { false, true })
            using (var caller = new CancellationTokenSource())
            using (var permitAcquireReturn = new ManualResetEventSlim())
            {
                var entered = CooperativeCompletion();
                var stopped = CooperativeCompletion();
                var lease = new CooperativeTestLease();
                var gate = new CooperativeTestGate { Handler = (timeout, signal) =>
                {
                    entered.TrySetResult(true);
                    Check(signal.WaitOne(2000), "admission never received the caller's stop intent");
                    stopped.TrySetResult(true);
                    Check(permitAcquireReturn.Wait(2000), "late acquisition was not released by the test");
                    return new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired, lease);
                }};
                var channel = new CooperativeTestChannel();
                var owner = CooperativeOwner(channel, gate);
                var exchange = new WsabiWmiFrameExchange(owner,
                    callerStops ? TimeSpan.FromSeconds(2) : TimeSpan.FromMilliseconds(150));
                try
                {
                    var pending = exchange.ExchangeAsync(0x34, FrameExchangePayload(), caller.Token);
                    await CooperativeAwait(entered.Task);
                    if (callerStops) caller.Cancel();
                    AssertFrameExchangeFailure(await pending.WaitAsync(TimeSpan.FromSeconds(2)),
                        callerStops ? WsabiWmiFrameExchangeStatus.Cancelled : WsabiWmiFrameExchangeStatus.TimedOut);
                    await CooperativeAwait(stopped.Task);
                    Check(exchange.IsBusy, "stop released an acquisition still in progress");
                    permitAcquireReturn.Set();
                    await FrameExchangeIdle(exchange);
                    Equal(0, channel.Calls);
                    Equal(1, lease.DisposeCalls);
                    Equal(gate.AcquireThread, lease.DisposeThread);
                    Check(!owner.IsOwnershipUncertain, "late but clean cancelled acquisition quarantined");
                }
                finally
                {
                    permitAcquireReturn.Set();
                    await FrameExchangeIdle(exchange);
                }
            }
        });
        AddAsync("cancelled gate admission owns nothing and dispatches nothing", async () =>
        {
            var channel = new CooperativeTestChannel();
            var gate = new CooperativeTestGate
            {
                Handler = (timeout, signal) => new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Cancelled)
            };
            var owner = CooperativeOwner(channel, gate);
            await CooperativeCancelled(owner.ExchangeAsync(BoundChannelRequest(), CancellationToken.None));
            Equal(1, gate.Calls); Equal(0, channel.Calls);
            Check(gate.LastLease == null && !owner.IsOwnershipUncertain, "unowned cancellation claimed uncertain ownership");
        });

        AddAsync("abandoned owned admission releases on its owner and quarantines new peers", async () =>
        {
            var channel = new CooperativeTestChannel();
            var lease = new CooperativeTestLease();
            var gate = new CooperativeTestGate
            {
                Handler = (timeout, signal) => new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Abandoned, lease)
            };
            var owner = CooperativeOwner(channel, gate);
            await CooperativeFailure(owner.ExchangeAsync(BoundChannelRequest(), CancellationToken.None),
                WsabiWmiCooperativeExchangeFailure.GateAbandoned);
            Equal(0, channel.Calls); Equal(1, lease.DisposeCalls);
            Equal(gate.AcquireThread, lease.DisposeThread);
            Check(!lease.IsHeld && owner.IsOwnershipUncertain, "abandonment was accepted or leaked ownership");
            var peerChannel = new CooperativeTestChannel();
            var peer = CooperativeOwner(peerChannel, gate);
            await CooperativeFailure(peer.ExchangeAsync(BoundChannelRequest(), CancellationToken.None),
                WsabiWmiCooperativeExchangeFailure.OwnershipUncertain);
            Equal(1, gate.Calls); Equal(0, peerChannel.Calls);
        });

        AddAsync("unknown acquisition exceptions and null outcomes quarantine without a lower call", async () =>
        {
            foreach (bool throwInsteadOfNull in new[] { true, false })
            {
                var channel = new CooperativeTestChannel();
                var gate = new CooperativeTestGate
                {
                    Handler = (timeout, signal) =>
                    {
                        if (throwInsteadOfNull) throw new InvalidOperationException("synthetic gate failure");
                        return null;
                    }
                };
                var owner = CooperativeOwner(channel, gate);
                await CooperativeFailure(owner.ExchangeAsync(BoundChannelRequest(), CancellationToken.None),
                    WsabiWmiCooperativeExchangeFailure.OwnershipUncertain);
                Check(owner.IsOwnershipUncertain, "ambiguous acquisition remained reusable");
                Equal(0, channel.Calls);
                var peer = CooperativeOwner(new CooperativeTestChannel(), gate);
                await CooperativeFailure(peer.ExchangeAsync(BoundChannelRequest(), CancellationToken.None),
                    WsabiWmiCooperativeExchangeFailure.OwnershipUncertain);
                Equal(1, gate.Calls);
            }
        });

        AddAsync("release failure suppresses success and quarantines resource and gate peers", async () =>
        {
            var channel = new CooperativeTestChannel();
            var lease = new CooperativeTestLease { OnDispose = () => { throw new SynchronizationLockException(); } };
            var gate = new CooperativeTestGate
            {
                Handler = (timeout, signal) => new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired, lease)
            };
            var owner = CooperativeOwner(channel, gate);
            await CooperativeFailure(owner.ExchangeAsync(BoundChannelRequest(), CancellationToken.None),
                WsabiWmiCooperativeExchangeFailure.ReleaseFailure);
            Equal(1, channel.Calls); Equal(1, lease.DisposeCalls);
            Equal(gate.AcquireThread, lease.DisposeThread);
            var otherGate = new CooperativeTestGate();
            await CooperativeFailure(CooperativeOwner(channel, otherGate).ExchangeAsync(BoundChannelRequest(), CancellationToken.None),
                WsabiWmiCooperativeExchangeFailure.OwnershipUncertain);
            Equal(0, otherGate.Calls);
            var otherChannel = new CooperativeTestChannel();
            await CooperativeFailure(CooperativeOwner(otherChannel, gate).ExchangeAsync(BoundChannelRequest(), CancellationToken.None),
                WsabiWmiCooperativeExchangeFailure.OwnershipUncertain);
            Equal(0, otherChannel.Calls); Equal(1, gate.Calls);
            var plainPeer = new WsabiWmiFrameExchange(channel, TimeSpan.FromSeconds(2));
            Check(plainPeer.IsBusy, "a plain wrapper bypassed uncertain ownership of its channel");
            AssertFrameExchangeFailure(await plainPeer.ExchangeAsync(0x34, FrameExchangePayload()), WsabiWmiFrameExchangeStatus.Busy);
        });

        AddAsync("stopped lower faults release normally while untracked channel failures quarantine", async () =>
        {
            var channel = new CooperativeTestChannel
            {
                Handler = (request, token) => Task.FromException<WsabiWmiReplyResult>(new InvalidOperationException("synthetic lower fault"))
            };
            var gate = new CooperativeTestGate();
            var owner = CooperativeOwner(channel, gate);
            await CooperativeFailure(owner.ExchangeAsync(BoundChannelRequest(), CancellationToken.None),
                WsabiWmiCooperativeExchangeFailure.ChannelFailure);
            var firstLease = gate.LastLease;
            Equal(1, firstLease.DisposeCalls); Equal(gate.AcquireThread, firstLease.DisposeThread);
            Check(!owner.IsOwnershipUncertain && !firstLease.IsHeld, "completed lower failure poisoned normal ownership");
            channel.Handler = (request, token) => Task.FromResult(FrameExchangeReply());
            Check((await owner.ExchangeAsync(BoundChannelRequest(), CancellationToken.None)).IsValidFrame,
                "a finished lower fault prevented a later software exchange");
            Equal(2, gate.Calls); Equal(2, channel.Calls);
            foreach (bool synchronousThrow in new[] { true, false })
            {
                var broken = new CooperativeTestChannel
                {
                    Handler = (request, token) =>
                    {
                        if (synchronousThrow) throw new InvalidOperationException("synthetic untracked channel failure");
                        return null;
                    }
                };
                var brokenGate = new CooperativeTestGate();
                var brokenOwner = CooperativeOwner(broken, brokenGate);
                await CooperativeFailure(brokenOwner.ExchangeAsync(BoundChannelRequest(), CancellationToken.None),
                    WsabiWmiCooperativeExchangeFailure.ChannelFailure);
                Check(brokenOwner.IsOwnershipUncertain, "a channel contract violation remained reusable");
                Equal(1, broken.Calls); Equal(1, brokenGate.LastLease.DisposeCalls);
                Equal(brokenGate.AcquireThread, brokenGate.LastLease.DisposeThread);
                var plainPeer = new WsabiWmiFrameExchange(broken, TimeSpan.FromSeconds(2));
                Check(plainPeer.IsBusy, "a new plain peer bypassed channel-contract quarantine");
                AssertFrameExchangeFailure(await plainPeer.ExchangeAsync(0x34, FrameExchangePayload()), WsabiWmiFrameExchangeStatus.Busy);
                var gatePeer = CooperativeOwner(new CooperativeTestChannel(), brokenGate);
                await CooperativeFailure(gatePeer.ExchangeAsync(BoundChannelRequest(), CancellationToken.None),
                    WsabiWmiCooperativeExchangeFailure.OwnershipUncertain);
                Equal(1, brokenGate.Calls);
            }
        });

        AddAsync("bound direct transport throws retain cooperative quarantine across wrappers", () =>
            CooperativeBoundUntracked((request, token) => { throw new InvalidOperationException("synthetic private transport detail"); }));

        AddAsync("bound null transport tasks retain cooperative quarantine across wrappers", () =>
            CooperativeBoundUntracked((request, token) => null));

        AddAsync("bound direct transport cancellation retains cooperative quarantine across wrappers", () =>
            CooperativeBoundUntracked((request, token) => { throw new OperationCanceledException(); }));

        AddAsync("bound completed faults cancellations and null snapshots retain normal ownership cleanup", async () =>
        {
            Func<WsabiWmiMethodRequest, CancellationToken, Task<WsabiWmiMethodSnapshot>>[] outcomes =
            {
                (request, token) => Task.FromException<WsabiWmiMethodSnapshot>(new InvalidOperationException("synthetic completed fault")),
                (request, token) => Task.FromCanceled<WsabiWmiMethodSnapshot>(new CancellationToken(true)),
                (request, token) => Task.FromResult<WsabiWmiMethodSnapshot>(null)
            };
            for (int i = 0; i < outcomes.Length; i++)
            {
                var transport = new BoundChannelTransport { Handler = outcomes[i] };
                var gate = new CooperativeTestGate();
                var owner = CooperativeOwner(new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport), gate);
                var pending = owner.ExchangeAsync(BoundChannelRequest(), CancellationToken.None);
                if (i == 1) await CooperativeCancelled(pending);
                else await CooperativeFailure(pending, WsabiWmiCooperativeExchangeFailure.ChannelFailure);
                Check(!owner.IsOwnershipUncertain, "a returned terminal task was mistaken for an untracked dispatch");
                Equal(1, gate.LastLease.DisposeCalls);
                Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                transport.Handler = (request, token) => Task.FromResult(new WsabiWmiMethodSnapshot(0, BoundChannelOutput(BoundChannelReply())));
                var peer = CooperativeOwner(new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport), gate);
                Check((await peer.ExchangeAsync(BoundChannelRequest(), CancellationToken.None)).IsValidFrame,
                    "completed transport outcome prevented a later bound exchange");
                Equal(2, transport.Calls); Equal(2, gate.Calls);
            }
        });

        AddAsync("bound local rejection and predispatch cancellation do not quarantine unused transport", async () =>
        {
            var transport = new BoundChannelTransport();
            var gate = new CooperativeTestGate();
            var owner = CooperativeOwner(new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport), gate);
            await CooperativeFailure(owner.ExchangeAsync(new byte[21], CancellationToken.None),
                WsabiWmiCooperativeExchangeFailure.ChannelFailure);
            Equal(0, transport.Calls); Equal(1, gate.LastLease.DisposeCalls);
            Check(!owner.IsOwnershipUncertain, "local binding rejection quarantined an unused transport");
            using (var caller = new CancellationTokenSource())
            {
                caller.Cancel();
                await CooperativeCancelled(owner.ExchangeAsync(BoundChannelRequest(), caller.Token));
            }
            Equal(0, transport.Calls); Equal(1, gate.Calls);
            Check(!owner.IsOwnershipUncertain, "pre-admission cancellation quarantined an unused transport");
            Check((await owner.ExchangeAsync(BoundChannelRequest(), CancellationToken.None)).IsValidFrame,
                "local rejection or pre-cancellation prevented a later exchange");
        });

        AddAsync("stop while bound transport dispatch is blocked cannot hide a later direct throw", async () =>
        {
            using (var release = new ManualResetEventSlim())
            using (var caller = new CancellationTokenSource())
            {
                var entered = CooperativeCompletion();
                var transport = new BoundChannelTransport { Handler = (request, token) =>
                {
                    entered.TrySetResult(true);
                    Check(release.Wait(TimeSpan.FromSeconds(5)), "test never released the blocked transport dispatch");
                    throw new OperationCanceledException();
                }};
                var gate = new CooperativeTestGate();
                var owner = CooperativeOwner(new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport), gate);
                var pending = owner.ExchangeAsync(BoundChannelRequest(), caller.Token);
                try
                {
                    await CooperativeAwait(entered.Task);
                    caller.Cancel();
                    Check(!pending.IsCompleted && gate.LastLease.IsHeld,
                        "caller stop released a transport dispatch still on the owner stack");
                    release.Set();
                    await CooperativeFailure(pending, WsabiWmiCooperativeExchangeFailure.ChannelFailure);
                    Check(owner.IsOwnershipUncertain, "caller stop concealed the later untracked transport failure");
                    Equal(1, gate.LastLease.DisposeCalls);
                    Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
                }
                finally
                {
                    release.Set();
                    try { await CooperativeAwait(pending); } catch (WsabiWmiCooperativeExchangeException) { }
                    catch (OperationCanceledException) { }
                }
            }
        });

        AddAsync("outer timeout retains the cooperative lease until a late lower fault stops", async () =>
        {
            var lower = FrameExchangeCompletion();
            var channel = new CooperativeTestChannel { Handler = (request, token) => lower.Task };
            var gate = new CooperativeTestGate();
            var owner = CooperativeOwner(channel, gate);
            var exchange = new WsabiWmiFrameExchange(owner, TimeSpan.FromMilliseconds(300));
            try
            {
                var pending = exchange.ExchangeAsync(0x34, FrameExchangePayload());
                await CooperativeAwait(channel.Entered.Task);
                var lease = gate.LastLease;
                var result = await pending.WaitAsync(TimeSpan.FromSeconds(3));
                AssertFrameExchangeFailure(result, WsabiWmiFrameExchangeStatus.TimedOut);
                Check(lease.IsHeld && lease.DisposeCalls == 0 && exchange.IsBusy,
                    "published timeout released unfinished lower ownership");
                var peerGate = new CooperativeTestGate();
                var peer = new WsabiWmiFrameExchange(CooperativeOwner(channel, peerGate), TimeSpan.FromSeconds(2));
                AssertFrameExchangeFailure(await peer.ExchangeAsync(0x34, FrameExchangePayload()), WsabiWmiFrameExchangeStatus.Busy);
                Equal(0, peerGate.Calls);
                lower.TrySetException(new InvalidOperationException("synthetic late lower fault"));
                await FrameExchangeIdle(exchange);
                Equal(1, lease.DisposeCalls); Equal(gate.AcquireThread, lease.DisposeThread);
                Check(!lease.IsHeld && !owner.IsOwnershipUncertain, "late fault did not finish normal cleanup");
                AssertFrameExchangeFailure(result, WsabiWmiFrameExchangeStatus.TimedOut);
                channel.Handler = (request, token) => Task.FromResult(FrameExchangeReply());
                Check((await peer.ExchangeAsync(0x34, FrameExchangePayload())).IsValidFrame, "late-fault cleanup retained a peer slot");
                await FrameExchangeIdle(peer);
            }
            finally
            {
                lower.TrySetResult(FrameExchangeReply());
                await FrameExchangeIdle(exchange);
            }
        });

        AddAsync("caller cancellation returns while a blocked lower callback retains the lease", async () =>
        {
            using (var allowCallback = new ManualResetEventSlim(false))
            using (var caller = new CancellationTokenSource())
            {
                var lower = FrameExchangeCompletion();
                var callbackRegistered = CooperativeCompletion();
                var callbackEntered = CooperativeCompletion();
                int callbackThread = 0;
                var channel = new CooperativeTestChannel
                {
                    Handler = (request, token) =>
                    {
                        token.Register(() =>
                        {
                            Volatile.Write(ref callbackThread, Thread.CurrentThread.ManagedThreadId);
                            callbackEntered.TrySetResult(true);
                            if (!allowCallback.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("synthetic callback was not released");
                        });
                        callbackRegistered.TrySetResult(true);
                        return lower.Task;
                    }
                };
                var gate = new CooperativeTestGate();
                var owner = CooperativeOwner(channel, gate);
                var exchange = new WsabiWmiFrameExchange(owner, TimeSpan.FromSeconds(3));
                try
                {
                    var pending = exchange.ExchangeAsync(0x34, FrameExchangePayload(), caller.Token);
                    await CooperativeAwait(callbackRegistered.Task);
                    var lease = gate.LastLease;
                    caller.Cancel();
                    var result = await pending.WaitAsync(TimeSpan.FromSeconds(2));
                    AssertFrameExchangeFailure(result, WsabiWmiFrameExchangeStatus.Cancelled);
                    await CooperativeAwait(callbackEntered.Task);
                    lower.TrySetResult(FrameExchangeReply());
                    Check(lease.IsHeld && lease.DisposeCalls == 0 && exchange.IsBusy,
                        "finishing the task bypassed a running cancellation callback");
                    Equal(gate.AcquireThread, Volatile.Read(ref callbackThread));
                    allowCallback.Set();
                    await FrameExchangeIdle(exchange);
                    Equal(1, lease.DisposeCalls); Equal(gate.AcquireThread, lease.DisposeThread);
                    Check(!lease.IsHeld && !owner.IsOwnershipUncertain, "callback cleanup retained the lease");
                    AssertFrameExchangeFailure(result, WsabiWmiFrameExchangeStatus.Cancelled);
                }
                finally
                {
                    allowCallback.Set();
                    lower.TrySetResult(FrameExchangeReply());
                    await FrameExchangeIdle(exchange);
                }
            }
        });

        AddAsync("a cooperative owner preserves the supplied plain channel identity for peers", async () =>
        {
            var lower = FrameExchangeCompletion();
            var channel = new CooperativeTestChannel { Handler = (request, token) => lower.Task };
            var gate = new CooperativeTestGate();
            var owned = new WsabiWmiFrameExchange(CooperativeOwner(channel, gate), TimeSpan.FromSeconds(3));
            var plain = new WsabiWmiFrameExchange(channel, TimeSpan.FromSeconds(3));
            try
            {
                var pending = owned.ExchangeAsync(0x34, FrameExchangePayload());
                await CooperativeAwait(channel.Entered.Task);
                Check(owned.IsBusy && plain.IsBusy, "the owner wrapper hid its inner channel identity");
                AssertFrameExchangeFailure(await plain.ExchangeAsync(0x34, FrameExchangePayload()), WsabiWmiFrameExchangeStatus.Busy);
                Equal(1, channel.Calls);
                lower.TrySetResult(FrameExchangeReply());
                Check((await pending).IsValidFrame, "plain peer changed an owned reply");
                await FrameExchangeIdle(owned);
                Check(!plain.IsBusy, "normal release retained the plain peer");
            }
            finally
            {
                lower.TrySetResult(FrameExchangeReply());
                await FrameExchangeIdle(owned);
            }
        });

        AddAsync("separate bound wrappers keep the same snapshot transport identity through an owner", async () =>
        {
            var lower = BoundChannelCompletion();
            var transport = new BoundChannelTransport { Handler = (request, token) => lower.Task };
            var gate = new CooperativeTestGate();
            var firstBound = new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport);
            var otherBound = new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport);
            var first = new WsabiWmiFrameExchange(CooperativeOwner(firstBound, gate), TimeSpan.FromSeconds(3));
            var plainPeer = new WsabiWmiFrameExchange(otherBound, TimeSpan.FromSeconds(3));
            var peerGate = new CooperativeTestGate();
            var ownedPeer = new WsabiWmiFrameExchange(CooperativeOwner(otherBound, peerGate), TimeSpan.FromSeconds(3));
            try
            {
                var pending = first.ExchangeAsync(0x34, BoundChannelPayload());
                await CooperativeAwait(transport.Entered.Task);
                Check(first.IsBusy && plainPeer.IsBusy && ownedPeer.IsBusy, "new bound wrappers bypassed the shared snapshot transport");
                AssertFrameExchangeFailure(await plainPeer.ExchangeAsync(0x34, BoundChannelPayload()), WsabiWmiFrameExchangeStatus.Busy);
                AssertFrameExchangeFailure(await ownedPeer.ExchangeAsync(0x34, BoundChannelPayload()), WsabiWmiFrameExchangeStatus.Busy);
                Equal(0, peerGate.Calls); Equal(1, transport.Calls);
                lower.TrySetResult(new WsabiWmiMethodSnapshot(0, BoundChannelOutput(BoundChannelReply())));
                Check((await pending).IsValidFrame, "shared transport did not finish its owned exchange");
                await FrameExchangeIdle(first);
                Check(!plainPeer.IsBusy && !ownedPeer.IsBusy, "finished shared transport retained peer wrappers");
            }
            finally
            {
                lower.TrySetResult(new WsabiWmiMethodSnapshot(0, BoundChannelOutput(BoundChannelReply())));
                await FrameExchangeIdle(first);
            }
        });
    }

    private static async Task CooperativeBoundUntracked(
        Func<WsabiWmiMethodRequest, CancellationToken, Task<WsabiWmiMethodSnapshot>> outcome)
    {
        var transport = new BoundChannelTransport { Handler = outcome };
        var gate = new CooperativeTestGate();
        var owner = CooperativeOwner(new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport), gate);
        await CooperativeFailure(owner.ExchangeAsync(BoundChannelRequest(), CancellationToken.None),
            WsabiWmiCooperativeExchangeFailure.ChannelFailure);
        Check(owner.IsOwnershipUncertain, "a bound wrapper concealed an untracked transport failure");
        Equal(1, transport.Calls); Equal(1, gate.LastLease.DisposeCalls);
        Equal(gate.AcquireThread, gate.LastLease.DisposeThread);
        Check(!gate.LastLease.IsHeld, "software quarantine leaked its lease");

        var plainPeer = new WsabiWmiFrameExchange(new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport), TimeSpan.FromSeconds(2));
        AssertFrameExchangeFailure(await plainPeer.ExchangeAsync(0x34, BoundChannelPayload()), WsabiWmiFrameExchangeStatus.Busy);
        var otherGate = new CooperativeTestGate();
        var transportPeer = CooperativeOwner(new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport), otherGate);
        await CooperativeFailure(transportPeer.ExchangeAsync(BoundChannelRequest(), CancellationToken.None),
            WsabiWmiCooperativeExchangeFailure.OwnershipUncertain);
        Equal(0, otherGate.Calls); Equal(1, transport.Calls);

        var otherTransport = new BoundChannelTransport();
        var gatePeer = CooperativeOwner(new WsabiWmiBoundFrameChannel(BoundChannelBinder(), otherTransport), gate);
        await CooperativeFailure(gatePeer.ExchangeAsync(BoundChannelRequest(), CancellationToken.None),
            WsabiWmiCooperativeExchangeFailure.OwnershipUncertain);
        Equal(0, otherTransport.Calls); Equal(1, gate.Calls);

        var independent = CooperativeOwner(new WsabiWmiBoundFrameChannel(BoundChannelBinder(), new BoundChannelTransport()),
            new CooperativeTestGate());
        Check((await independent.ExchangeAsync(BoundChannelRequest(), CancellationToken.None)).IsValidFrame,
            "quarantine spread to an unrelated software resource and gate");
    }

    private static WsabiWmiCooperativeFrameChannel CooperativeOwner(IWsabiWmiFrameChannel channel, IWsabiWmiExchangeGate gate)
        => new WsabiWmiCooperativeFrameChannel(channel, gate, TimeSpan.FromMilliseconds(250));

    private static TaskCompletionSource<bool> CooperativeCompletion()
        => new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);

    private static async Task CooperativeAwait(Task task) => await task.WaitAsync(TimeSpan.FromSeconds(3));

    private static async Task CooperativeFailure(Task task, WsabiWmiCooperativeExchangeFailure expected)
    {
        try { await task.WaitAsync(TimeSpan.FromSeconds(3)); }
        catch (WsabiWmiCooperativeExchangeException error) { Equal(expected, error.Failure); return; }
        throw new InvalidOperationException("Expected a closed cooperative failure.");
    }

    private static async Task CooperativeCancelled(Task task)
    {
        try { await task.WaitAsync(TimeSpan.FromSeconds(3)); }
        catch (OperationCanceledException) { return; }
        throw new InvalidOperationException("Expected cooperative cancellation.");
    }

    private sealed class CooperativeTestGate : IWsabiWmiExchangeGate
    {
        private int calls;
        internal int Calls => Volatile.Read(ref calls);
        internal int AcquireThread;
        internal TimeSpan LastTimeout;
        internal CooperativeTestLease LastLease;
        internal Func<TimeSpan, WaitHandle, WsabiWmiExchangeGateAttempt> Handler;

        public WsabiWmiExchangeGateAttempt Acquire(TimeSpan timeout, WaitHandle cancellationSignal)
        {
            Interlocked.Increment(ref calls);
            AcquireThread = Thread.CurrentThread.ManagedThreadId;
            LastTimeout = timeout;
            var result = Handler == null
                ? new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired, new CooperativeTestLease())
                : Handler(timeout, cancellationSignal);
            LastLease = result?.Lease as CooperativeTestLease;
            return result;
        }
    }

    private sealed class CooperativeTestLease : IWsabiWmiExchangeLease
    {
        private int disposeCalls;
        private int held = 1;
        internal int DisposeCalls => Volatile.Read(ref disposeCalls);
        internal bool IsHeld => Volatile.Read(ref held) != 0;
        internal int DisposeThread;
        internal Action OnDispose;
        internal readonly TaskCompletionSource<bool> DisposeEntered = CooperativeCompletion();

        public void Dispose()
        {
            Interlocked.Increment(ref disposeCalls);
            DisposeThread = Thread.CurrentThread.ManagedThreadId;
            DisposeEntered.TrySetResult(true);
            OnDispose?.Invoke();
            Interlocked.Exchange(ref held, 0);
        }
    }

    private sealed class CooperativeTestChannel : IWsabiWmiFrameChannel
    {
        private int calls;
        internal int Calls => Volatile.Read(ref calls);
        internal int CallThread;
        internal Func<byte[], CancellationToken, Task<WsabiWmiReplyResult>> Handler;
        internal readonly TaskCompletionSource<bool> Entered = CooperativeCompletion();

        public Task<WsabiWmiReplyResult> ExchangeAsync(byte[] request, CancellationToken cancellationToken)
        {
            Interlocked.Increment(ref calls);
            CallThread = Thread.CurrentThread.ManagedThreadId;
            Entered.TrySetResult(true);
            return Handler == null ? Task.FromResult(FrameExchangeReply()) : Handler(request, cancellationToken);
        }
    }
}
