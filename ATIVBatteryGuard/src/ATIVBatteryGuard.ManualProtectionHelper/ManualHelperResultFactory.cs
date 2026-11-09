using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.ManualProtectionHelper
{
    // Detached result normalization only, called after actual SDK/target join.
    // It grants no execution authority and never clamps counters or candidates.
    internal static class ManualHelperResultFactory
    {
        internal static ManualProtectionResult FromCompleted(ManualProtectionOperation operation,
            ManualProtectionStatus status, int sdkEntries, int setterEntries, int readCandidates,
            int? preMode, int? mode, int? upper, int? lower)
        {
            if (status == ManualProtectionStatus.Cancelled || status == ManualProtectionStatus.Busy ||
                status == ManualProtectionStatus.Unsupported || status == ManualProtectionStatus.PreflightFailed)
            {
                if (sdkEntries == 0 && setterEntries == 0 && readCandidates == 0 && !preMode.HasValue)
                    return ManualProtectionResult.Failure(operation, status);
                // A stopped entered operation is not an untouched request.
                // Its known actual close can be reported without pretending
                // the setting was not executed or retaining the process forever.
                status = ManualProtectionStatus.Unknown;
            }
            bool success = status == ManualProtectionStatus.StateRead || status == ManualProtectionStatus.ChangedCandidate ||
                status == ManualProtectionStatus.AlreadyDesiredCandidate;
            return new ManualProtectionResult(operation, status, true, true, sdkEntries, setterEntries,
                readCandidates, preMode, success ? mode : null, success ? upper : null, success ? lower : null);
        }
    }
}
