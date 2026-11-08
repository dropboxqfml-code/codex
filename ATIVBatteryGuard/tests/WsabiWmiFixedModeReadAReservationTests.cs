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
    // Every path below is a newly created temporary test directory. These
    // tests access only this purpose's new marker, never an existing experiment.
    private static void RegisterWsabiWmiFixedModeReadAReservationTests()
    {
        Add("fixed mode read A reservation durably claims one fixed marker and survives new instances", () => WithDirectory(dir =>
        {
            Equal("FixedModeReadA-v1.attempt", WsabiWmiFixedModeReadAFileReservation.MarkerFileName);
            string local = Path.Combine(dir, "ATIVBatteryGuard", "Experiments");
            IWsabiWmiOneShotReservation reservation = new WsabiWmiFixedModeReadAFileReservation(local);
            Equal(WsabiWmiOneShotReservationStatus.Claimed, reservation.TryClaim());
            string marker = Path.Combine(local, WsabiWmiFixedModeReadAFileReservation.MarkerFileName);
            byte[] previous = File.ReadAllBytes(marker);
            Equal("ATIV-FIXED-MODE-READ-A-V1-RESERVED\n", Encoding.ASCII.GetString(previous));
            Equal(1, Directory.GetFiles(local).Length);
            Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, reservation.TryClaim());
            Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, new WsabiWmiFixedModeReadAFileReservation(local).TryClaim());
            Check(previous.SequenceEqual(File.ReadAllBytes(marker)), "a subsequent claim changed the durable marker");
            Check(typeof(WsabiWmiFixedModeReadAFileReservation).GetProperties(BindingFlags.Public | BindingFlags.Instance).Length == 0,
                "reservation exposed an input path or diagnostic identity");
        }));

        AddAsync("fixed mode read A independent concurrent reservation objects grant exactly one durable claim", async () =>
        {
            string directory = Path.Combine(Path.GetTempPath(), "ATIV-read-A-reservation-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            try
            {
                using (var start = new ManualResetEventSlim())
                {
                    var contenders = Enumerable.Range(0, 24).Select(index => Task.Run(() =>
                    {
                        if (!start.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("Synthetic reservation gate was not released.");
                        return new WsabiWmiFixedModeReadAFileReservation(directory).TryClaim();
                    })).ToArray();
                    var all = Task.WhenAll(contenders);
                    try
                    {
                        start.Set(); await CooperativeAwait(all);
                        var results = await all;
                        Equal(1, results.Count(status => status == WsabiWmiOneShotReservationStatus.Claimed));
                        Equal(23, results.Count(status => status == WsabiWmiOneShotReservationStatus.AlreadyUsed));
                    }
                    finally { start.Set(); await CooperativeAwait(all); }
                }
                Equal(1, Directory.GetFiles(directory).Length);
                Equal("ATIV-FIXED-MODE-READ-A-V1-RESERVED\n",
                    File.ReadAllText(Path.Combine(directory, WsabiWmiFixedModeReadAFileReservation.MarkerFileName), Encoding.ASCII));
            }
            finally { Directory.Delete(directory, true); }
        });

        Add("fixed mode read A empty corrupt and arbitrary prior markers are used without content recovery", () => WithDirectory(dir =>
        {
            var cases = new[] { new byte[0], new byte[] { 0, 255, 17, 99 }, Encoding.UTF8.GetBytes("arbitrary interrupted bytes") };
            for (int index = 0; index < cases.Length; index++)
            {
                string local = Path.Combine(dir, "case-" + index); Directory.CreateDirectory(local);
                string marker = Path.Combine(local, WsabiWmiFixedModeReadAFileReservation.MarkerFileName);
                File.WriteAllBytes(marker, cases[index]);
                Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, new WsabiWmiFixedModeReadAFileReservation(local).TryClaim());
                Check(cases[index].SequenceEqual(File.ReadAllBytes(marker)), "existing marker bytes were repaired or replaced");
                Equal(1, Directory.GetFiles(local).Length);
            }
        }));

        Add("fixed mode read A invalid relative remote and control-character directories fail without a fallback", () => WithDirectory(dir =>
        {
            foreach (string invalid in new[]
            {
                null, "", " ", ".", "..", "relative-read-A", @"\\server\share\Experiments", "//server/share/Experiments",
                "https://example.test/Experiments", Path.Combine(dir, "invalid\0root"), Path.Combine(dir, "invalid\nroot")
            }) Equal(WsabiWmiOneShotReservationStatus.Unavailable, new WsabiWmiFixedModeReadAFileReservation(invalid).TryClaim());
            Equal(0, Directory.GetFileSystemEntries(dir).Length);
        }));

        Add("fixed mode read A unavailable parent and directory-shaped marker fail closed without replacing storage", () => WithDirectory(dir =>
        {
            string blocked = Path.Combine(dir, "blocked-parent"); File.WriteAllText(blocked, "preserve");
            Equal(WsabiWmiOneShotReservationStatus.Unavailable,
                new WsabiWmiFixedModeReadAFileReservation(Path.Combine(blocked, "Experiments")).TryClaim());
            Equal("preserve", File.ReadAllText(blocked));
            string local = Path.Combine(dir, "Experiments"); Directory.CreateDirectory(local);
            string marker = Path.Combine(local, WsabiWmiFixedModeReadAFileReservation.MarkerFileName);
            Directory.CreateDirectory(marker);
            Equal(WsabiWmiOneShotReservationStatus.Unavailable, new WsabiWmiFixedModeReadAFileReservation(local).TryClaim());
            Check(Directory.Exists(marker) && Directory.GetFileSystemEntries(marker).Length == 0,
                "unavailable marker storage was replaced or used as a fallback directory");
        }));

        Add("fixed mode read A locked existing marker remains used and is never overwritten", () => WithDirectory(dir =>
        {
            string marker = Path.Combine(dir, WsabiWmiFixedModeReadAFileReservation.MarkerFileName);
            byte[] previous = { 5, 4, 3, 2, 1 }; File.WriteAllBytes(marker, previous);
            using (var locked = new FileStream(marker, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, new WsabiWmiFixedModeReadAFileReservation(dir).TryClaim());
            Check(previous.SequenceEqual(File.ReadAllBytes(marker)), "locked previous marker was changed");
        }));

        Add("fixed mode read A refuses a file reparse marker without touching its target", () => WithDirectory(dir =>
        {
            string target = Path.Combine(dir, "untouched.data"); File.WriteAllText(target, "preserve");
            string local = Path.Combine(dir, "Experiments"); Directory.CreateDirectory(local);
            string marker = Path.Combine(local, WsabiWmiFixedModeReadAFileReservation.MarkerFileName);
            try { File.CreateSymbolicLink(marker, target); }
            catch (UnauthorizedAccessException) { throw new SkippedTestException("this account cannot create a symbolic link"); }
            catch (PlatformNotSupportedException) { throw new SkippedTestException("this platform cannot create a symbolic link"); }
            Equal(WsabiWmiOneShotReservationStatus.Unavailable, new WsabiWmiFixedModeReadAFileReservation(local).TryClaim());
            Equal("preserve", File.ReadAllText(target));
            Check((File.GetAttributes(marker) & FileAttributes.ReparsePoint) != 0, "reparse marker was replaced");
        }));

        Add("fixed mode read A refuses a reparse ancestor without creating an alternate purpose directory", () => WithDirectory(dir =>
        {
            string target = Path.Combine(dir, "untouched-directory"); Directory.CreateDirectory(target);
            string link = Path.Combine(dir, "linked-parent");
            try { Directory.CreateSymbolicLink(link, target); }
            catch (UnauthorizedAccessException) { throw new SkippedTestException("this account cannot create a symbolic link"); }
            catch (PlatformNotSupportedException) { throw new SkippedTestException("this platform cannot create a symbolic link"); }
            Equal(WsabiWmiOneShotReservationStatus.Unavailable,
                new WsabiWmiFixedModeReadAFileReservation(Path.Combine(link, "nested", "Experiments")).TryClaim());
            Equal(0, Directory.GetFileSystemEntries(target).Length);
        }));
    }
}
