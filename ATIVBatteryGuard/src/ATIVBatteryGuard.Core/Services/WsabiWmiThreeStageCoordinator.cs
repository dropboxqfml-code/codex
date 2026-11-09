using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;

namespace ATIVBatteryGuard.Core.Services
{
    // Fixed three-role owner for the separately approved disable purpose.
    // No arbitrary role schedule, frame, retry or live gate factory is supplied.
    internal enum WsabiWmiThreeStageStatus
    {
        StoredReadbackMatchedCandidate, AlreadyUsed, Cancelled, TimedOut,
        GateRejected, StageRejected, StageFailed, CompletionUnknown, CleanupFailed
    }

    internal enum WsabiWmiThreeStageCleanupStatus { Complete }

    internal sealed class WsabiWmiThreeStageStopView
    {
        private readonly WsabiWmiThreeStageStopIntent intent;
        internal WsabiWmiThreeStageStopView(WsabiWmiThreeStageStopIntent intent) { this.intent = intent; }
        internal bool IsRequested => intent.IsRequested;
        internal Task Notification => intent.Notification;
    }

    internal sealed class WsabiWmiThreeStageStopIntent : IDisposable
    {
        private readonly object sync = new object();
        private readonly ManualResetEvent signal = new ManualResetEvent(false);
        private readonly TaskCompletionSource<bool> notification = NewSignal();
        private int requested;
        private bool disposed;
        internal bool IsRequested => Volatile.Read(ref requested) != 0;
        internal WaitHandle WaitHandle => signal;
        internal Task Notification => notification.Task;
        internal void Request()
        {
            lock (sync)
            {
                if (disposed) return;
                Volatile.Write(ref requested, 1);
                signal.Set(); notification.TrySetResult(true);
            }
        }
        public void Dispose() { lock (sync) { if (!disposed) { disposed = true; signal.Dispose(); } } }
        private static TaskCompletionSource<bool> NewSignal()
            => new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
    }

    // A diagnostic close failure is not actual closure. A source may confirm
    // actual closure later only with new applicable evidence that ALL related
    // accesses ended. Tests provide explicit fake evidence; production code must
    // preserve uncertainty. The close task cannot be faulted or cancelled.
    internal sealed class WsabiWmiThreeStageLifetime
    {
        private readonly object sync = new object();
        private readonly TaskCompletionSource<bool> closed = NewSignal(), uncertain = NewSignal();
        private bool started;
        internal Task ActualClose => closed.Task;
        internal Task Uncertainty => uncertain.Task;
        internal bool TryBegin()
        {
            lock (sync)
            {
                if (started || closed.Task.IsCompleted || uncertain.Task.IsCompleted) return false;
                started = true;
                return true;
            }
        }
        internal void ConfirmActualClose() { lock (sync) closed.TrySetResult(true); }
        internal void ReportUncertainClose() { lock (sync) uncertain.TrySetResult(true); }
        private static TaskCompletionSource<bool> NewSignal()
            => new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
    }

    internal sealed class WsabiWmiThreeStageOperation
    {
        private readonly Func<WsabiWmiThreeStageStopView, Task<WsabiWmiProtectionDisableObservation>> start;
        private readonly object[] additionalClaimIdentities;
        internal WsabiWmiProtectionDisableStage Role { get; }
        internal WsabiWmiThreeStageLifetime Lifetime { get; }
        internal WsabiWmiThreeStageOperation(WsabiWmiProtectionDisableStage role,
            Func<WsabiWmiThreeStageStopView, Task<WsabiWmiProtectionDisableObservation>> start,
            WsabiWmiThreeStageLifetime lifetime, params object[] additionalClaimIdentities)
        {
            if (!Enum.IsDefined(typeof(WsabiWmiProtectionDisableStage), role)) throw new ArgumentOutOfRangeException(nameof(role));
            Role = role; this.start = start ?? throw new ArgumentNullException(nameof(start));
            Lifetime = lifetime ?? throw new ArgumentNullException(nameof(lifetime));
            this.additionalClaimIdentities = (object[])(additionalClaimIdentities ?? throw new ArgumentNullException(nameof(additionalClaimIdentities))).Clone();
        }
        internal object[] AdditionalClaimIdentities => (object[])additionalClaimIdentities.Clone();
        // Result is detached numeric evidence. ActualClose must cover Start's
        // stack, source workers, capture, input access and related cleanup.
        // Any result arriving after ActualClose must access no protected object.
        internal Task<WsabiWmiProtectionDisableObservation> Start(WsabiWmiThreeStageStopView stop) => start(stop);
    }

