using System;
using System.Diagnostics;
using System.IO;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;

namespace ATIVBatteryGuard.Diagnostics
{
    public sealed class WindowsSamsungFileInspectionProvider : ISamsungFileInspectionProvider
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

        public SamsungFileInspectionReport Collect()
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) return Result(SamsungFileInspectionStatus.UnsupportedPlatform);
            Execution execution = null;
            try
            {
                lock (Gate)
                {
                    if (shuttingDown) return Result(SamsungFileInspectionStatus.Unavailable);
                    if (active != null)
                    {
                        if (!active.AwaitingExit || !active.Process.HasExited) return Result(SamsungFileInspectionStatus.TimedOut);
                        Cleanup(active); active = null;
                    }
                    string directory = LocalPathPolicy.NormalizeDirectory(SamsungFileInspectionWorker.OutputDirectory);
                    Directory.CreateDirectory(directory);
                    string output = Path.Combine(directory, "samsung-file-inspection-worker-" + Guid.NewGuid().ToString("N") + ".json");
                    LocalPathPolicy.EnsureNoReparsePoints(output);
                    string self = typeof(WindowsSamsungFileInspectionProvider).Assembly.Location;
                    if (!string.Equals(Path.GetFileName(self), "ATIVBatteryGuard.exe", StringComparison.OrdinalIgnoreCase)) return Result(SamsungFileInspectionStatus.Unavailable);
                    execution = new Execution
                    {
                        OutputPath = output,
                        Process = new Process { StartInfo = new ProcessStartInfo
                        {
                            FileName = self,
                            Arguments = SamsungFileInspectionWorker.Argument + " \"" + output + "\"",
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
                    return Result(SamsungFileInspectionStatus.TimedOut);
                }
                if (execution.Process.ExitCode != 0) return Result(SamsungFileInspectionStatus.Unavailable);
                LocalPathPolicy.EnsureNoReparsePoints(execution.OutputPath);
                using (var input = new FileStream(execution.OutputPath, FileMode.Open, FileAccess.Read, FileShare.Read))
                {
                    if (input.Length < 1 || input.Length > SamsungFileInspectionProtocol.MaximumBytes) return Result(SamsungFileInspectionStatus.InvalidResponse);
                    var bytes = new byte[(int)input.Length];
                    int position = 0;
                    while (position < bytes.Length)
                    {
                        int count = input.Read(bytes, position, bytes.Length - position);
                        if (count == 0) return Result(SamsungFileInspectionStatus.InvalidResponse);
                        position += count;
                    }
                    return SamsungFileInspectionProtocol.Decode(bytes);
                }
            }
            catch (UnauthorizedAccessException) { return Result(SamsungFileInspectionStatus.Unavailable); }
            catch { return Result(SamsungFileInspectionStatus.Unavailable); }
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

        private static SamsungFileInspectionReport Result(SamsungFileInspectionStatus status)
        {
            // A failed/terminated worker supplies no completed observations. Do not
            // turn missing IPC data into a successful empty driver enumeration.
            var queryStatus = status == SamsungFileInspectionStatus.TimedOut ? SamsungDriverQueryStatus.TimedOut
                : status == SamsungFileInspectionStatus.UnsupportedPlatform ? SamsungDriverQueryStatus.UnsupportedPlatform
                : status == SamsungFileInspectionStatus.InvalidResponse ? SamsungDriverQueryStatus.InvalidResponse
                : SamsungDriverQueryStatus.Unavailable;
            var link = status == SamsungFileInspectionStatus.UnsupportedPlatform
                ? SabiDriverLinkStatus.UnsupportedPlatform : SabiDriverLinkStatus.Unavailable;
            return new SamsungFileInspectionReport(status, driverLink: link,
                kernelDrivers: new SamsungKernelDriverReport(queryStatus));
        }
    }
}
