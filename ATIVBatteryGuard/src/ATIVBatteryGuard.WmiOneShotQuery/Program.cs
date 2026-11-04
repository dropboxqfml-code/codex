using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Diagnostics;
using ATIVBatteryGuard.WmiAccessCheck;

namespace ATIVBatteryGuard.WmiOneShotQuery
{
    // The main application never launches this separate, explicitly approved
    // experiment. No command, payload, query, server or path is accepted.
    internal static class Program
    {
        private const string WorkerArgument = "--one-shot-query65-worker";
        private const int WorkerTimeoutMilliseconds = 10000;
        private const string ExperimentRevision = "Query65-locator-v2";

        [MTAThread]
        private static int Main(string[] args)
        {
            Console.OutputEncoding = new UTF8Encoding(false);
            if (args.Length == 1 && args[0] == WorkerArgument) return RunWorker();
            if (args.Length != 0)
            {
                Console.WriteLine("이 도구는 명령·입력값·쿼리·서버·파일 경로를 받지 않습니다. OEM 호출 없음.");
                return 2;
            }

            Console.WriteLine("수정판: 승인된 단1회 조회 · 경로 정보 확보 보완 (" + ExperimentRevision + ")");
            int result;
            if (!IsSupportedProcess())
            {
                Console.WriteLine("Windows 10 계열 x64 프로세스에서만 이 한정 실험을 준비합니다. OEM 호출 없음.");
                result = 2;
            }
            else if (ProcessElevationProbe.Read() != ProcessElevationState.Elevated)
            {
                Console.WriteLine("현재 토큰이 Elevated로 확인되지 않아 OEM 호출 없이 종료했습니다.");
                Console.WriteLine("승인된 절차는 같은 계정에서 이 별도 EXE를 수동 관리자 실행하는 한 번의 실험입니다. 자동 권한 상승은 없습니다.");
                result = 0;
            }
            else result = RunBoundedWorker();

            PauseForConsole();
            return result;
        }

        private static bool IsSupportedProcess()
            => Environment.OSVersion.Platform == PlatformID.Win32NT && Environment.Is64BitProcess &&
                Environment.OSVersion.Version.Major >= 10;

        private static int RunWorker()
        {
            // Even direct use of the internal argument cannot bypass the
            // worker's process limit. A dedicated thread avoids timer-pool
            // starvation. Exit cannot undo firmware work already dispatched.
            var watchdog = new Thread(() =>
            {
                Thread.Sleep(WorkerTimeoutMilliseconds);
                Environment.Exit(3);
            }) { IsBackground = true };
            watchdog.Start();
            try
            {
                if (!IsSupportedProcess() || ProcessElevationProbe.Read() != ProcessElevationState.Elevated)
                {
                    Console.WriteLine("실행 환경 또는 Elevated 토큰 조건을 확인하지 못했습니다. OEM 호출 없음.");
                    return 0;
                }
                string localData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                if (string.IsNullOrWhiteSpace(localData))
                {
                    Console.WriteLine("로컬 1회 예약 위치를 확인하지 못했습니다. OEM 호출 없음.");
                    return 0;
                }
                string directory = LocalPathPolicy.NormalizeDirectory(Path.Combine(localData, "ATIVBatteryGuard", "Experiments"));
                var reservation = new WsabiWmiOneShotFileReservation(directory);
                using (var backend = new WindowsOneShotBackend())
                {
                    var experiment = new WsabiWmiOneShotExperiment(backend, reservation);
                    Console.Write(experiment.RunAsync().GetAwaiter().GetResult().ToDisplayText());
                }
                return 0;
            }
            catch
            {
                Console.WriteLine("한정 실험 결과를 확인하지 못했습니다. 원문 오류·경로·응답은 기록하지 않습니다.");
                Console.WriteLine("호출 여부나 결과를 추측하지 않고 재시도하지 마세요. 실제 충전 제어는 미지원입니다.");
                return 2;
            }
        }

        private static int RunBoundedWorker()
        {
            Process child = null;
            try
            {
                string self = Assembly.GetExecutingAssembly().Location;
                if (!string.Equals(Path.GetFileName(self), "ATIVBatteryGuard.WmiOneShotQuery.exe", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException();
                string directory = LocalPathPolicy.NormalizeDirectory(Path.GetDirectoryName(self));
                LocalPathPolicy.EnsureNoReparsePoints(self);
                child = new Process
                {
                    StartInfo = new ProcessStartInfo
                    {
                        FileName = self, Arguments = WorkerArgument, WorkingDirectory = directory,
                        UseShellExecute = false, CreateNoWindow = true,
                        RedirectStandardOutput = true, RedirectStandardError = true,
                        StandardOutputEncoding = new UTF8Encoding(false, true)
                    }
                };
                if (!child.Start()) throw new InvalidOperationException();
                Task<string> output = Task.Run(() => BoundedTextCapture.Read(child.StandardOutput));
                Task<string> errors = Task.Run(() => BoundedTextCapture.Read(child.StandardError));
                if (!child.WaitForExit(WorkerTimeoutMilliseconds))
                {
                    TryStop(child);
                    child.WaitForExit(1000);
                    Console.WriteLine("한정 조회 후보 실험 시간 초과·결과 불명입니다. 중간 관측을 성공으로 사용하지 않습니다.");
                    Console.WriteLine("프로세스 종료는 펌웨어 동작의 취소나 원상 복구를 보장하지 않습니다. 재시도·예약 표식 삭제를 하지 마세요.");
                    return 3;
                }
                if (child.ExitCode == 3)
                {
                    Console.WriteLine("작업자의 독립 시간 제한으로 종료됐습니다. 실제 호출 여부와 결과는 불명입니다. 재시도하지 마세요.");
                    return 3;
                }
                if (child.ExitCode != 0 || !output.Wait(1000) || !errors.Wait(1000) || output.Result == null)
                    throw new InvalidOperationException();
                Console.Write(output.Result);
                return 0;
            }
            catch
            {
                if (child != null) TryStop(child);
                Console.WriteLine("작업자 결과를 받지 못했습니다. 실제 호출 여부와 결과는 확인 불가입니다.");
                Console.WriteLine("재실행·예약 표식 삭제·다른 명령 시험은 하지 마세요. 실제 충전 제어는 미지원입니다.");
                return 2;
            }
            finally { if (child != null) child.Dispose(); }
        }

        private static void PauseForConsole()
        {
            if (Console.IsInputRedirected || Console.IsOutputRedirected) return;
            Console.WriteLine("결과를 복사한 뒤 Enter를 눌러 닫으세요.");
            try { Console.ReadLine(); } catch { }
        }

        private static void TryStop(Process child)
        {
            try { if (!child.HasExited) child.Kill(); } catch { }
        }
    }
}