    internal sealed class WsabiWmiThreeStageOutcome
    {
        internal WsabiWmiThreeStageStatus Status { get; }
        internal int StartedStages { get; }
        internal bool SetterRoleStarted { get; }
        internal WsabiWmiProtectionDisableSnapshot Snapshot { get; }
        internal WsabiWmiProtectionDisableDecision LastDecision { get; }
        internal WsabiWmiExchangeGateStatus? GateStatus { get; }
        internal bool IsStoredReadbackMatchedCandidate => Status == WsabiWmiThreeStageStatus.StoredReadbackMatchedCandidate;
        internal bool IsExecutable => false;
        internal bool CanInvokeMethods => false;
        internal bool CanReadHardware => false;
        internal bool CanWriteHardware => false;
        internal WsabiWmiThreeStageOutcome(WsabiWmiThreeStageStatus status, int startedStages,
            bool setterRoleStarted, WsabiWmiProtectionDisableSnapshot snapshot,
            WsabiWmiProtectionDisableDecision lastDecision, WsabiWmiExchangeGateStatus? gateStatus)
        { Status = status; StartedStages = startedStages; SetterRoleStarted = setterRoleStarted;
          Snapshot = snapshot; LastDecision = lastDecision; GateStatus = gateStatus; }
    }

    internal sealed class WsabiWmiThreeStageCoordinator
    {
        private static readonly object claimSync = new object();
        private static readonly ConditionalWeakTable<object, Claim> claims = new ConditionalWeakTable<object, Claim>();
        private static readonly Task never = new TaskCompletionSource<bool>().Task;
        private readonly object sync = new object();
        private readonly IWsabiWmiExchangeGate gate;
        private readonly WsabiWmiThreeStageOperation[] operations;
        private readonly object[] claimIdentities;
        private readonly TimeSpan acquireTimeout, displayTimeout;
        private readonly WsabiWmiProtectionDisableReview review = new WsabiWmiProtectionDisableReview();
        private readonly WsabiWmiThreeStageStopIntent stop = new WsabiWmiThreeStageStopIntent();
        private readonly WsabiWmiThreeStageStopView stopView;
        private readonly TaskCompletionSource<WsabiWmiThreeStageOutcome> display = NewDisplay();
        private readonly TaskCompletionSource<WsabiWmiThreeStageCleanupStatus> actual =
            new TaskCompletionSource<WsabiWmiThreeStageCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly WsabiWmiExchangeResource sourceResource, gateResource;
        private CancellationTokenRegistration callerRegistration;
        private bool started, finished, setterStarted;
        private int startedStages;
        private WsabiWmiThreeStageStatus? stopReason;
        private WsabiWmiExchangeGateStatus? gateStatus;
        private WsabiWmiProtectionDisableDecision lastDecision;
        internal Task<WsabiWmiThreeStageCleanupStatus> ActualCompletion => actual.Task;
        internal bool IsCompletionUnknown => sourceResource.IsQuarantined || gateResource.IsQuarantined;
        internal bool IsExecutable => false;

