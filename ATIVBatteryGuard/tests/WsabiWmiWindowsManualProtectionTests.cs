using System;
using System.Collections.Generic;
using System.Linq;
using System.Management;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.WmiInterop;

internal static partial class Program
{
    private static void RegisterWsabiWmiWindowsManualProtectionTests()
    {
        Add("manual live SDK entry exposes only the typed attempt and target and rejects all invalid targets before allocation", () =>
        {
            var methods = typeof(WsabiWmiWindowsManualProtection).GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly);
            Equal(1, methods.Length); Equal("Prepare", methods[0].Name); Equal(2, methods[0].GetParameters().Length);
            var target = new ManagementObject();
            var attempt = ManualSdkAttemptCreate(ManualProtectionOperation.ReadState, target);
            int allocated = 0;
            for (int variant = 0; variant < 5; variant++)
            {
                var supplied = variant == 0 ? new ManagementObject() : target;
                target.Scope.Path.NamespacePath = variant == 1 ? @"root\cimv2" : @"root\WMI";
                target.Path.ClassName = variant == 2 ? "OtherMethod" : "WmiAcpiMethod";
                target.Scope.IsConnected = variant != 3;
                target.Scope.Path.Server = variant == 4 ? "remote-host" : ".";
                BatteryThrows<ArgumentException>(() => WsabiWmiWindowsManualProtection.PrepareForTests(attempt, supplied,
                    new CooperativeTestGate(), () => { allocated++; return null; }, () => null, () => null));
            }
            Equal(0, allocated); Equal(0, target.InvokeCalls); Equal(0, target.ConcreteDisposeCalls);
        });

        Add("manual SDK does not admit a peer attempt request even when its target operation and frozen bytes are equal", () =>
        {
            var target = new ManagementObject(); var attempt = ManualSdkAttemptCreate(ManualProtectionOperation.ReadState, target);
            var peer = ManualSdkAttemptCreate(ManualProtectionOperation.ReadState, target); int allocated = 0;
            var factory = new ManualProtectionSdkLeafFactory(attempt, target,
                () => { allocated++; return null; }, () => { allocated++; return null; }, () => { allocated++; return null; });
            var request = new ManualProtectionLeafRequest(peer, peer.GetRole(0));
            Check(attempt.ValidateRoleRequest(request.Role, request.Request), "test peer did not preserve equal fixed bytes");
            BatteryThrows<InvalidOperationException>(() => factory.PrepareAsync(request,
                new WsabiWmiProtectionStop(() => false, CooperativeCompletion().Task)));
            Equal(0, allocated); Equal(0, factory.SdkEntries); Equal(0, target.InvokeCalls);
        });

        AddAsync("manual SDK state read uses exactly three read-only entries and preserves independently supplied thresholds", async () =>
        {
            var fixture = new ManualSdkFixture(ManualProtectionOperation.ReadState) { PreMode = 0, PreUpper = 92, PreLower = 87 };
            try
            {
                Equal(0, fixture.Pairs.Count); Equal(0, fixture.Observers.Count);
                var outcome = await ManualSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(ManualProtectionStatus.StateRead, outcome.Status);
                Equal((int?)0, outcome.ModeCandidate); Equal((int?)92, outcome.UpperCandidate); Equal((int?)87, outcome.LowerCandidate);
                Equal(3, outcome.ReadCandidates); Equal(3, fixture.Session.SdkEntries); Equal(0, fixture.Session.SetterEntries);
                Equal(3, fixture.Target.InvokeCalls); Equal(3, fixture.Pairs.Count); Equal(3, fixture.Observers.Count);
                Check(fixture.Requests.All(raw => raw[6] == 0x80), "state inspection admitted a semantic setter");
                fixture.AssertReleased(); Equal(1, fixture.Gate.Calls);
                Equal(fixture.Gate.AcquireThread, fixture.Gate.LastLease.DisposeThread);
                Equal(3, fixture.Session.GetStageDiagnostics().Count);
                Check(!fixture.Session.IsCompletionUnknown, "normal closed read was quarantined");
            }
            finally { await fixture.FinishAsync(); }
        });

