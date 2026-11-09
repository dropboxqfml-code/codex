using System;
using System.IO;
using System.Text;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Storage
{
    public enum ManualProtectionLeaseStatus { Claimed, Busy, Unavailable }

    // This is the manual application's own durable in-progress record, not a
    // trial reservation. Only this live owner may remove its own record after
    // actual cleanup AND an acknowledged result. Dispose/crash leaves it spent
    // and blocks another action; no recovery/reset/delete-old-record API exists.
    public sealed class ManualProtectionOperationLease : IDisposable
    {
        public const string Purpose = "ManualProtection-v1";
        public const string MarkerFileName = "active.operation";
        private readonly object gate = new object();
        private readonly string path;
        private readonly byte[] content;
        private FileStream stream;
        private bool released, disposed;

        private ManualProtectionOperationLease(string path, byte[] content, FileStream stream)
        { this.path = path; this.content = content; this.stream = stream; }

        public static ManualProtectionLeaseStatus TryClaim(ManualProtectionContext context,
            out ManualProtectionOperationLease lease)
        {
            lease = null;
            try
            {
                string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                if (!IsFullyQualifiedDirectory(local)) return ManualProtectionLeaseStatus.Unavailable;
                return Claim(Path.Combine(local, "ATIVBatteryGuard", "ManualProtectionV1"), context, out lease, null);
            }
            catch { return ManualProtectionLeaseStatus.Unavailable; }
        }

#if PORTABLE_TESTS
        internal static ManualProtectionLeaseStatus TryClaimAtDirectory(string directory,
            ManualProtectionContext context, out ManualProtectionOperationLease lease,
            Action<FileStream, byte[]> writeAndFlushForTests = null)
            => Claim(directory, context, out lease, writeAndFlushForTests);
#endif

        private static ManualProtectionLeaseStatus Claim(string directory, ManualProtectionContext context,
            out ManualProtectionOperationLease lease, Action<FileStream, byte[]> writeAndFlush)
        {
            lease = null;
            FileStream created = null;
            string marker = null;
            bool createAttempted = false;
            try
            {
                if (context == null || !IsFullyQualifiedDirectory(directory)) return ManualProtectionLeaseStatus.Unavailable;
                foreach (char value in directory) if (char.IsControl(value)) return ManualProtectionLeaseStatus.Unavailable;
                string local = LocalPathPolicy.NormalizeDirectory(directory);
                Directory.CreateDirectory(local);
                LocalPathPolicy.EnsureNoReparsePoints(local);
                marker = Path.Combine(local, MarkerFileName);
                LocalPathPolicy.EnsureNoReparsePoints(marker);
                if (File.Exists(marker)) return ManualProtectionLeaseStatus.Busy;
                if (Directory.Exists(marker)) return ManualProtectionLeaseStatus.Unavailable;
                byte[] bytes = Encoding.ASCII.GetBytes("ATIV-MANUAL-PROTECTION-V1\n" + context.JobId + "\n" + context.Operation + "\n");
                createAttempted = true;
                created = new FileStream(marker, FileMode.CreateNew, FileAccess.ReadWrite,
                    FileShare.None, 4096, FileOptions.WriteThrough);
#if PORTABLE_TESTS
                if (writeAndFlush != null) writeAndFlush(created, (byte[])bytes.Clone());
                else
#endif
                {
                    created.Write(bytes, 0, bytes.Length);
                    created.Flush(true);
                }
                lease = new ManualProtectionOperationLease(marker, bytes, created);
                created = null;
                return ManualProtectionLeaseStatus.Claimed;
            }
            catch (IOException)
            {
                // Once CreateNew succeeded, an uncertain flush is never a
                // lease. Keep that record without retry, truncation or repair.
                if (created == null && createAttempted && marker != null)
                {
                    try
                    {
                        LocalPathPolicy.EnsureNoReparsePoints(marker);
                        if (!Directory.Exists(marker) && File.Exists(marker)) return ManualProtectionLeaseStatus.Busy;
                    }
                    catch { }
                }
                return ManualProtectionLeaseStatus.Unavailable;
            }
            catch { return ManualProtectionLeaseStatus.Unavailable; }
            finally { try { if (created != null) created.Dispose(); } catch { } }
        }

        public bool CompleteAndRelease(bool actualCloseConfirmed, bool validAcknowledgment)
        {
            lock (gate)
            {
                if (released) return true;
                if (disposed || !actualCloseConfirmed || !validAcknowledgment || stream == null) return false;
                try
                {
                    LocalPathPolicy.EnsureNoReparsePoints(path);
                    // Check the still-exclusively-held original stream before
                    // close. Normal peer processes cannot replace this marker.
                    if (stream.Length != content.Length) return false;
                    stream.Position = 0;
                    var observed = new byte[content.Length];
                    int position = 0;
                    while (position < observed.Length)
                    {
                        int count = stream.Read(observed, position, observed.Length - position);
                        if (count == 0) return false;
                        position += count;
                    }
                    int difference = 0;
                    for (int i = 0; i < observed.Length; i++) difference |= observed[i] ^ content[i];
                    Array.Clear(observed, 0, observed.Length);
                    if (difference != 0) return false;
                    stream.Dispose(); stream = null;
                    LocalPathPolicy.EnsureNoReparsePoints(path);
                    // Recheck bounded owner content after close. Never remove
                    // a changed or replacement record, even at this path.
                    using (var check = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
                    {
                        if (check.Length != content.Length) return false;
                        for (int i = 0; i < content.Length; i++) if (check.ReadByte() != content[i]) return false;
                    }
                    File.Delete(path);
                    if (File.Exists(path) || Directory.Exists(path)) return false;
                    released = true; disposed = true;
                    return true;
                }
                catch { return false; }
            }
        }

        public void Dispose()
        {
            lock (gate)
            {
                if (disposed) return;
                disposed = true;
                try { if (stream != null) stream.Dispose(); } catch { }
                stream = null;
                // Intentional: unacknowledged or uncertain records remain.
            }
        }

        private static bool IsFullyQualifiedDirectory(string value)
        {
            if (string.IsNullOrWhiteSpace(value) || !Path.IsPathRooted(value)) return false;
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) return true;
            string root = Path.GetPathRoot(value);
            return root != null && root.Length == 3 && root[1] == ':' &&
                (root[2] == '\\' || root[2] == '/') && char.IsLetter(root[0]);
        }
    }
}