        internal WsabiWmiThreeStageCoordinator(IWsabiWmiExchangeGate gate,
            WsabiWmiThreeStageOperation[] operations, TimeSpan acquireTimeout, TimeSpan displayTimeout)
        {
            this.gate = gate ?? throw new ArgumentNullException(nameof(gate));
            if (operations == null) throw new ArgumentNullException(nameof(operations));
            if (operations.Length != WsabiWmiProtectionDisableReview.MaximumStages)
                throw new ArgumentException("The fixed three roles are required.", nameof(operations));
            this.operations = (WsabiWmiThreeStageOperation[])operations.Clone();
            var identities = new List<object>();
            for (int i = 0; i < this.operations.Length; i++)
            {
                var item = this.operations[i];
                if (item == null || item.Role != WsabiWmiProtectionDisableReview.StageOrder[i])
                    throw new ArgumentException("The fixed evidence order is required.", nameof(operations));
                AddIdentity(identities, item);
                AddIdentity(identities, item.Lifetime);
                foreach (var identity in item.AdditionalClaimIdentities) AddIdentity(identities, identity);
            }
            claimIdentities = identities.ToArray();
            if (acquireTimeout <= TimeSpan.Zero || acquireTimeout > WsabiWmiCooperativeFrameChannel.MaximumAcquireTimeout)
                throw new ArgumentOutOfRangeException(nameof(acquireTimeout));
            if (displayTimeout <= TimeSpan.Zero || displayTimeout > WsabiWmiFrameExchange.MaximumTimeout)
                throw new ArgumentOutOfRangeException(nameof(displayTimeout));
            this.acquireTimeout = acquireTimeout; this.displayTimeout = displayTimeout;
            stopView = new WsabiWmiThreeStageStopView(stop);
            sourceResource = WsabiWmiExchangeResource.For(this.operations[0]);
            gateResource = WsabiWmiExchangeResource.For((gate as WsabiWmiWindowsMutexGate)?.CoordinationIdentity ?? gate);
        }

        internal Task<WsabiWmiThreeStageOutcome> RunAsync(CancellationToken cancellationToken = default(CancellationToken))
        {
            lock (sync)
            {
                if (started) return Task.FromResult(Outcome(WsabiWmiThreeStageStatus.AlreadyUsed));
                started = true;
                if (!ClaimAll()) { FinishWithoutOwner(WsabiWmiThreeStageStatus.AlreadyUsed); return display.Task; }
            }
            try
            {
                callerRegistration = cancellationToken.Register(() => RequestStop(WsabiWmiThreeStageStatus.Cancelled));
                _ = MonitorDeadlineAsync();
                var owner = new Thread(RunOwner) { IsBackground = true, Name = "ATIV fixed disable owner" };
                owner.Start();
            }
            catch { FinishWithoutOwner(WsabiWmiThreeStageStatus.StageFailed); }
            return display.Task;
        }

        internal Task<WsabiWmiThreeStageCleanupStatus> RequestCloseAsync()
        {
            lock (sync)
            {
                if (!started) { started = true; FinishWithoutOwner(WsabiWmiThreeStageStatus.Cancelled); return actual.Task; }
            }
            RequestStop(WsabiWmiThreeStageStatus.Cancelled);
            return actual.Task;
        }

        internal Task<WsabiWmiThreeStageOutcome> RunAndCloseAsync(Action<WsabiWmiThreeStageOutcome> publish,
            CancellationToken cancellationToken = default(CancellationToken))
        {
            if (publish == null) throw new ArgumentNullException(nameof(publish));
            return RunAndJoinAsync(RunAsync(cancellationToken), publish);
        }

        private async Task<WsabiWmiThreeStageOutcome> RunAndJoinAsync(Task<WsabiWmiThreeStageOutcome> run,
            Action<WsabiWmiThreeStageOutcome> publish)
        {
            var outcome = await run.ConfigureAwait(false);
            if (outcome.Status == WsabiWmiThreeStageStatus.AlreadyUsed) { publish(outcome); return outcome; }
            try { publish(outcome); return outcome; }
            finally { await RequestCloseAsync().ConfigureAwait(false); }
        }

