using System;
using System.Collections.Generic;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterObservationFinalSaveTests()
    {
        Add("observation recording then final save exports distinct status with identical rows and no extra battery read", () =>
        {
            using (var f = new Fixture())
            {
                var battery = new PresentationGraphBattery();
                using (var vm = PresentationGraphVm(f, battery))
                {
                    var changes = new List<string>();
                    vm.PropertyChanged += (sender, args) => changes.Add(args.PropertyName);
                    Equal("시작 전", vm.ObservationStatusText);
                    vm.StartBatteryObservationCommand.Execute(null);
                    Equal("기록 중", vm.ObservationStatusText);
                    vm.RefreshBattery();
                    int reads = battery.Calls;
                    vm.SaveBatteryObservationCommand.Execute(null);
                    string recording = f.Interaction.LastObservation;
                    Check(recording.Contains("상태: 기록 중"), "recording status missing");
                    Check(!vm.SaveBatteryObservationCommand.CanExecute(null), "same revision can be saved twice");
                    vm.StopBatteryObservationCommand.Execute(null);
                    Equal("사용자 중지", vm.ObservationStatusText);
                    Check(changes.Contains("ObservationStatusText"), "status binding was not notified");
                    Check(vm.SaveBatteryObservationCommand.CanExecute(null), "final status is blocked");
                    vm.SaveBatteryObservationCommand.Execute(null);
                    string stopped = f.Interaction.LastObservation;
                    Equal(recording.Substring(recording.IndexOf("elapsed_seconds,")),
                        stopped.Substring(stopped.IndexOf("elapsed_seconds,")));
                    Check(stopped.Contains("상태: 사용자 중지"), "terminal status missing");
                    vm.SaveBatteryObservationCommand.Execute(null);
                    Equal(2, f.Interaction.ObservationSaves); Equal(reads, battery.Calls);
                    Check(!vm.SaveBatteryObservationCommand.CanExecute(null), "same final revision can be saved twice");
                    vm.ClearBatteryObservationCommand.Execute(null);
                    Equal("시작 전", vm.ObservationStatusText);
                    Check(!vm.SaveBatteryObservationCommand.CanExecute(null), "empty data became saveable");
                }
            }
        });

        Add("observation terminal status changes without new rows stay saveable after a failed final save", () =>
        {
            foreach (bool invalidTime in new[] { false, true })
            using (var f = new Fixture())
            using (var vm = f.ViewModel())
            {
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery();
                vm.SaveBatteryObservationCommand.Execute(null);
                var session = PresentationObservation(vm);
                session.Record(invalidTime ? TimeSpan.FromSeconds(-1) : TimeSpan.FromSeconds(7201),
                    new BatterySnapshot(80, ExternalPowerStatus.Connected, BatteryChargeState.NotCharging, ""));
                PresentationPublishObservation(vm);
                Equal(1, vm.ObservationSampleCount);
                Equal(invalidTime ? "시간 순서 오류로 중지" : "시간 한도 도달", vm.ObservationStatusText);
                Check(vm.SaveBatteryObservationCommand.CanExecute(null), "changed terminal reason is deduplicated");
                f.Interaction.ObservationSaver = text => { throw new InvalidOperationException("PRIVATE-FINAL-SAVE"); };
                vm.SaveBatteryObservationCommand.Execute(null);
                Check(vm.ObservationSaveFailed && vm.SaveBatteryObservationCommand.CanExecute(null), "failure consumed final revision");
                f.Interaction.ObservationSaver = text => "final saved";
                vm.SaveBatteryObservationCommand.Execute(null);
                Equal(3, f.Interaction.ObservationSaves);
                Check(f.Interaction.LastObservation.Contains("상태: " + vm.ObservationStatusText), "status label and export disagree");
                Check(!vm.SaveBatteryObservationCommand.CanExecute(null), "retry duplicated terminal revision");
            }
        });

        Add("observation sample limit and empty stop labels agree with the session export", () =>
        {
            using (var f = new Fixture())
            using (var vm = f.ViewModel())
            {
                vm.StartBatteryObservationCommand.Execute(null);
                vm.StopBatteryObservationCommand.Execute(null);
                Equal("사용자 중지", vm.ObservationStatusText);
                Check(!vm.SaveBatteryObservationCommand.CanExecute(null), "no samples can be exported");
                vm.StartBatteryObservationCommand.Execute(null);
                var session = PresentationObservation(vm);
                for (int i = 0; i < BatteryObservationSession.MaxSamples; i++)
                    session.Record(TimeSpan.FromSeconds(i * 10),
                        new BatterySnapshot(80, ExternalPowerStatus.Connected, BatteryChargeState.NotCharging, ""));
                PresentationPublishObservation(vm);
                Equal("샘플 한도 도달", vm.ObservationStatusText);
                vm.SaveBatteryObservationCommand.Execute(null);
                Check(f.Interaction.LastObservation.Contains("상태: 샘플 한도 도달"), "limit label missing");
                Check(!vm.SaveBatteryObservationCommand.CanExecute(null), "unchanged limit export is duplicated");
            }
        });

        Add("observation saving records the exported revision when the saver changes session status", () =>
        {
            using (var f = new Fixture())
            using (var vm = f.ViewModel())
            {
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery();
                f.Interaction.ObservationSaver = text =>
                {
                    vm.StopBatteryObservationCommand.Execute(null);
                    return "recording saved";
                };
                vm.SaveBatteryObservationCommand.Execute(null);
                Check(f.Interaction.LastObservation.Contains("상태: 기록 중"), "export changed mid-save");
                Check(vm.SaveBatteryObservationCommand.CanExecute(null), "a newer terminal revision was falsely marked saved");
                f.Interaction.ObservationSaver = text => "final saved";
                vm.SaveBatteryObservationCommand.Execute(null);
                Equal(2, f.Interaction.ObservationSaves);
                Check(f.Interaction.LastObservation.Contains("상태: 사용자 중지"), "final revision not exported");
                Check(!vm.SaveBatteryObservationCommand.CanExecute(null), "final deduplication failed");
            }
        });
    }
}
