using System;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Text;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Services;

internal static partial class Program
{
    private static void RegisterQualityAndUsabilityTests()
    {
        Add("note JSON rejects trailing documents duplicate fields depth and invalid UTF8 preserving original bytes", () =>
        {
            using (var f = new Fixture())
            {
                string key = NoteRecord(Path.Combine(f.DirectoryPath, "a.txt")).NoteKey;
                var notes = new ObservationNoteStore(f.DirectoryPath); notes.Save(key, "original", "missing");
                string path = Path.Combine(f.DirectoryPath, "observation-notes", key + ".json");
                string valid = File.ReadAllText(path);
                foreach (byte[] data in new[] { Encoding.UTF8.GetBytes(valid + "{}"), Encoding.UTF8.GetBytes(valid + " PRIVATE"),
                    Encoding.UTF8.GetBytes(valid.Insert(1, "\"Version\":1,")), new byte[] { 0xff, 0xfe },
                    Encoding.UTF8.GetBytes("{\"x\":" + new string('[', 20) + "0" + new string(']', 20) + "}") })
                {
                    File.WriteAllBytes(path, data);
                    var loaded = notes.Load(key); Check(!loaded.Available && !loaded.Notice.Contains("PRIVATE"), "invalid note accepted or echoed");
                    Check(!notes.Save(key, "overwrite", "missing").Available, "invalid note overwritten");
                    Check(data.SequenceEqual(File.ReadAllBytes(path)), "invalid note bytes changed");
                }
            }
        });

        Add("recent JSON rejects trailing documents and invalid UTF8 without replacing the index", () =>
        {
            using (var f = new Fixture())
            {
                string path = Path.Combine(f.DirectoryPath, "a.txt"); var record = NoteRecord(path);
                var recent = new RecentObservationStore(f.DirectoryPath); recent.Record(path, record);
                string valid = File.ReadAllText(recent.FilePath);
                foreach (byte[] data in new[] { Encoding.UTF8.GetBytes(valid + "{}"), Encoding.UTF8.GetBytes(valid + " PRIVATE"), new byte[] { 0xff } })
                {
                    File.WriteAllBytes(recent.FilePath, data);
                    RejectLocalStorage(() => recent.Load()); RejectLocalStorage(() => recent.Record(path, record));
                    Check(data.SequenceEqual(File.ReadAllBytes(recent.FilePath)), "invalid index replaced");
                }
            }
        });

        Add("strict local JSON supports legacy BOM whitespace escaped braces Unicode and existing schema data", () =>
        {
            using (var f = new Fixture())
            {
                string path = Path.Combine(f.DirectoryPath, "a.txt"); var record = NoteRecord(path);
                var recent = new RecentObservationStore(f.DirectoryPath); recent.Record(path, record);
                File.WriteAllText(recent.FilePath, "\uFEFF" + File.ReadAllText(recent.FilePath) + " \r\n");
                Equal(1, recent.Load().Count);
                var notes = new ObservationNoteStore(f.DirectoryPath); notes.Save(record.NoteKey, "한글 🙂 { } \" \\ 내용", "missing");
                string notePath = Path.Combine(f.DirectoryPath, "observation-notes", record.NoteKey + ".json");
                File.WriteAllText(notePath, "\uFEFF" + File.ReadAllText(notePath) + "\t");
                Equal("한글 🙂 { } \" \\ 내용", notes.Load(record.NoteKey).Text);
                Check(f.Store.Save(new AppSettings()).Success, "settings fixture failed");
                File.WriteAllText(f.Store.FilePath, "\uFEFF" + File.ReadAllText(f.Store.FilePath) + "\r\n");
                var loaded = new SettingsStore(f.DirectoryPath).Load(); Check(loaded.CanSave && loaded.Warning.Length == 0, "legacy settings rejected");
                var bundle = ObservationBundle.Create(record, "memo").ToBytes();
                Equal("memo", ReadBundle(new byte[] { 0xef, 0xbb, 0xbf }.Concat(bundle).ToArray()).NoteText);
            }
        });

        Add("settings trailing document and invalid UTF8 are preserved as corrupt copies before defaults can save", () =>
        {
            foreach (byte[] data in new[] { Encoding.UTF8.GetBytes("{\"schemaVersion\":1,\"desiredMode\":\"Normal100\",\"restoreOnBoot\":false,\"mockModeEnabled\":false,\"lastUiState\":\"Normal\"}{}"), new byte[] { 0xff } })
            using (var f = new Fixture())
            {
                File.WriteAllBytes(f.Store.FilePath, data);
                var store = new SettingsStore(f.DirectoryPath); var loaded = store.Load();
                Check(loaded.CanSave && loaded.Warning.Length > 0, "corruption unreported");
                string copy = Directory.GetFiles(f.DirectoryPath, "settings.corrupt-*.json").Single();
                Check(data.SequenceEqual(File.ReadAllBytes(copy)), "corrupt bytes not preserved");
                Check(store.Save(loaded.Settings).Success, "recovery save blocked");
                Check(data.SequenceEqual(File.ReadAllBytes(copy)), "recovery overwrote corrupt copy");
            }
        });

        Add("settings two instances cannot overwrite each others valid changes and reload enables an explicit retry", () =>
        {
            using (var f = new Fixture())
            {
                var a = new SettingsStore(f.DirectoryPath); var b = new SettingsStore(f.DirectoryPath); a.Load(); b.Load();
                Check(a.Save(new AppSettings { DesiredMode = ChargeMode.Protection80 }).Success, "A save failed");
                byte[] latest = File.ReadAllBytes(a.FilePath);
                var result = b.Save(new AppSettings()); Check(!result.Success && result.Message.Contains("다른 창"), "stale valid save accepted");
                Check(latest.SequenceEqual(File.ReadAllBytes(a.FilePath)), "stale writer changed bytes");
                Check(!b.Save(new AppSettings()).Success, "stale store silently retried");
                Equal(ChargeMode.Protection80, b.Load().Settings.DesiredMode);
                Check(b.Save(new AppSettings()).Success, "explicit reload failed to recover");
                Check(!a.Save(new AppSettings { DesiredMode = ChargeMode.Protection80 }).Success, "reverse stale write accepted");
                Check(latest.SequenceEqual(File.ReadAllBytes(a.FilePath + ".bak")), "backup lost preceding state");
            }
        });

        Add("settings lease contention preserves settings and backup and permits retry when released", () =>
        {
            using (var f = new Fixture())
            {
                Check(f.Store.Save(new AppSettings()).Success, "first save failed");
                byte[] current = File.ReadAllBytes(f.Store.FilePath);
                using (var held = new FileStream(f.Store.FilePath + ".lock", FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                {
                    Check(!f.Store.Save(new AppSettings { DesiredMode = ChargeMode.Protection80 }).Success, "write ignored lease");
                    Check(!new SettingsStore(f.DirectoryPath).Load().CanSave, "read/recovery ignored lease");
                    Check(current.SequenceEqual(File.ReadAllBytes(f.Store.FilePath)), "busy write changed settings");
                    Check(!File.Exists(f.Store.FilePath + ".bak"), "busy write changed backup");
                }
                Check(f.Store.Save(new AppSettings { DesiredMode = ChargeMode.Protection80 }).Success, "release did not recover");
                Check(!Directory.GetFiles(f.DirectoryPath, ".settings-*.tmp").Any(), "temporary settings retained");
            }
        });

        Add("busy or read-only settings loading retains the valid preference snapshot while save and recovery remain blocked", () =>
        {
            using (var f = new Fixture())
            {
                f.Store.Save(new AppSettings { DesiredMode = ChargeMode.Protection80 });
                byte[] original = File.ReadAllBytes(f.Store.FilePath);
                using (var held = new FileStream(f.Store.FilePath + ".lock", FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                {
                    var store = new SettingsStore(f.DirectoryPath); var loaded = store.Load();
                    Equal(ChargeMode.Protection80, loaded.Settings.DesiredMode);
                    Check(!loaded.CanSave && loaded.Warning.Contains("읽기 전용"), "read-only snapshot status unclear");
                    Check(!store.Save(new AppSettings()).Success, "fallback enabled writes");
                }
                Check(original.SequenceEqual(File.ReadAllBytes(f.Store.FilePath)), "read-only fallback changed data");
                Equal(0, Directory.GetFiles(f.DirectoryPath, "settings.corrupt-*.json").Length);
            }
        });

        Add("settings removal and external same-schema modifications cannot be silently recreated or overwritten", () =>
        {
            using (var f = new Fixture())
            {
                f.Store.Save(new AppSettings()); File.Delete(f.Store.FilePath);
                Check(!f.Store.Save(new AppSettings()).Success && !File.Exists(f.Store.FilePath), "deleted setting recreated from stale state");
                f.Store.Load(); f.Store.Save(new AppSettings());
                string changed = File.ReadAllText(f.Store.FilePath).Replace("Normal100", "Protection80");
                File.WriteAllText(f.Store.FilePath, changed);
                Check(!f.Store.Save(new AppSettings()).Success, "same-schema change overwritten"); Equal(changed, File.ReadAllText(f.Store.FilePath));
            }
        });

        Add("local file names reject streams device aliases reserved superscript names and normalized aliases", () =>
        {
            using (var f = new Fixture())
            {
                foreach (string name in new[] { "stream:note.txt", "NUL.txt", "com¹.txt", "LPT².log", "CON .txt", "name.txt ", "name.txt.", "a\0.txt", "bad\uD800.txt" })
                    Check(!LocalPathPolicy.IsSafeFileName(name), "unsafe name accepted");
                foreach (string name in new[] { "한글.txt", ".hidden.txt", "ordinary file.txt", "observation-123.txt" })
                    Check(LocalPathPolicy.IsSafeFileName(name), "valid leaf rejected");
                foreach (string path in new[] { "//server/share/a.txt", @"\\?\C:\a.txt", @"\\.\NUL", "relative.txt", Path.Combine(f.DirectoryPath, "a:stream.txt") })
                    ExpectBundleIo(() => LocalPathPolicy.NormalizeFile(path));
            }
        });

        Add("ab and recent identity labels distinguish matching file names without exposing full private locations", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                var a = NoteRecord(Path.Combine(f.DirectoryPath, "PRIVATE-A", "same.txt"));
                var b = NoteRecord(Path.Combine(f.DirectoryPath, "PRIVATE-B", "same.txt"));
                f.Interaction.ObservationOpener = () => a; vm.OpenSavedObservationCommand.Execute(null);
                f.Interaction.ObservationOpener = () => b; vm.OpenComparisonObservationCommand.Execute(null);
                Check(vm.SavedObservationIdentityText != vm.ComparisonObservationIdentityText, "same names cannot be distinguished");
                Check(!vm.SavedObservationIdentityText.Contains("PRIVATE") && !vm.ComparisonObservationIdentityText.Contains(f.DirectoryPath), "identity leaked path");
                var history = new RecentObservationStore(f.DirectoryPath); history.Record(a.SourcePath, a); var entry = history.Record(b.SourcePath, b)[0];
                Equal(vm.ComparisonObservationIdentityText, entry.IdentityText);
                Equal(a.IdentityText, NoteRecord(a.SourcePath).IdentityText);
            }
        });

        Add("recent selected item remains selected across note save preview refresh and a reordered list", () =>
        {
            using (var f = new Fixture())
            {
                var notes = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, notes);
                var recent = new RecentObservationStore(f.DirectoryPath);
                var a = NoteRecord(Path.Combine(f.DirectoryPath, "a.txt")); var b = NoteRecord(Path.Combine(f.DirectoryPath, "b.txt"));
                recent.Record(a.SourcePath, a); recent.Record(b.SourcePath, b);
                f.Interaction.RecentReader = () => recent.Load().Select(e => e.WithNote(notes.Load(e.NoteKey))).ToList().AsReadOnly();
                f.Interaction.RecentOpener = e => e.Path == a.SourcePath ? a : b;
                using (var vm = f.ViewModel())
                {
                    vm.SelectedRecentObservation = vm.RecentObservations.Single(e => e.Path == a.SourcePath);
                    vm.OpenRecentObservationCommand.Execute(null); Equal(a.SourcePath, vm.SelectedRecentObservation.Path);
                    var selected = vm.SelectedRecentObservation;
                    recent.Record(a.SourcePath, a);
                    vm.SavedObservationNote.Text = "메모 선택 유지"; vm.SavedObservationNote.SaveCommand.Execute(null);
                    Check(!ReferenceEquals(selected, vm.SelectedRecentObservation), "stale index item retained");
                    Equal(a.SourcePath, vm.SelectedRecentObservation.Path);
                    Check(vm.SelectedRecentObservation.NotePreview.Contains("선택 유지") && vm.OpenRecentObservationCommand.CanExecute(null), "selection or preview lost");
                    f.Interaction.RecentReader = () => Array.AsReadOnly(new RecentObservationEntry[0]);
                    vm.SavedObservationNote.Text = "다음"; vm.SavedObservationNote.SaveCommand.Execute(null);
                    Check(vm.SelectedRecentObservation == null && !vm.OpenRecentObservationCommand.CanExecute(null), "removed selection retained");
                }
            }
        });

        Add("recent refresh ignores transient selection clearing caused by a two-way items-source binding", () =>
        {
            using (var f = new Fixture())
            {
                var notes = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, notes);
                var history = new RecentObservationStore(f.DirectoryPath);
                var record = NoteRecord(Path.Combine(f.DirectoryPath, "selected.txt")); history.Record(record.SourcePath, record);
                f.Interaction.RecentReader = () => history.Load().Select(e => e.WithNote(notes.Load(e.NoteKey))).ToList().AsReadOnly();
                f.Interaction.RecentOpener = e => record;
                using (var vm = f.ViewModel())
                {
                    vm.SelectedRecentObservation = vm.RecentObservations[0];
                    int sourceChanges = 0;
                    vm.PropertyChanged += (sender, args) => {
                        if (args.PropertyName == "RecentObservations")
                        {
                            sourceChanges++;
                            // WPF Selector clears SelectedItem when ItemsSource is replaced.
                            vm.SelectedRecentObservation = null;
                        }
                    };
                    vm.OpenRecentObservationCommand.Execute(null);
                    Check(vm.SelectedRecentObservation != null && vm.SelectedRecentObservation.Path == record.SourcePath,
                        "two-way items-source update erased selected path");
                    vm.SavedObservationNote.Text = "선택 유지 확인"; vm.SavedObservationNote.SaveCommand.Execute(null);
                    Check(vm.SelectedRecentObservation != null && vm.SelectedRecentObservation.NotePreview.Contains("선택 유지 확인"),
                        "memo refresh lost selection or preview");
                    Check(sourceChanges >= 2 && vm.OpenRecentObservationCommand.CanExecute(null), "selection not restored after refresh");
                    vm.SelectedRecentObservation = null;
                    Check(vm.SelectedRecentObservation == null && !vm.OpenRecentObservationCommand.CanExecute(null), "explicit deselection outside refresh blocked");
                    vm.SelectedRecentObservation = vm.RecentObservations[0];
                    f.Interaction.RecentReader = () => Array.AsReadOnly(new RecentObservationEntry[0]);
                    vm.SavedObservationNote.Text = "목록 제거 확인"; vm.SavedObservationNote.SaveCommand.Execute(null);
                    Check(vm.SelectedRecentObservation == null && !vm.OpenRecentObservationCommand.CanExecute(null), "removed item remained selected");
                }
            }
        });

        Add("memo saved empty modified and reverted states stay clear with normalized Korean multiline drafts", () =>
        {
            using (var f = new Fixture())
            {
                var notes = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, notes);
                using (var vm = new ATIVBatteryGuard.ViewModels.ObservationNoteViewModel(f.Interaction, NoteRecord(Path.Combine(f.DirectoryPath, "a.txt"))))
                {
                    Check(vm.Status.Contains("비어"), "empty status missing");
                    vm.Text = "한글 입력\r\n둘째 줄"; Equal("한글 입력\n둘째 줄", vm.Text);
                    Check(vm.Status.Contains("수정 중"), "dirty status missing"); vm.SaveCommand.Execute(null);
                    vm.Text = "변경"; vm.Text = "한글 입력\r\n둘째 줄";
                    Check(!vm.HasChanges && vm.Status.Contains("수정 사항이 없습니다"), "revert state unclear");
                    Equal(1, f.Interaction.NoteSaves); Check(!vm.SaveCommand.CanExecute(null), "unchanged memo remains saveable");
                }
            }
        });

