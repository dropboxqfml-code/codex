using System;
using System.IO;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Services;

internal static partial class Program
{
    private static void RegisterObservationProtectionTests()
    {
        foreach (string action in new[] { "new", "clear", "close" })
        {
            string target = action;
            Add("unsaved observation cancel preserves data for " + target, () =>
            {
                using (var f = new Fixture()) using (var vm = f.ViewModel())
                {
                    vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); vm.StopBatteryObservationCommand.Execute(null);
                    string before = vm.ObservationText;
                    f.Interaction.ObservationConfirmer = label => ObservationLossChoice.Cancel;
                    bool allowed = ExecuteProtectedObservationAction(vm, target);
                    Check(!allowed && vm.HasUnsavedObservation, "cancel discarded the session");
                    Equal(before, vm.ObservationText); Equal(0, f.Interaction.ObservationSaves);
                    Equal(1, f.Interaction.ObservationConfirmations);
                }
            });

            Add("unsaved observation save completes before " + target + " and duplicate prompts are avoided", () =>
            {
                using (var f = new Fixture()) using (var vm = f.ViewModel())
                {
                    vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery();
                    if (target == "new") vm.StopBatteryObservationCommand.Execute(null);
                    f.Interaction.ObservationConfirmer = label => ObservationLossChoice.Save;
                    Check(ExecuteProtectedObservationAction(vm, target), "saved action was blocked");
                    Equal(1, f.Interaction.ObservationSaves);
                    Check(f.Interaction.LastObservation.Contains("상태: 사용자 중지"), "final state was not saved");
                    Check(!vm.HasUnsavedObservation, "saved or cleared session stayed dirty");
                    if (target == "close") Check(vm.TryPrepareToClose(), "saved close prompted again");
                    Equal(1, f.Interaction.ObservationConfirmations);
                }
            });
        }

        Add("unsaved observation discard is explicit and failed saves retain data and permit retry", () =>
        {
            foreach (string action in new[] { "new", "clear", "close" })
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); vm.StopBatteryObservationCommand.Execute(null);
                f.Interaction.ObservationConfirmer = label => ObservationLossChoice.Save;
                f.Interaction.ObservationSaver = text => { throw new IOException("PRIVATE-FAILED-SAVE"); };
                Check(!ExecuteProtectedObservationAction(vm, action), "failed save permitted data loss");
                Equal(1, vm.ObservationSampleCount);
                Check(vm.HasUnsavedObservation && vm.ObservationSaveFailed, "failed save consumed revision");
                Check(!vm.ObservationSaveStatusText.Contains("PRIVATE"), "private error leaked");
                int writes = f.Interaction.ObservationSaves;
                f.Interaction.ObservationConfirmer = label => ObservationLossChoice.Discard;
                Check(ExecuteProtectedObservationAction(vm, action), "explicit discard was blocked");
                Equal(writes, f.Interaction.ObservationSaves);
            }
        });

        Add("active observations saved mid-recording request final status protection while empty and saved stopped sessions do not", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                Check(vm.TryPrepareToClose(), "empty session prompted");
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); vm.SaveBatteryObservationCommand.Execute(null);
                Check(vm.HasUnsavedObservation, "active final status lost protection");
                f.Interaction.ObservationConfirmer = label => ObservationLossChoice.Cancel;
                Check(!vm.TryPrepareToClose() && vm.ObservationActive, "cancel changed active state");
                f.Interaction.ObservationConfirmer = label => ObservationLossChoice.Save;
                Check(vm.TryPrepareToClose() && !vm.ObservationActive, "final save failed");
                Equal(2, f.Interaction.ObservationSaves);
                Check(!vm.HasUnsavedObservation, "final status stayed dirty");
                Check(vm.TryPrepareToClose(), "saved stopped session prompted");
                Equal(2, f.Interaction.ObservationConfirmations);
            }
        });

        Add("observation protection rejects reentry invalid choices and confirmation failures without losing records", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); vm.StopBatteryObservationCommand.Execute(null);
                f.Interaction.ObservationConfirmer = label =>
                {
                    Check(!vm.TryPrepareToClose(), "confirmation reentered");
                    vm.ClearBatteryObservationCommand.Execute(null); vm.StartBatteryObservationCommand.Execute(null);
                    return (ObservationLossChoice)999;
                };
                Check(!vm.TryPrepareToClose(), "unknown choice discarded data");
                Equal(1, vm.ObservationSampleCount); Equal(1, f.Interaction.ObservationConfirmations);
                f.Interaction.ObservationConfirmer = label => { throw new IOException("PRIVATE-CONFIRM"); };
                Check(!vm.TryPrepareToClose() && vm.HasUnsavedObservation, "failed dialog discarded data");
                Check(!vm.StatusMessage.Contains("PRIVATE"), "dialog error leaked");
                f.Interaction.ObservationConfirmer = label => ObservationLossChoice.Save;
                Check(vm.TryPrepareToClose(), "dialog failure locked later attempts");
            }
        });

        AddAsync("manual helper activity blocks close before any observation prompt", async () =>
        {
            using (var f = new Fixture())
            {
                var completion = new TaskCompletionSource<ATIVBatteryGuard.Core.Models.ManualProtectionResult>();
                var service = new ManualVmService { Handler = (op, progress) => completion.Task };
                using (var vm = PresentationGraphVm(f, new PresentationGraphBattery(), service))
                {
                    vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery();
                    var running = vm.RunManualProtectionAsync(ATIVBatteryGuard.Core.Models.ManualProtectionOperation.ReadState);
                    Check(vm.ManualProtectionBusy && !vm.TryPrepareToClose(), "busy helper did not block close");
                    Equal(0, f.Interaction.ObservationConfirmations);
                    completion.SetResult(PresentationRead(0, 80, 75)); await running;
                }
            }
        });
    }

    private static bool ExecuteProtectedObservationAction(ATIVBatteryGuard.ViewModels.MainViewModel vm, string action)
    {
        if (action == "close") return vm.TryPrepareToClose();
        if (action == "new") vm.StartBatteryObservationCommand.Execute(null);
        else vm.ClearBatteryObservationCommand.Execute(null);
        return vm.ObservationSampleCount == 0;
    }
}
