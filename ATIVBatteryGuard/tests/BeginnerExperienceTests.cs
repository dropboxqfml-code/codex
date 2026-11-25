using System;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using System.Xml.Linq;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterBeginnerExperienceTests()
    {
        Add("940X3G model display preserves raw firmware identity and does not turn display aliases into write authorization", () =>
        {
            var device = KnownDevice();
            Equal("940X3G", device.DisplayModel); Equal("940X3G/930X3G", device.Model);
            Check(!DeviceSupportAssessment.Evaluate(device).HardwareWriteAllowed, "display authorized a hardware write");
            foreach (string model in new[] { "NP940X3G-K01", "940X3G", "940x3g/firmware-family" })
                Equal("940X3G", new DeviceDiagnosticsResult(model: model).DisplayModel);
            foreach (string model in new[] { "930X3G", "940X3G2", "different model" })
            {
                var other = new DeviceDiagnosticsResult(model: model); Equal("940X3G 대상과 다름", other.DisplayModel); Equal(model, other.Model);
                Check(!DeviceSupportAssessment.Evaluate(other).HardwareWriteAllowed, "mismatched display authorized write");
            }
            Equal("알 수 없음", new DeviceDiagnosticsResult().DisplayModel);
        });

        Add("device diagnostic and detailed report use 940X3G display and describe read-only collection without denying the separate control feature", () =>
        {
            var device = KnownDevice();
            string[] displays = { device.ToDisplayText(), new HardwareProbeReport(device: device).ToDisplayText(), SupportInquiryFormatter.Format(device) };
            foreach (string text in displays) Check(text.Contains("940X3G") && !text.Contains("930X3G"), "other model leaked into presentation");
            Check(device.ToDisplayText().Contains("현재 설정 확인") && !device.ToDisplayText().Contains("실제 충전 제어: 미지원"), "obsolete diagnostic instructions remain");
            Check(!new HardwareProbeReport(device: device).ToDisplayText().Contains("실제 충전 제어: 미지원"), "detailed report denies the control feature");
            Equal("940X3G/930X3G", device.Model);
        });

        Add("section navigation keeps the battery home as default and never invokes a device diagnostics timer or file action", () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService(); var battery = new OfflineReviewCountingBattery();
                using (var vm = ManualVm(f, service, battery))
                {
                    int reads = battery.Calls; Equal(0, vm.SelectedSection);
                    for (int i = 0; i < 30; i++)
                    {
                        vm.OpenRecordingSectionCommand.Execute(null); Equal(1, vm.SelectedSection);
                        vm.SelectedSection = 2; Equal(2, vm.SelectedSection); vm.SelectedSection = -1; vm.SelectedSection = 3; Equal(2, vm.SelectedSection);
                        vm.SelectedSection = 0;
                    }
                    Equal(reads, battery.Calls); Equal(0, service.Operations.Count); Equal(0, f.Interaction.Saves); Equal(0, f.Interaction.ObservationSaves);
                    Check(!vm.ObservationActive && !vm.SavedObservationVisible && !vm.IsMockMode, "navigation created data or enabled mock");
                    vm.Dispose(); vm.SelectedSection = 2; vm.OpenRecordingSectionCommand.Execute(null); Equal(0, vm.SelectedSection);
                }
            }
        });

        AddAsync("first-use charge guidance follows accepted read results and not the Windows battery percentage", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService { Handler = (op, phase) => Task.FromResult(PresentationRead(1, 80, 75)) };
                using (var vm = ManualVm(f, service))
                {
                    Check(vm.FirstUseGuidanceVisible && vm.ProtectionSummaryText.Contains("확인하세요"), "new-user state unclear");
                    Check(!vm.ManualEnableProtectionCommand.CanExecute(null) && vm.ProtectionActionHint.Contains("먼저"), "settings enabled before explicit read");
                    int changed = 0; vm.PropertyChanged += (sender, args) => { if (args.PropertyName == "ProtectionSummaryText") changed++; };
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Check(!vm.FirstUseGuidanceVisible && vm.ProtectionSummaryText.Contains("마지막 확인") && vm.ProtectionSummaryText.Contains("80%"), "accepted read not shown");
                    Check(vm.ManualEnableProtectionCommand.CanExecute(null) && changed > 0, "new labels not notified");
                    vm.InvalidateManualState();
                    Check(vm.FirstUseGuidanceVisible && !vm.ProtectionSummaryText.Contains("80%"), "stale read still appears current");
                    Equal(1, service.Operations.Count); Equal(0, f.Interaction.ObservationSaves);
                }
            }
        });

        AddAsync("unsupported charge response points to diagnostics while upper-unknown responses never invent 80 percent", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService { Handler = (op, phase) => Task.FromResult(ManualProtectionResult.Failure(op, ManualProtectionStatus.Unsupported, true)) };
                using (var vm = ManualVm(f, service))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Check(vm.ProtectionActionHint.Contains("도움말·진단") && !vm.ManualEnableProtectionCommand.CanExecute(null), "unsupported device lacks safe next step");
                    service.Handler = (op, phase) => Task.FromResult(PresentationRead(1, 255, 255));
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Check(vm.ProtectionSummaryText.Contains("상한 미확인") && !vm.ProtectionSummaryText.Contains("80%"), "mode one became 80 percent");
                }
            }
        });

        Add("beginner interface keeps three purposeful sections and required charging recording and diagnostic actions", () =>
        {
            var document = BeginnerWindow(); XNamespace ui = "http://schemas.microsoft.com/winfx/2006/xaml/presentation";
            XNamespace x = "http://schemas.microsoft.com/winfx/2006/xaml";
            var tabs = document.Descendants(ui + "TabItem").ToArray(); Equal(3, tabs.Length);
            Equal("배터리", (string)tabs[0].Attribute("Header")); Equal("기록", (string)tabs[1].Attribute("Header")); Equal("도움말·진단", (string)tabs[2].Attribute("Header"));
            foreach (string action in new[] { "ManualReadProtectionButton", "ManualEnableProtectionButton", "ManualDisableProtectionButton" })
                Check(tabs[0].Descendants(ui + "Button").Any(e => (string)e.Attribute(x + "Name") == action), "core charging action missing from home");
            foreach (string action in new[] { "StartBatteryObservationButton", "SaveBatteryObservationButton", "OpenSavedObservationButton", "ExportObservationBundleButton", "ImportComparisonBundleButton" })
                Check(tabs[1].Descendants(ui + "Button").Any(e => (string)e.Attribute(x + "Name") == action), "record function removed");
            Check(tabs[2].Descendants(ui + "Button").Any(e => (string)e.Attribute(x + "Name") == "ReadDiagnosticsButton"), "basic diagnostics unavailable");
            Check(tabs.All(t => t.Elements(ui + "ScrollViewer").Any()), "a section cannot scroll at small sizes");
        });

        AddAsync("successful diagnostics clear routine footer notices while copy results failures and settings warnings remain visible", async () =>
        {
            using (var f = new Fixture())
            using (var vm = ManualVm(f, new ManualVmService()))
            {
                Check(!vm.HasStatusNotice, "startup still shows a routine notice");
                int changes = 0; vm.PropertyChanged += (sender, args) => { if (args.PropertyName == "HasStatusNotice") changes++; };
                await vm.RefreshDiagnosticsAsync();
                Check(vm.DiagnosticsSucceeded && !vm.HasStatusNotice && vm.StatusMessage == "", "successful diagnosis left a footer notice");
                vm.CopyDiagnosticsCommand.Execute(null); Check(vm.HasStatusNotice && vm.StatusMessage.Contains("복사"), "copy feedback was lost");
                f.Interaction.Reader = () => throw new InvalidOperationException("PRIVATE");
                await vm.RefreshDiagnosticsAsync();
                Check(vm.HasStatusNotice && vm.StatusMessage.Contains("실패") && !vm.StatusMessage.Contains("PRIVATE"), "diagnostic failure hidden or leaked");
                Check(changes > 0, "footer visibility was not notified");
            }
            using (var f = new Fixture())
            {
                System.IO.File.WriteAllText(f.Store.FilePath, "{\"schemaVersion\":99}");
                using (var vm = ManualVm(f, new ManualVmService()))
                    Check(vm.HasStatusNotice && vm.SettingsWarning.Length > 0, "settings warning hidden");
            }
        });

        Add("production interface excludes inactive preferences simulations historical experiments inquiry drafts and file research controls", () =>
        {
            var document = BeginnerWindow(); XNamespace x = "http://schemas.microsoft.com/winfx/2006/xaml";
            string[] removed = { "MockSwitch", "MockApplyButton", "SavePreferencesButton", "ProtectionChoice", "NormalChoice", "ProtectionResultInput", "FixedReadResultInput", "ExperimentResultInput", "InspectSamsungFilesButton" };
            foreach (string name in removed) Check(!document.Descendants().Any(e => (string)e.Attribute(x + "Name") == name), "development control remains reachable");
            string markup = document.ToString();
            foreach (string phrase in new[] { "930X3G", "Query65", "Access1", "RestoreOnBoot", "SupportInquiryText", "InspectSamsungFilesCommand" })
                Check(!markup.Contains(phrase), "unnecessary technical feature exposed");
            Check(markup.Contains("SettingsWarning") && markup.Contains("ManualProtectionNotice") && markup.Contains("ManualProtectionText"), "safety feedback was removed with development tools");
        });
    }

    private static XDocument BeginnerWindow()
    {
        using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("Beginner.MainWindow.xaml"))
            return XDocument.Load(stream);
    }
}
