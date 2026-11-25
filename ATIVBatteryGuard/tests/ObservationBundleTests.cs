using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using ATIVBatteryGuard.Services;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;

internal static partial class Program
{
    private static void RegisterObservationBundleTests()
    {
        Add("observation bundle roundtrip preserves exact TXT unicode note and excludes source paths", () =>
        {
            using (var f = new Fixture())
            {
                string source = Path.Combine(f.DirectoryPath, "PRIVATE-source", "한글 기록.txt");
                string text = "\uFEFF" + SavedObservationText().Replace("\r\n", "\n").Replace("\n", "\r\n");
                string memo = "관찰 🙂\r\n둘째 줄\t메모 { } [ ] " + (char)34 + (char)92;
                var bundle = ObservationBundle.Create(NoteRecord(source, text), memo);
                byte[] bytes = bundle.ToBytes();
                var restored = ReadBundle(bytes);
                Equal(text, restored.Observation.Text); Equal("한글 기록.txt", restored.Observation.FileName);
                Equal(ObservationNote.Normalize(memo), restored.NoteText);
                Equal("", restored.Observation.NoteKey); Equal("", restored.Observation.SourcePath);
                var imported = restored.Import(f.DirectoryPath);
                Check(Encoding.UTF8.GetBytes(text).SequenceEqual(File.ReadAllBytes(imported.SourcePath)), "BOM or CRLF bytes changed on import");
                Check(!Encoding.UTF8.GetString(bytes).Contains("PRIVATE-source"), "source path entered bundle");
            }
        });

        Add("bundle export is atomic refuses existing targets and preserves original TXT and memo", () =>
        {
            using (var f = new Fixture())
            {
                string source = Path.Combine(f.DirectoryPath, "source.txt"); File.WriteAllText(source, SavedObservationText());
                var record = NoteRecord(source); var notes = new ObservationNoteStore(f.DirectoryPath);
                var note = notes.Save(record.NoteKey, "local", "missing");
                var bundle = ObservationBundle.Create(record, "exported draft");
                string path = Path.Combine(f.DirectoryPath, "export.ativrecord"); bundle.Export(path);
                Equal("exported draft", ObservationBundle.ReadFile(path).NoteText);
                byte[] before = File.ReadAllBytes(path);
                ExpectBundleIo(() => bundle.Export(path));
                Check(before.SequenceEqual(File.ReadAllBytes(path)), "existing bundle overwritten");
                ExpectBundleIo(() => bundle.Export(source)); Equal(record.Text, File.ReadAllText(source));
                Equal(note.Revision, notes.Load(record.NoteKey).Revision);
                Check(!Directory.GetFiles(f.DirectoryPath, ".bundle-*.tmp").Any(), "temporary export retained");
            }
        });

        Add("bundle export snapshots remain valid when source is edited moved or deleted", () =>
        {
            using (var f = new Fixture())
            {
                string path = Path.Combine(f.DirectoryPath, "source.txt"); File.WriteAllText(path, SavedObservationText());
                var record = NoteRecord(path); File.WriteAllText(path, "changed"); File.Delete(path);
                string export = Path.Combine(f.DirectoryPath, "snapshot.ativrecord");
                ObservationBundle.Create(record, "snapshot").Export(export);
                Equal(record.Text, ObservationBundle.ReadFile(export).Observation.Text);
                Check(!File.Exists(path), "export recreated source");
            }
        });

        Add("bundle import rebinds note at a new location and supports recent reopening and re-export", () =>
        {
            using (var source = new Fixture()) using (var destination = new Fixture())
            {
                string path = Path.Combine(source.DirectoryPath, "source.txt"); File.WriteAllText(path, SavedObservationText());
                var record = NoteRecord(path); var sourceNotes = new ObservationNoteStore(source.DirectoryPath);
                sourceNotes.Save(record.NoteKey, "original local memo", "missing");
                string package = Path.Combine(source.DirectoryPath, "move.ativrecord");
                ObservationBundle.Create(record, "moved 🙂\n메모").Export(package);
                byte[] original = File.ReadAllBytes(package);
                var imported = ObservationBundle.ReadFile(package).Import(destination.DirectoryPath);
                Check(imported.Success && File.Exists(imported.SourcePath) && imported.NoteKey != record.NoteKey, "destination identity not restored");
                Equal(record.Text, File.ReadAllText(imported.SourcePath)); Equal("source.txt", imported.FileName);
                var notes = new ObservationNoteStore(destination.DirectoryPath);
                Equal("moved 🙂\n메모", notes.Load(imported.NoteKey).Text);
                var recent = new RecentObservationStore(destination.DirectoryPath); recent.Record(imported.SourcePath, imported);
                var entry = recent.Load()[0].WithNote(notes.Load(imported.NoteKey)); Check(entry.HasNote, "recent note missing");
                SavedBatteryObservation reopened;
                using (var input = File.OpenRead(entry.Path)) reopened = SavedBatteryObservation.Read(input, entry.FileName, entry.Path);
                Equal(imported.NoteKey, reopened.NoteKey);
                var again = ReadBundle(ObservationBundle.Create(reopened, notes.Load(reopened.NoteKey).Text).ToBytes());
                Equal(record.Text, again.Observation.Text); Equal("moved 🙂\n메모", again.NoteText);
                Equal("original local memo", sourceNotes.Load(record.NoteKey).Text);
                Check(original.SequenceEqual(File.ReadAllBytes(package)), "source bundle changed");
                Equal(record.Text, File.ReadAllText(path));
            }
        });

        Add("repeated imports with matching names and contents retain independent notes and existing destination files", () =>
        {
            using (var f = new Fixture())
            {
                string existing = Path.Combine(f.DirectoryPath, "record.txt"); File.WriteAllText(existing, "existing");
                var bundle = ObservationBundle.Create(NoteRecord(existing), "restored");
                var a = bundle.Import(f.DirectoryPath); var b = bundle.Import(f.DirectoryPath);
                Check(a.SourcePath != b.SourcePath && a.NoteKey != b.NoteKey, "import overwrote matching record");
                var notes = new ObservationNoteStore(f.DirectoryPath); var old = notes.Load(a.NoteKey);
                Check(notes.Save(a.NoteKey, "A edited", old.Revision).Available, "A edit failed");
                Equal("restored", notes.Load(b.NoteKey).Text); Equal("existing", File.ReadAllText(existing));
            }
        });

        Add("empty memo and maximum memo and TXT bounds survive bundle transfer", () =>
        {
            using (var f = new Fixture())
            {
                string text = SavedObservationText();
                int remaining = SavedBatteryObservation.MaximumBytes - Encoding.UTF8.GetByteCount(text) - 1;
                string large = text.Replace(SavedBatteryObservation.Columns, new string('x', remaining) + "\n" + SavedBatteryObservation.Columns);
                Equal(SavedBatteryObservation.MaximumBytes, Encoding.UTF8.GetByteCount(large));
                var record = NoteRecord(Path.Combine(f.DirectoryPath, "maximum.txt"), large); Check(record.Success, record.ErrorMessage);
                foreach (string memo in new[] { "", string.Concat(Enumerable.Repeat("🙂", 500)) })
                {
                    var bundle = ReadBundle(ObservationBundle.Create(record, memo).ToBytes());
                    Equal(large, bundle.Observation.Text); Equal(memo, bundle.NoteText);
                    var imported = bundle.Import(f.DirectoryPath); Equal(memo, new ObservationNoteStore(f.DirectoryPath).Load(imported.NoteKey).Text);
                }
            }
        });

        Add("bundle parser rejects tampering unsupported versions missing duplicate fields and trailing content", () =>
        {
            byte[] valid = ObservationBundle.Create(SavedBatteryObservation.Parse(SavedObservationText(), "a.txt"), "memo").ToBytes();
            foreach (Action<JsonObject> change in new Action<JsonObject>[] {
                d => d["Version"] = 2, d => d["Format"] = "other", d => d.Remove("NoteText"),
                d => d["ObservationSha256"] = new string('0', 64), d => d["NoteText"] = "changed",
                d => d["NoteSha256"] = "invalid", d => d["ObservationText"] = null, d => d["NoteText"] = null })
                RejectBundle(MutateBundle(valid, change));
            string json = Encoding.UTF8.GetString(valid);
            RejectBundle(Encoding.UTF8.GetBytes(json.Substring(0, json.Length - 1)));
            RejectBundle(Encoding.UTF8.GetBytes(json + "{}"));
            RejectBundle(Encoding.UTF8.GetBytes(json + " PRIVATE-TRAILING"));
            RejectBundle(Encoding.UTF8.GetBytes(json.Insert(1, "\"Version\":1,")));
            Equal("memo", ReadBundle(Encoding.UTF8.GetBytes(json + " \r\n\t")).NoteText);
        });

        Add("bundle parser validates TXT and note even when attacker recalculates hashes", () =>
        {
            byte[] valid = ObservationBundle.Create(SavedBatteryObservation.Parse(SavedObservationText(), "a.txt"), "memo").ToBytes();
            foreach (string text in new[] { "PRIVATE invalid TXT", SavedObservationText().Replace("0,80,", "0,999,"), new string('x', 262145) })
                RejectBundle(MutateBundle(valid, d => { d["ObservationText"] = text; d["ObservationSha256"] = BundleHash(text); }));
            foreach (string note in new[] { new string('x', 1001), "bad\0control", "line\r\nending" })
                RejectBundle(MutateBundle(valid, d => { d["NoteText"] = note; d["NoteSha256"] = BundleHash(note); }));
        });

        Add("bundle parser rejects traversal reserved names paths streams and oversized file names", () =>
        {
            byte[] valid = ObservationBundle.Create(SavedBatteryObservation.Parse(SavedObservationText(), "a.txt"), "memo").ToBytes();
            foreach (string name in new[] { "../escape.txt", "..\\escape.txt", "/absolute.txt", "C:\\absolute.txt", "file:stream.txt", "CON.txt", "lpt1.txt", "AUX.data.txt", "COM1 .txt", "bad\nname.txt", "a.exe", new string('a', 252) + ".txt", "" })
                RejectBundle(MutateBundle(valid, d => d["ObservationFileName"] = name));
            Equal("a.txt", ReadBundle(valid).Observation.FileName);
        });

        Add("bundle input limits malformed UTF8 and excessive nesting are rejected with bounded diagnostics", () =>
        {
            RejectBundle(new byte[ObservationBundle.MaximumBytes + 1]);
            RejectBundle(new byte[] { 0xff, 0xfe, 0x00 });
            RejectBundle(Encoding.UTF8.GetBytes("{\"PRIVATE\":" + new string('[', 40) + "0" + new string(']', 40) + "}"));
            byte[] valid = ObservationBundle.Create(SavedBatteryObservation.Parse(SavedObservationText(), "a.txt"), "memo").ToBytes();
            // Bound the reader independently of seek support and small incoming chunks.
            using (var stream = new BundleChunkStream(valid)) Equal("memo", ObservationBundle.Read(stream).NoteText);
        });

        Add("bundle local path policy rejects network relative and symbolic link paths without writing targets", () =>
        {
            using (var f = new Fixture())
            {
                var bundle = ObservationBundle.Create(NoteRecord(Path.Combine(f.DirectoryPath, "a.txt")), "memo");
                foreach (string path in new[] { "//server/share/export.ativrecord", "relative.ativrecord" })
                { ExpectBundleIo(() => bundle.Export(path)); ExpectBundleIo(() => ObservationBundle.ReadFile(path)); }
                string real = Path.Combine(f.DirectoryPath, "real"); Directory.CreateDirectory(real);
                string link = Path.Combine(f.DirectoryPath, "linked"); if (!TryCreateQualityDirectoryLink(link, real)) return;
                ExpectBundleIo(() => bundle.Export(Path.Combine(link, "a.ativrecord")));
                ExpectBundleIo(() => bundle.Import(link)); Check(!Directory.EnumerateFileSystemEntries(real).Any(), "link followed");
                string file = Path.Combine(f.DirectoryPath, "file"); File.WriteAllText(file, "unchanged");
                string alias = Path.Combine(f.DirectoryPath, "alias"); File.CreateSymbolicLink(alias, file);
                ExpectBundleIo(() => bundle.Export(alias)); ExpectBundleIo(() => ObservationBundle.ReadFile(alias));
                Equal("unchanged", File.ReadAllText(file));
            }
        });

        Add("failed import note storage leaves no published TXT and supports retry preserving the bundle", () =>
        {
            using (var f = new Fixture())
            {
                var bundle = ObservationBundle.Create(NoteRecord(Path.Combine(f.DirectoryPath, "a.txt")), "memo");
                string blocked = Path.Combine(f.DirectoryPath, "observation-notes"); File.WriteAllText(blocked, "existing blocker");
                ExpectBundleIo(() => bundle.Import(f.DirectoryPath)); Equal("existing blocker", File.ReadAllText(blocked));
                Check(!Directory.EnumerateFileSystemEntries(Path.Combine(f.DirectoryPath, "imported-observations")).Any(), "failed import published or retained stage");
                File.Delete(blocked);
                var imported = bundle.Import(f.DirectoryPath); Equal("memo", new ObservationNoteStore(f.DirectoryPath).Load(imported.NoteKey).Text);
            }
        });

        Add("import rollback removes only its own note revision and retains concurrent modifications", () =>
        {
            using (var f = new Fixture())
            {
                var notes = new ObservationNoteStore(f.DirectoryPath); string key = NoteRecord(Path.Combine(f.DirectoryPath, "a.txt")).NoteKey;
                var own = notes.Save(key, "own", "missing"); var other = notes.Save(key, "other", own.Revision);
                Check(!notes.RemoveImportedRevision(key, own.Revision), "rollback removed concurrent revision");
                Equal("other", notes.Load(key).Text);
                Check(notes.RemoveImportedRevision(key, other.Revision), "own rollback failed"); Equal("missing", notes.Load(key).Revision);
            }
        });

        Add("viewmodel bundle export includes displayed draft and preserves unsaved state on success cancellation and failure", () =>
        {
            using (var f = new Fixture())
            {
                var notes = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, notes);
                var record = NoteRecord(Path.Combine(f.DirectoryPath, "a.txt")); f.Interaction.ObservationOpener = () => record;
                using (var vm = f.ViewModel())
                {
                    Check(!vm.ExportObservationBundleCommand.CanExecute(null), "export enabled before open");
                    vm.OpenSavedObservationCommand.Execute(null); vm.SavedObservationNote.Text = "draft";
                    f.Interaction.BundleExporter = (snapshot, text) => {
                        Check(ReferenceEquals(record, snapshot), "wrong snapshot"); Equal("draft", text);
                        Check(!vm.TryPrepareToClose() && !vm.ImportObservationBundleCommand.CanExecute(null), "export allows close or import reentry");
                        vm.ExportObservationBundleCommand.Execute(null); return "export.ativrecord";
                    };
                    vm.ExportObservationBundleCommand.Execute(null); Equal(1, f.Interaction.BundleExports);
                    Check(vm.SavedObservationNote.HasChanges, "draft state changed");
                    Check(vm.SavedObservationOpenStatus.Contains("로컬 메모는 수정 중"), "unsaved memo feedback missing");
                    f.Interaction.BundleExporter = (r, t) => null; vm.ExportObservationBundleCommand.Execute(null);
                    Check(!vm.SavedObservationOpenFailed && vm.SavedObservationOpenStatus.Contains("취소"), "cancel reported as error");
                    f.Interaction.BundleExporter = (r, t) => throw new IOException("PRIVATE-path"); vm.ExportObservationBundleCommand.Execute(null);
                    Check(vm.SavedObservationOpenFailed && !vm.SavedObservationOpenStatus.Contains("PRIVATE"), "failure leaked details");
                    Equal("draft", vm.SavedObservationNote.Text); Equal(0, f.Interaction.NoteSaves); Equal(0, f.Interaction.ObservationSaves);
                    Equal("missing", notes.Load(record.NoteKey).Revision);
                    vm.SavedObservationNote.Text = "bad\0"; Check(!vm.ExportObservationBundleCommand.CanExecute(null), "invalid draft export enabled");
                    vm.SavedObservationNote.Text = "valid"; Check(vm.ExportObservationBundleCommand.CanExecute(null), "export did not recover");
                }
            }
        });

