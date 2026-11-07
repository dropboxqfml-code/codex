using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // A managed transport for an explicitly supplied source. It joins the
    // invocation stack, source-reported terminal and selected capture lifetime;
    // it cannot authenticate those source facts or stop an external provider.
    public sealed class WsabiWmiInvocationSnapshotTransport : IWsabiWmiMethodSnapshotTransport
    {
        private static readonly ConditionalWeakTable<IWsabiWmiInvocationSource, InvocationState> States =
            new ConditionalWeakTable<IWsabiWmiInvocationSource, InvocationState>();
        private readonly IWsabiWmiInvocationSource source;
        private readonly InvocationState state;

        internal object ExchangeIdentity => source;
        // No claimed attempt has no invocation work to await. A host must also
        // prevent a new start when it takes its own close/cleanup barrier.
        internal Task InvocationCompletion => state.Completion;
        public bool IsInvocationSettled => state.IsSettled;
        public bool IsCompletionUnknown => state.IsUnknown;
        public bool IsStopRequested => state.IsStopRequested;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        public WsabiWmiInvocationSnapshotTransport(IWsabiWmiInvocationSource source)
        {
            this.source = source ?? throw new ArgumentNullException(nameof(source));
            state = States.GetValue(source, _ => new InvocationState());
        }

        // Stop is intent only. It is shared by wrappers over the same source,
        // which represents one logical single-use attempt, not a new operation.
        public void RequestStop() => state.RequestStop();

        public Task<WsabiWmiMethodSnapshot> ExchangeAsync(WsabiWmiMethodRequest request,
            CancellationToken cancellationToken)
        {
            if (request == null)
                return Task.FromException<WsabiWmiMethodSnapshot>(new ArgumentNullException(nameof(request)));
            if (!state.TryClaim())
                return Task.FromException<WsabiWmiMethodSnapshot>(Failure());

            CancellationTokenRegistration registration = default(CancellationTokenRegistration);
            Task worker;
            try
            {
                registration = cancellationToken.Register(state.RequestStop);
                worker = Task.Run(() => state.Invoke(source, request));
            }
            catch
            {
                // Registration/scheduling failed before source entry. This is a
                // local no-dispatch failure, not inferred provider completion.
                state.FailBeforeEntry();
                worker = Task.CompletedTask;
            }
            Task<WsabiWmiMethodSnapshot> method = CompleteAsync(worker, registration);
            _ = method.ContinueWith(completed =>
            {
                _ = completed.Exception;
                state.MarkTaskEnded();
            }, CancellationToken.None, TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
            return method;
        }

        private async Task<WsabiWmiMethodSnapshot> CompleteAsync(Task worker,
            CancellationTokenRegistration registration)
        {
            try
            {
                await worker.ConfigureAwait(false);
                await state.Ready.ConfigureAwait(false);
            }
            finally
            {
                // A token callback may still be entering its short state update.
                // Join that registration before the returned task can finish.
                registration.Dispose();
            }
            return state.Publish();
        }

        private static InvalidOperationException Failure()
            => new InvalidOperationException("The supplied invocation did not produce a usable tracked result.");

        private sealed class InvocationState : IWsabiWmiInvocationObserver
        {
            private const int MaximumCaptureBytes = 4096;
            private enum CapturePhase { Unsettled, Copying, Settled }
            private readonly object gate = new object();
            private readonly TaskCompletionSource<bool> ready =
                new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            private readonly TaskCompletionSource<bool> ended =
                new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            private bool claimed;
            private bool begun;
            private bool noDispatch;
            private bool callExited;
            private bool invocationFailed;
            private bool protocolFailed;
            private bool captureFailed;
            private bool terminal;
            private int status;
            private CapturePhase capture;
            private byte[] bytes;
            private bool stopped;
            private bool published;
            private bool taskEnded;

            internal Task Ready => ready.Task;
            internal Task Completion { get { lock (gate) return claimed ? ended.Task : Task.CompletedTask; } }
            internal bool IsSettled { get { lock (gate) return !claimed || taskEnded; } }
            internal bool IsUnknown
            {
                get
                {
                    lock (gate)
                        return callExited && !terminal && (invocationFailed || protocolFailed || stopped) && !taskEnded;
                }
            }
            public bool IsStopRequested { get { lock (gate) return stopped; } }

            internal bool TryClaim()
            {
                lock (gate)
                {
                    if (claimed) return false;
                    claimed = true;
                    return true;
                }
            }

            internal void RequestStop()
            {
                lock (gate) stopped = true;
            }

            internal void Invoke(IWsabiWmiInvocationSource source, WsabiWmiMethodRequest request)
            {
                bool enter;
                lock (gate)
                {
                    // Linearize entry admission against stop. A later stop is
                    // intent for an admitted call, not a no-dispatch guarantee.
                    enter = !stopped;
                    if (enter) begun = true;
                    else
                    {
                        noDispatch = true;
                        capture = CapturePhase.Settled;
                        ready.TrySetResult(true);
                    }
                }
                if (!enter) return;
                bool failed = false;
                try { source.Invoke(request, this); }
                catch { failed = true; }
                finally
                {
                    lock (gate)
                    {
                        // Call exit and its fixed failure are one state update.
                        invocationFailed = failed;
                        callExited = true;
                        SignalReadyLocked();
                    }
                }
            }

            internal void FailBeforeEntry()
            {
                lock (gate)
                {
                    stopped = true;
                    if (begun)
                    {
                        // Do not manufacture no-dispatch if a worker entered
                        // despite a scheduling/registration failure.
                        invocationFailed = true;
                        protocolFailed = true;
                        SignalReadyLocked();
                        return;
                    }
                    noDispatch = true;
                    invocationFailed = true;
                    capture = CapturePhase.Settled;
                    ready.TrySetResult(true);
                }
            }

            public bool ReportTerminal(int terminalStatus)
            {
                lock (gate)
                {
                    if (published || noDispatch) return false;
                    if (!begun)
                    {
                        protocolFailed = true;
                        return false;
                    }
                    if (terminal)
                    {
                        if (status != terminalStatus) protocolFailed = true;
                        return false;
                    }
                    terminal = true;
                    status = terminalStatus;
                    SignalReadyLocked();
                    return true;
                }
            }

            public bool SettleCapture(byte[] detachedBytes)
            {
                int terminalStatus;
                lock (gate)
                {
                    if (!ReserveCaptureLocked()) return false;
                    terminalStatus = status;
                }

                byte[] captured = null;
                bool failed = false;
                // Nonzero terminal status is authoritative: do not inspect or
                // retain the supplied bytes, even their length, on that path.
                if (terminalStatus == 0)
                {
                    try
                    {
                        if (detachedBytes == null || detachedBytes.Length > MaximumCaptureBytes) failed = true;
                        else captured = (byte[])detachedBytes.Clone();
                    }
                    catch { failed = true; }
                }
                lock (gate)
                {
                    bytes = captured;
                    captureFailed = failed;
                    capture = CapturePhase.Settled;
                    SignalReadyLocked();
                }
                return true;
            }

            public bool FailCapture()
            {
                lock (gate)
                {
                    if (!ReserveCaptureLocked()) return false;
                    captureFailed = true;
                    capture = CapturePhase.Settled;
                    SignalReadyLocked();
                    return true;
                }
            }

            private bool ReserveCaptureLocked()
            {
                if (published || noDispatch) return false;
                if (!begun || !terminal || capture != CapturePhase.Unsettled)
                {
                    protocolFailed = true;
                    return false;
                }
                capture = CapturePhase.Copying;
                return true;
            }

            private void SignalReadyLocked()
            {
                if (callExited && terminal && capture == CapturePhase.Settled)
                    ready.TrySetResult(true);
            }

            internal WsabiWmiMethodSnapshot Publish()
            {
                lock (gate)
                {
                    // This is the single outcome-publication claim, after the
                    // worker and token registration have both been joined.
                    published = true;
                    if (invocationFailed || protocolFailed || captureFailed)
                    {
                        bytes = null;
                        throw Failure();
                    }
                    if (stopped || noDispatch)
                    {
                        bytes = null;
                        throw new OperationCanceledException();
                    }
                    if (status != 0) return new WsabiWmiMethodSnapshot(status, null);
                    var inner = new Dictionary<string, object>(StringComparer.Ordinal) { { "Bytes", bytes } };
                    var outer = new Dictionary<string, object>(StringComparer.Ordinal)
                    {
                        { "outData", new ReadOnlyDictionary<string, object>(inner) }
                    };
                    bytes = null;
                    return new WsabiWmiMethodSnapshot(status, new ReadOnlyDictionary<string, object>(outer));
                }
            }

            internal void MarkTaskEnded()
            {
                lock (gate) taskEnded = true;
                ended.TrySetResult(true);
            }
        }
    }
}
