using System;
using System.Collections.Generic;
using System.Management;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.WmiInterop;

internal static partial class Program
{
    private static void RegisterWsabiWmiSingleReadBindingTests()
    {
        AddAsync("single read binding rejects missing plan before adding SDK subscriptions", async () =>
        {
            var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); int adds = 0, calls = 0;
            sdk.BeforeAdd = name => adds++;
            var binding = new WsabiWmiWindowsReadTrialBinding(SingleReadTarget(new object()), sdk, (observer, request) => calls++);
            var result = await PrepareSingleReadTest(null, binding, InvocationRequest(), gate);
            AssertSingleReadRejected(result, WsabiWmiSingleReadPreparationStatus.PlanMissing);
            Equal(0, adds); Equal(0, calls); Equal(0, gate.Calls);
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiWindowsReadTrialBinding(null, null, (observer, request) => { }));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiWindowsReadTrialBinding(null, sdk, null));
        });

        AddAsync("single read binding rejects changed target claims or identity before lower preparation and consumes its plan", async () =>
        {
            for (int shape = 0; shape < 4; shape++)
            {
                var token = new SingleReadPoisonIdentity(); var target = SingleReadTarget(token); var plan = SingleReadPlanCreate(target);
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); int adds = 0, calls = 0;
                sdk.BeforeAdd = name => adds++;
                var other = shape == 0 ? SingleReadTarget(new SingleReadPoisonIdentity())
                    : shape == 1 ? SingleReadTarget(token, active: false)
                    : shape == 2 ? SingleReadTarget(token, model: "940X3G") : null;
                var rejected = await PrepareSingleReadTest(plan, new WsabiWmiWindowsReadTrialBinding(other, sdk, (observer, request) => calls++), InvocationRequest(), gate);
                AssertSingleReadRejected(rejected, WsabiWmiSingleReadPreparationStatus.TargetMismatch);
                var retry = await PrepareSingleReadTest(plan, new WsabiWmiWindowsReadTrialBinding(target, sdk, (observer, request) => calls++), InvocationRequest(), gate);
                AssertSingleReadRejected(retry, WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
                Equal(0, adds); Equal(0, calls); Equal(0, gate.Calls);
            }
        });

        AddAsync("single read binding rejects malformed or differently bound templates before SDK registration", async () =>
        {
            byte[] reserved = BoundChannelRequest(); reserved[4] = 1;
            byte[] header = BoundChannelRequest(); header[0] ^= 255;
            foreach (var request in new[]
            {
                null,
                new WsabiWmiMethodRequest(2, 0x34, BoundChannelRequest()),
                new WsabiWmiMethodRequest(1, 0x34, reserved),
                new WsabiWmiMethodRequest(1, 0x34, header),
                new WsabiWmiMethodRequest(1, 0x35, BoundChannelRequest())
            })
            {
                var target = SingleReadTarget(new object()); var plan = SingleReadPlanCreate(target);
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); int adds = 0, calls = 0;
                sdk.BeforeAdd = name => adds++;
                var binding = new WsabiWmiWindowsReadTrialBinding(target, sdk, (observer, value) => calls++);
                AssertSingleReadRejected(await PrepareSingleReadTest(plan, binding, request, gate), WsabiWmiSingleReadPreparationStatus.RequestMismatch);
                AssertSingleReadRejected(await PrepareSingleReadTest(plan, binding, InvocationRequest(), gate), WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
                Equal(0, adds); Equal(0, calls); Equal(0, gate.Calls);
            }
        });

        AddAsync("single read bound run uses only its frozen request and retains structural result without hardware authority", async () =>
        {
            var target = SingleReadTarget(new object()); var plan = SingleReadPlanCreate(target);
            var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); int calls = 0, reports = 0;
            byte[] original = BoundChannelRequest(); var request = new WsabiWmiMethodRequest(1, 0x34, original);
            byte[] expected = request.Frame;
            ManagementBaseObject embedded; var root = WindowsOutputFixture(BoundChannelReply(), out embedded);
            var binding = new WsabiWmiWindowsReadTrialBinding(target, sdk, (observer, supplied) =>
            {
                calls++; Equal((uint)1, supplied.ObservedMethodId); Equal((ushort)0x34, supplied.FirmwareCommand);
                var actual = supplied.Frame; for (int i = 0; i < expected.Length; i++) Equal(expected[i], actual[i]);
                observer.EmitObjectReady(root); observer.EmitCompleted(ManagementStatus.NoError);
            });
            var prepared = await PrepareSingleReadTest(plan, binding, request, gate);
            Check(prepared.IsReady && prepared.RegistrationStatus == WsabiWmiWindowsPreparationStatus.Ready, "fixed synthetic request did not prepare");
            original[5] ^= 255; request.Frame[5] ^= 255;
            ((byte[])((IReadOnlyDictionary<string, object>)request.Arguments["inData"])["Bytes"])[5] ^= 255;
            var invocation = prepared.Invocation;
            Check(!invocation.CanInvokeMethods && !invocation.CanReadHardware && !invocation.CanWriteHardware, "pinned fixture became a hardware permission");
            BatteryThrows<ArgumentNullException>(() => invocation.RunAndCloseAsync(null));
            var result = await invocation.RunAndCloseAsync(value => reports++);
            Check(result.IsValidFrame && !result.IsHardwareObservation && !result.CanReadHardware && !result.CanWriteHardware,
                "fixed structural frame became a protection setting observation");
            Equal(1, calls); Equal(1, reports); Equal(1, gate.Calls); Equal(1, gate.LastLease.DisposeCalls);
            Equal(WsabiWmiWindowsCleanupStatus.Complete, await invocation.RequestCloseAsync());
            BatteryThrows<InvalidOperationException>(() => invocation.RunAndCloseAsync(value => reports++));
            Equal(1, calls); Equal(1, reports);
        });

        Add("single read handoff guard checks the frozen observer method command and every byte once", () =>
        {
            for (int fault = 0; fault < 5; fault++)
            {
                var sdk = new ManagementOperationObserver(); int calls = 0;
                var binding = new WsabiWmiWindowsReadTrialBinding(SingleReadTarget(new object()), sdk, (observer, request) => calls++);
                var guard = new WsabiWmiSingleReadDispatch(binding, InvocationRequest());
                byte[] modified = BoundChannelRequest(); modified[20] ^= 255;
                var invalid = fault == 0 ? null : fault == 1 ? new WsabiWmiMethodRequest(2, 0x34, BoundChannelRequest())
                    : fault == 2 ? new WsabiWmiMethodRequest(1, 0x35, BoundChannelRequest())
                    : fault == 3 ? new WsabiWmiMethodRequest(1, 0x34, modified) : InvocationRequest();
                BatteryThrows<InvalidOperationException>(() => guard.Invoke(fault == 4 ? new ManagementOperationObserver() : sdk, invalid));
                BatteryThrows<InvalidOperationException>(() => guard.Invoke(sdk, InvocationRequest()));
                Equal(0, calls);
            }
            var observerGood = new ManagementOperationObserver(); int goodCalls = 0;
            var good = new WsabiWmiSingleReadDispatch(new WsabiWmiWindowsReadTrialBinding(SingleReadTarget(new object()), observerGood,
                (observer, request) => goodCalls++), InvocationRequest());
            good.Invoke(observerGood, InvocationRequest());
            BatteryThrows<InvalidOperationException>(() => good.Invoke(observerGood, InvocationRequest()));
            Equal(1, goodCalls);
        });

        AddAsync("single read preparation preserves registration and cleanup failure without exposing run or rearming its plan", async () =>
        {
            foreach (bool cleanupFails in new[] { false, true })
            {
                var target = SingleReadTarget(new object()); var plan = SingleReadPlanCreate(target);
                var sdk = new ManagementOperationObserver(); var gate = new CooperativeTestGate(); int calls = 0;
                sdk.AfterAdd = name => { throw new InvalidOperationException("PRIVATE-SDK fixed binding registration error"); };
                if (cleanupFails) sdk.BeforeRemove = name => { throw new InvalidOperationException("PRIVATE-SDK fixed binding cleanup error"); };
                var binding = new WsabiWmiWindowsReadTrialBinding(target, sdk, (observer, request) => calls++);
                var result = await PrepareSingleReadTest(plan, binding, InvocationRequest(), gate);
                AssertSingleReadRejected(result, WsabiWmiSingleReadPreparationStatus.PreparationNotReady);
                Equal<WsabiWmiWindowsPreparationStatus?>(cleanupFails ? WsabiWmiWindowsPreparationStatus.CleanupFailed
                    : WsabiWmiWindowsPreparationStatus.RegistrationFailed, result.RegistrationStatus);
                AssertSingleReadRejected(await PrepareSingleReadTest(plan, binding, InvocationRequest(), gate), WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);
                Equal(0, calls); Equal(0, gate.Calls);
            }
        });
    }

    private static Task<WsabiWmiSingleReadPreparationResult> PrepareSingleReadTest(WsabiWmiSingleReadPlan plan,
        WsabiWmiWindowsReadTrialBinding binding, WsabiWmiMethodRequest request, CooperativeTestGate gate,
        CancellationToken token = default(CancellationToken), TimeSpan? responseTimeout = null)
        => WsabiWmiWindowsSingleReadPreparation.PrepareAsync(plan, binding, request, gate,
            TimeSpan.FromMilliseconds(200), responseTimeout ?? TimeSpan.FromSeconds(3), token);

    private static void AssertSingleReadRejected(WsabiWmiSingleReadPreparationResult result, WsabiWmiSingleReadPreparationStatus expected)
    {
        Equal(expected, result.Status); Check(!result.IsReady && result.Invocation == null, "rejected fixed-request policy exposed execution");
    }
}