        Add("viewmodel import cancellation validation and save failure preserve graph draft and avoid destination writes", () =>
        {
            using (var f = new Fixture())
            {
                var notes = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, notes);
                var bundle = ObservationBundle.Create(NoteRecord(Path.Combine(f.DirectoryPath, "new.txt")), "new memo");
                f.Interaction.ObservationOpener = () => NoteRecord(Path.Combine(f.DirectoryPath, "old.txt"));
                using (var vm = f.ViewModel())
                {
                    vm.OpenSavedObservationCommand.Execute(null); var graph = vm.SavedObservationGraph; var editor = vm.SavedObservationNote; editor.Text = "keep draft";
                    f.Interaction.BundleOpener = () => null; vm.ImportObservationBundleCommand.Execute(null); Equal(0, f.Interaction.NoteConfirmations);
                    f.Interaction.BundleOpener = () => throw new InvalidDataException("검증 실패"); vm.ImportObservationBundleCommand.Execute(null);
                    Check(vm.SavedObservationOpenFailed, "validation error hidden"); Equal(0, f.Interaction.NoteConfirmations);
                    f.Interaction.BundleOpener = () => bundle; f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Cancel;
                    vm.ImportObservationBundleCommand.Execute(null); Equal(0, f.Interaction.BundleImports);
                    f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Save;
                    f.Interaction.NoteSaver = (r, t, rev) => ObservationNote.Unavailable("cannot save");
                    vm.ImportObservationBundleCommand.Execute(null); Equal(0, f.Interaction.BundleImports);
                    Check(ReferenceEquals(editor, vm.SavedObservationNote) && ReferenceEquals(graph, vm.SavedObservationGraph), "cancel replaced current record");
                    Equal("keep draft", editor.Text); Check(editor.HasChanges, "unsaved state lost");
                    f.Interaction.NoteConfirmer = (name, action) => ObservationLossChoice.Discard;
                    f.Interaction.BundleImporter = b => throw new IOException("PRIVATE"); vm.ImportObservationBundleCommand.Execute(null);
                    Check(vm.SavedObservationOpenFailed && !vm.SavedObservationOpenStatus.Contains("PRIVATE"), "import failure invalid");
                    Equal("keep draft", editor.Text); Check(ReferenceEquals(graph, vm.SavedObservationGraph), "failed import replaced graph");
                    f.Interaction.BundleImporter = b => b.Import(f.DirectoryPath); vm.ImportObservationBundleCommand.Execute(null);
                    Equal("new memo", vm.SavedObservationNote.Text); Check(!vm.SavedObservationOpenFailed, "retry did not recover");
                }
            }
        });

        Add("viewmodel moved bundles restore recent previews and independent AB notes without hardware or capture changes", () =>
        {
            using (var f = new Fixture())
            {
                var notes = new ObservationNoteStore(f.DirectoryPath); ConfigureNotes(f, notes);
                var history = new RecentObservationStore(f.DirectoryPath);
                f.Interaction.RecentReader = () => history.Load().Select(e => e.WithNote(notes.Load(e.NoteKey))).ToList().AsReadOnly();
                f.Interaction.RecentOpener = e => NoteRecord(e.Path, File.ReadAllText(e.Path));
                var bundle = ObservationBundle.Create(NoteRecord(Path.Combine(f.DirectoryPath, "source.txt")), "imported memo");
                f.Interaction.BundleOpener = () => bundle;
                f.Interaction.BundleImporter = b => { var r = b.Import(f.DirectoryPath); history.Record(r.SourcePath, r); return r; };
                var battery = new PresentationGraphBattery(); var service = new ManualVmService(); var clock = new ManualUsabilityClock();
                using (var vm = PresentationGraphVm(f, battery, service, clock))
                {
                    vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); var live = vm.ObservationGraph;
                    int reads = battery.Calls, operations = service.Operations.Count, times = clock.Calls;
                    Check(!vm.ImportComparisonBundleCommand.CanExecute(null), "B import without A");
                    vm.ImportObservationBundleCommand.Execute(null); var a = vm.SavedObservationGraph;
                    vm.ImportComparisonBundleCommand.Execute(null);
                    Check(vm.ComparisonObservationVisible && !ReferenceEquals(vm.SavedObservationNote, vm.ComparisonObservationNote), "imported AB share identity");
                    Equal("imported memo", vm.SavedObservationNote.Text); Equal("imported memo", vm.ComparisonObservationNote.Text);
                    vm.ComparisonObservationNote.Text = "B draft";
                    f.Interaction.BundleExporter = (r, text) => { Equal("B draft", text); return "b.ativrecord"; };
                    vm.ExportComparisonBundleCommand.Execute(null); Equal(1, f.Interaction.BundleExports);
                    Check(vm.RecentObservations.Count == 2 && vm.RecentObservations.All(e => e.NotePreview.Contains("imported memo")), "recent restoration failed");
                    vm.ComparisonObservationNote.SaveCommand.Execute(null); Check(vm.RecentObservations[0].NotePreview.Contains("B draft"), "recent note not updated");
                    vm.CloseSavedObservationCommand.Execute(null); vm.SelectedRecentObservation = vm.RecentObservations[0];
                    vm.OpenRecentObservationCommand.Execute(null); Equal("B draft", vm.SavedObservationNote.Text);
                    Check(vm.ObservationActive && ReferenceEquals(live, vm.ObservationGraph), "bundle changed live capture");
                    Equal(reads, battery.Calls); Equal(operations, service.Operations.Count); Equal(times, clock.Calls); Equal(0, f.Interaction.ObservationSaves);
                }
            }
        });

        Add("unavailable memo cannot be silently exported and import confirmation handles shared note owners", () =>
        {
            using (var f = new Fixture())
            {
                var record = NoteRecord(Path.Combine(f.DirectoryPath, "a.txt")); f.Interaction.ObservationOpener = () => record;
                f.Interaction.NoteLoader = r => ObservationNote.Unavailable("unavailable");
                using (var vm = f.ViewModel())
                {
                    vm.OpenSavedObservationCommand.Execute(null); Check(!vm.ExportObservationBundleCommand.CanExecute(null), "unknown memo exported as empty");
                    f.Interaction.NoteLoader = r => ObservationNote.Empty; vm.SavedObservationNote.ReloadCommand.Execute(null);
                    Check(vm.ExportObservationBundleCommand.CanExecute(null), "reload did not enable export");
                    ConfigureNotes(f, new ObservationNoteStore(f.DirectoryPath));
                    vm.OpenComparisonObservationCommand.Execute(null); var shared = vm.SavedObservationNote; shared.Text = "shared draft";
                    f.Interaction.BundleOpener = () => ObservationBundle.Create(record, "new"); f.Interaction.BundleImporter = b => b.Import(f.DirectoryPath);
                    vm.ImportComparisonBundleCommand.Execute(null); Equal(0, f.Interaction.NoteConfirmations);
                    Check(ReferenceEquals(shared, vm.SavedObservationNote) && shared.HasChanges, "shared A draft lost");
                    Equal("new", vm.ComparisonObservationNote.Text); Equal("shared draft", shared.Text);
                }
            }
        });

        Add("late bundle dialog and import returns cannot revive disposed viewmodels", () =>
        {
            using (var f = new Fixture())
            {
                var bundle = ObservationBundle.Create(NoteRecord(Path.Combine(f.DirectoryPath, "a.txt")), "memo");
                var vm = f.ViewModel(); f.Interaction.BundleOpener = () => { vm.Dispose(); return bundle; };
                vm.ImportObservationBundleCommand.Execute(null); Equal(0, f.Interaction.BundleImports); Check(!vm.SavedObservationVisible, "late dialog revived graph");
                vm = f.ViewModel(); f.Interaction.BundleOpener = () => bundle;
                f.Interaction.BundleImporter = b => { var record = b.Import(f.DirectoryPath); vm.Dispose(); return record; };
                vm.ImportObservationBundleCommand.Execute(null); Check(!vm.SavedObservationVisible && vm.SavedObservationNote == null, "late import revived graph");
            }
        });
    }

    private static string BundleHash(string text)
    { return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text))).ToLowerInvariant(); }
    private static ObservationBundle ReadBundle(byte[] bytes)
    { using (var input = new MemoryStream(bytes)) return ObservationBundle.Read(input); }
    private static byte[] MutateBundle(byte[] bytes, Action<JsonObject> change)
    { var value = JsonNode.Parse(bytes).AsObject(); change(value); return Encoding.UTF8.GetBytes(value.ToJsonString()); }
    private static void RejectBundle(byte[] bytes)
    {
        try { ReadBundle(bytes); }
        catch (InvalidDataException ex) { Check(!ex.Message.Contains("PRIVATE"), "untrusted input echoed"); return; }
        throw new InvalidOperationException("invalid bundle accepted");
    }
    private static void ExpectBundleIo(Action action)
    {
        try { action(); } catch (IOException) { return; } catch (UnauthorizedAccessException) { return; }
        throw new InvalidOperationException("unsafe or unavailable path accepted");
    }
    private sealed class BundleChunkStream : MemoryStream
    {
        public BundleChunkStream(byte[] bytes) : base(bytes) { }
        public override bool CanSeek => false;
        public override int Read(byte[] buffer, int offset, int count) { return base.Read(buffer, offset, Math.Min(7, count)); }
    }
}