        private async Task MonitorDeadlineAsync()
        {
            if (await Task.WhenAny(Task.Delay(displayTimeout), actual.Task).ConfigureAwait(false) != actual.Task)
                RequestStop(WsabiWmiThreeStageStatus.TimedOut);
        }

        private void RequestStop(WsabiWmiThreeStageStatus reason)
        {
            lock (sync)
            {
                if (finished) return;
                if (!stopReason.HasValue) stopReason = reason;
                stop.Request();
                display.TrySetResult(Outcome(stopReason.Value));
            }
        }

        private void RunOwner()
        {
            IWsabiWmiExchangeLease lease = null;
            bool entered = false, acquiring = false;
            var final = WsabiWmiThreeStageStatus.StageFailed;
            try
            {
                if (Stopped()) { final = StopStatus(); return; }
                if (!sourceResource.TryEnter()) { final = WsabiWmiThreeStageStatus.GateRejected; return; }
                entered = true;
                if (IsCompletionUnknown) { final = WsabiWmiThreeStageStatus.GateRejected; return; }
                acquiring = true;
                var attempt = gate.Acquire(acquireTimeout, stop.WaitHandle);
                if (attempt == null) { UnknownAndHold(); return; }
                acquiring = false; lease = attempt.Lease;
                lock (sync) gateStatus = attempt.Status;
                if (attempt.Status == WsabiWmiExchangeGateStatus.Abandoned)
                { Quarantine(); final = WsabiWmiThreeStageStatus.GateRejected; return; }
                if (attempt.Status != WsabiWmiExchangeGateStatus.Acquired)
                { final = attempt.Status == WsabiWmiExchangeGateStatus.Cancelled ? WsabiWmiThreeStageStatus.Cancelled : WsabiWmiThreeStageStatus.GateRejected; return; }
                if (IsCompletionUnknown) { final = WsabiWmiThreeStageStatus.GateRejected; return; }

                foreach (var operation in operations)
                {
                    bool admitted;
                    lock (sync)
                    {
                        if (stopReason.HasValue) { final = stopReason.Value; return; }
                        admitted = operation.Lifetime.TryBegin();
                        if (admitted)
                        {
                            // This is role admission, not evidence of a hardware call.
                            startedStages++;
                            if (operation.Role == WsabiWmiProtectionDisableStage.SemanticSet0) setterStarted = true;
                        }
                    }
                    if (!admitted)
                    {
                        if (operation.Lifetime.Uncertainty.IsCompleted)
                        {
                            Quarantine(); RequestStop(WsabiWmiThreeStageStatus.CompletionUnknown);
                            operation.Lifetime.ActualClose.GetAwaiter().GetResult();
                            final = StopStatus();
                        }
                        else final = WsabiWmiThreeStageStatus.StageFailed;
                        return;
                    }
                    Task<WsabiWmiProtectionDisableObservation> result = null;
                    bool resultFailed = false;
                    try { result = operation.Start(stopView); }
                    catch { resultFailed = true; }
                    if (result == null)
                    { resultFailed = true; Quarantine(); RequestStop(WsabiWmiThreeStageStatus.CompletionUnknown); }
                    if (result != null) ObserveLateFault(result);
                    var lifetime = operation.Lifetime;
                    while (!lifetime.ActualClose.IsCompleted || (result != null && !result.IsCompleted && !Stopped()))
                    {
                        if (lifetime.Uncertainty.IsCompleted)
                        { Quarantine(); RequestStop(WsabiWmiThreeStageStatus.CompletionUnknown); }
                        if (Stopped()) lifetime.ActualClose.GetAwaiter().GetResult();
                        else
                        {
                            // Wait for a state change, then recheck. Completed
                            // tasks are omitted to avoid spinning on early data.
                            if (lifetime.ActualClose.IsCompleted)
                                Task.WhenAny(result, stop.Notification, lifetime.Uncertainty).GetAwaiter().GetResult();
                            else if (result == null || result.IsCompleted)
                                Task.WhenAny(lifetime.ActualClose, stop.Notification, lifetime.Uncertainty).GetAwaiter().GetResult();
                            else
                                Task.WhenAny(result, lifetime.ActualClose, stop.Notification, lifetime.Uncertainty).GetAwaiter().GetResult();
                        }
                    }
                    if (lifetime.Uncertainty.IsCompleted)
                    { Quarantine(); RequestStop(WsabiWmiThreeStageStatus.CompletionUnknown); }
                    if (Stopped()) { final = StopStatus(); return; }
                    if (resultFailed || result == null || result.IsFaulted || result.IsCanceled)
                    { final = WsabiWmiThreeStageStatus.StageFailed; return; }
                    var observation = result.GetAwaiter().GetResult();
                    lock (sync)
                    {
                        if (stopReason.HasValue) { final = stopReason.Value; return; }
                        lastDecision = review.Observe(observation);
                        if (!lastDecision.IsAccepted) { final = WsabiWmiThreeStageStatus.StageRejected; return; }
                    }
                }
                final = WsabiWmiThreeStageStatus.StoredReadbackMatchedCandidate;
            }
            catch
            {
                if (acquiring) { UnknownAndHold(); return; }
                // Unexpected internal failures cannot prove related closure.
                UnknownAndHold(); return;
            }
            finally
            {
                if (lease != null)
                {
                    try { lease.Dispose(); }
                    catch { Quarantine(); RequestStop(WsabiWmiThreeStageStatus.CleanupFailed); never.GetAwaiter().GetResult(); }
                }
                if (entered) sourceResource.Release();
                FinishWithoutOwner(final);
            }
        }

