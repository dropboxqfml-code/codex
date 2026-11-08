using System;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.ViewModels;

internal static partial class Program
{
    private static void RegisterFixedReadAccess1ReviewViewModelTests()
    {
        Add("Access1 review starts empty and never supplies a current hardware mode", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                Equal(WsabiWmiFixedReadAccess1ReviewStatus.NotLoaded, vm.FixedReadReviewStatus);
                Equal<int?>(null, vm.FixedReadReviewStoredModeCandidate);
                Check(!vm.FixedReadReviewHasReportedStoredModeCandidate && !vm.CanApply, "startup inferred device support");
                Check(!vm.ReviewFixedReadResultCommand.CanExecute(null), "empty historical input actionable");
                Check(vm.ActualModeText.Contains("미지원"), "actual mode gained live support");
            }
        });
        Add("Access1 review preserves battery settings controllers providers and local files", () =>
        {
            using (var f = new Fixture())
            {
                var battery = new OfflineReviewCountingBattery();
                f.Interaction.Reader = () => { throw new InvalidOperationException("PRIVATE-DIAGNOSTIC"); };
                f.Hardware.Reader = () => { throw new InvalidOperationException("PRIVATE-HARDWARE"); };
                using (var vm = new MainViewModel(battery, f.Store, new LocalLog(f.DirectoryPath),
                    f.Interaction, f.Hardware, f.Bundle, () => true, f.Files))
                {
                    string actual = vm.ActualModeText, desired = vm.DesiredModeText, percent = vm.BatteryPercentText;
                    string status = vm.StatusMessage, mock = vm.MockActualModeText, reason = vm.SupportReason;
                    bool restore = vm.RestoreOnBoot, protection = vm.IsProtectionSelected;
                    int reads = battery.Calls; var before = OfflineReviewFileSnapshot(f.DirectoryPath);
                    vm.FixedReadReviewInput = FixedReadAccess1ReviewFixture(0);
                    vm.ReviewFixedReadResultCommand.Execute(null);
                    Equal(WsabiWmiFixedReadAccess1ReviewStatus.ReportedStoredModeCandidate, vm.FixedReadReviewStatus);
                    Equal<int?>(0, vm.FixedReadReviewStoredModeCandidate);
                    Check(vm.FixedReadReviewHasReportedStoredModeCandidate, "reported zero lost");
                    Equal(string.Empty, vm.FixedReadReviewInput);
                    Equal(actual, vm.ActualModeText); Equal(desired, vm.DesiredModeText); Equal(percent, vm.BatteryPercentText);
                    Equal(status, vm.StatusMessage); Equal(mock, vm.MockActualModeText); Equal(reason, vm.SupportReason);
                    Equal(restore, vm.RestoreOnBoot); Equal(protection, vm.IsProtectionSelected);
                    Check(!vm.CanApply && !vm.IsMockMode, "record enabled a write");
                    Equal(reads, battery.Calls); Equal(0, f.Files.Calls); Equal(0, f.Bundle.Calls);
                    Equal(0, f.Interaction.Saves); Equal(0, f.Interaction.Copies); Equal(0, f.Interaction.FileInspectionSaves);
                    OfflineReviewAssertSameFiles(before, f.DirectoryPath);
                }
            }
        });
        Add("Access1 editing rejected oversized and cleared input remove an older candidate", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                vm.FixedReadReviewInput = FixedReadAccess1ReviewFixture(1); vm.ReviewFixedReadResult();
                Equal<int?>(1, vm.FixedReadReviewStoredModeCandidate);
                vm.FixedReadReviewInput = string.Empty;
                Equal<int?>(1, vm.FixedReadReviewStoredModeCandidate); // Empty binding echo after review.
                vm.FixedReadReviewInput = "replacement incomplete";
                Equal(WsabiWmiFixedReadAccess1ReviewStatus.NotLoaded, vm.FixedReadReviewStatus);
                Equal<int?>(null, vm.FixedReadReviewStoredModeCandidate);
                vm.ReviewFixedReadResult();
                Check(!vm.FixedReadReviewHasReportedStoredModeCandidate, "invalid replacement retained candidate");
                vm.FixedReadReviewInput = FixedReadAccess1ReviewFixture(0); vm.ReviewFixedReadResult();
                vm.FixedReadReviewInput = FixedReadAccess1ReviewFixture(0) + new string('x', WsabiWmiFixedReadAccess1ReviewParser.MaximumCharacters);
                Equal(WsabiWmiFixedReadAccess1ReviewStatus.InvalidInput, vm.FixedReadReviewStatus);
                Equal(string.Empty, vm.FixedReadReviewInput); Equal<int?>(null, vm.FixedReadReviewStoredModeCandidate);
                Check(!vm.ReviewFixedReadResultCommand.CanExecute(null), "rejected raw input remains actionable");
                vm.ClearFixedReadReviewCommand.Execute(null);
                Equal(WsabiWmiFixedReadAccess1ReviewStatus.NotLoaded, vm.FixedReadReviewStatus);
            }
        });
        Add("Access1 and Query65 offline records cannot overwrite or upgrade each other", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                vm.ExperimentReviewInput = OfflineReviewViewModelReport(); vm.ReviewExperimentResult();
                string oldReview = vm.ExperimentReviewText;
                vm.FixedReadReviewInput = FixedReadAccess1ReviewFixture(0); vm.ReviewFixedReadResult();
                Equal(oldReview, vm.ExperimentReviewText);
                string fixedReview = vm.FixedReadReviewText;
                vm.ClearExperimentReviewCommand.Execute(null);
                Equal(fixedReview, vm.FixedReadReviewText); Equal<int?>(0, vm.FixedReadReviewStoredModeCandidate);
                vm.FixedReadReviewInput = OfflineReviewViewModelReport(); vm.ReviewFixedReadResult();
                Check(!vm.FixedReadReviewHasReportedStoredModeCandidate && !vm.CanApply, "Query65 accepted as fixed read");
            }
        });
        Add("Access1 review drops raw identity input and does not retain it in result or storage", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                var before = OfflineReviewFileSnapshot(f.DirectoryPath);
                string diagnostics = vm.DiagnosticsText, files = vm.SamsungFileInspectionText;
                vm.FixedReadReviewInput = FixedReadAccess1ReviewFixture(0) +
                    "\n추가 참고: C:\\Users\\PrivateName\\result.txt\nID: S-1-5-21-private";
                vm.ReviewFixedReadResult();
                Equal(string.Empty, vm.FixedReadReviewInput);
                Check(!vm.FixedReadReviewText.Contains("PrivateName") && !vm.FixedReadReviewText.Contains("S-1-5-21-private"),
                    "private data escaped historical result");
                Equal(diagnostics, vm.DiagnosticsText); Equal(files, vm.SamsungFileInspectionText);
                OfflineReviewAssertSameFiles(before, f.DirectoryPath);
            }
        });
        Add("Access1 clear dispose and mock isolation cannot enable a physical action", () =>
        {
            using (var f = new Fixture())
            {
                var vm = f.ViewModel(); vm.IsMockMode = true;
                string mock = vm.MockActualModeText; string desired = vm.DesiredModeText;
                vm.FixedReadReviewInput = FixedReadAccess1ReviewFixture(1); vm.ReviewFixedReadResult();
                Equal(mock, vm.MockActualModeText); Equal(desired, vm.DesiredModeText);
                vm.IsMockMode = false; Check(!vm.CanApply, "historical one enabled hardware apply");
                vm.ClearFixedReadReviewCommand.Execute(null);
                Equal<int?>(null, vm.FixedReadReviewStoredModeCandidate);
                vm.FixedReadReviewInput = "PRIVATE-PENDING"; vm.Dispose();
                Equal(string.Empty, vm.FixedReadReviewInput);
                string prior = vm.FixedReadReviewText; int changes = 0;
                vm.PropertyChanged += (sender, args) => changes++;
                vm.FixedReadReviewInput = FixedReadAccess1ReviewFixture(0); vm.ReviewFixedReadResult();
                vm.ReviewFixedReadResultCommand.Execute(null); vm.ClearFixedReadReviewCommand.Execute(null);
                Equal(string.Empty, vm.FixedReadReviewInput); Equal(prior, vm.FixedReadReviewText); Equal(0, changes);
                Check(!vm.ReviewFixedReadResultCommand.CanExecute(null) && !vm.ClearFixedReadReviewCommand.CanExecute(null),
                    "disposed record command enabled");
            }
        });
    }
}
