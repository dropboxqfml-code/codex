using System;
using System.Linq;
using System.Reflection;
using ATIVBatteryGuard.Core.Models;

internal static partial class Program
{
    private static void RegisterManualProtectionModelTests()
    {
        Add("manual model fixes SDK read and setter budgets per closed operation", () =>
        {
            Equal(3, ManualProtectionLimits.MaximumSdkEntries(ManualProtectionOperation.ReadState));
            Equal(3, ManualProtectionLimits.MaximumReadCandidates(ManualProtectionOperation.ReadState));
            Equal(0, ManualProtectionLimits.MaximumSetterEntries(ManualProtectionOperation.ReadState));
            Equal(7, ManualProtectionLimits.MaximumSdkEntries(ManualProtectionOperation.Enable80));
            Equal(6, ManualProtectionLimits.MaximumReadCandidates(ManualProtectionOperation.Enable80));
            Equal(1, ManualProtectionLimits.MaximumSetterEntries(ManualProtectionOperation.Enable80));
            Equal(3, ManualProtectionLimits.MaximumSdkEntries(ManualProtectionOperation.DisableProtection));
            Equal(2, ManualProtectionLimits.MaximumReadCandidates(ManualProtectionOperation.DisableProtection));
            Equal(1, ManualProtectionLimits.MaximumSetterEntries(ManualProtectionOperation.DisableProtection));
            BatteryThrows<ArgumentOutOfRangeException>(() => ManualProtectionLimits.MaximumSdkEntries((ManualProtectionOperation)3));
            BatteryThrows<ArgumentOutOfRangeException>(() => ManualProtectionLimits.MaximumReadCandidates((ManualProtectionOperation)(-1)));
        });

        Add("manual state read accepts only three detached fields without implying an enabled threshold", () =>
        {
            foreach (int mode in new[] { 0, 1 })
            foreach (int upper in new[] { 0, 80, 255 })
            foreach (int lower in new[] { 0, 75, 255 })
            {
                var value = new ManualProtectionResult(ManualProtectionOperation.ReadState, ManualProtectionStatus.StateRead,
                    true, true, 3, 0, 3, mode, mode, upper, lower);
                Check(value.IsSuccess && value.HasKnownMode && !value.IsPending, "complete read not exposed");
                Equal((int?)upper, value.UpperCandidate); Equal((int?)lower, value.LowerCandidate);
                ManualModelNoAuthority(value);
            }
            BatteryThrows<ArgumentException>(() => new ManualProtectionResult(ManualProtectionOperation.ReadState,
                ManualProtectionStatus.StateRead, true, true, 3, 0, 3, 1, 0, 80, 75));
        });

        Add("manual enable and disable require their independent post readback and exact fixed counts", () =>
        {
            var enable = ManualModelEnable(); var disable = ManualModelDisable();
            Check(enable.IsSuccess && enable.HasKnownMode && disable.IsSuccess && disable.HasKnownMode, "complete transitions lost");
            Equal((int?)0, enable.PreModeCandidate); Equal((int?)1, enable.ModeCandidate);
            Equal((int?)80, enable.UpperCandidate); Equal((int?)75, enable.LowerCandidate);
            Equal((int?)1, disable.PreModeCandidate); Equal((int?)0, disable.ModeCandidate);
            Check(!disable.UpperCandidate.HasValue && !disable.LowerCandidate.HasValue, "disable invented threshold restoration");
            ManualModelNoAuthority(enable); ManualModelNoAuthority(disable);
        });

        Add("manual successful enable shape rejects changed pre post thresholds counters or operation", () =>
        {
            foreach (int variant in Enumerable.Range(0, 12))
            {
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(
                    variant == 0 ? ManualProtectionOperation.DisableProtection : ManualProtectionOperation.Enable80,
                    ManualProtectionStatus.ChangedCandidate, true, true,
                    variant == 1 ? 6 : 7, variant == 2 ? 0 : 1, variant == 3 ? 5 : 6,
                    variant == 4 ? (int?)1 : variant == 5 ? null : 0,
                    variant == 6 ? (int?)0 : variant == 7 ? null : 1,
                    variant == 8 ? (int?)79 : variant == 9 ? null : 80,
                    variant == 10 ? (int?)74 : variant == 11 ? null : 75));
            }
        });

