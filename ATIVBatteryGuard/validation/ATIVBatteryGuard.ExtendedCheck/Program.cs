using System;
using System.IO;
using System.Runtime.CompilerServices;
using System.Text;
using System.Windows;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Validation;

namespace ATIVBatteryGuard.ExtendedValidation
{
    internal static class Program
    {
        internal static volatile bool StopRequested;
        [STAThread]
        private static int Main(string[] args)
        {
            StartupJournal journal = null;
            try
            {
                Console.OutputEncoding = new UTF8Encoding(false);
                journal = new StartupJournal(AppDomain.CurrentDomain.BaseDirectory);
                return RunChecked(args, journal);
            }
            catch (Exception error)
            {
                bool diagnosticSaved = false;
                try { if (journal != null) { journal.Fail(error); diagnosticSaved = true; } } catch { }
                Console.WriteLine("추가 검사 시작 실패 · " + (journal?.ErrorCode ?? "STARTUP_REPORT_UNAVAILABLE"));
                Console.WriteLine("단계: " + (journal?.Stage ?? "bootstrap"));
                Console.WriteLine("오류값(HResult): 0x" + error.HResult.ToString("X8"));
                if (diagnosticSaved) Console.WriteLine("진단 결과: extended-results\\" + Path.GetFileName(journal.ReportPath));
                else Console.WriteLine("시작 진단 파일도 저장하지 못했습니다. 이 폴더의 쓰기 권한과 파일 잠금을 확인하세요.");
                Console.WriteLine("통과로 기록하지 않았습니다. 같은 검사를 반복하기 전에 시작 진단 결과를 전달하세요.");
                return 2;
            }
        }

        // Defer product/WPF type resolution until after the BCL startup journal
        // exists, allowing assembly loading failures to be recorded safely.
        [MethodImpl(MethodImplOptions.NoInlining)]
        private static int RunChecked(string[] args, StartupJournal journal)
        {
            journal.Advance("arguments");
            bool ime = ExtendedPolicy.IsIme(args);
            bool soak = !ime && ExtendedPolicy.IsSoak(args);
            if (ime) journal.SelectImeMode(); else journal.SelectMode(soak);
            journal.Advance("platform");
            var os = Environment.OSVersion;
            if (os.Platform != PlatformID.Win32NT || !Environment.Is64BitOperatingSystem
                || os.Version.Major != 10 || os.Version.Build < 10240 || os.Version.Build >= 22000)
                throw new PlatformNotSupportedException();
            journal.Advance("location");
            string root = LocalPathPolicy.NormalizeDirectory(AppDomain.CurrentDomain.BaseDirectory);
            journal.Advance("manifest-read");
            string manifestPath = LocalPathPolicy.NormalizeFile(Path.Combine(root, "EXTENDED-MANIFEST.json"));
            byte[] bytes;
            using (var input = new FileStream(manifestPath, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                if (input.Length > 65536) throw new InvalidDataException();
                using (var memory = new MemoryStream()) { input.CopyTo(memory); bytes = memory.ToArray(); }
            }
            var manifest = ValidationEvidence.ReadManifest(bytes);
            journal.Advance("files-before"); ValidationEvidence.VerifyFiles(root, manifest);
            journal.Advance("product-version");
            var version = System.Diagnostics.FileVersionInfo.GetVersionInfo(Path.Combine(root, "ATIVBatteryGuard.exe"));
            if (version.ProductVersion != ApplicationRelease.Version || version.FileVersion != ApplicationRelease.FileVersion)
                throw new InvalidDataException();
            Console.WriteLine(ime ? "한글 입력 확인 · 안내에 따라 직접 입력하세요." : soak ? "20분 반복 검사 · 합성 예제만 사용합니다." : "빠른 추가 검사 · 합성 예제만 사용합니다.");
            Console.WriteLine(ime ? "기존 빠른/20분 검사는 반복하지 않습니다. 입력 완료 후 결과 저장을 누르세요."
                : "두 검증 창의 입력은 자동입니다. 중단하려면 검증 창의 X 또는 콘솔 Ctrl+C를 누르세요.");
            Console.CancelKeyPress += (sender, e) => { e.Cancel = true; StopRequested = true; };
            journal.Advance("application-create");
            var app = new ExtendedApplication(root, manifest, soak, ime, journal);
            journal.Advance("resources-load"); app.InitializeResources();
            app.ShutdownMode = ShutdownMode.OnExplicitShutdown;
            journal.Advance("dispatcher-start");
            int exitCode = app.Run(); journal.Complete(exitCode); return exitCode;
        }
    }

    internal sealed class ExtendedApplication : Application
    {
        private readonly string root;
        private readonly ValidationManifest manifest;
        private readonly bool soak, ime;
        private readonly StartupJournal journal;
        public ExtendedApplication(string root, ValidationManifest manifest, bool soak, bool ime, StartupJournal journal)
        { this.root = root; this.manifest = manifest; this.soak = soak; this.ime = ime; this.journal = journal; }
        public void InitializeResources()
        {
            // The host owns this dictionary. Product App.InitializeComponent cannot
            // initialize a subclass from another assembly (WPF BAML root ownership).
            Resources = (ResourceDictionary)LoadComponent(new Uri(
                "/ATIVBatteryGuard.ExtendedCheck;component/productresources.xaml", UriKind.Relative));
        }
        protected override async void OnStartup(StartupEventArgs e)
        {
            base.OnStartup(e);
            int code;
            try
            {
                journal.Advance("runner-start");
                code = ime ? await new ImeRunner(this, root, manifest).Run() : await new Runner(this, root, manifest, soak).Run();
            }
            catch (Exception error)
            {
                try { journal.Fail(error); } catch { }
                Console.WriteLine("검사 호스트 초기화 실패 · " + journal.ErrorCode); code = 2;
            }
            Shutdown(code);
        }
    }
}
