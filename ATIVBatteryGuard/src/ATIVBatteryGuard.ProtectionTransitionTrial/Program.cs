using System;
using System.Globalization;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Diagnostics;
using ATIVBatteryGuard.WmiInterop;

namespace ATIVBatteryGuard.ProtectionTransitionTrial
{
    // Separate explicitly-started tool. No arguments, arbitrary request input,
    // worker mode, automatic elevation, retry, rollback or ordinary-app caller.
    internal static class Program
    {
        private static readonly Task Never = new TaskCompletionSource<bool>().Task;
        private static object uncertainOwnershipRoot;

        [MTAThread]
        private static int Main(string[] args)
        {
            try { Console.OutputEncoding = new UTF8Encoding(false); } catch { }
            if (args.Length != 0 || Console.IsInputRedirected || Console.IsOutputRedirected)
            {
                Console.WriteLine("인수나 리디렉션을 받지 않습니다. 대화형 직접 실행만 허용합니다. 호출 없음.");
                return 2;
            }
            if (!IsWindows10X64())
            {
                Console.WriteLine("Windows 10 x64에서만 준비합니다. 호출 없음."); PauseAfterClose(); return 2;
            }
            ProcessElevationState elevation = ProcessElevationProbe.Read();
            var admission = WsabiWmiFixedReadAdmissionPolicy.Evaluate(elevation);
            Console.WriteLine("현재 토큰: " + elevation + " / 시작 조건: " + admission);
            if (admission != WsabiWmiFixedReadAdmissionStatus.Ready)
            {
                Console.WriteLine("토큰 조건을 확인하지 못했습니다. START·예약·WMI 준비·method 호출 없음.");
                Console.WriteLine("승인된 새 도구만 같은 계정에서 수동 관리자 실행하는 범위입니다. 자동 상승·권한 변경은 없습니다.");
                Console.WriteLine("다른 계정의 암호나 보안 우회가 필요하면 중단하세요. 과거 도구·예약은 건드리지 마세요.");
                PauseAfterClose(); return 2;
            }
            using (var stop = new CancellationTokenSource())
            {
                ConsoleCancelEventHandler onCancel = (sender, e) =>
                {
                    e.Cancel = true;
                    try { stop.Cancel(); } catch { }
                };
                try { Console.CancelKeyPress += onCancel; }
                catch { Console.WriteLine("중단 처리를 준비하지 못했습니다. 호출 없음."); return 2; }
                try
                {
                    Console.WriteLine("ATIV Battery Guard — " + WsabiWmiProtectionTransitionAttempt.Purpose);
                    Console.WriteLine("최초 보호 설정0→1 단발 시험입니다. 새 준비1회이며 실패해도 반복하지 않습니다.");
                    Console.WriteLine("대상: 기존 940X3G/930X3G · P05ACJ.128.140819.dg profile");
                    Console.WriteLine("새 사전 모드가0일 때만 설정1을 최대1회 요청합니다. 전후 읽기 포함 method 최대7회입니다.");
                    Console.WriteLine("기존 보호 모드·임계값이1/80/75로 바뀔 수 있습니다. 단순 조회·잠깐 켠 뒤 원복하는 시험이 아닙니다.");
                    Console.WriteLine("끄기·역방향1→0·이전 임계값 복원·자동rollback은 없습니다. 재부팅·절전 원복도 보장하지 않습니다.");
                    Console.WriteLine("handshake·삼성 DLL 초기화·재시도·다른 명령·직접 임계값 쓰기는 없습니다.");
                    Console.WriteLine("START 후 준비 실패도 이번1회를 소모합니다. 재실행·예약 삭제로 반복하지 마세요.");
                    Console.WriteLine("표시 시간 초과는 펌웨어 중단이 아닙니다. Pending/정리 대기 중 강제로 닫거나 재실행하지 마세요.");
                    Console.WriteLine("이 영향을 이해하고 이번1회 시험을 시작하려면 START를 입력하고 Enter를 누르세요.");
                    if (!string.Equals(Console.ReadLine(), "START", StringComparison.Ordinal) || stop.IsCancellationRequested)
                    { Console.WriteLine("시작하지 않았습니다. 호출 없음."); return 0; }
                    int result = RunApprovedTrialAsync(stop, elevation).GetAwaiter().GetResult();
                    PauseAfterClose(); return result;
                }
                catch
                {
                    // The post-start method below retains all uncertain exits.
                    Console.WriteLine("시작 절차를 완료하지 못했습니다. 원문 오류·경로는 출력하지 않습니다.");
                    return 2;
                }
                finally { Console.CancelKeyPress -= onCancel; }
            }
        }

        private static bool IsWindows10X64()
        {
            Version version = Environment.OSVersion.Version;
            return Environment.OSVersion.Platform == PlatformID.Win32NT && Environment.Is64BitProcess &&
                Environment.Is64BitOperatingSystem && version.Major == 10 && version.Minor == 0 &&
                version.Build >= 10240 && version.Build < 22000;
        }

