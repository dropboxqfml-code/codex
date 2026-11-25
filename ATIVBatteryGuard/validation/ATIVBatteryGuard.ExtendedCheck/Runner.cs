using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.Serialization.Json;
using System.Text;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Threading;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Services;
using ATIVBatteryGuard.Validation;
using ATIVBatteryGuard.ViewModels;
using ATIVBatteryGuard.Views;

namespace ATIVBatteryGuard.ExtendedValidation
{
    internal sealed class Runner
    {
        private sealed class Failure : Exception
        {
            public string Code;
            public Failure(string code) { Code = code; }
        }
        private sealed class BindingListener : TraceListener
        {
            public int Errors;
            public override void Write(string message) { }
            public override void WriteLine(string message) { }
            public override void TraceEvent(TraceEventCache cache, string source, TraceEventType kind,
                int id, string message) { if (kind == TraceEventType.Error || kind == TraceEventType.Critical) Errors++; }
            public override void TraceEvent(TraceEventCache cache, string source, TraceEventType kind,
                int id, string format, params object[] args) { TraceEvent(cache, source, kind, id, format); }
        }
        private readonly Application app;
        private readonly string root;
        private readonly ValidationManifest manifest;
        private readonly bool soak;
        private readonly RunReport report = new RunReport();
        private MainViewModel first, second;
        private MainWindow windowA, windowB;
        private TestInteraction interactionA, interactionB;
        private SavedBatteryObservation recordA, recordB;
        private string temporary, resultPath;
        private bool closingInternally, testingWindowClose;
        public Runner(Application app, string root, ValidationManifest manifest, bool soak)
        { this.app = app; this.root = root; this.manifest = manifest; this.soak = soak; }

