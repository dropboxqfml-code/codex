using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    public sealed class WsabiWmiProtectionStageDiagnostic
    {
        public WsabiWmiProtectionTransitionStage Role { get; }
        public string BindingVerdict { get; }
        public string ReadVerdict { get; }
        public string SetterVerdict { get; }
        internal WsabiWmiProtectionStageDiagnostic(WsabiWmiProtectionBoundStage stage)
        { Role = stage.Binding.Role; BindingVerdict = stage.ReviewStatus.ToString(); ReadVerdict = stage.ReadVerdict; SetterVerdict = stage.SetterVerdict; }
    }

    public enum WsabiWmiProtectionTransitionStatus
    {
        StoredReadbackMatchedCandidate, AlreadyUsed, Cancelled, TimedOut,
        GateRejected, StageRejected, StageFailed, CompletionUnknown, CleanupFailed
    }

    public sealed class WsabiWmiProtectionTransitionOutcome
    {
        public WsabiWmiProtectionTransitionStatus Status { get; }
        public int StartedStages { get; }
        public bool SetterRoleStarted { get; }
        public WsabiWmiProtectionTransitionSnapshot Snapshot { get; }
        public WsabiWmiProtectionTransitionDecisionStatus? LastDecisionStatus { get; }
        public WsabiWmiExchangeGateStatus? GateStatus { get; }
        public bool IsChargeLimitConfirmed => false;
        public bool CanWriteHardware => false;
        internal WsabiWmiProtectionTransitionOutcome(WsabiWmiSevenStageOutcome outcome)
        {
            Status = (WsabiWmiProtectionTransitionStatus)outcome.Status;
            StartedStages = outcome.StartedStages; SetterRoleStarted = outcome.SetterRoleStarted;
            Snapshot = outcome.Snapshot; LastDecisionStatus = outcome.LastDecision?.Status;
            GateStatus = outcome.GateStatus;
        }
    }

    // Fixed-purpose facade only. Core remains independent of System.Management.
    // The live entry supplies its own validated SDK factory and fixed gate;
    // this dependency-injection constructor is also used by offline tests.
    public sealed class WsabiWmiProtectionTransitionSession
    {
        private readonly WsabiWmiSevenStageCoordinator coordinator;
        private readonly Runner[] runners = new Runner[7];
        private readonly WsabiWmiProtectionBoundStage[] stages;
        public bool IsChargeLimitConfirmed => false;
        public bool CanWriteHardware => false;
        public bool IsCompletionUnknown => coordinator.IsCompletionUnknown;

        public WsabiWmiProtectionTransitionSession(WsabiWmiProtectionTransitionAttempt attempt,
            IWsabiWmiProtectionLeafFactory factory, IWsabiWmiExchangeGate gate)
            : this(attempt, factory, gate, TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(10)) { }

        internal WsabiWmiProtectionTransitionSession(WsabiWmiProtectionTransitionAttempt attempt,
            IWsabiWmiProtectionLeafFactory factory, IWsabiWmiExchangeGate gate,
            TimeSpan acquireTimeout, TimeSpan displayTimeout)
        {
            if (attempt == null) throw new ArgumentNullException(nameof(attempt));
            if (factory == null) throw new ArgumentNullException(nameof(factory));
            object target = factory.TargetIdentity;
            if (!attempt.TargetMatches(target)) throw new ArgumentException("The fixed trial target does not match.", nameof(factory));
            stages = new WsabiWmiProtectionBoundStage[7];
            for (int i = 0; i < stages.Length; i++)
            {
                var role = WsabiWmiProtectionTransitionReview.StageOrder[i];
                var binding = new WsabiWmiProtectionStageBinding(role, attempt, target,
                    new object(), new object(), new object(), new object());
                var runner = new Runner(attempt, factory, role, binding); runners[i] = runner;
                stages[i] = new WsabiWmiProtectionBoundStage(binding, attempt.GetFirstComponent(role),
                    attempt.GetSecondComponent(role), attempt.GetComparison(role), runner.Start,
                    runner.InvocationEnd.Task, runner.OutputClose.Task, runner.InputClose.Task);
#if PORTABLE_TESTS
                runner.StageLifetimeForTests = stages[i].Operation.Lifetime;
#endif
            }
            coordinator = WsabiWmiProtectionBindingPlan.Create(gate, stages, acquireTimeout, displayTimeout);
        }

        public IReadOnlyList<WsabiWmiProtectionStageDiagnostic> GetStageDiagnostics()
        {
            var values = new WsabiWmiProtectionStageDiagnostic[7];
            for (int i = 0; i < values.Length; i++) values[i] = new WsabiWmiProtectionStageDiagnostic(stages[i]);
            return Array.AsReadOnly(values);
        }

        public async Task<WsabiWmiProtectionTransitionOutcome> RunAsync(CancellationToken token = default(CancellationToken))
            => new WsabiWmiProtectionTransitionOutcome(await coordinator.RunAsync(token).ConfigureAwait(false));

        public async Task<WsabiWmiProtectionTransitionOutcome> RunAndCloseAsync(Action<WsabiWmiProtectionTransitionOutcome> publish,
            CancellationToken token = default(CancellationToken))
        {
            if (publish == null) throw new ArgumentNullException(nameof(publish));
            var result = await coordinator.RunAndCloseAsync(value => publish(new WsabiWmiProtectionTransitionOutcome(value)), token).ConfigureAwait(false);
            return new WsabiWmiProtectionTransitionOutcome(result);
        }

        public async Task<WsabiWmiProtectionCleanupStatus> RequestCloseAsync()
        {
            await coordinator.RequestCloseAsync().ConfigureAwait(false);
            return WsabiWmiProtectionCleanupStatus.Complete;
        }

#if PORTABLE_TESTS
        // Only to join explicitly detached fake resources after fault injection.
        // No live SDK recovery path calls this method.
        internal void ConfirmDetachedForTests()
        {
            foreach (var runner in runners) runner.StageLifetimeForTests?.ConfirmActualClose();
        }
#endif

        private sealed class Runner
        {
            private readonly WsabiWmiProtectionTransitionAttempt attempt;
            private readonly IWsabiWmiProtectionLeafFactory factory;
            private readonly WsabiWmiProtectionLeafRequest request;
            private readonly WsabiWmiProtectionStageBinding binding;
            private WsabiWmiProtectionLeaf retainedLeaf;
#if PORTABLE_TESTS
            internal WsabiWmiSevenStageLifetime StageLifetimeForTests;
#endif
            internal readonly TaskCompletionSource<bool> InvocationEnd = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            internal readonly TaskCompletionSource<WsabiWmiBoundStageCleanupStatus> OutputClose = NewCleanup();
            internal readonly TaskCompletionSource<WsabiWmiBoundStageCleanupStatus> InputClose = NewCleanup();
            internal Runner(WsabiWmiProtectionTransitionAttempt attempt, IWsabiWmiProtectionLeafFactory factory,
                WsabiWmiProtectionTransitionStage role, WsabiWmiProtectionStageBinding binding)
            { this.attempt = attempt; this.factory = factory; request = new WsabiWmiProtectionLeafRequest(attempt, role); this.binding = binding; }

            internal Task<WsabiWmiProtectionBoundReply> Start(WsabiWmiSevenStageStopView stop)
            {
                Task<WsabiWmiProtectionLeaf> preparing;
                try { preparing = factory.PrepareAsync(request, new WsabiWmiProtectionStop(() => stop.IsRequested, stop.Notification)); }
                catch { UnknownPreparation(); throw; }
                if (preparing == null) { UnknownPreparation(); return null; }
                return RunLeafAsync(preparing, stop);
            }

            private async Task<WsabiWmiProtectionBoundReply> RunLeafAsync(Task<WsabiWmiProtectionLeaf> preparing,
                WsabiWmiSevenStageStopView stop)
            {
                try { retainedLeaf = await preparing.ConfigureAwait(false); }
                catch { UnknownPreparation(); return null; }
                if (retainedLeaf == null) { UnknownPreparation(); return null; }
                WsabiWmiReplyResult reply = null;
                if (retainedLeaf.IsReady && !stop.IsRequested)
                {
                    var transport = new WsabiWmiInvocationSnapshotTransport(retainedLeaf.Source);
                    var channel = new WsabiWmiBoundFrameChannel(attempt.Binder, transport);
                    Task forwarding = null;
                    try
                    {
                        if (stop.IsRequested) transport.RequestStop();
                        var pending = channel.ExchangeAsync(request.Request.Frame, CancellationToken.None);
                        forwarding = ForwardStopAsync(stop, transport);
                        try { reply = await pending.ConfigureAwait(false); } catch { }
                    }
                    finally
                    {
                        // A rejected result/throw is not a terminal. This await
                        // remains pending for an actually untracked invocation.
                        await transport.InvocationCompletion.ConfigureAwait(false);
                        if (forwarding != null) await forwarding.ConfigureAwait(false);
                        InvocationEnd.TrySetResult(true);
                    }
                }
                else InvocationEnd.TrySetResult(true); // no source.Invoke entry
                await CloseLeafAsync().ConfigureAwait(false);
                var exchange = reply == null
                    ? new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.TransportFailure)
                    : new WsabiWmiFrameExchangeResult(WsabiWmiFrameExchangeStatus.ReplyReceived, reply);
                return new WsabiWmiProtectionBoundReply(binding, exchange);
            }

            private async Task CloseLeafAsync()
            {
                WsabiWmiProtectionCleanupStatus output;
                try
                {
                    var pending = retainedLeaf.CloseOutputAsync();
                    output = pending == null ? WsabiWmiProtectionCleanupStatus.Unknown : await pending.ConfigureAwait(false);
                }
                catch { output = WsabiWmiProtectionCleanupStatus.Unknown; }
                OutputClose.TrySetResult(Map(output));
                if (output != WsabiWmiProtectionCleanupStatus.Complete)
                {
                    // Uncertain output/handler ownership cannot release inputs.
                    InputClose.TrySetResult(WsabiWmiBoundStageCleanupStatus.Unknown); return;
                }
                WsabiWmiProtectionCleanupStatus input;
                try
                {
                    var pending = retainedLeaf.CloseInputsAsync();
                    input = pending == null ? WsabiWmiProtectionCleanupStatus.Unknown : await pending.ConfigureAwait(false);
                }
                catch { input = WsabiWmiProtectionCleanupStatus.Unknown; }
                InputClose.TrySetResult(Map(input));
            }

            private void UnknownPreparation()
            {
                InvocationEnd.TrySetException(new InvalidOperationException("The fixed leaf preparation did not establish ownership."));
                OutputClose.TrySetResult(WsabiWmiBoundStageCleanupStatus.Unknown);
                InputClose.TrySetResult(WsabiWmiBoundStageCleanupStatus.Unknown);
            }

            private static async Task ForwardStopAsync(WsabiWmiSevenStageStopView stop, WsabiWmiInvocationSnapshotTransport transport)
            {
                await Task.WhenAny(stop.Notification, transport.InvocationCompletion).ConfigureAwait(false);
                if (stop.IsRequested) transport.RequestStop();
            }

            private static WsabiWmiBoundStageCleanupStatus Map(WsabiWmiProtectionCleanupStatus status)
                => status == WsabiWmiProtectionCleanupStatus.Complete ? WsabiWmiBoundStageCleanupStatus.Complete
                    : status == WsabiWmiProtectionCleanupStatus.Failed ? WsabiWmiBoundStageCleanupStatus.Failed : WsabiWmiBoundStageCleanupStatus.Unknown;
            private static TaskCompletionSource<WsabiWmiBoundStageCleanupStatus> NewCleanup()
                => new TaskCompletionSource<WsabiWmiBoundStageCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
        }
    }
}
