using System;
using System.Reflection;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Hardware;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.ViewModels;

internal static partial class Program
{
    private static void RegisterProtectionPresentationAndGraphViewModelTests()
    {
        Add("friendly protection disabled label does not imply a full charge or threshold restoration", () =>
        {
            foreach (var value in new[] { PresentationRead(0, 80, 75), PresentationRead(0, 255, 255),
                new ManualProtectionResult(ManualProtectionOperation.DisableProtection,
                    ManualProtectionStatus.AlreadyDesiredCandidate, true, true, 1, 0, 1, 0, 0),
                ManualVmChanged(ManualProtectionOperation.DisableProtection) })
            {
                Equal("충전 제한 해제 · 일반 충전", ManualProtectionPresentation.GetStateLabel(value));
                Check(!ManualProtectionPresentation.GetStateLabel(value).Contains("100%"), "disabled mode promised full charging");
            }
        });

        Add("friendly protection percentages require credible detached thresholds and exact 80 75 for the short label", () =>
        {
            Equal("80% 충전 제한", ManualProtectionPresentation.GetStateLabel(PresentationRead(1, 80, 75)));
            Equal("80% 충전 제한", ManualProtectionPresentation.GetStateLabel(ManualVmChanged(ManualProtectionOperation.Enable80)));
            Equal("충전 제한 켜짐 · 상한 90%", ManualProtectionPresentation.GetStateLabel(PresentationRead(1, 90, 85)));
            Equal("충전 제한 켜짐 · 상한 80%", ManualProtectionPresentation.GetStateLabel(PresentationRead(1, 80, 70)));
            Equal("충전 제한 켜짐 · 상한 100%", ManualProtectionPresentation.GetStateLabel(PresentationRead(1, 100, 95)));
            foreach (var value in new[] { PresentationRead(1, 0, 0), PresentationRead(1, 255, 1),
                PresentationRead(1, 80, 255), PresentationRead(1, 75, 80), PresentationRead(1, 80, 80) })
                Equal("충전 제한 켜짐 · 상한 미확인", ManualProtectionPresentation.GetStateLabel(value));
        });

        Add("friendly protection presentation never reuses old thresholds or publishes unknown results as enabled", () =>
        {
            var already = new ManualProtectionResult(ManualProtectionOperation.Enable80,
                ManualProtectionStatus.AlreadyDesiredCandidate, true, true, 1, 0, 1, 1, 1);
            Equal("80% 충전 제한", ManualProtectionPresentation.GetStateLabel(PresentationRead(1, 80, 75)));
            Equal("충전 제한 켜짐 · 상한 미확인", ManualProtectionPresentation.GetStateLabel(already));
            Check(!already.UpperCandidate.HasValue && !already.LowerCandidate.HasValue, "display mutated immutable candidates");
            Equal("충전 제한 상태 미확인", ManualProtectionPresentation.GetStateLabel(null));
            foreach (var status in new[] { ManualProtectionStatus.Unknown, ManualProtectionStatus.TimedOut,
                ManualProtectionStatus.Rejected, ManualProtectionStatus.Unsupported, ManualProtectionStatus.Cancelled })
                Equal("충전 제한 상태 미확인", ManualProtectionPresentation.GetStateLabel(
                    ManualProtectionResult.Failure(ManualProtectionOperation.ReadState, status, true)));
        });

        AddAsync("friendly GUI state labels preserve last query provenance raw details and passive getters", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService(); var battery = new OfflineReviewCountingBattery();
                var clock = new ManualUsabilityClock();
                using (var vm = ManualUsabilityVm(f, service, clock, battery))
                {
                    int reads = battery.Calls;
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Equal("마지막 조회: 충전 제한 해제 · 일반 충전", vm.ManualProtectionStateText);
                    service.Handler = (op, phase) => Task.FromResult(PresentationRead(1, 90, 85));
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Equal("마지막 조회: 충전 제한 켜짐 · 상한 90%", vm.ActualModeText);
                    Check(vm.ManualProtectionText.Contains("모드 후보: 1 / 상한 후보: 90 / 하한 후보: 85"), "technical candidates were changed by friendly text");
                    Check(!vm.SupportReason.Contains("베타") && !vm.SupportReason.Contains("beta"), "release still presented as beta");
                    int clockReads = clock.Calls;
                    for (int i = 0; i < 50; i++)
                    {
                        Equal(vm.ManualProtectionStateText, vm.ActualModeText);
                        string ignored = vm.ManualProtectionText + vm.ManualProtectionReadTimeText + vm.SupportReason;
                    }
                    Equal(reads, battery.Calls); Equal(clockReads, clock.Calls); Equal(2, service.Operations.Count);
                    Equal(0, f.Interaction.ManualResultSaves); Equal(0, f.Interaction.ObservationSaves);
                }
            }
        });

        AddAsync("friendly GUI already desired enable replaces an old 80 percent snapshot with unknown upper", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService { Handler = (op, phase) => Task.FromResult(PresentationRead(1, 80, 75)) };
                using (var vm = ManualVm(f, service))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Equal("마지막 조회: 80% 충전 제한", vm.ManualProtectionStateText);
                    service.Handler = (op, phase) => Task.FromResult(new ManualProtectionResult(op,
                        ManualProtectionStatus.AlreadyDesiredCandidate, true, true, 1, 0, 1, 1, 1));
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.Enable80);
                    Equal("마지막 조회: 충전 제한 켜짐 · 상한 미확인", vm.ActualModeText);
                    Check(!vm.ActualModeText.Contains("80%"), "requested enable was displayed as measured 80 percent");
                    Equal(2, service.Operations.Count);
                }
            }
        });

        AddAsync("friendly GUI mock and failed fresh read discard prior enabled state", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService { Handler = (op, phase) => Task.FromResult(PresentationRead(1, 80, 75)) };
                using (var vm = ManualVm(f, service))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    vm.IsMockMode = true;
                    Check(vm.ActualModeText.Contains("시뮬레이션") && !vm.ActualModeText.Contains("80%"), "mock reused the real enabled label");
                    vm.IsMockMode = false;
                    Check(vm.ActualModeText.Contains("미조회") && !vm.ManualDisableProtectionCommand.CanExecute(null), "leaving mock restored prior enabled state");
                    service.Handler = (op, phase) => Task.FromResult(ManualProtectionResult.Failure(op, ManualProtectionStatus.Rejected, true));
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Check(vm.ActualModeText.Contains("알 수 없음") && !vm.ActualModeText.Contains("80%"), "failed fresh query retained an enabled label");
                    Equal(2, service.Operations.Count);
                }
            }
        });

        AddAsync("friendly GUI pending and invalidated late completion outrank old friendly labels", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService();
                using (var vm = ManualVm(f, service))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    var pending = new TaskCompletionSource<ManualProtectionResult>(TaskCreationOptions.RunContinuationsAsynchronously);
                    service.Handler = (op, phase) => pending.Task;
                    var run = vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Check(vm.ActualModeText.Contains("정리 중") && !vm.ActualModeText.Contains("일반 충전"), "active query retained the old friendly state");
                    vm.InvalidateManualState(); pending.SetResult(PresentationRead(1, 80, 75)); await run;
                    Check(vm.ActualModeText.Contains("미조회") && !vm.ActualModeText.Contains("80%"), "invalidated completion revived a stale label");
                    service.Handler = (op, phase) => Task.FromResult(ManualProtectionResult.Failure(op, ManualProtectionStatus.Unknown));
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Check(vm.ActualModeText.Contains("실제 종료 미확인") && !vm.ActualModeText.Contains("80%"), "pending cleanup published a friendly mode");
                    Equal(3, service.Operations.Count);
                }
            }
        });

        Add("observation graph appears empty at start records only existing refresh and retains stopped history", () =>
        {
            using (var f = new Fixture())
            {
                var battery = new PresentationGraphBattery(); var service = new ManualVmService(); var clock = new ManualUsabilityClock();
                using (var vm = PresentationGraphVm(f, battery, service, clock))
                {
                    int reads = battery.Calls; var files = OfflineReviewFileSnapshot(f.DirectoryPath);
                    var initial = vm.ObservationGraph;
                    Equal(BatteryObservationSessionStatus.NotStarted, initial.Status);
                    Check(!vm.ObservationGraphVisible, "empty initial graph was visible");
                    vm.StartBatteryObservationCommand.Execute(null);
                    var started = vm.ObservationGraph;
                    Check(vm.ObservationGraphVisible && vm.ObservationActive, "start did not expose the waiting graph");
                    Equal(BatteryObservationSessionStatus.Recording, started.Status); Equal(0, started.SampleCount);
                    Equal(reads, battery.Calls); Equal(0, clock.Calls); Equal(0, service.Operations.Count);
                    for (int i = 0; i < 50; i++) Check(ReferenceEquals(started, vm.ObservationGraph) && vm.ObservationGraphVisible, "graph getter rebuilt the snapshot");
                    vm.RefreshBattery(); Equal(reads + 1, battery.Calls);
                    var recorded = vm.ObservationGraph;
                    Equal(1, recorded.SampleCount); Equal(1, recorded.ObservedPointCount); Equal(0, started.SampleCount);
                    vm.RefreshBattery(); Equal(reads + 2, battery.Calls); Equal(1, vm.ObservationGraph.SampleCount);
                    vm.StopBatteryObservationCommand.Execute(null);
                    Equal(BatteryObservationSessionStatus.Stopped, vm.ObservationGraph.Status);
                    Check(vm.ObservationGraphVisible && !vm.ObservationActive, "stop hid recorded history");
                    Equal(1, vm.ObservationGraph.SampleCount); Equal(1, recorded.SampleCount);
                    Equal(BatteryObservationSessionStatus.Recording, recorded.Status);
                    vm.RefreshBattery(); Equal(reads + 3, battery.Calls); Equal(1, vm.ObservationGraph.SampleCount);
                    Equal(0, clock.Calls); Equal(0, service.Operations.Count); Equal(0, f.Files.Calls); Equal(0, f.Bundle.Calls);
                    Equal(0, f.Interaction.ObservationSaves); OfflineReviewAssertSameFiles(files, f.DirectoryPath);
                }
            }
        });

        Add("observation graph clear resets visibility and restart does not reuse previous rows", () =>
        {
            using (var f = new Fixture())
            {
                var battery = new PresentationGraphBattery();
                using (var vm = PresentationGraphVm(f, battery))
                {
                    vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery();
                    var history = vm.ObservationGraph; int reads = battery.Calls;
                    vm.ClearBatteryObservationCommand.Execute(null);
                    Check(!vm.ObservationGraphVisible && !vm.ObservationActive, "clear retained a visible session");
                    Equal(BatteryObservationSessionStatus.NotStarted, vm.ObservationGraph.Status); Equal(0, vm.ObservationGraph.SampleCount);
                    Equal(1, history.SampleCount); Equal(reads, battery.Calls);
                    vm.StartBatteryObservationCommand.Execute(null);
                    Check(vm.ObservationGraphVisible && vm.ObservationActive, "restart did not expose a fresh graph");
                    Equal(0, vm.ObservationGraph.SampleCount); Equal(reads, battery.Calls);
                    vm.RefreshBattery(); Equal(1, vm.ObservationGraph.SampleCount); Equal(reads + 1, battery.Calls);
                    Equal(0, f.Interaction.ObservationSaves);
                }
            }
        });

        Add("observation graph is hidden during simulation and only real stopped history returns afterward", () =>
        {
            using (var f = new Fixture())
            {
                var battery = new PresentationGraphBattery();
                using (var vm = PresentationGraphVm(f, battery))
                {
                    vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery();
                    vm.IsMockMode = true;
                    Check(!vm.ObservationGraphVisible && !vm.ObservationActive, "real graph was labelled live in simulation");
                    var history = vm.ObservationGraph;
                    Equal(BatteryObservationSessionStatus.Stopped, history.Status); Equal(1, history.SampleCount);
                    vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery();
                    Check(ReferenceEquals(history, vm.ObservationGraph), "simulation refresh entered real observation history");
                    vm.IsMockMode = false;
                    Check(vm.ObservationGraphVisible && !vm.ObservationActive, "stopped history did not return after simulation");
                    Check(ReferenceEquals(history, vm.ObservationGraph), "leaving simulation reconstructed or resumed history");
                    Equal(0, f.Interaction.ObservationSaves);
                }
            }
        });

        Add("observation graph snapshot keeps unknown samples and long gaps separate without polling", () =>
        {
            using (var f = new Fixture())
            {
                var battery = new PresentationGraphBattery(); var service = new ManualVmService(); var clock = new ManualUsabilityClock();
                using (var vm = PresentationGraphVm(f, battery, service, clock))
                {
                    vm.StartBatteryObservationCommand.Execute(null); int reads = battery.Calls;
                    // Feed the existing bounded session directly to make elapsed
                    // times deterministic without adding a production clock hook.
                    var session = PresentationObservation(vm);
                    session.Record(TimeSpan.Zero, battery.Result);
                    session.Record(TimeSpan.FromSeconds(10), BatterySnapshot.Unknown("PRIVATE-PROVIDER-ERROR"));
                    session.Record(TimeSpan.FromSeconds(20), battery.Result);
                    session.Record(TimeSpan.FromSeconds(60), battery.Result);
                    session.Record(TimeSpan.FromSeconds(70), new BatterySnapshot(99, ExternalPowerStatus.Connected, BatteryChargeState.NoBattery, string.Empty));
                    session.Record(TimeSpan.FromSeconds(80), battery.Result);
                    PresentationPublishObservation(vm);
                    var graph = vm.ObservationGraph;
                    Equal(6, graph.SampleCount); Equal(4, graph.ObservedPointCount); Equal(80, graph.ElapsedSeconds); Equal(1, graph.GapCount);
                    Equal(4, graph.Points.Count);
                    Equal(0, graph.Points[0].ElapsedSeconds); Equal(20, graph.Points[1].ElapsedSeconds);
                    Equal(60, graph.Points[2].ElapsedSeconds); Equal(80, graph.Points[3].ElapsedSeconds);
                    foreach (var point in graph.Points) Check(point.StartsSegment, "unknown or long gap was interpolated as continuous observation");
                    for (int i = 0; i < 25; i++) Check(ReferenceEquals(graph, vm.ObservationGraph), "reading deterministic graph changed its data");
                    Equal(reads, battery.Calls); Equal(0, clock.Calls); Equal(0, service.Operations.Count);
                    Equal(0, f.Interaction.ObservationSaves); Equal(0, f.Files.Calls); Equal(0, f.Bundle.Calls);
                }
            }
        });

        Add("observation graph retains terminal session status until explicit clear or a new start", () =>
        {
            using (var f = new Fixture())
            {
                var battery = new PresentationGraphBattery();
                using (var vm = PresentationGraphVm(f, battery))
                {
                    vm.StartBatteryObservationCommand.Execute(null);
                    var session = PresentationObservation(vm);
                    session.Record(TimeSpan.Zero, battery.Result);
                    session.Record(BatteryObservationSession.MaxDuration, battery.Result);
                    PresentationPublishObservation(vm);
                    var terminal = vm.ObservationGraph;
                    Equal(BatteryObservationSessionStatus.DurationLimitReached, terminal.Status);
                    Equal(7200, terminal.ElapsedSeconds); Equal(2, terminal.SampleCount);
                    Check(vm.ObservationGraphVisible && !vm.ObservationActive, "bounded terminal history was hidden or resumed");
                    int reads = battery.Calls; vm.RefreshBattery();
                    Equal(reads + 1, battery.Calls); Check(ReferenceEquals(terminal, vm.ObservationGraph), "terminal session captured a later refresh");
                    vm.StopBatteryObservationCommand.Execute(null);
                    Equal(BatteryObservationSessionStatus.DurationLimitReached, vm.ObservationGraph.Status);
                    vm.ClearBatteryObservationCommand.Execute(null);
                    Check(!vm.ObservationGraphVisible, "clear did not hide terminal graph"); Equal(0, vm.ObservationGraph.SampleCount);
                }
            }
        });
    }

    private static ManualProtectionResult PresentationRead(int mode, int upper, int lower)
        => new ManualProtectionResult(ManualProtectionOperation.ReadState, ManualProtectionStatus.StateRead,
            true, true, 3, 0, 3, mode, mode, upper, lower);

    private static MainViewModel PresentationGraphVm(Fixture f, PresentationGraphBattery battery,
        ManualVmService service = null, ManualUsabilityClock clock = null)
        => new MainViewModel(battery, f.Store, new LocalLog(f.DirectoryPath), f.Interaction,
            f.Hardware, f.Bundle, () => true, f.Files, service, clock == null ? (Func<DateTimeOffset>)null : clock.Read);

    private static BatteryObservationSession PresentationObservation(MainViewModel vm)
        => (BatteryObservationSession)typeof(MainViewModel).GetField("observation", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(vm);

    private static void PresentationPublishObservation(MainViewModel vm)
        => typeof(MainViewModel).GetMethod("NotifyBatteryObservation", BindingFlags.Instance | BindingFlags.NonPublic).Invoke(vm, null);

    private sealed class PresentationGraphBattery : IBatteryStatusProvider
    {
        internal int Calls;
        internal BatterySnapshot Result = new BatterySnapshot(43, ExternalPowerStatus.Connected, BatteryChargeState.Charging, string.Empty);
        public BatterySnapshot Read() { Calls++; return Result; }
    }
}