        AddAsync("manual SDK rejects a later fixed role before allocation or dispatch for each closed operation", async () =>
        {
            foreach (var operation in new[] { ManualProtectionOperation.ReadState, ManualProtectionOperation.Enable80, ManualProtectionOperation.DisableProtection })
            {
                var target = new ManagementObject(); var attempt = ManualSdkAttemptCreate(operation, target); int allocated = 0;
                var factory = new ManualProtectionSdkLeafFactory(attempt, target,
                    () => { allocated++; return null; }, () => { allocated++; return null; }, () => { allocated++; return null; });
                var stop = new WsabiWmiProtectionStop(() => false, CooperativeCompletion().Task);
                var leaf = await factory.PrepareAsync(new ManualProtectionLeafRequest(attempt, attempt.GetRole(1)), stop);
                Check(!leaf.IsReady && leaf.Source == null, "a skipped manual role prepared a source");
                Equal(0, allocated); Equal(0, target.InvokeCalls); Equal(0, factory.SdkEntries); Equal(0, factory.SetterEntries);
                Equal(WsabiWmiProtectionSdkPreparationStatus.InputRejected, factory.LastPreparationStatus);
                Equal(WsabiWmiProtectionCleanupStatus.Complete, await leaf.CloseOutputAsync());
                Equal(WsabiWmiProtectionCleanupStatus.Complete, await leaf.CloseInputsAsync());
            }
        });

        AddAsync("manual SDK enable uses the fixed seven-role frame sequence and one input-one setting", async () =>
        {
            var fixture = new ManualSdkFixture(ManualProtectionOperation.Enable80) { PreUpper = 33, PreLower = 12 };
            try
            {
                var outcome = await ManualSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(ManualProtectionStatus.ChangedCandidate, outcome.Status);
                Equal(7, outcome.StartedStages); Equal(7, fixture.Session.SdkEntries); Equal(1, fixture.Session.SetterEntries);
                Equal(6, outcome.ReadCandidates); Equal((int?)0, outcome.PreModeCandidate);
                Equal((int?)1, outcome.ModeCandidate); Equal((int?)80, outcome.UpperCandidate); Equal((int?)75, outcome.LowerCandidate);
                Equal(7, fixture.Requests.Count);
                byte[] second = { 0x4f, 0x50, 0x51, 0, 0x4f, 0x50, 0x51 };
                for (int i = 0; i < fixture.Requests.Count; i++)
                    ManualSdkAssertFrame(fixture.Requests[i], i == 3, i == 3 ? (byte)1 : (byte)0xf0, second[i]);
                Check(outcome.SetterReceiptAccepted, "independent post reads did not follow the input-one receipt");
                fixture.AssertReleased(); Equal(1, fixture.Gate.Calls);
                Equal(WsabiWmiProtectionSdkPreparationStatus.Ready, fixture.Session.LastPreparationStatus);
                var repeated = await ManualSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(ManualProtectionStatus.Busy, repeated.Status); Equal(7, fixture.Target.InvokeCalls);
            }
            finally { await fixture.FinishAsync(); }
        });

        AddAsync("manual SDK disable uses only pre mode input-zero setting and independent post mode", async () =>
        {
            var fixture = new ManualSdkFixture(ManualProtectionOperation.DisableProtection);
            try
            {
                var outcome = await ManualSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(ManualProtectionStatus.ChangedCandidate, outcome.Status);
                Equal(3, outcome.StartedStages); Equal(3, fixture.Session.SdkEntries); Equal(1, fixture.Session.SetterEntries);
                Equal(2, outcome.ReadCandidates); Equal((int?)1, outcome.PreModeCandidate); Equal((int?)0, outcome.ModeCandidate);
                Equal((int?)null, outcome.UpperCandidate); Equal((int?)null, outcome.LowerCandidate);
                for (int i = 0; i < fixture.Requests.Count; i++)
                    ManualSdkAssertFrame(fixture.Requests[i], i == 1, i == 1 ? (byte)0 : (byte)0xf0, i == 1 ? (byte)0 : (byte)0x4f);
                fixture.AssertReleased(); Equal(1, fixture.Gate.Calls);
            }
            finally { await fixture.FinishAsync(); }
        });

        AddAsync("manual SDK already requested modes stop after one fresh read without setting or threshold inference", async () =>
        {
            foreach (var operation in new[] { ManualProtectionOperation.Enable80, ManualProtectionOperation.DisableProtection })
            {
                var fixture = new ManualSdkFixture(operation) { PreMode = operation == ManualProtectionOperation.Enable80 ? (byte)1 : (byte)0 };
                try
                {
                    var outcome = await ManualSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                    Equal(ManualProtectionStatus.AlreadyDesiredCandidate, outcome.Status);
                    Equal(1, outcome.StartedStages); Equal(1, fixture.Session.SdkEntries); Equal(0, fixture.Session.SetterEntries);
                    Equal((int?)fixture.PreMode, outcome.ModeCandidate); Equal((int?)null, outcome.UpperCandidate); Equal((int?)null, outcome.LowerCandidate);
                    Equal(1, fixture.Pairs.Count); Equal(1, fixture.Observers.Count); fixture.AssertReleased();
                }
                finally { await fixture.FinishAsync(); }
            }
        });

