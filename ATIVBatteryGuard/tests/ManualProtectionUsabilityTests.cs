using System;
using System.Globalization;
using System.IO;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.ViewModels;

internal static partial class Program
{
    private static void RegisterManualProtectionUsabilityTests()
    {
        AddAsync("manual release and unobserved receipt getters never query the clock or helper", async () =>
        {
            using (var f = new Fixture())
            {
                var clock = new ManualUsabilityClock();
                var service = new ManualVmService();
                var battery = new OfflineReviewCountingBattery();
                using (var vm = ManualUsabilityVm(f, service, clock, battery))
                {
                    Equal("0.2.0-beta.3", ApplicationRelease.Version);
                    Equal(ApplicationRelease.DisplayText, vm.ApplicationVersionText);
                    int batteryReads = battery.Calls;
                    for (int i = 0; i < 25; i++)
                    {
                        Equal("마지막 보호 조회 결과 수신: 미관측", vm.ManualProtectionReadTimeText);
                        string ignored = vm.ApplicationVersionText + vm.ManualProtectionStateText + vm.ManualProtectionText;
                    }
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.Enable80);
                    await vm.RunManualProtectionAsync((ManualProtectionOperation)99);
                    service.Blocked = true;
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    service.Blocked = false;
                    vm.IsMockMode = true;
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    vm.IsMockMode = false;
                    vm.InvalidateManualState();
                    Equal(0, clock.Calls); Equal(0, service.Operations.Count);
                    Equal(batteryReads, battery.Calls);
                    vm.RefreshBattery();
                    Equal(batteryReads + 1, battery.Calls); Equal(0, clock.Calls); Equal(0, service.Operations.Count);
                }
            }
        });

        AddAsync("manual receipt records one accepted read and displays a cached local offset", async () =>
        {
            using (var f = new Fixture())
            {
                var clock = new ManualUsabilityClock();
                var pending = new TaskCompletionSource<ManualProtectionResult>(TaskCreationOptions.RunContinuationsAsynchronously);
                var service = new ManualVmService { Handler = (op, progress) => pending.Task };
                var battery = new OfflineReviewCountingBattery();
                using (var vm = ManualUsabilityVm(f, service, clock, battery))
                {
                    int receiptChanges = 0;
                    vm.PropertyChanged += (sender, args) => { if (args.PropertyName == "ManualProtectionReadTimeText") receiptChanges++; };
                    var run = vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Equal(1, clock.Calls);
                    Equal("마지막 보호 조회 결과 수신: 미관측", vm.ManualProtectionReadTimeText);
                    service.LastProgress(ManualProtectionPhase.Running);
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Equal(1, clock.Calls); Equal(1, service.Operations.Count);
                    clock.Current = clock.Current.AddMinutes(2);
                    DateTimeOffset receipt = clock.Current;
                    pending.SetResult(ManualVmRead(1)); await run;
                    Equal(2, clock.Calls);
                    string visible = vm.ManualProtectionReadTimeText;
                    Check(visible.StartsWith("마지막 보호 조회 결과 수신: ") && visible.Contains("GUI 수신 시각"), "receipt is not labelled as a GUI observation");
                    Check(visible.Contains(receipt.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss zzz", CultureInfo.InvariantCulture)), "receipt lacks the captured local time and offset");
                    Check(receiptChanges >= 2, "receipt binding was not notified at request and completion");
                    clock.Current = clock.Current.AddDays(1);
                    int batteryReads = battery.Calls;
                    for (int i = 0; i < 25; i++) Equal(visible, vm.ManualProtectionReadTimeText);
                    service.LastProgress(ManualProtectionPhase.Uncertain);
                    Equal(ManualProtectionPhase.Completed, vm.ManualProtectionCurrentPhase);
                    Equal(batteryReads, battery.Calls); Equal(2, clock.Calls);
                    vm.RefreshBattery(); Equal(visible, vm.ManualProtectionReadTimeText);
                    Equal(2, clock.Calls); Equal(1, service.Operations.Count);
                }
            }
        });

        AddAsync("a new accepted setting clears the old receipt until its own successful result arrives", async () =>
        {
            using (var f = new Fixture())
            {
                var clock = new ManualUsabilityClock(); var service = new ManualVmService();
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    string firstReceipt = vm.ManualProtectionReadTimeText;
                    var pending = new TaskCompletionSource<ManualProtectionResult>(TaskCreationOptions.RunContinuationsAsynchronously);
                    service.Handler = (op, progress) => pending.Task;
                    clock.Current = clock.Current.AddHours(1);
                    var run = vm.RunManualProtectionAsync(ManualProtectionOperation.Enable80);
                    Equal("마지막 보호 조회 결과 수신: 미관측", vm.ManualProtectionReadTimeText);
                    Check(vm.ManualProtectionLastResult == null && !vm.ManualSaveResultCommand.CanExecute(null), "new request retained an old live result or report");
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.DisableProtection);
                    Equal(2, service.Operations.Count); Equal(3, clock.Calls);
                    clock.Current = clock.Current.AddMinutes(1);
                    pending.SetResult(ManualVmChanged(ManualProtectionOperation.Enable80)); await run;
                    Equal(4, clock.Calls);
                    Check(vm.ManualProtectionReadTimeText != firstReceipt && !vm.ManualProtectionReadTimeText.Contains("미관측"), "new known result did not replace its receipt");
                    Equal<int?>(1, vm.ManualProtectionLastResult.ModeCandidate);
                }
            }
        });

