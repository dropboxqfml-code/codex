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
    private static void RegisterWsabiWmiWindowsProtectionDisableTrialTests()
    {
        Add("disable live entry accepts no arbitrary dispatcher allocator gate or frame and rejects wrong target before allocation", () =>
        {
            var method = typeof(WsabiWmiWindowsProtectionDisableTrial).GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly);
            Equal(1, method.Length); Equal("Prepare", method[0].Name); Equal(2, method[0].GetParameters().Length);
            var target = new ManagementObject(); var attempt = DisableSdkAttemptCreate(target); int allocated = 0;
            foreach (int variant in new[] { 0, 1, 2, 3 })
            {
                var supplied = variant == 0 ? new ManagementObject() : target;
                target.Scope.Path.NamespacePath = variant == 1 ? @"root\cimv2" : @"root\WMI";
                target.Path.ClassName = variant == 2 ? "OtherMethod" : "WmiAcpiMethod";
                target.Scope.IsConnected = variant != 3;
                BatteryThrows<ArgumentException>(() => WsabiWmiWindowsProtectionDisableTrial.PrepareForTests(attempt, supplied,
                    new CooperativeTestGate(), () => { allocated++; return null; }, () => null, () => null));
            }
            Equal(0, allocated); Equal(0, target.InvokeCalls); Equal(0, target.ConcreteDisposeCalls);
        });

        AddAsync("disable SDK full fixed sequence creates only admitted leaves and uses one setter with actual entry counters", async () =>
        {
            var fixture = new DisableSdkFixture();
            Equal(0, fixture.Pairs.Count); Equal(0, fixture.Observers.Count); Equal(0, fixture.Session.SdkEntries);
            try
            {
                var outcome = await DisableSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(WsabiWmiProtectionDisableStatus.StoredReadbackMatchedCandidate, outcome.Status);
                Equal(3, outcome.StartedStages); Equal(3, fixture.Session.SdkEntries); Equal(1, fixture.Session.SetterEntries);
                Equal(3, fixture.Target.InvokeCalls); Equal(3, fixture.Pairs.Count); Equal(3, fixture.Observers.Count);
                Equal(3, fixture.Requests.Count);
                for (int i = 0; i < fixture.Requests.Count; i++)
                {
                    var raw = fixture.Requests[i];
                    Equal(21, raw.Length); Equal((byte)0x43, raw[0]); Equal((byte)0x58, raw[1]);
                    Equal((byte)0x7a, raw[2]); Equal((byte)0x82, raw[5]);
                    Equal(i == 1 ? (byte)0xe3 : (byte)0x80, raw[6]);
                    Equal(i == 1 ? (byte)0 : (byte)0xf0, raw[7]);
                    Equal(i == 1 ? (byte)0 : (byte)0x4f, raw[8]);
                }
                Check(outcome.Snapshot.SetterReceiptAccepted && !outcome.Snapshot.SetterAcknowledged &&
                    outcome.Snapshot.BoundReadCandidateCount == 2 && !outcome.IsChargeLimitConfirmed && !outcome.CanWriteHardware,
                    "SDK receipt/readback enabled normal charge control");
                fixture.AssertReleased(); Equal(1, fixture.Gate.Calls);
                Equal(fixture.Gate.AcquireThread, fixture.Gate.LastLease.DisposeThread);
                Equal(WsabiWmiProtectionSdkPreparationStatus.Ready, fixture.Session.LastPreparationStatus);
                Equal(3, fixture.Session.GetStageDiagnostics().Count);
                var duplicate = await DisableSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(WsabiWmiProtectionDisableStatus.AlreadyUsed, duplicate.Status); Equal(3, fixture.Target.InvokeCalls);
            }
            finally { await fixture.FinishAsync(); }
        });

        AddAsync("disable SDK mode zero prevents every unused SDK allocation and setting entry", async () =>
        {
            var fixture = new DisableSdkFixture { PreMode = 0 };
            try
            {
                var result = await DisableSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(WsabiWmiProtectionDisableStatus.StageRejected, result.Status);
                Equal(1, result.StartedStages); Equal(1, fixture.Session.SdkEntries); Equal(0, fixture.Session.SetterEntries);
                Equal(1, fixture.Pairs.Count); Equal(1, fixture.Observers.Count); fixture.AssertReleased();
            }
            finally { await fixture.FinishAsync(); }
        });

        AddAsync("disable SDK input-one setter echo is rejected before the post read with no automatic repair", async () =>
        {
            var fixture = new DisableSdkFixture { SetterEcho = 1 };
            try
            {
                var result = await DisableSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(WsabiWmiProtectionDisableStatus.StageRejected, result.Status);
                Equal(2, result.StartedStages); Equal(2, fixture.Session.SdkEntries);
                Equal(1, fixture.Session.SetterEntries); Equal(2, fixture.Target.InvokeCalls);
                Equal(2, fixture.Pairs.Count); Equal(2, fixture.Observers.Count);
                Check(!result.Snapshot.SetterReceiptAccepted && !result.IsChargeLimitConfirmed,
                    "an ON-shaped receipt was accepted by the OFF purpose");
                fixture.AssertReleased();
            }
            finally { await fixture.FinishAsync(); }
        });

        AddAsync("disable SDK post mode one remains a mismatch after one setting and never retries or restores", async () =>
        {
            var fixture = new DisableSdkFixture { PostMode = 1 };
            try
            {
                var result = await DisableSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(WsabiWmiProtectionDisableStatus.StageRejected, result.Status);
                Equal(3, result.StartedStages); Equal(3, fixture.Session.SdkEntries);
                Equal(1, fixture.Session.SetterEntries); Equal(3, fixture.Target.InvokeCalls);
                Equal((int?)1, result.Snapshot.ObservedPostModeByte);
                Check(result.Snapshot.SetterReceiptAccepted && !result.IsChargeLimitConfirmed,
                    "a receipt or mismatched post mode became charge success");
                fixture.AssertReleased();
            }
            finally { await fixture.FinishAsync(); }
        });

        AddAsync("disable SDK partial allocation failure releases only its already claimed parameter wrapper without dispatch", async () =>
        {
            var fixture = new DisableSdkFixture { BufferFailure = true };
            try
            {
                var result = await DisableSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(WsabiWmiProtectionDisableStatus.StageRejected, result.Status);
                Equal(0, fixture.Session.SdkEntries); Equal(0, fixture.Observers.Count);
                Equal(1, fixture.Pairs[0].Parameters.ConcreteDisposeCalls);
                Equal(0, fixture.Pairs[0].Buffer.ConcreteDisposeCalls); // The fake buffer was never allocated to the leaf.
                Equal(WsabiWmiProtectionSdkPreparationStatus.AllocationFailed, fixture.Session.LastPreparationStatus);
            }
            finally { await fixture.FinishAsync(); }
        });

        AddAsync("disable SDK common input registry does not dispose or rearm a wrapper owned by the old read path", async () =>
        {
            var old = InputPreparationPair.Create();
            Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                WsabiWmiWindowsInputPreparation.Populate(InputPreparationPlan(), InputPreparationRequest(), old.Parameters, old.Buffer));
            var fixture = new DisableSdkFixture { ParametersOverride = old.Parameters };
            try
            {
                var result = await DisableSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(WsabiWmiProtectionDisableStatus.StageRejected, result.Status);
                Equal(0, fixture.Target.InvokeCalls); Equal(0, fixture.BufferAllocations); Equal(0, fixture.Observers.Count);
                Equal(0, old.Parameters.ConcreteDisposeCalls); Equal(0, old.Buffer.ConcreteDisposeCalls);
                Equal(WsabiWmiProtectionSdkPreparationStatus.InputRejected, fixture.Session.LastPreparationStatus);
            }
            finally { await fixture.FinishAsync(); }
        });

        AddAsync("disable SDK shape and partial property mutation failures retire both claimed inputs and create no observer", async () =>
        {
            for (int variant = 0; variant < 3; variant++)
            {
                int failure = variant;
                var fixture = new DisableSdkFixture { OnPair = pair =>
                {
                    if (failure == 0) pair.Input.Type = CimType.String;
                    if (failure == 1) pair.Buffer.OnGetClassPath = () => throw new InvalidOperationException("Unreported fake metadata detail.");
                    if (failure == 2) pair.Bytes.AfterSetValue = value => throw new InvalidOperationException("Unreported fake assignment detail.");
                }};
                try
                {
                    var result = await DisableSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                    Equal(WsabiWmiProtectionDisableStatus.StageRejected, result.Status);
                    Equal(0, fixture.Target.InvokeCalls); Equal(0, fixture.Observers.Count);
                    Equal(1, fixture.Pairs[0].Parameters.ConcreteDisposeCalls); Equal(1, fixture.Pairs[0].Buffer.ConcreteDisposeCalls);
                    Equal(WsabiWmiProtectionSdkPreparationStatus.InputRejected, fixture.Session.LastPreparationStatus);
                }
                finally { await fixture.FinishAsync(); }
            }
        });

        AddAsync("disable SDK reused observer is rejected without removing the earlier observer owner", async () =>
        {
            var observer = new ManagementOperationObserver();
            var prior = new WsabiWmiWindowsCallbackSource(observer, (o, r) => { });
            Equal(WsabiWmiWindowsPreparationStatus.Ready, await prior.PrepareAsync(CancellationToken.None));
            var fixture = new DisableSdkFixture { ObserverOverride = observer };
            try
            {
                var result = await DisableSdkAwait(fixture.Session.RunAndCloseAsync(value => { }));
                Equal(WsabiWmiProtectionDisableStatus.StageRejected, result.Status); Equal(0, fixture.Target.InvokeCalls);
                Equal(1, observer.ObjectReadySubscriberCount); Equal(1, observer.CompletedSubscriberCount);
                Equal(WsabiWmiProtectionSdkPreparationStatus.ObserverUnavailable, fixture.Session.LastPreparationStatus);
                Equal(1, fixture.Pairs[0].Parameters.ConcreteDisposeCalls); Equal(1, fixture.Pairs[0].Buffer.ConcreteDisposeCalls);
            }
            finally { fixture.ObserverOverride = null; await prior.CloseUnusedAsync(); await fixture.FinishAsync(); }
        });

        AddAsync("disable SDK stop during blocked lazy allocation publishes cancellation but retains input ownership until allocation settles", async () =>
        {
            using (var release = new ManualResetEventSlim())
            using (var caller = new CancellationTokenSource())
            {
                var entered = CooperativeCompletion();
                var fixture = new DisableSdkFixture { OnPair = pair => { entered.TrySetResult(true); release.Wait(); } };
                var published = new TaskCompletionSource<WsabiWmiProtectionDisableOutcome>(TaskCreationOptions.RunContinuationsAsynchronously);
                var run = fixture.Session.RunAndCloseAsync(value => published.TrySetResult(value), caller.Token);
                try
                {
                    await CooperativeAwait(entered.Task); caller.Cancel(); await CooperativeAwait(published.Task);
                    Equal(WsabiWmiProtectionDisableStatus.Cancelled, (await published.Task).Status);
                    Check(!run.IsCompleted && fixture.Gate.LastLease.IsHeld, "cancel released a still-active SDK preparation worker");
                    Equal(0, fixture.Target.InvokeCalls); Equal(0, fixture.Pairs[0].Parameters.ConcreteDisposeCalls);
                    release.Set(); await DisableSdkAwait(run);
                    Equal(1, fixture.Pairs[0].Parameters.ConcreteDisposeCalls); Equal(0, fixture.BufferAllocations);
                    Equal(0, fixture.Observers.Count); Equal(WsabiWmiProtectionSdkPreparationStatus.Stopped, fixture.Session.LastPreparationStatus);
                }
                finally { release.Set(); await fixture.FinishAsync(); }
            }
        });

        AddAsync("disable SDK output unsubscribe failure keeps inputs held and blocks every later stage", async () =>
        {
            var fixture = new DisableSdkFixture { ObserverFailure = true };
            var published = new TaskCompletionSource<WsabiWmiProtectionDisableOutcome>(TaskCreationOptions.RunContinuationsAsynchronously);
            var run = fixture.Session.RunAndCloseAsync(value => published.TrySetResult(value));
            try
            {
                await CooperativeAwait(published.Task);
                Equal(WsabiWmiProtectionDisableStatus.CompletionUnknown, (await published.Task).Status);
                Equal(1, fixture.Target.InvokeCalls); Equal(1, fixture.Pairs.Count);
                Check(!run.IsCompleted && fixture.Gate.LastLease.IsHeld, "failed unsubscribe fabricated actual termination");
                Equal(0, fixture.Pairs[0].Parameters.ConcreteDisposeCalls); Equal(0, fixture.Pairs[0].Buffer.ConcreteDisposeCalls);
            }
            finally
            {
                fixture.DetachFailedFakeResources(); fixture.Session.ConfirmDetachedForTests();
                await DisableSdkAwait(run); await fixture.FinishAsync();
            }
        });

        AddAsync("disable SDK client-cancel terminal is not actual close and a later applicable fake terminal is still joined", async () =>
        {
            using (var caller = new CancellationTokenSource())
            {
                var entered = CooperativeCompletion(); var fixture = new DisableSdkFixture();
                fixture.OnInvoke = (observer, input) => { observer.EmitCompleted(ManagementStatus.CallCanceled); entered.TrySetResult(true); };
                var published = new TaskCompletionSource<WsabiWmiProtectionDisableOutcome>(TaskCreationOptions.RunContinuationsAsynchronously);
                var run = fixture.Session.RunAndCloseAsync(value => published.TrySetResult(value), caller.Token);
                try
                {
                    await CooperativeAwait(entered.Task); caller.Cancel(); await CooperativeAwait(published.Task);
                    Equal(WsabiWmiProtectionDisableStatus.Cancelled, (await published.Task).Status);
                    Check(!run.IsCompleted && fixture.Gate.LastLease.IsHeld, "CallCanceled was treated as provider termination");
                    Equal(0, fixture.Pairs[0].Parameters.ConcreteDisposeCalls);
                    fixture.Observers[0].EmitCompleted(ManagementStatus.NoError); // Applicable fake end; no real provider is involved.
                    await DisableSdkAwait(run); fixture.AssertReleased(); Equal(1, fixture.Target.InvokeCalls);
                }
                finally { await fixture.FinishAsync(); }
            }
        });
    }

    private static WsabiWmiProtectionDisableAttempt DisableSdkAttemptCreate(object identity)
    {
        WsabiWmiProtectionDisableAttempt attempt; WsabiWmiProtectionDisableAttemptIssue issue;
        Check(WsabiWmiProtectionDisableAttempt.TryCreateWithRandom(SingleReadTarget(identity), BinderCompleteMetadata(1),
            bytes => { for (int i = 0; i < bytes.Length; i++) bytes[i] = (byte)(i + 1); }, out attempt, out issue),
            "disable fixed SDK fixture creation failed");
        Equal(WsabiWmiProtectionDisableAttemptIssue.None, issue); return attempt;
    }

    private static async Task<WsabiWmiProtectionDisableOutcome> DisableSdkAwait(Task<WsabiWmiProtectionDisableOutcome> value)
    { await CooperativeAwait(value); return await value; }

    private sealed class DisableSdkFixture
    {
        internal readonly ManagementObject Target = new ManagementObject();
        internal readonly CooperativeTestGate Gate = new CooperativeTestGate();
        internal readonly List<InputPreparationPair> Pairs = new List<InputPreparationPair>();
        internal readonly List<ManagementOperationObserver> Observers = new List<ManagementOperationObserver>();
        internal readonly List<byte[]> Requests = new List<byte[]>();
        internal readonly WsabiWmiWindowsProtectionDisableTrialSession Session;
        internal byte PreMode = 1;
        internal byte PostMode;
        internal byte SetterEcho;
        internal bool BufferFailure, ObserverFailure;
        internal int BufferAllocations;
        internal ManagementBaseObject ParametersOverride;
        internal ManagementOperationObserver ObserverOverride;
        internal Action<InputPreparationPair> OnPair;
        internal Action<ManagementOperationObserver, ManagementBaseObject> OnInvoke;
        private InputPreparationPair current;
        internal DisableSdkFixture()
        {
            var attempt = DisableSdkAttemptCreate(Target);
            Session = WsabiWmiWindowsProtectionDisableTrial.PrepareForTests(attempt, Target, Gate,
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
                var raw = (byte[])buffer.Properties["Bytes"].Value; raw = (byte[])raw.Clone();
                Requests.Add((byte[])raw.Clone());
                raw[4] = 0xaa; raw[5] = 0; raw[6] = 0;
                int index = Target.InvokeCalls;
                raw[7] = index == 1 ? PreMode : index == 2 ? SetterEcho : PostMode;
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
