using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.ViewModels;

internal static partial class Program
{
    private static void RegisterWsabiWmiExperimentReviewViewModelTests()
    {
        Add("offline experiment review cannot change hardware preferences mock state storage or provider calls", () =>
        {
            using (var fixture = new Fixture())
            {
                var battery = new OfflineReviewCountingBattery();
                fixture.Interaction.Reader = () => { throw new InvalidOperationException("diagnostic must stay idle"); };
                fixture.Hardware.Reader = () => { throw new InvalidOperationException("hardware must stay idle"); };
                using (var vm = new MainViewModel(battery, fixture.Store, new LocalLog(fixture.DirectoryPath),
                    fixture.Interaction, fixture.Hardware, fixture.Bundle, () => true, fixture.Files))
                {
                    string actual = vm.ActualModeText, desired = vm.DesiredModeText;
                    string mock = vm.MockActualModeText, status = vm.StatusMessage;
                    bool protection = vm.IsProtectionSelected, restore = vm.RestoreOnBoot;
                    int batteryReads = battery.Calls;
                    var before = OfflineReviewFileSnapshot(fixture.DirectoryPath);
                    vm.ExperimentReviewInput = OfflineReviewViewModelReport();
                    Check(vm.ReviewExperimentResultCommand.CanExecute(null), "pasted review is unavailable");
                    vm.ReviewExperimentResultCommand.Execute(null);
                    Equal(WsabiWmiExperimentReviewStatus.ValidatedFrameMeaningUnknown, vm.ExperimentReviewStatus);
                    Check(vm.ExperimentReviewHasValidatedFrame && vm.ExperimentReviewText.Contains("FF"),
                        "historical FF observation was lost");
                    Equal(string.Empty, vm.ExperimentReviewInput);
                    vm.ExperimentReviewInput = string.Empty;
                    Equal(WsabiWmiExperimentReviewStatus.ValidatedFrameMeaningUnknown, vm.ExperimentReviewStatus);
                    Check(vm.ExperimentReviewHasValidatedFrame, "an unchanged empty binding cleared the completed review");
                    Equal(actual, vm.ActualModeText); Equal(desired, vm.DesiredModeText);
                    Equal(mock, vm.MockActualModeText); Equal(status, vm.StatusMessage);
                    Equal(protection, vm.IsProtectionSelected); Equal(restore, vm.RestoreOnBoot);
                    Check(!vm.CanApply && !vm.IsMockMode, "review enabled a charge operation");
                    Equal(batteryReads, battery.Calls);
                    Equal(0, fixture.Files.Calls); Equal(0, fixture.Bundle.Calls);
                    Equal(0, fixture.Interaction.Saves); Equal(0, fixture.Interaction.Copies);
                    Equal(0, fixture.Interaction.FileInspectionSaves);
                    OfflineReviewAssertSameFiles(before, fixture.DirectoryPath);
                }
            }
        });
        Add("editing rejecting and oversizing pasted experiment text cannot retain a previous validated review", () =>
        {
            using (var fixture = new Fixture()) using (var vm = fixture.ViewModel())
            {
                vm.ExperimentReviewInput = OfflineReviewViewModelReport();
                vm.ReviewExperimentResult();
                Check(vm.ExperimentReviewHasValidatedFrame, "valid fixture was not reviewed");
                vm.ExperimentReviewInput = "incomplete replacement";
                Equal(WsabiWmiExperimentReviewStatus.NotLoaded, vm.ExperimentReviewStatus);
                Check(!vm.ExperimentReviewHasValidatedFrame, "edit retained historical success");
                vm.ReviewExperimentResultCommand.Execute(null);
                Equal(WsabiWmiExperimentReviewStatus.InvalidInput, vm.ExperimentReviewStatus);
                Equal(string.Empty, vm.ExperimentReviewInput);
                vm.ExperimentReviewInput = OfflineReviewViewModelReport(); vm.ReviewExperimentResult();
                vm.ExperimentReviewInput = OfflineReviewViewModelReport()
                    + new string('x', WsabiWmiExperimentReviewParser.MaximumCharacters);
                Equal(string.Empty, vm.ExperimentReviewInput);
                Equal(WsabiWmiExperimentReviewStatus.InvalidInput, vm.ExperimentReviewStatus);
                Check(!vm.ExperimentReviewHasValidatedFrame, "oversized input was truncated into success");
                Check(!vm.ReviewExperimentResultCommand.CanExecute(null), "rejected raw text remained actionable");
                vm.ExperimentReviewInput = string.Empty;
                Equal(WsabiWmiExperimentReviewStatus.InvalidInput, vm.ExperimentReviewStatus);
                vm.ExperimentReviewInput = null;
                Equal(string.Empty, vm.ExperimentReviewInput);
                Equal(WsabiWmiExperimentReviewStatus.InvalidInput, vm.ExperimentReviewStatus);
                vm.ClearExperimentReviewCommand.Execute(null);
                Equal(WsabiWmiExperimentReviewStatus.NotLoaded, vm.ExperimentReviewStatus);
            }
        });
        Add("offline review drops pasted identity text instead of copying it to results diagnostics logs or settings", () =>
        {
            using (var fixture = new Fixture()) using (var vm = fixture.ViewModel())
            {
                string diagnostics = vm.DiagnosticsText, hardware = vm.HardwareReportText;
                string files = vm.SamsungFileInspectionText, summary = vm.SamsungTransportSummary;
                var before = OfflineReviewFileSnapshot(fixture.DirectoryPath);
                vm.ExperimentReviewInput = OfflineReviewViewModelReport()
                    + "\n추가 참고: C:\\Users\\PrivateName\\private-result.txt\nID: S-1-5-21-private";
                vm.ReviewExperimentResult();
                Equal(WsabiWmiExperimentReviewStatus.ValidatedFrameMeaningUnknown, vm.ExperimentReviewStatus);
                Equal(string.Empty, vm.ExperimentReviewInput);
                Check(!vm.ExperimentReviewText.Contains("PrivateName")
                    && !vm.ExperimentReviewText.Contains(@"C:\Users")
                    && !vm.ExperimentReviewText.Contains("S-1-5-21-private"), "pasted identity leaked");
                Equal(diagnostics, vm.DiagnosticsText); Equal(hardware, vm.HardwareReportText);
                Equal(files, vm.SamsungFileInspectionText); Equal(summary, vm.SamsungTransportSummary);
                Equal(0, fixture.Interaction.Saves); Equal(0, fixture.Interaction.Copies);
                Equal(0, fixture.Interaction.FileInspectionSaves);
                OfflineReviewAssertSameFiles(before, fixture.DirectoryPath);
            }
        });
        Add("offline review clear and disposal discard input without allowing later review actions", () =>
        {
            using (var fixture = new Fixture())
            {
                var vm = fixture.ViewModel();
                Equal(WsabiWmiExperimentReviewStatus.NotLoaded, vm.ExperimentReviewStatus);
                Check(!vm.ReviewExperimentResultCommand.CanExecute(null), "empty review was enabled");
                vm.ExperimentReviewInput = OfflineReviewViewModelReport(); vm.ReviewExperimentResult();
                vm.ClearExperimentReviewCommand.Execute(null);
                Equal(WsabiWmiExperimentReviewStatus.NotLoaded, vm.ExperimentReviewStatus);
                Check(!vm.ExperimentReviewHasValidatedFrame, "clear retained the historical frame");
                Equal(string.Empty, vm.ExperimentReviewInput);
                vm.ExperimentReviewInput = "PrivateName pending input";
                vm.Dispose();
                Equal(string.Empty, vm.ExperimentReviewInput);
                string prior = vm.ExperimentReviewText;
                int changes = 0; vm.PropertyChanged += (sender, args) => changes++;
                vm.ExperimentReviewInput = OfflineReviewViewModelReport();
                vm.ReviewExperimentResult();
                vm.ReviewExperimentResultCommand.Execute(null);
                vm.ClearExperimentReviewCommand.Execute(null);
                Equal(string.Empty, vm.ExperimentReviewInput);
                Equal(prior, vm.ExperimentReviewText); Equal(0, changes);
                Check(!vm.ReviewExperimentResultCommand.CanExecute(null)
                    && !vm.ClearExperimentReviewCommand.CanExecute(null), "disposed review commands enabled");
                Check(!vm.CanApply && !vm.IsMockMode, "disposed review enabled control");
            }
        });
    }

