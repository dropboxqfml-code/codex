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
    // The public real-trial entry rejects opaque synthetic frames. Mechanical
    // binding tests use a separate internal entry and establish no read spec.
    private static void RegisterWsabiWmiReadTrialEntryTests()
    {
        AddAsync("public read trial rejects different valid opaque synthetic payloads before all lower work", async () =>
        {
            for (int variant = 0; variant < 3; variant++)
            {
                var fixture = new SdkBindingFixture();
                byte[] payload = BoundChannelPayload();
                if (variant == 1) payload[0] ^= 0xff;
                if (variant == 2) payload[payload.Length - 1] ^= 0xff;
                WsabiWmiMethodRequest request;
                Check(BinderCreate().TryPrepareRequest(0x34, payload, out request), "synthetic opaque fixture was rejected by framing");
                var rejected = await TrialEntryCall(fixture.Plan, fixture.Binding, request, fixture.Gate);
                TrialEntryAssertBlocked(rejected); fixture.AssertNoLowerWork();
                Check(fixture.Plan.MatchesCandidateScope && !fixture.Plan.IsHardwareObservation &&
                    !fixture.Plan.CanInvokeMethods && !fixture.Plan.CanReadHardware && !fixture.Plan.CanWriteHardware,
                    "an opaque frame or candidate match became hardware authority");
            }
        });

        AddAsync("public read trial rejects before SDK type routing getters and input metadata validation", async () =>
        {
            foreach (bool subclass in new[] { false, true })
            {
                var fixture = new SdkBindingFixture(subclass ? new SdkBindingPoisonTarget() : null);
                int touches = 0; SdkBindingPoisonAccess(fixture, () => Interlocked.Increment(ref touches));
                var rejected = await TrialEntryCall(fixture.Plan, fixture.Binding, InputPreparationRequest(), fixture.Gate);
                TrialEntryAssertBlocked(rejected);
                Equal(0, touches); fixture.AssertNoLowerWork();
            }
        });

        AddAsync("public read trial argument rejection precedes plan consumption and SDK or input access", async () =>
        {
            var fixture = new SdkBindingFixture(); int touches = 0;
            SdkBindingPoisonAccess(fixture, () => touches++);
            BatteryThrows<ArgumentNullException>(() => TrialEntryCall(null, null, InputPreparationRequest(), fixture.Gate));
            BatteryThrows<ArgumentNullException>(() => TrialEntryCall(fixture.Plan, fixture.Binding, InputPreparationRequest(), null));
            BatteryThrows<ArgumentOutOfRangeException>(() => WsabiWmiWindowsSingleReadPreparation.PrepareSdkAsync(
                fixture.Plan, fixture.Binding, InputPreparationRequest(), fixture.Gate, TimeSpan.Zero, TimeSpan.FromSeconds(3)));
            BatteryThrows<ArgumentOutOfRangeException>(() => WsabiWmiWindowsSingleReadPreparation.PrepareSdkAsync(
                fixture.Plan, fixture.Binding, InputPreparationRequest(), fixture.Gate, TimeSpan.FromMilliseconds(200), TimeSpan.Zero));
            Equal(0, touches); fixture.AssertNoLowerWork();
            var rejected = await TrialEntryCall(fixture.Plan, fixture.Binding, InputPreparationRequest(), fixture.Gate);
            TrialEntryAssertBlocked(rejected); Equal(0, touches); fixture.AssertNoLowerWork();
        });

        AddAsync("public read trial preserves plan facts request and actual identity errors ahead of cancellation and read unavailability", async () =>
        {
            using (var caller = new CancellationTokenSource())
            {
                caller.Cancel();
                for (int variant = 0; variant < 4; variant++)
                {
                    var fixture = new SdkBindingFixture(factsIdentity: variant == 3 ? new object() : null);
                    int touches = 0; SdkBindingPoisonAccess(fixture, () => touches++);
                    var plan = variant == 0 ? null : variant == 1 ? SingleReadPlanCreate(SingleReadTarget(new object())) : fixture.Plan;
                    var request = variant == 2 ? new WsabiWmiMethodRequest(2, 0x34, BoundChannelRequest()) : InputPreparationRequest();
                    var rejected = await TrialEntryCall(plan, fixture.Binding, request, fixture.Gate, caller.Token);
                    if (variant == 3) SdkBindingAssertRejected(rejected, WsabiWmiWindowsSdkBindingStatus.IdentityMismatch);
                    else
                    {
                        OwnedInputAssertRejected(rejected, variant == 0 ? WsabiWmiSingleReadPreparationStatus.PlanMissing
                            : variant == 1 ? WsabiWmiSingleReadPreparationStatus.TargetMismatch : WsabiWmiSingleReadPreparationStatus.RequestMismatch);
                        Equal<WsabiWmiWindowsSdkBindingStatus?>(null, rejected.SdkStatus);
                    }
                    Equal(0, touches); fixture.AssertNoLowerWork();
                }
            }
        });

        AddAsync("public read trial pre cancellation consumes both budgets without lower reads or ownership transfer", async () =>
        {
            using (var caller = new CancellationTokenSource())
            {
                var fixture = new SdkBindingFixture(); int touches = 0;
                SdkBindingPoisonAccess(fixture, () => touches++); caller.Cancel();
                var cancelled = await TrialEntryCall(fixture.Plan, fixture.Binding, InputPreparationRequest(), fixture.Gate, caller.Token);
                OwnedInputAssertRejected(cancelled, WsabiWmiSingleReadPreparationStatus.PreparationNotReady,
                    registration: WsabiWmiWindowsPreparationStatus.Cancelled);
                Equal<WsabiWmiWindowsSdkBindingStatus?>(null, cancelled.SdkStatus);
                var samePlan = await TrialEntryCall(fixture.Plan, fixture.Binding, InputPreparationRequest(), fixture.Gate);
                OwnedInputAssertRejected(samePlan, WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
                var sameBundle = await TrialEntryCall(SingleReadPlanCreate(fixture.Facts), fixture.Binding, InputPreparationRequest(), fixture.Gate);
                SdkBindingAssertRejected(sameBundle, WsabiWmiWindowsSdkBindingStatus.BindingAlreadyUsed);
                var internalRetry = await SdkBindingCall(SingleReadPlanCreate(fixture.Facts), fixture.Binding, InputPreparationRequest(), fixture.Gate);
                SdkBindingAssertRejected(internalRetry, WsabiWmiWindowsSdkBindingStatus.BindingAlreadyUsed);
                Equal(0, touches); fixture.AssertNoLowerWork();
            }
        });

        AddAsync("public read trial rejection cannot rearm the same plan or SDK bundle through the internal mechanical entry", async () =>
        {
            var fixture = new SdkBindingFixture(); int touches = 0;
            SdkBindingPoisonAccess(fixture, () => touches++);
            TrialEntryAssertBlocked(await TrialEntryCall(fixture.Plan, fixture.Binding, InputPreparationRequest(), fixture.Gate));
            var replacementBundle = new WsabiWmiWindowsSdkBinding(fixture.Facts, fixture.Target,
                new ManagementOperationObserver(), fixture.Pair.Parameters, fixture.Pair.Buffer);
            var samePlan = await TrialEntryCall(fixture.Plan, replacementBundle, InputPreparationRequest(), fixture.Gate);
            OwnedInputAssertRejected(samePlan, WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
            var internalPlan = await SdkBindingCall(fixture.Plan, fixture.Binding, InputPreparationRequest(), fixture.Gate);
            OwnedInputAssertRejected(internalPlan, WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
            var internalBundle = await SdkBindingCall(SingleReadPlanCreate(fixture.Facts), fixture.Binding, InputPreparationRequest(), fixture.Gate);
            SdkBindingAssertRejected(internalBundle, WsabiWmiWindowsSdkBindingStatus.BindingAlreadyUsed);
            var publicBundle = await TrialEntryCall(SingleReadPlanCreate(fixture.Facts), fixture.Binding, InputPreparationRequest(), fixture.Gate);
            SdkBindingAssertRejected(publicBundle, WsabiWmiWindowsSdkBindingStatus.BindingAlreadyUsed);
            Equal(0, touches); fixture.AssertNoLowerWork();
        });

        AddAsync("public read trial leaves supplied inputs unclaimed and exposes no approval flag or public mechanical SDK entry", async () =>
        {
            var fixture = new SdkBindingFixture(); int touches = 0;
            SdkBindingPoisonAccess(fixture, () => touches++);
            TrialEntryAssertBlocked(await TrialEntryCall(fixture.Plan, fixture.Binding, InputPreparationRequest(), fixture.Gate));
            Equal(0, touches); fixture.AssertNoLowerWork();
            InputPreparationResetSdk(fixture.Pair);
            Equal(WsabiWmiWindowsInputPreparationStatus.Populated,
                WsabiWmiWindowsInputPreparation.Populate(fixture.Plan, InputPreparationRequest(), fixture.Pair.Parameters, fixture.Pair.Buffer));
            InputPreparationAssertBorrowed(fixture.Pair);
            var entryType = typeof(WsabiWmiWindowsSingleReadPreparation);
            var publicEntries = entryType.GetMethods(BindingFlags.Public | BindingFlags.Static).Where(method => method.Name == "PrepareSdkAsync").ToArray();
            Equal(1, publicEntries.Length);
            Check(publicEntries[0].GetParameters().All(parameter => parameter.ParameterType != typeof(bool)), "public trial entry exposes an approval bypass flag");
            Check(entryType.GetMethod("PrepareSdkBindingAsync", BindingFlags.Public | BindingFlags.Static) == null,
                "mechanical SDK binding entry became public");
        });

        AddAsync("concurrent public read trial requests publish one blocked result and reject the other consumed plan", async () =>
        {
            using (var start = new ManualResetEventSlim())
            {
                var fixture = new SdkBindingFixture(); int touches = 0;
                SdkBindingPoisonAccess(fixture, () => Interlocked.Increment(ref touches));
                Func<Task<WsabiWmiSingleReadPreparationResult>> enter = () => Task.Run(() =>
                {
                    if (!start.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("Synthetic entry gate was not released.");
                    return TrialEntryCall(fixture.Plan, fixture.Binding, InputPreparationRequest(), fixture.Gate);
                });
                var first = enter(); var second = enter(); var both = Task.WhenAll(first, second);
                try
                {
                    start.Set(); await CooperativeAwait(both);
                    var results = await both;
                    Equal(1, results.Count(result => result.Status == WsabiWmiSingleReadPreparationStatus.ReadSpecificationUnavailable));
                    Equal(1, results.Count(result => result.Status == WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed));
                    foreach (var result in results)
                    {
                        if (result.Status == WsabiWmiSingleReadPreparationStatus.ReadSpecificationUnavailable) TrialEntryAssertBlocked(result);
                        else
                        {
                            OwnedInputAssertRejected(result, WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
                            Equal<WsabiWmiWindowsSdkBindingStatus?>(null, result.SdkStatus);
                        }
                    }
                    Equal(0, touches); fixture.AssertNoLowerWork();
                }
                finally { start.Set(); await InvocationSettled(both); }
            }
        });
    }

    private static Task<WsabiWmiSingleReadPreparationResult> TrialEntryCall(WsabiWmiSingleReadPlan plan,
        WsabiWmiWindowsSdkBinding binding, WsabiWmiMethodRequest request, IWsabiWmiExchangeGate gate,
        CancellationToken token = default(CancellationToken))
        => WsabiWmiWindowsSingleReadPreparation.PrepareSdkAsync(plan, binding, request, gate,
            TimeSpan.FromMilliseconds(200), TimeSpan.FromSeconds(3), token);

    private static void TrialEntryAssertBlocked(WsabiWmiSingleReadPreparationResult result)
    {
        OwnedInputAssertRejected(result, WsabiWmiSingleReadPreparationStatus.ReadSpecificationUnavailable);
        Equal<WsabiWmiWindowsSdkBindingStatus?>(null, result.SdkStatus);
    }
}
