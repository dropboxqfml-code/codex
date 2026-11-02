using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using ATIVBatteryGuard.Diagnostics;
using ATIVBatteryGuard.Core.Storage;

namespace ATIVBatteryGuard.WmiAccessCheck
{
    // Separate asInvoker tool. The GUI never launches this executable or requests UAC.
    // Neither mode accepts arbitrary queries, commands, server names or file paths.
    internal static class Program
    {
        private const string WorkerArgument = "--read-only-wmi-worker";

        private static int Main(string[] args)
        {
            Console.OutputEncoding = new UTF8Encoding(false);
            if (args.Length == 1 && args[0] == WorkerArgument) return RunWorker();
            if (args.Length != 0)
            {
                Console.WriteLine("이 도구는 인수·파일 경로·임의 WMI 쿼리를 받지 않습니다.");
                return 2;
            }
            int result = RunBoundedWorker();
            if (!Console.IsInputRedirected && !Console.IsOutputRedirected)
            {
                Console.WriteLine("확인을 마치면 Enter를 눌러 닫으세요.");
                try { Console.ReadLine(); } catch { }
            }
            return result;
        }

        private static int RunWorker()
        {
            try
            {
                var elevation = ProcessElevationProbe.Read();
                var result = SamsungWmiInstanceProbe.CollectWithAccessTrace();
                Console.Write(result.ToDisplayText(elevation));
                return 0;
            }
            catch
            {
                Console.WriteLine("고정 WMI 조회 결과를 확인하지 못했습니다. 원문 오류는 기록하지 않습니다.");
                return 2;
            }
        }

        private static int RunBoundedWorker()
        {
            Process child = null;
            try
            {
                string self = Assembly.GetExecutingAssembly().Location;
                if (!string.Equals(Path.GetFileName(self), "ATIVBatteryGuard.WmiAccessCheck.exe", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException();
                string directory = LocalPathPolicy.NormalizeDirectory(Path.GetDirectoryName(self));
                LocalPathPolicy.EnsureNoReparsePoints(self);
                child = new Process
                {
                    StartInfo = new ProcessStartInfo
                    {
                        FileName = self, Arguments = WorkerArgument,
                        WorkingDirectory = directory,
                        UseShellExecute = false, CreateNoWindow = true,
                        RedirectStandardOutput = true, RedirectStandardError = true,
                        StandardOutputEncoding = new UTF8Encoding(false, true)
                    }
                };
                if (!child.Start()) throw new InvalidOperationException();
                Task<string> output = Task.Run(() => BoundedTextCapture.Read(child.StandardOutput));
                // Consume only a bounded diagnostic channel and never print its content.
                Task<string> errors = Task.Run(() => BoundedTextCapture.Read(child.StandardError));
                if (!child.WaitForExit(10000))
                {
                    TryStop(child);
                    child.WaitForExit(1000);
                    Console.WriteLine("WMI 비교 조회 시간 초과. 중간 관측을 성공·부재로 해석하지 않습니다.");
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
                Console.WriteLine("WMI 비교 결과를 받지 못했습니다. 추가 권한이나 임의 작업으로 전환하지 않습니다.");
                return 2;
            }
            finally
            {
                if (child != null) child.Dispose();
            }
        }

        private static void TryStop(Process child)
        {
            try { if (!child.HasExited) child.Kill(); } catch { }
        }
    }
}
