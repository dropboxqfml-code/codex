using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Storage;

namespace ATIVBatteryGuard.Validation
{
    internal static class Program
    {
        private sealed class CheckFailure : Exception
        {
            public CheckFailure(string notice) : base(notice) { }
        }
        [DataContract]
        private sealed class RunReport
        {
            [DataMember] public int SchemaVersion = 1;
            [DataMember] public string ReleaseVersion = ApplicationRelease.Version;
            [DataMember] public string StartedUtc = DateTime.UtcNow.ToString("O");
            [DataMember] public string CompletedUtc;
            [DataMember] public string Outcome = "not-completed";
            [DataMember] public bool TargetWindows10X64;
            [DataMember] public bool FilesVerifiedBefore;
            [DataMember] public bool FilesVerifiedAfter;
            [DataMember] public bool GuiExecuted;
            [DataMember] public bool GuiPassed;
            [DataMember] public int? GuiExitCode;
            [DataMember] public string GuiReportFile;
            [DataMember] public GuiEvidence Gui;
            [DataMember] public string SourceFingerprintSha256;
            [DataMember] public bool DefenderScanExecuted = false;
            [DataMember] public bool AuthenticodeSigned = false;
            [DataMember] public bool ManualUserFlowsConfirmed = false;
            [DataMember] public bool FinalReleaseApproved = false;
            [DataMember] public string Notice;
        }

        private static int Main(string[] args)
        {
            Console.OutputEncoding = new UTF8Encoding(false);
            Console.WriteLine("ATIV Battery Guard 0.3.0 실사용 검증판 · 로컬 검사");
            Console.WriteLine("파일과 모의 GUI를 검사합니다. 충전 제어·관리자 요청·자동 전송은 수행하지 않습니다.");
            var report = new RunReport();
            string root = null, resultDirectory = null;
            try
            {
                if (args.Length != 0) throw new CheckFailure("이 도구는 인수 없이 검증 묶음 폴더에서 실행하세요.");
                var os = Environment.OSVersion;
                report.TargetWindows10X64 = os.Platform == PlatformID.Win32NT && Environment.Is64BitOperatingSystem
                    && os.Version.Major == 10 && os.Version.Minor == 0 && os.Version.Build >= 10240 && os.Version.Build < 22000;
                if (!report.TargetWindows10X64) throw new CheckFailure("검증 대상은 Windows 10 x64입니다.");
                root = LocalPathPolicy.NormalizeDirectory(AppDomain.CurrentDomain.BaseDirectory);
                resultDirectory = Path.Combine(root, "validation-results");
                LocalPathPolicy.NormalizeDirectory(resultDirectory);
                Directory.CreateDirectory(resultDirectory);
                var manifest = ValidationEvidence.ReadManifest(ReadBounded(Path.Combine(root, "VALIDATION-MANIFEST.json")));
                report.SourceFingerprintSha256 = manifest.SourceFingerprintSha256;
                Console.WriteLine("1/3 배포 파일 확인 중…");
                ValidationEvidence.VerifyFiles(root, manifest);
                var version = FileVersionInfo.GetVersionInfo(Path.Combine(root, "ATIVBatteryGuard.exe"));
                if (version.FileVersion != ApplicationRelease.FileVersion || version.ProductVersion != ApplicationRelease.Version)
                    throw new CheckFailure("프로그램 버전이 검증 묶음과 일치하지 않습니다.");
                report.FilesVerifiedBefore = true;
                report.GuiReportFile = "gui-" + Guid.NewGuid().ToString("N") + ".json";
                string guiReport = Path.Combine(resultDirectory, report.GuiReportFile);
                LocalPathPolicy.EnsureNoReparsePoints(guiReport);
                Console.WriteLine("2/3 별도 임시 자료로 화면 자동 검사 중… 창이 잠시 나타납니다.");
                // The self-test constructs its own temporary data and a synthetic battery.
                // It never constructs WindowsManualProtectionOperationService or launches the helper.
                using (var process = Process.Start(new ProcessStartInfo
                {
                    FileName = Path.Combine(root, "ATIVBatteryGuard.exe"), WorkingDirectory = root,
                    Arguments = "--self-test \"" + guiReport + "\"", UseShellExecute = false
                }))
                {
                    if (process == null) throw new CheckFailure("자동 검사 창을 열지 못했습니다.");
                    report.GuiExecuted = true;
                    if (!process.WaitForExit(120000))
                        throw new CheckFailure("자동 검사가 시간 안에 끝나지 않았습니다. 통과로 기록하지 않으며 창을 강제 종료하지 않았습니다.");
                    report.GuiExitCode = process.ExitCode;
                    report.Gui = ValidationEvidence.ReadGui(ReadBounded(guiReport));
                    report.GuiPassed = ValidationEvidence.GuiPassed(process.ExitCode, report.Gui);
                }
                Console.WriteLine("3/3 검사 후 파일 확인 중…");
                ValidationEvidence.VerifyFiles(root, manifest);
                report.FilesVerifiedAfter = true;
                report.Outcome = report.GuiPassed ? "automated-checks-passed-manual-checks-pending" : "gui-check-failed";
                report.Notice = report.GuiPassed
                    ? "자동 검사 통과. 한글 입력·실제 대화상자·고배율·반복 사용과 보안 검사는 아직 확인하지 않았습니다."
                    : "화면 자동 검사가 통과하지 않았습니다. 결과 파일을 확인하세요.";
            }
            catch (CheckFailure error)
            {
                // These messages are fixed by this tool, never taken from file content or native errors.
                report.Outcome = "not-passed"; report.Notice = error.Message;
            }
            catch
            {
                report.Outcome = "not-passed";
                report.Notice = "검사를 완료하지 못했습니다. 전체 파일을 새 로컬 폴더에 풀고 쓰기 권한·파일 잠금을 확인하세요.";
            }
            finally
            {
                report.CompletedUtc = DateTime.UtcNow.ToString("O");
                Console.WriteLine(report.Notice ?? "검사를 완료하지 못했습니다.");
                if (resultDirectory != null)
                {
                    try
                    {
                        string name = "validation-" + Guid.NewGuid().ToString("N") + ".json";
                        string output = LocalPathPolicy.NormalizeFile(Path.Combine(resultDirectory, name));
                        using (var file = new FileStream(output, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                        {
                            new DataContractJsonSerializer(typeof(RunReport)).WriteObject(file, report);
                            file.Flush(true);
                        }
                        Console.WriteLine("검증 묶음의 validation-results 폴더에 저장했습니다: " + name);
                    }
                    catch { Console.WriteLine("결과 파일을 저장하지 못했습니다. 통과로 처리하지 않습니다."); report.Outcome = "not-passed"; }
                }
                Console.WriteLine("이 검사는 최종 출시 승인이나 악성 코드 부재 인증이 아닙니다.");
            }
            return report.Outcome == "automated-checks-passed-manual-checks-pending" ? 0 : 1;
        }

        private static byte[] ReadBounded(string path)
        {
            path = LocalPathPolicy.NormalizeFile(path);
            using (var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            using (var output = new MemoryStream())
            {
                byte[] bytes = new byte[4096]; int count;
                while ((count = input.Read(bytes, 0, bytes.Length)) != 0)
                {
                    if (output.Length + count > 65536) throw new InvalidDataException();
                    output.Write(bytes, 0, count);
                }
                return output.ToArray();
            }
        }
    }
}
