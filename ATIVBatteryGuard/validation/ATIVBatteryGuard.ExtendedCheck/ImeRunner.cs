using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Threading;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Services;
using ATIVBatteryGuard.Validation;
using ATIVBatteryGuard.ViewModels;
using ATIVBatteryGuard.Views;

namespace ATIVBatteryGuard.ExtendedValidation
{
    internal sealed class ImeRunner
    {
        [DataContract]
        private sealed class Report
        {
            [DataMember] public int SchemaVersion = 1;
            [DataMember] public string ToolRevision = "extended-v4";
            [DataMember] public string ReleaseVersion = "0.3.0-rc.3";
            [DataMember] public string Mode = "guided-ime";
            [DataMember] public string SourceFingerprintSha256;
            [DataMember] public string StartedUtc = DateTime.UtcNow.ToString("O");
            [DataMember] public string CompletedUtc;
            [DataMember] public string Outcome = "running-not-passed";
            [DataMember] public string Phase = "initializing";
            [DataMember] public string ErrorCode;
            [DataMember] public ImeEvidence Evidence = new ImeEvidence();
            [DataMember] public ImeCloseDiagnostics CloseDiagnostics = new ImeCloseDiagnostics();
            [DataMember] public bool KnownSavedBaselinePrepared;
            [DataMember] public bool SaveRoundtripPerformedInThisRun;
            [DataMember] public bool FilesVerifiedBefore;
            [DataMember] public bool FilesVerifiedAfter;
            [DataMember] public bool CleanupSucceeded;
            [DataMember] public bool StopRequested;
            [DataMember] public int CancelDialogCount;
            [DataMember] public bool HardwareWritesPerformed = false;
            [DataMember] public bool BatteryOrOemQueriesPerformed = false;
            [DataMember] public bool DefenderScanExecuted = false;
            [DataMember] public bool AuthenticodeSigningPerformed = false;
            [DataMember] public bool FinalReleaseApproved = false;
        }
        private readonly Application app;
        private readonly string root;
        private readonly ValidationManifest manifest;
        private readonly bool closeOnly;
        private HwndSource windowSource;
        private readonly Report report = new Report();
        private readonly TaskCompletionSource<bool> finished = new TaskCompletionSource<bool>();
        private string temporary, reportPath;
        private MainViewModel vm;
        private MainWindow window;
        private TestInteraction interaction;
        private SavedBatteryObservation record;
        private TextBox box;
        private TextBlock instruction, status;
        private CheckBox attestation;
        private bool closingInternally, compositionActive, checking;
        public ImeRunner(Application app, string root, ValidationManifest manifest, bool closeOnly)
        {
            this.app = app; this.root = root; this.manifest = manifest; this.closeOnly = closeOnly;
            report.Mode = closeOnly ? "guided-ime-close" : "guided-ime";
        }