        AddAsync("manual SDK rejects a setter receipt for the opposite mode before any post read and never repairs", async () =>
        {
            foreach (var operation in new[] { ManualProtectionOperation.Enable80, ManualProtectionOperation.DisableProtection })
            {
                var fixture = new ManualSdkFixture(operation) { SetterEchoOverride = operation == ManualProtectionOperation.Enable80 ? (byte)0 : (byte)1 };
                try
                {
                    var outcome = await ManualSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                    int expected = operation == ManualProtectionOperation.Enable80 ? 4 : 2;
                    Equal(ManualProtectionStatus.Rejected, outcome.Status);
                    Equal(expected, fixture.Session.SdkEntries); Equal(1, fixture.Session.SetterEntries);
                    Equal(expected, fixture.Target.InvokeCalls); Equal(expected, fixture.Pairs.Count);
                    Equal((int?)null, outcome.ModeCandidate); Equal((int?)null, outcome.UpperCandidate); Equal((int?)null, outcome.LowerCandidate);
                    fixture.AssertReleased();
                }
                finally { await fixture.FinishAsync(); }
            }
        });

        AddAsync("manual SDK mismatched post reads retain no applied-state claim and perform no second setting", async () =>
        {
            foreach (var operation in new[] { ManualProtectionOperation.Enable80, ManualProtectionOperation.DisableProtection })
            {
                var fixture = new ManualSdkFixture(operation) { PostMode = operation == ManualProtectionOperation.Enable80 ? (byte)0 : (byte)1 };
                try
                {
                    var outcome = await ManualSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                    Equal(ManualProtectionStatus.Rejected, outcome.Status);
                    Equal(operation == ManualProtectionOperation.Enable80 ? 5 : 3, fixture.Session.SdkEntries);
                    Equal(1, fixture.Session.SetterEntries); Equal((int?)null, outcome.ModeCandidate);
                    fixture.AssertReleased();
                }
                finally { await fixture.FinishAsync(); }
            }
        });

        AddAsync("manual SDK failed post threshold does not use a matching mode to claim the full enabled configuration", async () =>
        {
            var fixture = new ManualSdkFixture(ManualProtectionOperation.Enable80) { PostUpper = 81 };
            try
            {
                var outcome = await ManualSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(ManualProtectionStatus.Rejected, outcome.Status); Equal(6, fixture.Session.SdkEntries); Equal(1, fixture.Session.SetterEntries);
                Equal((int?)null, outcome.ModeCandidate); Equal((int?)null, outcome.UpperCandidate); Equal((int?)null, outcome.LowerCandidate);
                fixture.AssertReleased();
            }
            finally { await fixture.FinishAsync(); }
        });

        AddAsync("manual SDK partial allocation failure closes claimed parameters without constructing a buffer or observer", async () =>
        {
            var fixture = new ManualSdkFixture(ManualProtectionOperation.ReadState) { BufferFailure = true };
            try
            {
                var outcome = await ManualSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(ManualProtectionStatus.Rejected, outcome.Status); Equal(0, fixture.Session.SdkEntries);
                Equal(0, fixture.Observers.Count); Equal(1, fixture.Pairs[0].Parameters.ConcreteDisposeCalls);
                Equal(0, fixture.Pairs[0].Buffer.ConcreteDisposeCalls);
                Equal(WsabiWmiProtectionSdkPreparationStatus.AllocationFailed, fixture.Session.LastPreparationStatus);
            }
            finally { await fixture.FinishAsync(); }
        });

