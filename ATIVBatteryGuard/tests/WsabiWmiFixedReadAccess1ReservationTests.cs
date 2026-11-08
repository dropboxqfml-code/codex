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
    // The new Access1 purpose is tested only in fresh temporary directories.
    // No real application-data directory or other reservation is inspected.
    private static void RegisterWsabiWmiFixedReadAccess1ReservationTests()
    {
        Add("Access1 reservation writes only its fixed durable purpose and refuses subsequent objects", () => WithDirectory(dir =>
        {
            Equal("FixedModeReadA-Access1.attempt", WsabiWmiFixedReadAccess1FileReservation.MarkerFileName);
            string local = Path.Combine(dir, "ATIVBatteryGuard", "Experiments");
            IWsabiWmiOneShotReservation reservation = new WsabiWmiFixedReadAccess1FileReservation(local);
            Equal(WsabiWmiOneShotReservationStatus.Claimed, reservation.TryClaim());
            string marker = Path.Combine(local, WsabiWmiFixedReadAccess1FileReservation.MarkerFileName);
            byte[] original = File.ReadAllBytes(marker);
            Equal("ATIV-FIXED-MODE-READ-A-ACCESS1-RESERVED\n", Encoding.ASCII.GetString(original));
            Equal(1, Directory.GetFiles(local).Length);
            Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, reservation.TryClaim());
            Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, new WsabiWmiFixedReadAccess1FileReservation(local).TryClaim());
            Check(original.SequenceEqual(File.ReadAllBytes(marker)), "a subsequent Access1 claim modified its existing file");
            Check(typeof(WsabiWmiFixedReadAccess1FileReservation).GetProperties(BindingFlags.Public | BindingFlags.Instance).Length == 0,
                "reservation exposed a path or diagnostic identity");
        }));

        AddAsync("Access1 simultaneous independent objects grant exactly one claim and deny all other attempts", async () =>
        {
            string directory = Path.Combine(Path.GetTempPath(), "ATIV-access1-reservation-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            try
            {
                using (var start = new ManualResetEventSlim())
                {
                    var contenders = Enumerable.Range(0, 24).Select(index => Task.Run(() =>
                    {
                        if (!start.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("Synthetic Access1 reservation gate was not released.");
                        return new WsabiWmiFixedReadAccess1FileReservation(directory).TryClaim();
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
                Equal("ATIV-FIXED-MODE-READ-A-ACCESS1-RESERVED\n", File.ReadAllText(
                    Path.Combine(directory, WsabiWmiFixedReadAccess1FileReservation.MarkerFileName), Encoding.ASCII));
            }
            finally { Directory.Delete(directory, true); }
        });

        Add("Access1 empty interrupted and corrupt marker files deny another claim without repair", () => WithDirectory(dir =>
        {
            var contents = new[] { new byte[0], new byte[] { 0, 255, 1, 19 }, Encoding.UTF8.GetBytes("arbitrary interrupted Access1 bytes") };
            for (int index = 0; index < contents.Length; index++)
            {
                string local = Path.Combine(dir, "case-" + index); Directory.CreateDirectory(local);
                string marker = Path.Combine(local, WsabiWmiFixedReadAccess1FileReservation.MarkerFileName);
                File.WriteAllBytes(marker, contents[index]);
                Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, new WsabiWmiFixedReadAccess1FileReservation(local).TryClaim());
                Check(contents[index].SequenceEqual(File.ReadAllBytes(marker)), "previous Access1 content was replaced or repaired");
                Equal(1, Directory.GetFiles(local).Length);
            }
        }));

        Add("Access1 caller preparation failure leaves the durable attempt spent without rollback", () => WithDirectory(dir =>
        {
            var reservation = new WsabiWmiFixedReadAccess1FileReservation(dir);
            Equal(WsabiWmiOneShotReservationStatus.Claimed, reservation.TryClaim());
            string marker = Path.Combine(dir, WsabiWmiFixedReadAccess1FileReservation.MarkerFileName);
            byte[] original = File.ReadAllBytes(marker);
            BatteryThrows<InvalidOperationException>(() => { throw new InvalidOperationException("Synthetic preparation rejection."); });
            Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, reservation.TryClaim());
            Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, new WsabiWmiFixedReadAccess1FileReservation(dir).TryClaim());
            Check(original.SequenceEqual(File.ReadAllBytes(marker)), "caller failure restored or changed a spent attempt");
            Equal(1, Directory.GetFiles(dir).Length);
        }));

        Add("Access1 invalid relative remote and control-character directories cannot select a fallback", () => WithDirectory(dir =>
        {
            foreach (string invalid in new[]
            {
                null, "", " ", ".", "..", "relative-access1", "C:relative-access1", @"\root-relative-access1",
                @"\\server\share\Experiments", "//server/share/Experiments", "https://example.test/Experiments",
                Path.Combine(dir, "invalid\0root"), Path.Combine(dir, "invalid\nroot")
            }) Equal(WsabiWmiOneShotReservationStatus.Unavailable, new WsabiWmiFixedReadAccess1FileReservation(invalid).TryClaim());
            Equal(0, Directory.GetFileSystemEntries(dir).Length);
        }));

        Add("Access1 blocked parent or directory-shaped marker fails closed without modifying storage", () => WithDirectory(dir =>
        {
            string blocked = Path.Combine(dir, "blocked-parent"); File.WriteAllText(blocked, "preserve");
            Equal(WsabiWmiOneShotReservationStatus.Unavailable,
                new WsabiWmiFixedReadAccess1FileReservation(Path.Combine(blocked, "Experiments")).TryClaim());
            Equal("preserve", File.ReadAllText(blocked));
            string local = Path.Combine(dir, "Experiments"); Directory.CreateDirectory(local);
            string marker = Path.Combine(local, WsabiWmiFixedReadAccess1FileReservation.MarkerFileName);
            Directory.CreateDirectory(marker);
            Equal(WsabiWmiOneShotReservationStatus.Unavailable, new WsabiWmiFixedReadAccess1FileReservation(local).TryClaim());
            Check(Directory.Exists(marker) && Directory.GetFileSystemEntries(marker).Length == 0, "blocked marker storage was replaced");
        }));

        Add("Access1 locked existing marker stays used without another content access or overwrite", () => WithDirectory(dir =>
        {
            string marker = Path.Combine(dir, WsabiWmiFixedReadAccess1FileReservation.MarkerFileName);
            byte[] previous = { 9, 8, 7, 6 }; File.WriteAllBytes(marker, previous);
            using (var exclusive = new FileStream(marker, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, new WsabiWmiFixedReadAccess1FileReservation(dir).TryClaim());
            Check(previous.SequenceEqual(File.ReadAllBytes(marker)), "locked Access1 marker was modified");
        }));

        Add("Access1 file reparse markers are refused without modifying the linked target", () => WithDirectory(dir =>
        {
            string target = Path.Combine(dir, "untouched.data"); File.WriteAllText(target, "preserve");
            string local = Path.Combine(dir, "Experiments"); Directory.CreateDirectory(local);
            string marker = Path.Combine(local, WsabiWmiFixedReadAccess1FileReservation.MarkerFileName);
            try { File.CreateSymbolicLink(marker, target); }
            catch (UnauthorizedAccessException) { throw new SkippedTestException("this account cannot create a symbolic link"); }
            catch (PlatformNotSupportedException) { throw new SkippedTestException("this platform cannot create a symbolic link"); }
            Equal(WsabiWmiOneShotReservationStatus.Unavailable, new WsabiWmiFixedReadAccess1FileReservation(local).TryClaim());
            Equal("preserve", File.ReadAllText(target));
            Check((File.GetAttributes(marker) & FileAttributes.ReparsePoint) != 0, "reparse marker was replaced");
        }));

        Add("Access1 reparse ancestors cannot redirect the fixed marker or create alternate storage", () => WithDirectory(dir =>
        {
            string target = Path.Combine(dir, "untouched-directory"); Directory.CreateDirectory(target);
            string link = Path.Combine(dir, "linked-parent");
            try { Directory.CreateSymbolicLink(link, target); }
            catch (UnauthorizedAccessException) { throw new SkippedTestException("this account cannot create a symbolic link"); }
            catch (PlatformNotSupportedException) { throw new SkippedTestException("this platform cannot create a symbolic link"); }
            Equal(WsabiWmiOneShotReservationStatus.Unavailable,
                new WsabiWmiFixedReadAccess1FileReservation(Path.Combine(link, "nested", "Experiments")).TryClaim());
            Equal(0, Directory.GetFileSystemEntries(target).Length);
        }));
    }
}
