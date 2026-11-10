using System;
using System.IO;
using System.Windows;
using System.Windows.Threading;
using Microsoft.Win32;
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
        private WindowsManualProtectionOperationService manualProtection;
        private bool powerEventsSubscribed;

        protected override async void OnStartup(StartupEventArgs e)
        {
            base.OnStartup(e);
            if (e.Args.Length != 0)
            {
                if (e.Args.Length == 2 && e.Args[0] == BatteryCapabilitiesWorker.Argument)
                {
                    Shutdown(BatteryCapabilitiesWorker.Run(e.Args[1]));
                    return;
                }
                if (e.Args.Length == 2 && e.Args[0] == SamsungFileInspectionWorker.Argument)
                {
                    Shutdown(SamsungFileInspectionWorker.Run(e.Args[1]));
                    return;
                }
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
                manualProtection = new WindowsManualProtectionOperationService();
                viewModel = new MainViewModel(
                    new WindowsBatteryStatusProvider(), store, log, interaction,
                    new HardwareDiagnosticsCollector(), samsungFiles: new WindowsSamsungFileInspectionProvider(),
                    manualProtectionService: manualProtection);
                var window = new MainWindow { DataContext = viewModel };
                MainWindow = window;
                // Start in the compact normal window even when an older
                // release remembered a maximized window. The user may still
                // maximize it explicitly after it is safely placed.
                window.Closing += (sender, closing) =>
                {
                    if (closing.Cancel) return;
                    if (viewModel.ManualProtectionBusy)
                    { closing.Cancel = true; viewModel.NotifyManualCloseBlocked(); }
                };
                window.Closed += delegate
                {
                    timer?.Stop();
                    viewModel.RememberWindowState(window.WindowState == WindowState.Maximized);
                    viewModel.Dispose();
                };
                timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(10) };
                timer.Tick += PollBattery;
                timer.Start();
                window.Show();
                try { SystemEvents.PowerModeChanged += PowerModeChanged; powerEventsSubscribed = true; } catch { }
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

        private void PowerModeChanged(object sender, PowerModeChangedEventArgs e)
        {
            if (e.Mode != PowerModes.Resume && e.Mode != PowerModes.Suspend) return;
            try
            {
                if (!Dispatcher.HasShutdownStarted)
                    Dispatcher.BeginInvoke(new Action(() => viewModel?.InvalidateManualState()));
            }
            catch { }
        }

        protected override void OnExit(ExitEventArgs e)
        {
            if (powerEventsSubscribed) { try { SystemEvents.PowerModeChanged -= PowerModeChanged; } catch { } }
            manualProtection?.Dispose();
            WindowsBatteryCapabilitiesProvider.StopForShutdown();
            WindowsSamsungFileInspectionProvider.StopForShutdown();
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
