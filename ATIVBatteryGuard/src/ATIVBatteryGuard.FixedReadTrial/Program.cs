using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.WmiInterop;

namespace ATIVBatteryGuard.FixedReadTrial
{
    // Separate manual tool: the normal application never launches this entry.
    // No command, address, server, payload, marker path or worker switch exists.
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
                Console.WriteLine("이 도구는 인수나 리디렉션을 받지 않습니다. 대화형 직접 실행만 허용합니다. 호출 없음.");
                return 2;
            }
            if (!IsWindows10X64())
            {
                Console.WriteLine("Windows 10 x64에서만 준비합니다. 호출 없음.");
                PauseAfterClose();
                return 2;
            }

            using (var stop = new CancellationTokenSource())
            {
                ConsoleCancelEventHandler onCancel = (sender, e) =>
                {
                    e.Cancel = true;
                    try { stop.Cancel(); } catch { }
                    // This local intent never calls SDK Cancel or ends Main.
                };
                try { Console.CancelKeyPress += onCancel; }
                catch { Console.WriteLine("안전한 중단 처리를 준비하지 못했습니다. 호출 없음."); return 2; }
                try
                {
                    Console.WriteLine("ATIV Battery Guard — 보호 저장값 단발 조회 A");
                    Console.WriteLine("대상: 기존 940X3G/930X3G · P05ACJ.128.140819.dg profile");
                    Console.WriteLine("설정 변경·초기화·재시도 없음. 고정 읽기 WMI method 최대 1회, 저장 byte 샘플 0~1회.");
                    Console.WriteLine("통신 입력과 mailbox 교환은 있으며 충전 제어는 하지 않습니다.");
                    Console.WriteLine("시작 후 준비 실패도 이 시험의 1회를 소모합니다. 관리자 재실행·예약 삭제로 반복하지 마세요.");
                    Console.WriteLine("시간 초과는 펌웨어 중단이 아닙니다. 정리 완료 전에는 창을 강제로 닫지 마세요.");
                    Console.WriteLine("이 한 번의 조회를 시작하려면 START를 입력하고 Enter를 누르세요. 다른 입력은 호출 없이 종료합니다.");
                    if (!string.Equals(Console.ReadLine(), "START", StringComparison.Ordinal) || stop.IsCancellationRequested)
                    { Console.WriteLine("시작하지 않았습니다. 호출 없음."); return 0; }

                    int result = RunApprovedTrialAsync(stop.Token).GetAwaiter().GetResult();
                    PauseAfterClose();
                    return result;
                }
                catch
                {
                    // All post-preparation uncertain exits are handled by the
                    // retained pending branch below, never this outer return.
                    Console.WriteLine("시작 절차를 완료하지 못했습니다. 원문 오류·경로는 출력하지 않습니다.");
                    return 2;
                }
                finally { Console.CancelKeyPress -= onCancel; }
            }
        }

        private static bool IsWindows10X64()
        {
            var version = Environment.OSVersion.Version;
            return Environment.OSVersion.Platform == PlatformID.Win32NT && Environment.Is64BitProcess &&
                Environment.Is64BitOperatingSystem && version.Major == 10 && version.Build >= 10240 && version.Build < 22000;
        }

        private static async Task<int> RunApprovedTrialAsync(CancellationToken token)
        {
            WsabiWmiOneShotReservationStatus reservation;
            try
            {
                string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                if (string.IsNullOrWhiteSpace(local) || !Path.IsPathRooted(local)) throw new InvalidOperationException();
                var claim = new WsabiWmiFixedModeReadAFileReservation(Path.Combine(local, "ATIVBatteryGuard", "Experiments"));
                reservation = claim.TryClaim();
            }
            catch { reservation = WsabiWmiOneShotReservationStatus.Unavailable; }
            if (reservation != WsabiWmiOneShotReservationStatus.Claimed)
            {
                Console.WriteLine("새 시험의 1회 예약: " + reservation + ". 호출 없음. 예약 변경·재시도하지 마세요.");
                return 2;
            }

            var journal = FixedReadTrialJournal.TryCreate(AppDomain.CurrentDomain.BaseDirectory);
            if (journal == null)
            {
                Console.WriteLine("결과 TXT를 준비하지 못했습니다. 호출 없음. 이번 시험 예약은 소모됐습니다.");
                return 2;
            }
            FixedReadPreparedResources resources = null;
            bool sdkPreparationStarted = false;
            try
            {
                journal.Write("ATIV Battery Guard — FixedModeReadA-v1");
                journal.Write("새 목적의 영속 1회 예약: Claimed");
                journal.Write("method 최대1 / 저장 byte 샘플0~1 / 초기화·handshake·재시도·설정 변경·fallback 각각0");
                journal.Write("실제 충전 제어: Unsupported. 저장 후보는 실제 충전 제한 적용이나 임계값의 증거가 아닙니다.");
                if (token.IsCancellationRequested || journal.WriteFailed)
                { journal.Write("준비 전 중단: 호출 없음. 예약은 소모됐습니다."); return 2; }

                var preflight = await FixedReadTrialLifetime.AwaitWithNoticeAsync(
                    Task.Run(() => WindowsFixedReadPreflight.Prepare()), Task.Delay(TimeSpan.FromSeconds(10)),
                    () => journal.Write("메타데이터 준비 표시 시간 초과: 호출 전 작업의 실제 반환을 기다립니다. 강제 종료·재시도 없음."))
                    .ConfigureAwait(false);
                journal.Write("사전 검증: " + preflight.Status + " / 단계: " + preflight.Stage);
                if (!preflight.IsReady) { journal.Write("호출 없음. 이번 시험은 종료하며 재시도하지 않습니다."); return 2; }
                resources = preflight.Resources;

                WsabiWmiFixedModeReadAttempt attempt;
                var creation = WsabiWmiFixedModeReadAttempt.TryCreate(out attempt);
                journal.Write("고정 요청 준비: " + creation);
                if (attempt == null || token.IsCancellationRequested || journal.WriteFailed)
                {
                    resources.AcceptInputOwnership(false);
                    resources.Dispose(); resources = null;
                    journal.Write("호출 전 중단. 비교 내용·원문 요청은 기록하지 않습니다. 재시도 없음.");
                    return 2;
                }

                sdkPreparationStarted = true;
                var prepared = await FixedReadTrialLifetime.AwaitWithNoticeAsync(
                    WsabiWmiWindowsSingleReadPreparation.PrepareFixedReadAAsync(resources.Plan, resources.Binding,
                        attempt, new WsabiWmiWindowsMutexGate(), token), Task.Delay(TimeSpan.FromSeconds(10)),
                    () => journal.Write("SDK 준비 표시 시간 초과: 소유권과 실제 준비 종료를 기다립니다. 강제 종료·재시도 없음."))
                    .ConfigureAwait(false);
                resources.AcceptInputOwnership(prepared.InputOwnershipTransferred);
                journal.Write("SDK 준비: " + prepared.Status);
                journal.Write("대상 연결: " + (prepared.SdkStatus.HasValue ? prepared.SdkStatus.Value.ToString() : "NotObserved"));
                journal.Write("등록: " + (prepared.RegistrationStatus.HasValue ? prepared.RegistrationStatus.Value.ToString() : "NotObserved"));
                journal.Write("입력: " + (prepared.InputStatus.HasValue ? prepared.InputStatus.Value.ToString() : "NotObserved"));
                if (!prepared.IsReady)
                {
                    if (prepared.InputOwnershipTransferred && prepared.InputCleanupStatus != WsabiWmiWindowsCleanupStatus.Complete)
                        await HoldUncertainAsync(resources, journal).ConfigureAwait(false);
                    resources.Dispose(); resources = null;
                    journal.Write("WMI method 호출 없음. 준비 종료. 이번 시험을 반복하지 마세요.");
                    return 2;
                }

                var invocation = prepared.Invocation;
                journal.Write("고정 시도 준비 완료: owner 획득 최대2초 / 응답 표시10초 / 실제 종료·정리는 별도 대기.");
                if (journal.WriteFailed)
                {
                    var closed = await invocation.RequestCloseAsync().ConfigureAwait(false);
                    if (closed != WsabiWmiWindowsCleanupStatus.Complete)
                        await HoldUncertainAsync(resources, journal).ConfigureAwait(false);
                    resources.Dispose(); resources = null;
                    journal.Write("TXT 기록 실패로 호출 전에 종료했습니다. 예약은 소모됐으며 재시도하지 않습니다.");
                    return 2;
                }
                // Run still uses the original local stop token if it changed
                // during preparation. This does not bypass actual-close joins.
                var joined = await FixedReadTrialLifetime.RunAndJoinAsync(
                    () => invocation.RunAndCloseAsync(frame =>
                    {
                        var verdict = attempt.Evaluate(frame);
                        journal.Write("교환 상태: " + frame.Status);
                        journal.Write("조회 판정: " + verdict.Status);
                        journal.Write("저장 모드 후보: " + (verdict.StoredModeCandidate.HasValue
                            ? verdict.StoredModeCandidate.Value.ToString(System.Globalization.CultureInfo.InvariantCulture) : "미관측"));
                        journal.Write("결과 표시는 실제 종료 보장이 아닙니다. 관련 정리 완료를 기다립니다.");
                    }, token),
                    () => invocation.RequestCloseAsync(),
                    () => journal.Write("시도 결과 확인 불가. 성공으로 해석하지 않고 관련 정리를 기다립니다."))
                    .ConfigureAwait(false);
                if (!joined.CleanupComplete) await HoldUncertainAsync(resources, journal).ConfigureAwait(false);
                resources.Dispose(); resources = null;
                journal.Write("관련 정리: Complete. 이번 시험 종료. 재시도하지 마세요.");
                journal.Write("실제 보호 조회/충전 제어 지원은 활성화하지 않습니다. 원문 frame·비교 내용·경로·고유 ID는 기록하지 않습니다.");
                if (journal.WriteFailed) Console.WriteLine("TXT 저장 일부 실패. 표시된 결과를 확인하세요. 호출 재시도 없음.");
                return joined.RunFailed ? 2 : 0;
            }
            catch
            {
                if (sdkPreparationStarted) await HoldUncertainAsync(resources, journal).ConfigureAwait(false);
                if (resources != null) { resources.AcceptInputOwnership(false); resources.Dispose(); resources = null; }
                journal.Write("호출 전 준비 결과 확인 불가. 원문 오류는 제외하며 재시도하지 않습니다.");
                return 2;
            }
            finally
            {
                // This block is reached after safe pre-invocation failure or
                // actual close only. The unknown branch deliberately stays pending.
                journal.Dispose();
            }
        }

        private static async Task HoldUncertainAsync(object resources, FixedReadTrialJournal journal)
        {
            uncertainOwnershipRoot = new object[] { resources, journal };
            journal.Write("관련 종료·소유권 확인 불가: Pending. 관련 참조를 유지하고 추가 해제·새 호출·강제 종료·재시도 없이 기다립니다.");
            await Never.ConfigureAwait(false);
            GC.KeepAlive(uncertainOwnershipRoot);
        }

        private static void PauseAfterClose()
        {
            Console.WriteLine("종료된 결과를 확인한 뒤 Enter를 눌러 닫으세요.");
            try { Console.ReadLine(); } catch { }
        }
    }
}
