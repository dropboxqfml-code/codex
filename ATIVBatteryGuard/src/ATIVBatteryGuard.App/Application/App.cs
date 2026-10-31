using System;
using System.IO;
using System.Windows;
using System.Windows.Threading;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Diagnostics;
using ATIVBatteryGuard.Services;
using ATIVBatteryGuard.ViewModels;
using ATIVBatteryGuard.Views;

namespace ATIVBatteryGuard
{
    // Startup was reconstructed from the previously distributed application.
    public partial class App : Application
    {
        private DispatcherTimer timer;
        private MainViewModel viewModel;

        protected override async void OnStartup(StartupEventArgs e)
        {
            base.OnStartup(e);
            if (e.Args.Length != 0)
            {
                if (e.Args.Length == 2 && e.Args[0] == "--self-test")
                {
                    try { Shutdown(await WindowsSmokeTest.RunAsync(this, e.Args[1])); }
                    catch { Shutdown(2); }
                    return;
                }
                Shutdown(2);
                return;
            }
            try
            {
                string directory = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "ATIVBatteryGuard");
                var store = new SettingsStore(directory);
                var log = new LocalLog(directory);
                var interaction = new LocalUserInteraction(directory, log);
                viewModel = new MainViewModel(
                    new WindowsBatteryStatusProvider(), store, log, interaction,
                    new HardwareDiagnosticsCollector(), new SamsungAnalysisBundleService(directory, SamsungAnalysisScope.SettingsApplication),
                    interaction.ConfirmSamsungAnalysisExport);
                var window = new MainWindow { DataContext = viewModel };
                MainWindow = window;
                if (viewModel.InitialWindowState == "Maximized")
                    window.WindowState = WindowState.Maximized;
                window.Closing += delegate
                {
                    timer?.Stop();
                    viewModel.RememberWindowState(window.WindowState == WindowState.Maximized);
                    viewModel.Dispose();
                };
                timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(10) };
                timer.Tick += PollBattery;
                timer.Start();
                window.Show();
                viewModel.ShowDiagnosticsCommand.Execute(null);
            }
            catch
            {
                MessageBox.Show(
                    "앱을 안전하게 시작하지 못했습니다. 장치 설정은 변경하지 않았습니다.",
                    "ATIV Battery Guard", MessageBoxButton.OK, MessageBoxImage.Error);
                Shutdown(1);
            }
        }

        private void PollBattery(object sender, EventArgs e)
        {
            viewModel?.RefreshBattery();
        }

        protected override void OnExit(ExitEventArgs e)
        {
            if (timer != null)
            {
                timer.Stop();
                timer.Tick -= PollBattery;
            }
            viewModel?.Dispose();
            base.OnExit(e);
        }
    }
}
