using System;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    // The production host flow, supplied fakes and existing synthetic fixtures
    // only. No SDK, native object, process exit or device command is exercised.
    private static void RegisterWsabiWmiInvocationHostTests()
    {
        AddAsync("invocation host validates reporter before entry and closes admission before publishing", async () =>
        {
            var source = new InvocationTestSource();
            var gate = new CooperativeTestGate();
            var session = InvocationSession(source, gate);
            BatteryThrows<ArgumentNullException>(() => session.RunAndCloseAsync(0x34, BoundChannelPayload(), null));
            Equal(0, source.Calls); Equal(0, gate.Calls);
            Check(!session.IsCloseReady, "null reporter consumed or closed a fresh session");
            int reports = 0;
            WsabiWmiFrameExchangeResult reported = null;
            var result = await session.RunAndCloseAsync(0x34, BoundChannelPayload(), value =>
            {
                reports++; reported = value;
                Check(value.IsValidFrame && !value.IsHardwareObservation && !value.CanReadHardware &&
                    !value.CanWriteHardware && !value.CanInvokeMethods, "host escalated a structural frame to hardware permission");
                var retry = session.ExchangeAsync(0x34, BoundChannelPayload());
                Check(retry.IsCompleted, "closed admission attempted asynchronous dispatch");
                AssertFrameExchangeFailure(retry.GetAwaiter().GetResult(), WsabiWmiFrameExchangeStatus.Cancelled);
            });
            Check(ReferenceEquals(result, reported) && session.IsCloseReady, "host returned before close or changed the reported result");
            Equal(1, reports); Equal(1, source.Calls); Equal(1, gate.LastLease.DisposeCalls);
        });

        AddAsync("invocation host local rejection and pre cancellation publish once without dispatch", async () =>
        {
            foreach (bool cancelled in new[] { false, true })
            using (var caller = new CancellationTokenSource())
            {
                var source = new InvocationTestSource();
                var gate = new CooperativeTestGate();
                var session = InvocationSession(source, gate);
                if (cancelled) caller.Cancel();
                int reports = 0;
                var result = await session.RunAndCloseAsync(0x34, cancelled ? BoundChannelPayload() : null,
                    value => reports++, caller.Token);
                AssertFrameExchangeFailure(result, cancelled ? WsabiWmiFrameExchangeStatus.Cancelled : WsabiWmiFrameExchangeStatus.InvalidRequest);
                Check(session.IsCloseReady, "no-dispatch result skipped close");
                Equal(1, reports); Equal(0, source.Calls); Equal(0, gate.Calls);
            }
        });

        AddAsync("invocation host publishes timeout while its main lifetime and ownership remain pending", () => InvocationHostUnknown(false));
        AddAsync("invocation host repeated caller stop cannot cancel its cleanup wait", () => InvocationHostUnknown(true));

        AddAsync("invocation host reporting failure waits for terminal and actual owner release before faulting", async () =>
        {
            using (var release = new ManualResetEventSlim())
            {
                var source = new InvocationTestSource { Handler = (request, observer) => { } };
                var lease = new CooperativeTestLease { OnDispose = () =>
                {
                    if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException();
                }};
                var gate = new CooperativeTestGate { Handler = (timeout, signal) =>
                    new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired, lease) };
                var session = InvocationSession(source, gate, TimeSpan.FromMilliseconds(500));
                var published = CooperativeCompletion();
                var reportingFailure = new InvalidOperationException("Host result display failed.");
                int reports = 0;
                var run = session.RunAndCloseAsync(0x34, BoundChannelPayload(), value =>
                {
                    reports++; AssertFrameExchangeFailure(value, WsabiWmiFrameExchangeStatus.TimedOut);
                    published.TrySetResult(true);
                    throw reportingFailure;
                });
                try
                {
                    await CooperativeAwait(published.Task);
                    Check(!run.IsCompleted && !session.IsCloseReady && lease.IsHeld,
                        "reporting failure escaped before unknown invocation cleanup");
                    InvocationSupplyFinal(source); // Explicit fake-only completion, not SDK evidence.
                    await CooperativeAwait(lease.DisposeEntered.Task);
                    Check(!run.IsCompleted && !session.IsCloseReady && lease.IsHeld,
                        "reporting failure bypassed the blocked owner release");
                    release.Set();
                    await AssertInvocationHostFailure(run, reportingFailure);
                    Check(session.IsCloseReady && !lease.IsHeld, "reporting failure did not join close");
                    Equal(1, reports); Equal(1, source.Calls); Equal(1, lease.DisposeCalls);
                    Equal(gate.AcquireThread, lease.DisposeThread);
                }
                finally
                {
                    release.Set(); await InvocationClose(session, source);
                    await AssertInvocationHostFailure(run, reportingFailure);
                }
            }
        });

        AddAsync("invocation host busy peer publishes once but waits for the original owner release", async () =>
        {
            using (var release = new ManualResetEventSlim())
            {
                var source = new InvocationTestSource();
                var lease = new CooperativeTestLease { OnDispose = () =>
                {
                    if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException();
                }};
                var ownerGate = new CooperativeTestGate { Handler = (timeout, signal) =>
                    new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.Acquired, lease) };
                var owner = InvocationSession(source, ownerGate);
                var peerGate = new CooperativeTestGate();
                var peer = InvocationSession(source, peerGate);
                var pendingOwner = owner.ExchangeAsync(0x34, BoundChannelPayload());
                Task<WsabiWmiFrameExchangeResult> run = null;
                try
                {
                    await CooperativeAwait(lease.DisposeEntered.Task);
                    int reports = 0;
                    run = peer.RunAndCloseAsync(0x34, BoundChannelPayload(), value =>
                    {
                        reports++; AssertFrameExchangeFailure(value, WsabiWmiFrameExchangeStatus.Busy);
                        Check(!peer.IsCloseReady && lease.IsHeld, "busy peer reported close ready before the original owner release");
                    });
                    Equal(1, reports);
                    Check(!run.IsCompleted && !peer.IsCloseReady, "busy result became permission to exit");
                    Equal(0, peerGate.Calls); Equal(1, source.Calls);
                    release.Set();
                    await CooperativeAwait(run);
                    AssertFrameExchangeFailure(await run, WsabiWmiFrameExchangeStatus.Busy);
                    Check(peer.IsCloseReady && !lease.IsHeld, "peer host did not join canonical cleanup");
                    Equal(1, lease.DisposeCalls); Equal(ownerGate.AcquireThread, lease.DisposeThread);
                }
                finally
                {
                    release.Set(); await InvocationClose(owner, source);
                    await CooperativeAwait(peer.RequestCloseAsync());
                    await CooperativeAwait(pendingOwner);
                    if (run != null) await CooperativeAwait(run);
                }
            }
        });
    }

    private static async Task InvocationHostUnknown(bool callerStops)
    {
        using (var caller = new CancellationTokenSource())
        {
            var source = new InvocationTestSource { Handler = (request, observer) =>
            {
                if (callerStops) throw new InvalidOperationException("Unreported source detail.");
            }};
            var gate = new CooperativeTestGate();
            var session = InvocationSession(source, gate,
                callerStops ? TimeSpan.FromSeconds(3) : TimeSpan.FromMilliseconds(500));
            var published = CooperativeCompletion();
            int reports = 0;
            WsabiWmiFrameExchangeResult reported = null;
            var run = session.RunAndCloseAsync(0x34, BoundChannelPayload(), value =>
            {
                reported = value; reports++; published.TrySetResult(true);
            }, caller.Token);
            try
            {
                await CooperativeAwait(source.Returned.Task);
                if (callerStops) caller.Cancel();
                await CooperativeAwait(published.Task);
                // The fake's Returned notification precedes the transport's
                // outer call-exit update; observe that state explicitly.
                await InvocationEventually(() => session.IsCompletionUnknown);
                var expected = callerStops ? WsabiWmiFrameExchangeStatus.Cancelled : WsabiWmiFrameExchangeStatus.TimedOut;
                AssertFrameExchangeFailure(reported, expected);
                Check(!run.IsCompleted && !session.IsCloseReady && gate.LastLease.IsHeld && session.IsCompletionUnknown,
                    "bounded result ended the host main lifetime or released unknown work");
                caller.Cancel(); caller.Cancel();
                Check(!run.IsCompleted && gate.LastLease.IsHeld, "repeated stop cancelled the close join");
                var close = session.RequestCloseAsync();
                Check(ReferenceEquals(close, session.RequestCloseAsync()) && !close.IsCompleted, "host close restarted or completed unknown work");
                InvocationSupplyFinal(source); // Explicit fake-only completion, not SDK evidence.
                await CooperativeAwait(run);
                Check(ReferenceEquals(reported, await run) && session.IsCloseReady && !gate.LastLease.IsHeld,
                    "late cleanup rewrote a published result or host returned before close");
                Equal(1, reports); Equal(1, source.Calls); Equal(1, gate.LastLease.DisposeCalls);
            }
            finally { await InvocationClose(session, source); await CooperativeAwait(run); }
        }
    }

    private static async Task AssertInvocationHostFailure(Task task, Exception expected)
    {
        try { await CooperativeAwait(task); }
        catch (InvalidOperationException failure)
        {
            Check(ReferenceEquals(failure, expected), "host reporting failure changed during close");
            return;
        }
        throw new InvalidOperationException("Expected the host reporting failure after close.");
    }
}
