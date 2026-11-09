using System;
using ATIVBatteryGuard.Core.Hardware;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.ViewModels;

internal static partial class Program
{
    private static void RegisterProtectionReviewObservationViewModelTests()
    {
        Add("protection review and passive observation start empty without physical support", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                Equal(WsabiWmiProtection0To1ReviewStatus.NotLoaded, vm.ProtectionReviewStatus);
                Check(!vm.ProtectionReviewHasReportedStoredTransition && !vm.CanApply, "startup inferred physical control");
                Check(!vm.ReviewProtectionResultCommand.CanExecute(null), "empty historical review actionable");
                Equal(0, vm.ObservationSampleCount); Equal(0, vm.ObservationGapCount);
                Check(!vm.ObservationActive && vm.StartBatteryObservationCommand.CanExecute(null), "passive session auto-started");
                Check(!vm.StopBatteryObservationCommand.CanExecute(null) && !vm.SaveBatteryObservationCommand.CanExecute(null), "empty session actionable");
                Equal(0, f.Interaction.ObservationSaves);
            }
        });

        Add("protection historical review cannot change live state providers settings or files", () =>
        {
            using (var f = new Fixture())
            {
                var battery = new OfflineReviewCountingBattery();
                f.Interaction.Reader = () => { throw new InvalidOperationException("UNEXPECTED-DIAGNOSTIC"); };
                f.Hardware.Reader = () => { throw new InvalidOperationException("UNEXPECTED-HARDWARE"); };
                using (var vm = new MainViewModel(battery, f.Store, new LocalLog(f.DirectoryPath), f.Interaction, f.Hardware, f.Bundle, () => true, f.Files))
                {
                    string actual = vm.ActualModeText, desired = vm.DesiredModeText, percent = vm.BatteryPercentText;
                    string status = vm.StatusMessage, mock = vm.MockActualModeText, reason = vm.SupportReason;
                    bool restore = vm.RestoreOnBoot, protection = vm.IsProtectionSelected;
                    int reads = battery.Calls; var files = OfflineReviewFileSnapshot(f.DirectoryPath);
                    vm.ProtectionReviewInput = Protection0To1ReviewFixture(255, 1);
                    vm.ReviewProtectionResultCommand.Execute(null);
                    Equal(WsabiWmiProtection0To1ReviewStatus.ReportedStoredTransitionMatched, vm.ProtectionReviewStatus);
                    Check(vm.ProtectionReviewHasReportedStoredTransition, "historical transition not classified");
                    Check(vm.ProtectionReviewText.Contains("255 / 1"), "historical baseline replaced by uploaded values");
                    Equal(string.Empty, vm.ProtectionReviewInput);
                    Equal(actual, vm.ActualModeText); Equal(desired, vm.DesiredModeText); Equal(percent, vm.BatteryPercentText);
                    Equal(status, vm.StatusMessage); Equal(mock, vm.MockActualModeText); Equal(reason, vm.SupportReason);
                    Equal(restore, vm.RestoreOnBoot); Equal(protection, vm.IsProtectionSelected);
                    Check(!vm.CanApply && !vm.IsMockMode && !vm.ObservationActive, "history authorized a live action");
                    Equal(reads, battery.Calls); Equal(0, f.Files.Calls); Equal(0, f.Bundle.Calls);
                    Equal(0, f.Interaction.Saves); Equal(0, f.Interaction.Copies); Equal(0, f.Interaction.FileInspectionSaves); Equal(0, f.Interaction.ObservationSaves);
                    OfflineReviewAssertSameFiles(files, f.DirectoryPath);
                }
            }
        });

        Add("protection historical edits limits and clear cannot retain stale accepted or private text", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                vm.ProtectionReviewInput = Protection0To1ReviewFixture(); vm.ReviewProtectionResult();
                vm.ProtectionReviewInput = string.Empty; // Harmless empty binding echo after review.
                Check(vm.ProtectionReviewHasReportedStoredTransition, "binding echo discarded parsed record");
                vm.ProtectionReviewInput = "PRIVATE-ACCOUNT-PATH";
                Equal(WsabiWmiProtection0To1ReviewStatus.NotLoaded, vm.ProtectionReviewStatus);
                vm.ReviewProtectionResult(); Equal(string.Empty, vm.ProtectionReviewInput);
                Check(!vm.ProtectionReviewHasReportedStoredTransition && !vm.ProtectionReviewText.Contains("PRIVATE-ACCOUNT-PATH"), "untrusted source retained");
                vm.ProtectionReviewInput = Protection0To1ReviewFixture(); vm.ReviewProtectionResult();
                vm.ProtectionReviewInput = new string('x', WsabiWmiProtection0To1ReviewParser.MaximumCharacters + 1);
                Equal(WsabiWmiProtection0To1ReviewStatus.InvalidInput, vm.ProtectionReviewStatus);
                Equal(string.Empty, vm.ProtectionReviewInput);
                Check(!vm.ReviewProtectionResultCommand.CanExecute(null), "oversized raw input retained");
                vm.ClearProtectionReviewCommand.Execute(null);
                Equal(WsabiWmiProtection0To1ReviewStatus.NotLoaded, vm.ProtectionReviewStatus);
            }
        });

        Add("protection Access1 and Query65 historical results remain independent", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                vm.ExperimentReviewInput = OfflineReviewViewModelReport(); vm.ReviewExperimentResult();
                vm.FixedReadReviewInput = FixedReadAccess1ReviewFixture(0); vm.ReviewFixedReadResult();
                string experiment = vm.ExperimentReviewText, access = vm.FixedReadReviewText;
                vm.ProtectionReviewInput = Protection0To1ReviewFixture(); vm.ReviewProtectionResult();
                Equal(experiment, vm.ExperimentReviewText); Equal(access, vm.FixedReadReviewText);
                string transition = vm.ProtectionReviewText;
                vm.ClearExperimentReviewCommand.Execute(null); vm.ClearFixedReadReviewCommand.Execute(null);
                Equal(transition, vm.ProtectionReviewText);
                vm.ProtectionReviewInput = FixedReadAccess1ReviewFixture(1); vm.ReviewProtectionResult();
                Check(!vm.ProtectionReviewHasReportedStoredTransition, "Access1 substituted for transition proof");
                vm.ProtectionReviewInput = OfflineReviewViewModelReport(); vm.ReviewProtectionResult();
                Check(!vm.ProtectionReviewHasReportedStoredTransition && !vm.CanApply, "Query65 enabled physical control");
            }
        });

        Add("passive observation start never reads and only existing refresh supplies a throttled sample", () =>
        {
            using (var f = new Fixture())
            {
                var battery = new OfflineReviewCountingBattery();
                using (var vm = new MainViewModel(battery, f.Store, new LocalLog(f.DirectoryPath), f.Interaction, f.Hardware, f.Bundle, () => true, f.Files))
                {
                    int reads = battery.Calls; var files = OfflineReviewFileSnapshot(f.DirectoryPath);
                    vm.StartBatteryObservationCommand.Execute(null);
                    Equal(reads, battery.Calls); Equal(0, vm.ObservationSampleCount);
                    Check(vm.ObservationActive && !vm.StartBatteryObservationCommand.CanExecute(null), "start not bounded to one active session");
                    vm.RefreshBattery(); Equal(reads + 1, battery.Calls); Equal(1, vm.ObservationSampleCount);
                    vm.RefreshBattery(); Equal(reads + 2, battery.Calls); Equal(1, vm.ObservationSampleCount);
                    vm.StopBatteryObservationCommand.Execute(null); vm.RefreshBattery();
                    Equal(reads + 3, battery.Calls); Equal(1, vm.ObservationSampleCount); Check(!vm.ObservationActive, "stopped capture resumed");
                    Equal(0, f.Files.Calls); Equal(0, f.Bundle.Calls); Equal(0, f.Interaction.ObservationSaves);
                    OfflineReviewAssertSameFiles(files, f.DirectoryPath);
                }
            }
        });

        Add("passive observation exports only through explicit save without other historical raw input", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                vm.SaveBatteryObservationCommand.Execute(null); Equal(0, f.Interaction.ObservationSaves);
                vm.ProtectionReviewInput = "PRIVATE-PENDING-REVIEW";
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery();
                Equal(0, f.Interaction.ObservationSaves);
                Check(vm.SaveBatteryObservationCommand.CanExecute(null), "observed data cannot be explicitly exported");
                vm.SaveBatteryObservationCommand.Execute(null); Equal(1, f.Interaction.ObservationSaves);
                Check(f.Interaction.LastObservation.Contains("elapsed_seconds,percent,ac,state,quality,read_error,gap_before"), "bounded data missing from explicit export");
                Check(!f.Interaction.LastObservation.Contains("PRIVATE-PENDING-REVIEW"), "historical raw input leaked into observation");
                Equal(0, f.Interaction.Saves); Equal(0, f.Interaction.Copies); Equal(0, f.Interaction.FileInspectionSaves);
                Check(!vm.CanApply && vm.ActualModeText.Contains("미지원"), "passive sample promoted physical support");
            }
        });

        Add("passive observation save failure preserves samples without exposing private exception text", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery();
                vm.StopBatteryObservationCommand.Execute(null);
                string before = vm.ObservationText;
                f.Interaction.ObservationSaver = text => { throw new InvalidOperationException("PRIVATE-SAVE-PATH-ACCOUNT"); };
                vm.SaveBatteryObservationCommand.Execute(null);
                Equal(1, f.Interaction.ObservationSaves); Equal(1, vm.ObservationSampleCount);
                Equal(before, vm.ObservationText);
                Check(!vm.StatusMessage.Contains("PRIVATE-SAVE-PATH-ACCOUNT"), "save exception leaked private details");
                Check(vm.SaveBatteryObservationCommand.CanExecute(null) && !vm.ObservationActive,
                    "save failure consumed data or restarted observation");
                Check(!vm.CanApply, "save failure enabled physical control");
                string log = System.IO.File.ReadAllText(System.IO.Path.Combine(f.DirectoryPath, "application.log"));
                Check(!log.Contains("PRIVATE-SAVE-PATH-ACCOUNT"), "save exception leaked into local log");
            }
        });

        Add("mock activation stops passive recording and excludes all mock mode refreshes", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); Equal(1, vm.ObservationSampleCount);
                vm.IsMockMode = true; Check(!vm.ObservationActive, "mock kept passive session active");
                Check(!vm.StartBatteryObservationCommand.CanExecute(null), "mock can start observation");
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); Equal(1, vm.ObservationSampleCount);
                vm.IsMockMode = false; vm.RefreshBattery(); Equal(1, vm.ObservationSampleCount);
                Check(!vm.ObservationActive && !vm.CanApply, "leaving mock auto-resumed session or physical control");
                vm.StartBatteryObservationCommand.Execute(null); Equal(0, vm.ObservationSampleCount);
                vm.RefreshBattery(); Equal(1, vm.ObservationSampleCount);
                Equal(0, f.Interaction.ObservationSaves);
            }
        });

        Add("unknown passive snapshots export fixed quality fields and never private provider errors", () =>
        {
            using (var f = new Fixture())
            {
                var battery = new ProtectionObservationResultBattery();
                using (var vm = new MainViewModel(battery, f.Store, new LocalLog(f.DirectoryPath), f.Interaction))
                {
                    battery.Result = BatterySnapshot.Unknown("C:\\Users\\PrivateAccount\\ID-SERIAL-SECRET");
                    vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); vm.StopBatteryObservationCommand.Execute(null);
                    Equal(1, vm.ObservationSampleCount); vm.SaveBatteryObservationCommand.Execute(null);
                    string text = f.Interaction.LastObservation;
                    Check(text.Contains(",Unknown,Unknown,Unknown,Unknown,Yes,No"), "unknown became a measured sample");
                    Check(!text.Contains("PrivateAccount") && !text.Contains("ID-SERIAL-SECRET"), "free-form provider error leaked into export");
                    Check(!vm.ObservationText.Contains("PrivateAccount"), "provider error leaked into summary");
                }
            }
        });

        Add("clearing passive observations stops capture and a new session does not reuse old rows", () =>
        {
            using (var f = new Fixture())
            {
                var battery = new OfflineReviewCountingBattery();
                using (var vm = new MainViewModel(battery, f.Store, new LocalLog(f.DirectoryPath), f.Interaction))
                {
                    vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); Equal(1, vm.ObservationSampleCount);
                    int reads = battery.Calls; vm.ClearBatteryObservationCommand.Execute(null);
                    Equal(reads, battery.Calls); Equal(0, vm.ObservationSampleCount); Equal(0, vm.ObservationGapCount);
                    Check(!vm.ObservationActive && !vm.SaveBatteryObservationCommand.CanExecute(null), "clear retained actionable history");
                    vm.RefreshBattery(); Equal(0, vm.ObservationSampleCount);
                    vm.StartBatteryObservationCommand.Execute(null); Equal(0, vm.ObservationSampleCount);
                    vm.RefreshBattery(); Equal(1, vm.ObservationSampleCount); Equal(0, f.Interaction.ObservationSaves);
                }
            }
        });

        Add("dispose clears pending transition input stops observation and blocks commands without auto export", () =>
        {
            using (var f = new Fixture())
            {
                var battery = new OfflineReviewCountingBattery();
                var vm = new MainViewModel(battery, f.Store, new LocalLog(f.DirectoryPath), f.Interaction);
                vm.ProtectionReviewInput = "PRIVATE-PENDING";
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); vm.Dispose();
                Equal(string.Empty, vm.ProtectionReviewInput); Check(!vm.ObservationActive, "disposed clock/session remained active");
                Equal(1, vm.ObservationSampleCount); Equal(0, f.Interaction.ObservationSaves);
                int reads = battery.Calls, changes = 0; string text = vm.ObservationText;
                vm.PropertyChanged += (sender, args) => changes++;
                vm.RefreshBattery(); vm.ProtectionReviewInput = Protection0To1ReviewFixture(); vm.ReviewProtectionResult();
                vm.ReviewProtectionResultCommand.Execute(null); vm.ClearProtectionReviewCommand.Execute(null);
                vm.StartBatteryObservationCommand.Execute(null); vm.StopBatteryObservationCommand.Execute(null);
                vm.ClearBatteryObservationCommand.Execute(null); vm.SaveBatteryObservationCommand.Execute(null);
                Equal(reads, battery.Calls); Equal(0, changes); Equal(text, vm.ObservationText); Equal(string.Empty, vm.ProtectionReviewInput);
                Check(!vm.ReviewProtectionResultCommand.CanExecute(null) && !vm.ClearProtectionReviewCommand.CanExecute(null) &&
                    !vm.StartBatteryObservationCommand.CanExecute(null) && !vm.StopBatteryObservationCommand.CanExecute(null) &&
                    !vm.ClearBatteryObservationCommand.CanExecute(null) && !vm.SaveBatteryObservationCommand.CanExecute(null), "disposed command enabled");
                Equal(0, f.Interaction.ObservationSaves);
            }
        });
    }

    private sealed class ProtectionObservationResultBattery : IBatteryStatusProvider
    {
        public BatterySnapshot Result = new BatterySnapshot(43, ExternalPowerStatus.Connected, BatteryChargeState.Charging, string.Empty);
        public BatterySnapshot Read() { return Result; }
    }
}
