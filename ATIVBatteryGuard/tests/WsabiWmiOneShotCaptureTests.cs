using System;
using System.Collections.Generic;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.WmiOneShotQuery;

internal static partial class Program
{
    private static void RegisterWsabiWmiOneShotCaptureTests()
    {
        Add("one-shot callback capture suppresses output on failed completion and cancellation", () =>
        {
            foreach (int status in new[] { 1, 2, -1, int.MinValue, unchecked((int)0x80041003) })
            {
                var capture = new OneShotResultCapture<CaptureTestResult>();
                var value = new CaptureTestResult();
                capture.Accept(value);
                int reads = 0;
                WsabiWmiMethodSnapshot snapshot;
                Check(capture.TryComplete(status, item => { reads++; throw new Exception("private getter"); },
                    CancellationToken.None, out snapshot), "completion was not accepted");
                Equal(status, snapshot.ApiResult);
                Check(snapshot.Output == null, "failed completion retained output");
                Equal(0, reads); Equal(1, value.DisposeCalls);
                CaptureTestAssertNoSource(capture);
            }
            using (var caller = new CancellationTokenSource())
            {
                var capture = new OneShotResultCapture<CaptureTestResult>();
                var value = new CaptureTestResult();
                capture.Accept(value);
                caller.Cancel();
                int reads = 0;
                WsabiWmiMethodSnapshot snapshot = null;
                BatteryThrows<OperationCanceledException>(() => capture.TryComplete(0,
                    item => { reads++; return new object(); }, caller.Token, out snapshot));
                Equal(0, reads); Equal(1, value.DisposeCalls);
                Check(snapshot == null, "cancelled completion retained a snapshot");
                Check(!capture.TryComplete(0, item => new object(), CancellationToken.None, out snapshot),
                    "cancelled capture reopened");
                CaptureTestAssertNoSource(capture);
            }
            using (var caller = new CancellationTokenSource())
            {
                var capture = new OneShotResultCapture<CaptureTestResult>();
                var value = new CaptureTestResult();
                capture.Accept(value);
                WsabiWmiMethodSnapshot snapshot = null;
                BatteryThrows<OperationCanceledException>(() => capture.TryComplete(0, item =>
                {
                    caller.Cancel();
                    return new Dictionary<string, object>();
                }, caller.Token, out snapshot));
                Check(snapshot == null, "cancellation during output capture published a snapshot");
                Equal(1, value.DisposeCalls);
                CaptureTestAssertNoSource(capture);
            }
        });
        Add("one-shot callback capture reads exactly one successful object and cleans it before returning", () =>
        {
            var capture = new OneShotResultCapture<CaptureTestResult>();
            var source = new CaptureTestResult();
            var detached = new Dictionary<string, object> { { "outData", new object() } };
            capture.Accept(source);
            int reads = 0;
            WsabiWmiMethodSnapshot snapshot;
            Check(capture.TryComplete(0, item =>
            {
                Check(ReferenceEquals(source, item), "wrong callback object read");
                Equal(0, item.DisposeCalls);
                reads++;
                return detached;
            }, CancellationToken.None, out snapshot), "successful capture rejected");
            Equal(1, reads); Equal(1, source.DisposeCalls);
            Equal(0, snapshot.ApiResult);
            Check(ReferenceEquals(detached, snapshot.Output) && !ReferenceEquals(source, snapshot.Output),
                "capture substituted its raw callback object for detached output");
            Check(!snapshot.CanInvokeMethods && !snapshot.CanReadHardware && !snapshot.CanWriteHardware,
                "completion became hardware authorization");
            CaptureTestAssertNoSource(capture);
        });
        Add("one-shot callback capture distinguishes empty null duplicate and invalid callback sets without reading", () =>
        {
            for (int variant = 0; variant < 5; variant++)
            {
                var capture = new OneShotResultCapture<CaptureTestResult>();
                var first = new CaptureTestResult();
                var second = new CaptureTestResult();
                if (variant == 1) capture.Accept(null);
                if (variant == 2) { capture.Accept(first); capture.Accept(second); }
                if (variant == 3) { capture.Accept(first); capture.Accept(first); }
                if (variant == 4) { capture.Accept(first); capture.Invalidate(); }
                int reads = 0;
                WsabiWmiMethodSnapshot snapshot;
                Check(capture.TryComplete(0, item => { reads++; return new object(); },
                    CancellationToken.None, out snapshot), "first completion rejected");
                Equal(0, reads);
                if (variant <= 1) Check(snapshot.Output == null, "empty capture was not missing output");
                else Check(snapshot.Output != null && !(snapshot.Output is IReadOnlyDictionary<string, object>),
                    "invalid capture became a usable field view");
                Equal(variant >= 2 ? 1 : 0, first.DisposeCalls);
                Equal(variant == 2 ? 1 : 0, second.DisposeCalls);
                CaptureTestAssertNoSource(capture);
            }
        });
        Add("one-shot callback capture cannot be revived by late objects or repeated completion", () =>
        {
            var capture = new OneShotResultCapture<CaptureTestResult>();
            WsabiWmiMethodSnapshot snapshot;
            Check(capture.TryComplete(0, item => { throw new Exception("must not read"); },
                CancellationToken.None, out snapshot), "empty completion rejected");
            Check(snapshot.Output == null, "empty completion retained output");
            var late = new CaptureTestResult();
            capture.Accept(late);
            capture.Invalidate();
            Equal(1, late.DisposeCalls);
            snapshot = new WsabiWmiMethodSnapshot(0, new object());
            Check(!capture.TryComplete(0, item => { throw new Exception("must not read"); },
                CancellationToken.None, out snapshot) && snapshot == null, "late callback reopened completion");
            capture.Dispose();
            CaptureTestAssertNoSource(capture);
        });
        AddAsync("one-shot callback capture keeps an in-flight object alive across late callbacks and disposal", async () =>
        {
            var capture = new OneShotResultCapture<CaptureTestResult>();
            var source = new CaptureTestResult();
            var late = new CaptureTestResult();
            using (var entered = new ManualResetEventSlim(false))
            using (var release = new ManualResetEventSlim(false))
            {
                capture.Accept(source);
                Task<WsabiWmiMethodSnapshot> pending = Task.Run(() =>
                {
                    WsabiWmiMethodSnapshot result;
                    Check(capture.TryComplete(0, item =>
                    {
                        entered.Set();
                        Check(release.Wait(TimeSpan.FromSeconds(3)), "reader gate was not released");
                        Equal(0, item.DisposeCalls);
                        return new Dictionary<string, object>();
                    }, CancellationToken.None, out result), "in-flight completion rejected");
                    return result;
                });
                try
                {
                    Check(entered.Wait(TimeSpan.FromSeconds(3)), "reader did not start");
                    capture.Accept(source);
                    capture.Accept(late);
                    capture.Invalidate();
                    capture.Dispose();
                    Equal(0, source.DisposeCalls);
                    Equal(1, late.DisposeCalls);
                }
                finally { release.Set(); }
                Check(ReferenceEquals(pending, await Task.WhenAny(pending, Task.Delay(TimeSpan.FromSeconds(3)))),
                    "completion did not finish");
                var snapshot = await pending;
                Check(snapshot.Output is IReadOnlyDictionary<string, object>, "closed late callbacks corrupted the chosen result");
                Equal(1, source.DisposeCalls);
                CaptureTestAssertNoSource(capture);
            }
        });
        Add("one-shot callback capture cleans reader failures and tolerates reentrant throwing disposal", () =>
        {
            var capture = new OneShotResultCapture<CaptureTestResult>();
            var source = new CaptureTestResult();
            capture.Accept(source);
            WsabiWmiMethodSnapshot snapshot = null;
            BatteryThrows<InvalidOperationException>(() => capture.TryComplete(0,
                item => { throw new InvalidOperationException("private reader detail"); },
                CancellationToken.None, out snapshot));
            Check(snapshot == null, "reader failure retained a snapshot");
            Equal(1, source.DisposeCalls);
            Check(!capture.TryComplete(0, item => new object(), CancellationToken.None, out snapshot),
                "reader failure reopened capture");
            CaptureTestAssertNoSource(capture);

            var reentrant = new OneShotResultCapture<CaptureTestResult>();
            var value = new CaptureTestResult();
            value.OnDispose = () =>
            {
                reentrant.Accept(value);
                reentrant.Dispose();
                throw new InvalidOperationException("private disposal detail");
            };
            reentrant.Accept(value);
            Check(reentrant.TryComplete(0, item => new Dictionary<string, object>(),
                CancellationToken.None, out snapshot), "disposal exception replaced a complete result");
            Equal(1, value.DisposeCalls);
            Check(snapshot.Output is IReadOnlyDictionary<string, object>, "disposal failure destroyed detached output");
            CaptureTestAssertNoSource(reentrant);

            var invalidating = new OneShotResultCapture<CaptureTestResult>();
            var invalidated = new CaptureTestResult();
            invalidated.OnDispose = () => invalidating.Accept(invalidated);
            invalidating.Accept(invalidated);
            invalidating.Invalidate();
            Equal(1, invalidated.DisposeCalls);
            Check(invalidating.TryComplete(0, item => { throw new Exception("must not read"); },
                CancellationToken.None, out snapshot) && snapshot.Output != null,
                "reentrant invalidation restored a valid callback set");
            CaptureTestAssertNoSource(invalidating);
        });
        Add("one-shot callback capture disposal closes an uncompleted capture and releases only its owned object", () =>
        {
            var capture = new OneShotResultCapture<CaptureTestResult>();
            var source = new CaptureTestResult { OnDispose = () => { throw new Exception("private cleanup detail"); } };
            capture.Accept(source);
            capture.Dispose();
            capture.Dispose();
            Equal(1, source.DisposeCalls);
            WsabiWmiMethodSnapshot snapshot;
            Check(!capture.TryComplete(0, item => { throw new Exception("must not read"); },
                CancellationToken.None, out snapshot) && snapshot == null, "disposed capture completed");
            CaptureTestAssertNoSource(capture);
            var late = new CaptureTestResult();
            capture.Accept(late);
            Equal(1, late.DisposeCalls);
        });
    }

    private static void CaptureTestAssertNoSource(OneShotResultCapture<CaptureTestResult> capture)
    {
        foreach (var field in capture.GetType().GetFields(BindingFlags.Instance | BindingFlags.NonPublic))
        {
            if (field.FieldType == typeof(CaptureTestResult))
                Check(field.GetValue(capture) == null, "closed collector retained a provider object");
            var activeDisposal = field.GetValue(capture) as ICollection<CaptureTestResult>;
            if (activeDisposal != null) Equal(0, activeDisposal.Count);
        }
    }

    private sealed class CaptureTestResult : IDisposable
    {
        private int disposeCalls;
        internal Action OnDispose;
        internal int DisposeCalls => Volatile.Read(ref disposeCalls);
        public override bool Equals(object value) { throw new Exception("provider equality must not be called"); }
        public override int GetHashCode() { throw new Exception("provider hash must not be called"); }
        public void Dispose()
        {
            Interlocked.Increment(ref disposeCalls);
            if (OnDispose != null) OnDispose();
        }
    }
}
