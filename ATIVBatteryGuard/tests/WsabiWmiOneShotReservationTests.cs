using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;

internal static partial class Program
{
    private static void RegisterWsabiWmiOneShotReservationTests()
    {
        Add("repaired preparation retains the original durable attempt across fresh experiment objects and transport outcomes", () => WithDirectory(dir =>
        {
            Equal("WmiQuery65-v1.attempt", WsabiWmiOneShotFileReservation.MarkerFileName);
            foreach (bool transportFault in new[] { false, true })
            {
                string local = Path.Combine(dir, transportFault ? "fault-case" : "reply-case");
                var failedPreparation = new OneShotExperimentBackend
                {
                    Preparer = () => new WsabiWmiOneShotPreflight(WsabiWmiMetadataStatus.Unavailable,
                        null, null, false, 0, null, false, WsabiWmiOneShotPreflightStage.MethodEnumeration)
                };
                var initial = new WsabiWmiOneShotExperiment(failedPreparation,
                    new WsabiWmiOneShotFileReservation(local)).RunAsync().GetAwaiter().GetResult();
                Equal(WsabiWmiOneShotStatus.PreflightFailed, initial.Status);
                Check(!initial.InvocationRequested && failedPreparation.Calls == 0,
                    "failed preparation dispatched a request");
                Check(!Directory.Exists(local), "failed preparation touched the reservation directory");

                var prepared = new OneShotExperimentBackend
                {
                    Handler = (request, token) =>
                    {
                        Check(WsabiWmiOneShotPolicy.IsApprovedRequest(request), "candidate request changed");
                        string marker = Path.Combine(local, WsabiWmiOneShotFileReservation.MarkerFileName);
                        Check(File.Exists(marker), "dispatch preceded its durable claim");
                        if (transportFault) throw new InvalidOperationException("synthetic transport failure");
                        return Task.FromResult(OneShotExperimentSnapshot(0));
                    }
                };
                var requested = new WsabiWmiOneShotExperiment(prepared,
                    new WsabiWmiOneShotFileReservation(local)).RunAsync().GetAwaiter().GetResult();
                Equal(transportFault ? WsabiWmiOneShotStatus.TransportFailure : WsabiWmiOneShotStatus.ResponseReceived,
                    requested.Status);
                Check(requested.InvocationRequested, "dispatch attempt was not recorded");
                Equal(1, prepared.Calls);
                OneShotExperimentAssertNoHardwareMeaning(requested);
                string claimPath = Path.Combine(local, WsabiWmiOneShotFileReservation.MarkerFileName);
                byte[] claim = File.ReadAllBytes(claimPath);

                var later = new OneShotExperimentBackend();
                var blocked = new WsabiWmiOneShotExperiment(later,
                    new WsabiWmiOneShotFileReservation(local)).RunAsync().GetAwaiter().GetResult();
                Equal(WsabiWmiOneShotStatus.ReservationAlreadyUsed, blocked.Status);
                Check(!blocked.InvocationRequested && later.Calls == 0,
                    "a fresh experiment bypassed the original attempt marker");
                Check(claim.SequenceEqual(File.ReadAllBytes(claimPath)), "original claim was modified");
                Equal(1, Directory.GetFiles(local).Length);
            }
        }));
        Add("one-shot file reservation durably records only the fixed claim and survives new instances", () => WithDirectory(dir =>
        {
            string local = Path.Combine(dir, "nested", "experiments");
            var reservation = new WsabiWmiOneShotFileReservation(local);
            Equal(WsabiWmiOneShotReservationStatus.Claimed, reservation.TryClaim());
            string marker = Path.Combine(local, WsabiWmiOneShotFileReservation.MarkerFileName);
            Equal("ATIV-WMI-QUERY65-V1-RESERVED\n", Encoding.ASCII.GetString(File.ReadAllBytes(marker)));
            Equal(1, Directory.GetFiles(local).Length);
            Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed, reservation.TryClaim());
            Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed,
                new WsabiWmiOneShotFileReservation(local).TryClaim());
            Equal("ATIV-WMI-QUERY65-V1-RESERVED\n", File.ReadAllText(marker, Encoding.ASCII));
        }));
        Add("one-shot file reservation grants exactly one claim across simultaneous independent objects", () => WithDirectory(dir =>
        {
            using (var start = new ManualResetEventSlim(false))
            {
                Task<WsabiWmiOneShotReservationStatus>[] contenders = Enumerable.Range(0, 24)
                    .Select(index => Task.Run(() =>
                    {
                        start.Wait();
                        return new WsabiWmiOneShotFileReservation(dir).TryClaim();
                    })).ToArray();
                start.Set();
                Task.WaitAll(contenders);
                Equal(1, contenders.Count(task => task.Result == WsabiWmiOneShotReservationStatus.Claimed));
                Equal(23, contenders.Count(task => task.Result == WsabiWmiOneShotReservationStatus.AlreadyUsed));
            }
            Equal("ATIV-WMI-QUERY65-V1-RESERVED\n",
                File.ReadAllText(Path.Combine(dir, WsabiWmiOneShotFileReservation.MarkerFileName), Encoding.ASCII));
        }));
        Add("one-shot file reservation refuses empty or arbitrary existing claims without recovery or overwrite", () => WithDirectory(dir =>
        {
            string marker = Path.Combine(dir, WsabiWmiOneShotFileReservation.MarkerFileName);
            foreach (byte[] previous in new[] { new byte[0], new byte[] { 0, 255, 17, 99 }, Encoding.UTF8.GetBytes("private previous bytes") })
            {
                File.WriteAllBytes(marker, previous);
                Equal(WsabiWmiOneShotReservationStatus.AlreadyUsed,
                    new WsabiWmiOneShotFileReservation(dir).TryClaim());
                Check(previous.SequenceEqual(File.ReadAllBytes(marker)), "existing attempt marker was read as permission or overwritten");
            }
        }));
        Add("one-shot file reservation fails closed for unavailable storage and invalid or remote roots", () => WithDirectory(dir =>
        {
            foreach (string invalid in new[] { null, "", " ", "relative-experiments", ".", "../experiments",
                @"\\server\share\experiments", "//server/share/experiments", "https://example.test/experiments",
                Path.Combine(dir, "invalid\0root"), Path.Combine(dir, "invalid\nroot") })
                Equal(WsabiWmiOneShotReservationStatus.Unavailable,
                    new WsabiWmiOneShotFileReservation(invalid).TryClaim());
            string blocked = Path.Combine(dir, "file-instead-of-parent");
            File.WriteAllText(blocked, "keep");
            Equal(WsabiWmiOneShotReservationStatus.Unavailable,
                new WsabiWmiOneShotFileReservation(Path.Combine(blocked, "experiments")).TryClaim());
            Equal("keep", File.ReadAllText(blocked));
            Directory.CreateDirectory(Path.Combine(dir, WsabiWmiOneShotFileReservation.MarkerFileName));
            Equal(WsabiWmiOneShotReservationStatus.Unavailable,
                new WsabiWmiOneShotFileReservation(dir).TryClaim());
        }));
        Add("one-shot file reservation cannot follow an existing file reparse point", () => WithDirectory(dir =>
        {
            string target = Path.Combine(dir, "untouched.data");
            string local = Path.Combine(dir, "experiments");
            Directory.CreateDirectory(local);
            File.WriteAllText(target, "keep");
            try { File.CreateSymbolicLink(Path.Combine(local, WsabiWmiOneShotFileReservation.MarkerFileName), target); }
            catch (UnauthorizedAccessException) { throw new SkippedTestException("this account cannot create a symbolic link"); }
            catch (PlatformNotSupportedException) { throw new SkippedTestException("this platform cannot create a symbolic link"); }
            Equal(WsabiWmiOneShotReservationStatus.Unavailable,
                new WsabiWmiOneShotFileReservation(local).TryClaim());
            Equal("keep", File.ReadAllText(target));
        }));
        Add("one-shot file reservation cannot redirect its fixed marker through a directory reparse point", () => WithDirectory(dir =>
        {
            string target = Path.Combine(dir, "untouched-directory");
            string link = Path.Combine(dir, "experiments");
            Directory.CreateDirectory(target);
            try { Directory.CreateSymbolicLink(link, target); }
            catch (UnauthorizedAccessException) { throw new SkippedTestException("this account cannot create a symbolic link"); }
            catch (PlatformNotSupportedException) { throw new SkippedTestException("this platform cannot create a symbolic link"); }
            Equal(WsabiWmiOneShotReservationStatus.Unavailable,
                new WsabiWmiOneShotFileReservation(link).TryClaim());
            Equal(0, Directory.GetFiles(target).Length);
        }));
    }
}
