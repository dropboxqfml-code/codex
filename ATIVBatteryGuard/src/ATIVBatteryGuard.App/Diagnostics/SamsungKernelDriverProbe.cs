using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Management;
using System.Runtime.InteropServices;
using System.Security;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Diagnostics
{
    // Passive Windows inventory, invoked only by the explicit file-inspection worker.
    // Never opens a driver, invokes a WMI method, loads Samsung code, or changes a service.
    internal static class SamsungKernelDriverProbe
    {
        private const int MaximumRows = 1024;
        private const int MaximumMatches = 32;
        private const int MaximumTextLength = 256;
        private const string Query = "SELECT Name, DisplayName, State, StartMode, ServiceType " +
            "FROM Win32_SystemDriver WHERE ServiceType = 'Kernel Driver'";

        internal static SamsungKernelDriverReport Collect()
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
                return Result(SamsungDriverQueryStatus.UnsupportedPlatform);
            try
            {
                var elapsed = Stopwatch.StartNew();
                var matches = new List<SamsungKernelDriverEntry>();
                bool partial = false;
                var scope = new ManagementScope(@"\\.\root\cimv2", new ConnectionOptions
                {
                    Timeout = TimeSpan.FromSeconds(2),
                    EnablePrivileges = false
                });
                using (var searcher = new ManagementObjectSearcher(scope, new ObjectQuery(Query),
                    new EnumerationOptions
                    {
                        ReturnImmediately = true,
                        Rewindable = false,
                        BlockSize = 1,
                        Timeout = TimeSpan.FromSeconds(2)
                    }))
                using (var rows = searcher.Get())
                using (var iterator = rows.GetEnumerator())
                {
                    int visited = 0;
                    while (true)
                    {
                        // This is a cooperative budget. The parent process also enforces
                        // a hard 10-second deadline if native WMI blocks despite its timeout.
                        if (elapsed.Elapsed >= TimeSpan.FromSeconds(3))
                            return Result(SamsungDriverQueryStatus.TimedOut);
                        bool available = iterator.MoveNext();
                        if (elapsed.Elapsed >= TimeSpan.FromSeconds(3))
                            return Result(SamsungDriverQueryStatus.TimedOut);
                        if (!available) break;
                        using (var row = iterator.Current)
                        {
                            if (++visited > MaximumRows) { partial = true; break; }
                            string name, displayName, state, startMode, serviceType;
                            if (row == null || !TryRead(row, "Name", out name, false) ||
                                !TryRead(row, "DisplayName", out displayName, true) ||
                                !TryRead(row, "State", out state, false) ||
                                !TryRead(row, "StartMode", out startMode, false) ||
                                !TryRead(row, "ServiceType", out serviceType, false) ||
                                !string.Equals(serviceType, "Kernel Driver", StringComparison.OrdinalIgnoreCase))
                            {
                                // An unreadable row might have matched. It must not become
                                // a successful empty inventory or an absence conclusion.
                                partial = true;
                                continue;
                            }
                            SamsungDriverCategory? category = SamsungKernelDriverPolicy.Classify(name, displayName);
                            if (!category.HasValue) continue;
                            if (matches.Count == MaximumMatches) { partial = true; break; }
                            matches.Add(new SamsungKernelDriverEntry(category.Value,
                                SamsungKernelDriverPolicy.NormalizeState(state),
                                SamsungKernelDriverPolicy.NormalizeStartMode(startMode)));
                        }
                    }
                }
                return new SamsungKernelDriverReport(partial ? SamsungDriverQueryStatus.Partial : SamsungDriverQueryStatus.Complete,
                    matches);
            }
            catch (ManagementException exception)
            {
                if (exception.ErrorCode == ManagementStatus.AccessDenied)
                    return Result(SamsungDriverQueryStatus.AccessDenied);
                if (exception.ErrorCode == ManagementStatus.Timedout)
                    return Result(SamsungDriverQueryStatus.TimedOut);
                return Result(SamsungDriverQueryStatus.Unavailable);
            }
            catch (UnauthorizedAccessException) { return Result(SamsungDriverQueryStatus.AccessDenied); }
            catch (SecurityException) { return Result(SamsungDriverQueryStatus.AccessDenied); }
            catch (TimeoutException) { return Result(SamsungDriverQueryStatus.TimedOut); }
            catch (COMException exception) { return Result(ClassifyHResult(exception.ErrorCode)); }
            catch { return Result(SamsungDriverQueryStatus.Unavailable); }
        }

        private static bool TryRead(ManagementBaseObject row, string property, out string value, bool allowEmpty)
        {
            // Only these projected fields are inspected; no PathName, account, device
            // identifier, registry value or arbitrary exception text is retained.
            object raw = row[property];
            value = raw as string;
            if (raw == null && allowEmpty) { value = string.Empty; return true; }
            return value != null && value.Length <= MaximumTextLength &&
                (allowEmpty || !string.IsNullOrWhiteSpace(value));
        }

        private static SamsungDriverQueryStatus ClassifyHResult(int code)
        {
            switch (unchecked((uint)code))
            {
                case 0x80070005:
                case 0x80041003: return SamsungDriverQueryStatus.AccessDenied;
                case 0x80043001:
                case 0x800705B4: return SamsungDriverQueryStatus.TimedOut;
                default: return SamsungDriverQueryStatus.Unavailable;
            }
        }

        private static SamsungKernelDriverReport Result(SamsungDriverQueryStatus status) =>
            new SamsungKernelDriverReport(status);
    }
}
