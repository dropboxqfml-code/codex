using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Services;
using ATIVBatteryGuard.ViewModels;

internal static partial class Program
{
    private static void RegisterFinalUsageValidationTests()
    {
        Add("two main windows preserve conflicting A and B drafts through close cancel export and explicit reload", () =>
        {
            using (var f = new Fixture())
            {
                var notes = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, notes);
                var a = NoteRecord(Path.Combine(f.DirectoryPath, "a.txt"));
                var b = NoteRecord(Path.Combine(f.DirectoryPath, "b.txt"));
                using (var first = f.ViewModel()) using (var second = f.ViewModel())
                {
                    f.Interaction.ObservationOpener = () => a;
                    first.OpenSavedObservationCommand.Execute(null); second.OpenSavedObservationCommand.Execute(null);
                    f.Interaction.ObservationOpener = () => b; second.OpenComparisonObservationCommand.Execute(null);
                    first.SavedObservationNote.Text = "첫 창 저장\n한글";
                    second.SavedObservationNote.Text = "둘째 창의 보관할 초안";
                    second.ComparisonObservationNote.Text = "비교 B 초안";
                    first.SavedObservationNote.SaveCommand.Execute(null);
                    f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Save;
                    Check(!second.TryPrepareToClose(), "stale close-save allowed app exit");
                    Check(second.SavedObservationNote.Status.Contains("다른 창"), "save conflict not surfaced");
                    Check(second.SavedObservationVisible && second.ComparisonObservationVisible, "conflict closed graphs");
                    Equal("둘째 창의 보관할 초안", second.SavedObservationNote.Text);
                    Equal("비교 B 초안", second.ComparisonObservationNote.Text);
                    Equal("첫 창 저장\n한글", notes.Load(a.NoteKey).Text);
                    Equal("", notes.Load(b.NoteKey).Text);
                    string backup = Path.Combine(f.DirectoryPath, "conflict-draft.ativrecord");
                    f.Interaction.BundleExporter = (record, text) => { ObservationBundle.Create(record, text).Export(backup); return backup; };
                    second.ExportObservationBundleCommand.Execute(null);
                    Equal("둘째 창의 보관할 초안", ObservationBundle.ReadFile(backup).NoteText);
                    Check(second.SavedObservationNote.HasChanges, "backup marked conflicting local draft saved");
                    f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Cancel;
                    second.SavedObservationNote.ReloadCommand.Execute(null);
                    second.CloseSavedObservationCommand.Execute(null);
                    Equal("둘째 창의 보관할 초안", second.SavedObservationNote.Text);
                    Check(second.ComparisonObservationVisible, "cancel removed comparison draft");
                    f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Discard;
                    second.SavedObservationNote.ReloadCommand.Execute(null);
                    Equal("첫 창 저장\n한글", second.SavedObservationNote.Text);
                    Equal("비교 B 초안", second.ComparisonObservationNote.Text);
                    second.SavedObservationNote.Text = "합친 최종 메모";
                    f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Save;
                    Check(second.TryPrepareToClose(), "explicitly resolved close blocked");
                    Equal("합친 최종 메모", notes.Load(a.NoteKey).Text);
                    Equal("비교 B 초안", notes.Load(b.NoteKey).Text);
                    first.SavedObservationNote.Text = "이전 창의 뒤늦은 수정";
                    Check(!first.TryPrepareToClose(), "reverse stale save overwrote latest value");
                    Equal("합친 최종 메모", notes.Load(a.NoteKey).Text);
                    Equal("이전 창의 뒤늦은 수정", first.SavedObservationNote.Text);
                }
            }
        });

