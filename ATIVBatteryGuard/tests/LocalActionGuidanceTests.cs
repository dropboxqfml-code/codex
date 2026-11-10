using System;
using System.IO;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

internal static partial class Program
{
    private static void RegisterLocalActionGuidanceTests()
    {
        Add("folder opening reports its own success beside both saves without creating data or reading a clock", () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService(); var clock = new ManualUsabilityClock();
                var battery = new OfflineReviewCountingBattery();
                using (var vm = ManualUsabilityVm(f, service, clock, battery))
                {
                    int reads = battery.Calls;
                    string manualBefore = vm.ManualSaveStatusText, observationBefore = vm.ObservationSaveStatusText;
                    int manualChanges = 0, observationChanges = 0;
                    vm.PropertyChanged += (sender, args) =>
                    {
                        if (args.PropertyName == "ManualSaveStatusText") manualChanges++;
                        if (args.PropertyName == "ObservationSaveStatusText") observationChanges++;
                    };
                    vm.OpenSettingsFolderCommand.Execute(null);
                    Check(vm.ManualSaveStatusText.StartsWith(manualBefore + "\n") &&
                        vm.ObservationSaveStatusText.StartsWith(observationBefore + "\n"), "folder feedback replaced an existing save instruction");
                    Check(vm.ManualSaveStatusText.Contains("저장 폴더를 열었습니다") &&
                        vm.ObservationSaveStatusText.Contains("저장 폴더를 열었습니다"), "folder success is absent from a save area");
                    Check(!vm.ManualSaveStatusText.Contains("저장 완료") && !vm.ObservationSaveStatusText.Contains("저장 완료"), "opening a folder claimed a TXT save");
                    Check(manualChanges > 0 && observationChanges > 0, "folder result did not notify local bindings");
                    Check(!vm.ManualSaveFailed && !vm.ObservationSaveFailed &&
                        !vm.ManualSaveResultCommand.CanExecute(null) && !vm.SaveBatteryObservationCommand.CanExecute(null), "folder success fabricated saved data or an error");
                    Equal(1, f.Interaction.FoldersOpened); Equal(0, f.Interaction.ManualResultSaves);
                    Equal(0, f.Interaction.ObservationSaves); Equal(0, f.Interaction.Saves);
                    Equal(0, service.Operations.Count); Equal(0, clock.Calls); Equal(reads, battery.Calls);
                }
            }
        });

        AddAsync("folder failure and recovery preserve saved filenames exports and duplicate-save gates", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService(); var clock = new ManualUsabilityClock();
                var battery = new OfflineReviewCountingBattery();
                using (var vm = ManualUsabilityVm(f, service, clock, battery))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    f.Interaction.ManualResultSaver = text => "제어 결과 저장 완료: manual-control-example.txt";
                    f.Interaction.ObservationSaver = text => "관찰 TXT 저장 완료: battery-observation-example.txt";
                    vm.ManualSaveResultCommand.Execute(null);
                    vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); vm.StopBatteryObservationCommand.Execute(null);
                    vm.SaveBatteryObservationCommand.Execute(null);
                    string manual = vm.ManualSaveStatusText, observation = vm.ObservationSaveStatusText;
                    string report = f.Interaction.LastManualResult, samples = f.Interaction.LastObservation;
                    string receipt = vm.ManualProtectionReadTimeText, notice = vm.ManualProtectionNotice;
                    var result = vm.ManualProtectionLastResult;
                    int reads = battery.Calls;
                    f.Interaction.FolderOpener = () => { throw new IOException(@"C:\Users\PRIVATE-ACCOUNT\PRIVATE-FOLDER-ERROR"); };
                    vm.OpenSettingsFolderCommand.Execute(null);
                    Check(vm.ManualSaveStatusText.StartsWith(manual + "\n") && vm.ObservationSaveStatusText.StartsWith(observation + "\n"), "folder failure erased a successful filename or export history");
                    Check(vm.ManualSaveFailed && vm.ObservationSaveFailed &&
                        vm.ManualSaveStatusText.Contains("저장 폴더를 열지 못했습니다") && vm.ObservationSaveStatusText.Contains("저장 폴더를 열지 못했습니다"), "folder failure is not visibly an error beside each save");
                    Check(!vm.ManualSaveStatusText.Contains("PRIVATE-ACCOUNT") && !vm.ObservationSaveStatusText.Contains("PRIVATE-FOLDER-ERROR") &&
                        !vm.StatusMessage.Contains("PRIVATE-ACCOUNT"), "folder exception leaked into the UI");
                    Check(!File.ReadAllText(Path.Combine(f.DirectoryPath, "application.log")).Contains("PRIVATE-"), "folder exception leaked into the log");
                    vm.ManualSaveResultCommand.Execute(null); vm.SaveBatteryObservationCommand.Execute(null);
                    f.Interaction.FolderOpener = null; vm.OpenSettingsFolderCommand.Execute(null);
                    Check(vm.ManualSaveStatusText.StartsWith(manual + "\n") && vm.ObservationSaveStatusText.StartsWith(observation + "\n"), "folder recovery erased a successful filename or export history");
                    Check(!vm.ManualSaveFailed && !vm.ObservationSaveFailed &&
                        !vm.ManualSaveStatusText.Contains("열지 못했습니다") && !vm.ObservationSaveStatusText.Contains("열지 못했습니다"), "folder recovery retained its old error");
                    Check(!vm.ManualSaveResultCommand.CanExecute(null) && !vm.SaveBatteryObservationCommand.CanExecute(null), "folder action reset duplicate-save markers");
                    Equal(report, f.Interaction.LastManualResult); Equal(samples, f.Interaction.LastObservation);
                    Equal(receipt, vm.ManualProtectionReadTimeText); Equal(notice, vm.ManualProtectionNotice);
                    Check(ReferenceEquals(result, vm.ManualProtectionLastResult) && vm.ManualEnableProtectionCommand.CanExecute(null), "folder action changed known manual control state");
                    Equal(2, f.Interaction.FoldersOpened); Equal(1, f.Interaction.ManualResultSaves); Equal(1, f.Interaction.ObservationSaves);
                    Equal(1, service.Operations.Count); Equal(2, clock.Calls); Equal(reads, battery.Calls);
                }
            }
        });

        AddAsync("folder recovery leaves actual save failures visible and permits saving the same data", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService(); var clock = new ManualUsabilityClock();
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); vm.StopBatteryObservationCommand.Execute(null);
                    f.Interaction.ManualResultSaver = text => { throw new IOException("PRIVATE-SAVE-ERROR"); };
                    f.Interaction.ObservationSaver = text => { throw new IOException("PRIVATE-SAVE-ERROR"); };
                    vm.ManualSaveResultCommand.Execute(null); vm.SaveBatteryObservationCommand.Execute(null);
                    string manual = vm.ManualSaveStatusText, observation = vm.ObservationSaveStatusText;
                    string report = f.Interaction.LastManualResult, samples = f.Interaction.LastObservation;
                    f.Interaction.FolderOpener = () => { throw new IOException("PRIVATE-FOLDER-ERROR"); };
                    vm.OpenSettingsFolderCommand.Execute(null);
                    f.Interaction.FolderOpener = null; vm.OpenSettingsFolderCommand.Execute(null);
                    Check(vm.ManualSaveFailed && vm.ObservationSaveFailed, "opening a folder cleared an actual save failure");
                    Check(vm.ManualSaveStatusText.StartsWith(manual + "\n") && vm.ObservationSaveStatusText.StartsWith(observation + "\n"), "opening a folder replaced actual save failure guidance");
                    Check(vm.ManualSaveResultCommand.CanExecute(null) && vm.SaveBatteryObservationCommand.CanExecute(null), "folder action consumed unsaved data");
                    f.Interaction.ManualResultSaver = text => "manual-control-recovered.txt 저장 완료";
                    f.Interaction.ObservationSaver = text => "battery-observation-recovered.txt 저장 완료";
                    vm.ManualSaveResultCommand.Execute(null); vm.SaveBatteryObservationCommand.Execute(null);
                    Equal(report, f.Interaction.LastManualResult); Equal(samples, f.Interaction.LastObservation);
                    Check(!vm.ManualSaveFailed && !vm.ObservationSaveFailed, "actual successful saves retained an error");
                    Check(!vm.ManualSaveResultCommand.CanExecute(null) && !vm.SaveBatteryObservationCommand.CanExecute(null), "successful save recovery lost deduplication");
                    Equal(2, f.Interaction.ManualResultSaves); Equal(2, f.Interaction.ObservationSaves);
                    Equal(1, service.Operations.Count); Equal(2, clock.Calls);
                }
            }
        });

        AddAsync("folder feedback preserves every unconfirmed cleanup hold without read or restart advice", async () =>
        {
            foreach (var status in new[] { ManualProtectionStatus.TimedOut, ManualProtectionStatus.Unknown })
            using (var f = new Fixture())
            {
                var service = new ManualVmService { Handler = (op, progress) => Task.FromResult(ManualProtectionResult.Failure(op, status)) };
                var clock = new ManualUsabilityClock();
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    string hold = vm.ManualProtectionNotice;
                    Check(hold.Contains("실제 정리 완료를 기다리세요") && !hold.Contains("보호 상태 확인을 직접") &&
                        !hold.Contains("정리는 끝났"), "status-specific advice overrode the cleanup hold: " + status);
                    f.Interaction.FolderOpener = () => { throw new IOException("PRIVATE-PENDING-FOLDER"); };
                    vm.OpenSettingsFolderCommand.Execute(null);
                    Check(!vm.ManualSaveStatusText.Contains("다시 누르") && !vm.ManualSaveStatusText.Contains("다시 실행") &&
                        !vm.ManualSaveStatusText.Contains("보호 상태 확인"), "folder failure advised a device retry or restart during cleanup");
                    Equal(hold, vm.ManualProtectionNotice);
                    vm.ManualSaveResultCommand.Execute(null);
                    f.Interaction.FolderOpener = null; vm.OpenSettingsFolderCommand.Execute(null);
                    Equal(hold, vm.ManualProtectionNotice);
                    Check(vm.ManualProtectionPending && vm.ManualProtectionBusy && !vm.ManualReadProtectionCommand.CanExecute(null) &&
                        !vm.ManualEnableProtectionCommand.CanExecute(null) && !vm.ManualDisableProtectionCommand.CanExecute(null), "folder feedback or export released an unconfirmed cleanup hold");
                    Check(!vm.ManualSaveResultCommand.CanExecute(null), "folder recovery made a saved pending report saveable again");
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Equal(1, service.Operations.Count); Equal(2, clock.Calls); Equal(1, f.Interaction.ManualResultSaves);
                    Check(f.Interaction.LastManualResult.Contains("미관측") && !f.Interaction.LastManualResult.Contains("SDK 진입: 0"), "pending export inferred zero hardware calls");
                }
            }
        });

        AddAsync("cancelled manual confirmation covers UAC and helper without inferring hardware execution", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService { Handler = (op, progress) => Task.FromResult(ManualProtectionResult.Failure(op, ManualProtectionStatus.Cancelled, true)) };
                var clock = new ManualUsabilityClock();
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Check(vm.ManualProtectionNotice.Contains("UAC") && vm.ManualProtectionNotice.Contains("helper") &&
                        vm.ManualProtectionNotice.Contains("취소") && vm.ManualProtectionNotice.Contains("보호 상태 확인"), "cancellation guidance assumes only one confirmation stage");
                    Check(!vm.ManualProtectionNotice.Contains("호출하지 않았") && !vm.ManualProtectionNotice.Contains("호출0") &&
                        !vm.ManualProtectionNotice.Contains("호출 0"), "cancellation notice inferred a hardware call count");
                    Check(!vm.ManualProtectionPending && vm.ManualReadProtectionCommand.CanExecute(null) &&
                        !vm.ManualEnableProtectionCommand.CanExecute(null) && !vm.ManualDisableProtectionCommand.CanExecute(null), "cancellation wording changed state gates");
                    Equal("마지막 보호 조회 결과 수신: 미관측", vm.ManualProtectionReadTimeText);
                    Equal(1, service.Operations.Count); Equal(2, clock.Calls);
                }
            }
        });

        AddAsync("device diagnostic failure is scoped to that diagnostic and preserves manual state and exports", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService(); var clock = new ManualUsabilityClock();
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    var result = vm.ManualProtectionLastResult; string receipt = vm.ManualProtectionReadTimeText;
                    f.Interaction.Reader = () => { throw new IOException("PRIVATE-DIAGNOSTIC-ERROR"); };
                    await vm.RefreshDiagnosticsAsync();
                    Check(vm.DiagnosticsText.Contains("이 진단") && !vm.DiagnosticsText.Contains("제어는 차단") &&
                        !vm.DiagnosticsText.Contains("PRIVATE-DIAGNOSTIC-ERROR"), "diagnostic failure claimed unrelated control was disabled or leaked its exception");
                    Check(!vm.DiagnosticsSucceeded && vm.CanExportDiagnostics && vm.SaveDiagnosticsCommand.CanExecute(null), "failed diagnostic lost its legacy export behavior");
                    vm.SaveDiagnosticsCommand.Execute(null); Equal(1, f.Interaction.Saves);
                    Check(ReferenceEquals(result, vm.ManualProtectionLastResult) && vm.ManualReadProtectionCommand.CanExecute(null) &&
                        vm.ManualEnableProtectionCommand.CanExecute(null) && vm.ManualDisableProtectionCommand.CanExecute(null), "read-only diagnostic failure changed manual control gates");
                    Equal(receipt, vm.ManualProtectionReadTimeText); Equal(1, service.Operations.Count); Equal(2, clock.Calls);
                }
            }
        });

        AddAsync("hardware report failure is scoped to that report and preserves manual control candidates", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService(); var clock = new ManualUsabilityClock();
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    var result = vm.ManualProtectionLastResult; string receipt = vm.ManualProtectionReadTimeText;
                    f.Hardware.Reader = () => { throw new IOException("PRIVATE-HARDWARE-DIAGNOSTIC-ERROR"); };
                    await vm.CreateHardwareReportAsync();
                    Check(vm.HardwareReportStatus.Contains("이번 진단") && !vm.HardwareReportStatus.Contains("실제 제어는 차단") &&
                        !vm.HardwareReportStatus.Contains("PRIVATE-HARDWARE-DIAGNOSTIC-ERROR"), "hardware diagnostic failure claimed unrelated control was disabled or leaked its exception");
                    Check(ReferenceEquals(result, vm.ManualProtectionLastResult) && vm.ManualReadProtectionCommand.CanExecute(null) &&
                        vm.ManualEnableProtectionCommand.CanExecute(null) && vm.ManualDisableProtectionCommand.CanExecute(null), "report failure changed manual control gates");
                    Equal(receipt, vm.ManualProtectionReadTimeText); Equal(0, f.Interaction.Saves);
                    Equal(1, service.Operations.Count); Equal(2, clock.Calls);
                }
            }
        });

        AddAsync("Samsung file diagnostic failure preserves known manual state gates and receipt", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService(); var clock = new ManualUsabilityClock();
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    var result = vm.ManualProtectionLastResult; string receipt = vm.ManualProtectionReadTimeText;
                    f.Files.Reader = () => { throw new IOException("PRIVATE-SAMSUNG-FILE-DIAGNOSTIC-ERROR"); };
                    await vm.InspectSamsungFilesAsync();
                    Check(vm.SamsungFileInspectionStatus.Contains("이번 삼성 파일 진단 정보는 미확인") &&
                        !vm.SamsungFileInspectionStatus.Contains("실제 충전 제어는 차단") &&
                        !vm.SamsungFileInspectionStatus.Contains("PRIVATE-SAMSUNG-FILE-DIAGNOSTIC-ERROR") &&
                        !vm.SamsungFileInspectionText.Contains("PRIVATE-SAMSUNG-FILE-DIAGNOSTIC-ERROR"), "Samsung file diagnostic failure misrepresented control state or leaked its exception");
                    Check(ReferenceEquals(result, vm.ManualProtectionLastResult) && vm.ManualReadProtectionCommand.CanExecute(null) &&
                        vm.ManualEnableProtectionCommand.CanExecute(null) && vm.ManualDisableProtectionCommand.CanExecute(null), "Samsung file diagnostic failure changed manual control gates");
                    Equal(receipt, vm.ManualProtectionReadTimeText); Equal(0, f.Interaction.FileInspectionSaves);
                    Equal(1, f.Files.Calls); Equal(1, service.Operations.Count); Equal(2, clock.Calls);
                }
            }
        });

        AddAsync("folder feedback while a manual request runs cannot complete it or refresh receipt metadata", async () =>
        {
            using (var f = new Fixture())
            {
                var pending = new TaskCompletionSource<ManualProtectionResult>(TaskCreationOptions.RunContinuationsAsynchronously);
                var service = new ManualVmService { Handler = (op, progress) => pending.Task };
                var clock = new ManualUsabilityClock();
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    Task run = vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    string notice = vm.ManualProtectionNotice;
                    f.Interaction.FolderOpener = () => { throw new IOException("PRIVATE-ACTIVE-FOLDER"); };
                    vm.OpenSettingsFolderCommand.Execute(null);
                    f.Interaction.FolderOpener = null; vm.OpenSettingsFolderCommand.Execute(null);
                    Equal(notice, vm.ManualProtectionNotice);
                    Check(vm.ManualProtectionBusy && vm.ManualProtectionLastResult == null &&
                        !vm.ManualReadProtectionCommand.CanExecute(null) && !vm.ManualSaveResultCommand.CanExecute(null), "folder feedback completed a live request");
                    Equal("마지막 보호 조회 결과 수신: 미관측", vm.ManualProtectionReadTimeText);
                    Equal(1, clock.Calls); Equal(1, service.Operations.Count); Equal(0, f.Interaction.ManualResultSaves);
                    pending.SetResult(ManualVmRead(0)); await run;
                    Check(!vm.ManualProtectionBusy && vm.ManualSaveResultCommand.CanExecute(null), "actual request completion was lost after folder feedback");
                    Equal(2, clock.Calls); Equal(1, service.Operations.Count);
                }
            }
        });

        Add("disposed folder command cannot publish feedback or open a folder", () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService(); var clock = new ManualUsabilityClock();
                var vm = ManualUsabilityVm(f, service, clock); vm.Dispose();
                string manual = vm.ManualSaveStatusText, observation = vm.ObservationSaveStatusText;
                int changes = 0; vm.PropertyChanged += (sender, args) => changes++;
                Check(!vm.OpenSettingsFolderCommand.CanExecute(null), "disposed folder command remains enabled");
                vm.OpenSettingsFolderCommand.Execute(null);
                Equal(manual, vm.ManualSaveStatusText); Equal(observation, vm.ObservationSaveStatusText);
                Equal(0, f.Interaction.FoldersOpened); Equal(0, changes); Equal(0, clock.Calls); Equal(0, service.Operations.Count);
            }
        });
    }
}
