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
    // Only fixed local property reads; no keys, paths, buffers or OEM calls.
    internal static class SamsungWmiInstanceProbe
    {
        private static readonly TimeSpan TotalBudget = TimeSpan.FromSeconds(4);
        private static readonly TimeSpan QueryTimeout = TimeSpan.FromSeconds(2);

        internal static SamsungWmiInstanceReport Collect()
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
                return SamsungWmiInstanceReport.Failure(SamsungWmiQueryStatus.UnsupportedPlatform);
            var elapsed = Stopwatch.StartNew();
            var version = ReadClass(SamsungWmiClass.Version, elapsed);
            var method = ReadClass(SamsungWmiClass.Method, elapsed);
            return new SamsungWmiInstanceReport(version, method);
        }

        private static SamsungWmiClassObservation ReadClass(SamsungWmiClass kind, Stopwatch elapsed)
        {
            TimeSpan remaining = TotalBudget - elapsed.Elapsed;
            if (remaining <= TimeSpan.Zero) return Result(kind, SamsungWmiQueryStatus.TimedOut);
            TimeSpan timeout = remaining < QueryTimeout ? remaining : QueryTimeout;
            try
            {
                var scope = new ManagementScope(@"\\.\" + SamsungWmiInstancePolicy.LocalNamespace,
                    new ConnectionOptions
                    {
                        Timeout = timeout, EnablePrivileges = false,
                        // Encrypted WMI/DCOM authentication can be required by a
                        // namespace. This keeps the caller's ordinary token and
                        // never repairs ACLs, enables privileges or retries weaker.
                        Authentication = AuthenticationLevel.PacketPrivacy,
                        Impersonation = ImpersonationLevel.Impersonate
                    });
                var entries = new List<SamsungWmiInstanceEntry>();
                bool partial = false;
                using (var searcher = new ManagementObjectSearcher(scope,
                    new ObjectQuery(SamsungWmiInstancePolicy.GetQuery(kind)), new EnumerationOptions
                    {
                        ReturnImmediately = true, Rewindable = false, BlockSize = 1, Timeout = timeout
                    }))
                using (var rows = searcher.Get())
                using (var iterator = rows.GetEnumerator())
                {
                    int visited = 0;
                    while (true)
                    {
                        // The worker additionally enforces its existing hard 10-second limit.
                        if (elapsed.Elapsed >= TotalBudget) return Result(kind, SamsungWmiQueryStatus.TimedOut);
                        bool available = iterator.MoveNext();
                        if (elapsed.Elapsed >= TotalBudget) return Result(kind, SamsungWmiQueryStatus.TimedOut);
                        if (!available) break;
                        using (var row = iterator.Current)
                        {
                            // One lookahead detects truncation; extra row values are not read.
                            if (++visited > SamsungWmiClassObservation.MaximumEntries) { partial = true; break; }
                            if (row == null) { partial = true; continue; }
                            bool? active = SamsungWmiInstancePolicy.NormalizeActive(ReadValue(row, "Active"));
                            uint? version = kind == SamsungWmiClass.Version
                                ? SamsungWmiInstancePolicy.NormalizeVersion(ReadValue(row, "version")) : null;
                            if (!active.HasValue || (kind == SamsungWmiClass.Version && !version.HasValue)) partial = true;
                            entries.Add(new SamsungWmiInstanceEntry(active, version));
                        }
                    }
                }
                return new SamsungWmiClassObservation(kind,
                    partial ? SamsungWmiQueryStatus.Partial : SamsungWmiQueryStatus.Complete, entries);
            }
            catch (ManagementException exception) { return Result(kind, Classify(exception.ErrorCode)); }
            catch (UnauthorizedAccessException) { return Result(kind, SamsungWmiQueryStatus.AccessDenied); }
            catch (SecurityException) { return Result(kind, SamsungWmiQueryStatus.AccessDenied); }
            catch (TimeoutException) { return Result(kind, SamsungWmiQueryStatus.TimedOut); }
            catch (COMException exception) { return Result(kind, ClassifyHResult(exception.ErrorCode)); }
            catch { return Result(kind, SamsungWmiQueryStatus.Unavailable); }
        }

        private static object ReadValue(ManagementBaseObject row, string property)
        {
            try { return row[property]; }
            catch (ManagementException exception) when (exception.ErrorCode == ManagementStatus.NotFound)
            {
                // Missing projected value is not missing class: keep unknown field/Partial.
                return null;
            }
        }

        private static SamsungWmiQueryStatus Classify(ManagementStatus status)
        {
            switch (status)
            {
                case ManagementStatus.InvalidClass:
                case ManagementStatus.NotFound: return SamsungWmiQueryStatus.ClassNotFound;
                case ManagementStatus.InvalidNamespace: return SamsungWmiQueryStatus.NamespaceNotFound;
                case ManagementStatus.AccessDenied: return SamsungWmiQueryStatus.AccessDenied;
                case ManagementStatus.Timedout: return SamsungWmiQueryStatus.TimedOut;
                default: return SamsungWmiQueryStatus.Unavailable;
            }
        }

        private static SamsungWmiQueryStatus ClassifyHResult(int code)
        {
            switch (unchecked((uint)code))
            {
                case 0x80041002:
                case 0x80041010: return SamsungWmiQueryStatus.ClassNotFound;
                case 0x8004100E: return SamsungWmiQueryStatus.NamespaceNotFound;
                case 0x80070005:
                case 0x80041003: return SamsungWmiQueryStatus.AccessDenied;
                case 0x80043001:
                case 0x800705B4: return SamsungWmiQueryStatus.TimedOut;
                default: return SamsungWmiQueryStatus.Unavailable;
            }
        }

        private static SamsungWmiClassObservation Result(SamsungWmiClass kind, SamsungWmiQueryStatus status) =>
            new SamsungWmiClassObservation(kind, status);
    }
}
