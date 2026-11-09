using System;
using System.IO.Pipes;
using System.Security.Principal;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Diagnostics;
using ATIVBatteryGuard.ProtectionTransitionTrial;
using ATIVBatteryGuard.WmiInterop;

namespace ATIVBatteryGuard.ManualProtectionHelper
{
    internal static class Program
    {
        private static readonly Task Never = new TaskCompletionSource<bool>().Task;
        private static object uncertainOwnershipRoot;

        [MTAThread]
        private static int Main(string[] args)
        {
            ManualProtectionContext context;
            if (!ManualHelperAdmission.TryParse(args, out context))
            {
                Notice("이 도구는 ATIV Battery Guard의 수동 제어 버튼에서만 실행합니다. 장치 호출은 없습니다.");
                return 2;
            }
            if (!IsWindows10X64() || ProcessElevationProbe.Read() != ProcessElevationState.Elevated)
            {
                Notice("현재 Windows10 x64·관리자 토큰 조건을 확인하지 못했습니다. 장치 호출은 없습니다.");
                return 2;
            }
            try { return RunAsync(context).GetAwaiter().GetResult(); }
            catch
            {
                // Execution after a durable claim handles uncertain lifetime
                // inside ExecuteAndJoinAsync; this is only pre-admission/IPC.
                Notice("수동 제어 연결을 완료하지 못했습니다. 기존 작업·예약을 변경하거나 강제로 재시도하지 마세요.");
                return 2;
            }
        }

        private static bool IsWindows10X64()
        {
            Version value = Environment.OSVersion.Version;
            return Environment.OSVersion.Platform == PlatformID.Win32NT && Environment.Is64BitOperatingSystem &&
                Environment.Is64BitProcess && value.Major == 10 && value.Minor == 0 && value.Build >= 10240 && value.Build < 22000;
        }

        private static async Task<int> RunAsync(ManualProtectionContext context)
        {
            // Identification prevents this elevated client from delegating an
            // impersonation-capable administrator token to the ordinary GUI.
            using (var pipe = new NamedPipeClientStream(".", ManualHelperAdmission.PipePrefix + context.JobId,
                PipeDirection.InOut, PipeOptions.Asynchronous, TokenImpersonationLevel.Identification))
            {
                await pipe.ConnectAsync(15000).ConfigureAwait(false);
                var channel = new ManualHelperPipe(pipe, context);
                if (!await channel.SendAsync(ManualProtectionWireMessage.Hello(context)).ConfigureAwait(false)) return 2;
                if (await channel.ReadExpectedAsync(ManualProtectionWireKind.Request, TimeSpan.FromSeconds(20)).ConfigureAwait(false) == null)
                    return 2; // No Execute request: no lease, preflight or SDK.

                if (!Confirm(context.Operation))
                    return await DeliverAsync(context, channel,
                        ManualProtectionResult.Failure(context.Operation, ManualProtectionStatus.Cancelled), null).ConfigureAwait(false);

                if (!await channel.SendAsync(ManualProtectionWireMessage.Progress(context, ManualProtectionPhase.Preparing)).ConfigureAwait(false))
                    return 2; // Lost GUI before new lease or firmware work.

                ManualProtectionOperationLease lease;
                var claimed = ManualProtectionOperationLease.TryClaim(context, out lease);
                if (claimed != ManualProtectionLeaseStatus.Claimed)
                    return await DeliverAsync(context, channel,
                        ManualProtectionResult.Failure(context.Operation,
                            claimed == ManualProtectionLeaseStatus.Busy ? ManualProtectionStatus.Busy : ManualProtectionStatus.Rejected), null).ConfigureAwait(false);

                using (lease)
                {
                    channel.StartAcknowledgmentMonitor();
                    // This scope never exits while an invocation or related
                    // input/output/target lifetime remains unconfirmed.
                    var result = await ExecuteAndJoinAsync(context, channel, lease).ConfigureAwait(false);
                    return await DeliverAsync(context, channel, result, lease).ConfigureAwait(false);
                }
            }
        }