        AddAsync("manual report UTC metadata survives invalidation and failed save without taking a new time", async () =>
        {
            using (var f = new Fixture())
            {
                var clock = new ManualUsabilityClock(); DateTimeOffset started = clock.Current;
                var service = new ManualVmService { Handler = (op, progress) => { clock.Current = clock.Current.AddMinutes(3); return Task.FromResult(ManualVmRead(0)); } };
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    DateTimeOffset received = clock.Current;
                    vm.InvalidateManualState();
                    Equal("마지막 보호 조회 결과 수신: 미관측", vm.ManualProtectionReadTimeText);
                    Check(vm.ManualSaveResultCommand.CanExecute(null), "invalidation removed the historical report");
                    f.Interaction.ManualResultSaver = text => { throw new IOException("PRIVATE-SAVE-PATH"); };
                    clock.Current = clock.Current.AddDays(7);
                    vm.ManualSaveResultCommand.Execute(null);
                    string firstExport = f.Interaction.LastManualResult;
                    Check(vm.ManualSaveFailed && vm.ManualSaveResultCommand.CanExecute(null), "failed save consumed the report");
                    Check(firstExport.StartsWith("ATIV Battery Guard — 수동 보호 제어 결과\n해당 요청의 저장 후보·정리 보고입니다."), "existing report prefix changed");
                    Check(firstExport.Contains("배포 버전: " + ApplicationRelease.Version), "release version missing");
                    Check(firstExport.Contains("GUI 요청 시작 시각 (UTC): " + started.ToUniversalTime().ToString("O", CultureInfo.InvariantCulture)), "request start was not captured as invariant UTC ISO8601");
                    Check(firstExport.Contains("GUI 결과 기록 시각 (UTC): " + received.ToUniversalTime().ToString("O", CultureInfo.InvariantCulture)), "result record time was not captured as invariant UTC ISO8601");
                    Check(firstExport.Contains("GUI 수신 시각") && firstExport.Contains("정확한 펌웨어 읽기 시각이나 TXT 저장 시각이 아닙니다"), "report does not explain the timestamp limits");
                    clock.Current = clock.Current.AddMonths(1);
                    f.Interaction.ManualResultSaver = text => "저장 완료";
                    vm.ManualSaveResultCommand.Execute(null);
                    Equal(firstExport, f.Interaction.LastManualResult); Equal(2, clock.Calls);
                    Check(!vm.ManualSaveFailed && !vm.ManualSaveResultCommand.CanExecute(null), "successful retry did not deduplicate");
                    Check(vm.ManualProtectionLastResult == null && !vm.ManualEnableProtectionCommand.CanExecute(null), "historical export authorized a setting");
                    Equal(1, service.Operations.Count); Equal(2, f.Interaction.ManualResultSaves);
                }
            }
        });

        AddAsync("a result crossing suspend resume invalidation keeps only historical receipt metadata", async () =>
        {
            using (var f = new Fixture())
            {
                var clock = new ManualUsabilityClock();
                var pending = new TaskCompletionSource<ManualProtectionResult>(TaskCreationOptions.RunContinuationsAsynchronously);
                var service = new ManualVmService { Handler = (op, progress) => pending.Task };
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    var run = vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    vm.InvalidateManualState(); vm.InvalidateManualState();
                    clock.Current = clock.Current.AddMinutes(1);
                    DateTimeOffset received = clock.Current;
                    pending.SetResult(ManualVmRead(1)); await run;
                    Equal("마지막 보호 조회 결과 수신: 미관측", vm.ManualProtectionReadTimeText);
                    Check(vm.ManualProtectionLastResult == null && !vm.ManualEnableProtectionCommand.CanExecute(null), "late result revived a stale mode");
                    vm.ManualSaveResultCommand.Execute(null);
                    Check(f.Interaction.LastManualResult.Contains(received.ToUniversalTime().ToString("O", CultureInfo.InvariantCulture)), "late historical result lost its record time");
                    Equal(2, clock.Calls); Equal(1, service.Operations.Count);
                    service.Handler = (op, progress) => Task.FromResult(ManualVmRead(0));
                    clock.Current = clock.Current.AddMinutes(2);
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Check(!vm.ManualProtectionReadTimeText.Contains("미관측") && vm.ManualEnableProtectionCommand.CanExecute(null), "fresh explicit read did not restore a valid receipt");
                    Equal(4, clock.Calls); Equal(2, service.Operations.Count);
                }
            }
        });

        AddAsync("Mock transitions discard the visible receipt while keeping historical export metadata", async () =>
        {
            using (var f = new Fixture())
            {
                var clock = new ManualUsabilityClock(); var service = new ManualVmService();
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    DateTimeOffset received = clock.Current;
                    vm.IsMockMode = true;
                    Equal("마지막 보호 조회 결과 수신: 미관측", vm.ManualProtectionReadTimeText);
                    Check(vm.ManualSaveResultCommand.CanExecute(null), "Mock removed historical export");
                    clock.Current = clock.Current.AddDays(2);
                    vm.ManualSaveResultCommand.Execute(null);
                    Check(f.Interaction.LastManualResult.Contains(received.ToUniversalTime().ToString("O", CultureInfo.InvariantCulture)), "Mock rewrote a historical timestamp");
                    vm.IsMockMode = false;
                    Equal("마지막 보호 조회 결과 수신: 미관측", vm.ManualProtectionReadTimeText);
                    Check(!vm.ManualEnableProtectionCommand.CanExecute(null) && !vm.ManualDisableProtectionCommand.CanExecute(null), "leaving Mock revived historical write support");
                    Equal(2, clock.Calls); Equal(1, service.Operations.Count);
                }
            }
        });

        AddAsync("all failed manual results clear the visible receipt and give distinct next action guidance", async () =>
        {
            var statuses = new[] { ManualProtectionStatus.Cancelled, ManualProtectionStatus.Unsupported,
                ManualProtectionStatus.PreflightFailed, ManualProtectionStatus.Rejected, ManualProtectionStatus.Busy,
                ManualProtectionStatus.TimedOut, ManualProtectionStatus.Unknown };
            var guidance = new[] { "보호 상태 확인", "지원 범위", "배포 파일", "결과 TXT", "진행 중인 창", "정리는 끝났", "다시 읽으세요" };
            for (int i = 0; i < statuses.Length; i++)
            using (var f = new Fixture())
            {
                var clock = new ManualUsabilityClock(); var service = new ManualVmService();
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    var status = statuses[i];
                    service.Handler = (op, progress) => Task.FromResult(ManualProtectionResult.Failure(op, status, true));
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Equal("마지막 보호 조회 결과 수신: 미관측", vm.ManualProtectionReadTimeText);
                    Check(vm.ManualProtectionNotice.Contains(guidance[i]), "failure lacks its next action: " + status);
                    Check(!vm.ManualProtectionBusy && vm.ManualReadProtectionCommand.CanExecute(null), "completed cleanup retained a live owner: " + status);
                    Check(!vm.ManualEnableProtectionCommand.CanExecute(null) && !vm.ManualDisableProtectionCommand.CanExecute(null), "failure enabled writes: " + status);
                    Equal(4, clock.Calls); Equal(2, service.Operations.Count);
                }
            }
        });

        AddAsync("null foreign and throwing result sources keep unknown counters and safe historical times", async () =>
        {
            for (int source = 0; source < 3; source++)
            using (var f = new Fixture())
            {
                var clock = new ManualUsabilityClock(); int selectedSource = source;
                var service = new ManualVmService { Handler = (op, progress) =>
                {
                    if (selectedSource == 2) throw new InvalidOperationException("PRIVATE-ACCOUNT-PATH");
                    return Task.FromResult(selectedSource == 0 ? null : ManualVmChanged(ManualProtectionOperation.Enable80));
                } };
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Equal("마지막 보호 조회 결과 수신: 미관측", vm.ManualProtectionReadTimeText);
                    Check(vm.ManualProtectionPending && !vm.ManualReadProtectionCommand.CanExecute(null), "unknown source released actual cleanup hold");
                    Check(vm.ManualProtectionNotice.Contains("결과 TXT") && vm.ManualProtectionNotice.Contains("기다리세요"), "pending result lacks safe next action");
                    vm.InvalidateManualState(); vm.ManualSaveResultCommand.Execute(null);
                    Check(vm.ManualProtectionNotice.Contains("앱·helper를 강제로 닫거나 다시 실행하지 말고"), "invalidation lost the visible pending safety guidance");
                    string report = f.Interaction.LastManualResult;
                    Check(report.Contains("GUI 결과 기록 시각 (UTC): ") && report.Contains("SDK 진입·설정 진입·수용 읽기: 미관측"), "unknown source lost its metadata or invented counters");
                    Check(!report.Contains("SDK 진입: 0") && !report.Contains("PRIVATE-ACCOUNT-PATH"), "unknown source inferred zero execution or leaked private data");
                    Check(vm.ManualProtectionPending && !vm.ManualEnableProtectionCommand.CanExecute(null), "export or invalidation released pending safety state");
                    Equal(2, clock.Calls); Equal(1, service.Operations.Count);
                }
            }
        });

        AddAsync("pending timeout explains actual cleanup and never restores the previous receipt", async () =>
        {
            using (var f = new Fixture())
            {
                var clock = new ManualUsabilityClock(); var service = new ManualVmService();
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    service.Handler = (op, progress) => Task.FromResult(ManualProtectionResult.Failure(op, ManualProtectionStatus.TimedOut));
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.DisableProtection);
                    Equal("마지막 보호 조회 결과 수신: 미관측", vm.ManualProtectionReadTimeText);
                    Check(vm.ManualProtectionNotice.Contains("표시 시간") && vm.ManualProtectionNotice.Contains("실제 정리는 미확인"), "timeout was confused with actual completion");
                    Check(vm.ManualProtectionNotice.Contains("자동 재시도하지 않습니다") && vm.ManualProtectionPending, "timeout lost pending safety guidance");
                    Check(vm.ManualProtectionNotice.Contains("앱·helper를 강제로 닫거나 다시 실행하지 말고") &&
                        !vm.ManualProtectionNotice.Contains("정리는 끝났") && !vm.ManualProtectionNotice.Contains("보호 상태 확인을 직접"), "completed-result advice overrode the pending cleanup hold");
                    vm.ManualSaveResultCommand.Execute(null);
                    Check(f.Interaction.LastManualResult.Contains("SDK 진입·설정 진입·수용 읽기: 미관측"), "timeout invented zero calls");
                    Equal(4, clock.Calls); Equal(2, service.Operations.Count);
                }
            }
        });

        AddAsync("each accepted request can export once even if its detached result object is reused", async () =>
        {
            using (var f = new Fixture())
            {
                var clock = new ManualUsabilityClock(); var shared = ManualVmRead(0);
                var service = new ManualVmService { Handler = (op, progress) => Task.FromResult(shared) };
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    vm.ManualSaveResultCommand.Execute(null);
                    string first = f.Interaction.LastManualResult;
                    vm.ManualSaveResultCommand.Execute(null); Equal(1, f.Interaction.ManualResultSaves);
                    clock.Current = clock.Current.AddHours(1);
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Check(vm.ManualSaveResultCommand.CanExecute(null), "new request sharing a result object was deduplicated as an old request");
                    vm.ManualSaveResultCommand.Execute(null);
                    Check(first != f.Interaction.LastManualResult, "new accepted request reused old metadata");
                    vm.ManualSaveResultCommand.Execute(null);
                    Equal(2, f.Interaction.ManualResultSaves); Equal(2, service.Operations.Count); Equal(4, clock.Calls);
                }
            }
        });

        AddAsync("unavailable GUI clock metadata cannot turn completed cleanup into an unknown device result", async () =>
        {
            using (var f = new Fixture())
            {
                var clock = new ManualUsabilityClock { Throw = true }; var service = new ManualVmService();
                using (var vm = ManualUsabilityVm(f, service, clock))
                {
                    await vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                    Check(vm.ManualProtectionLastResult.HasKnownMode && !vm.ManualProtectionPending && !vm.ManualProtectionBusy, "metadata error altered actual completion");
                    Check(vm.ManualEnableProtectionCommand.CanExecute(null), "metadata error discarded a valid completed read");
                    Equal("마지막 보호 조회 결과 수신: 미관측", vm.ManualProtectionReadTimeText);
                    vm.ManualSaveResultCommand.Execute(null);
                    Check(f.Interaction.LastManualResult.Contains("GUI 요청 시작 시각 (UTC): 미관측") &&
                        f.Interaction.LastManualResult.Contains("GUI 결과 기록 시각 (UTC): 미관측"), "missing clock was fabricated");
                    Check(f.Interaction.LastManualResult.Contains("관련 정리: Complete") && f.Interaction.LastManualResult.Contains("마지막 모드 후보: 0"), "clock error replaced the actual result");
                    Check(!f.Interaction.LastManualResult.Contains("PRIVATE-CLOCK-FAILURE"), "clock exception was exported");
                    Equal(2, clock.Calls); Equal(1, service.Operations.Count);
                }
            }
        });

        AddAsync("disposing during a manual request prevents late receipt publication or new clock reads", async () =>
        {
            using (var f = new Fixture())
            {
                var clock = new ManualUsabilityClock();
                var pending = new TaskCompletionSource<ManualProtectionResult>(TaskCreationOptions.RunContinuationsAsynchronously);
                var service = new ManualVmService { Handler = (op, progress) => pending.Task };
                var vm = ManualUsabilityVm(f, service, clock);
                var run = vm.RunManualProtectionAsync(ManualProtectionOperation.ReadState);
                vm.Dispose(); int changes = 0;
                vm.PropertyChanged += (sender, args) => changes++;
                clock.Current = clock.Current.AddHours(1);
                service.LastProgress(ManualProtectionPhase.Completed);
                pending.SetResult(ManualVmRead(1)); await run;
                Equal(0, changes); Equal(1, clock.Calls);
                Equal("마지막 보호 조회 결과 수신: 미관측", vm.ManualProtectionReadTimeText);
                Check(vm.ManualProtectionLastResult == null && !vm.ManualSaveResultCommand.CanExecute(null), "disposed result became visible or exportable");
                Equal(1, service.Operations.Count);
            }
        });
    }

    private static MainViewModel ManualUsabilityVm(Fixture f, ManualVmService service, ManualUsabilityClock clock, OfflineReviewCountingBattery battery = null)
        => new MainViewModel(battery ?? new OfflineReviewCountingBattery(), f.Store, new LocalLog(f.DirectoryPath),
            f.Interaction, f.Hardware, f.Bundle, () => true, f.Files, service, clock.Read);

    private sealed class ManualUsabilityClock
    {
        internal DateTimeOffset Current = new DateTimeOffset(2026, 11, 10, 9, 0, 0, TimeSpan.FromHours(9));
        internal int Calls;
        internal bool Throw;
        internal DateTimeOffset Read()
        {
            Calls++;
            if (Throw) throw new InvalidOperationException("PRIVATE-CLOCK-FAILURE");
            return Current;
        }
    }
}