        Add("abandoned import recovery notice is bounded local non-destructive and allows restoring both TXT and memo", () =>
        {
            using (var f = new Fixture())
            {
                var original = NoteRecord(Path.Combine(f.DirectoryPath, "source.txt"));
                var bundle = ObservationBundle.Create(original, "중단 복원 메모");
                string stage = Path.Combine(f.DirectoryPath, "imported-observations", ".import-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(stage);
                string recovery = Path.Combine(stage, ObservationBundle.RecoveryFileName); bundle.Export(recovery);
                File.WriteAllText(Path.Combine(stage, original.FileName), original.Text);
                byte[] bytes = File.ReadAllBytes(recovery);
                string notice = ObservationBundle.RecoveryNotice(f.DirectoryPath);
                Check(notice.Contains("중단") && notice.Contains(ObservationBundle.RecoveryFileName) && !notice.Contains(f.DirectoryPath), "recovery guidance missing or leaked path");
                var imported = ObservationBundle.ReadFile(recovery).Import(f.DirectoryPath);
                Equal("중단 복원 메모", new ObservationNoteStore(f.DirectoryPath).Load(imported.NoteKey).Text);
                Check(bytes.SequenceEqual(File.ReadAllBytes(recovery)), "abandoned recovery auto-deleted or modified");
                Check(!File.Exists(Path.Combine(Path.GetDirectoryName(imported.SourcePath), ObservationBundle.RecoveryFileName)), "successful import retained recovery copy");
                Check(!new RecentObservationStore(f.DirectoryPath).Load().Any(), "unpublished stage entered recent list");
            }
        });

        Add("recovery notice distinguishes another active import from an abandoned stage by its file lease", () =>
        {
            using (var f = new Fixture())
            {
                string stage = Path.Combine(f.DirectoryPath, "imported-observations", ".import-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(stage);
                ObservationBundle.Create(NoteRecord(Path.Combine(f.DirectoryPath, "a.txt")), "memo").Export(Path.Combine(stage, ObservationBundle.RecoveryFileName));
                using (var active = new FileStream(stage + ".lock", FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None))
                    Equal("", ObservationBundle.RecoveryNotice(f.DirectoryPath));
                Check(ObservationBundle.RecoveryNotice(f.DirectoryPath).Contains("중단"), "abandoned stage hidden after lease release");
                Check(File.Exists(stage + ".lock"), "notice deleted lease data");
            }
        });

        Add("recovery notices never follow linked import folders and ordinary folders are not mistaken for pending imports", () =>
        {
            using (var f = new Fixture())
            {
                string root = Path.Combine(f.DirectoryPath, "imported-observations"); Directory.CreateDirectory(root);
                string ordinary = Path.Combine(root, "ordinary"); Directory.CreateDirectory(ordinary);
                File.WriteAllText(Path.Combine(ordinary, ObservationBundle.RecoveryFileName), "keep");
                Equal("", ObservationBundle.RecoveryNotice(f.DirectoryPath));
                string outside = Path.Combine(f.DirectoryPath, "outside"); Directory.CreateDirectory(outside);
                string file = Path.Combine(outside, ObservationBundle.RecoveryFileName); File.WriteAllText(file, "PRIVATE");
                if (!TryCreateQualityDirectoryLink(Path.Combine(root, ".import-" + Guid.NewGuid().ToString("N")), outside)) return;
                string notice = ObservationBundle.RecoveryNotice(f.DirectoryPath);
                Check(!notice.Contains("PRIVATE") && notice.Contains("확인하지 못"), "recovery followed link or hid error"); Equal("PRIVATE", File.ReadAllText(file));
            }
        });

        Add("fixed manual and observation log categories remain useful while arbitrary private text stays excluded", () =>
        {
            using (var f = new Fixture())
            {
                var log = new LocalLog(f.DirectoryPath);
                foreach (string code in new[] { "MANUAL_PROTECTION_REQUESTED", "MANUAL_PROTECTION_UNCERTAIN", "OBSERVATION_OPEN_FAILED", "OBSERVATION_CONFIRM_FAILED", "OBSERVATION_BUNDLE_EXPORT_FAILED" }) log.Write(code);
                log.Write("PRIVATE user path or memo"); string text = File.ReadAllText(log.LogPath);
                Check(text.Contains("MANUAL_PROTECTION_UNCERTAIN") && text.Contains("OBSERVATION_BUNDLE_EXPORT_FAILED"), "known categories collapsed");
                Check(text.Contains("UNRECOGNIZED_EVENT") && !text.Contains("PRIVATE"), "private input persisted");
            }
        });

        Add("repeated local open compare note save and close release file leases and retain bounded recent history", () =>
        {
            using (var f = new Fixture())
            {
                var notes = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, notes);
                var recent = new RecentObservationStore(f.DirectoryPath);
                var a = NoteRecord(Path.Combine(f.DirectoryPath, "a.txt")); var b = NoteRecord(Path.Combine(f.DirectoryPath, "b.txt"));
                File.WriteAllText(a.SourcePath, a.Text); File.WriteAllText(b.SourcePath, b.Text);
                f.Interaction.ObservationOpener = () => a;
                using (var vm = f.ViewModel())
                {
                    for (int i = 0; i < 100; i++)
                    {
                        f.Interaction.ObservationOpener = () => a; vm.OpenSavedObservationCommand.Execute(null);
                        f.Interaction.ObservationOpener = () => b; vm.OpenComparisonObservationCommand.Execute(null);
                        vm.SavedObservationNote.Text = "반복 " + i; vm.SavedObservationNote.SaveCommand.Execute(null);
                        recent.Record(a.SourcePath, a); recent.Record(b.SourcePath, b);
                        vm.CloseSavedObservationCommand.Execute(null); Check(!vm.SavedObservationVisible, "close did not release view");
                        using (File.Open(a.SourcePath, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { }
                        using (File.Open(Path.Combine(f.DirectoryPath, "observation-notes", a.NoteKey + ".json.lock"), FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { }
                    }
                }
                Equal(2, recent.Load().Count); Equal("반복 99", notes.Load(a.NoteKey).Text);
            }
        });
    }

    private static bool TryCreateQualityDirectoryLink(string link, string target)
    {
        try { Directory.CreateSymbolicLink(link, target); return true; }
        catch (Exception ex) when (Environment.OSVersion.Platform == PlatformID.Win32NT
            && (ex is IOException || ex is UnauthorizedAccessException || ex is PlatformNotSupportedException)) { return false; }
    }

    private static void RejectLocalStorage(Action action)
    {
        try { action(); } catch (SerializationException) { return; } catch (IOException) { return; }
        throw new InvalidOperationException("invalid local storage accepted");
    }
}