        private void UnknownAndHold()
        { Quarantine(); RequestStop(WsabiWmiThreeStageStatus.CompletionUnknown); never.GetAwaiter().GetResult(); }

        private void FinishWithoutOwner(WsabiWmiThreeStageStatus status)
        {
            lock (sync)
            {
                if (finished) return;
                finished = true;
                display.TrySetResult(Outcome(stopReason ?? status));
            }
            callerRegistration.Dispose();
            stop.Dispose();
            actual.TrySetResult(WsabiWmiThreeStageCleanupStatus.Complete);
        }

        private bool ClaimAll()
        {
            lock (claimSync)
            {
                foreach (var identity in claimIdentities)
                    if (claims.GetValue(identity, _ => new Claim()).Used)
                        return false;
                foreach (var identity in claimIdentities) claims.GetValue(identity, _ => new Claim()).Used = true;
                return true;
            }
        }
        private static void AddIdentity(List<object> identities, object identity)
        {
            if (identity == null) throw new ArgumentException("Claim identities must be non-null.");
            foreach (var existing in identities)
                if (ReferenceEquals(existing, identity)) throw new ArgumentException("Stage resources must be distinct.");
            identities.Add(identity);
        }
        private bool Stopped() { lock (sync) return stopReason.HasValue; }
        private WsabiWmiThreeStageStatus StopStatus() { lock (sync) return stopReason ?? WsabiWmiThreeStageStatus.Cancelled; }
        private WsabiWmiThreeStageOutcome Outcome(WsabiWmiThreeStageStatus status)
            => new WsabiWmiThreeStageOutcome(status, startedStages, setterStarted, review.Snapshot, lastDecision, gateStatus);
        private void Quarantine() { sourceResource.Quarantine(); gateResource.Quarantine(); }
        private static void ObserveLateFault(Task task)
            => task.ContinueWith(done => { _ = done.Exception; }, CancellationToken.None,
                TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
        private static TaskCompletionSource<WsabiWmiThreeStageOutcome> NewDisplay()
            => new TaskCompletionSource<WsabiWmiThreeStageOutcome>(TaskCreationOptions.RunContinuationsAsynchronously);
        private sealed class Claim { internal bool Used; }
    }
}
