using System;
using System.IO;
using System.Text;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Core.Storage
{
    // A durable, per-directory claim before the approved experiment can request
    // its single invocation. It stores no observation or identity and has no
    // reset, overwrite, content-recovery or temporary-directory fallback path.
    public sealed class WsabiWmiOneShotFileReservation : IWsabiWmiOneShotReservation
    {
        public const string MarkerFileName = "WmiQuery65-v1.attempt";
        private static readonly byte[] MarkerBytes = Encoding.ASCII.GetBytes("ATIV-WMI-QUERY65-V1-RESERVED\n");
        private readonly string directory;

        public WsabiWmiOneShotFileReservation(string directory)
        {
            this.directory = directory;
        }

        public WsabiWmiOneShotReservationStatus TryClaim()
        {
            string marker = null;
            bool created = false;
            try
            {
                // Never turn a missing application-data directory into a claim
                // in the current working directory or a temporary location.
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

                // CreateNew arbitrates independent processes atomically. Even
                // an empty or interrupted previous claim consumes the attempt.
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
                // Do not read, repair or delete an existing claim. A failed
                // flush also leaves its newly created marker in place.
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