        public async Task<int> Run()
        {
            try
            {
                report.SourceFingerprintSha256 = manifest.SourceFingerprintSha256;
                report.FilesVerifiedBefore = true;
                string results = LocalPathPolicy.NormalizeDirectory(Path.Combine(root, "extended-results"));
                Directory.CreateDirectory(results);
                reportPath = LocalPathPolicy.NormalizeFile(Path.Combine(results, (closeOnly ? "ime-close-" : "ime-") + Guid.NewGuid().ToString("N") + ".json"));
                using (new FileStream(reportPath, FileMode.CreateNew, FileAccess.Write, FileShare.None)) { }
                Write();
                temporary = LocalPathPolicy.NormalizeDirectory(Path.Combine(Path.GetTempPath(), "ATIV-ime-" + Guid.NewGuid().ToString("N")));
                Directory.CreateDirectory(temporary);
                string sample = Path.Combine(temporary, "synthetic.ativrecord");
                using (var input = typeof(ImeRunner).Assembly.GetManifestResourceStream("Extended.SampleA"))
                using (var output = new FileStream(sample, FileMode.CreateNew)) input.CopyTo(output);
                record = ObservationBundle.ReadFile(sample).Import(temporary);
                var notes = new ObservationNoteStore(temporary);
                Require(notes.Save(record.NoteKey, closeOnly ? ImeEvidence.SavePhrase : "", notes.Load(record.NoteKey).Revision).Available, "IME_BASELINE_FAILED");
                report.KnownSavedBaselinePrepared = closeOnly;
                interaction = new TestInteraction(temporary) { NextRecord = record, NextChoice = ObservationLossChoice.Cancel };
                vm = new MainViewModel(new SyntheticBattery(), new SettingsStore(temporary), new LocalLog(temporary), interaction);
                vm.SelectedSection = 1;
                window = new MainWindow { DataContext = vm, Title = "한글 입력 확인 · 임시 예제 · 실제 충전 제어 없음" };
                app.MainWindow = window;
                AddGuidance();
                window.Closing += WindowClosing;
                window.SourceInitialized += (sender, e) => {
                    windowSource = HwndSource.FromHwnd(new WindowInteropHelper(window).Handle);
                    windowSource?.AddHook(ObserveCloseMessage);
                };
                window.Show();
                vm.OpenSavedObservationCommand.Execute(null);
                await Idle();
                box = window.FindName("ANoteText") as TextBox;
                Require(box != null, "IME_MEMO_CONTROL_MISSING"); ExpandMemo();
                TextCompositionManager.AddPreviewTextInputStartHandler(box, CompositionStart);
                TextCompositionManager.AddPreviewTextInputUpdateHandler(box, CompositionUpdate);
                TextCompositionManager.AddPreviewTextInputHandler(box, CompositionComplete);
                var save = window.FindName("SaveANoteButton") as Button;
                Require(save != null, "IME_SAVE_CONTROL_MISSING");
                save.PreviewMouseLeftButtonDown += (sender, e) => {
                    if (report.Phase != "save" || checking) return;
                    report.Evidence.SavePointerObserved = true;
                    report.Evidence.SaveCompositionActiveAtPointer = compositionActive;
                    report.Evidence.SaveExpectedTextVisibleBeforePointer = ObservationNote.Normalize(box.Text) == ImeEvidence.SavePhrase;
                };
                save.Click += (sender, e) => {
                    if (report.Phase == "save" && !checking)
                    { checking = true; app.Dispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle, new Action(CheckSave)); }
                };
                report.Phase = closeOnly ? "close" : "save";
                instruction.Text = "1. 메모에 ‘" + ImeEvidence.SavePhrase + "’을 직접 입력하고, 마지막 글자에 조합 표시가 남아 있을 때 아래 ‘메모 저장’을 클릭하세요.";
                status.Text = "실제 한글 입력기로 입력합니다. 붙여넣기나 자동 입력은 사용하지 않습니다.";
                if (closeOnly)
                {
                    instruction.Text = "메모에서 Ctrl+A로 기존 글자를 선택해 ‘" + ImeEvidence.ClosePhrase + "’을 직접 입력한 뒤, 마지막 글자 조합 중 창의 X를 누르세요. 확인창은 자동 취소합니다.";
                    status.Text = "저장·재열기 검사는 반복하지 않습니다. 미리 준비한 저장값은 취소 후 그대로인지 확인합니다.";
                }
                Write(); await Idle(); box.BringIntoView(); box.Focus();
                var duration = Stopwatch.StartNew();
                while (!finished.Task.IsCompleted && !Program.StopRequested && duration.Elapsed.TotalMinutes < 10)
                    await Task.Delay(200);
                report.StopRequested = Program.StopRequested || !finished.Task.IsCompleted;
                report.Evidence.UserConfirmedCompositionActions = attestation.IsChecked == true;
            }
            catch (Exception error)
            {
                report.ErrorCode = error is ImeFailure ? ((ImeFailure)error).Code : "IME_CHECK_FAILED";
            }
            finally
            {
                closingInternally = true;
                windowSource?.RemoveHook(ObserveCloseMessage);
                report.CancelDialogCount = interaction?.Confirmations ?? 0;
                try { vm?.Dispose(); window?.Close(); } catch { report.ErrorCode = report.ErrorCode ?? "IME_WINDOW_CLEANUP_FAILED"; }
                try
                {
                    if (temporary != null) { LocalPathPolicy.NormalizeDirectory(temporary); Directory.Delete(temporary, true); }
                    report.CleanupSucceeded = true;
                }
                catch { report.CleanupSucceeded = false; }
                try { ValidationEvidence.VerifyFiles(root, manifest); report.FilesVerifiedAfter = true; }
                catch { report.FilesVerifiedAfter = false; }
                report.Outcome = closeOnly
                    ? report.Evidence.CloseOnlyOutcome(report.StopRequested, report.FilesVerifiedBefore, report.FilesVerifiedAfter, report.CleanupSucceeded, report.ErrorCode)
                    : report.Evidence.Outcome(report.StopRequested, report.FilesVerifiedBefore, report.FilesVerifiedAfter, report.CleanupSucceeded, report.ErrorCode);
                report.CompletedUtc = DateTime.UtcNow.ToString("O");
                try { Write(); Console.WriteLine("한글 입력 결과: " + report.Outcome + "\nextended-results: " + Path.GetFileName(reportPath)); }
                catch { report.Outcome = "not-passed"; Console.WriteLine("한글 입력 결과를 저장하지 못했습니다. 통과로 처리하지 않습니다."); }
            }
            return report.Outcome == "user-assisted-ime-checks-passed-release-pending"
                || report.Outcome == "user-assisted-ime-close-checks-passed-release-pending" ? 0 : 1;
        }
        private void AddGuidance()
        {
            var original = window.Content as UIElement;
            window.Content = null;
            var layout = new DockPanel();
            var guidance = new StackPanel { Margin = new Thickness(12) };
            instruction = new TextBlock { TextWrapping = TextWrapping.Wrap, FontWeight = FontWeights.SemiBold };
            status = new TextBlock { TextWrapping = TextWrapping.Wrap };
            attestation = new CheckBox { Content = closeOnly ? "직접 입력하고 조합 표시가 있을 때 닫기를 눌렀습니다." : "직접 입력하고 조합 표시가 있을 때 저장과 닫기를 눌렀습니다.", IsChecked = false };
            var finish = new Button { Content = "결과 저장 후 종료", HorizontalAlignment = HorizontalAlignment.Left };
            finish.Click += (sender, e) => finished.TrySetResult(true);
            guidance.Children.Add(instruction); guidance.Children.Add(status); guidance.Children.Add(attestation); guidance.Children.Add(finish);
            DockPanel.SetDock(guidance, Dock.Top); layout.Children.Add(guidance); layout.Children.Add(original); window.Content = layout;
        }
        private void CheckSave()
        {
            try
            {
                Require(interaction.ReadNote(record).Text == ImeEvidence.SavePhrase && !vm.SavedObservationNote.HasChanges, "IME_SAVE_TEXT_MISMATCH");
                vm.CloseSavedObservationCommand.Execute(null); vm.OpenSavedObservationCommand.Execute(null);
                Require(vm.SavedObservationNote.Text == ImeEvidence.SavePhrase, "IME_REOPEN_TEXT_MISMATCH");
                report.Evidence.SaveRoundtripPassed = true;
                report.SaveRoundtripPerformedInThisRun = true;
                report.Phase = "close"; compositionActive = false;
                instruction.Text = "2. 메모에서 Ctrl+A로 기존 글자를 선택해 ‘" + ImeEvidence.ClosePhrase + "’으로 바꾼 뒤, 마지막 글자 조합 중 창의 X를 누르세요. 저장 확인은 도구가 자동 취소합니다.";
                status.Text = "저장·다시 열기 확인 완료. 두 번째 문구는 저장하지 않습니다.";
                ExpandMemo(); box.BringIntoView(); box.Focus(); Write();
            }
            catch (Exception error) { Fail(error); }
            finally { checking = false; }
        }
        private void WindowClosing(object sender, System.ComponentModel.CancelEventArgs e)
        {
            if (closingInternally) return;
            report.CloseDiagnostics.ProductCancelledBeforeHostGuard = e.Cancel;
            e.Cancel = true; // Keep this temporary test window safe even if the tested guard fails.
            if (report.Phase != "close" || checking)
            { Program.StopRequested = true; finished.TrySetResult(false); return; }
            checking = true;
            try
            {
                report.Evidence.CloseCompositionActiveAtRequest = report.CloseDiagnostics.BeforeProductClose?.CompositionActive ?? compositionActive;
                report.CloseDiagnostics.BeforeConfirmation = CaptureState(true);
                Require(!report.CloseDiagnostics.ProductCancelledBeforeHostGuard, "IME_CLOSE_PENDING_INPUT_CAPTURE_FAILED");
                bool blocked = !vm.TryPrepareToClose();
                report.CloseDiagnostics.GuardBlockedClose = blocked;
                Require(blocked && !interaction.DialogAutomationFailed && interaction.Confirmations == 1, "IME_CANCEL_DECISION_INVALID");
                app.Dispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle, new Action(() => {
                    try
                    {
                        report.CloseDiagnostics.AfterCancellation = CaptureState(true);
                        string failure = report.CloseDiagnostics.AfterCancellation.FailureCode();
                        Require(failure == null, failure);
                        report.Evidence.CloseCancelPassed = true; report.Phase = "ready";
                        instruction.Text = "저장·취소 확인 완료. 직접 조합 중 동작을 확인했다면 위 체크 항목을 선택하고 결과를 저장하세요.";
                        status.Text = "입력기 이벤트 증거가 부족하면 통과 대신 미확인으로 기록합니다."; Write();
                    }
                    catch (Exception error) { Fail(error); }
                    finally { checking = false; }
                }));
            }
            catch (Exception error) { checking = false; Fail(error); }
        }
        private IntPtr ObserveCloseMessage(IntPtr hwnd, int message, IntPtr wparam, IntPtr lparam, ref bool handled)
        {
            if (!closingInternally && report.Phase == "close" && !report.CloseDiagnostics.NativeCloseRequestObserved
                && (message == 0x0010 || message == 0x0112 && (wparam.ToInt64() & 0xFFF0) == 0xF060))
            {
                // Observe only this window before MainWindow.OnClosing transfers the
                // focused pending text. Never consume messages or record characters.
                try
                {
                    report.CloseDiagnostics.BeforeProductClose = CaptureState(false);
                    report.CloseDiagnostics.NativeCloseRequestObserved = true;
                }
                catch { /* Missing observation is kept distinct from a successful snapshot. */ }
            }
            return IntPtr.Zero;
        }
        private ImeCloseState CaptureState(bool readStored)
        {
            string displayed = ObservationNote.Normalize(box.Text);
            string model = vm.SavedObservationNote.Text;
            var stored = readStored ? interaction.ReadNote(record) : null;
            return new ImeCloseState {
                WindowVisible = window.IsVisible, DraftModified = vm.SavedObservationNote.HasChanges,
                ModelMatchesExpected = model == ImeEvidence.ClosePhrase,
                DisplayMatchesExpected = displayed == ImeEvidence.ClosePhrase,
                DisplayMatchesModel = displayed == model, CompositionActive = compositionActive,
                StoredAvailable = stored?.Available,
                StoredMatchesBaseline = readStored ? (bool?)(stored.Available && stored.Text == ImeEvidence.SavePhrase) : null };
        }
        private void CompositionStart(object sender, TextCompositionEventArgs e)
        {
            compositionActive = true;
            if (report.Phase == "save") report.Evidence.SaveCompositionStarts++;
            if (report.Phase == "close") report.Evidence.CloseCompositionStarts++;
            ObserveInputMethod();
        }
        private void CompositionUpdate(object sender, TextCompositionEventArgs e)
        {
            compositionActive = true;
            if (report.Phase == "save") report.Evidence.SaveCompositionUpdates++;
            if (report.Phase == "close") report.Evidence.CloseCompositionUpdates++;
            ObserveInputMethod();
        }
        private void CompositionComplete(object sender, TextCompositionEventArgs e) { ObserveInputMethod(); compositionActive = false; }
        private void ObserveInputMethod()
        {
            try
            {
                bool koreanIme = InputLanguageManager.Current.CurrentInputLanguage.TwoLetterISOLanguageName == "ko"
                    && InputMethod.Current.ImeState == InputMethodState.On;
                if (report.Phase == "save") report.Evidence.SaveKoreanImeObserved |= koreanIme;
                if (report.Phase == "close") report.Evidence.CloseKoreanImeObserved |= koreanIme;
            }
            catch { /* Unknown input method state remains unconfirmed. */ }
        }
        private void ExpandMemo()
        {
            for (DependencyObject p = box; p != null; p = LogicalTreeHelper.GetParent(p))
                if (p is Expander expander) expander.IsExpanded = true;
        }
        private Task Idle() => app.Dispatcher.InvokeAsync(() => { }, DispatcherPriority.ApplicationIdle).Task;
        private void Fail(Exception error)
        {
            report.ErrorCode = error is ImeFailure ? ((ImeFailure)error).Code : "IME_CHECK_FAILED";
            report.Phase = "failed"; instruction.Text = "확인을 완료하지 못했습니다. 결과를 저장해 전달하세요.";
            status.Text = report.ErrorCode; try { Write(); } catch { }
        }
        private void Write()
        {
            if (reportPath == null) throw new InvalidOperationException();
            string staging = reportPath + ".tmp";
            LocalPathPolicy.EnsureNoReparsePoints(reportPath); LocalPathPolicy.EnsureNoReparsePoints(staging);
            using (var output = new FileStream(staging, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { new DataContractJsonSerializer(typeof(Report)).WriteObject(output, report); output.Flush(true); }
            File.Replace(staging, reportPath, null);
        }
        private sealed class ImeFailure : Exception { public readonly string Code; public ImeFailure(string code) { Code = code; } }
        private static void Require(bool condition, string code) { if (!condition) throw new ImeFailure(code); }
    }
}
