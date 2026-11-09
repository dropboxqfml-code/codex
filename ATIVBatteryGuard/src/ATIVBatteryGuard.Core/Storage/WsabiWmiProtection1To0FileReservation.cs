using System;
using System.IO;
using System.Text;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Core.Storage
{
    // The separately approved Protection1To0-v1 purpose only. The host injects its fixed local
    // Experiments directory. There is no account, version or folder fallback,
    // marker-content read, recovery, overwrite, reset or deletion operation.
    public sealed class WsabiWmiProtection1To0FileReservation : IWsabiWmiOneShotReservation
    {
        public const string Purpose = "Protection1To0-v1";
        public const string MarkerFileName = "Protection1To0-v1.attempt";
        private static readonly byte[] MarkerBytes = Encoding.ASCII.GetBytes("ATIV-PROTECTION-1TO0-V1-RESERVED\n");
        private readonly string directory;
#if PORTABLE_TESTS
        private readonly Action<FileStream, byte[]> writeAndFlushForTests;
#endif

        public WsabiWmiProtection1To0FileReservation(string directory)
        {
            this.directory = directory;
        }

#if PORTABLE_TESTS
        // Offline fault injection only; absent from notebook assemblies.
        internal WsabiWmiProtection1To0FileReservation(string directory, Action<FileStream, byte[]> writeAndFlushForTests)
            : this(directory)
        { this.writeAndFlushForTests = writeAndFlushForTests; }
#endif

        public WsabiWmiOneShotReservationStatus TryClaim()
        {
            string marker = null;
            bool created = false;
            try
            {
                if (!IsFullyQualifiedDirectory(directory)) return WsabiWmiOneShotReservationStatus.Unavailable;
                foreach (char character in directory)
                    if (char.IsControl(character)) return WsabiWmiOneShotReservationStatus.Unavailable;

                string local = LocalPathPolicy.NormalizeDirectory(directory);
                Directory.CreateDirectory(local);
                LocalPathPolicy.EnsureNoReparsePoints(local);
                marker = Path.Combine(local, MarkerFileName);
                LocalPathPolicy.EnsureNoReparsePoints(marker);
                if (Directory.Exists(marker)) return WsabiWmiOneShotReservationStatus.Unavailable;
                if (File.Exists(marker)) return WsabiWmiOneShotReservationStatus.AlreadyUsed;

                // Only this fixed purpose is created. CreateNew arbitrates
                // separate objects/processes even when another claim has not
                // yet written its bytes. Empty interrupted files stay spent.
                using (var stream = new FileStream(marker, FileMode.CreateNew, FileAccess.Write,
                    FileShare.None, 4096, FileOptions.WriteThrough))
                {
                    created = true;
#if PORTABLE_TESTS
                    if (writeAndFlushForTests != null) writeAndFlushForTests(stream, (byte[])MarkerBytes.Clone());
                    else
#endif
                    {
                        stream.Write(MarkerBytes, 0, MarkerBytes.Length);
                        stream.Flush(true);
                    }
                }
                return WsabiWmiOneShotReservationStatus.Claimed;
            }
            catch (IOException)
            {
                // An uncertain write/flush/close never grants an invocation.
                // Leave any newly created file in place without another try.
                if (created) return WsabiWmiOneShotReservationStatus.Unavailable;
                try
                {
                    if (marker != null && File.Exists(marker))
                    {
                        LocalPathPolicy.EnsureNoReparsePoints(marker);
                        return WsabiWmiOneShotReservationStatus.AlreadyUsed;
                    }
                }
                catch { }
                return WsabiWmiOneShotReservationStatus.Unavailable;
            }
            catch
            {
                return WsabiWmiOneShotReservationStatus.Unavailable;
            }
        }

        private static bool IsFullyQualifiedDirectory(string value)
        {
            if (string.IsNullOrWhiteSpace(value) || !Path.IsPathRooted(value)) return false;
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) return true;
            // IsPathRooted alone also accepts drive-relative/root-relative
            // Windows paths. Neither may acquire a current-directory fallback.
            string root = Path.GetPathRoot(value);
            return root != null && root.Length == 3 && root[1] == ':' &&
                (root[2] == '\\' || root[2] == '/') &&
                ((root[0] >= 'A' && root[0] <= 'Z') || (root[0] >= 'a' && root[0] <= 'z'));
        }
    }
}