        public async Task<int> Run()
        {
            var binding = new BindingListener();
            var trace = PresentationTraceSources.DataBindingSource;
            var oldLevel = trace.Switch.Level;
            try
            {
                report.Mode = soak ? "soak-20-minutes" : "quick-30-cycles";
                report.SourceFingerprintSha256 = manifest.SourceFingerprintSha256;
                report.FilesVerifiedBefore = true;
                string results = LocalPathPolicy.NormalizeDirectory(Path.Combine(root, "extended-results"));
                Directory.CreateDirectory(results);
                resultPath = LocalPathPolicy.NormalizeFile(Path.Combine(results, "extended-" + Guid.NewGuid().ToString("N") + ".json"));
                using (new FileStream(resultPath, FileMode.CreateNew, FileAccess.Write, FileShare.None)) { }
                Checkpoint();
                trace.Listeners.Add(binding); trace.Switch.Level = SourceLevels.Error;
                temporary = LocalPathPolicy.NormalizeDirectory(Path.Combine(Path.GetTempPath(), "ATIV-extended-" + Guid.NewGuid().ToString("N")));
                Directory.CreateDirectory(temporary);
                recordA = Fixture("Extended.SampleA"); recordB = Fixture("Extended.SampleB");
                interactionA = new TestInteraction(temporary); interactionB = new TestInteraction(temporary);
                first = Model(interactionA); second = Model(interactionB);
                windowA = Window(first); windowB = Window(second);
                app.MainWindow = windowA; windowA.Show(); windowB.Show();
                await Idle();
                report.Phase = "korean-binding-and-cancel"; Checkpoint();
                await Open(windowA, interactionA, recordA, false);
                await Edit(windowA, "ANoteText", "한글 저장 확인\r\n두 번째 줄");
                await Click(windowA, "SaveANoteButton");
                Require(interactionA.ReadNote(recordA).Text == "한글 저장 확인\n두 번째 줄", "KOREAN_SAVE_INVALID");
                await CloseRecords(windowA, first);
                await Open(windowA, interactionA, recordA, false);
                Require(first.SavedObservationNote.Text == "한글 저장 확인\n두 번째 줄", "KOREAN_REOPEN_INVALID");
                report.CommittedKoreanBindingPassed = true;
                await Edit(windowA, "ANoteText", "닫기 취소 초안");
                interactionA.NextChoice = ObservationLossChoice.Cancel;
                app.MainWindow = windowA;
                testingWindowClose = true;
                try { windowA.Close(); } finally { testingWindowClose = false; }
                await Idle();
                Require(windowA.IsVisible && first.SavedObservationNote.Text == "닫기 취소 초안", "WINDOW_CLOSE_CANCEL_INVALID");
                report.WindowCloseCancelPassed = true;
                await Open(windowA, interactionA, recordB, true);
                await Edit(windowA, "BNoteText", "비교 취소 초안");
                await CloseRecords(windowA, first);
                Require(first.SavedObservationVisible && first.ComparisonObservationVisible
                    && first.SavedObservationNote.Text == "닫기 취소 초안" && first.ComparisonObservationNote.Text == "비교 취소 초안", "AB_CANCEL_INVALID");
                report.BothDraftsCancelPassed = true;
                interactionA.NextChoice = ObservationLossChoice.Save;
                await CloseRecords(windowA, first);
                Require(!first.SavedObservationVisible, "CONFIRMED_SAVE_CLOSE_INVALID");

                report.Phase = "two-window-conflict"; Checkpoint();
                await Open(windowA, interactionA, recordA, false);
                await Open(windowB, interactionB, recordA, false);
                await Open(windowB, interactionB, recordB, true);
                await Edit(windowA, "ANoteText", "첫 창 저장");
                await Edit(windowB, "ANoteText", "둘째 창 초안");
                await Edit(windowB, "BNoteText", "B 유지 초안");
                await Click(windowA, "SaveANoteButton");
                await Click(windowB, "SaveANoteButton");
                Require(second.SavedObservationNote.HasChanges && second.SavedObservationNote.Status.Contains("다른 창")
                    && second.SavedObservationNote.Text == "둘째 창 초안" && interactionB.ReadNote(recordA).Text == "첫 창 저장", "CONFLICT_DRAFT_LOST");
                interactionB.NextChoice = ObservationLossChoice.Save;
                await CloseRecords(windowB, second);
                Require(second.SavedObservationVisible && second.ComparisonObservationNote.Text == "B 유지 초안", "CONFLICT_CLOSE_NOT_BLOCKED");
                await Click(windowB, "ExportObservationBundleButton");
                Require(ObservationBundle.ReadFile(interactionB.LastBundle).NoteText == "둘째 창 초안"
                    && second.SavedObservationNote.HasChanges, "CONFLICT_BACKUP_INVALID");
                interactionB.NextChoice = ObservationLossChoice.Cancel;
                await InvokeCommand(windowB, second.SavedObservationNote.ReloadCommand);
                Require(second.SavedObservationNote.Text == "둘째 창 초안", "RELOAD_CANCEL_LOST_DRAFT");
                interactionB.NextChoice = ObservationLossChoice.Discard;
                await InvokeCommand(windowB, second.SavedObservationNote.ReloadCommand);
                Require(second.SavedObservationNote.Text == "첫 창 저장" && second.ComparisonObservationNote.Text == "B 유지 초안", "RELOAD_LATEST_INVALID");
                report.TwoWindowConflictAndBackupPassed = true;

                report.Phase = "locked-save-retry"; Checkpoint();
                await Edit(windowB, "ANoteText", "잠금 해제 후 저장");
                interactionB.NextChoice = ObservationLossChoice.Save;
                string lockPath = Path.Combine(temporary, "observation-notes", recordA.NoteKey + ".json.lock");
                using (var lease = new FileStream(lockPath, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                {
                    await CloseRecords(windowB, second);
                    Require(second.SavedObservationVisible && second.SavedObservationNote.Text == "잠금 해제 후 저장"
                        && interactionB.ReadNote(recordA).Text == "첫 창 저장", "LOCKED_SAVE_LOST_DRAFT");
                }
                await CloseRecords(windowB, second);
                Require(!second.SavedObservationVisible && interactionB.ReadNote(recordA).Text == "잠금 해제 후 저장", "LOCKED_SAVE_RETRY_INVALID");
                report.LockedSaveRetryPassed = true;
                interactionA.NextChoice = ObservationLossChoice.Discard;
                await CloseRecords(windowA, first);
                report.AutomatedDialogCount = interactionA.Confirmations + interactionB.Confirmations;
                report.OwnedNativeConfirmationDialogsPassed = report.AutomatedDialogCount >= 8
                    && !interactionA.DialogAutomationFailed && !interactionB.DialogAutomationFailed;
                Require(report.OwnedNativeConfirmationDialogsPassed, "DIALOG_COVERAGE_INCOMPLETE");

                report.Phase = "repeating"; Checkpoint();
                var clock = Stopwatch.StartNew(); double sampled = -30, previousCycle = 0;
                do
                {
                    StopIfRequested();
                    await Open(windowA, interactionA, recordA, false);
                    await Open(windowA, interactionA, recordB, true);
                    await Edit(windowA, "ANoteText", "반복 A " + report.CompletedCycles);
                    await Edit(windowA, "BNoteText", "반복 B " + report.CompletedCycles);
                    await Click(windowA, "SaveANoteButton"); await Click(windowA, "SaveBNoteButton");
                    await CloseRecords(windowA, first);
                    Require(!first.SavedObservationVisible && !first.ComparisonObservationVisible, "REPEAT_CLOSE_INVALID");
                    VerifyReleased(recordA); VerifyReleased(recordB);
                    report.CompletedCycles++;
                    report.RepetitionSeconds = clock.Elapsed.TotalSeconds;
                    double gap = clock.Elapsed.TotalSeconds - previousCycle;
                    previousCycle = clock.Elapsed.TotalSeconds;
                    report.MaximumCycleGapSeconds = Math.Max(report.MaximumCycleGapSeconds, gap);
                    Require(ExtendedPolicy.CycleGapAccepted(gap), "REPETITION_STALL_OR_SUSPEND");
                    if (clock.Elapsed.TotalSeconds - sampled >= 30)
                    {
                        await Sample(clock); sampled = clock.Elapsed.TotalSeconds; Checkpoint();
                        Console.WriteLine("반복 " + report.CompletedCycles + "회 / " + (int)clock.Elapsed.TotalSeconds + "초");
                    }
                    await Task.Delay(soak ? 2000 : 10);
                } while (!ExtendedPolicy.RunComplete(soak, report.CompletedCycles, clock.Elapsed.TotalSeconds));
                report.RepetitionSeconds = clock.Elapsed.TotalSeconds;
                double finalGap = clock.Elapsed.TotalSeconds - previousCycle;
                report.MaximumCycleGapSeconds = Math.Max(report.MaximumCycleGapSeconds, finalGap);
                Require(ExtendedPolicy.CycleGapAccepted(finalGap), "REPETITION_STALL_OR_SUSPEND");
                await Sample(clock);
                Require(binding.Errors == 0, "WPF_BINDING_ERRORS");
            }
            catch (Failure error) { report.ErrorCode = error.Code; }
            catch { report.ErrorCode = "EXTENDED_CHECK_FAILED"; }
            finally
            {
                report.StopRequested = Program.StopRequested;
                report.BindingErrors = binding.Errors;
                trace.Listeners.Remove(binding); trace.Switch.Level = oldLevel;
                closingInternally = true;
                try { first?.Dispose(); second?.Dispose(); windowA?.Close(); windowB?.Close(); }
                catch { report.ErrorCode = report.ErrorCode ?? "WINDOW_CLEANUP_FAILED"; }
                try
                {
                    if (temporary != null) { LocalPathPolicy.NormalizeDirectory(temporary); Directory.Delete(temporary, true); }
                    report.CleanupSucceeded = true;
                }
                catch { report.CleanupSucceeded = false; }
                try { ValidationEvidence.VerifyFiles(root, manifest); report.FilesVerifiedAfter = true; }
                catch { report.FilesVerifiedAfter = false; }
                bool scenarios = report.ErrorCode == null && report.CommittedKoreanBindingPassed && report.WindowCloseCancelPassed
                    && report.BothDraftsCancelPassed && report.TwoWindowConflictAndBackupPassed && report.LockedSaveRetryPassed
                    && report.OwnedNativeConfirmationDialogsPassed;
                report.Outcome = ExtendedPolicy.Outcome(report.StopRequested, report.FilesVerifiedBefore, report.FilesVerifiedAfter,
                    scenarios, ExtendedPolicy.RunComplete(soak, report.CompletedCycles, report.RepetitionSeconds), report.BindingErrors, report.CleanupSucceeded);
                report.LastActivePhase = report.Phase;
                report.Phase = "completed"; report.CompletedUtc = DateTime.UtcNow.ToString("O");
                try { Checkpoint(); Console.WriteLine("결과: " + report.Outcome + "\nextended-results: " + Path.GetFileName(resultPath)); }
                catch { report.Outcome = "not-passed"; Console.WriteLine("결과 저장 실패. 통과로 처리하지 않습니다."); }
                Console.WriteLine("실제 한글 입력기 조합·파일 선택 대화상자·서명·보안 검사는 별도 확인 항목입니다.");
            }
            return report.Outcome == "automated-checks-passed-ime-and-release-pending" ? 0 : 1;
        }

        private MainViewModel Model(TestInteraction interaction) => new MainViewModel(new SyntheticBattery(),
            new SettingsStore(temporary), new LocalLog(temporary), interaction);
        private MainWindow Window(MainViewModel vm)
        {
            var window = new MainWindow { DataContext = vm, Title = "추가 자동 검증 · 실제 충전 제어 없음" };
            vm.SelectedSection = 1;
            window.Closing += (sender, e) => {
                if (closingInternally) return;
                if (testingWindowClose) { app.MainWindow = window; if (!vm.TryPrepareToClose()) e.Cancel = true; }
                else { Program.StopRequested = true; e.Cancel = true; }
            };
            return window;
        }
        private SavedBatteryObservation Fixture(string name)
        {
            var stream = typeof(Runner).Assembly.GetManifestResourceStream(name);
            string path = Path.Combine(temporary, name.EndsWith("A") ? "synthetic-a.ativrecord" : "synthetic-b.ativrecord");
            using (stream) using (var output = new FileStream(path, FileMode.CreateNew)) stream.CopyTo(output);
            return ObservationBundle.ReadFile(path).Import(temporary);
        }
        private async Task Open(MainWindow window, TestInteraction interaction, SavedBatteryObservation record, bool comparison)
        {
            StopIfRequested(); interaction.NextRecord = record;
            await Click(window, comparison ? "OpenComparisonObservationButton" : "OpenSavedObservationButton");
        }
        private async Task Edit(MainWindow window, string name, string text)
        {
            var box = window.FindName(name) as TextBox;
            Require(box != null, "MEMO_CONTROL_MISSING");
            // This supplies committed text to WPF, not IME pre-edit/composition events.
            for (DependencyObject parent = box; parent != null; parent = LogicalTreeHelper.GetParent(parent))
                if (parent is Expander expander) expander.IsExpanded = true;
            await Idle();
            Require(!box.IsReadOnly, "MEMO_READONLY");
            box.SetCurrentValue(TextBox.TextProperty, text); await Idle();
            var editor = box.DataContext as ObservationNoteViewModel;
            Require(editor != null && editor.Text == ObservationNote.Normalize(text), "MEMO_BINDING_INVALID");
        }
        private async Task Click(MainWindow window, string name)
        {
            var button = window.FindName(name) as Button;
            Require(button != null, "BUTTON_MISSING"); await Invoke(window, button);
        }
        private async Task InvokeCommand(MainWindow window, ICommand command)
        {
            var button = Buttons(window).FirstOrDefault(b => ReferenceEquals(b.Command, command));
            Require(button != null, "BOUND_BUTTON_MISSING"); await Invoke(window, button);
        }
        private async Task CloseRecords(MainWindow window, MainViewModel vm) => await InvokeCommand(window, vm.CloseSavedObservationCommand);
        private async Task Invoke(MainWindow window, Button button)
        {
            StopIfRequested(); app.MainWindow = window;
            Require(button.IsEnabled && button.Command != null && button.Command.CanExecute(button.CommandParameter), "BUTTON_DISABLED");
            button.BringIntoView(); window.UpdateLayout();
            // Execute the actual bound command synchronously so a modal nested
            // dispatcher cannot let the next assertion run before its command returns.
            // This tests button-command wiring, not physical pointer hit-testing.
            button.Command.Execute(button.CommandParameter); await Idle();
        }
        private static System.Collections.Generic.IEnumerable<Button> Buttons(DependencyObject item)
        {
            if (item is Button b) yield return b;
            foreach (object child in LogicalTreeHelper.GetChildren(item))
                if (child is DependencyObject dependency)
                    foreach (var button in Buttons(dependency)) yield return button;
        }
        private Task Idle() => app.Dispatcher.InvokeAsync(() => { }, DispatcherPriority.ApplicationIdle).Task;
        private async Task Sample(Stopwatch clock)
        {
            var heartbeat = Stopwatch.StartNew(); await Idle(); heartbeat.Stop();
            using (var process = Process.GetCurrentProcess())
            {
                process.Refresh();
                report.Samples.Add(new MemorySample { ElapsedSeconds = clock.Elapsed.TotalSeconds, Cycles = report.CompletedCycles,
                    PrivateBytes = process.PrivateMemorySize64, WorkingSetBytes = process.WorkingSet64,
                    ManagedBytes = GC.GetTotalMemory(false), HandleCount = process.HandleCount,
                    DispatcherRoundTripMilliseconds = heartbeat.Elapsed.TotalMilliseconds });
            }
        }
        private void VerifyReleased(SavedBatteryObservation record)
        {
            using (File.Open(record.SourcePath, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { }
            string path = Path.Combine(temporary, "observation-notes", record.NoteKey + ".json");
            using (File.Open(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { }
            using (File.Open(path + ".lock", FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { }
            Require(!Directory.EnumerateFiles(Path.Combine(temporary, "observation-notes"), "*.tmp").Any(), "TEMP_FILE_RETAINED");
        }
        private void Checkpoint()
        {
            if (resultPath == null) throw new InvalidOperationException();
            report.UpdatedUtc = DateTime.UtcNow.ToString("O");
            string staging = resultPath + ".tmp";
            LocalPathPolicy.EnsureNoReparsePoints(resultPath); LocalPathPolicy.EnsureNoReparsePoints(staging);
            using (var file = new FileStream(staging, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { new DataContractJsonSerializer(typeof(RunReport)).WriteObject(file, report); file.Flush(true); }
            File.Replace(staging, resultPath, null);
        }
        private static void StopIfRequested() { if (Program.StopRequested) throw new Failure("STOP_REQUESTED"); }
        private static void Require(bool condition, string code) { if (!condition) throw new Failure(code); }
    }
}
