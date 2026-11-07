using System;
using System.Collections.Generic;
using System.Linq;
using System.Management;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.WmiInterop;

internal static partial class Program
{
    // Ownership orchestration with existing synthetic frames and test-only SDK
    // objects. No actual SDK invocation, target acquisition or read is present.
    private static void RegisterWsabiWmiOwnedInputPreparationTests()
    {
        AddAsync("owned input preparation rejects plan target and request mismatch before taking or inspecting inputs", async () =>
        {
            for (int variant = 0; variant < 3; variant++)
            {
                var fixture = new OwnedInputFixture();
                int sdkTouches = 0; InputPreparationPoisonSdk(fixture.Pair, () => sdkTouches++);
                var binding = variant == 1 ? new WsabiWmiWindowsReadTrialBinding(SingleReadTarget(new object()), fixture.Sdk,
                    (observer, request) => throw new InvalidOperationException("Unexpected mismatch dispatch.")) : fixture.Binding;
                var request = variant == 2 ? new WsabiWmiMethodRequest(2, 0x34, BoundChannelRequest()) : InputPreparationRequest();
                var result = await OwnedInputCall(variant == 0 ? null : fixture.Plan, binding, request,
                    fixture.Pair.Parameters, fixture.Pair.Buffer, fixture.Gate);
                OwnedInputAssertRejected(result, variant == 0 ? WsabiWmiSingleReadPreparationStatus.PlanMissing
                    : variant == 1 ? WsabiWmiSingleReadPreparationStatus.TargetMismatch : WsabiWmiSingleReadPreparationStatus.RequestMismatch);
                Equal(0, sdkTouches); InputPreparationAssertUntouched(fixture.Pair); InputPreparationAssertBorrowed(fixture.Pair);
                fixture.AssertNoRegistrationOrDispatch();
                InputPreparationResetSdk(fixture.Pair);
                Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                    WsabiWmiWindowsInputPreparation.Populate(fixture.Plan, InputPreparationRequest(), fixture.Pair.Parameters, fixture.Pair.Buffer));
                InputPreparationAssertBorrowed(fixture.Pair);
            }
        });

