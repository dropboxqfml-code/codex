using System;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.ViewModels;

internal static partial class Program
{
    private static void RegisterManualProtectionViewModelTests()
    {
        Add("manual GUI starts unknown and property reads or battery refreshes never invoke the manual service", () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService(); var battery = new OfflineReviewCountingBattery();
                using (var vm = ManualVm(f, service, battery))
                {
                    int reads = battery.Calls;
                    Check(vm.ManualProtectionAvailable && !vm.ManualProtectionBusy && vm.ManualProtectionLastResult == null, "startup inferred actual mode");
                    Check(vm.ManualReadProtectionCommand.CanExecute(null), "manual status query missing");
                    Check(!vm.ManualEnableProtectionCommand.CanExecute(null) && !vm.ManualDisableProtectionCommand.CanExecute(null), "unknown profile enabled setting");
                    for (int i = 0; i < 50; i++)
                    {
                        Check(vm.ActualModeText.Contains("미조회"), "getter inferred a current setting");
                        Check(vm.ManualProtectionText.Contains("사용자 희망"), "fields are not separated");
                        string ignored = vm.SupportReason + vm.ManualProtectionPhaseText;
                    }
                    Equal(0, service.Operations.Count); Equal(reads, battery.Calls);
                    vm.RefreshBattery(); Equal(reads + 1, battery.Calls); Equal(0, service.Operations.Count);
                }
            }
        });

        AddAsync("manual GUI rejects setting until a completed fixed-profile read and does not change desired mode or Windows percent", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService(); var battery = new OfflineReviewCountingBattery();
                using (var vm = ManualVm(f, service, battery))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.Enable80);
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.DisableProtection);
                    Equal(0, service.Operations.Count);
                    string desired = vm.DesiredModeText, percent = vm.BatteryPercentText;
                    bool restore = vm.RestoreOnBoot; int reads = battery.Calls;
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Equal(1, service.Operations.Count); Equal(reads, battery.Calls);
                    Check(vm.ManualProtectionLastResult.HasKnownMode && vm.ManualProtectionLastResult.ModeCandidate == 0, "read snapshot missing");
                    Check(vm.ManualEnableProtectionCommand.CanExecute(null) && vm.ManualDisableProtectionCommand.CanExecute(null), "validated profile did not admit explicit setting");
                    Equal(desired, vm.DesiredModeText); Equal(percent, vm.BatteryPercentText); Equal(restore, vm.RestoreOnBoot);
                    Check(!vm.CanApply && !vm.IsMockMode, "real request changed the mock path");
                    Equal(0, f.Files.Calls); Equal(0, f.Bundle.Calls); Equal(0, f.Interaction.ObservationSaves);
                }
            }
        });

        AddAsync("manual GUI enable adopts only its completed new snapshot and never polls or performs a second action", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService(); var battery = new OfflineReviewCountingBattery();
                using (var vm = ManualVm(f, service, battery))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    service.Handler = (op, phase) => Task.FromResult(ManualVmChanged(op));
                    int reads = battery.Calls; string desired = vm.DesiredModeText;
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.Enable80);
                    Equal(2, service.Operations.Count); Equal(ManualProtectionOperation.Enable80, service.Operations[1]);
                    Equal(1, vm.ManualProtectionLastResult.ModeCandidate); Equal(80, vm.ManualProtectionLastResult.UpperCandidate);
                    Equal(75, vm.ManualProtectionLastResult.LowerCandidate); Equal(7, vm.ManualProtectionLastResult.SdkEntries);
                    Check(vm.ActualModeText.Contains("모드1") && vm.ManualProtectionText.Contains("Complete"), "completed enable not displayed");
                    Equal(reads, battery.Calls); Equal(desired, vm.DesiredModeText); Check(!vm.CanApply, "real helper enabled legacy mock apply");
                }
            }
        });

        AddAsync("manual GUI disable does not retain old thresholds or label mode zero as full charge success", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService { Handler = (op, phase) => Task.FromResult(ManualVmRead(1)) };
                using (var vm = ManualVm(f, service))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    service.Handler = (op, phase) => Task.FromResult(ManualVmChanged(op));
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.DisableProtection);
                    Equal(0, vm.ManualProtectionLastResult.ModeCandidate);
                    Check(!vm.ManualProtectionLastResult.UpperCandidate.HasValue && !vm.ManualProtectionLastResult.LowerCandidate.HasValue, "old threshold snapshot merged into new result");
                    Check(vm.ManualProtectionText.Contains("상한 후보: 미조회") && vm.ManualProtectionText.Contains("100% 충전 보장이 아니"), "mode zero overstated");
                    Equal(2, service.Operations.Count);
                }
            }
        });

        AddAsync("manual already desired result reports one read without restoring a previously known threshold", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService { Handler = (op, phase) => Task.FromResult(ManualVmRead(1)) };
                using (var vm = ManualVm(f, service))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    service.Handler = (op, phase) => Task.FromResult(new ManualProtectionResult(op,
                        ManualProtectionStatus.AlreadyDesiredCandidate, true, true, 1, 0, 1, 1, 1));
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.Enable80);
                    Equal(1, vm.ManualProtectionLastResult.SdkEntries); Equal(0, vm.ManualProtectionLastResult.SetterEntries);
                    Check(vm.ManualProtectionText.Contains("이번 동작에서 조회하지") && !vm.ManualProtectionText.Contains("상한 후보: 80"), "same mode inferred thresholds");
                    Equal(2, service.Operations.Count);
                }
            }
        });

        AddAsync("manual active request blocks duplicate actions mock changes and closing while permitting existing battery refresh only", async () =>
        {
            using (var f = new Fixture())
            {
                var pending = new TaskCompletionSource<ManualProtectionResult>(TaskCreationOptions.RunContinuationsAsynchronously);
                var service = new ManualVmService { Handler = (op, phase) => pending.Task };
                var battery = new OfflineReviewCountingBattery();
                using (var vm = ManualVm(f, service, battery))
                {
                    var run = vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Check(vm.ManualProtectionBusy && !vm.CanChangeMockMode, "active owner was not reflected in GUI");
                    Check(!vm.ManualReadProtectionCommand.CanExecute(null) && !vm.ManualEnableProtectionCommand.CanExecute(null), "busy command enabled");
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState); Equal(1, service.Operations.Count);
                    vm.IsMockMode = true; Check(!vm.IsMockMode, "mock changed during actual work");
                    vm.NotifyManualCloseBlocked(); Check(vm.ManualProtectionNotice.Contains("창을 닫지"), "close refusal missing");
                    service.LastProgress(ManualProtectionPhase.WaitingForActualCompletion);
                    Equal(ManualProtectionPhase.WaitingForActualCompletion, vm.ManualProtectionCurrentPhase);
                    int reads = battery.Calls; vm.RefreshBattery(); Equal(reads + 1, battery.Calls); Equal(1, service.Operations.Count);
                    pending.SetResult(ManualVmRead(0)); await run;
                    Check(!vm.ManualProtectionBusy && vm.ManualReadProtectionCommand.CanExecute(null), "joined task remained busy");
                    service.LastProgress(ManualProtectionPhase.Uncertain);
                    Equal(ManualProtectionPhase.Completed, vm.ManualProtectionCurrentPhase);
                }
            }
        });

        AddAsync("manual resume invalidation rejects a late successful snapshot and requires a new explicit read", async () =>
        {
            using (var f = new Fixture())
            {
                var pending = new TaskCompletionSource<ManualProtectionResult>(TaskCreationOptions.RunContinuationsAsynchronously);
                var service = new ManualVmService { Handler = (op, phase) => pending.Task };
                using (var vm = ManualVm(f, service))
                {
                    var run = vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    vm.InvalidateManualState(); Check(vm.ManualProtectionBusy, "resume cleared a live owner");
                    pending.SetResult(ManualVmRead(1)); await run;
                    Check(vm.ManualProtectionLastResult == null && !vm.ManualEnableProtectionCommand.CanExecute(null), "late result revived stale support or mode");
                    Check(vm.ManualProtectionNotice.Contains("다시"), "fresh read guidance missing");
                    Equal(1, service.Operations.Count);
                    service.Handler = (op, phase) => Task.FromResult(ManualVmRead(0));
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Equal(2, service.Operations.Count); Check(vm.ManualEnableProtectionCommand.CanExecute(null), "explicit fresh read not adopted");
                }
            }
        });

        AddAsync("manual unconfirmed cleanup remains pending even when invalidated and never admits further operations", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService { Handler = (op, phase) => Task.FromResult(ManualProtectionResult.Failure(op, ManualProtectionStatus.Unknown)) };
                using (var vm = ManualVm(f, service))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Check(vm.ManualProtectionBusy && vm.ManualProtectionPending, "uncertain cleanup released GUI owner");
                    Check(!vm.ManualReadProtectionCommand.CanExecute(null) && !vm.ManualDisableProtectionCommand.CanExecute(null), "pending allows later action");
                    Check(!vm.ManualProtectionText.Contains("SDK 진입: 0") && !vm.ManualProtectionText.Contains("설정 진입: 0"), "unknown counters presented as no execution");
                    vm.InvalidateManualState(); Check(vm.ManualProtectionBusy && !vm.ManualReadProtectionCommand.CanExecute(null), "invalidating unknown state bypassed hold");
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState); Equal(1, service.Operations.Count);
                }
            }
        });

        AddAsync("manual completed cleanup with unknown data and known no-start results permits read but never setting", async () =>
        {
            foreach (var status in new[] { ManualProtectionStatus.Unknown, ManualProtectionStatus.Busy,
                ManualProtectionStatus.Cancelled, ManualProtectionStatus.Unsupported, ManualProtectionStatus.PreflightFailed })
            using (var f = new Fixture())
            {
                var service = new ManualVmService { Handler = (op, phase) => Task.FromResult(ManualProtectionResult.Failure(op, status, true)) };
                using (var vm = ManualVm(f, service))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Check(!vm.ManualProtectionBusy && vm.ManualReadProtectionCommand.CanExecute(null), "known actual closure unnecessarily blocked explicit read");
                    Check(!vm.ManualEnableProtectionCommand.CanExecute(null) && !vm.ManualDisableProtectionCommand.CanExecute(null), "failed read enabled setting");
                    Equal(1, service.Operations.Count); Check(!vm.ActualModeText.Contains("모드1"), "failed result inherited mode");
                }
            }
        });

        AddAsync("manual service block and private failures fail closed without displaying error details", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService { Blocked = true };
                using (var vm = ManualVm(f, service))
                {
                    Check(!vm.ManualReadProtectionCommand.CanExecute(null), "persistent block ignored");
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState); Equal(0, service.Operations.Count);
                    service.Blocked = false;
                    service.Handler = (op, phase) => { throw new InvalidOperationException("C:\\Users\\PRIVATE-ACCOUNT\\UNIQUE-ID"); };
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Check(vm.ManualProtectionPending && !vm.ManualReadProtectionCommand.CanExecute(null), "throw assumed actual completion");
                    Check(!vm.ManualProtectionText.Contains("PRIVATE-ACCOUNT") && !vm.ManualProtectionNotice.Contains("UNIQUE-ID"), "exception leaked to UI");
                    Check(!File.ReadAllText(Path.Combine(f.DirectoryPath, "application.log")).Contains("PRIVATE-ACCOUNT"), "private failure leaked into log");
                }
            }
        });

        AddAsync("manual response belonging to another operation cannot update mode or authorize more writes", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService();
                using (var vm = ManualVm(f, service))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    service.Handler = (op, phase) => Task.FromResult(ManualVmRead(1));
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.Enable80);
                    Check(vm.ManualProtectionPending && !vm.ManualEnableProtectionCommand.CanExecute(null), "foreign result authorized setting");
                    Check(!vm.ManualProtectionLastResult.HasKnownMode, "foreign operation published known mode");
                    Equal(2, service.Operations.Count);
                }
            }
        });

        AddAsync("manual mock and historical reviews never invoke the helper and leaving mock discards prior real state", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService();
                using (var vm = ManualVm(f, service))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    vm.IsMockMode = true;
                    Check(!vm.ManualReadProtectionCommand.CanExecute(null) && vm.ManualProtectionLastResult == null, "mock retained actionable real snapshot");
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    vm.IsProtectionSelected = true; vm.ApplyCommand.Execute(null);
                    vm.ProtectionReviewInput = Protection0To1ReviewFixture(); vm.ReviewProtectionResult();
                    Equal(1, service.Operations.Count);
                    vm.IsMockMode = false;
                    Check(vm.ManualReadProtectionCommand.CanExecute(null) && !vm.ManualDisableProtectionCommand.CanExecute(null), "leaving mock restored stale mode");
                }
            }
        });

        AddAsync("manual dispose ignores late completion and progress without another action or property change", async () =>
        {
            using (var f = new Fixture())
            {
                var pending = new TaskCompletionSource<ManualProtectionResult>(TaskCreationOptions.RunContinuationsAsynchronously);
                var service = new ManualVmService { Handler = (op, phase) => pending.Task };
                var vm = ManualVm(f, service);
                var run = vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                vm.Dispose(); int changes = 0;
                vm.PropertyChanged += (sender, args) => changes++;
                service.LastProgress(ManualProtectionPhase.Running); pending.SetResult(ManualVmRead(1)); await run;
                Equal(0, changes); Check(vm.ManualProtectionLastResult == null, "disposed result revived actual state");
                await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                Equal(1, service.Operations.Count); Check(!vm.ManualReadProtectionCommand.CanExecute(null), "disposed command active");
            }
        });

        Add("observation save status is local to its card and unchanged rows cannot be saved twice even after stop", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                f.Interaction.ObservationSaver = text => "관찰 TXT 저장 완료: battery-observation-example.txt";
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery();
                vm.SaveBatteryObservationCommand.Execute(null);
                Equal(1, f.Interaction.ObservationSaves);
                Check(vm.ObservationSaveStatusText.Contains("battery-observation-example.txt"), "saved file name is not visible near the observation");
                Check(!vm.SaveBatteryObservationCommand.CanExecute(null), "same recording remains saveable");
                vm.SaveBatteryObservationCommand.Execute(null); vm.StopBatteryObservationCommand.Execute(null);
                vm.SaveBatteryObservationCommand.Execute(null); Equal(1, f.Interaction.ObservationSaves);
                Check(!vm.SaveBatteryObservationCommand.CanExecute(null), "stop alone created duplicate data revision");
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery();
                Check(vm.SaveBatteryObservationCommand.CanExecute(null), "new session cannot save identical values");
                vm.SaveBatteryObservationCommand.Execute(null); Equal(2, f.Interaction.ObservationSaves);
            }
        });

        Add("observation failed save preserves data and does not mark a revision saved or leak its error", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); vm.StopBatteryObservationCommand.Execute(null);
                f.Interaction.ObservationSaver = text => { throw new IOException("PRIVATE-SAVE-PATH"); };
                vm.SaveBatteryObservationCommand.Execute(null);
                Check(vm.SaveBatteryObservationCommand.CanExecute(null), "failed save consumed revision");
                Check(vm.ObservationSaveFailed, "failed save lacks visible error state");
                Check(vm.ObservationSaveStatusText.Contains("완료하지 못") && !vm.ObservationSaveStatusText.Contains("PRIVATE-SAVE-PATH"), "save failure feedback missing or private");
                Equal(1, vm.ObservationSampleCount);
                f.Interaction.ObservationSaver = text => "saved once";
                vm.SaveBatteryObservationCommand.Execute(null); Equal(2, f.Interaction.ObservationSaves);
                Check(!vm.ObservationSaveFailed, "successful save retained error state");
                Check(!vm.SaveBatteryObservationCommand.CanExecute(null), "successful retry failed to deduplicate");
            }
        });

        AddAsync("manual result export is explicit bounded and deduplicated without changing control state or replaying the helper", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService();
                using (var vm = ManualVm(f, service))
                {
                    Check(!vm.ManualSaveResultCommand.CanExecute(null), "empty result export enabled");
                    vm.ProtectionReviewInput = "PRIVATE-HISTORY-FOR-ANALYSIS";
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    f.Interaction.ManualResultSaver = text => "제어 결과 저장 완료: manual-control-example.txt";
                    var result = vm.ManualProtectionLastResult;
                    vm.ManualSaveResultCommand.Execute(null); Equal(1, f.Interaction.ManualResultSaves);
                    Check(ReferenceEquals(result, vm.ManualProtectionLastResult), "saving changed the live control snapshot");
                    Check(f.Interaction.LastManualResult.StartsWith("ATIV Battery Guard — 수동 보호 제어 결과"), "sanitized result header missing");
                    Check(f.Interaction.LastManualResult.Contains("마지막 모드 후보: 0") && f.Interaction.LastManualResult.Contains("관련 정리: Complete"), "known detached result missing");
                    Check(!f.Interaction.LastManualResult.Contains("PRIVATE-HISTORY") && !f.Interaction.LastManualResult.Contains("Nonce") &&
                        !f.Interaction.LastManualResult.Contains("JobId") && !f.Interaction.LastManualResult.Contains("SID"), "unrelated source or transport identity exported");
                    Check(vm.ManualSaveStatusText.Contains("manual-control-example.txt"), "saved filename feedback missing");
                    Check(!vm.ManualSaveResultCommand.CanExecute(null), "same immutable result remains saveable");
                    vm.ManualSaveResultCommand.Execute(null); Equal(1, f.Interaction.ManualResultSaves); Equal(1, service.Operations.Count);
                    vm.InvalidateManualState(); Check(!vm.ManualEnableProtectionCommand.CanExecute(null), "saved historical report restored write support");
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    vm.ManualSaveResultCommand.Execute(null); Equal(2, f.Interaction.ManualResultSaves); Equal(2, service.Operations.Count);
                }
            }
        });

        AddAsync("manual pending result export hides unobserved counters and failed save can retry without another device request", async () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService { Handler = (op, phase) => Task.FromResult(ManualProtectionResult.Failure(op, ManualProtectionStatus.Unknown)) };
                using (var vm = ManualVm(f, service))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Check(vm.ManualProtectionPending && vm.ManualSaveResultCommand.CanExecute(null), "pending report cannot be saved");
                    f.Interaction.ManualResultSaver = text => { throw new IOException("PRIVATE-MANUAL-SAVE-PATH"); };
                    vm.ManualSaveResultCommand.Execute(null); Equal(1, f.Interaction.ManualResultSaves);
                    Check(vm.ManualSaveFailed && vm.ManualSaveResultCommand.CanExecute(null), "failed save consumed result revision");
                    Check(!vm.ManualSaveStatusText.Contains("PRIVATE-MANUAL-SAVE-PATH"), "save exception leaked to UI");
                    Check(f.Interaction.LastManualResult.Contains("미관측") && f.Interaction.LastManualResult.Contains("현재 보호 상태: 미확인") &&
                        !f.Interaction.LastManualResult.Contains("SDK 진입: 0"), "pending export inferred no hardware calls");
                    f.Interaction.ManualResultSaver = text => "manual-control-pending.txt 저장 완료";
                    vm.ManualSaveResultCommand.Execute(null); Equal(2, f.Interaction.ManualResultSaves);
                    Check(!vm.ManualSaveFailed && !vm.ManualSaveResultCommand.CanExecute(null), "successful save did not deduplicate");
                    Check(vm.ManualProtectionPending && !vm.ManualReadProtectionCommand.CanExecute(null), "report saving released pending control");
                    Equal(1, service.Operations.Count);
                }
            }
        });

        Add("observation folder action does not start a helper or save another file", () =>
        {
            using (var f = new Fixture())
            {
                var service = new ManualVmService(); var battery = new OfflineReviewCountingBattery();
                using (var vm = ManualVm(f, service, battery))
                {
                    int reads = battery.Calls;
                    vm.OpenSettingsFolderCommand.Execute(null);
                    Equal(1, f.Interaction.FoldersOpened); Equal(0, f.Interaction.ObservationSaves);
                    Equal(0, service.Operations.Count); Equal(reads, battery.Calls);
                }
            }
        });
    }

    private static MainViewModel ManualVm(Fixture f, ManualVmService service, OfflineReviewCountingBattery battery = null)
        => new MainViewModel(battery ?? new OfflineReviewCountingBattery(), f.Store, new LocalLog(f.DirectoryPath),
            f.Interaction, f.Hardware, f.Bundle, () => true, f.Files, service);

    private static ManualProtectionResult ManualVmRead(int mode)
        => new ManualProtectionResult(ManualProtectionOperation.ReadState, ManualProtectionStatus.StateRead,
            true, true, 3, 0, 3, mode, mode, 80, 75);

    private static ManualProtectionResult ManualVmChanged(ManualProtectionOperation op)
        => op == ManualProtectionOperation.Enable80
            ? new ManualProtectionResult(op, ManualProtectionStatus.ChangedCandidate, true, true, 7, 1, 6, 0, 1, 80, 75)
            : new ManualProtectionResult(op, ManualProtectionStatus.ChangedCandidate, true, true, 3, 1, 2, 1, 0);

    private sealed class ManualVmService : IManualProtectionOperationService
    {
        internal readonly List<ManualProtectionOperation> Operations = new List<ManualProtectionOperation>();
        internal bool Blocked;
        internal Func<ManualProtectionOperation, Action<ManualProtectionPhase>, Task<ManualProtectionResult>> Handler;
        internal Action<ManualProtectionPhase> LastProgress;
        public bool IsBlocked => Blocked;
        public Task<ManualProtectionResult> RunAsync(ManualProtectionOperation operation, Action<ManualProtectionPhase> progress)
        {
            Operations.Add(operation); LastProgress = progress;
            return Handler == null ? Task.FromResult(ManualVmRead(0)) : Handler(operation, progress);
        }
    }
}
