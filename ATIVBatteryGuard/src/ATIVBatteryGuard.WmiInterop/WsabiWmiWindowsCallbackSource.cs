using System;
using System.Management;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.WmiInterop
{
    // A supplied observer must be dedicated to this attempt: no other user of
    // its ObjectReady objects, Cancel, reuse or independent dispatch. There is
    // no InvokeMethod, target selection, default dispatch or hardware policy.
    // Post-cutoff queued handlers may only do independent local cleanup.
    internal sealed class WsabiWmiWindowsCallbackSource : IWsabiWmiInvocationSource
    {
        private static readonly ConditionalWeakTable<ManagementOperationObserver, ObserverOwner> Observers =
            new ConditionalWeakTable<ManagementOperationObserver, ObserverOwner>();
        private readonly object gate = new object();
        private readonly ManagementOperationObserver sdkObserver;
        private readonly Action<ManagementOperationObserver, WsabiWmiMethodRequest> dispatch;
        private readonly WsabiWmiWindowsOwnedInputPair protectedInputs;
        private readonly ConditionalWeakTable<ManagementBaseObject, OwnedWmiResult> objects =
            new ConditionalWeakTable<ManagementBaseObject, OwnedWmiResult>();
        private readonly WsabiWmiCallbackInvocationSource<OwnedWmiResult> source;
        private Action<OwnedWmiResult> accept;
        private Action<int> terminal;
        private IWsabiWmiInvocationObserver output;
        private int entered;
        private bool registrationDone;
        private bool registrationStarted;
        private bool prepared;
        private bool reserved;
        private bool invocationEntered;
        private bool callbacksArmed;
        private bool preparationFault;
        private bool unusedClosing;
        private bool cleanupFailed;
        private readonly TaskCompletionSource<WsabiWmiWindowsCleanupStatus> closed =
            new TaskCompletionSource<WsabiWmiWindowsCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
        private bool objectSubscribed;
        private bool completedSubscribed;
        private int activeHandlers;
        private int activeObjects;
        private bool completionObserved;
        private bool closing;
        private bool captureSeen;
        private bool failed;
        private byte[] bytes;
        private bool finalizationStarted;

        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        internal async Task<WsabiWmiWindowsPreparationStatus> PrepareAsync(CancellationToken token)
        {
            lock (gate)
            {
                if (registrationStarted) throw Failure();
                registrationStarted = true;
            }
            bool registrationFailed = false;
            try
            {
                await Task.Run(() =>
                {
                    if (PreparationStopped(token)) return;
                    // Record the attempt before external add: even mutate-then-
                    // throw accessors require a matching remove attempt.
                    lock (gate) objectSubscribed = true;
                    sdkObserver.ObjectReady += OnObject;
                    if (PreparationStopped(token)) return;
                    lock (gate) completedSubscribed = true;
                    sdkObserver.Completed += OnCompleted;
                }).ConfigureAwait(false);
            }
            catch { registrationFailed = true; }
            WsabiWmiWindowsPreparationStatus status;
            lock (gate)
            {
                registrationDone = true;
                status = registrationFailed ? WsabiWmiWindowsPreparationStatus.RegistrationFailed
                    : preparationFault ? WsabiWmiWindowsPreparationStatus.UnexpectedCallback
                    : unusedClosing || token.IsCancellationRequested ? WsabiWmiWindowsPreparationStatus.Cancelled
                    : WsabiWmiWindowsPreparationStatus.Ready;
                prepared = status == WsabiWmiWindowsPreparationStatus.Ready;
                // Failure classification and its primary admission cutoff are
                // one decision; a later event cannot enter an older outcome.
                if (!prepared) unusedClosing = closing = true;
            }
            if (status == WsabiWmiWindowsPreparationStatus.Ready) return status;
            var cleanup = await CloseUnusedAsync().ConfigureAwait(false);
            return cleanup == WsabiWmiWindowsCleanupStatus.Failed
                ? WsabiWmiWindowsPreparationStatus.CleanupFailed : status;
        }

        private bool PreparationStopped(CancellationToken token)
        {
            lock (gate) return unusedClosing || preparationFault || token.IsCancellationRequested;
        }

        internal bool TryReserve()
        {
            lock (gate)
            {
                if (!prepared || preparationFault || reserved || unusedClosing) return false;
                reserved = true;
                return true;
            }
        }

        internal Task<WsabiWmiWindowsCleanupStatus> CloseUnusedAsync()
        {
            lock (gate)
            {
                // Once Core entered Invoke, close is not evidence that dispatch
                // stopped. Only the normal capture/handler join may end it.
                if (!invocationEntered)
                {
                    unusedClosing = closing = true;
                    prepared = false;
                }
            }
            _ = Task.Run(TryFinalize);
            return closed.Task;
        }

        public WsabiWmiWindowsCallbackSource(ManagementOperationObserver dedicatedObserver,
            Action<ManagementOperationObserver, WsabiWmiMethodRequest> dispatch,
            WsabiWmiWindowsOwnedInputPair protectedInputs = null)
        {
            if (dedicatedObserver == null) throw new ArgumentNullException(nameof(dedicatedObserver));
            if (dispatch == null) throw new ArgumentNullException(nameof(dispatch));
            ObserverOwner owner = Observers.GetValue(dedicatedObserver, _ => new ObserverOwner());
            if (Interlocked.CompareExchange(ref owner.Claimed, 1, 0) != 0)
                throw new ArgumentException("The supplied WMI observer already belongs to a single-use binding.", nameof(dedicatedObserver));
            sdkObserver = dedicatedObserver;
            this.dispatch = dispatch;
            this.protectedInputs = protectedInputs;
            source = new WsabiWmiCallbackInvocationSource<OwnedWmiResult>(Dispatch, value => value.Read());
        }

        public void Invoke(WsabiWmiMethodRequest request, IWsabiWmiInvocationObserver observer)
        {
            if (request == null) throw new ArgumentNullException(nameof(request));
            if (observer == null) throw new ArgumentNullException(nameof(observer));
            if (Interlocked.CompareExchange(ref entered, 1, 0) != 0) throw Failure();
            lock (gate)
            {
                invocationEntered = true;
                if (!prepared || !reserved || preparationFault || unusedClosing) throw Failure();
            }
            output = observer;
            source.Invoke(request, new CaptureObserver(this));
        }

        private void Dispatch(WsabiWmiMethodRequest request, Action<OwnedWmiResult> onObject, Action<int> onTerminal)
        {
            lock (gate)
            {
                if (preparationFault || unusedClosing) throw Failure();
                accept = onObject;
                terminal = onTerminal;
                callbacksArmed = true;
            }
            // A normal return, throw or client stop does not detach handlers
            // or invent a terminal. Unknown keeps its possible terminal path.
            dispatch(sdkObserver, request);
        }

        private bool EnterHandler(bool isObject, out bool armed)
        {
            lock (gate)
            {
                armed = callbacksArmed;
                if (closing) return false;
                activeHandlers++;
                if (!armed)
                {
                    preparationFault = true;
                    prepared = false;
                    return true;
                }
                if (isObject)
                {
                    activeObjects++;
                    // Admission and completion phase are one decision. A new
                    // raw handoff cannot hide behind an earlier count check.
                    if (completionObserved) failed = true;
                }
                else
                {
                    completionObserved = true;
                    if (activeObjects != 0) failed = true;
                }
                return true;
            }
        }

        private void LeaveHandler(bool isObject, bool armed)
        {
            lock (gate)
            {
                activeHandlers--;
                if (isObject && armed) activeObjects--;
            }
            TryFinalize();
        }

        private void OnObject(object sender, ObjectReadyEventArgs args)
        {
            bool armed;
            bool admitted = EnterHandler(true, out armed);
            try
            {
                // Count entry before the SDK getter/handoff, not just when
                // generic Accept finally sees the object.
                ManagementBaseObject value = args == null ? null : args.NewObject;
                if (value != null && protectedInputs != null && protectedInputs.Contains(value))
                {
                    // Input ownership lasts through the outer close join. Do
                    // not read or dispose an input reported as a result, even
                    // by a queued callback after that input was released.
                    if (admitted && armed)
                    {
                        lock (gate) failed = true;
                        accept(null);
                    }
                    return;
                }
                OwnedWmiResult owned = value == null ? null : objects.GetValue(value,
                    raw => new OwnedWmiResult(raw, protectedInputs));
                if (armed) accept(owned);
                else owned?.Dispose(); // Pre-invocation events are never replayed.
            }
            catch
            {
                lock (gate)
                {
                    if (armed) failed = true;
                    else cleanupFailed = true;
                }
                if (armed) { try { accept(null); } catch { } }
            }
            finally { if (admitted) LeaveHandler(true, armed); }
        }

        private void OnCompleted(object sender, CompletedEventArgs args)
        {
            bool armed;
            bool admitted = EnterHandler(false, out armed);
            try
            {
                if (!armed) return; // Not a terminal for our not-yet-started call.
                ManagementStatus status = args.Status;
                if (status == ManagementStatus.CallCanceled)
                {
                    // This can be internal/client cancellation while the
                    // implementing method still runs. Keep the completion
                    // phase failure, but do not settle capture or release the
                    // selected output/inputs/lease without an applicable final.
                    lock (gate) failed = true;
                    return;
                }
                // StatusObject and Context stay outside our ownership. Do not
                // read, retain, report or treat them as ObjectReady output.
                terminal((int)status);
            }
            catch { lock (gate) failed = true; }
            finally { if (admitted) LeaveHandler(false, armed); }
        }

        private bool Capture(byte[] detached, bool failure)
        {
            lock (gate)
            {
                if (captureSeen) return false;
                captureSeen = true;
                closing = true;
                failed |= failure;
                bytes = failure ? null : detached;
            }
            TryFinalize();
            return true;
        }

        private void TryFinalize()
        {
            lock (gate)
            {
                if (activeHandlers != 0 || finalizationStarted) return;
                if (!captureSeen && !(unusedClosing && registrationDone)) return;
                finalizationStarted = true;
            }
            // The entered handlers have finished relevant access. Unsubscribe
            // attempts also finish before the real capture report. A queued
            // delegate is not retracted and is independent/local by contract.
            Detach();
            if (!captureSeen)
            {
                lock (gate) closed.TrySetResult(cleanupFailed ? WsabiWmiWindowsCleanupStatus.Failed : WsabiWmiWindowsCleanupStatus.Complete);
                return;
            }
            byte[] detached;
            bool failure;
            lock (gate)
            {
                failure = failed;
                detached = failure ? null : bytes;
                bytes = null;
            }
            try
            {
                if (failure) output.FailCapture();
                else output.SettleCapture(detached);
            }
            catch { } // No callback, path or raw SDK exception leaves here.
            lock (gate) closed.TrySetResult(cleanupFailed ? WsabiWmiWindowsCleanupStatus.Failed : WsabiWmiWindowsCleanupStatus.Complete);
        }

        private void Detach()
        {
            bool removeObject;
            bool removeCompleted;
            lock (gate)
            {
                removeObject = objectSubscribed;
                removeCompleted = completedSubscribed;
                objectSubscribed = completedSubscribed = false;
            }
            if (removeObject)
            {
                try { sdkObserver.ObjectReady -= OnObject; }
                catch { lock (gate) { failed = cleanupFailed = true; } }
            }
            if (removeCompleted)
            {
                try { sdkObserver.Completed -= OnCompleted; }
                catch { lock (gate) { failed = cleanupFailed = true; } }
            }
        }

        private static InvalidOperationException Failure()
            => new InvalidOperationException("The supplied WMI event binding did not produce a usable result.");

        private sealed class ObserverOwner
        {
            internal int Claimed;
        }

        private sealed class CaptureObserver : IWsabiWmiInvocationObserver
        {
            private readonly WsabiWmiWindowsCallbackSource owner;
            internal CaptureObserver(WsabiWmiWindowsCallbackSource owner) { this.owner = owner; }
            public bool IsStopRequested => owner.output.IsStopRequested;
            public bool ReportTerminal(int status) => owner.output.ReportTerminal(status);
            public bool SettleCapture(byte[] bytes) => owner.Capture(bytes, false);
            public bool FailCapture() => owner.Capture(null, true);
        }
    }
}
