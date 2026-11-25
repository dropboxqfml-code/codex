using System;
using System.IO;
using System.Linq;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Services;
using ATIVBatteryGuard.ViewModels;

internal static partial class Program
{
    private static void RegisterObservationNoteViewModelTests()
    {
        Add("record note editing is explicit and persists into a reopened record and recent list preview", () =>
        {
            using (var f = new Fixture())
            {
                string path = Path.Combine(f.DirectoryPath, "record.txt");
                File.WriteAllText(path, SavedObservationText());
                var record = NoteRecord(path); var notes = new ObservationNoteStore(f.DirectoryPath);
                var history = new RecentObservationStore(f.DirectoryPath); history.Record(path, record);
                ConfigureNotes(f, notes);
                f.Interaction.RecentReader = () => history.Load().Select(row => row.WithNote(notes.Load(row.NoteKey))).ToList().AsReadOnly();
                f.Interaction.ObservationOpener = () => record;
                using (var vm = f.ViewModel())
                {
                    vm.OpenSavedObservationCommand.Execute(null);
                    vm.SavedObservationNote.Text = "보호 켜기 후 관찰\r\n메모";
                    Check(vm.SavedObservationNote.HasChanges && vm.SavedObservationNote.SaveCommand.CanExecute(null), "draft not editable");
                    Equal(0, f.Interaction.NoteSaves);
                    vm.SavedObservationNote.SaveCommand.Execute(null);
                    Check(!vm.SavedObservationNote.HasChanges && vm.SavedObservationNote.Preview.Contains("보호 켜기"), "save feedback missing");
                    Check(vm.RecentObservations[0].NotePreview.Contains("보호 켜기"), "recent preview not refreshed");
                    Equal(1, f.Interaction.NoteSaves);
                }
                using (var reopened = f.ViewModel())
                {
                    reopened.OpenSavedObservationCommand.Execute(null);
                    Equal("보호 켜기 후 관찰\n메모", reopened.SavedObservationNote.Text);
                }
            }
        });

        Add("A and B record notes remain independent without changing live observation or execution counters", () =>
        {
            using (var f = new Fixture())
            {
                var notes = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, notes);
                var a = NoteRecord(Path.Combine(f.DirectoryPath, "a.txt")); var b = NoteRecord(Path.Combine(f.DirectoryPath, "b.txt"));
                var battery = new PresentationGraphBattery(); var service = new ManualVmService(); var clock = new ManualUsabilityClock();
                using (var vm = PresentationGraphVm(f, battery, service, clock))
                {
                    vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); var live = vm.ObservationGraph;
                    f.Interaction.ObservationOpener = () => a; vm.OpenSavedObservationCommand.Execute(null);
                    f.Interaction.ObservationOpener = () => b; vm.OpenComparisonObservationCommand.Execute(null);
                    int reads = battery.Calls, times = clock.Calls, ops = service.Operations.Count;
                    vm.SavedObservationNote.Text = "A memo"; vm.ComparisonObservationNote.Text = "B memo";
                    vm.SavedObservationNote.SaveCommand.Execute(null); vm.ComparisonObservationNote.SaveCommand.Execute(null);
                    Equal("A memo", notes.Load(a.NoteKey).Text); Equal("B memo", notes.Load(b.NoteKey).Text);
                    Check(ReferenceEquals(live, vm.ObservationGraph) && vm.ObservationActive, "notes changed current capture");
                    Equal(reads, battery.Calls); Equal(times, clock.Calls); Equal(ops, service.Operations.Count);
                    Equal(0, f.Interaction.ObservationSaves);
                }
            }
        });

        Add("the same record shares its memo across A and B and closing B keeps the remaining draft", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                var store = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, store);
                var record = NoteRecord(Path.Combine(f.DirectoryPath, "same.txt"));
                f.Interaction.ObservationOpener = () => record;
                vm.OpenSavedObservationCommand.Execute(null); vm.OpenComparisonObservationCommand.Execute(null);
                Check(ReferenceEquals(vm.SavedObservationNote, vm.ComparisonObservationNote), "same record created competing drafts");
                vm.SavedObservationNote.Text = "shared";
                Equal("shared", vm.ComparisonObservationNote.Text);
                vm.CloseComparisonObservationCommand.Execute(null);
                Equal(0, f.Interaction.NoteConfirmations); Check(vm.SavedObservationNote.HasChanges, "closing B discarded shared draft");
                vm.OpenComparisonObservationCommand.Execute(null);
                f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Save;
                vm.CloseSavedObservationCommand.Execute(null);
                Equal(1, f.Interaction.NoteConfirmations); Equal(1, f.Interaction.NoteSaves);
                Check(!vm.SavedObservationVisible && !vm.ComparisonObservationVisible, "saved pair did not close");
                Equal("shared", store.Load(record.NoteKey).Text);
            }
        });

        Add("memo cancel blocks record replacement and failed save preserves the draft until successful retry", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                var store = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, store);
                var first = NoteRecord(Path.Combine(f.DirectoryPath, "first.txt"));
                var next = NoteRecord(Path.Combine(f.DirectoryPath, "next.txt"));
                f.Interaction.ObservationOpener = () => first; vm.OpenSavedObservationCommand.Execute(null);
                var editor = vm.SavedObservationNote; editor.Text = "unsaved";
                f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Cancel;
                f.Interaction.ObservationOpener = () => next; vm.OpenSavedObservationCommand.Execute(null);
                Check(ReferenceEquals(editor, vm.SavedObservationNote), "cancel replaced memo owner");
                Equal("first.txt", vm.SavedObservationName); Equal("unsaved", editor.Text);
                f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Save;
                f.Interaction.NoteSaver = (record, text, revision) => { throw new IOException("PRIVATE-SAVE"); };
                vm.CloseSavedObservationCommand.Execute(null);
                Check(vm.SavedObservationVisible && editor.HasChanges && !editor.Status.Contains("PRIVATE"), "save failure lost draft");
                Check(vm.SavedObservationOpenStatus.Contains("메모") && vm.SavedObservationOpenStatus.Contains("중단"),
                    "blocked close lacked visible parent feedback");
                ConfigureNotes(f, store); vm.CloseSavedObservationCommand.Execute(null);
                Check(!vm.SavedObservationVisible, "successful retry did not close");
                Equal("unsaved", store.Load(first.NoteKey).Text);
            }
        });

        Add("reopening the identical record keeps its unsaved memo without a replacement prompt", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                var store = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, store);
                string path = Path.Combine(f.DirectoryPath, "same.txt");
                f.Interaction.ObservationOpener = () => NoteRecord(path);
                vm.OpenSavedObservationCommand.Execute(null); var editor = vm.SavedObservationNote;
                editor.Text = "keep this draft";
                vm.OpenSavedObservationCommand.Execute(null);
                Check(ReferenceEquals(editor, vm.SavedObservationNote), "same identity replaced draft");
                Equal("keep this draft", editor.Text); Equal(0, f.Interaction.NoteConfirmations);
                editor.SaveCommand.Execute(null);
                var key = NoteRecord(path).NoteKey;
                Check(store.Save(key, "external latest", store.Load(key).Revision).Available, "external save failed");
                vm.OpenSavedObservationCommand.Execute(null);
                Equal("external latest", editor.Text);
                Equal(0, f.Interaction.NoteConfirmations);
            }
        });

        Add("note close decisions preserve earlier drafts if a later note or current observation cancels close", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                var store = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, store);
                var a = NoteRecord(Path.Combine(f.DirectoryPath, "a.txt")); var b = NoteRecord(Path.Combine(f.DirectoryPath, "b.txt"));
                f.Interaction.ObservationOpener = () => a; vm.OpenSavedObservationCommand.Execute(null);
                f.Interaction.ObservationOpener = () => b; vm.OpenComparisonObservationCommand.Execute(null);
                vm.SavedObservationNote.Text = "A draft"; vm.ComparisonObservationNote.Text = "B draft";
                f.Interaction.NoteConfirmer = (name, action) => name == "a.txt" ? ObservationLossChoice.Discard : ObservationLossChoice.Cancel;
                Check(!vm.TryPrepareToClose(), "later cancel ignored");
                Equal("A draft", vm.SavedObservationNote.Text); Equal("B draft", vm.ComparisonObservationNote.Text);
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery();
                f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Save;
                f.Interaction.ObservationConfirmer = action => ObservationLossChoice.Cancel;
                Check(!vm.TryPrepareToClose() && vm.ObservationActive, "current capture cancel ignored");
                Equal("A draft", store.Load(a.NoteKey).Text); Equal("B draft", store.Load(b.NoteKey).Text);
                Check(!vm.SavedObservationNote.HasChanges && !vm.ComparisonObservationNote.HasChanges, "chosen saves not committed");
                f.Interaction.ObservationConfirmer = action => ObservationLossChoice.Save;
                Check(vm.TryPrepareToClose(), "fully saved close blocked");
            }
        });

        Add("note editors retain conflict drafts and reload the latest value only after the user permits replacement", () =>
        {
            using (var f = new Fixture())
            {
                var store = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, store);
                var record = NoteRecord(Path.Combine(f.DirectoryPath, "record.txt"));
                using (var a = new ObservationNoteViewModel(f.Interaction, record))
                using (var b = new ObservationNoteViewModel(f.Interaction, record))
                {
                    a.Text = "A"; b.Text = "B";
                    a.SaveCommand.Execute(null); b.SaveCommand.Execute(null);
                    Equal("B", b.Text); Check(b.HasChanges && b.Status.Contains("다른 창"), "conflict overwrote draft");
                    f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Cancel;
                    b.ReloadCommand.Execute(null); Equal("B", b.Text);
                    f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Discard;
                    b.ReloadCommand.Execute(null); Equal("A", b.Text); Check(!b.HasChanges, "reload kept old baseline");
                    b.Text = "merged"; b.SaveCommand.Execute(null); Equal("merged", store.Load(record.NoteKey).Text);
                    b.Text = new string('x', 1001);
                    Check(!b.SaveCommand.CanExecute(null), "oversized draft can save");
                    f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Save;
                    Check(!b.TryPrepareToClose("close") && b.Text.Length == 1001, "invalid draft lost");
                }
            }
        });

        Add("entering note confirmation does not replace an uncommitted displayed Hangul syllable", () =>
        {
            using (var f = new Fixture())
            {
                var store = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, store);
                var record = NoteRecord(Path.Combine(f.DirectoryPath, "pending.txt"));
                using (var editor = new ObservationNoteViewModel(f.Interaction, record))
                {
                    editor.Text = "종료 취소 확";
                    string displayed = "종료 취소 확인", observedAtPrompt = null;
                    // Model WPF's target refresh while its source update is deferred by IME.
                    editor.PropertyChanged += (sender, args) => { if (args.PropertyName == "Text") displayed = editor.Text; };
                    f.Interaction.NoteConfirmer = (name, action) => { observedAtPrompt = displayed; return ObservationLossChoice.Cancel; };
                    Check(!editor.TryPrepareToClose("앱 종료"), "cancel ignored");
                    Equal("종료 취소 확인", observedAtPrompt);
                }
            }
        });

        Add("captured pending Hangul survives close cancellation and reentry without changing the saved note", () =>
        {
            using (var f = new Fixture())
            {
                var store = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, store);
                var record = NoteRecord(Path.Combine(f.DirectoryPath, "pending.txt"));
                store.Save(record.NoteKey, "한글 입력 확인", "missing");
                using (var editor = new ObservationNoteViewModel(f.Interaction, record))
                {
                    editor.Text = "종료 취소 확";
                    string displayed = "종료 취소 확인";
                    editor.PropertyChanged += (sender, args) => { if (args.PropertyName == "Text") displayed = editor.Text; };
                    Check(editor.TryCapturePendingText(displayed), "pending text capture failed");
                    f.Interaction.NoteConfirmer = (name, action) => {
                        Check(!editor.TryCapturePendingText("reentrant") && !editor.TryPrepareToClose("reentry"), "confirmation reentry allowed");
                        editor.SaveCommand.Execute(null); return ObservationLossChoice.Cancel;
                    };
                    Check(!editor.TryPrepareToClose("앱 종료"), "cancel ignored");
                    Equal("종료 취소 확인", displayed); Equal(displayed, editor.Text);
                    Check(editor.HasChanges, "draft marked saved"); Equal("한글 입력 확인", store.Load(record.NoteKey).Text);
                    Equal(0, f.Interaction.NoteSaves);
                }
            }
        });
        Add("pending input capture respects save discard readonly and disposed boundaries", () =>
        {
            using (var f = new Fixture())
            {
                var store = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, store);
                var record = NoteRecord(Path.Combine(f.DirectoryPath, "pending.txt"));
                using (var editor = new ObservationNoteViewModel(f.Interaction, record))
                {
                    Check(editor.TryCapturePendingText("한글\r\n확인"), "capture failed");
                    f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Save;
                    Check(editor.TryPrepareToClose("앱 종료"), "captured save failed"); Equal("한글\n확인", store.Load(record.NoteKey).Text);
                    Check(editor.TryCapturePendingText("버릴 초안"), "second capture failed");
                    f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Discard;
                    Check(editor.TryPrepareToClose("앱 종료"), "discard blocked"); Equal("한글\n확인", store.Load(record.NoteKey).Text);
                    editor.Dispose(); Check(!editor.TryCapturePendingText("late"), "disposed editor accepted text");
                }
                f.Interaction.NoteLoader = source => ObservationNote.Unavailable("unavailable");
                using (var locked = new ObservationNoteViewModel(f.Interaction, record))
                    Check(!locked.TryCapturePendingText("cannot edit"), "readonly baseline accepted input");
            }
        });

        Add("unavailable memo loads recover via reload and late memo loads cannot republish after disposal", () =>
        {
            using (var f = new Fixture())
            {
                var store = new ObservationNoteStore(f.DirectoryPath);
                var record = NoteRecord(Path.Combine(f.DirectoryPath, "record.txt"));
                f.Interaction.NoteLoader = source => ObservationNote.Unavailable("unavailable");
                using (var editor = new ObservationNoteViewModel(f.Interaction, record))
                {
                    Check(editor.IsReadOnly && !editor.SaveCommand.CanExecute(null), "unknown baseline editable");
                    ConfigureNotes(f, store); editor.ReloadCommand.Execute(null);
                    Check(!editor.IsReadOnly, "reload did not recover");
                }
                using (var vm = f.ViewModel())
                {
                    f.Interaction.ObservationOpener = () => record;
                    f.Interaction.NoteLoader = source => { vm.Dispose(); return ObservationNote.Empty; };
                    vm.OpenSavedObservationCommand.Execute(null);
                    Check(!vm.SavedObservationVisible && vm.SavedObservationNote == null, "late note load restored disposed data");
                }
            }
        });
    }
}
