using System;
using System.Runtime.CompilerServices;
using System.Threading;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Prepared callbacks only: no SDK implementation, endpoint, command policy
    // or default dispatch is supplied. The dispatch must report an applicable
    // method terminal, never a notification created by client cancellation.
    // Object callbacks transfer ownership. The reader must only inspect and
    // detach the selected output; its byte view must stay stable during copy.
    // After the capture-publication claim, late objects must
    // require only independent local cleanup, not access to shared invocation
    // storage. This contract does not authenticate SDK/provider termination.
    public sealed class WsabiWmiCallbackInvocationSource<T> : IWsabiWmiInvocationSource
        where T : class, IDisposable
    {
        private readonly Action<WsabiWmiMethodRequest, Action<T>, Action<int>> dispatch;
        private readonly Func<T, byte[]> reader;
        private int entered;
        // Keep an unknown attempt's selected object alive even if dispatch
        // throws and its external callback registration is lost.
        private Capture attempt;

        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        public WsabiWmiCallbackInvocationSource(
            Action<WsabiWmiMethodRequest, Action<T>, Action<int>> dispatch, Func<T, byte[]> reader)
        {
            this.dispatch = dispatch ?? throw new ArgumentNullException(nameof(dispatch));
            this.reader = reader ?? throw new ArgumentNullException(nameof(reader));
        }

        public void Invoke(WsabiWmiMethodRequest request, IWsabiWmiInvocationObserver observer)
        {
            if (request == null) throw new ArgumentNullException(nameof(request));
            if (observer == null) throw new ArgumentNullException(nameof(observer));
            if (Interlocked.CompareExchange(ref entered, 1, 0) != 0) throw Failure();
            var capture = new Capture(reader, observer);
            attempt = capture;
            // A throw remains a failed invocation stack, not a terminal. Do not
            // close callbacks or dispose a possibly still selected object here.
            try { dispatch(request, capture.Accept, capture.Complete); }
            catch { throw Failure(); }
            finally { GC.KeepAlive(attempt); }
        }

        private static InvalidOperationException Failure()
            => new InvalidOperationException("The supplied callback invocation did not produce a usable result.");

        private sealed class Capture
        {
            private const int MaximumCaptureBytes = 4096;
            private readonly object gate = new object();
            // Weak keys do not retain all historical SDK objects. Values never
            // refer to their keys; identity lookup calls no provider equality.
            private readonly ConditionalWeakTable<T, Disposal> disposals = new ConditionalWeakTable<T, Disposal>();
            private readonly Func<T, byte[]> reader;
            private readonly IWsabiWmiInvocationObserver observer;
            private T first;
            private T processing;
            private int count;
            private bool terminal;
            private int status;
            private bool terminalForwarded;
            private bool conflict;
            private int conflictingStatus;
            private bool selectedWorkEnded;
            private int pendingDisposals;
            private bool failed;
            private byte[] bytes;
            private bool published;

            internal Capture(Func<T, byte[]> reader, IWsabiWmiInvocationObserver observer)
            {
                this.reader = reader;
                this.observer = observer;
            }

            internal void Accept(T value)
            {
                Disposal discard = null;
                lock (gate)
                {
                    if (!terminal)
                    {
                        // Count notifications, including null and repeated
                        // identities. Object uniqueness does not repair count.
                        count = Math.Min(2, count + 1);
                        if (count == 1) first = value;
                        else if (!ReferenceEquals(value, first)) discard = ReserveDisposalLocked(value);
                    }
                    else if (!ReferenceEquals(value, processing))
                        discard = ReserveDisposalLocked(value);
                }
                if (discard != null) DisposeOwned(value, discard);
            }

            internal void Complete(int terminalStatus)
            {
                T selected = null;
                bool firstTerminal;
                bool forwardConflict = false;
                bool read = false;
                lock (gate)
                {
                    firstTerminal = !terminal;
                    if (firstTerminal)
                    {
                        terminal = true;
                        status = terminalStatus;
                        selected = processing = first;
                        first = null;
                        read = status == 0 && count == 1 && selected != null;
                        if (status == 0 && !read) failed = true;
                    }
                    else if (status != terminalStatus)
                    {
                        conflict = failed = true;
                        conflictingStatus = terminalStatus;
                        forwardConflict = terminalForwarded;
                    }
                }
                if (!firstTerminal)
                {
                    if (forwardConflict) ReportTerminal(terminalStatus);
                    return;
                }

                // No finalizer may publish capture before the first terminal
                // has actually been forwarded outside our lock.
                ReportTerminal(terminalStatus);
                int? deferredConflict;
                lock (gate)
                {
                    terminalForwarded = true;
                    deferredConflict = conflict ? (int?)conflictingStatus : null;
                }
                if (deferredConflict.HasValue) ReportTerminal(deferredConflict.Value);

                byte[] detached = null;
                bool readFailed = false;
                if (read)
                {
                    try
                    {
                        byte[] value = reader(selected);
                        if (value == null || value.Length > MaximumCaptureBytes) readFailed = true;
                        // Copy before Dispose, which may mutate the SDK view.
                        else detached = (byte[])value.Clone();
                    }
                    catch { readFailed = true; }
                }
                Disposal selectedDisposal;
                lock (gate) selectedDisposal = ReserveDisposalLocked(selected);
                if (selectedDisposal != null) DisposeOwned(selected, selectedDisposal);
                lock (gate)
                {
                    failed |= readFailed;
                    bytes = detached;
                    processing = null;
                    selectedWorkEnded = true;
                }
                TryPublish();
            }

            private void ReportTerminal(int terminalStatus)
            {
                try { observer.ReportTerminal(terminalStatus); }
                catch { lock (gate) failed = true; }
            }

            // Call under gate before invoking Dispose. Returning no work also
            // covers the same object's reentrant and historical notifications.
            private Disposal ReserveDisposalLocked(T value)
            {
                if (value == null || disposals.TryGetValue(value, out _)) return null;
                var work = new Disposal { Related = !published };
                disposals.Add(value, work);
                if (work.Related) pendingDisposals++;
                return work;
            }

            private void DisposeOwned(T value, Disposal work)
            {
                bool disposalFailed = false;
                try { value.Dispose(); }
                catch { disposalFailed = true; }
                finally
                {
                    lock (gate)
                    {
                        if (work.Related)
                        {
                            failed |= disposalFailed;
                            pendingDisposals--;
                        }
                    }
                    TryPublish();
                }
            }

            private void TryPublish()
            {
                byte[] detached;
                bool failure;
                lock (gate)
                {
                    if (published || !terminalForwarded || !selectedWorkEnded || pendingDisposals != 0) return;
                    // Atomically close this capture's cleanup admission. A
                    // later object's local discard is independent by contract;
                    // this is not a drain of future SDK callbacks.
                    published = true;
                    failure = failed;
                    detached = failure ? null : bytes;
                    bytes = null;
                }
                try
                {
                    if (failure) observer.FailCapture();
                    else observer.SettleCapture(detached);
                }
                catch { } // Never leak callback/reader/provider details.
            }

            private sealed class Disposal
            {
                internal bool Related;
            }
        }
    }
}
