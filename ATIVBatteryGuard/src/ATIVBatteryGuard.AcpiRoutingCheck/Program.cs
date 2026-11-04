using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.WmiAccessCheck;

namespace ATIVBatteryGuard.AcpiRoutingCheck
{
    // Separate static firmware-table reader; no AML evaluation or OEM backend.
    // No command, payload, query, server or user-supplied path is accepted.
    internal static class Program
    {
        private const string WorkerArgument = "--acpi-routing-worker";
        private const int WorkerTimeoutMilliseconds = 10000;

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

            int result;
            if (!IsSupportedProcess())
            {
                WriteFailure("UnsupportedPlatform");
                result = 2;
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
            // Direct use of the internal argument retains the independent limit.
            var watchdog = new Thread(() =>
            {
                Thread.Sleep(WorkerTimeoutMilliseconds);
                Environment.Exit(3);
            }) { IsBackground = true };
            watchdog.Start();
            try
            {
                if (!IsSupportedProcess())
                {
                    WriteFailure("UnsupportedPlatform");
                    return 0;
                }
                Console.Write(WindowsAcpiRoutingProbe.Collect());
                return 0;
            }
            catch
            {
                WriteFailure("Unavailable");
                return 2;
            }
        }

        private static int RunBoundedWorker()
        {
            Process child = null;
            try
            {
                string self = Assembly.GetExecutingAssembly().Location;
                if (!string.Equals(Path.GetFileName(self), "ATIVBatteryGuard.AcpiRoutingCheck.exe", StringComparison.OrdinalIgnoreCase))
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
                    WriteFailure("TimedOut");
                    Console.WriteLine("작업자 제한 시간 초과로 세부 단계는 미관측입니다. 중간 출력은 결과로 사용하지 않습니다.");
                    return 3;
                }
                if (child.ExitCode == 3)
                {
                    WriteFailure("TimedOut");
                    Console.WriteLine("작업자의 독립 시간 제한으로 종료되어 세부 단계는 미관측입니다.");
                    return 3;
                }
                if (child.ExitCode != 0 || !output.Wait(1000) || !errors.Wait(1000) ||
                    string.IsNullOrWhiteSpace(output.Result) || !string.IsNullOrEmpty(errors.Result))
                    throw new InvalidOperationException();
                Console.Write(output.Result);
                return 0;
            }
            catch
            {
                if (child != null) TryStop(child);
                WriteFailure("Unavailable");
                Console.WriteLine("작업자 결과를 확인하지 못했습니다. 원문 오류와 경로는 출력하지 않습니다.");
                return 2;
            }
            finally { if (child != null) child.Dispose(); }
        }

        private static void WriteFailure(string category)
        {
            Console.WriteLine("ATIV Battery Guard — ACPI 정적 WMI 연결 점검 (Acpi-routing-v1)");
            Console.WriteLine("수집 결과: " + category);
            Console.WriteLine("OEM 호출·AML 실행·예약 접근·원문 저장 없음. 실제 충전 제어: 미지원.");
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
