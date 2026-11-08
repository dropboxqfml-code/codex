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
    // Fixed A preparation is compiled with the existing test-only SDK stand-ins.
    // No SDK runtime, target discovery, OEM call or device reservation executes.
    private static void RegisterWsabiWmiFixedReadPreparationTests()
    {
        Add("fixed A SDK entry takes a sealed attempt without arbitrary request or wait arguments", () =>
        {
            var method = typeof(WsabiWmiWindowsSingleReadPreparation).GetMethod("PrepareFixedReadAAsync",
                BindingFlags.Static | BindingFlags.Public);
            Check(method != null, "fixed A entry missing");
            var parameters = method.GetParameters();
            Equal(5, parameters.Length);
            Equal(typeof(WsabiWmiFixedModeReadAttempt), parameters[2].ParameterType);
            Check(parameters[2].ParameterType.IsSealed, "fixed request type is extensible");
            foreach (var parameter in parameters)
                Check(parameter.ParameterType != typeof(WsabiWmiMethodRequest) &&
                    parameter.ParameterType != typeof(byte[]) && parameter.ParameterType != typeof(TimeSpan) &&
                    !typeof(Delegate).IsAssignableFrom(parameter.ParameterType), "fixed entry permits caller-selected request or dispatch");
        });

        AddAsync("fixed A missing attempt and local argument errors perform no lower work", async () =>
        {
            var fixture = new SdkBindingFixture(); int touches = 0;
            SdkBindingPoisonAccess(fixture, () => touches++);
            var missing = await FixedReadPrepare(fixture, null);
            OwnedInputAssertRejected(missing, WsabiWmiSingleReadPreparationStatus.RequestMismatch);
            var attempt = FixedReadAttemptCreate();
            BatteryThrows<ArgumentNullException>(() => WsabiWmiWindowsSingleReadPreparation.PrepareFixedReadAAsync(
                fixture.Plan, null, attempt, fixture.Gate));
            BatteryThrows<ArgumentNullException>(() => WsabiWmiWindowsSingleReadPreparation.PrepareFixedReadAAsync(
                fixture.Plan, fixture.Binding, attempt, null));
            Equal(0, touches); fixture.AssertNoLowerWork();
            SdkBindingResetAccess(fixture);
            var ready = await SdkLifeReady(FixedReadPrepare(fixture, attempt));
            try { Equal(0, fixture.Target.InvokeCalls); Equal(0, fixture.Gate.Calls); }
            finally { await CooperativeAwait(ready.Invocation.RequestCloseAsync()); }
            SdkLifeAssertPairDisposes(fixture.Pair, 1); SdkLifeAssertBorrowedTarget(fixture.Target);
        });

        AddAsync("generic SDK entry stays blocked even for bytes exposed by a fixed A attempt", async () =>
        {
            var fixture = new SdkBindingFixture(); var attempt = FixedReadAttemptCreate(); int touches = 0;
            SdkBindingPoisonAccess(fixture, () => touches++);
            var rejected = await WsabiWmiWindowsSingleReadPreparation.PrepareSdkAsync(fixture.Plan,
                fixture.Binding, attempt.Request, fixture.Gate, TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(10));
            TrialEntryAssertBlocked(rejected); Equal(0, touches); fixture.AssertNoLowerWork();
        });

        AddAsync("fixed A attempt plan and SDK bundle remain consumed after pre cancellation", async () =>
        {
            using (var caller = new CancellationTokenSource())
            {
                var fixture = new SdkBindingFixture(); var attempt = FixedReadAttemptCreate();
                int touches = 0; SdkBindingPoisonAccess(fixture, () => touches++); caller.Cancel();
                var cancelled = await FixedReadPrepare(fixture, attempt, caller.Token);
                OwnedInputAssertRejected(cancelled, WsabiWmiSingleReadPreparationStatus.PreparationNotReady,
                    registration: WsabiWmiWindowsPreparationStatus.Cancelled);
                var fresh = new SdkBindingFixture(); SdkBindingPoisonAccess(fresh, () => touches++);
                var attemptRetry = await FixedReadPrepare(fresh, attempt);
                OwnedInputAssertRejected(attemptRetry, WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
                var planRetry = await FixedReadPrepare(fixture, FixedReadAttemptCreate());
                OwnedInputAssertRejected(planRetry, WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
                var bindingRetry = await WsabiWmiWindowsSingleReadPreparation.PrepareFixedReadAAsync(
                    SingleReadPlanCreate(fixture.Facts), fixture.Binding, FixedReadAttemptCreate(), fixture.Gate);
                SdkBindingAssertRejected(bindingRetry, WsabiWmiWindowsSdkBindingStatus.BindingAlreadyUsed);
                Equal(0, touches); fixture.AssertNoLowerWork(); fresh.AssertNoLowerWork();
            }
        });

        AddAsync("fixed A target fact and actual SDK type rejection precede input ownership", async () =>
        {
            for (int variant = 0; variant < 4; variant++)
            {
                var fixture = variant == 2 ? new SdkBindingFixture(new SdkBindingPoisonTarget())
                    : new SdkBindingFixture(factsIdentity: variant == 3 ? new object() : null);
                int touches = 0; SdkBindingPoisonAccess(fixture, () => touches++);
                var plan = variant == 0 ? null : variant == 1 ? SingleReadPlanCreate(SingleReadTarget(new object())) : fixture.Plan;
                var rejected = await WsabiWmiWindowsSingleReadPreparation.PrepareFixedReadAAsync(
                    plan, fixture.Binding, FixedReadAttemptCreate(), fixture.Gate);
                if (variant >= 2) SdkBindingAssertRejected(rejected, variant == 2
                    ? WsabiWmiWindowsSdkBindingStatus.UnsupportedTargetType : WsabiWmiWindowsSdkBindingStatus.IdentityMismatch);
                else OwnedInputAssertRejected(rejected, variant == 0 ? WsabiWmiSingleReadPreparationStatus.PlanMissing
                    : WsabiWmiSingleReadPreparationStatus.TargetMismatch);
                Equal(0, touches); fixture.AssertNoLowerWork();
            }
        });

        AddAsync("fixed A prepares its immutable request and dispatches the same target input and observer once", async () =>
        {
            var fixture = new SdkBindingFixture(); var attempt = FixedReadAttemptCreate();
            byte[] expected = attempt.Request.Frame; byte[] returned = attempt.Request.Frame; returned[0] ^= 1;
            fixture.Target.OnInvoke = (observer, method, input, options) =>
            {
                Check(ReferenceEquals(observer, fixture.Observer) && ReferenceEquals(input, fixture.Pair.Parameters), "fixed A substituted its SDK bundle");
                Equal("CallSabiFunction", method); Check(options != null, "fixed A omitted method options");
                Check(((byte[])fixture.Pair.Bytes.Value).SequenceEqual(expected), "fixed A input differs from its immutable request");
                observer.EmitCompleted(ManagementStatus.AccessDenied); // Applicable stand-in final only.
            };
            var prepared = await SdkLifeReady(FixedReadPrepare(fixture, attempt));
            Equal(0, fixture.Target.InvokeCalls); Equal(0, fixture.Gate.Calls);
            var run = prepared.Invocation.RunAndCloseAsync(value => { });
            try
            {
                await CooperativeAwait(run); var result = await run;
                Equal(WsabiWmiFrameExchangeStatus.ReplyReceived, result.Status);
                Equal(WsabiWmiReplyStatus.ApiNotSuccessful, result.Reply.Status);
                Equal(1, fixture.Target.InvokeCalls); Equal(1, fixture.Gate.Calls);
                Equal(TimeSpan.FromSeconds(2), fixture.Gate.LastTimeout);
                SdkLifeAssertPairDisposes(fixture.Pair, 1); SdkLifeAssertBorrowedTarget(fixture.Target);
                SdkLifeAssertUnsubscribed(fixture.Observer);
                BatteryThrows<InvalidOperationException>(() => prepared.Invocation.RunAndCloseAsync(value => { }));
                var retry = await FixedReadPrepare(new SdkBindingFixture(), attempt);
                OwnedInputAssertRejected(retry, WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
            }
            finally
            {
                if (fixture.Target.InvokeCalls != 0) fixture.Observer.EmitCompleted(ManagementStatus.AccessDenied); // Fake cleanup only.
                try { await CooperativeAwait(prepared.Invocation.RequestCloseAsync()); }
                finally { await CooperativeAwait(run); }
            }
        });

        AddAsync("fixed A gate refusal performs no method and closes its unused input and registration", async () =>
        {
            var fixture = new SdkBindingFixture();
            fixture.Gate.Handler = (timeout, stop) => new WsabiWmiExchangeGateAttempt(WsabiWmiExchangeGateStatus.TimedOut);
            var prepared = await SdkLifeReady(FixedReadPrepare(fixture, FixedReadAttemptCreate()));
            var run = prepared.Invocation.RunAndCloseAsync(value => { });
            try
            {
                await CooperativeAwait(run);
                AssertFrameExchangeFailure(await run, WsabiWmiFrameExchangeStatus.TransportFailure);
                Equal(1, fixture.Gate.Calls); Equal(0, fixture.Target.InvokeCalls);
                SdkLifeAssertPairDisposes(fixture.Pair, 1); SdkLifeAssertBorrowedTarget(fixture.Target);
                SdkLifeAssertUnsubscribed(fixture.Observer);
            }
            finally
            {
                try { await CooperativeAwait(prepared.Invocation.RequestCloseAsync()); }
                finally { await CooperativeAwait(run); }
            }
        });

        AddAsync("fixed A cancellation status and caller stop retain ownership until an applicable stand in final", async () =>
        {
            using (var caller = new CancellationTokenSource())
            {
                var fixture = new SdkBindingFixture(); var entered = CooperativeCompletion(); var published = CooperativeCompletion();
                var output = new ManagementBaseObject { OnGetProperties = () => throw new InvalidOperationException("PRIVATE-SDK cancelled fixed A output") };
                WsabiWmiFrameExchangeResult shown = null; int reports = 0;
                fixture.Target.OnInvoke = (observer, method, input, options) =>
                {
                    observer.EmitObjectReady(output); entered.TrySetResult(true);
                };
                var prepared = await SdkLifeReady(FixedReadPrepare(fixture, FixedReadAttemptCreate()));
                var invocation = prepared.Invocation;
                var run = invocation.RunAndCloseAsync(value => { shown = value; reports++; published.TrySetResult(true); }, caller.Token);
                try
                {
                    await CooperativeAwait(entered.Task);
                    fixture.Observer.EmitCompleted(ManagementStatus.CallCanceled); caller.Cancel();
                    await CooperativeAwait(published.Task);
                    AssertFrameExchangeFailure(shown, WsabiWmiFrameExchangeStatus.Cancelled);
                    var close = invocation.RequestCloseAsync();
                    Check(!run.IsCompleted && !close.IsCompleted && fixture.Gate.LastLease.IsHeld, "fixed A cancellation ended unknown ownership");
                    Equal(0, output.ConcreteDisposeCalls); SdkLifeAssertPairDisposes(fixture.Pair, 0);
                    Equal(1, fixture.Observer.ObjectReadySubscriberCount); Equal(1, fixture.Observer.CompletedSubscriberCount);
                    fixture.Observer.EmitCompleted(ManagementStatus.CallCanceled);
                    Check(!run.IsCompleted && !close.IsCompleted, "repeated fixed A cancellation invented final completion");
                    fixture.Observer.EmitCompleted(ManagementStatus.AccessDenied); // Stand-in terminal for test cleanup, not SDK evidence.
                    await CooperativeAwait(run);
                    Check(ReferenceEquals(shown, await run), "fixed A late cleanup replaced the cancelled report");
                    Equal(1, reports); Equal(1, fixture.Target.InvokeCalls); Equal(1, output.ConcreteDisposeCalls);
                    Equal(WsabiWmiWindowsCleanupStatus.Complete, await close);
                    SdkLifeAssertPairDisposes(fixture.Pair, 1); SdkLifeAssertBorrowedTarget(fixture.Target);
                    SdkLifeAssertUnsubscribed(fixture.Observer);
                }
                finally
                {
                    if (fixture.Target.InvokeCalls != 0) fixture.Observer.EmitCompleted(ManagementStatus.AccessDenied); // Synthetic fake cleanup only.
                    try { await CooperativeAwait(invocation.RequestCloseAsync()); }
                    finally { await CooperativeAwait(run); }
                }
            }
        });
    }

    private static Task<WsabiWmiSingleReadPreparationResult> FixedReadPrepare(SdkBindingFixture fixture,
        WsabiWmiFixedModeReadAttempt attempt, CancellationToken token = default(CancellationToken))
        => WsabiWmiWindowsSingleReadPreparation.PrepareFixedReadAAsync(fixture.Plan, fixture.Binding,
            attempt, fixture.Gate, token);

    private static WsabiWmiFixedModeReadAttempt FixedReadAttemptCreate()
    {
        WsabiWmiFixedModeReadAttempt attempt;
        var status = WsabiWmiFixedModeReadAttempt.TryCreateWithRandom(bytes =>
        {
            for (int index = 0; index < bytes.Length; index++) bytes[index] = (byte)(index + 1);
        }, out attempt);
        Equal(WsabiWmiFixedReadCreationStatus.Created, status);
        Check(attempt != null, "deterministic fixed A attempt missing");
        return attempt;
    }
}
