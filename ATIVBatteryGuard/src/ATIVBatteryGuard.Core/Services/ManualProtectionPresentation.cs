using System.Globalization;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Presentation of an already accepted detached result only. These labels
    // neither validate hardware support nor establish electrical charging effect.
    public static class ManualProtectionPresentation
    {
        public static string GetStateLabel(ManualProtectionResult result)
        {
            if (result == null || !result.HasKnownMode) return "충전 제한 상태 미확인";
            if (result.ModeCandidate == 0) return "충전 제한 해제 · 일반 충전";
            if (result.UpperCandidate == 80 && result.LowerCandidate == 75) return "80% 충전 제한";

            // The wire contract permits byte candidates, including sentinel or
            // inverted values. Only an ordered percentage pair is a credible
            // threshold for a friendly percentage label; retain all raw values
            // in technical details and the explicit TXT export.
            if (result.UpperCandidate.HasValue && result.LowerCandidate.HasValue &&
                result.UpperCandidate.Value >= 1 && result.UpperCandidate.Value <= 100 &&
                result.LowerCandidate.Value >= 0 && result.LowerCandidate.Value < result.UpperCandidate.Value)
                return "충전 제한 켜짐 · 상한 " + result.UpperCandidate.Value.ToString(CultureInfo.InvariantCulture) + "%";

            return "충전 제한 켜짐 · 상한 미확인";
        }
    }
}
