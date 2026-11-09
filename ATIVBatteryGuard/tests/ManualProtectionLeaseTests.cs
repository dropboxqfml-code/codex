using System;
using System.Collections.Concurrent;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Storage;

internal static partial class Program
{
    private static void RegisterManualProtectionLeaseTests()
    {
        Add("manual operation lease creates only its new fixed active record and excludes nonce from disk", () => WithDirectory(dir =>
        {
            var context = ManualLeaseContext(); ManualProtectionOperationLease lease;
            Equal(ManualProtectionLeaseStatus.Claimed, ManualProtectionOperationLease.TryClaimAtDirectory(dir, context, out lease));
            ManualProtectionOperationLease blocked;
            Equal(ManualProtectionLeaseStatus.Busy, ManualProtectionOperationLease.TryClaimAtDirectory(dir, ManualLeaseContext(), out blocked));
            Check(blocked == null, "busy granted a second owner");
            lease.Dispose();
            string[] names = Directory.GetFiles(dir); Equal(1, names.Length);
            Equal(ManualProtectionOperationLease.MarkerFileName, Path.GetFileName(names[0]));
            string content = File.ReadAllText(names[0]);
            Check(content.Contains(context.JobId) && content.Contains(context.Operation.ToString()), "active owner was not recorded");
            Check(!content.Contains(context.Nonce) && !content.Contains(dir), "private wire token or path entered the active record");
        }));

        Add("manual operation lease requires actual close and matching acknowledgement before another explicit action", () => WithDirectory(dir =>
        {
            ManualProtectionOperationLease lease, blocked;
            Equal(ManualProtectionLeaseStatus.Claimed, ManualProtectionOperationLease.TryClaimAtDirectory(dir, ManualLeaseContext(), out lease));
            foreach (var flags in new[] { new[] { false, false }, new[] { true, false }, new[] { false, true } })
            {
                Check(!lease.CompleteAndRelease(flags[0], flags[1]), "missing close or acknowledgment released operation");
                Equal(ManualProtectionLeaseStatus.Busy, ManualProtectionOperationLease.TryClaimAtDirectory(dir, ManualLeaseContext(), out blocked));
            }
            Check(lease.CompleteAndRelease(true, true), "closed acknowledged operation stayed blocked");
            Check(lease.CompleteAndRelease(true, true), "completed owner is not idempotent");
            Check(!File.Exists(Path.Combine(dir, ManualProtectionOperationLease.MarkerFileName)), "normal owner record remained");
            ManualProtectionOperationLease next;
            Equal(ManualProtectionLeaseStatus.Claimed, ManualProtectionOperationLease.TryClaimAtDirectory(dir, ManualLeaseContext(), out next));
            next.Dispose(); lease.Dispose();
        }));

        Add("manual operation dispose and missing acknowledgment leave a durable block across new objects", () => WithDirectory(dir =>
        {
            ManualProtectionOperationLease first, next;
            Equal(ManualProtectionLeaseStatus.Claimed, ManualProtectionOperationLease.TryClaimAtDirectory(dir, ManualLeaseContext(), out first));
            first.Dispose(); first.Dispose();
            byte[] original = File.ReadAllBytes(Path.Combine(dir, ManualProtectionOperationLease.MarkerFileName));
            Check(!first.CompleteAndRelease(true, true), "disposed owner removed its uncertain record");
            Equal(ManualProtectionLeaseStatus.Busy, ManualProtectionOperationLease.TryClaimAtDirectory(dir, ManualLeaseContext(), out next));
            Check(original.SequenceEqual(File.ReadAllBytes(Path.Combine(dir, ManualProtectionOperationLease.MarkerFileName))), "new object repaired uncertain state");
        }));

        AddAsync("manual operation competing owners grant exactly one active lease", async () =>
        {
            string dir = Path.Combine(Path.GetTempPath(), "ATIV-manual-lease-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            var owners = new ConcurrentBag<ManualProtectionOperationLease>();
            try
            {
                var statuses = await Task.WhenAll(Enumerable.Range(0, 12).Select(index => Task.Run(() =>
                {
                    ManualProtectionOperationLease lease;
                    var status = ManualProtectionOperationLease.TryClaimAtDirectory(dir, ManualLeaseContext(), out lease);
                    if (lease != null) owners.Add(lease);
                    return status;
                })));
                Equal(1, statuses.Count(value => value == ManualProtectionLeaseStatus.Claimed));
                Equal(11, statuses.Count(value => value == ManualProtectionLeaseStatus.Busy));
                Equal(1, owners.Count);
                Check(owners.Single().CompleteAndRelease(true, true), "single normal owner could not finish");
            }
            finally { foreach (var owner in owners) owner.Dispose(); Directory.Delete(dir, true); }
        });

        Add("manual operation uncertain write and flush leave a block without granting an owner", () => WithDirectory(dir =>
        {
            for (int stage = 0; stage < 3; stage++)
            {
                string local = Path.Combine(dir, "uncertain-" + stage); int writes = 0;
                ManualProtectionOperationLease lease;
                Equal(ManualProtectionLeaseStatus.Unavailable, ManualProtectionOperationLease.TryClaimAtDirectory(local, ManualLeaseContext(), out lease,
                    (stream, bytes) =>
                    {
                        writes++;
                        if (stage != 0) stream.Write(bytes, 0, stage == 1 ? 1 : bytes.Length);
                        if (stage == 2) stream.Flush(true);
                        throw new IOException("PRIVATE-WRITE-FAILURE");
                    }));
                Equal(1, writes); Check(lease == null, "uncertain durable write granted admission");
                string marker = Path.Combine(local, ManualProtectionOperationLease.MarkerFileName);
                Check(File.Exists(marker), "failed write removed its pending block");
                byte[] content = File.ReadAllBytes(marker);
                Equal(ManualProtectionLeaseStatus.Busy, ManualProtectionOperationLease.TryClaimAtDirectory(local, ManualLeaseContext(), out lease));
                Check(content.SequenceEqual(File.ReadAllBytes(marker)), "failed write was reset or rewritten");
            }
        }));

        Add("manual operation empty corrupt and locked records are never read repaired or replaced", () => WithDirectory(dir =>
        {
            foreach (byte[] value in new[] { new byte[0], new byte[] { 0, 255, 19 }, Encoding.ASCII.GetBytes("old-user-owned-record") })
            {
                string local = Path.Combine(dir, Guid.NewGuid().ToString("N")); Directory.CreateDirectory(local);
                string path = Path.Combine(local, ManualProtectionOperationLease.MarkerFileName); File.WriteAllBytes(path, value);
                ManualProtectionOperationLease lease;
                using (var locked = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                    Equal(ManualProtectionLeaseStatus.Busy, ManualProtectionOperationLease.TryClaimAtDirectory(local, ManualLeaseContext(), out lease));
                Check(lease == null && value.SequenceEqual(File.ReadAllBytes(path)), "existing record was touched");
            }
        }));

        Add("manual operation invalid directories and null contexts have no fallback storage", () => WithDirectory(dir =>
        {
            ManualProtectionOperationLease lease;
            foreach (string invalid in new[] { null, "", " ", ".", "relative", "C:relative", @"\root-relative", @"\\server\share", "//server/share", "https://example.test", Path.Combine(dir, "invalid\nroot"), Path.Combine(dir, "invalid\0root") })
                Equal(ManualProtectionLeaseStatus.Unavailable, ManualProtectionOperationLease.TryClaimAtDirectory(invalid, ManualLeaseContext(), out lease));
            Equal(ManualProtectionLeaseStatus.Unavailable, ManualProtectionOperationLease.TryClaimAtDirectory(dir, null, out lease));
            Equal(0, Directory.GetFileSystemEntries(dir).Length);
        }));

        Add("manual operation lease preserves every historical purpose and unrelated file", () => WithDirectory(dir =>
        {
            string[] names = { "Protection0To1-v1.attempt", "Protection1To0-v1.attempt", "FixedReadA-v1.attempt", "FixedReadAccess1-v1.attempt", "Query65-v1.attempt", "user-observation.txt" };
            foreach (string name in names) File.WriteAllText(Path.Combine(dir, name), "preserve-" + name);
            ManualProtectionOperationLease lease;
            Equal(ManualProtectionLeaseStatus.Claimed, ManualProtectionOperationLease.TryClaimAtDirectory(dir, ManualLeaseContext(), out lease));
            Check(lease.CompleteAndRelease(true, true), "own new operation failed to release");
            Equal(names.Length, Directory.GetFiles(dir).Length);
            foreach (string name in names) Equal("preserve-" + name, File.ReadAllText(Path.Combine(dir, name)));
        }));

        Add("manual operation rejects directory marker blocked parent and linked target without modification", () => WithDirectory(dir =>
        {
            string local = Path.Combine(dir, "directory-marker"); Directory.CreateDirectory(local);
            Directory.CreateDirectory(Path.Combine(local, ManualProtectionOperationLease.MarkerFileName));
            ManualProtectionOperationLease lease;
            Equal(ManualProtectionLeaseStatus.Unavailable, ManualProtectionOperationLease.TryClaimAtDirectory(local, ManualLeaseContext(), out lease));
            string blocked = Path.Combine(dir, "file-parent"); File.WriteAllText(blocked, "keep");
            Equal(ManualProtectionLeaseStatus.Unavailable, ManualProtectionOperationLease.TryClaimAtDirectory(Path.Combine(blocked, "manual"), ManualLeaseContext(), out lease));
            Equal("keep", File.ReadAllText(blocked));
            string target = Path.Combine(dir, "linked-data"); File.WriteAllText(target, "untouched");
            string links = Path.Combine(dir, "linked-marker"); Directory.CreateDirectory(links);
            try { File.CreateSymbolicLink(Path.Combine(links, ManualProtectionOperationLease.MarkerFileName), target); }
            catch (UnauthorizedAccessException) { throw new SkippedTestException("this account cannot create a symbolic link"); }
            catch (PlatformNotSupportedException) { throw new SkippedTestException("this platform cannot create a symbolic link"); }
            Equal(ManualProtectionLeaseStatus.Unavailable, ManualProtectionOperationLease.TryClaimAtDirectory(links, ManualLeaseContext(), out lease));
            Equal("untouched", File.ReadAllText(target));
        }));
    }

    private static ManualProtectionContext ManualLeaseContext()
        => new ManualProtectionContext(Guid.NewGuid().ToString("N"), new string('a', 64), ManualProtectionOperation.ReadState);
}
