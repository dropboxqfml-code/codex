using System;
using System.IO;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterSavedObservationViewModelTests()
    {
        Add("a saved observation reopens from disk in a new view model with the original file bytes", () =>
        {
            using (var f = new Fixture())
            {
                string path = Path.Combine(f.DirectoryPath, "battery-observation-reopen.txt");
                using (var first = f.ViewModel())
                {
                    f.Interaction.ObservationSaver = text => { File.WriteAllText(path, text); return "saved"; };
                    first.StartBatteryObservationCommand.Execute(null); first.RefreshBattery();
                    first.StopBatteryObservationCommand.Execute(null); first.SaveBatteryObservationCommand.Execute(null);
                }
                byte[] original = File.ReadAllBytes(path);
                f.Interaction.ObservationOpener = () =>
                {
                    using (var input = File.OpenRead(path))
                        return SavedBatteryObservation.Read(input, Path.GetFileName(path));
                };
                using (var reopened = f.ViewModel())
                {
                    reopened.OpenSavedObservationCommand.Execute(null);
                    Check(reopened.SavedObservationVisible && !reopened.ObservationActive, "new instance failed to restore historical graph");
                    Equal(1, reopened.SavedObservationGraph.SampleCount);
                    Equal(BatteryObservationSessionStatus.Stopped, reopened.SavedObservationGraph.Status);
                    Check(System.Linq.Enumerable.SequenceEqual(original, File.ReadAllBytes(path)), "opening changed the saved file");
                    reopened.CloseSavedObservationCommand.Execute(null);
                }
            }
        });

        Add("opening a saved observation preserves live samples control permissions and all execution counts", () =>
        {
            using (var f = new Fixture())
            {
                var battery = new PresentationGraphBattery(); var service = new ManualVmService(); var clock = new ManualUsabilityClock();
                using (var vm = PresentationGraphVm(f, battery, service, clock))
                {
                    Check(!vm.SavedObservationVisible && vm.OpenSavedObservationCommand.CanExecute(null), "initial file controls invalid");
                    vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery();
                    var live = vm.ObservationGraph; string liveText = vm.ObservationText;
                    int reads = battery.Calls, times = clock.Calls, operations = service.Operations.Count;
                    f.Interaction.ObservationOpener = () => SavedBatteryObservation.Parse(SavedObservationText(), @"C:\PrivateAccount\history.txt");
                    vm.OpenSavedObservationCommand.Execute(null);
                    Check(vm.SavedObservationVisible && !vm.SavedObservationOpenFailed, "file graph not visible");
                    Equal("history.txt", vm.SavedObservationName); Equal(80, vm.SavedObservationGraph.Points[0].Percent);
                    Check(ReferenceEquals(live, vm.ObservationGraph) && vm.ObservationActive, "opening replaced or stopped live observation");
                    Equal(liveText, vm.ObservationText);
                    for (int i = 0; i < 20; i++)
                    {
                        var graph = vm.SavedObservationGraph; var summary = vm.SavedObservationSummary;
                        Check(summary.Contains("파일 저장 당시") && !summary.Contains("PrivateAccount"), "historical summary ambiguous");
                    }
                    Equal(reads, battery.Calls); Equal(times, clock.Calls); Equal(operations, service.Operations.Count);
                    Equal(0, f.Interaction.ObservationSaves); Check(!vm.CanApply, "historical file enabled real control");
                    vm.CloseSavedObservationCommand.Execute(null);
                    Check(!vm.SavedObservationVisible && !vm.CloseSavedObservationCommand.CanExecute(null), "close retained file view");
                    Check(ReferenceEquals(live, vm.ObservationGraph) && vm.ObservationActive, "closing changed live session");
                }
            }
        });

        Add("saved observation cancellation malformed replacement and IO failures retain the last successful record", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                f.Interaction.ObservationOpener = () => SavedBatteryObservation.Parse(SavedObservationText(), "good.txt");
                vm.OpenSavedObservationCommand.Execute(null); var graph = vm.SavedObservationGraph;
                f.Interaction.ObservationOpener = () => null; vm.OpenSavedObservationCommand.Execute(null);
                Check(!vm.SavedObservationOpenFailed && ReferenceEquals(graph, vm.SavedObservationGraph), "cancel removed history");
                f.Interaction.ObservationOpener = () => SavedBatteryObservation.Parse("PRIVATE-PATH-ACCOUNT", "bad.txt");
                vm.OpenSavedObservationCommand.Execute(null);
                Check(vm.SavedObservationOpenFailed && ReferenceEquals(graph, vm.SavedObservationGraph), "bad input published partial history");
                Equal("good.txt", vm.SavedObservationName);
                Check(!vm.SavedObservationOpenStatus.Contains("PRIVATE"), "input echoed in error");
                f.Interaction.ObservationOpener = () => { throw new IOException("PRIVATE-PATH"); };
                vm.OpenSavedObservationCommand.Execute(null);
                Check(vm.SavedObservationOpenFailed && !vm.SavedObservationOpenStatus.Contains("PRIVATE"), "private IO failure leaked");
                Check(vm.OpenSavedObservationCommand.CanExecute(null), "failure left picker locked");
                f.Interaction.ObservationOpener = () => SavedBatteryObservation.Parse(SavedObservationText(), "recovered.txt");
                vm.OpenSavedObservationCommand.Execute(null);
                Equal("recovered.txt", vm.SavedObservationName); Check(!vm.SavedObservationOpenFailed, "success kept stale error");
            }
        });

        Add("saved observation picker rejects reentry and never publishes after disposal", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                f.Interaction.ObservationOpener = () =>
                {
                    Check(!vm.OpenSavedObservationCommand.CanExecute(null) && !vm.CloseSavedObservationCommand.CanExecute(null), "picker controls reentrant");
                    vm.OpenSavedObservationCommand.Execute(null);
                    vm.Dispose();
                    return SavedBatteryObservation.Parse(SavedObservationText(), "late.txt");
                };
                vm.OpenSavedObservationCommand.Execute(null);
                Equal(1, f.Interaction.ObservationOpens);
                Check(!vm.SavedObservationVisible && !vm.OpenSavedObservationCommand.CanExecute(null), "disposed view adopted late file");
                Equal(0, f.Interaction.ObservationSaves);
            }
        });

        Add("saved history remains historical while mock changes and new live observations are created", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                f.Interaction.ObservationOpener = () => SavedBatteryObservation.Parse(SavedObservationText().Replace("상태: 사용자 중지", "상태: 기록 중"), "old-recording.txt");
                vm.OpenSavedObservationCommand.Execute(null);
                var history = vm.SavedObservationGraph;
                Check(!vm.ObservationActive, "saved recording status started a live session");
                vm.IsMockMode = true;
                Check(vm.SavedObservationVisible && ReferenceEquals(history, vm.SavedObservationGraph), "mock changed historical view");
                vm.IsMockMode = false;
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); vm.ClearBatteryObservationCommand.Execute(null);
                Check(vm.SavedObservationVisible && ReferenceEquals(history, vm.SavedObservationGraph), "live clear changed historical data");
                vm.Dispose(); Check(!vm.SavedObservationVisible, "dispose retained imported record");
            }
        });
    }
}