        Add("manual successful disable shape rejects missing pre receipt count post and fabricated thresholds", () =>
        {
            foreach (int variant in Enumerable.Range(0, 9))
            {
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(ManualProtectionOperation.DisableProtection,
                    ManualProtectionStatus.ChangedCandidate, true, true,
                    variant == 0 ? 2 : 3, variant == 1 ? 0 : 1, variant == 2 ? 1 : 2,
                    variant == 3 ? (int?)0 : variant == 4 ? null : 1,
                    variant == 5 ? (int?)1 : variant == 6 ? null : 0,
                    variant == 7 ? (int?)80 : null, variant == 8 ? (int?)75 : null));
            }
        });

        Add("manual already desired result carries one fresh read and no threshold assumption or setting", () =>
        {
            foreach (var operation in new[] { ManualProtectionOperation.Enable80, ManualProtectionOperation.DisableProtection })
            {
                int expected = operation == ManualProtectionOperation.Enable80 ? 1 : 0;
                var result = new ManualProtectionResult(operation, ManualProtectionStatus.AlreadyDesiredCandidate,
                    true, true, 1, 0, 1, expected, expected);
                Check(result.IsSuccess && result.HasKnownMode, "fresh already-desired candidate lost");
                Check(!result.UpperCandidate.HasValue && !result.LowerCandidate.HasValue, "same mode invented thresholds");
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(operation, ManualProtectionStatus.AlreadyDesiredCandidate,
                    true, true, 1, 0, 1, expected, expected, 80, 75));
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(operation, ManualProtectionStatus.AlreadyDesiredCandidate,
                    true, true, 2, 0, 1, expected, expected));
            }
            BatteryThrows<ArgumentException>(() => new ManualProtectionResult(ManualProtectionOperation.ReadState,
                ManualProtectionStatus.AlreadyDesiredCandidate, true, true, 1, 0, 1, 1, 1));
        });

        Add("manual success cannot precede real cleanup or fixed profile validation", () =>
        {
            foreach (bool cleanup in new[] { false, true })
            foreach (bool profile in new[] { false, true })
            {
                if (cleanup && profile) continue;
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(ManualProtectionOperation.Enable80,
                    ManualProtectionStatus.ChangedCandidate, cleanup, profile, 7, 1, 6, 0, 1, 80, 75));
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(ManualProtectionOperation.ReadState,
                    ManualProtectionStatus.StateRead, cleanup, profile, 3, 0, 3, null, 1, 80, 75));
            }
        });

        Add("manual failed results clear current candidates and distinguish cleanup from uncertain setting effect", () =>
        {
            var pending = ManualProtectionResult.Failure(ManualProtectionOperation.Enable80, ManualProtectionStatus.Unknown);
            var closed = ManualProtectionResult.Failure(ManualProtectionOperation.Enable80, ManualProtectionStatus.Unknown, true, true, 4, 1, 3, 0);
            Check(pending.IsPending && pending.IsUncertain && !pending.HasKnownMode, "unconfirmed local result became closed");
            Check(!closed.IsPending && closed.IsUncertain && !closed.HasKnownMode, "actual close incorrectly confirmed setting state");
            Equal((int?)0, closed.PreModeCandidate);
            foreach (var status in new[] { ManualProtectionStatus.Rejected, ManualProtectionStatus.TimedOut, ManualProtectionStatus.Unknown })
            {
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(ManualProtectionOperation.Enable80,
                    status, true, true, 7, 1, 6, 0, 1));
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(ManualProtectionOperation.Enable80,
                    status, true, true, 7, 1, 6, 0, null, 80));
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(ManualProtectionOperation.Enable80,
                    status, true, true, 7, 1, 6, 0, null, null, 75));
            }
        });

        Add("manual no hardware statuses cannot hide counters profile claims or pending ownership", () =>
        {
            foreach (var status in new[] { ManualProtectionStatus.Cancelled, ManualProtectionStatus.Unsupported,
                ManualProtectionStatus.PreflightFailed, ManualProtectionStatus.Busy })
            {
                var result = ManualProtectionResult.Failure(ManualProtectionOperation.Enable80, status);
                Check(result.CleanupComplete && !result.ProfileValidated && !result.IsSuccess && !result.HasKnownMode, "no-entry status granted state");
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(ManualProtectionOperation.Enable80, status, false, false));
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(ManualProtectionOperation.Enable80, status, true, true));
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(ManualProtectionOperation.Enable80, status, true, false, 1));
            }
            BatteryThrows<ArgumentException>(() => ManualProtectionResult.Failure(ManualProtectionOperation.ReadState, ManualProtectionStatus.StateRead));
        });

        Add("manual candidates enums and counters reject out of range or impossible read setting combinations", () =>
        {
            BatteryThrows<ArgumentOutOfRangeException>(() => new ManualProtectionResult((ManualProtectionOperation)50, ManualProtectionStatus.Unknown, false, false));
            BatteryThrows<ArgumentOutOfRangeException>(() => new ManualProtectionResult(ManualProtectionOperation.ReadState, (ManualProtectionStatus)50, false, false));
            foreach (int value in new[] { -1, 2, 255 })
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(ManualProtectionOperation.Enable80,
                    ManualProtectionStatus.Rejected, true, true, 1, 0, 1, value));
            foreach (var operation in (ManualProtectionOperation[])Enum.GetValues(typeof(ManualProtectionOperation)))
            {
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(operation, ManualProtectionStatus.Unknown, false, false, -1));
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(operation, ManualProtectionStatus.Unknown, false, false,
                    ManualProtectionLimits.MaximumSdkEntries(operation) + 1));
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(operation, ManualProtectionStatus.Unknown, false, false, 1, 0, 2));
                BatteryThrows<ArgumentException>(() => new ManualProtectionResult(operation, ManualProtectionStatus.Unknown, false, false, 1, 1, 1));
            }
        });

        Add("manual context accepts only bounded lower hex and compares job operation and every nonce cell", () =>
        {
            var context = ManualModelContext(ManualProtectionOperation.ReadState);
            Check(context.Matches(new ManualProtectionContext(new string('a', 32), new string('b', 64), ManualProtectionOperation.ReadState)), "matching context lost");
            Check(!context.Matches(null), "null context matched");
            Check(!context.Matches(ManualModelContext(ManualProtectionOperation.Enable80)), "operation identity ignored");
            for (int i = 0; i < 64; i++)
            {
                var value = new string('b', 64).ToCharArray(); value[i] = 'c';
                Check(!context.Matches(new ManualProtectionContext(context.JobId, new string(value), context.Operation)), "nonce suffix ignored");
            }
            for (int i = 0; i < 32; i++)
            {
                var value = context.JobId.ToCharArray(); value[i] = 'c';
                Check(!context.Matches(new ManualProtectionContext(new string(value), context.Nonce, context.Operation)), "job suffix ignored");
            }
            foreach (string value in new[] { null, string.Empty, new string('a', 31), new string('a', 33), new string('A', 32), new string('g', 32), new string('a', 31) + "\n" })
                BatteryThrows<ArgumentException>(() => new ManualProtectionContext(value, context.Nonce, context.Operation));
            foreach (string value in new[] { null, new string('b', 63), new string('b', 65), new string('B', 64), new string('x', 64), new string('b', 63) + " " })
                BatteryThrows<ArgumentException>(() => new ManualProtectionContext(context.JobId, value, context.Operation));
        });

        Add("manual generated contexts are independent and local identifiers never appear in result display", () =>
        {
            var one = ManualProtectionContext.Create(ManualProtectionOperation.Enable80);
            var two = ManualProtectionContext.Create(ManualProtectionOperation.Enable80);
            Check(one.JobId.Length == 32 && one.Nonce.Length == 64 && !one.Matches(two), "local contexts reused");
            string success = ManualModelEnable().ToDisplayText(), unknown = ManualProtectionResult.Failure(one.Operation, ManualProtectionStatus.Unknown).ToDisplayText();
            Check(!success.Contains(one.JobId) && !success.Contains(one.Nonce) && !unknown.Contains(one.JobId) && !unknown.Contains(one.Nonce), "private correlation data entered user text");
            Check(unknown.Contains("실제 호출이0회였다는 보장이 아닙니다"), "zero counters were presented as no-call proof while pending");
            Check(ManualModelDisable().ToDisplayText().Contains("100% 충전 완료나 이전 임계값 복원을 뜻하지 않습니다"), "disable changed into full charge guarantee");
            Check(typeof(ManualProtectionResult).GetProperties().All(property => property.SetMethod == null), "result is mutable");
            Check(typeof(ManualProtectionContext).GetProperties().All(property => property.SetMethod == null), "context is mutable");
        });
    }

    private static ManualProtectionResult ManualModelEnable() => new ManualProtectionResult(ManualProtectionOperation.Enable80,
        ManualProtectionStatus.ChangedCandidate, true, true, 7, 1, 6, 0, 1, 80, 75);
    private static ManualProtectionResult ManualModelDisable() => new ManualProtectionResult(ManualProtectionOperation.DisableProtection,
        ManualProtectionStatus.ChangedCandidate, true, true, 3, 1, 2, 1, 0);
    private static ManualProtectionContext ManualModelContext(ManualProtectionOperation operation)
        => new ManualProtectionContext(new string('a', 32), new string('b', 64), operation);
    private static void ManualModelNoAuthority(ManualProtectionResult value)
        => Check(!value.CanInvokeMethods && !value.CanReadHardware && !value.CanWriteHardware && !value.IsChargeLimitConfirmed,
            "a detached numeric result became execution authority or electrical measurement");
}
