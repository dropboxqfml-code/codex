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
            => CollectWithAccessTrace().Observation;

        internal static SamsungWmiAccessProbeResult CollectWithAccessTrace()
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
                return new SamsungWmiAccessProbeResult(
                    SamsungWmiInstanceReport.Failure(SamsungWmiQueryStatus.UnsupportedPlatform),
                    new SamsungWmiAccessTrace(SamsungWmiClass.Version, SamsungWmiAccessStage.NotStarted, SamsungWmiAccessCode.None),
                    new SamsungWmiAccessTrace(SamsungWmiClass.Method, SamsungWmiAccessStage.NotStarted, SamsungWmiAccessCode.None));
            var elapsed = Stopwatch.StartNew();
            SamsungWmiAccessTrace versionTrace, methodTrace;
            var version = ReadClass(SamsungWmiClass.Version, elapsed, out versionTrace);
            var method = ReadClass(SamsungWmiClass.Method, elapsed, out methodTrace);
            return new SamsungWmiAccessProbeResult(new SamsungWmiInstanceReport(version, method), versionTrace, methodTrace);
        }

        private static SamsungWmiClassObservation ReadClass(SamsungWmiClass kind, Stopwatch elapsed,
            out SamsungWmiAccessTrace trace)
        {
            var stage = SamsungWmiAccessStage.NotStarted;
            trace = new SamsungWmiAccessTrace(kind, stage, SamsungWmiAccessCode.None);
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
                // An explicit local connection separates namespace access from
                // query/provider access. It does not invoke an OEM method.
                stage = SamsungWmiAccessStage.Connect;
                scope.Connect();
                if (elapsed.Elapsed >= TotalBudget)
                    return TracedResult(kind, SamsungWmiQueryStatus.TimedOut, stage, SamsungWmiAccessCode.None, out trace);
                remaining = TotalBudget - elapsed.Elapsed;
                timeout = remaining < QueryTimeout ? remaining : QueryTimeout;
                var entries = new List<SamsungWmiInstanceEntry>();
                bool partial = false;
                stage = SamsungWmiAccessStage.Query;
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
                        stage = SamsungWmiAccessStage.Enumerate;
                        if (elapsed.Elapsed >= TotalBudget)
                            return TracedResult(kind, SamsungWmiQueryStatus.TimedOut, stage, SamsungWmiAccessCode.None, out trace);
                        bool available = iterator.MoveNext();
                        if (elapsed.Elapsed >= TotalBudget)
                            return TracedResult(kind, SamsungWmiQueryStatus.TimedOut, stage, SamsungWmiAccessCode.None, out trace);
                        if (!available) break;
                        using (var row = iterator.Current)
                        {
                            // One lookahead detects truncation; extra row values are not read.
                            if (++visited > SamsungWmiClassObservation.MaximumEntries) { partial = true; break; }
                            if (row == null) { partial = true; continue; }
                            stage = SamsungWmiAccessStage.ReadProperties;
                            bool? active = SamsungWmiInstancePolicy.NormalizeActive(ReadValue(row, "Active"));
                            uint? version = kind == SamsungWmiClass.Version
                                ? SamsungWmiInstancePolicy.NormalizeVersion(ReadValue(row, "version")) : null;
                            if (!active.HasValue || (kind == SamsungWmiClass.Version && !version.HasValue)) partial = true;
                            entries.Add(new SamsungWmiInstanceEntry(active, version));
                        }
                    }
                }
                trace = new SamsungWmiAccessTrace(kind, SamsungWmiAccessStage.Completed, SamsungWmiAccessCode.None);
                return new SamsungWmiClassObservation(kind,
                    partial ? SamsungWmiQueryStatus.Partial : SamsungWmiQueryStatus.Complete, entries);
            }
            catch (ManagementException exception)
            {
                return TracedResult(kind, Classify(exception.ErrorCode), stage, ErrorCategory((int)exception.ErrorCode), out trace);
            }
            catch (UnauthorizedAccessException exception)
            {
                return TracedResult(kind, SamsungWmiQueryStatus.AccessDenied, stage, ErrorCategory(exception.HResult), out trace);
            }
            catch (SecurityException)
            {
                return TracedResult(kind, SamsungWmiQueryStatus.AccessDenied, stage, SamsungWmiAccessCode.Other, out trace);
            }
            catch (TimeoutException)
            {
                return TracedResult(kind, SamsungWmiQueryStatus.TimedOut, stage, SamsungWmiAccessCode.Other, out trace);
            }
            catch (COMException exception)
            {
                return TracedResult(kind, ClassifyHResult(exception.ErrorCode), stage, ErrorCategory(exception.ErrorCode), out trace);
            }
            catch
            {
                return TracedResult(kind, SamsungWmiQueryStatus.Unavailable, stage, SamsungWmiAccessCode.Other, out trace);
            }
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

        private static SamsungWmiClassObservation TracedResult(SamsungWmiClass kind, SamsungWmiQueryStatus status,
            SamsungWmiAccessStage stage, SamsungWmiAccessCode code, out SamsungWmiAccessTrace trace)
        {
            trace = new SamsungWmiAccessTrace(kind, stage, code);
            return Result(kind, status);
        }

        private static SamsungWmiAccessCode ErrorCategory(int code)
        {
            // Only fixed categories escape. Never retain raw HRESULT values,
            // extended WMI error objects, exception messages or provider data.
            switch (unchecked((uint)code))
            {
                case 0x80041003: return SamsungWmiAccessCode.WmiAccessDenied;
                case 0x80070005: return SamsungWmiAccessCode.WindowsAccessDenied;
                case 0x80041010: return SamsungWmiAccessCode.WmiClassNotFound;
                case 0x8004100E: return SamsungWmiAccessCode.WmiNamespaceNotFound;
                case 0x80041002: return SamsungWmiAccessCode.WmiNotFound;
                case 0x80043001: return SamsungWmiAccessCode.WmiTimedOut;
                case 0x800705B4: return SamsungWmiAccessCode.WindowsTimedOut;
                default: return SamsungWmiAccessCode.Other;
            }
        }
    }
}
