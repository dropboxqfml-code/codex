using System;
using System.IO;
using System.Text;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Core.Storage
{
    // FixedModeReadA-v1 only. The host supplies its one fixed per-user
    // Experiments directory; this class selects no account, folder or version
    // fallback and provides no reset, overwrite, repair or marker-content read.
    public sealed class WsabiWmiFixedModeReadAFileReservation : IWsabiWmiOneShotReservation
    {
        public const string MarkerFileName = "FixedModeReadA-v1.attempt";
        private static readonly byte[] MarkerBytes = Encoding.ASCII.GetBytes("ATIV-FIXED-MODE-READ-A-V1-RESERVED\n");
        private readonly string directory;

        public WsabiWmiFixedModeReadAFileReservation(string directory)
        {
            this.directory = directory;
        }

        public WsabiWmiOneShotReservationStatus TryClaim()
        {
            string marker = null;
            bool created = false;
            try
            {
                if (string.IsNullOrWhiteSpace(directory) || !Path.IsPathRooted(directory))
                    return WsabiWmiOneShotReservationStatus.Unavailable;
                foreach (char character in directory)
                    if (char.IsControl(character)) return WsabiWmiOneShotReservationStatus.Unavailable;

                string local = LocalPathPolicy.NormalizeDirectory(directory);
                Directory.CreateDirectory(local);
                LocalPathPolicy.EnsureNoReparsePoints(local);
                marker = Path.Combine(local, MarkerFileName);
                LocalPathPolicy.EnsureNoReparsePoints(marker);
                if (Directory.Exists(marker)) return WsabiWmiOneShotReservationStatus.Unavailable;
                if (File.Exists(marker)) return WsabiWmiOneShotReservationStatus.AlreadyUsed;

                // CreateNew arbitrates the same purpose across objects and
                // processes. Any previous file, including an interrupted empty
                // claim, blocks another attempt without inspecting its bytes.
                using (var stream = new FileStream(marker, FileMode.CreateNew, FileAccess.Write,
                    FileShare.None, 4096, FileOptions.WriteThrough))
                {
                    created = true;
                    stream.Write(MarkerBytes, 0, MarkerBytes.Length);
                    stream.Flush(true);
                }
                return WsabiWmiOneShotReservationStatus.Claimed;
            }
            catch (IOException)
            {
                // A write/flush/close failure is uncertain and never grants
                // dispatch. Preserve any newly created file; do not retry.
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
    }
}
