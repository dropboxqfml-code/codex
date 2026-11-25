using System;
using System.IO;
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
            Console.OutputEncoding = new UTF8Encoding(false);
            try
            {
                bool soak = ExtendedPolicy.IsSoak(args);
                var os = Environment.OSVersion;
                if (os.Platform != PlatformID.Win32NT || !Environment.Is64BitOperatingSystem
                    || os.Version.Major != 10 || os.Version.Build < 10240 || os.Version.Build >= 22000)
                    throw new InvalidOperationException();
                string root = LocalPathPolicy.NormalizeDirectory(AppDomain.CurrentDomain.BaseDirectory);
                string manifestPath = LocalPathPolicy.NormalizeFile(Path.Combine(root, "EXTENDED-MANIFEST.json"));
                byte[] bytes;
                using (var input = new FileStream(manifestPath, FileMode.Open, FileAccess.Read, FileShare.Read))
                {
                    if (input.Length > 65536) throw new InvalidDataException();
                    using (var memory = new MemoryStream()) { input.CopyTo(memory); bytes = memory.ToArray(); }
                }
                var manifest = ValidationEvidence.ReadManifest(bytes);
                ValidationEvidence.VerifyFiles(root, manifest);
                var version = System.Diagnostics.FileVersionInfo.GetVersionInfo(Path.Combine(root, "ATIVBatteryGuard.exe"));
                if (version.ProductVersion != ApplicationRelease.Version || version.FileVersion != ApplicationRelease.FileVersion)
                    throw new InvalidDataException();
                Console.WriteLine(soak ? "20분 반복 검사 · 합성 예제만 사용합니다." : "빠른 추가 검사 · 합성 예제만 사용합니다.");
                Console.WriteLine("두 검증 창의 이동/입력은 자동입니다. 중단하려면 검증 창의 X 또는 콘솔 Ctrl+C를 누르세요.");
                Console.CancelKeyPress += (sender, e) => { e.Cancel = true; StopRequested = true; };
                var app = new ExtendedApplication(root, manifest, soak);
                // Reuse the product's compiled resources, while the override below avoids
                // its normal startup, real battery/WMI polling and manual helper service.
                app.InitializeComponent();
                app.ShutdownMode = ShutdownMode.OnExplicitShutdown;
                return app.Run();
            }
            catch
            {
                Console.WriteLine("추가 검사를 시작하지 못했습니다. Windows 10 x64에서 ZIP 전체를 새 로컬 폴더에 풀어 실행하세요.");
                Console.WriteLine("통과로 기록하지 않았습니다. 사용법: ExtendedCheck --quick 또는 --soak");
                return 2;
            }
        }
    }

    internal sealed class ExtendedApplication : ATIVBatteryGuard.App
    {
        private readonly string root;
        private readonly ValidationManifest manifest;
        private readonly bool soak;
        public ExtendedApplication(string root, ValidationManifest manifest, bool soak)
        { this.root = root; this.manifest = manifest; this.soak = soak; }
        protected override async void OnStartup(StartupEventArgs e)
        {
            // Do not call App.OnStartup: the harness owns all windows and temporary data.
            int code;
            try { code = await new Runner(this, root, manifest, soak).Run(); }
            catch { Console.WriteLine("검사를 완료하지 못했습니다. 통과로 처리하지 않습니다."); code = 2; }
            Shutdown(code);
        }
        protected override void OnExit(ExitEventArgs e) { /* Harness cleanup is owned by Runner. */ }
    }
}