        Add("locked note file prevents close-save without losing either draft and succeeds after lease release", () =>
        {
            using (var f = new Fixture())
            {
                var notes = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, notes);
                var a = NoteRecord(Path.Combine(f.DirectoryPath, "a.txt"));
                var b = NoteRecord(Path.Combine(f.DirectoryPath, "b.txt"));
                Check(notes.Save(a.NoteKey, "기존 메모", "missing").Available, "initial save failed");
                using (var vm = f.ViewModel())
                {
                    f.Interaction.ObservationOpener = () => a; vm.OpenSavedObservationCommand.Execute(null);
                    f.Interaction.ObservationOpener = () => b; vm.OpenComparisonObservationCommand.Execute(null);
                    vm.SavedObservationNote.Text = "A 새 초안"; vm.ComparisonObservationNote.Text = "B 새 초안";
                    f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Save;
                    string lockPath = Path.Combine(f.DirectoryPath, "observation-notes", a.NoteKey + ".json.lock");
                    using (var lease = new FileStream(lockPath, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                    {
                        Check(!vm.TryPrepareToClose(), "locked note close allowed");
                        vm.CloseSavedObservationCommand.Execute(null);
                        Check(vm.SavedObservationVisible && vm.ComparisonObservationVisible, "failed save removed graph");
                        Equal("A 새 초안", vm.SavedObservationNote.Text); Equal("B 새 초안", vm.ComparisonObservationNote.Text);
                        Equal("기존 메모", notes.Load(a.NoteKey).Text); Equal("", notes.Load(b.NoteKey).Text);
                        Check(!Directory.EnumerateFiles(Path.Combine(f.DirectoryPath, "observation-notes"), "*.tmp").Any(), "failed save left temp files");
                    }
                    Check(vm.TryPrepareToClose(), "retry after release failed");
                    Equal("A 새 초안", notes.Load(a.NoteKey).Text); Equal("B 새 초안", notes.Load(b.NoteKey).Text);
                }
            }
        });

        Add("250 A B editor lifecycles release obsolete editor objects and storage leases while main window stays alive", () =>
        {
            using (var f = new Fixture())
            {
                var notes = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, notes);
                var a = NoteRecord(Path.Combine(f.DirectoryPath, "a.txt"));
                var b = NoteRecord(Path.Combine(f.DirectoryPath, "b.txt"));
                using (var vm = f.ViewModel())
                {
                    var references = new List<WeakReference>();
                    for (int i = 0; i < 250; i++) references.AddRange(CompleteEditorLifecycle(f, vm, a, b, i));
                    GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
                    Check(references.All(reference => !reference.IsAlive), "closed editors retained while main viewmodel lives");
                    Check(!vm.SavedObservationVisible && !vm.ComparisonObservationVisible, "graph remained open");
                    foreach (var record in new[] { a, b })
                    {
                        Equal("확인 249\n" + record.FileName, notes.Load(record.NoteKey).Text);
                        string path = Path.Combine(f.DirectoryPath, "observation-notes", record.NoteKey + ".json");
                        using (File.Open(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { }
                        using (File.Open(path + ".lock", FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { }
                    }
                    Check(!Directory.EnumerateFiles(Path.Combine(f.DirectoryPath, "observation-notes"), "*.tmp").Any(), "cycles leaked temporary files");
                    GC.KeepAlive(vm);
                }
            }
        });
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static WeakReference[] CompleteEditorLifecycle(Fixture f, MainViewModel vm,
        SavedBatteryObservation a, SavedBatteryObservation b, int iteration)
    {
        f.Interaction.ObservationOpener = () => a; vm.OpenSavedObservationCommand.Execute(null);
        f.Interaction.ObservationOpener = () => b; vm.OpenComparisonObservationCommand.Execute(null);
        var first = vm.SavedObservationNote; var second = vm.ComparisonObservationNote;
        first.Text = "확인 " + iteration + "\r\n" + a.FileName; first.SaveCommand.Execute(null);
        second.Text = "확인 " + iteration + "\r\n" + b.FileName; second.SaveCommand.Execute(null);
        Check(!first.HasChanges && !second.HasChanges, "cycle save failed");
        var references = new[] { new WeakReference(first), new WeakReference(second) };
        vm.CloseSavedObservationCommand.Execute(null);
        Check(vm.SavedObservationNote == null && vm.ComparisonObservationNote == null, "cycle retained editors");
        return references;
    }
}
