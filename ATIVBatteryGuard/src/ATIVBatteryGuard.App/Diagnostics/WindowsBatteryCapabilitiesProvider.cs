using System;
using System.Diagnostics;
using System.IO;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;

namespace ATIVBatteryGuard.Diagnostics
{
    public sealed class WindowsBatteryCapabilitiesProvider
    {
        private sealed class Execution
        {
            internal Process Process;
            internal string OutputPath;
            internal bool AwaitingExit;
        }
        private static readonly object Gate = new object();
        private static Execution active;
        private static bool shuttingDown;

        public WindowsBatteryCapabilitiesReport Collect()
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) return Result(BatteryProbeStatus.UnsupportedPlatform);
            Execution execution = null;
            try
            {
                lock (Gate)
                {
                    if (shuttingDown) return Result(BatteryProbeStatus.Unavailable);
                    if (active != null)
                    {
                        if (!active.AwaitingExit || !active.Process.HasExited) return Result(BatteryProbeStatus.TimedOut);
                        Cleanup(active); active = null;
                    }
                    string directory = LocalPathPolicy.NormalizeDirectory(BatteryCapabilitiesWorker.OutputDirectory);
                    Directory.CreateDirectory(directory);
                    string output = Path.Combine(directory, "battery-capabilities-worker-" + Guid.NewGuid().ToString("N") + ".json");
                    LocalPathPolicy.EnsureNoReparsePoints(output);
                    string self = typeof(WindowsBatteryCapabilitiesProvider).Assembly.Location;
                    if (!string.Equals(Path.GetFileName(self), "ATIVBatteryGuard.exe", StringComparison.OrdinalIgnoreCase)) return Result(BatteryProbeStatus.Unavailable);
                    execution = new Execution
                    {
                        OutputPath = output,
                        Process = new Process { StartInfo = new ProcessStartInfo
                        {
                            FileName = self,
                            Arguments = BatteryCapabilitiesWorker.Argument + " \"" + output + "\"",
                            UseShellExecute = false, CreateNoWindow = true,
                            WorkingDirectory = Path.GetDirectoryName(self)
                        }}
                    };
                    active = execution;
                    if (!execution.Process.Start()) throw new InvalidOperationException();
                }
                if (!execution.Process.WaitForExit(10000))
                {
                    TryStop(execution);
                    execution.Process.WaitForExit(1000);
                    return Result(BatteryProbeStatus.TimedOut);
                }
                if (execution.Process.ExitCode != 0) return Result(BatteryProbeStatus.Unavailable);
                LocalPathPolicy.EnsureNoReparsePoints(execution.OutputPath);
                using (var input = new FileStream(execution.OutputPath, FileMode.Open, FileAccess.Read, FileShare.Read))
                {
                    if (input.Length < 1 || input.Length > BatteryCapabilitiesProtocol.MaximumBytes) return Result(BatteryProbeStatus.InvalidResponse);
                    var bytes = new byte[(int)input.Length];
                    int position = 0;
                    while (position < bytes.Length)
                    {
                        int count = input.Read(bytes, position, bytes.Length - position);
                        if (count == 0) return Result(BatteryProbeStatus.InvalidResponse);
                        position += count;
                    }
                    return BatteryCapabilitiesProtocol.Decode(bytes);
                }
            }
            catch (UnauthorizedAccessException) { return Result(BatteryProbeStatus.AccessDenied); }
            catch { return Result(BatteryProbeStatus.Unavailable); }
            finally
            {
                if (execution != null)
                {
                    lock (Gate)
                    {
                        bool exited;
                        try { exited = execution.Process.HasExited; }
                        catch { exited = true; }
                        if (exited) { Cleanup(execution); if (ReferenceEquals(active, execution)) active = null; }
                        else execution.AwaitingExit = true;
                        // If termination is still pending, retain the slot so repeated
                        // requests cannot spawn more blocked worker processes.
                    }
                }
            }
        }

        public static void StopForShutdown()
        {
            lock (Gate)
            {
                shuttingDown = true;
                if (active != null) TryStop(active);
            }
        }

        private static void TryStop(Execution execution)
        {
            try { if (!execution.Process.HasExited) execution.Process.Kill(); } catch { }
        }

        private static void Cleanup(Execution execution)
        {
            try { LocalPathPolicy.EnsureNoReparsePoints(execution.OutputPath); File.Delete(execution.OutputPath); } catch { }
            try { execution.Process.Dispose(); } catch { }
        }

        private static WindowsBatteryCapabilitiesReport Result(BatteryProbeStatus status) => new WindowsBatteryCapabilitiesReport(status);
    }
}