    private static string OfflineReviewViewModelReport()
    {
        var reply = WsabiWmiReplyResult.FromMethodReply(OneShotExperimentBinder(1).DecodeOutput(0,
            OneShotExperimentOutput(OneShotExperimentReply(0xff))));
        var report = new WsabiWmiOneShotReport(WsabiWmiOneShotStatus.ResponseReceived,
            ProcessElevationState.Elevated, WsabiWmiMetadataStatus.Complete, true, reply,
            WsabiWmiOneShotPreflightStage.Ready);
        return "수정판: 승인된 단1회 조회 · 경로 정보 확보 보완 (Query65-locator-v2)\n" + report.ToDisplayText();
    }

    private static Dictionary<string, byte[]> OfflineReviewFileSnapshot(string directory)
        => Directory.GetFiles(directory, "*", SearchOption.AllDirectories)
            .ToDictionary(path => path, File.ReadAllBytes);

    private static void OfflineReviewAssertSameFiles(Dictionary<string, byte[]> expected, string directory)
    {
        var current = OfflineReviewFileSnapshot(directory);
        Equal(expected.Count, current.Count);
        foreach (var file in expected)
            Check(current.TryGetValue(file.Key, out byte[] data) && file.Value.SequenceEqual(data),
                "review created changed or removed a local file");
    }

    private sealed class OfflineReviewCountingBattery : IBatteryStatusProvider
    {
        internal int Calls;
        public BatterySnapshot Read()
        {
            Calls++;
            return new NativePowerReading(true, 1, 6, 0).ToSnapshot();
        }
    }
}
