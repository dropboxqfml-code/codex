using System;
using System.IO;
using System.Linq;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;

internal static partial class Program
{
    private static void RegisterRecentObservationTests()
    {
        Add("recent observations persist metadata deduplicate and retain the ten most recent paths", () =>
        {
            using (var f = new Fixture())
            {
                var store = new RecentObservationStore(f.DirectoryPath);
                Check(!store.Load().Any() && !File.Exists(store.FilePath), "empty read wrote an index");
                var snapshot = SavedBatteryObservation.Parse(SavedObservationText(), "sample.txt");
                for (int i = 0; i < 12; i++) store.Record(Path.Combine(f.DirectoryPath, i + ".txt"), snapshot);
                var loaded = new RecentObservationStore(f.DirectoryPath).Load();
                Equal(10, loaded.Count); Equal("11.txt", loaded[0].FileName); Equal("2.txt", loaded[9].FileName);
                Check(loaded[0].Summary.Contains("표본 1건") && loaded[0].Summary.Contains("사용자 중지"), "metadata missing");
                store.Record(Path.Combine(f.DirectoryPath, "5.txt"), snapshot);
                loaded = store.Load(); Equal(10, loaded.Count); Equal("5.txt", loaded[0].FileName);
                Equal(1, loaded.Count(entry => entry.FileName == "5.txt"));
                Check(!Directory.GetFiles(f.DirectoryPath, ".recent-*.tmp").Any(), "temporary file retained");
            }
        });

        Add("recent index lock failure preserves the previous file and a later writer merges latest entries", () =>
        {
            using (var f = new Fixture())
            {
                var first = new RecentObservationStore(f.DirectoryPath);
                var second = new RecentObservationStore(f.DirectoryPath);
                var snapshot = SavedBatteryObservation.Parse(SavedObservationText(), "sample.txt");
                first.Record(Path.Combine(f.DirectoryPath, "first.txt"), snapshot);
                byte[] before = File.ReadAllBytes(first.FilePath);
                using (var lease = new FileStream(first.FilePath + ".lock", FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                {
                    bool rejected = false;
                    try { second.Record(Path.Combine(f.DirectoryPath, "second.txt"), snapshot); } catch (IOException) { rejected = true; }
                    Check(rejected, "concurrent lease was ignored");
                    Check(before.SequenceEqual(File.ReadAllBytes(first.FilePath)), "failed update replaced the index");
                }
                second.Record(Path.Combine(f.DirectoryPath, "second.txt"), snapshot);
                first.Record(Path.Combine(f.DirectoryPath, "third.txt"), snapshot);
                Equal(3, second.Load().Count); Equal("third.txt", second.Load()[0].FileName);
            }
        });

        Add("recent index corruption and unsupported versions are reported while original bytes remain preserved", () =>
        {
            using (var f = new Fixture())
            {
                var store = new RecentObservationStore(f.DirectoryPath);
                var snapshot = SavedBatteryObservation.Parse(SavedObservationText(), "sample.txt");
                foreach (string invalid in new[] { "not json", "{\"Version\":2,\"Entries\":[]}", new string('x', 65537) })
                {
                    File.WriteAllText(store.FilePath, invalid);
                    bool rejected = false;
                    try { store.Record(Path.Combine(f.DirectoryPath, "file.txt"), snapshot); } catch { rejected = true; }
                    Check(rejected, "corrupt index overwritten");
                    Equal(invalid, File.ReadAllText(store.FilePath));
                }
            }
        });

        Add("recent index rejects nonlocal paths and remains readable when referenced files are missing", () =>
        {
            using (var f = new Fixture())
            {
                var store = new RecentObservationStore(f.DirectoryPath);
                var snapshot = SavedBatteryObservation.Parse(SavedObservationText(), "sample.txt");
                foreach (string path in new[] { @"\\server\share\record.txt", "//server/share/file.txt", "https://example.com/file.txt", "relative.txt" })
                {
                    bool rejected = false;
                    try { store.Record(path, snapshot); } catch { rejected = true; }
                    Check(rejected, "nonlocal or relative path stored");
                }
                string missing = Path.Combine(f.DirectoryPath, "missing.txt");
                store.Record(missing, snapshot);
                Check(!File.Exists(missing), "metadata operation created a referenced TXT");
                Equal(1, new RecentObservationStore(f.DirectoryPath).Load().Count);
            }
        });

        Add("recent selection reopens through file validation and missing files retain the previously opened graph", () =>
        {
            using (var f = new Fixture())
            {
                var store = new RecentObservationStore(f.DirectoryPath);
                string path = Path.Combine(f.DirectoryPath, "known.txt");
                File.WriteAllText(path, SavedObservationText());
                f.Interaction.RecentEntries = store.Record(path, SavedBatteryObservation.Parse(SavedObservationText(), "known.txt"));
                int opens = 0;
                f.Interaction.RecentOpener = entry =>
                {
                    opens++;
                    using (var input = File.OpenRead(entry.Path)) return SavedBatteryObservation.Read(input, entry.FileName);
                };
                using (var vm = f.ViewModel())
                {
                    Equal(0, opens); Equal(1, vm.RecentObservations.Count);
                    Check(!vm.OpenRecentObservationCommand.CanExecute(null), "unselected history was opened");
                    vm.SelectedRecentObservation = vm.RecentObservations[0];
                    Check(vm.OpenRecentObservationCommand.CanExecute(null), "recent item cannot be opened");
                    vm.OpenRecentObservationCommand.Execute(null);
                    Equal(1, opens); Equal("known.txt", vm.SavedObservationName);
                    var graph = vm.SavedObservationGraph;
                    File.Delete(path);
                    vm.SelectedRecentObservation = vm.RecentObservations[0];
                    vm.OpenRecentObservationCommand.Execute(null);
                    Check(vm.SavedObservationOpenFailed && ReferenceEquals(graph, vm.SavedObservationGraph), "missing file replaced history");
                    Check(vm.SavedObservationOpenStatus.Contains("이동") && !vm.SavedObservationOpenStatus.Contains(f.DirectoryPath),
                        "missing path feedback invalid");
                    vm.Dispose(); Check(!vm.OpenRecentObservationCommand.CanExecute(null), "disposed history can reopen");
                }
            }
        });

        Add("history update warnings do not convert a successful TXT save into a failed or duplicate save", () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                f.Interaction.RecentObservationNotice = "최근 기록 목록을 갱신하지 못했습니다.";
                vm.StartBatteryObservationCommand.Execute(null); vm.RefreshBattery(); vm.StopBatteryObservationCommand.Execute(null);
                vm.SaveBatteryObservationCommand.Execute(null);
                Check(!vm.ObservationSaveFailed && !vm.HasUnsavedObservation, "cache warning invalidated saved TXT");
                Check(vm.RecentObservationNotice.Contains("갱신하지 못"), "history warning hidden");
                vm.SaveBatteryObservationCommand.Execute(null); Equal(1, f.Interaction.ObservationSaves);
            }
        });
    }
}
