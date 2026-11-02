using System;
using System.Linq;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterSamsungTransportAssessmentTests()
    {
        Add("observed stopped manual candidates and denied WMI retain independent meanings", () =>
        {
            var report = LatestTransportObservation();
            var result = SamsungTransportAssessment.Evaluate(report);
            Equal(7, result.DriverCandidates); Equal(7, result.StoppedManualCandidates);
            Check(result.DriverInventoryComplete && result.HasWmiAccessDenied, "observed results lost");
            string text = result.ToDisplayText();
            Check(text.Contains("권한 거부") && text.Contains("미관측") && text.Contains("중지·수동 시작 조합은 7개"), "facts missing");
            Check(text.Contains("관리자 실행이 해결한다는 근거도 없습니다") && text.Contains("원인으로 단정하지 않습니다"), "unsupported escalation or causal claim");
            Check(!result.CanReadHardware && !result.CanWriteHardware && !result.CanInvokeMethods, "observation authorized transport");
            var decoded = SamsungFileInspectionProtocol.Decode(SamsungFileInspectionProtocol.Encode(report));
            Equal(result.Summary, SamsungTransportAssessment.Evaluate(decoded).Summary);
            Equal(7, SamsungTransportAssessment.Evaluate(decoded).StoppedManualCandidates);
        });
        Add("WMI access denial never depends on a SABI name or the other class outcome", () =>
        {
            foreach (SabiDriverLinkStatus link in Enum.GetValues(typeof(SabiDriverLinkStatus)))
            foreach (SamsungWmiQueryStatus version in Enum.GetValues(typeof(SamsungWmiQueryStatus)))
            foreach (SamsungWmiQueryStatus method in Enum.GetValues(typeof(SamsungWmiQueryStatus)))
            {
                var wmi = new SamsungWmiInstanceReport(
                    new SamsungWmiClassObservation(SamsungWmiClass.Version, version),
                    new SamsungWmiClassObservation(SamsungWmiClass.Method, method));
                var result = SamsungTransportAssessment.Evaluate(new SamsungFileInspectionReport(driverLink: link, wmiInstances: wmi));
                Equal(version == SamsungWmiQueryStatus.AccessDenied || method == SamsungWmiQueryStatus.AccessDenied, result.HasWmiAccessDenied);
                Check(result.Summary.Contains(SamsungWmiInstanceReport.StatusText(version)) &&
                    result.Summary.Contains(SamsungWmiInstanceReport.StatusText(method)), "independent status hidden");
                Check(!result.CanReadHardware && !result.CanWriteHardware && !result.CanInvokeMethods, "status enabled control");
            }
        });
        Add("driver count describes only observed combinations without selecting a service", () =>
        {
            foreach (SamsungDriverState state in Enum.GetValues(typeof(SamsungDriverState)))
            foreach (SamsungDriverStartMode start in Enum.GetValues(typeof(SamsungDriverStartMode)))
            {
                var drivers = new SamsungKernelDriverReport(SamsungDriverQueryStatus.Partial,
                    new[] { new SamsungKernelDriverEntry(SamsungDriverCategory.SabiName, state, start) });
                var result = SamsungTransportAssessment.Evaluate(new SamsungFileInspectionReport(kernelDrivers: drivers));
                Equal(1, result.DriverCandidates);
                Equal(state == SamsungDriverState.Stopped && start == SamsungDriverStartMode.Manual ? 1 : 0, result.StoppedManualCandidates);
                Check(!result.DriverInventoryComplete && !result.CanInvokeMethods && !result.CanWriteHardware, "partial candidate enabled action");
                Check(result.ToDisplayText().Contains("시작 대상으로 선택하지 않습니다"), "candidate selected");
            }
        });
        Add("transport assessment clears failed inventories and remains unknown before collection", () =>
        {
            var failed = new SamsungFileInspectionReport(SamsungFileInspectionStatus.TimedOut,
                kernelDrivers: new SamsungKernelDriverReport(SamsungDriverQueryStatus.TimedOut, LatestTransportObservation().KernelDrivers.Entries),
                wmiInstances: SamsungWmiInstanceReport.Failure(SamsungWmiQueryStatus.TimedOut));
            var result = SamsungTransportAssessment.Evaluate(failed);
            Equal(0, result.DriverCandidates); Equal(0, result.StoppedManualCandidates);
            Check(!result.HasWmiAccessDenied && result.Summary.Contains("시간 초과"), "prior denial retained");
            var missing = SamsungTransportAssessment.Evaluate(null);
            Equal(0, missing.DriverCandidates);
            Check(missing.Summary.Contains("미조회") && missing.Summary.Contains("아직 조회하지 않음"), "uncollected promoted");
        });
        AddAsync("TXT save success keeps permission denial visible and refresh clears old summary", async () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel()) using (var gate = new Gate())
            {
                var report = LatestTransportObservation();
                f.Files.Reader = () => report;
                await vm.InspectSamsungFilesAsync();
                Check(vm.SamsungFileInspectionStatus.Contains("저장했습니다"), "TXT save failed");
                Equal(SamsungTransportAssessment.Evaluate(report).Summary, vm.SamsungTransportSummary);
                Check(vm.SamsungTransportSummary.Contains("조회 권한 없음") && !vm.CanApply, "save success hid denial or enabled control");
                f.Files.Reader = () => { gate.Enter(); return new SamsungFileInspectionReport(wmiInstances: SamsungWmiInstanceReport.Failure(SamsungWmiQueryStatus.TimedOut)); };
                Task pending = vm.InspectSamsungFilesAsync(); await gate.WaitEntered();
                Check(vm.SamsungTransportSummary.Contains("조회 중") && !vm.SamsungTransportSummary.Contains("조회 권한 없음"), "stale summary during refresh");
                gate.Release(); await pending;
                Check(vm.SamsungTransportSummary.Contains("시간 초과") && !vm.SamsungTransportSummary.Contains("조회 권한 없음"), "stale denial after refresh");
            }
        });
        AddAsync("save failure preserves assessment while provider error removes previous assessment", async () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                f.Files.Reader = LatestTransportObservation;
                f.Interaction.FileInspectionSaver = _ => { throw new Exception("private save path"); };
                await vm.InspectSamsungFilesAsync();
                Check(vm.SamsungTransportSummary.Contains("조회 권한 없음") &&
                    vm.SamsungFileInspectionStatus.Contains("저장하지 못했습니다"), "save failure discarded observation");
                f.Files.Reader = () => { throw new Exception(@"C:\Users\PrivateName"); };
                await vm.InspectSamsungFilesAsync();
                Check(vm.SamsungTransportSummary.Contains("조회 오류") && !vm.SamsungTransportSummary.Contains("조회 권한 없음") &&
                    !vm.SamsungTransportSummary.Contains("PrivateName") && !vm.CanApply, "provider failure kept prior facts or exposed data");
            }
        });
    }

    private static SamsungFileInspectionReport LatestTransportObservation() => new SamsungFileInspectionReport(
        SamsungFileInspectionStatus.Partial, limited: true, driverLink: SabiDriverLinkStatus.NotFound,
        kernelDrivers: new SamsungKernelDriverReport(SamsungDriverQueryStatus.Complete, Enumerable.Range(0, 7)
            .Select(_ => new SamsungKernelDriverEntry(SamsungDriverCategory.SamsungName, SamsungDriverState.Stopped, SamsungDriverStartMode.Manual))),
        wmiInstances: SamsungWmiInstanceReport.Failure(SamsungWmiQueryStatus.AccessDenied));
}
