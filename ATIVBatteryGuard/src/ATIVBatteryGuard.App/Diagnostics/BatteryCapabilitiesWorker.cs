using System;
using System.IO;
using System.Text.RegularExpressions;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;

namespace ATIVBatteryGuard.Diagnostics
{
    internal static class BatteryCapabilitiesWorker
    {
        internal const string Argument = "--read-only-battery-capabilities";
        internal static string OutputDirectory => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ATIVBatteryGuard");

        internal static int Run(string outputPath)
        {
            try
            {
                string directory = LocalPathPolicy.NormalizeDirectory(OutputDirectory);
                string full = Path.GetFullPath(outputPath);
                if (!string.Equals(Path.GetDirectoryName(full), directory, StringComparison.OrdinalIgnoreCase) ||
                    !Regex.IsMatch(Path.GetFileName(full), @"\Abattery-capabilities-worker-[a-f0-9]{32}\.json\z")) return 2;
                LocalPathPolicy.EnsureNoReparsePoints(full);
                Directory.CreateDirectory(directory);
                WindowsBatteryCapabilitiesReport report;
                try { report = NativeBatteryCapabilitiesReader.Collect(); }
                catch { report = new WindowsBatteryCapabilitiesReport(BatteryProbeStatus.Unavailable); }
                byte[] bytes = BatteryCapabilitiesProtocol.Encode(report);
                using (var output = new FileStream(full, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                {
                    output.Write(bytes, 0, bytes.Length);
                    output.Flush(true);
                }
                return 0;
            }
            catch { return 2; }
        }
    }
}
