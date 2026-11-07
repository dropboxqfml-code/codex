using System;
using System.Management;
using System.Runtime.CompilerServices;
using System.Threading;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.WmiInterop
{
    // A supplied observer must be dedicated to this attempt: no other user of
    // its ObjectReady objects, Cancel, reuse or independent dispatch. There is
    // no InvokeMethod, target selection, default dispatch or hardware policy.
    // Post-cutoff queued handlers may only do independent local cleanup.
    public sealed class WsabiWmiWindowsCallbackSource : IWsabiWmiInvocationSource
    {
        private static readonly ConditionalWeakTable<ManagementOperationObserver, ObserverOwner> Observers =
            new ConditionalWeakTable<ManagementOperationObserver, ObserverOwner>();
        private readonly object gate = new object();
        private readonly ManagementOperationObserver sdkObserver;
        private readonly Action<ManagementOperationObserver, WsabiWmiMethodRequest> dispatch;
        private readonly ConditionalWeakTable<ManagementBaseObject, OwnedWmiResult> objects =
            new ConditionalWeakTable<ManagementBaseObject, OwnedWmiResult>();
        private readonly WsabiWmiCallbackInvocationSource<OwnedWmiResult> source;
        private Action<OwnedWmiResult> accept;
        private Action<int> terminal;
        private IWsabiWmiInvocationObserver output;
        private int entered;
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

        public WsabiWmiWindowsCallbackSource(ManagementOperationObserver dedicatedObserver,
            Action<ManagementOperationObserver, WsabiWmiMethodRequest> dispatch)
        {
            if (dedicatedObserver == null) throw new ArgumentNullException(nameof(dedicatedObserver));
            if (dispatch == null) throw new ArgumentNullException(nameof(dispatch));
            ObserverOwner owner = Observers.GetValue(dedicatedObserver, _ => new ObserverOwner());
            if (Interlocked.CompareExchange(ref owner.Claimed, 1, 0) != 0)
                throw new ArgumentException("The supplied WMI observer already belongs to a single-use binding.", nameof(dedicatedObserver));
            sdkObserver = dedicatedObserver;
            this.dispatch = dispatch;
            source = new WsabiWmiCallbackInvocationSource<OwnedWmiResult>(Dispatch, value => value.Read());
        }

        public void Invoke(WsabiWmiMethodRequest request, IWsabiWmiInvocationObserver observer)
        {
            if (request == null) throw new ArgumentNullException(nameof(request));
            if (observer == null) throw new ArgumentNullException(nameof(observer));
            if (Interlocked.CompareExchange(ref entered, 1, 0) != 0) throw Failure();
            output = observer;
            source.Invoke(request, new CaptureObserver(this));
        }

        private void Dispatch(WsabiWmiMethodRequest request, Action<OwnedWmiResult> onObject, Action<int> onTerminal)
        {
            accept = onObject;
            terminal = onTerminal;
            try
            {
                sdkObserver.ObjectReady += OnObject;
                lock (gate) objectSubscribed = true;
                sdkObserver.Completed += OnCompleted;
                lock (gate) completedSubscribed = true;
            }
            catch
            {
                Detach();
                throw Failure();
            }
            // A normal return, throw or client stop does not detach handlers
            // or invent a terminal. Unknown keeps its possible terminal path.
            dispatch(sdkObserver, request);
        }

        private bool EnterHandler(bool isObject)
        {
            lock (gate)
            {
                if (closing) return false;
                activeHandlers++;
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

        private void LeaveHandler(bool isObject)
        {
            lock (gate)
            {
                activeHandlers--;
                if (isObject) activeObjects--;
            }
            TryFinalize();
        }

        private void OnObject(object sender, ObjectReadyEventArgs args)
        {
            bool admitted = EnterHandler(true);
            try
            {
                // Count entry before the SDK getter/handoff, not just when
                // generic Accept finally sees the object.
                ManagementBaseObject value = args == null ? null : args.NewObject;
                accept(value == null ? null : objects.GetValue(value, raw => new OwnedWmiResult(raw)));
            }
            catch
            {
                lock (gate) failed = true;
                try { accept(null); } catch { }
            }
            finally { if (admitted) LeaveHandler(true); }
        }

        private void OnCompleted(object sender, CompletedEventArgs args)
        {
            bool admitted = EnterHandler(false);
            try
            {
                int status = (int)args.Status;
                // StatusObject and Context stay outside our ownership. Do not
                // read, retain, report or treat them as ObjectReady output.
                terminal(status);
            }
            catch { lock (gate) failed = true; }
            finally { if (admitted) LeaveHandler(false); }
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
                if (!captureSeen || activeHandlers != 0 || finalizationStarted) return;
                finalizationStarted = true;
            }
            // The entered handlers have finished relevant access. Unsubscribe
            // attempts also finish before the real capture report. A queued
            // delegate is not retracted and is independent/local by contract.
            Detach();
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
                catch { lock (gate) failed = true; }
            }
            if (removeCompleted)
            {
                try { sdkObserver.Completed -= OnCompleted; }
                catch { lock (gate) failed = true; }
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