        private static async Task<ManualProtectionResult> ExecuteAndJoinAsync(ManualProtectionContext context,
            ManualHelperPipe channel, ManualProtectionOperationLease lease)
        {
            ProtectionPreparedTarget target = null;
            WsabiWmiWindowsManualProtectionSession session = null;
            bool profileValidated = false;
            try
            {
                channel.Notice(ManualProtectionPhase.Preparing);
                var preflight = await ManualHelperLifetime.AwaitWithNoticeAsync(
                    Task.Run(() => WindowsProtectionPreflight.Prepare()), Task.Delay(TimeSpan.FromSeconds(10)),
                    () => channel.Notice(ManualProtectionPhase.WaitingForActualCompletion)).ConfigureAwait(false);
                if (!preflight.IsReady)
                {
                    if (preflight.CleanupFailed)
                        await HoldUncertainAsync(context, channel, lease, target, session).ConfigureAwait(false);
                    return ManualProtectionResult.Failure(context.Operation,
                        preflight.Status == ProtectionPreflightStatus.UnsupportedPlatform || preflight.Status == ProtectionPreflightStatus.DeviceMismatch
                            ? ManualProtectionStatus.Unsupported : ManualProtectionStatus.PreflightFailed);
                }
                target = preflight.Resources;
                profileValidated = true;
                if (channel.HasFailed)
                {
                    await CloseTargetOrHoldAsync(context, channel, lease, target, session).ConfigureAwait(false);
                    target = null;
                    return ManualProtectionResult.Failure(context.Operation, ManualProtectionStatus.Unknown, true, true);
                }
                ManualProtectionAttempt attempt;
                ManualProtectionAttemptIssue issue;
                if (!ManualProtectionAttempt.TryCreate(context.Operation, target.Facts, target.Metadata, out attempt, out issue))
                {
                    await CloseTargetOrHoldAsync(context, channel, lease, target, session).ConfigureAwait(false);
                    target = null;
                    return ManualProtectionResult.Failure(context.Operation, ManualProtectionStatus.Rejected, true, true);
                }
                session = WsabiWmiWindowsManualProtection.Prepare(attempt, target.Target);
                channel.Notice(ManualProtectionPhase.Running);
                ManualProtectionOutcome outcome = null;
                try
                {
                    outcome = await session.RunAndCloseAsync(value =>
                    {
                        // Progress only. Even timeout/Unknown cannot publish a
                        // terminal result before actual lifetime is joined.
                        if (value.Status == ManualProtectionStatus.TimedOut || value.Status == ManualProtectionStatus.Unknown)
                            channel.Notice(ManualProtectionPhase.WaitingForActualCompletion);
                    }, channel.DisconnectedToken).ConfigureAwait(false);
                }
                catch { }
                if (!await ManualHelperLifetime.JoinActualCloseAsync(() => session.RequestCloseAsync()).ConfigureAwait(false) || session.IsCompletionUnknown)
                    await HoldUncertainAsync(context, channel, lease, target, session).ConfigureAwait(false);
                await CloseTargetOrHoldAsync(context, channel, lease, target, session).ConfigureAwait(false);
                target = null;

                if (outcome == null)
                    return ManualProtectionResult.Failure(context.Operation, ManualProtectionStatus.Unknown, true, true,
                        session.SdkEntries, session.SetterEntries);
                return ManualHelperResultFactory.FromCompleted(context.Operation, outcome.Status,
                    session.SdkEntries, session.SetterEntries, outcome.ReadCandidates,
                    outcome.PreModeCandidate, outcome.ModeCandidate, outcome.UpperCandidate, outcome.LowerCandidate);
            }
            catch
            {
                if (session != null &&
                    (!await ManualHelperLifetime.JoinActualCloseAsync(() => session.RequestCloseAsync()).ConfigureAwait(false) || session.IsCompletionUnknown))
                    await HoldUncertainAsync(context, channel, lease, target, session).ConfigureAwait(false);
                await CloseTargetOrHoldAsync(context, channel, lease, target, session).ConfigureAwait(false);
                // A serialization/shape/counter disagreement must not clear a
                // pending record or fabricate accepted candidates/counters.
                if (session != null)
                    await HoldUncertainAsync(context, channel, lease, target, session).ConfigureAwait(false);
                return ManualProtectionResult.Failure(context.Operation,
                    profileValidated ? ManualProtectionStatus.Rejected : ManualProtectionStatus.PreflightFailed,
                    true, profileValidated);
            }
        }

        private static async Task CloseTargetOrHoldAsync(ManualProtectionContext context, ManualHelperPipe channel,
            ManualProtectionOperationLease lease, ProtectionPreparedTarget target, WsabiWmiWindowsManualProtectionSession session)
        {
            if (target != null && !target.CloseAfterActualCompletion())
                await HoldUncertainAsync(context, channel, lease, target, session).ConfigureAwait(false);
        }

        private static async Task HoldUncertainAsync(ManualProtectionContext context, ManualHelperPipe channel,
            ManualProtectionOperationLease lease, object target, object session)
        {
            uncertainOwnershipRoot = new object[] { context, channel, lease, target, session };
            channel.Notice(ManualProtectionPhase.WaitingForActualCompletion);
            await Never.ConfigureAwait(false);
            GC.KeepAlive(uncertainOwnershipRoot);
        }

        private static async Task<int> DeliverAsync(ManualProtectionContext context, ManualHelperPipe channel,
            ManualProtectionResult result, ManualProtectionOperationLease lease)
        {
            if (result == null || !result.CleanupComplete) return 2;
            await channel.DrainNoticesAsync().ConfigureAwait(false);
            if (channel.HasFailed) return 2;
            channel.BeginTerminalResult();
            if (lease == null) channel.StartAcknowledgmentMonitor();
            if (!await channel.SendAsync(ManualProtectionWireMessage.ForResult(context, result)).ConfigureAwait(false)) return 2;
            if (!await channel.WaitForAcknowledgmentAsync().ConfigureAwait(false)) return 2;
            // Only this owner's new application record is cleared, after
            // actual closure and a matching GUI acknowledgment. No old trial.
            if (lease != null && !lease.CompleteAndRelease(result.CleanupComplete, true)) return 2;
            if (!await channel.SendAsync(ManualProtectionWireMessage.Released(context)).ConfigureAwait(false)) return 2;
            return result.IsSuccess || result.Status == ManualProtectionStatus.Cancelled ? 0 : 2;
        }

        private static bool Confirm(ManualProtectionOperation operation)
        {
            try
            {
                return MessageBox.Show(ManualHelperAdmission.Confirmation(operation),
                    "ATIV Battery Guard · " + ManualProtectionResult.OperationText(operation),
                    MessageBoxButtons.YesNo, MessageBoxIcon.Information, MessageBoxDefaultButton.Button2) == DialogResult.Yes;
            }
            catch { return false; }
        }

        private static void Notice(string text)
        { try { MessageBox.Show(text, "ATIV Battery Guard", MessageBoxButtons.OK, MessageBoxIcon.Information); } catch { } }
    }
}
