using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;

internal static partial class Program
{
    // The approved Protection1To0-v1 purpose is tested only in fresh temporary directories.
    // No real application-data directory or other reservation is inspected.
    private static void RegisterWsabiWmiProtection1To0ReservationTests()
    {
        Add("Protection1To0 uncertain write or flush never grants a claim and leaves the new purpose spent", () => WithDirectory(dir =>
        {
            for (int stage = 0; stage < 3; stage++)
            {
                int writes = 0; string local = Path.Combine(dir, "failure-" + stage);
                var reservation = new WsabiWmiProtection1To0FileReservation(local, (stream, bytes) =>
                {
                    writes++;
                    if (stage != 0) stream.Write(bytes, 0, stage == 1 ? 1 : bytes.Length);
                    if (stage == 2) stream.Flush(true);
                    throw new IOException("Synthetic uncertain disable marker write or flush.");
                });
                Equal(WsabiWmiOneShotReservationStatus.Unavailable, reservation.TryClaim()); Equal(1, writes);
                string marker = Path.Combine(local, WsabiWmiProtection1To0FileReservation.MarkerFileName);
                Check(File.Exists(marker), "uncertain disable marker was rolled back");
                byte[] before = File.ReadAllBytes(marker);
                Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, reservation.TryClaim());
                Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, new WsabiWmiProtection1To0FileReservation(local).TryClaim());
                Equal(1, writes); Check(before.SequenceEqual(File.ReadAllBytes(marker)), "uncertain disable marker was repaired or retried");
            }
        }));

        Add("Protection1To0 claim does not open modify or reuse locked historical purpose markers", () => WithDirectory(dir =>
        {
            string[] priorNames = { "FixedModeReadA-v1.attempt", "FixedModeReadA-Access1.attempt", "WmiQuery65-v1.attempt", "Protection0To1-v1.attempt" };
            var locks = new System.Collections.Generic.List<FileStream>();
            try
            {
                foreach (string name in priorNames)
                {
                    string path = Path.Combine(dir, name); File.WriteAllText(path, "historical-spent-" + name);
                    locks.Add(new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None));
                }
                Equal(WsabiWmiOneShotReservationStatus.Claimed, new WsabiWmiProtection1To0FileReservation(dir).TryClaim());
                Equal(5, Directory.GetFiles(dir).Length);
            }
            finally { foreach (var stream in locks) stream.Dispose(); }
            foreach (string name in priorNames) Equal("historical-spent-" + name, File.ReadAllText(Path.Combine(dir, name)));
        }));

        Add("Protection1To0 reservation writes only its fixed durable purpose and refuses subsequent objects", () => WithDirectory(dir =>
        {
            Equal("Protection1To0-v1", WsabiWmiProtection1To0FileReservation.Purpose);
            Equal("Protection1To0-v1.attempt", WsabiWmiProtection1To0FileReservation.MarkerFileName);
            string local = Path.Combine(dir, "ATIVBatteryGuard", "Experiments");
            IWsabiWmiOneShotReservation reservation = new WsabiWmiProtection1To0FileReservation(local);
            Equal(WsabiWmiOneShotReservationStatus.Claimed, reservation.TryClaim());
            string marker = Path.Combine(local, WsabiWmiProtection1To0FileReservation.MarkerFileName);
            byte[] original = File.ReadAllBytes(marker);
            Equal("ATIV-PROTECTION-1TO0-V1-RESERVED\n", Encoding.ASCII.GetString(original));
            Equal(1, Directory.GetFiles(local).Length);
            Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, reservation.TryClaim());
            Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, new WsabiWmiProtection1To0FileReservation(local).TryClaim());
            Check(original.SequenceEqual(File.ReadAllBytes(marker)), "a subsequent Protection1To0 claim modified its existing file");
            Check(typeof(WsabiWmiProtection1To0FileReservation).GetProperties(BindingFlags.Public | BindingFlags.Instance).Length == 0,
                "reservation exposed a path or diagnostic identity");
        }));

        AddAsync("Protection1To0 simultaneous independent objects grant exactly one claim and deny all other attempts", async () =>
        {
            string directory = Path.Combine(Path.GetTempPath(), "ATIV-protection-1to0-reservation-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            try
            {
                using (var start = new ManualResetEventSlim())
                {
                    var contenders = Enumerable.Range(0, 24).Select(index => Task.Run(() =>
                    {
                        if (!start.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("Synthetic Protection1To0 reservation gate was not released.");
                        return new WsabiWmiProtection1To0FileReservation(directory).TryClaim();
                    })).ToArray();
                    var all = Task.WhenAll(contenders);
                    try
                    {
                        start.Set(); await CooperativeAwait(all);
                        var statuses = await all;
                        Equal(1, statuses.Count(status => status == WsabiWmiOneShotReservationStatus.Claimed));
                        Equal(23, statuses.Count(status => status == WsabiWmiOneShotReservationStatus.AlreadyUsed));
                    }
                    finally { start.Set(); await CooperativeAwait(all); }
                }
                Equal(1, Directory.GetFiles(directory).Length);
                Equal("ATIV-PROTECTION-1TO0-V1-RESERVED\n", File.ReadAllText(
                    Path.Combine(directory, WsabiWmiProtection1To0FileReservation.MarkerFileName), Encoding.ASCII));
            }
            finally { Directory.Delete(directory, true); }
        });

        Add("Protection1To0 empty interrupted and corrupt marker files deny another claim without repair", () => WithDirectory(dir =>
        {
            var contents = new[] { new byte[0], new byte[] { 0, 255, 1, 19 }, Encoding.UTF8.GetBytes("arbitrary interrupted Protection1To0 bytes") };
            for (int index = 0; index < contents.Length; index++)
            {
                string local = Path.Combine(dir, "case-" + index); Directory.CreateDirectory(local);
                string marker = Path.Combine(local, WsabiWmiProtection1To0FileReservation.MarkerFileName);
                File.WriteAllBytes(marker, contents[index]);
                Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, new WsabiWmiProtection1To0FileReservation(local).TryClaim());
                Check(contents[index].SequenceEqual(File.ReadAllBytes(marker)), "previous Protection1To0 content was replaced or repaired");
                Equal(1, Directory.GetFiles(local).Length);
            }
        }));

        Add("Protection1To0 caller preparation failure leaves the durable attempt spent without rollback", () => WithDirectory(dir =>
        {
            var reservation = new WsabiWmiProtection1To0FileReservation(dir);
            Equal(WsabiWmiOneShotReservationStatus.Claimed, reservation.TryClaim());
            string marker = Path.Combine(dir, WsabiWmiProtection1To0FileReservation.MarkerFileName);
            byte[] original = File.ReadAllBytes(marker);
            BatteryThrows<InvalidOperationException>(() => { throw new InvalidOperationException("Synthetic preparation rejection."); });
            Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, reservation.TryClaim());
            Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, new WsabiWmiProtection1To0FileReservation(dir).TryClaim());
            Check(original.SequenceEqual(File.ReadAllBytes(marker)), "caller failure restored or changed a spent attempt");
            Equal(1, Directory.GetFiles(dir).Length);
        }));

        Add("Protection1To0 invalid relative remote and control-character directories cannot select a fallback", () => WithDirectory(dir =>
        {
            foreach (string invalid in new[]
            {
                null, "", " ", ".", "..", "relative-protection-1to0", "C:relative-protection-1to0", @"\root-relative-protection-1to0",
                @"\\server\share\Experiments", "//server/share/Experiments", "https://example.test/Experiments",
                Path.Combine(dir, "invalid\0root"), Path.Combine(dir, "invalid\nroot")
            }) Equal(WsabiWmiOneShotReservationStatus.Unavailable, new WsabiWmiProtection1To0FileReservation(invalid).TryClaim());
            Equal(0, Directory.GetFileSystemEntries(dir).Length);
        }));

        Add("Protection1To0 blocked parent or directory-shaped marker fails closed without modifying storage", () => WithDirectory(dir =>
        {
            string blocked = Path.Combine(dir, "blocked-parent"); File.WriteAllText(blocked, "preserve");
            Equal(WsabiWmiOneShotReservationStatus.Unavailable,
                new WsabiWmiProtection1To0FileReservation(Path.Combine(blocked, "Experiments")).TryClaim());
            Equal("preserve", File.ReadAllText(blocked));
            string local = Path.Combine(dir, "Experiments"); Directory.CreateDirectory(local);
            string marker = Path.Combine(local, WsabiWmiProtection1To0FileReservation.MarkerFileName);
            Directory.CreateDirectory(marker);
            Equal(WsabiWmiOneShotReservationStatus.Unavailable, new WsabiWmiProtection1To0FileReservation(local).TryClaim());
            Check(Directory.Exists(marker) && Directory.GetFileSystemEntries(marker).Length == 0, "blocked marker storage was replaced");
        }));

        Add("Protection1To0 locked existing marker stays used without another content access or overwrite", () => WithDirectory(dir =>
        {
            string marker = Path.Combine(dir, WsabiWmiProtection1To0FileReservation.MarkerFileName);
            byte[] previous = { 9, 8, 7, 6 }; File.WriteAllBytes(marker, previous);
            using (var exclusive = new FileStream(marker, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, new WsabiWmiProtection1To0FileReservation(dir).TryClaim());
            Check(previous.SequenceEqual(File.ReadAllBytes(marker)), "locked Protection1To0 marker was modified");
        }));

        Add("Protection1To0 file reparse markers are refused without modifying the linked target", () => WithDirectory(dir =>
        {
            string target = Path.Combine(dir, "untouched.data"); File.WriteAllText(target, "preserve");
            string local = Path.Combine(dir, "Experiments"); Directory.CreateDirectory(local);
            string marker = Path.Combine(local, WsabiWmiProtection1To0FileReservation.MarkerFileName);
            try { File.CreateSymbolicLink(marker, target); }
            catch (UnauthorizedAccessException) { throw new SkippedTestException("this account cannot create a symbolic link"); }
            catch (PlatformNotSupportedException) { throw new SkippedTestException("this platform cannot create a symbolic link"); }
            Equal(WsabiWmiOneShotReservationStatus.Unavailable, new WsabiWmiProtection1To0FileReservation(local).TryClaim());
            Equal("preserve", File.ReadAllText(target));
            Check((File.GetAttributes(marker) & FileAttributes.ReparsePoint) != 0, "reparse marker was replaced");
        }));

        Add("Protection1To0 reparse ancestors cannot redirect the fixed marker or create alternate storage", () => WithDirectory(dir =>
        {
            string target = Path.Combine(dir, "untouched-directory"); Directory.CreateDirectory(target);
            string link = Path.Combine(dir, "linked-parent");
            try { Directory.CreateSymbolicLink(link, target); }
            catch (UnauthorizedAccessException) { throw new SkippedTestException("this account cannot create a symbolic link"); }
            catch (PlatformNotSupportedException) { throw new SkippedTestException("this platform cannot create a symbolic link"); }
            Equal(WsabiWmiOneShotReservationStatus.Unavailable,
                new WsabiWmiProtection1To0FileReservation(Path.Combine(link, "nested", "Experiments")).TryClaim());
            Equal(0, Directory.GetFileSystemEntries(target).Length);
        }));
    }
}