        AddAsync("manual SDK common registry rejects an input wrapper owned by a historical read without disposing or rearming it", async () =>
        {
            var old = InputPreparationPair.Create();
            Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                WsabiWmiWindowsInputPreparation.Populate(InputPreparationPlan(), InputPreparationRequest(), old.Parameters, old.Buffer));
            var fixture = new ManualSdkFixture(ManualProtectionOperation.ReadState) { ParametersOverride = old.Parameters };
            try
            {
                var outcome = await ManualSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(ManualProtectionStatus.Rejected, outcome.Status); Equal(0, fixture.Session.SdkEntries);
                Equal(0, fixture.BufferAllocations); Equal(0, fixture.Observers.Count);
                Equal(0, old.Parameters.ConcreteDisposeCalls); Equal(0, old.Buffer.ConcreteDisposeCalls);
                Equal(WsabiWmiProtectionSdkPreparationStatus.InputRejected, fixture.Session.LastPreparationStatus);
            }
            finally { await fixture.FinishAsync(); }
        });

        AddAsync("manual SDK wrong shape and partial mutation retire both claimed inputs before any observer or dispatch", async () =>
        {
            for (int variant = 0; variant < 3; variant++)
            {
                int failure = variant;
                var fixture = new ManualSdkFixture(ManualProtectionOperation.ReadState) { OnPair = pair =>
                {
                    if (failure == 0) pair.Input.Type = CimType.String;
                    if (failure == 1) pair.Buffer.OnGetClassPath = () => throw new InvalidOperationException("Unreported metadata detail.");
                    if (failure == 2) pair.Bytes.AfterSetValue = value => throw new InvalidOperationException("Unreported mutation detail.");
                }};
                try
                {
                    var outcome = await ManualSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                    Equal(ManualProtectionStatus.Rejected, outcome.Status); Equal(0, fixture.Target.InvokeCalls); Equal(0, fixture.Observers.Count);
                    Equal(1, fixture.Pairs[0].Parameters.ConcreteDisposeCalls); Equal(1, fixture.Pairs[0].Buffer.ConcreteDisposeCalls);
                    Equal(WsabiWmiProtectionSdkPreparationStatus.InputRejected, fixture.Session.LastPreparationStatus);
                }
                finally { await fixture.FinishAsync(); }
            }
        });

        AddAsync("manual SDK refuses an observer already owned by another source without removing its handlers", async () =>
        {
            var observer = new ManagementOperationObserver();
            var prior = new WsabiWmiWindowsCallbackSource(observer, (o, r) => { });
            Equal(WsabiWmiWindowsPreparationStatus.Ready, await prior.PrepareAsync(CancellationToken.None));
            var fixture = new ManualSdkFixture(ManualProtectionOperation.ReadState) { ObserverOverride = observer };
            try
            {
                var outcome = await ManualSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(ManualProtectionStatus.Rejected, outcome.Status); Equal(0, fixture.Target.InvokeCalls);
                Equal(1, observer.ObjectReadySubscriberCount); Equal(1, observer.CompletedSubscriberCount);
                Equal(WsabiWmiProtectionSdkPreparationStatus.ObserverUnavailable, fixture.Session.LastPreparationStatus);
                Equal(1, fixture.Pairs[0].Parameters.ConcreteDisposeCalls); Equal(1, fixture.Pairs[0].Buffer.ConcreteDisposeCalls);
            }
            finally { await prior.CloseUnusedAsync(); await fixture.FinishAsync(); }
        });

        AddAsync("manual SDK stops during blocked lazy preparation without releasing ownership before allocation returns", async () =>
        {
            using (var release = new ManualResetEventSlim()) using (var caller = new CancellationTokenSource())
            {
                var entered = CooperativeCompletion();
                var fixture = new ManualSdkFixture(ManualProtectionOperation.Enable80) { OnPair = pair => { entered.TrySetResult(true); release.Wait(); } };
                var published = new TaskCompletionSource<ManualProtectionOutcome>(TaskCreationOptions.RunContinuationsAsynchronously);
                var run = fixture.Session.RunAndCloseAsync(value => published.TrySetResult(value), caller.Token);
                try
                {
                    await CooperativeAwait(entered.Task); caller.Cancel(); await CooperativeAwait(published.Task);
                    Equal(ManualProtectionStatus.Unknown, (await published.Task).Status);
                    Check(!run.IsCompleted && fixture.Gate.LastLease.IsHeld, "manual cancellation released active allocation");
                    Equal(0, fixture.Session.SdkEntries); Equal(0, fixture.Pairs[0].Parameters.ConcreteDisposeCalls);
                    release.Set(); await ManualSdkAwait(run);
                    Equal(1, fixture.Pairs[0].Parameters.ConcreteDisposeCalls); Equal(0, fixture.BufferAllocations);
                    Equal(0, fixture.Observers.Count); Equal(WsabiWmiProtectionSdkPreparationStatus.Stopped, fixture.Session.LastPreparationStatus);
                }
                finally { release.Set(); await fixture.FinishAsync(); }
            }
        });

        AddAsync("manual SDK unsubscribe failure holds both inputs and the common owner while every later role remains unstarted", async () =>
        {
            var fixture = new ManualSdkFixture(ManualProtectionOperation.Enable80) { ObserverFailure = true };
            var published = new TaskCompletionSource<ManualProtectionOutcome>(TaskCreationOptions.RunContinuationsAsynchronously);
            var run = fixture.Session.RunAndCloseAsync(value => published.TrySetResult(value));
            try
            {
                await CooperativeAwait(published.Task); Equal(ManualProtectionStatus.Unknown, (await published.Task).Status);
                Equal(1, fixture.Target.InvokeCalls); Equal(1, fixture.Pairs.Count);
                Check(!run.IsCompleted && fixture.Gate.LastLease.IsHeld, "failed output cleanup became completion");
                Check(fixture.Session.IsCompletionUnknown, "uncertain output did not quarantine the manual session");
                Equal(0, fixture.Pairs[0].Parameters.ConcreteDisposeCalls); Equal(0, fixture.Pairs[0].Buffer.ConcreteDisposeCalls);
            }
            finally
            {
                fixture.DetachFailedFakeResources(); fixture.Session.ConfirmDetachedForTests();
                await ManualSdkAwait(run); await fixture.FinishAsync();
            }
        });

        AddAsync("manual SDK client cancelled terminal never replaces the later applicable fake terminal or actual resource join", async () =>
        {
            using (var caller = new CancellationTokenSource())
            {
                var entered = CooperativeCompletion(); var fixture = new ManualSdkFixture(ManualProtectionOperation.DisableProtection);
                fixture.OnInvoke = (observer, parameters) => { observer.EmitCompleted(ManagementStatus.CallCanceled); entered.TrySetResult(true); };
                var published = new TaskCompletionSource<ManualProtectionOutcome>(TaskCreationOptions.RunContinuationsAsynchronously);
                var run = fixture.Session.RunAndCloseAsync(value => published.TrySetResult(value), caller.Token);
                try
                {
                    await CooperativeAwait(entered.Task); caller.Cancel(); await CooperativeAwait(published.Task);
                    Equal(ManualProtectionStatus.Unknown, (await published.Task).Status);
                    Check(!run.IsCompleted && fixture.Gate.LastLease.IsHeld, "CallCanceled fabricated actual source termination");
                    Equal(0, fixture.Pairs[0].Parameters.ConcreteDisposeCalls);
                    fixture.Observers[0].EmitCompleted(ManagementStatus.NoError);
                    await ManualSdkAwait(run); fixture.AssertReleased(); Equal(1, fixture.Target.InvokeCalls);
                }
                finally { await fixture.FinishAsync(); }
            }
        });
    }

    private static void ManualSdkAssertFrame(byte[] raw, bool setter, byte first, byte second)
    {
        Equal(21, raw.Length); Equal((byte)0x43, raw[0]); Equal((byte)0x58, raw[1]); Equal((byte)0x7a, raw[2]);
        Equal((byte)0x82, raw[5]); Equal(setter ? (byte)0xe3 : (byte)0x80, raw[6]); Equal(first, raw[7]); Equal(second, raw[8]);
    }

    private static ManualProtectionAttempt ManualSdkAttemptCreate(ManualProtectionOperation operation, object identity)
    {
        ManualProtectionAttempt attempt; ManualProtectionAttemptIssue issue;
        Check(ManualProtectionAttempt.TryCreateWithRandom(operation, SingleReadTarget(identity), BinderCompleteMetadata(1),
            bytes => { for (int i = 0; i < bytes.Length; i++) bytes[i] = (byte)(i + 1); }, out attempt, out issue),
            "manual fixed SDK fixture creation failed");
        Equal(ManualProtectionAttemptIssue.None, issue); return attempt;
    }

    private static async Task<ManualProtectionOutcome> ManualSdkAwait(Task<ManualProtectionOutcome> value)
    { await CooperativeAwait(value); return await value; }

    private sealed class ManualSdkFixture
    {
        internal readonly ManagementObject Target = new ManagementObject();
        internal readonly CooperativeTestGate Gate = new CooperativeTestGate();
        internal readonly List<InputPreparationPair> Pairs = new List<InputPreparationPair>();
        internal readonly List<ManagementOperationObserver> Observers = new List<ManagementOperationObserver>();
        internal readonly List<byte[]> Requests = new List<byte[]>();
        internal readonly WsabiWmiWindowsManualProtectionSession Session;
        internal byte PreMode, PostMode, PreUpper = 80, PreLower = 75, PostUpper = 80, PostLower = 75;
        internal byte? SetterEchoOverride;
        internal bool BufferFailure, ObserverFailure;
        internal int BufferAllocations;
        internal ManagementBaseObject ParametersOverride;
        internal ManagementOperationObserver ObserverOverride;
        internal Action<InputPreparationPair> OnPair;
        internal Action<ManagementOperationObserver, ManagementBaseObject> OnInvoke;
        private InputPreparationPair current;
        private bool settingSeen;
        internal ManualSdkFixture(ManualProtectionOperation operation)
        {
            PreMode = operation == ManualProtectionOperation.Enable80 ? (byte)0 : (byte)1;
            PostMode = operation == ManualProtectionOperation.Enable80 ? (byte)1 : (byte)0;
            var attempt = ManualSdkAttemptCreate(operation, Target);
            Session = WsabiWmiWindowsManualProtection.PrepareForTests(attempt, Target, Gate,
                () =>
                {
                    if (ParametersOverride != null) return ParametersOverride;
                    current = InputPreparationPair.Create(); Pairs.Add(current); OnPair?.Invoke(current); return current.Parameters;
                },
                () => { BufferAllocations++; if (BufferFailure) throw new InvalidOperationException("Unreported allocation detail."); return current.Buffer; },
                () =>
                {
                    var observer = ObserverOverride ?? new ManagementOperationObserver(); Observers.Add(observer);
                    if (ObserverFailure) observer.BeforeRemove = name => throw new InvalidOperationException("Unreported unsubscribe detail.");
                    return observer;
                });
            Target.OnInvoke = (observer, name, parameters, options) =>
            {
                Equal(WsabiWmiContractMetadataPolicy.MethodName, name);
                if (OnInvoke != null) { OnInvoke(observer, parameters); return; }
                var buffer = (ManagementBaseObject)parameters.Properties["inData"].Value;
                var raw = (byte[])((byte[])buffer.Properties["Bytes"].Value).Clone();
                Requests.Add((byte[])raw.Clone());
                bool setter = raw[6] == 0xe3;
                byte candidate;
                if (setter) { settingSeen = true; candidate = SetterEchoOverride ?? raw[7]; }
                else if (raw[8] == 0x4f) candidate = settingSeen ? PostMode : PreMode;
                else if (raw[8] == 0x50) candidate = settingSeen ? PostUpper : PreUpper;
                else if (raw[8] == 0x51) candidate = settingSeen ? PostLower : PreLower;
                else throw new InvalidOperationException("Unexpected fixed test request.");
                raw[4] = 0xaa; raw[5] = 0; raw[6] = 0; raw[7] = candidate;
                ManagementBaseObject embedded;
                observer.EmitObjectReady(WindowsOutputFixture(raw, out embedded)); observer.EmitCompleted(ManagementStatus.NoError);
            };
        }
        internal void AssertReleased()
        {
            foreach (var pair in Pairs)
            { Equal(1, pair.Parameters.ConcreteDisposeCalls); Equal(1, pair.Buffer.ConcreteDisposeCalls); }
            foreach (var observer in Observers)
            { Equal(0, observer.ObjectReadySubscriberCount); Equal(0, observer.CompletedSubscriberCount); }
            Equal(0, Target.ConcreteDisposeCalls);
        }
        internal void DetachFailedFakeResources()
        {
            foreach (var observer in Observers)
            {
                observer.BeforeRemove = null;
                observer.ObjectReady -= observer.ObjectReadySnapshot;
                observer.Completed -= observer.CompletedSnapshot;
            }
            foreach (var pair in Pairs)
            {
                if (pair.Parameters.ConcreteDisposeCalls == 0) pair.Parameters.Dispose();
                if (pair.Buffer.ConcreteDisposeCalls == 0) pair.Buffer.Dispose();
            }
        }
        internal async Task FinishAsync()
        {
            var close = Session.RequestCloseAsync();
            foreach (var observer in Observers)
            {
                observer.BeforeRemove = null;
                observer.EmitCompleted(ManagementStatus.NoError);
            }
            await CooperativeAwait(close);
        }
    }
}
