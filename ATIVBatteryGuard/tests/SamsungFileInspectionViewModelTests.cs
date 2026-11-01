using System;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.ViewModels;

internal static partial class Program
{
    private static void RegisterSamsungFileInspectionViewModelTests()
    {
        AddAsync("file inspection missing provider cannot run", async () =>
        {
            using (var f = new Fixture())
            using (var vm = new MainViewModel(new FakeBattery(), f.Store, new LocalLog(f.DirectoryPath), f.Interaction))
            {
                Check(!vm.InspectSamsungFilesCommand.CanExecute(null), "missing provider enabled");
                await vm.InspectSamsungFilesAsync(); Equal(0, f.Interaction.FileInspectionSaves);
            }
        });
        AddAsync("file inspection is explicit and saves metadata without enabling hardware", async () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                Equal(0, f.Files.Calls);
                vm.RefreshBattery(); Equal(0, f.Files.Calls);
                f.Files.Reader = InspectedFiles;
                await vm.InspectSamsungFilesAsync();
                Equal(1, f.Files.Calls); Equal(1, f.Interaction.FileInspectionSaves); Equal(0, f.Interaction.Saves);
                Equal(InspectedFiles().ToDisplayText(), vm.SamsungFileInspectionText);
                Equal(vm.SamsungFileInspectionText, f.Interaction.LastFileInspection);
                Check(!vm.CanApply && vm.ActualModeText.Contains("미지원"), "metadata enabled hardware");
                Check(!vm.SamsungFileInspectionBusy && vm.InspectSamsungFilesCommand.CanExecute(null), "command not restored");
            }
        });
        AddAsync("file inspection blocks repeats and clears stale displayed result", async () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel()) using (var gate = new Gate())
            {
                f.Files.Reader = InspectedFiles; await vm.InspectSamsungFilesAsync();
                string prior = vm.SamsungFileInspectionText;
                f.Files.Reader = () => { gate.Enter(); return new SamsungFileInspectionReport(SamsungFileInspectionStatus.TimedOut); };
                Task pending = vm.InspectSamsungFilesAsync(); await gate.WaitEntered();
                Check(vm.SamsungFileInspectionBusy && !vm.InspectSamsungFilesCommand.CanExecute(null), "busy command enabled");
                Check(vm.SamsungFileInspectionText != prior, "stale metadata displayed");
                await vm.InspectSamsungFilesAsync(); Equal(2, f.Files.Calls);
                gate.Release(); await pending;
                Equal(new SamsungFileInspectionReport(SamsungFileInspectionStatus.TimedOut).ToDisplayText(), vm.SamsungFileInspectionText);
                Check(!vm.CanApply, "timeout enabled control");
            }
        });
        AddAsync("file inspection failure hides prior facts and exception details", async () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                f.Files.Reader = InspectedFiles; await vm.InspectSamsungFilesAsync();
                f.Files.Reader = () => { throw new InvalidOperationException(@"C:\Users\PrivateName\secret.dll"); };
                await vm.InspectSamsungFilesAsync();
                Equal(new SamsungFileInspectionReport(SamsungFileInspectionStatus.Unavailable,
                    driverLink: SabiDriverLinkStatus.Unavailable,
                    kernelDrivers: new SamsungKernelDriverReport(SamsungDriverQueryStatus.Unavailable)).ToDisplayText(), vm.SamsungFileInspectionText);
                Equal(1, f.Interaction.FileInspectionSaves);
                Check(!vm.SamsungFileInspectionText.Contains("PrivateName") && !vm.SamsungFileInspectionStatus.Contains("PrivateName"), "exception exposed");
                f.Files.Reader = () => null; await vm.InspectSamsungFilesAsync();
                Check(!vm.SamsungFileInspectionBusy && !vm.CanApply, "null result unsafe");
                Check(vm.SamsungFileInspectionText.Contains("조회 오류로 확인할 수 없음"), "provider failure became unqueried");
            }
        });
        AddAsync("driver inventory is saved with SABI link even when Samsung folders are absent", async () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                var report = new SamsungFileInspectionReport(SamsungFileInspectionStatus.DirectoryNotFound,
                    driverLink: SabiDriverLinkStatus.NotFound,
                    kernelDrivers: new SamsungKernelDriverReport(SamsungDriverQueryStatus.Complete,
                        new[] { DriverEntry(SamsungDriverState.Running, SamsungDriverStartMode.Auto) }));
                f.Files.Reader = () => report;
                vm.RefreshBattery(); Equal(0, f.Files.Calls);
                await vm.InspectSamsungFilesAsync();
                Equal(1, f.Files.Calls); Equal(1, f.Interaction.FileInspectionSaves);
                Equal(report.ToDisplayText(), vm.SamsungFileInspectionText);
                Equal(report.ToDisplayText(), f.Interaction.LastFileInspection);
                Check(vm.SamsungFileInspectionText.Contains("등록 관측") && vm.SamsungFileInspectionText.Contains("동시에 가능합니다"), "driver/link comparison missing");
                Check(!vm.CanApply && vm.ActualModeText.Contains("미지원"), "running driver enabled control");
            }
        });
        AddAsync("driver timeout replaces previously running observations in screen and saved report", async () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                f.Files.Reader = () => new SamsungFileInspectionReport(SamsungFileInspectionStatus.DirectoryNotFound,
                    kernelDrivers: new SamsungKernelDriverReport(SamsungDriverQueryStatus.Complete, new[] { DriverEntry() }));
                await vm.InspectSamsungFilesAsync();
                Check(vm.SamsungFileInspectionText.Contains("등록 관측"), "initial observation missing");
                var timeout = new SamsungFileInspectionReport(SamsungFileInspectionStatus.TimedOut,
                    driverLink: SabiDriverLinkStatus.Unavailable,
                    kernelDrivers: new SamsungKernelDriverReport(SamsungDriverQueryStatus.TimedOut));
                f.Files.Reader = () => timeout;
                await vm.InspectSamsungFilesAsync();
                Equal(timeout.ToDisplayText(), vm.SamsungFileInspectionText);
                Equal(timeout.ToDisplayText(), f.Interaction.LastFileInspection);
                Check(!vm.SamsungFileInspectionText.Contains("등록 관측") && vm.SamsungFileInspectionText.Contains("조회 시간 초과"), "timeout retained running observation");
                Check(!vm.CanApply, "timeout enabled control");
            }
        });
        AddAsync("file inspection save failure keeps observed metadata available", async () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                f.Files.Reader = InspectedFiles;
                f.Interaction.FileInspectionSaver = text => { throw new InvalidOperationException("private save path"); };
                await vm.InspectSamsungFilesAsync();
                Equal(InspectedFiles().ToDisplayText(), vm.SamsungFileInspectionText);
                Check(vm.SamsungFileInspectionStatus.Contains("저장하지 못했습니다") && !vm.SamsungFileInspectionStatus.Contains("private"), "save error misrepresented");
                Check(!vm.CanApply, "save error enabled control");
            }
        });
        AddAsync("disposed file inspection cannot save or publish late metadata", async () =>
        {
            using (var f = new Fixture()) using (var gate = new Gate())
            {
                f.Files.Reader = () => { gate.Enter(); return InspectedFiles(); };
                var vm = f.ViewModel(); Task pending = vm.InspectSamsungFilesAsync(); await gate.WaitEntered();
                vm.Dispose(); string prior = vm.SamsungFileInspectionText;
                int changes = 0; vm.PropertyChanged += (sender, args) => changes++;
                gate.Release(); await pending;
                Equal(prior, vm.SamsungFileInspectionText); Equal(0, changes); Equal(0, f.Interaction.FileInspectionSaves);
                Check(!vm.InspectSamsungFilesCommand.CanExecute(null), "disposed command enabled");
                await vm.InspectSamsungFilesAsync(); Equal(1, f.Files.Calls);
            }
        });
    }

    private static SamsungFileInspectionReport InspectedFiles()
    {
        return new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, new[] {
            new SamsungFileInspectionEntry("Sabi3.dll", "Setting", SamsungFileEntryStatus.Inspected,
                length: 1024, fileVersion: "1.2.3.4", companyName: "Samsung", sha256: new string('a', 64),
                pe: new PeModuleInfo(true, false, "x86", new[] { "kernel32.dll" },
                    new[] { "InitBIOSInterface", "CheckSamsung", "CallBIOSInterface" }), signature: OfflineSignatureStatus.ValidOffline) });
    }
}