        AddAsync("owned input preparation structural guards preserve caller ownership and leave valid inputs unclaimed", async () =>
        {
            for (int variant = 0; variant < 4; variant++)
            {
                var fixture = new OwnedInputFixture(); int sdkTouches = 0;
                InputPreparationPoisonSdk(fixture.Pair, () => sdkTouches++);
                ManagementBaseObject parameters = variant == 0 || variant == 3 ? null : fixture.Pair.Parameters;
                ManagementBaseObject buffer = variant == 1 || variant == 3 ? null
                    : variant == 2 ? fixture.Pair.Parameters : fixture.Pair.Buffer;
                var result = await OwnedInputCall(fixture.Plan, fixture.Binding, InputPreparationRequest(), parameters, buffer, fixture.Gate);
                OwnedInputAssertRejected(result, WsabiWmiSingleReadPreparationStatus.InputNotReady,
                    WsabiWmiWindowsInputPreparationStatus.ObjectsMissingOrAliased);
                Equal(0, sdkTouches); InputPreparationAssertUntouched(fixture.Pair); InputPreparationAssertBorrowed(fixture.Pair);
                fixture.AssertNoRegistrationOrDispatch();
                InputPreparationResetSdk(fixture.Pair);
                Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                    WsabiWmiWindowsInputPreparation.Populate(fixture.Plan, InputPreparationRequest(), fixture.Pair.Parameters, fixture.Pair.Buffer));
            }
            var guarded = new OwnedInputFixture(); int touches = 0;
            InputPreparationPoisonSdk(guarded.Pair, () => touches++);
            BatteryThrows<ArgumentNullException>(() => OwnedInputCall(guarded.Plan, null, InputPreparationRequest(), guarded.Pair.Parameters, guarded.Pair.Buffer, guarded.Gate));
            BatteryThrows<ArgumentNullException>(() => OwnedInputCall(guarded.Plan, guarded.Binding, InputPreparationRequest(), guarded.Pair.Parameters, guarded.Pair.Buffer, null));
            BatteryThrows<ArgumentOutOfRangeException>(() => WsabiWmiWindowsSingleReadPreparation.PrepareWithInputsAsync(
                guarded.Plan, guarded.Binding, InputPreparationRequest(), guarded.Pair.Parameters, guarded.Pair.Buffer, guarded.Gate,
                TimeSpan.Zero, TimeSpan.FromSeconds(3)));
            Equal(0, touches); InputPreparationAssertUntouched(guarded.Pair); InputPreparationAssertBorrowed(guarded.Pair);
            guarded.AssertNoRegistrationOrDispatch();
        });

        AddAsync("owned input preparation pre cancellation consumes the plan attempt without taking input ownership", async () =>
        {
            using (var caller = new CancellationTokenSource())
            {
                var fixture = new OwnedInputFixture(); int sdkTouches = 0;
                InputPreparationPoisonSdk(fixture.Pair, () => sdkTouches++);
                caller.Cancel();
                var result = await OwnedInputPrepare(fixture, caller.Token);
                OwnedInputAssertRejected(result, WsabiWmiSingleReadPreparationStatus.PreparationNotReady,
                    registration: WsabiWmiWindowsPreparationStatus.Cancelled);
                Equal(0, sdkTouches); InputPreparationAssertUntouched(fixture.Pair); InputPreparationAssertBorrowed(fixture.Pair);
                fixture.AssertNoRegistrationOrDispatch();
                var retry = await WsabiWmiWindowsSingleReadPreparation.PrepareAsync(fixture.Plan, fixture.Binding,
                    InputPreparationRequest(), fixture.Gate, TimeSpan.FromMilliseconds(200), TimeSpan.FromSeconds(3));
                OwnedInputAssertRejected(retry, WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
                Equal(0, sdkTouches); fixture.AssertNoRegistrationOrDispatch();
                InputPreparationResetSdk(fixture.Pair);
                Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                    WsabiWmiWindowsInputPreparation.Populate(fixture.Plan, InputPreparationRequest(), fixture.Pair.Parameters, fixture.Pair.Buffer));
                InputPreparationAssertBorrowed(fixture.Pair);
            }
        });

        AddAsync("owned input preparation joins disposal after shape getter and partial setter failures before returning", async () =>
        {
            for (int variant = 0; variant < 4; variant++)
            {
                var fixture = new OwnedInputFixture();
                if (variant == 0) fixture.Pair.Input.Type = CimType.String;
                if (variant == 1) fixture.Pair.Buffer.OnGetClassPath = () => throw new InvalidOperationException("PRIVATE-SDK owned class getter");
                if (variant == 2) fixture.Pair.Bytes.BeforeSetValue = value => throw new InvalidOperationException("PRIVATE-SDK owned byte setter");
                if (variant == 3) fixture.Pair.Input.AfterSetValue = value => throw new InvalidOperationException("PRIVATE-SDK owned input after mutation");
                var result = await OwnedInputPrepare(fixture);
                OwnedInputAssertRejected(result, WsabiWmiSingleReadPreparationStatus.InputNotReady,
                    variant == 0 ? WsabiWmiWindowsInputPreparationStatus.ShapeMismatch : WsabiWmiWindowsInputPreparationStatus.PropertyAccessFailed,
                    transferred: true, cleanup: WsabiWmiWindowsCleanupStatus.Complete);
                OwnedInputAssertDisposed(fixture.Pair); fixture.AssertNoRegistrationOrDispatch();
                Equal(0, fixture.Pair.Input.ValueReads); Equal(0, fixture.Pair.Bytes.ValueReads);
                if (variant < 2) { Equal(0, fixture.Pair.Input.ValueWrites); Equal(0, fixture.Pair.Bytes.ValueWrites); }
                if (variant == 2) { Equal(0, fixture.Pair.Input.ValueWrites); Equal(1, fixture.Pair.Bytes.ValueWrites); }
                if (variant == 3) { Equal(1, fixture.Pair.Input.ValueWrites); Equal(1, fixture.Pair.Bytes.ValueWrites); }
                Equal(WsabiWmiWindowsInputPreparationStatus.ObjectsAlreadyUsed,
                    WsabiWmiWindowsInputPreparation.Populate(InputPreparationPlan(), InputPreparationRequest(), fixture.Pair.Parameters, fixture.Pair.Buffer));
                OwnedInputAssertDisposed(fixture.Pair);
            }
        });

        AddAsync("owned input preparation attempts both concrete disposals even when cleanup throws", async () =>
        {
            foreach (bool bothThrow in new[] { false, true })
            {
                var fixture = new OwnedInputFixture(); var attempted = new List<string>();
                fixture.Pair.Input.Type = CimType.String;
                fixture.Pair.Parameters.OnDispose = () =>
                {
                    attempted.Add("parameters"); throw new InvalidOperationException("PRIVATE-SDK first input cleanup");
                };
                fixture.Pair.Buffer.OnDispose = () =>
                {
                    attempted.Add("buffer"); if (bothThrow) throw new InvalidOperationException("PRIVATE-SDK second input cleanup");
                };
                var result = await OwnedInputPrepare(fixture);
                OwnedInputAssertRejected(result, WsabiWmiSingleReadPreparationStatus.InputNotReady,
                    WsabiWmiWindowsInputPreparationStatus.ShapeMismatch, transferred: true, cleanup: WsabiWmiWindowsCleanupStatus.Failed);
                Check(attempted.Count == 2 && attempted.Contains("parameters") && attempted.Contains("buffer"), "one failed disposal skipped the other borrowed root");
                OwnedInputAssertDisposed(fixture.Pair); fixture.AssertNoRegistrationOrDispatch();
            }
        });

        AddAsync("owned input preparation never disposes objects owned by borrowed population or a different ready invocation", async () =>
        {
            var borrowed = new OwnedInputFixture();
            Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                WsabiWmiWindowsInputPreparation.Populate(borrowed.Plan, InputPreparationRequest(), borrowed.Pair.Parameters, borrowed.Pair.Buffer));
            var rejected = await OwnedInputPrepare(borrowed);
            OwnedInputAssertRejected(rejected, WsabiWmiSingleReadPreparationStatus.InputNotReady,
                WsabiWmiWindowsInputPreparationStatus.ObjectsAlreadyUsed);
            InputPreparationAssertBorrowed(borrowed.Pair); borrowed.AssertNoRegistrationOrDispatch();

            var owner = new OwnedInputFixture();
            var ready = await OwnedInputPrepare(owner);
            try
            {
                Check(ready.IsReady && ready.Invocation != null, "owned input fixture did not become ready");
                var contender = new OwnedInputFixture { Pair = owner.Pair };
                var collision = await OwnedInputPrepare(contender);
                OwnedInputAssertRejected(collision, WsabiWmiSingleReadPreparationStatus.InputNotReady,
                    WsabiWmiWindowsInputPreparationStatus.ObjectsAlreadyUsed);
                InputPreparationAssertBorrowed(owner.Pair); contender.AssertNoRegistrationOrDispatch();
                Equal(1, owner.Sdk.ObjectReadySubscriberCount); Equal(1, owner.Sdk.CompletedSubscriberCount);
            }
            finally { if (ready.Invocation != null) await CooperativeAwait(ready.Invocation.RequestCloseAsync()); }
            OwnedInputAssertDisposed(owner.Pair);
        });

        AddAsync("owned input overlap rejection leaves a fresh other root unclaimed and undisposed", async () =>
        {
            foreach (bool reuseParameters in new[] { true, false })
            {
                var used = InputPreparationPair.Create();
                Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                    WsabiWmiWindowsInputPreparation.Populate(InputPreparationPlan(), InputPreparationRequest(), used.Parameters, used.Buffer));
                var fixture = new OwnedInputFixture(); int sdkTouches = 0;
                InputPreparationPoisonSdk(used, () => sdkTouches++); InputPreparationPoisonSdk(fixture.Pair, () => sdkTouches++);
                var rejected = await OwnedInputCall(fixture.Plan, fixture.Binding, InputPreparationRequest(),
                    reuseParameters ? used.Parameters : fixture.Pair.Parameters,
                    reuseParameters ? fixture.Pair.Buffer : used.Buffer, fixture.Gate);
                OwnedInputAssertRejected(rejected, WsabiWmiSingleReadPreparationStatus.InputNotReady,
                    WsabiWmiWindowsInputPreparationStatus.ObjectsAlreadyUsed);
                Equal(0, sdkTouches); InputPreparationAssertUntouched(fixture.Pair);
                InputPreparationAssertBorrowed(used); InputPreparationAssertBorrowed(fixture.Pair); fixture.AssertNoRegistrationOrDispatch();
                InputPreparationResetSdk(fixture.Pair);
                Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                    WsabiWmiWindowsInputPreparation.Populate(fixture.Plan, InputPreparationRequest(), fixture.Pair.Parameters, fixture.Pair.Buffer));
                InputPreparationAssertBorrowed(fixture.Pair);
            }
        });

        AddAsync("owned input successful population is disposed after failed SDK registration and cannot retry the same plan", async () =>
        {
            var fixture = new OwnedInputFixture();
            fixture.OnAdd = name => { if (name == "Completed") throw new InvalidOperationException("PRIVATE-SDK owned registration"); };
            fixture.Pair.Parameters.OnDispose = () => OwnedInputAssertUnsubscribed(fixture.Sdk);
            fixture.Pair.Buffer.OnDispose = () => OwnedInputAssertUnsubscribed(fixture.Sdk);
            var rejected = await OwnedInputPrepare(fixture);
            OwnedInputAssertRejected(rejected, WsabiWmiSingleReadPreparationStatus.PreparationNotReady,
                WsabiWmiWindowsInputPreparationStatus.Populated, WsabiWmiWindowsPreparationStatus.RegistrationFailed,
                true, WsabiWmiWindowsCleanupStatus.Complete);
            Equal(1, fixture.Pair.Input.ValueWrites); Equal(1, fixture.Pair.Bytes.ValueWrites);
            OwnedInputAssertDisposed(fixture.Pair); OwnedInputAssertUnsubscribed(fixture.Sdk);
            Equal(0, fixture.Calls); Equal(0, fixture.Gate.Calls);
            int adds = fixture.Adds;
            var retry = await OwnedInputPrepare(fixture);
            OwnedInputAssertRejected(retry, WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
            Equal(adds, fixture.Adds); OwnedInputAssertDisposed(fixture.Pair);
        });

        AddAsync("owned input successful population is disposed after cancellation during registration", async () =>
        {
            using (var caller = new CancellationTokenSource())
            {
                var fixture = new OwnedInputFixture();
                fixture.OnAdd = name => { if (name == "ObjectReady") caller.Cancel(); };
                fixture.Pair.Parameters.OnDispose = () => OwnedInputAssertUnsubscribed(fixture.Sdk);
                fixture.Pair.Buffer.OnDispose = () => OwnedInputAssertUnsubscribed(fixture.Sdk);
                var rejected = await OwnedInputPrepare(fixture, caller.Token);
                OwnedInputAssertRejected(rejected, WsabiWmiSingleReadPreparationStatus.PreparationNotReady,
                    WsabiWmiWindowsInputPreparationStatus.Populated, WsabiWmiWindowsPreparationStatus.Cancelled,
                    true, WsabiWmiWindowsCleanupStatus.Complete);
                Equal(1, fixture.Pair.Input.ValueWrites); Equal(1, fixture.Pair.Bytes.ValueWrites);
                Equal(1, fixture.Adds); Equal(0, fixture.Calls); Equal(0, fixture.Gate.Calls);
                OwnedInputAssertDisposed(fixture.Pair); OwnedInputAssertUnsubscribed(fixture.Sdk);
            }
        });

        AddAsync("owned input ready handle retains roots until unused close joins registration cleanup and repeated close is stable", async () =>
        {
            var fixture = new OwnedInputFixture(); var order = new List<string>();
            fixture.Sdk.BeforeRemove = name => order.Add("remove " + name);
            fixture.Pair.Parameters.OnDispose = () => { OwnedInputAssertUnsubscribed(fixture.Sdk); order.Add("dispose parameters"); };
            fixture.Pair.Buffer.OnDispose = () => { OwnedInputAssertUnsubscribed(fixture.Sdk); order.Add("dispose buffer"); };
            var ready = await OwnedInputPrepare(fixture);
            try
            {
                Check(ready.IsReady && ready.Invocation != null, "ready ownership fixture did not expose its existing invocation type");
                Equal(WsabiWmiSingleReadPreparationStatus.Ready, ready.Status);
                Equal<WsabiWmiWindowsPreparationStatus?>(WsabiWmiWindowsPreparationStatus.Ready, ready.RegistrationStatus);
                Equal<WsabiWmiWindowsInputPreparationStatus?>(WsabiWmiWindowsInputPreparationStatus.Populated, ready.InputStatus);
                Check(ready.InputOwnershipTransferred && ready.InputCleanupStatus == null, "Ready reported early cleanup or failed ownership transfer");
                InputPreparationAssertBorrowed(fixture.Pair);
                Equal(1, fixture.Pair.Input.ValueWrites); Equal(1, fixture.Pair.Bytes.ValueWrites);
                Equal(1, fixture.Sdk.ObjectReadySubscriberCount); Equal(1, fixture.Sdk.CompletedSubscriberCount);
                Check(!ready.Invocation.CanInvokeMethods && !ready.Invocation.CanReadHardware && !ready.Invocation.CanWriteHardware,
                    "owned input readiness became permission to access hardware");
                var close = ready.Invocation.RequestCloseAsync();
                Check(ReferenceEquals(close, ready.Invocation.RequestCloseAsync()), "owned unused close was restarted");
                await CooperativeAwait(close); Equal(WsabiWmiWindowsCleanupStatus.Complete, await close);
                Check(order.Count == 4 && order.Take(2).All(item => item.StartsWith("remove ")) &&
                    order.Skip(2).All(item => item.StartsWith("dispose ")), "owned inputs were disposed before inner registration cleanup");
                OwnedInputAssertDisposed(fixture.Pair); OwnedInputAssertUnsubscribed(fixture.Sdk);
                BatteryThrows<InvalidOperationException>(() => ready.Invocation.RunAndCloseAsync(value => { }));
                Equal(0, fixture.Calls); Equal(0, fixture.Gate.Calls);
            }
            finally { if (ready.Invocation != null) await CooperativeAwait(ready.Invocation.RequestCloseAsync()); }
        });
    }

    private static Task<WsabiWmiSingleReadPreparationResult> OwnedInputPrepare(OwnedInputFixture fixture,
        CancellationToken token = default(CancellationToken))
        => OwnedInputCall(fixture.Plan, fixture.Binding, InputPreparationRequest(), fixture.Pair.Parameters, fixture.Pair.Buffer, fixture.Gate, token);

    private static Task<WsabiWmiSingleReadPreparationResult> OwnedInputCall(WsabiWmiSingleReadPlan plan,
        WsabiWmiWindowsReadTrialBinding binding, WsabiWmiMethodRequest request, ManagementBaseObject parameters,
        ManagementBaseObject buffer, IWsabiWmiExchangeGate gate, CancellationToken token = default(CancellationToken))
        => WsabiWmiWindowsSingleReadPreparation.PrepareWithInputsAsync(plan, binding, request, parameters, buffer,
            gate, TimeSpan.FromMilliseconds(200), TimeSpan.FromSeconds(3), token);

    private static void OwnedInputAssertRejected(WsabiWmiSingleReadPreparationResult result,
        WsabiWmiSingleReadPreparationStatus status, WsabiWmiWindowsInputPreparationStatus? input = null,
        WsabiWmiWindowsPreparationStatus? registration = null, bool transferred = false,
        WsabiWmiWindowsCleanupStatus? cleanup = null)
    {
        Equal(status, result.Status); Check(!result.IsReady && result.Invocation == null, "rejected ownership result exposed an invocation");
        Equal(input, result.InputStatus); Equal(registration, result.RegistrationStatus);
        Equal(transferred, result.InputOwnershipTransferred); Equal(cleanup, result.InputCleanupStatus);
    }

    private static void OwnedInputAssertDisposed(InputPreparationPair pair)
    {
        Equal(1, pair.Parameters.ConcreteDisposeCalls); Equal(1, pair.Buffer.ConcreteDisposeCalls);
        Equal(0, pair.Parameters.ComponentDisposeCalls); Equal(0, pair.Buffer.ComponentDisposeCalls);
    }

    private static void OwnedInputAssertUnsubscribed(ManagementOperationObserver observer)
    {
        Equal(0, observer.ObjectReadySubscriberCount); Equal(0, observer.CompletedSubscriberCount);
    }

    private sealed class OwnedInputFixture
    {
        internal readonly WsabiWmiSingleReadTarget Target;
        internal readonly WsabiWmiSingleReadPlan Plan;
        internal readonly WsabiWmiWindowsReadTrialBinding Binding;
        internal readonly ManagementOperationObserver Sdk = new ManagementOperationObserver();
        internal readonly CooperativeTestGate Gate = new CooperativeTestGate();
        internal InputPreparationPair Pair = InputPreparationPair.Create();
        internal int Calls, Adds;
        internal Action<string> OnAdd;

        internal OwnedInputFixture()
        {
            Target = SingleReadTarget(new object()); Plan = SingleReadPlanCreate(Target);
            Binding = new WsabiWmiWindowsReadTrialBinding(Target, Sdk, (observer, request) => Interlocked.Increment(ref Calls));
            Sdk.BeforeAdd = name => { Interlocked.Increment(ref Adds); OnAdd?.Invoke(name); };
        }

        internal void AssertNoRegistrationOrDispatch()
        {
            Equal(0, Adds); Equal(0, Calls); Equal(0, Gate.Calls); OwnedInputAssertUnsubscribed(Sdk);
        }
    }
}
