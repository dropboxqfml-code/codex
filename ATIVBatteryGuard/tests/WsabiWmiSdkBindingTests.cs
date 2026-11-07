using System;
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
    // Executes our SDK boundary against stand-ins only. The supplied envelope
    // remains the existing synthetic 0x34 fixture, not a hardware read recipe.
    private static void RegisterWsabiWmiSdkBindingTests()
    {
        Add("SDK binding requires nonnull dedicated references and exposes no public SDK getters", () =>
        {
            var fixture = new SdkBindingFixture();
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiWindowsSdkBinding(null, fixture.Target, fixture.Observer, fixture.Pair.Parameters, fixture.Pair.Buffer));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiWindowsSdkBinding(fixture.Facts, null, fixture.Observer, fixture.Pair.Parameters, fixture.Pair.Buffer));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiWindowsSdkBinding(fixture.Facts, fixture.Target, null, fixture.Pair.Parameters, fixture.Pair.Buffer));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiWindowsSdkBinding(fixture.Facts, fixture.Target, fixture.Observer, null, fixture.Pair.Buffer));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiWindowsSdkBinding(fixture.Facts, fixture.Target, fixture.Observer, fixture.Pair.Parameters, null));
            BatteryThrows<ArgumentException>(() => new WsabiWmiWindowsSdkBinding(fixture.Facts, fixture.Target, fixture.Observer, fixture.Target, fixture.Pair.Buffer));
            BatteryThrows<ArgumentException>(() => new WsabiWmiWindowsSdkBinding(fixture.Facts, fixture.Target, fixture.Observer, fixture.Pair.Parameters, fixture.Target));
            BatteryThrows<ArgumentException>(() => new WsabiWmiWindowsSdkBinding(fixture.Facts, fixture.Target, fixture.Observer, fixture.Pair.Parameters, fixture.Pair.Parameters));
            foreach (var property in typeof(WsabiWmiWindowsSdkBinding).GetProperties(BindingFlags.Public | BindingFlags.Instance))
                Check(!typeof(ManagementBaseObject).IsAssignableFrom(property.PropertyType) &&
                    property.PropertyType != typeof(ManagementOperationObserver) && property.PropertyType != typeof(object),
                    "SDK binding exposed a mutable SDK reference");
            fixture.AssertNoLowerWork();
        });

        Add("single read plan matches SDK target identity purely by reference without SDK getters or provider equality", () =>
        {
            var target = new SdkBindingPoisonTarget(); int touches = 0;
            target.OnGetScope = () => { touches++; throw new InvalidOperationException("PRIVATE-SDK pure identity scope"); };
            target.OnGetPath = () => { touches++; throw new InvalidOperationException("PRIVATE-SDK pure identity path"); };
            var plan = SingleReadPlanCreate(SingleReadTarget(target));
            Check(plan.MatchesTargetIdentity(target), "same opaque SDK target reference did not match");
            Check(!plan.MatchesTargetIdentity(null) && !plan.MatchesTargetIdentity(new SdkBindingPoisonTarget()), "different SDK target identity matched");
            Equal(0, touches); Equal(0, target.InvokeCalls); Equal(0, target.ConcreteDisposeCalls);
            Check(!plan.IsHardwareObservation && !plan.CanInvokeMethods && !plan.CanReadHardware && !plan.CanWriteHardware,
                "SDK reference identity became hardware authority");
        });

        AddAsync("SDK preparation rejects actual target identity mismatch before SDK reads input claims or registration", async () =>
        {
            var fixture = new SdkBindingFixture(factsIdentity: new object()); int sdkTouches = 0;
            SdkBindingPoisonAccess(fixture, () => sdkTouches++);
            var rejected = await SdkBindingPrepare(fixture);
            SdkBindingAssertRejected(rejected, WsabiWmiWindowsSdkBindingStatus.IdentityMismatch);
            Equal(0, sdkTouches); fixture.AssertNoLowerWork();
            var old = new WsabiWmiWindowsReadTrialBinding(fixture.Facts, new ManagementOperationObserver(), (observer, request) => { });
            var retry = await WsabiWmiWindowsSingleReadPreparation.PrepareAsync(fixture.Plan, old, InputPreparationRequest(),
                fixture.Gate, TimeSpan.FromMilliseconds(200), TimeSpan.FromSeconds(3));
            OwnedInputAssertRejected(retry, WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
            Equal<WsabiWmiWindowsSdkBindingStatus?>(null, retry.SdkStatus);
            SdkBindingResetAccess(fixture);
            Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                WsabiWmiWindowsInputPreparation.Populate(fixture.Plan, InputPreparationRequest(), fixture.Pair.Parameters, fixture.Pair.Buffer));
            InputPreparationAssertBorrowed(fixture.Pair);
        });

        AddAsync("SDK preparation preserves plan facts and request rejection before inspecting the target or inputs", async () =>
        {
            for (int variant = 0; variant < 3; variant++)
            {
                var fixture = new SdkBindingFixture(); int sdkTouches = 0;
                SdkBindingPoisonAccess(fixture, () => sdkTouches++);
                var plan = variant == 0 ? null : variant == 1 ? SingleReadPlanCreate(SingleReadTarget(new object())) : fixture.Plan;
                var request = variant == 2 ? new WsabiWmiMethodRequest(2, 0x34, BoundChannelRequest()) : InputPreparationRequest();
                var rejected = await SdkBindingCall(plan, fixture.Binding, request, fixture.Gate);
                OwnedInputAssertRejected(rejected, variant == 0 ? WsabiWmiSingleReadPreparationStatus.PlanMissing
                    : variant == 1 ? WsabiWmiSingleReadPreparationStatus.TargetMismatch : WsabiWmiSingleReadPreparationStatus.RequestMismatch);
                Equal<WsabiWmiWindowsSdkBindingStatus?>(null, rejected.SdkStatus);
                Equal(0, sdkTouches); fixture.AssertNoLowerWork();
                SdkBindingResetAccess(fixture);
                Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                    WsabiWmiWindowsInputPreparation.Populate(fixture.Plan, InputPreparationRequest(), fixture.Pair.Parameters, fixture.Pair.Buffer));
            }
        });

        AddAsync("SDK preparation rejects target subclasses without calling their SDK routing getters", async () =>
        {
            var fixture = new SdkBindingFixture(new SdkBindingPoisonTarget()); int sdkTouches = 0;
            SdkBindingPoisonAccess(fixture, () => sdkTouches++);
            var rejected = await SdkBindingPrepare(fixture);
            SdkBindingAssertRejected(rejected, WsabiWmiWindowsSdkBindingStatus.UnsupportedTargetType);
            Equal(0, sdkTouches); fixture.AssertNoLowerWork();
            SdkBindingResetAccess(fixture);
            Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                WsabiWmiWindowsInputPreparation.Populate(fixture.Plan, InputPreparationRequest(), fixture.Pair.Parameters, fixture.Pair.Buffer));
        });

        AddAsync("SDK preparation requires an already connected local scope with exact bounded namespace", async () =>
        {
            var changes = new Action<SdkBindingFixture>[]
            {
                fixture => fixture.Target.Scope = null,
                fixture => fixture.Target.Scope.IsConnected = false,
                fixture => fixture.Target.Scope.Path = null,
                fixture => fixture.Target.Scope.Path.Server = "localhost",
                fixture => fixture.Target.Scope.Path.Server = "127.0.0.1",
                fixture => fixture.Target.Scope.Path.Server = " .",
                fixture => fixture.Target.Scope.Path.Server = null,
                fixture => fixture.Target.Scope.Path.Server = "",
                fixture => fixture.Target.Scope.Path.NamespacePath = @"root\cimv2",
                fixture => fixture.Target.Scope.Path.NamespacePath = @"\\remote\root\WMI",
                fixture => fixture.Target.Scope.Path.NamespacePath = @"root\WMI ",
                fixture => fixture.Target.Scope.Path.NamespacePath = null,
                fixture => fixture.Target.Scope.Path.NamespacePath = new string('x', 129)
            };
            for (int index = 0; index < changes.Length; index++)
            {
                var fixture = new SdkBindingFixture(); changes[index](fixture);
                int inputTouches = 0; InputPreparationPoisonSdk(fixture.Pair, () => inputTouches++);
                var rejected = await SdkBindingPrepare(fixture);
                SdkBindingAssertRejected(rejected, index < 2 ? WsabiWmiWindowsSdkBindingStatus.NotConnected : WsabiWmiWindowsSdkBindingStatus.LocalScopeMismatch);
                Equal(0, inputTouches); fixture.AssertNoLowerWork();
            }
            var accepted = new SdkBindingFixture(); accepted.Target.Scope.Path.NamespacePath = @"ROOT\wmi";
            var ready = await SdkBindingPrepare(accepted);
            try { Check(ready.IsReady, "ordinal namespace case variant was rejected"); }
            finally { if (ready.Invocation != null) await CooperativeAwait(ready.Invocation.RequestCloseAsync()); }
        });

        AddAsync("SDK preparation requires the supplied target path to be an instance of the fixed method class", async () =>
        {
            var changes = new Action<SdkBindingFixture>[]
            {
                fixture => fixture.Target.Path = null,
                fixture => fixture.Target.Path.IsInstance = false,
                fixture => fixture.Target.Path.ClassName = null,
                fixture => fixture.Target.Path.ClassName = "WmiAcpiVersion",
                fixture => fixture.Target.Path.ClassName = "WmiAcpiMethodExtra",
                fixture => fixture.Target.Path.ClassName = " WmiAcpiMethod",
                fixture => fixture.Target.Path.ClassName = new string('x', 129)
            };
            foreach (var change in changes)
            {
                var fixture = new SdkBindingFixture(); change(fixture);
                int inputTouches = 0; InputPreparationPoisonSdk(fixture.Pair, () => inputTouches++);
                var rejected = await SdkBindingPrepare(fixture);
                SdkBindingAssertRejected(rejected, WsabiWmiWindowsSdkBindingStatus.InstanceMismatch);
                Equal(0, inputTouches); fixture.AssertNoLowerWork();
            }
        });

        AddAsync("SDK preparation converts routing getter exceptions to fixed status before input ownership or registration", async () =>
        {
            var changes = new Action<SdkBindingFixture>[]
            {
                fixture => fixture.Target.OnGetScope = () => throw new InvalidOperationException("PRIVATE-SDK Scope"),
                fixture => fixture.Target.Scope.OnGetIsConnected = () => throw new InvalidOperationException("PRIVATE-SDK IsConnected"),
                fixture => fixture.Target.Scope.OnGetPath = () => throw new InvalidOperationException("PRIVATE-SDK scope Path"),
                fixture => fixture.Target.Scope.Path.OnGetServer = () => throw new InvalidOperationException("PRIVATE-SDK Server"),
                fixture => fixture.Target.Scope.Path.OnGetNamespacePath = () => throw new InvalidOperationException("PRIVATE-SDK NamespacePath"),
                fixture => fixture.Target.OnGetPath = () => throw new InvalidOperationException("PRIVATE-SDK instance Path"),
                fixture => fixture.Target.Path.OnGetIsInstance = () => throw new InvalidOperationException("PRIVATE-SDK IsInstance"),
                fixture => fixture.Target.Path.OnGetClassName = () => throw new InvalidOperationException("PRIVATE-SDK ClassName")
            };
            foreach (var change in changes)
            {
                var fixture = new SdkBindingFixture(); change(fixture);
                int inputTouches = 0; InputPreparationPoisonSdk(fixture.Pair, () => inputTouches++);
                var rejected = await SdkBindingPrepare(fixture);
                SdkBindingAssertRejected(rejected, WsabiWmiWindowsSdkBindingStatus.PropertyAccessFailed);
                Equal(0, inputTouches); fixture.AssertNoLowerWork();
            }
        });

        AddAsync("SDK preparation pre cancellation consumes bundle and plan budgets without SDK reads or input transfer", async () =>
        {
            using (var caller = new CancellationTokenSource())
            {
                var fixture = new SdkBindingFixture(); int sdkTouches = 0;
                SdkBindingPoisonAccess(fixture, () => sdkTouches++); caller.Cancel();
                var cancelled = await SdkBindingPrepare(fixture, caller.Token);
                OwnedInputAssertRejected(cancelled, WsabiWmiSingleReadPreparationStatus.PreparationNotReady,
                    registration: WsabiWmiWindowsPreparationStatus.Cancelled);
                Equal<WsabiWmiWindowsSdkBindingStatus?>(null, cancelled.SdkStatus);
                var samePlan = await SdkBindingPrepare(fixture);
                OwnedInputAssertRejected(samePlan, WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
                Equal<WsabiWmiWindowsSdkBindingStatus?>(null, samePlan.SdkStatus);
                var newPlan = SingleReadPlanCreate(fixture.Facts);
                var sameBinding = await SdkBindingCall(newPlan, fixture.Binding, InputPreparationRequest(), fixture.Gate);
                SdkBindingAssertRejected(sameBinding, WsabiWmiWindowsSdkBindingStatus.BindingAlreadyUsed);
                Equal(0, sdkTouches); fixture.AssertNoLowerWork();
            }
        });

        AddAsync("SDK binding performs one typed fixed method handoff using the exact observer and populated input roots", async () =>
        {
            var fixture = new SdkBindingFixture();
            var originalTarget = fixture.Target; var originalObserver = fixture.Observer; var originalPair = fixture.Pair;
            byte[] assignedBytes = null; object assignedBuffer = null;
            originalPair.Bytes.AfterSetValue = value => assignedBytes = (byte[])value;
            originalPair.Input.AfterSetValue = value => assignedBuffer = value;
            ManagementBaseObject embedded;
            var output = WindowsOutputFixture(BoundChannelReply(), out embedded);
            int handoffs = 0;
            ManagementOperationObserver observedObserver = null;
            ManagementBaseObject observedParameters = null;
            InvokeMethodOptions observedOptions = null;
            string observedMethod = null;
            byte[] bytesAtHandoff = null;
            object bufferAtHandoff = null;
            originalTarget.OnInvoke = (observer, method, parameters, options) =>
            {
                Interlocked.Increment(ref handoffs);
                observedObserver = observer; observedParameters = parameters;
                observedMethod = method; observedOptions = options;
                bytesAtHandoff = assignedBytes == null ? null : (byte[])assignedBytes.Clone();
                bufferAtHandoff = assignedBuffer;
                // Hook assertions must not turn a harness failure into a
                // missing-terminal invocation. Always finish the fake attempt.
                try { originalObserver.EmitObjectReady(output); }
                finally { originalObserver.EmitCompleted(ManagementStatus.NoError); }
            };
            // Replacing caller-side holders cannot redirect private bundle refs.
            fixture.Pair = InputPreparationPair.Create();
            var ready = await SdkBindingPrepare(fixture);
            Task<WsabiWmiFrameExchangeResult> run = null;
            try
            {
                Check(ready.IsReady && ready.Invocation != null, "SDK stand-in binding did not become ready");
                Equal<WsabiWmiWindowsSdkBindingStatus?>(WsabiWmiWindowsSdkBindingStatus.Ready, ready.SdkStatus);
                Equal<WsabiWmiWindowsInputPreparationStatus?>(WsabiWmiWindowsInputPreparationStatus.Populated, ready.InputStatus);
                Check(ready.InputOwnershipTransferred && ready.InputCleanupStatus == null, "SDK readiness misreported input ownership");
                int reports = 0;
                WsabiWmiFrameExchangeResult shown = null;
                run = ready.Invocation.RunAndCloseAsync(value => { reports++; shown = value; });
                await CooperativeAwait(run);
                var result = await run;
                Check(result.IsValidFrame && ReferenceEquals(shown, result), "fixed SDK stand-in result did not reach the existing decoder");
                Check(!result.IsHardwareObservation && !result.CanReadHardware && !result.CanWriteHardware && !result.CanInvokeMethods,
                    "synthetic SDK output became hardware authority");
                Check(ReferenceEquals(observedObserver, originalObserver) && ReferenceEquals(observedParameters, originalPair.Parameters),
                    "typed dispatch substituted the supplied observer or parameter root");
                Equal("CallSabiFunction", observedMethod); Check(observedOptions != null, "typed dispatch omitted its SDK method options");
                Check(ReferenceEquals(bufferAtHandoff, originalPair.Buffer) && bytesAtHandoff != null &&
                    bytesAtHandoff.SequenceEqual(BoundChannelRequest()), "typed dispatch did not use its populated fixed input pair");
                Equal(1, reports); Equal(1, handoffs); Equal(1, originalTarget.InvokeCalls);
                OwnedInputAssertDisposed(originalPair); InputPreparationAssertUntouched(fixture.Pair); InputPreparationAssertBorrowed(fixture.Pair);
                Equal(1, output.ConcreteDisposeCalls); Equal(1, embedded.ConcreteDisposeCalls);
                Equal(0, originalTarget.ConcreteDisposeCalls); Equal(0, originalTarget.ComponentDisposeCalls);
                BatteryThrows<InvalidOperationException>(() => ready.Invocation.RunAndCloseAsync(value => { }));
                Equal(1, originalTarget.InvokeCalls); OwnedInputAssertUnsubscribed(originalObserver);
            }
            finally
            {
                originalObserver.EmitCompleted(ManagementStatus.AccessDenied); // Fake-only failure cleanup.
                if (ready.Invocation != null) await CooperativeAwait(ready.Invocation.RequestCloseAsync());
                if (run != null) await InvocationSettled(run);
            }
        });

        AddAsync("SDK preparation shares the old plan budget while early plan rejection leaves its bundle unused", async () =>
        {
            var fixture = new SdkBindingFixture();
            var oldObserver = new ManagementOperationObserver();
            var oldBinding = new WsabiWmiWindowsReadTrialBinding(fixture.Facts, oldObserver, (observer, request) => { });
            var old = await WsabiWmiWindowsSingleReadPreparation.PrepareAsync(fixture.Plan, oldBinding, InputPreparationRequest(),
                fixture.Gate, TimeSpan.FromMilliseconds(200), TimeSpan.FromSeconds(3));
            WsabiWmiSingleReadPreparationResult ready = null;
            try
            {
                Check(old.IsReady, "legacy detached fixture did not become ready");
                await CooperativeAwait(old.Invocation.RequestCloseAsync());
                var rejected = await SdkBindingPrepare(fixture);
                OwnedInputAssertRejected(rejected, WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
                Equal<WsabiWmiWindowsSdkBindingStatus?>(null, rejected.SdkStatus); fixture.AssertNoLowerWork();
                ready = await SdkBindingCall(SingleReadPlanCreate(fixture.Facts), fixture.Binding, InputPreparationRequest(), fixture.Gate);
                Check(ready.IsReady, "plan-level rejection incorrectly consumed the private SDK bundle");
                Equal<WsabiWmiWindowsSdkBindingStatus?>(WsabiWmiWindowsSdkBindingStatus.Ready, ready.SdkStatus);
                Equal(0, fixture.Target.InvokeCalls);
            }
            finally
            {
                if (old.Invocation != null) await CooperativeAwait(old.Invocation.RequestCloseAsync());
                if (ready?.Invocation != null) await CooperativeAwait(ready.Invocation.RequestCloseAsync());
            }
        });

        AddAsync("SDK preparation rejects input wrappers already held by borrowed population or another ready owner", async () =>
        {
            foreach (bool owned in new[] { false, true })
            {
                var fixture = new SdkBindingFixture();
                WsabiWmiSingleReadPreparationResult owner = null;
                try
                {
                    if (owned)
                    {
                        var old = new OwnedInputFixture { Pair = fixture.Pair };
                        owner = await OwnedInputPrepare(old);
                        Check(owner.IsReady, "separate owned fixture did not become ready");
                    }
                    else Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                        WsabiWmiWindowsInputPreparation.Populate(fixture.Plan, InputPreparationRequest(), fixture.Pair.Parameters, fixture.Pair.Buffer));
                    var rejected = await SdkBindingPrepare(fixture);
                    OwnedInputAssertRejected(rejected, WsabiWmiSingleReadPreparationStatus.InputNotReady,
                        WsabiWmiWindowsInputPreparationStatus.ObjectsAlreadyUsed);
                    Equal<WsabiWmiWindowsSdkBindingStatus?>(WsabiWmiWindowsSdkBindingStatus.Ready, rejected.SdkStatus);
                    InputPreparationAssertBorrowed(fixture.Pair);
                    Equal(0, fixture.Adds); Equal(0, fixture.Target.InvokeCalls); Equal(0, fixture.Gate.Calls);
                    OwnedInputAssertUnsubscribed(fixture.Observer);
                }
                finally { if (owner?.Invocation != null) await CooperativeAwait(owner.Invocation.RequestCloseAsync()); }
                if (owned) OwnedInputAssertDisposed(fixture.Pair);
                else InputPreparationAssertBorrowed(fixture.Pair);
            }
        });
    }

    private static Task<WsabiWmiSingleReadPreparationResult> SdkBindingPrepare(SdkBindingFixture fixture,
        CancellationToken token = default(CancellationToken))
        => SdkBindingCall(fixture.Plan, fixture.Binding, InputPreparationRequest(), fixture.Gate, token);

    private static Task<WsabiWmiSingleReadPreparationResult> SdkBindingCall(WsabiWmiSingleReadPlan plan,
        WsabiWmiWindowsSdkBinding binding, WsabiWmiMethodRequest request, IWsabiWmiExchangeGate gate,
        CancellationToken token = default(CancellationToken))
        => WsabiWmiWindowsSingleReadPreparation.PrepareSdkBindingAsync(plan, binding, request, gate,
            TimeSpan.FromMilliseconds(200), TimeSpan.FromSeconds(3), token);

    private static void SdkBindingAssertRejected(WsabiWmiSingleReadPreparationResult result, WsabiWmiWindowsSdkBindingStatus sdkStatus)
    {
        OwnedInputAssertRejected(result, WsabiWmiSingleReadPreparationStatus.SdkBindingNotReady);
        Equal<WsabiWmiWindowsSdkBindingStatus?>(sdkStatus, result.SdkStatus);
    }

    private static void SdkBindingPoisonAccess(SdkBindingFixture fixture, Action touched)
    {
        fixture.Target.OnGetScope = () => { touched(); throw new InvalidOperationException("PRIVATE-SDK premature target scope"); };
        fixture.Target.OnGetPath = () => { touched(); throw new InvalidOperationException("PRIVATE-SDK premature target path"); };
        InputPreparationPoisonSdk(fixture.Pair, touched);
    }

    private static void SdkBindingResetAccess(SdkBindingFixture fixture)
    {
        fixture.Target.OnGetScope = null; fixture.Target.OnGetPath = null; InputPreparationResetSdk(fixture.Pair);
    }

    private sealed class SdkBindingFixture
    {
        internal readonly ManagementObject Target;
        internal readonly ManagementOperationObserver Observer = new ManagementOperationObserver();
        internal readonly CooperativeTestGate Gate = new CooperativeTestGate();
        internal readonly WsabiWmiSingleReadTarget Facts;
        internal readonly WsabiWmiSingleReadPlan Plan;
        internal readonly WsabiWmiWindowsSdkBinding Binding;
        internal InputPreparationPair Pair = InputPreparationPair.Create();
        internal int Adds;

        internal SdkBindingFixture(ManagementObject target = null, object factsIdentity = null)
        {
            Target = target ?? new ManagementObject();
            Target.Scope = new ManagementScope
            {
                IsConnected = true, Path = new ManagementPath { Server = ".", NamespacePath = @"root\WMI" }
            };
            Target.Path = new ManagementPath("WmiAcpiMethod") { IsInstance = true };
            Facts = SingleReadTarget(factsIdentity ?? Target); Plan = SingleReadPlanCreate(Facts);
            Binding = new WsabiWmiWindowsSdkBinding(Facts, Target, Observer, Pair.Parameters, Pair.Buffer);
            Observer.BeforeAdd = name => Interlocked.Increment(ref Adds);
        }

        internal void AssertNoLowerWork()
        {
            Equal(0, Adds); Equal(0, Gate.Calls); Equal(0, Target.InvokeCalls);
            InputPreparationAssertUntouched(Pair); InputPreparationAssertBorrowed(Pair);
            Equal(0, Target.ConcreteDisposeCalls); Equal(0, Target.ComponentDisposeCalls);
            OwnedInputAssertUnsubscribed(Observer);
        }
    }

    private sealed class SdkBindingPoisonTarget : ManagementObject
    {
        public override bool Equals(object value) => throw new InvalidOperationException("SDK target identity must not call provider equality.");
        public override int GetHashCode() => throw new InvalidOperationException("SDK target identity must not call provider hashing.");
        public override string ToString() => throw new InvalidOperationException("SDK target identity must not call provider text conversion.");
    }
}
