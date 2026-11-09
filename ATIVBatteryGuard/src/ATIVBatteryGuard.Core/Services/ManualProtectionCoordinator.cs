using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    internal sealed class ManualProtectionStageOperation
    {
        private readonly Func<WsabiWmiThreeStageStopView, Task<ManualProtectionObservation>> start;
        private readonly object[] additionalClaimIdentities;
        internal ManualProtectionRole Role { get; }
        internal WsabiWmiThreeStageLifetime Lifetime { get; }
        internal ManualProtectionStageOperation(ManualProtectionRole role,
            Func<WsabiWmiThreeStageStopView, Task<ManualProtectionObservation>> start,
            WsabiWmiThreeStageLifetime lifetime, params object[] additionalClaimIdentities)
        {
            if (!Enum.IsDefined(typeof(ManualProtectionRole), role)) throw new ArgumentOutOfRangeException(nameof(role));
            Role = role; this.start = start ?? throw new ArgumentNullException(nameof(start));
            Lifetime = lifetime ?? throw new ArgumentNullException(nameof(lifetime));
            this.additionalClaimIdentities = (object[])(additionalClaimIdentities ?? throw new ArgumentNullException(nameof(additionalClaimIdentities))).Clone();
        }
        internal object[] AdditionalClaimIdentities => (object[])additionalClaimIdentities.Clone();
        // Result is detached numeric evidence. ActualClose must cover Start's
        // stack, source workers, capture, input access and related cleanup.
        // Any result arriving after ActualClose must access no protected object.
        internal Task<ManualProtectionObservation> Start(WsabiWmiThreeStageStopView stop) => start(stop);
    }

    public sealed class ManualProtectionOutcome
    {
        public ManualProtectionOperation Operation { get; }
        public ManualProtectionStatus Status { get; }
        public int StartedStages { get; }
        public bool SetterRoleStarted { get; }
        public int ReadCandidates { get; }
        public bool SetterReceiptAccepted { get; }
        public int? PreModeCandidate { get; }
        public int? ModeCandidate { get; }
        public int? UpperCandidate { get; }
        public int? LowerCandidate { get; }
        public WsabiWmiExchangeGateStatus? GateStatus { get; }
        public bool IsChargeLimitConfirmed => false;
        public bool CanWriteHardware => false;
        internal ManualProtectionOutcome(ManualProtectionOperation operation, ManualProtectionStatus status, int startedStages,
            bool setterRoleStarted, ManualProtectionSnapshot snapshot, WsabiWmiExchangeGateStatus? gateStatus)
        {
            Operation = operation; Status = status;
            if (status == ManualProtectionStatus.Busy) return;
            StartedStages = startedStages; SetterRoleStarted = setterRoleStarted;
            ReadCandidates = snapshot.ReadCandidates; SetterReceiptAccepted = snapshot.SetterReceiptAccepted;
            PreModeCandidate = snapshot.PreModeCandidate; GateStatus = gateStatus;
            bool success = status == ManualProtectionStatus.StateRead || status == ManualProtectionStatus.ChangedCandidate ||
                status == ManualProtectionStatus.AlreadyDesiredCandidate;
            if (success) { ModeCandidate = snapshot.ModeCandidate; UpperCandidate = snapshot.UpperCandidate; LowerCandidate = snapshot.LowerCandidate; }
        }
    }

    internal sealed class ManualProtectionCoordinator
    {
        private static readonly object claimSync = new object();
        private static readonly ConditionalWeakTable<object, Claim> claims = new ConditionalWeakTable<object, Claim>();
        private static readonly Task never = new TaskCompletionSource<bool>().Task;
        private readonly object sync = new object();
        private readonly IWsabiWmiExchangeGate gate;
        private readonly ManualProtectionStageOperation[] operations;
        private readonly object[] claimIdentities;
        private readonly TimeSpan acquireTimeout, displayTimeout;
        private readonly ManualProtectionReview review;
        private readonly ManualProtectionAttempt attempt;
        private readonly WsabiWmiThreeStageStopIntent stop = new WsabiWmiThreeStageStopIntent();
        private readonly WsabiWmiThreeStageStopView stopView;
        private readonly TaskCompletionSource<ManualProtectionOutcome> display = NewDisplay();
        private readonly TaskCompletionSource<WsabiWmiThreeStageCleanupStatus> actual =
            new TaskCompletionSource<WsabiWmiThreeStageCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly WsabiWmiExchangeResource sourceResource, gateResource;
        private CancellationTokenRegistration callerRegistration;
        private bool started, finished, setterStarted;
        private int startedStages;
        private ManualProtectionStatus? stopReason;
        private WsabiWmiExchangeGateStatus? gateStatus;
        private ManualProtectionDecision lastDecision;
        internal Task<WsabiWmiThreeStageCleanupStatus> ActualCompletion => actual.Task;
        internal bool IsCompletionUnknown => sourceResource.IsQuarantined || gateResource.IsQuarantined;
        internal bool IsExecutable => false;

        internal ManualProtectionCoordinator(ManualProtectionAttempt attempt, IWsabiWmiExchangeGate gate,
            ManualProtectionStageOperation[] operations, TimeSpan acquireTimeout, TimeSpan displayTimeout)
        {
            this.attempt = attempt ?? throw new ArgumentNullException(nameof(attempt));
            review = new ManualProtectionReview(attempt.Operation);
            this.gate = gate ?? throw new ArgumentNullException(nameof(gate));
            if (operations == null) throw new ArgumentNullException(nameof(operations));
            if (operations.Length != attempt.StageOrder.Count)
                throw new ArgumentException("The fixed manual operation roles are required.", nameof(operations));
            this.operations = (ManualProtectionStageOperation[])operations.Clone();
            var identities = new List<object>();
            for (int i = 0; i < this.operations.Length; i++)
            {
                var item = this.operations[i];
                if (item == null || item.Role != attempt.StageOrder[i])
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

        internal Task<ManualProtectionOutcome> RunAsync(CancellationToken cancellationToken = default(CancellationToken))
        {
            lock (sync)
            {
                if (started) return Task.FromResult(Outcome(ManualProtectionStatus.Busy));
                started = true;
                if (!ClaimAll()) { FinishWithoutOwner(ManualProtectionStatus.Busy); return display.Task; }
            }
            try
            {
                callerRegistration = cancellationToken.Register(() => RequestStop(ManualProtectionStatus.Cancelled));
                _ = MonitorDeadlineAsync();
                var owner = new Thread(RunOwner) { IsBackground = true, Name = "ATIV manual protection owner" };
                owner.Start();
            }
            catch { FinishWithoutOwner(ManualProtectionStatus.Rejected); }
            return display.Task;
        }

        internal Task<WsabiWmiThreeStageCleanupStatus> RequestCloseAsync()
        {
            lock (sync)
            {
                if (!started) { started = true; FinishWithoutOwner(ManualProtectionStatus.Cancelled); return actual.Task; }
            }
            RequestStop(ManualProtectionStatus.Cancelled);
            return actual.Task;
        }

        internal Task<ManualProtectionOutcome> RunAndCloseAsync(Action<ManualProtectionOutcome> publish,
            CancellationToken cancellationToken = default(CancellationToken))
        {
            if (publish == null) throw new ArgumentNullException(nameof(publish));
            return RunAndJoinAsync(RunAsync(cancellationToken), publish);
        }

        private async Task<ManualProtectionOutcome> RunAndJoinAsync(Task<ManualProtectionOutcome> run,
            Action<ManualProtectionOutcome> publish)
        {
            var outcome = await run.ConfigureAwait(false);
            if (outcome.Status == ManualProtectionStatus.Busy) { publish(outcome); return outcome; }
            try { publish(outcome); return outcome; }
            finally { await RequestCloseAsync().ConfigureAwait(false); }
        }

        private async Task MonitorDeadlineAsync()
        {
            if (await Task.WhenAny(Task.Delay(displayTimeout), actual.Task).ConfigureAwait(false) != actual.Task)
                RequestStop(ManualProtectionStatus.TimedOut);
        }

        private void RequestStop(ManualProtectionStatus reason)
        {
            lock (sync)
            {
                if (finished) return;
                // Cancellation after role admission does not establish that
                // an entered source or semantic setting was prevented.
                if (reason == ManualProtectionStatus.Cancelled && startedStages != 0)
                    reason = ManualProtectionStatus.Unknown;
                if (!stopReason.HasValue) stopReason = reason;
                stop.Request();
                display.TrySetResult(Outcome(stopReason.Value));
            }
        }

        private void RunOwner()
        {
            IWsabiWmiExchangeLease lease = null;
            bool entered = false, acquiring = false;
            var final = ManualProtectionStatus.Rejected;
            try
            {
                if (Stopped()) { final = StopStatus(); return; }
                if (!sourceResource.TryEnter()) { final = IsCompletionUnknown ? ManualProtectionStatus.Unknown : ManualProtectionStatus.Busy; return; }
                entered = true;
                if (IsCompletionUnknown) { final = ManualProtectionStatus.Unknown; return; }
                acquiring = true;
                var attempt = gate.Acquire(acquireTimeout, stop.WaitHandle);
                if (attempt == null) { UnknownAndHold(); return; }
                acquiring = false; lease = attempt.Lease;
                lock (sync) gateStatus = attempt.Status;
                if (attempt.Status == WsabiWmiExchangeGateStatus.Abandoned)
                { Quarantine(); final = ManualProtectionStatus.Unknown; return; }
                if (attempt.Status != WsabiWmiExchangeGateStatus.Acquired)
                { final = attempt.Status == WsabiWmiExchangeGateStatus.Cancelled ? ManualProtectionStatus.Cancelled : ManualProtectionStatus.Rejected; return; }
                if (IsCompletionUnknown) { final = ManualProtectionStatus.Unknown; return; }

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
                            if (operation.Role == ManualProtectionRole.SemanticSet) setterStarted = true;
                        }
                    }
                    if (!admitted)
                    {
                        if (operation.Lifetime.Uncertainty.IsCompleted)
                        {
                            Quarantine(); RequestStop(ManualProtectionStatus.Unknown);
                            operation.Lifetime.ActualClose.GetAwaiter().GetResult();
                            final = StopStatus();
                        }
                        else final = ManualProtectionStatus.Rejected;
                        return;
                    }
                    Task<ManualProtectionObservation> result = null;
                    bool resultFailed = false;
                    try { result = operation.Start(stopView); }
                    catch { resultFailed = true; }
                    if (result == null)
                    { resultFailed = true; Quarantine(); RequestStop(ManualProtectionStatus.Unknown); }
                    if (result != null) ObserveLateFault(result);
                    var lifetime = operation.Lifetime;
                    while (!lifetime.ActualClose.IsCompleted || (result != null && !result.IsCompleted && !Stopped()))
                    {
                        if (lifetime.Uncertainty.IsCompleted)
                        { Quarantine(); RequestStop(ManualProtectionStatus.Unknown); }
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
                    { Quarantine(); RequestStop(ManualProtectionStatus.Unknown); }
                    if (Stopped()) { final = StopStatus(); return; }
                    if (resultFailed || result == null || result.IsFaulted || result.IsCanceled)
                    { final = ManualProtectionStatus.Rejected; return; }
                    var observation = result.GetAwaiter().GetResult();
                    lock (sync)
                    {
                        if (stopReason.HasValue) { final = stopReason.Value; return; }
                        lastDecision = review.Observe(observation);
                        if (!lastDecision.IsAccepted) { final = ManualProtectionStatus.Rejected; return; }
                        if (lastDecision.IsTerminal) { final = lastDecision.Snapshot.Status; return; }
                    }
                }
                final = ManualProtectionStatus.Rejected;
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
                    catch { Quarantine(); RequestStop(ManualProtectionStatus.Unknown); never.GetAwaiter().GetResult(); }
                }
                if (entered) sourceResource.Release();
                FinishWithoutOwner(final);
            }
        }

        private void UnknownAndHold()
        { Quarantine(); RequestStop(ManualProtectionStatus.Unknown); never.GetAwaiter().GetResult(); }

        private void FinishWithoutOwner(ManualProtectionStatus status)
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
        private ManualProtectionStatus StopStatus() { lock (sync) return stopReason ?? ManualProtectionStatus.Cancelled; }
        private ManualProtectionOutcome Outcome(ManualProtectionStatus status)
            => new ManualProtectionOutcome(attempt.Operation, status, startedStages, setterStarted, review.Snapshot, gateStatus);
        private void Quarantine() { sourceResource.Quarantine(); gateResource.Quarantine(); }
        private static void ObserveLateFault(Task task)
            => task.ContinueWith(done => { _ = done.Exception; }, CancellationToken.None,
                TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
        private static TaskCompletionSource<ManualProtectionOutcome> NewDisplay()
            => new TaskCompletionSource<ManualProtectionOutcome>(TaskCreationOptions.RunContinuationsAsynchronously);
        private sealed class Claim { internal bool Used; }
    }
}
