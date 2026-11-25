using System;
using System.IO;
using ATIVBatteryGuard.Controls;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterObservationComparisonTests()
    {
        Add("comparison charts use a common elapsed scale for pointer selection without extending shorter data", () =>
        {
            var shortFile = ComparisonFile("short.txt", 60, 80);
            var longFile = ComparisonFile("long.txt", 120, 90);
            var a = new BatteryObservationChartSelection(); var b = new BatteryObservationChartSelection();
            a.UpdateGraph(shortFile.Graph); b.UpdateGraph(longFile.Graph);
            a.MinimumDomainSeconds = b.MinimumDomainSeconds = 120;
            Equal(120.0, a.DomainSeconds); Equal(120.0, b.DomainSeconds);
            Equal(1, a.FindPointIndex(300, 20, 600, 100));
            Equal(-1, a.FindPointIndex(600, 20, 600, 100));
            Equal(1, b.FindPointIndex(600, 10, 600, 100));
            Equal(60, shortFile.Graph.ElapsedSeconds); Equal(120, longFile.Graph.ElapsedSeconds);
            var delayed = new BatteryObservationChartSelection();
            delayed.UpdateGraph(BatteryObservationGraph.FromSamples(new[] { GraphSample(30, 80) }, BatteryObservationSessionStatus.Stopped));
            delayed.MinimumDomainSeconds = 120;
            Equal(0, delayed.FindPointIndex(150, 20, 600, 100));
            Equal(-1, delayed.FindPointIndex(0, 20, 600, 100));
            a.Select(1); b.Select(0); a.Move(-1);
            Equal(0, a.Index); Equal(0, b.Index);
            b.Move(1); Equal(0, a.Index); Equal(1, b.Index);
        });

        Add("shared elapsed scale changes preserve selected observations and reject invalid bounds before mutation", () =>
        {
            var file = ComparisonFile("selection.txt", 120, 80);
            var selection = new BatteryObservationChartSelection(); selection.UpdateGraph(file.Graph); selection.Select(1);
            selection.MinimumDomainSeconds = 300;
            Equal(1, selection.Index); Equal(120, selection.Point.ElapsedSeconds);
            Equal(1, selection.FindPointIndex(240, 20, 600, 100));
            selection.MinimumDomainSeconds = 7200;
            Equal(7200.0, selection.DomainSeconds); Equal(1, selection.Index);
            selection.MinimumDomainSeconds = 60; Equal(120.0, selection.DomainSeconds);
            foreach (double invalid in new[] { 0.0, 59.0, 7201.0, double.NaN, double.PositiveInfinity })
            {
                bool rejected = false;
                try { selection.MinimumDomainSeconds = invalid; } catch (ArgumentOutOfRangeException) { rejected = true; }
                Check(rejected, "invalid axis accepted");
                Equal(60.0, selection.MinimumDomainSeconds); Equal(1, selection.Index);
            }
        });

        Add("comparison keeps each file gaps unknown tail and historical status with a common full-record extent", () =>
        {
            var a = ComparisonFile("unknown-tail.txt", 120, 80, false, true);
            var b = ComparisonFile("short.txt", 60, 90);
            Equal(1, a.Graph.Points.Count); Equal(2, a.Graph.SampleCount);
            Equal(BatteryObservationSessionStatus.Recording, a.Graph.Status);
            Check(b.Graph.Points[1].StartsSegment, "long gap joined");
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                f.Interaction.ObservationOpener = () => a;
                vm.OpenSavedObservationCommand.Execute(null);
                f.Interaction.ObservationOpener = () => b;
                vm.OpenComparisonObservationCommand.Execute(null);
                Equal(120.0, vm.SavedObservationDomainSeconds);
                Check(ReferenceEquals(a.Graph, vm.SavedObservationGraph) && ReferenceEquals(b.Graph, vm.ComparisonObservationGraph),
                    "comparison rewrote graph evidence");
                Check(vm.SavedObservationSummary.Contains("기록 중") && vm.ComparisonObservationSummary.Contains("사용자 중지"),
                    "saved terminal states were merged");
                Check(!vm.ObservationActive && !vm.CanApply, "comparison enabled capture or hardware control");
            }
        });

        Add("comparison opens a second historical file while retaining current capture and execution counters", () =>
        {
            using (var f = new Fixture())
            {
                var battery = new PresentationGraphBattery(); var service = new ManualVmService(); var clock = new ManualUsabilityClock();
                using (var vm = PresentationGraphVm(f, battery, service, clock))
                {
                    Check(!vm.OpenComparisonObservationCommand.CanExecute(null), "comparison can open without A");
                    vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery();
                    var live = vm.ObservationGraph;
                    f.Interaction.ObservationOpener = () => ComparisonFile("a.txt", 60, 80);
                    vm.OpenSavedObservationCommand.Execute(null); var a = vm.SavedObservationGraph;
                    int reads = battery.Calls, operations = service.Operations.Count, times = clock.Calls;
                    f.Interaction.ObservationOpener = () => ComparisonFile("b.txt", 120, 90);
                    vm.OpenComparisonObservationCommand.Execute(null);
                    Check(vm.ComparisonObservationVisible, "comparison file missing");
                    Equal("A · a.txt", vm.SavedObservationTitle); Equal("B · b.txt", vm.ComparisonObservationName);
                    Check(vm.ComparisonAxisText.Contains("00:02:00"), "common axis label incorrect");
                    Check(ReferenceEquals(live, vm.ObservationGraph) && vm.ObservationActive, "comparison changed live capture");
                    Check(ReferenceEquals(a, vm.SavedObservationGraph), "comparison replaced A");
                    for (int i = 0; i < 20; i++) { var summary = vm.ComparisonObservationSummary; var axis = vm.SavedObservationDomainSeconds; }
                    Equal(reads, battery.Calls); Equal(operations, service.Operations.Count); Equal(times, clock.Calls);
                    Equal(0, f.Interaction.ObservationSaves);
                    vm.CloseComparisonObservationCommand.Execute(null);
                    Check(!vm.ComparisonObservationVisible && ReferenceEquals(a, vm.SavedObservationGraph), "comparison close removed A");
                    Equal(60.0, vm.SavedObservationDomainSeconds); Equal("a.txt", vm.SavedObservationTitle);
                }
            }
        });

        Add("comparison cancellation invalid replacement and IO errors retain both files with retry available", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                f.Interaction.ObservationOpener = () => ComparisonFile("a.txt", 60, 80); vm.OpenSavedObservationCommand.Execute(null);
                f.Interaction.ObservationOpener = () => ComparisonFile("b.txt", 120, 90); vm.OpenComparisonObservationCommand.Execute(null);
                var a = vm.SavedObservationGraph; var b = vm.ComparisonObservationGraph;
                f.Interaction.ObservationOpener = () => null; vm.OpenComparisonObservationCommand.Execute(null);
                Check(!vm.SavedObservationOpenFailed, "cancel became an error");
                f.Interaction.ObservationOpener = () => SavedBatteryObservation.Parse("PRIVATE-INVALID", "bad.txt");
                vm.OpenComparisonObservationCommand.Execute(null);
                Check(vm.SavedObservationOpenFailed && !vm.SavedObservationOpenStatus.Contains("PRIVATE"), "bad file echoed");
                f.Interaction.ObservationOpener = () => { throw new IOException("PRIVATE-PATH"); };
                vm.OpenComparisonObservationCommand.Execute(null);
                Check(ReferenceEquals(a, vm.SavedObservationGraph) && ReferenceEquals(b, vm.ComparisonObservationGraph), "failure discarded a pair");
                Equal(120.0, vm.SavedObservationDomainSeconds);
                f.Interaction.ObservationOpener = () => ComparisonFile("replacement.txt", 300, 85);
                vm.OpenComparisonObservationCommand.Execute(null);
                Equal(300.0, vm.SavedObservationDomainSeconds); Check(!vm.SavedObservationOpenFailed, "retry retained error");
                vm.CloseSavedObservationCommand.Execute(null);
                Check(!vm.SavedObservationVisible && !vm.ComparisonObservationVisible, "close-all retained a file");
                Check(!vm.OpenComparisonObservationCommand.CanExecute(null), "B can open after close-all");
            }
        });

        Add("replacing A keeps B and identical files are supported before all comparison data is released on dispose", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                var same = ComparisonFile("same.txt", 60, 80);
                f.Interaction.ObservationOpener = () => same;
                vm.OpenSavedObservationCommand.Execute(null); vm.OpenComparisonObservationCommand.Execute(null);
                Check(vm.ComparisonObservationVisible, "identical files rejected");
                var b = vm.ComparisonObservationGraph;
                f.Interaction.ObservationOpener = () => ComparisonFile("longer-a.txt", 300, 85);
                vm.OpenSavedObservationCommand.Execute(null);
                Check(ReferenceEquals(b, vm.ComparisonObservationGraph), "A replacement removed B");
                Equal(300.0, vm.SavedObservationDomainSeconds);
                vm.Dispose();
                Check(!vm.SavedObservationVisible && !vm.ComparisonObservationVisible, "dispose retained graphs");
                Equal(60.0, vm.SavedObservationDomainSeconds);
            }
        });

        Add("comparison picker blocks reentry and late results cannot republish after disposal", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                f.Interaction.ObservationOpener = () => ComparisonFile("a.txt", 60, 80);
                vm.OpenSavedObservationCommand.Execute(null);
                f.Interaction.ObservationOpener = () =>
                {
                    Check(!vm.OpenComparisonObservationCommand.CanExecute(null) && !vm.OpenSavedObservationCommand.CanExecute(null)
                        && !vm.CloseSavedObservationCommand.CanExecute(null), "file picker reentered");
                    vm.OpenComparisonObservationCommand.Execute(null);
                    vm.Dispose();
                    return ComparisonFile("late.txt", 120, 90);
                };
                vm.OpenComparisonObservationCommand.Execute(null);
                Equal(2, f.Interaction.ObservationOpens);
                Check(!vm.SavedObservationVisible && !vm.ComparisonObservationVisible, "late result restored disposed graphs");
            }
        });
    }

    private static SavedBatteryObservation ComparisonFile(string name, int seconds, int percent, bool stop = true, bool unknownTail = false)
    {
        var session = new BatteryObservationSession(); session.Start();
        session.Record(TimeSpan.Zero, new BatterySnapshot(percent, ExternalPowerStatus.Connected, BatteryChargeState.NotCharging, ""));
        if (seconds > 0) session.Record(TimeSpan.FromSeconds(seconds), unknownTail ? BatterySnapshot.Unknown("private")
            : new BatterySnapshot(percent, ExternalPowerStatus.Connected, BatteryChargeState.Charging, ""));
        if (stop) session.Stop();
        return SavedBatteryObservation.Parse(session.ExportText(), name);
    }
}
