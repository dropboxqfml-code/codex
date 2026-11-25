using System;
using System.IO;
using System.Linq;
using System.Text;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;

internal static partial class Program
{
    private static void RegisterObservationNoteStoreTests()
    {
        Add("observation notes persist multiline unicode and clearing across store instances while TXT bytes stay intact", () =>
        {
            using (var f = new Fixture())
            {
                string path = Path.Combine(f.DirectoryPath, "record.txt");
                File.WriteAllText(path, SavedObservationText());
                byte[] original = File.ReadAllBytes(path);
                var record = NoteRecord(path);
                var store = new ObservationNoteStore(f.DirectoryPath);
                var empty = store.Load(record.NoteKey);
                Check(empty.Available && empty.Text == "", "new note unavailable");
                Check(!Directory.Exists(Path.Combine(f.DirectoryPath, "observation-notes")), "reading created a note folder");
                var saved = store.Save(record.NoteKey, "보호 관찰 🙂\r\n두 번째 줄\t내용", empty.Revision);
                Check(saved.Available, saved.Notice); Equal("보호 관찰 🙂\n두 번째 줄\t내용", saved.Text);
                var reopened = new ObservationNoteStore(f.DirectoryPath).Load(record.NoteKey);
                Equal(saved.Text, reopened.Text); Equal(saved.Revision, reopened.Revision);
                var cleared = store.Save(record.NoteKey, "", reopened.Revision);
                Check(cleared.Available, cleared.Notice); Equal("", store.Load(record.NoteKey).Text);
                Check(original.SequenceEqual(File.ReadAllBytes(path)), "memo changed source TXT");
            }
        });

        Add("note identity binds file location and validated content while tolerating BOM and newline conventions", () =>
        {
            using (var f = new Fixture())
            {
                string path = Path.Combine(f.DirectoryPath, "record.txt");
                string text = SavedObservationText();
                var a = SavedBatteryObservation.Parse(text, "record.txt", path);
                var lineEndingCopy = SavedBatteryObservation.Parse("\uFEFF" + text.Replace("\r\n", "\n").Replace("\n", "\r\n"), "record.txt", path);
                var otherPath = SavedBatteryObservation.Parse(text, "record.txt", Path.Combine(f.DirectoryPath, "other", "record.txt"));
                var changed = SavedBatteryObservation.Parse(text.Replace("0,80,", "0,81,"), "record.txt", path);
                Check(a.Success && changed.Success, "fixture invalid");
                Equal(a.NoteKey, lineEndingCopy.NoteKey);
                Check(a.NoteKey != otherPath.NoteKey && a.NoteKey != changed.NoteKey, "different records share note identity");
                var store = new ObservationNoteStore(f.DirectoryPath);
                Check(store.Save(a.NoteKey, "A only", ObservationNote.Empty.Revision).Available, "save failed");
                Equal("", store.Load(otherPath.NoteKey).Text); Equal("", store.Load(changed.NoteKey).Text);
                Check(!a.Summary.Contains(f.DirectoryPath), "private path exposed");
            }
        });

        Add("notes survive recent list eviction and optional identity metadata supports legacy recent files", () =>
        {
            using (var f = new Fixture())
            {
                var history = new RecentObservationStore(f.DirectoryPath);
                var notes = new ObservationNoteStore(f.DirectoryPath);
                string path = Path.Combine(f.DirectoryPath, "first.txt");
                var first = NoteRecord(path);
                notes.Save(first.NoteKey, "keep after eviction", ObservationNote.Empty.Revision);
                history.Record(path, first);
                for (int i = 0; i < 12; i++)
                {
                    string next = Path.Combine(f.DirectoryPath, i + ".txt");
                    history.Record(next, NoteRecord(next));
                }
                Check(history.Load().All(entry => entry.Path != path), "first entry not evicted");
                Equal("keep after eviction", new ObservationNoteStore(f.DirectoryPath).Load(first.NoteKey).Text);
                File.WriteAllText(history.FilePath, System.Text.Json.JsonSerializer.Serialize(new {
                    Version = 1, Entries = new[] { new { Path = path, SampleCount = 1, ElapsedSeconds = 0, Status = 2 } }
                }));
                var legacy = history.Load()[0];
                Check(string.IsNullOrEmpty(legacy.NoteKey) && !legacy.WithNote(ObservationNote.Empty).HasNote, "legacy entry rejected");
                var updated = history.Record(path, first)[0].WithNote(notes.Load(first.NoteKey));
                Check(updated.NotePreview.Contains("keep after eviction"), "note not recovered on open");
                Check(!File.ReadAllText(history.FilePath).Contains("keep after eviction"), "memo text entered recent index");
            }
        });

        Add("note writes detect stale revisions and recover after reading the latest stored value", () =>
        {
            using (var f = new Fixture())
            {
                var a = new ObservationNoteStore(f.DirectoryPath); var b = new ObservationNoteStore(f.DirectoryPath);
                string key = NoteRecord(Path.Combine(f.DirectoryPath, "record.txt")).NoteKey;
                var oldA = a.Load(key); var oldB = b.Load(key);
                var first = a.Save(key, "from A", oldA.Revision);
                Check(first.Available, first.Notice);
                var conflict = b.Save(key, "from B", oldB.Revision);
                Check(!conflict.Available && conflict.Notice.Contains("다른 창"), "stale write accepted");
                Equal("from A", a.Load(key).Text);
                var retry = b.Save(key, "merged B", b.Load(key).Revision);
                Check(retry.Available, retry.Notice); Equal("merged B", a.Load(key).Text);
            }
        });

        Add("note lock contention retains original data and later retry succeeds", () =>
        {
            using (var f = new Fixture())
            {
                var store = new ObservationNoteStore(f.DirectoryPath);
                string key = NoteRecord(Path.Combine(f.DirectoryPath, "record.txt")).NoteKey;
                var first = store.Save(key, "original", ObservationNote.Empty.Revision);
                string file = Path.Combine(f.DirectoryPath, "observation-notes", key + ".json");
                byte[] before = File.ReadAllBytes(file);
                using (var lease = new FileStream(file + ".lock", FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                    Check(!store.Save(key, "blocked", first.Revision).Available, "lock ignored");
                Check(before.SequenceEqual(File.ReadAllBytes(file)), "failed write changed note");
                Check(store.Save(key, "retry", first.Revision).Available, "lock release did not recover");
            }
        });

        Add("invalid note keys text limits controls and malformed unicode cannot alter stored notes", () =>
        {
            using (var f = new Fixture())
            {
                var store = new ObservationNoteStore(f.DirectoryPath);
                foreach (string key in new[] { "", "../outside", new string('G', 64), (string)null })
                {
                    Check(!store.Load(key).Available, "invalid key loaded");
                    Check(!store.Save(key, "bad", "missing").Available, "invalid key wrote a file");
                }
                string valid = NoteRecord(Path.Combine(f.DirectoryPath, "record.txt")).NoteKey;
                var first = store.Save(valid, new string('가', 1000), ObservationNote.Empty.Revision);
                Check(first.Available, first.Notice);
                foreach (string invalid in new[] { new string('x', 1001), "bad\0control", "\uD800" })
                    Check(!store.Save(valid, invalid, first.Revision).Available, "invalid text accepted");
                Equal(first.Text, store.Load(valid).Text);
                Check(!Directory.GetFiles(Path.Combine(f.DirectoryPath, "observation-notes"), ".note-*.tmp").Any(), "temporary file retained");
            }
        });

        Add("corrupt future and oversized note files remain preserved with editing unavailable", () =>
        {
            using (var f = new Fixture())
            {
                var store = new ObservationNoteStore(f.DirectoryPath);
                string key = NoteRecord(Path.Combine(f.DirectoryPath, "record.txt")).NoteKey;
                string folder = Path.Combine(f.DirectoryPath, "observation-notes"); Directory.CreateDirectory(folder);
                string path = Path.Combine(folder, key + ".json");
                foreach (string invalid in new[] { "PRIVATE-CORRUPT", "{\"Version\":2,\"Text\":\"future\"}", new string('x', 16385) })
                {
                    File.WriteAllText(path, invalid);
                    var loaded = store.Load(key);
                    Check(!loaded.Available && !loaded.Notice.Contains("PRIVATE"), "invalid stored data accepted or echoed");
                    Check(!store.Save(key, "overwrite", "missing").Available, "unknown note overwritten");
                    Equal(invalid, File.ReadAllText(path));
                }
            }
        });
    }

    private static SavedBatteryObservation NoteRecord(string path, string text = null)
    {
        return SavedBatteryObservation.Parse(text ?? SavedObservationText(), Path.GetFileName(path), path);
    }

    private static void ConfigureNotes(Fixture f, ObservationNoteStore store)
    {
        f.Interaction.NoteLoader = record => store.Load(record.NoteKey);
        f.Interaction.NoteSaver = (record, text, revision) => store.Save(record.NoteKey, text, revision);
    }
}