        private static async Task<int> RunApprovedTrialAsync(CancellationTokenSource stop, ProcessElevationState elevation)
        {
            WsabiWmiOneShotReservationStatus reservation;
            try
            {
                string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                if (string.IsNullOrWhiteSpace(local) || !Path.IsPathRooted(local)) throw new InvalidOperationException();
                reservation = new WsabiWmiProtection0To1FileReservation(Path.Combine(local, "ATIVBatteryGuard", "Experiments")).TryClaim();
            }
            catch { reservation = WsabiWmiOneShotReservationStatus.Unavailable; }
            if (reservation != WsabiWmiOneShotReservationStatus.Claimed)
            {
                Console.WriteLine("새 시험의1회 예약: " + reservation + ". 호출 없음. 예약 변경·재시도하지 마세요."); return 2;
            }
            var journal = ProtectionTrialJournal.TryCreate(AppDomain.CurrentDomain.BaseDirectory);
            if (journal == null)
            { Console.WriteLine("결과 TXT를 준비하지 못했습니다. 호출 없음. 예약은 소모됐습니다."); return 2; }

            ProtectionPreparedTarget resources = null;
            WsabiWmiWindowsProtectionTrialSession session = null;
            bool runFailed = false;
            try
            {
                journal.Write("ATIV Battery Guard — " + WsabiWmiProtectionTransitionAttempt.Purpose);
                journal.Write("현재 토큰: " + elevation);
                journal.Write("새 목적의 영속1회 예약: Claimed");
                journal.Write("CallSabiFunction SDK진입 최대7 / 설정1 최대1 / 읽기 후보 최대6 / 초기화·handshake·재시도·fallback·역방향·복원0");
                journal.Write("기존 임계값을80/75로 덮어쓸 수 있습니다. 끄기·원복 기능과 재부팅 원복 보장은 없습니다.");
                journal.Write("실제 충전 제어: Unsupported. 저장 후보 일치는 충전기 적용·전기적 제한 성공이 아닙니다.");
                if (stop.IsCancellationRequested || journal.WriteFailed)
                { journal.Write("준비 전 중단: 호출 없음. 예약은 소모됐습니다."); return 2; }

                var preflight = await ProtectionTrialLifetime.AwaitWithNoticeAsync(
                    Task.Run(() => WindowsProtectionPreflight.Prepare()), Task.Delay(TimeSpan.FromSeconds(10)),
                    () => journal.Write("사전 검증 표시 시간 초과: 호출 전 작업의 실제 반환을 기다립니다. 강제 종료·재시도 없음."))
                    .ConfigureAwait(false);
                journal.Write("사전 검증: " + preflight.Status + " / 단계: " + preflight.Stage);
                journal.Write("열거 세부 단계: " + preflight.Substep + " / 오류 범주: " + preflight.Error);
                journal.Write("열거 정리 오류 관측: " + (preflight.CleanupFailed ? "Yes" : "No"));
                if (!preflight.IsReady)
                { journal.Write("firmware method 호출 없음. 준비 종료. 이번 시험을 반복하지 마세요."); return 2; }
                resources = preflight.Resources;
                if (stop.IsCancellationRequested || journal.WriteFailed)
                {
                    await CloseTargetOrHoldAsync(resources, session, journal).ConfigureAwait(false); resources = null;
                    journal.Write("준비 뒤 중단: firmware method 호출 없음. 예약은 소모됐습니다."); return 2;
                }

                WsabiWmiProtectionTransitionAttempt attempt;
                WsabiWmiProtectionAttemptIssue issue;
                bool created = WsabiWmiProtectionTransitionAttempt.TryCreate(resources.Facts, resources.Metadata, out attempt, out issue);
                journal.Write("고정7단계 요청 준비: " + issue);
                if (!created || stop.IsCancellationRequested || journal.WriteFailed)
                {
                    await CloseTargetOrHoldAsync(resources, session, journal).ConfigureAwait(false); resources = null;
                    journal.Write("호출 전 중단. 비교 내용·요청 원문은 기록하지 않습니다. 재시도 없음."); return 2;
                }
                // Prepare creates only the fixed-purpose session/factory; SDK
                // stage inputs and observers remain lazy until owner admission.
                session = WsabiWmiWindowsProtectionTrial.Prepare(attempt, resources.Target);
                journal.Write("고정 시험 준비 완료: 전체 owner 획득2초 / 전체 절차 표시10초 / 실제 종료·정리는 별도 대기.");
                if (stop.IsCancellationRequested || journal.WriteFailed)
                {
                    if (await session.RequestCloseAsync().ConfigureAwait(false) != WsabiWmiProtectionCleanupStatus.Complete)
                        await HoldUncertainAsync(resources, session, journal).ConfigureAwait(false);
                    await CloseTargetOrHoldAsync(resources, session, journal).ConfigureAwait(false); resources = null;
                    journal.Write("실행 전 중단. firmware method 호출 없음. 예약은 소모됐습니다."); return 2;
                }
                var activeSession = session;
                var joined = await ProtectionTrialLifetime.RunAndJoinAsync(
                    () => activeSession.RunAndCloseAsync(outcome =>
                    {
                        journal.Write("전체 표시 결과: " + outcome.Status);
                        journal.Write("owner 획득 판정(표시 시점): " + (outcome.GateStatus.HasValue ? outcome.GateStatus.Value.ToString() : "NotObserved"));
                        journal.Write("전이 판정(표시 시점): " + (outcome.LastDecisionStatus.HasValue ? outcome.LastDecisionStatus.Value.ToString() : "NotObserved"));
                        journal.Write("역할 입장 수: " + outcome.StartedStages.ToString(CultureInfo.InvariantCulture));
                        journal.Write("설정 역할 입장: " + (outcome.SetterRoleStarted ? "Yes" : "No"));
                        journal.Write("SDK 진입 수(표시 시점): " + activeSession.SdkEntries.ToString(CultureInfo.InvariantCulture));
                        journal.Write("설정 SDK 진입 수(표시 시점): " + activeSession.SetterEntries.ToString(CultureInfo.InvariantCulture));
                        journal.Write("마지막 SDK 준비: " + activeSession.LastPreparationStatus);
                        journal.Write("단계별 응답 판정(표시 시점):");
                        ProtectionTrialReport.WriteDiagnostics(journal, activeSession.GetStageDiagnostics());
                        ProtectionTrialReport.WriteSnapshot(journal, outcome.Snapshot);
                        if (outcome.SetterRoleStarted || activeSession.SetterEntries != 0)
                            journal.Write("설정 효과: Unknown. 입력echo·역할입장·SDK진입만으로 실제 변경 성공/미변경을 단정하지 않습니다.");
                        journal.Write("결과 표시는 실제 종료 보장이 아닙니다. 관련 정리가 끝날 때까지 기다립니다.");
                        if (journal.WriteFailed) { try { stop.Cancel(); } catch { } }
                    }, stop.Token), () => activeSession.RequestCloseAsync(),
                    () => journal.Write("시도 결과 확인 불가. 성공으로 해석하지 않고 관련 정리를 기다립니다."))
                    .ConfigureAwait(false);
                runFailed = joined.RunFailed;
                if (!joined.CleanupComplete) await HoldUncertainAsync(resources, session, journal).ConfigureAwait(false);
                journal.Write("SDK 진입 수(실제 종료 뒤): " + session.SdkEntries.ToString(CultureInfo.InvariantCulture));
                journal.Write("설정 SDK 진입 수(실제 종료 뒤): " + session.SetterEntries.ToString(CultureInfo.InvariantCulture));
                journal.Write("단계별 응답 판정(실제 종료 뒤):");
                ProtectionTrialReport.WriteDiagnostics(journal, session.GetStageDiagnostics());
                journal.Write("SDK 진입은 EC 처리 성공 횟수가 아닙니다.");
                await CloseTargetOrHoldAsync(resources, session, journal).ConfigureAwait(false); resources = null;
                journal.Write("관련 정리: Complete. 이번 시험 종료. 재실행·예약 변경·추가 호출을 하지 마세요.");
                journal.Write("기존 앱의 보호 조회/충전 제어 지원은 활성화하지 않습니다. 이 새 TXT만 후속 분석에 사용합니다.");
                if (journal.WriteFailed) Console.WriteLine("TXT 일부 저장 실패. 표시된 결과를 확인하세요. 호출 재시도 없음.");
                return runFailed ? 2 : 0;
            }
            catch
            {
                if (session != null)
                {
                    try
                    {
                        if (await session.RequestCloseAsync().ConfigureAwait(false) != WsabiWmiProtectionCleanupStatus.Complete)
                            await HoldUncertainAsync(resources, session, journal).ConfigureAwait(false);
                    }
                    catch { await HoldUncertainAsync(resources, session, journal).ConfigureAwait(false); }
                }
                await CloseTargetOrHoldAsync(resources, session, journal).ConfigureAwait(false); resources = null;
                journal.Write("준비/실행 결과 확인 불가. 원문 오류는 제외하며 재시도하지 않습니다.");
                return 2;
            }
            finally { journal.Dispose(); }
        }

        private static async Task CloseTargetOrHoldAsync(ProtectionPreparedTarget resources,
            WsabiWmiWindowsProtectionTrialSession session, ProtectionTrialJournal journal)
        {
            if (resources != null && !resources.CloseAfterActualCompletion())
                await HoldUncertainAsync(resources, session, journal).ConfigureAwait(false);
        }
        private static async Task HoldUncertainAsync(object resources, object session, ProtectionTrialJournal journal)
        {
            uncertainOwnershipRoot = new object[] { resources, session, journal };
            journal.Write("관련 종료·정리 확인 불가: Pending. 참조와 수명을 유지하며 추가 해제·호출·재시도 없이 기다립니다.");
            await Never.ConfigureAwait(false); GC.KeepAlive(uncertainOwnershipRoot);
        }
        private static void PauseAfterClose()
        {
            Console.WriteLine("종료된 결과를 확인한 뒤 Enter를 눌러 닫으세요.");
            try { Console.ReadLine(); } catch { }
        }
    }
}
