using System;
using ATIVBatteryGuard.ExtendedValidation;

internal static partial class Program
{
    private static void RegisterExtendedValidationPolicyTests()
    {
        Add("extended validation permits only explicit quick or soak without arbitrary paths or commands", () =>
        {
            Check(!ExtendedPolicy.IsSoak(new[] { "--quick" }), "quick mode changed");
            Check(ExtendedPolicy.IsSoak(new[] { "--soak" }), "soak mode changed");
            foreach (var args in new[] { new string[0], new[] { "--soak", "elsewhere" }, new[] { "--helper" }, new[] { "--self-test" }, new[] { "--quick;run" } })
            {
                bool rejected = false; try { ExtendedPolicy.IsSoak(args); } catch (ArgumentException) { rejected = true; }
                Check(rejected, "unexpected argument accepted");
            }
        });
        Add("extended quick and soak require completed cycles and full duration without nonfinite times", () =>
        {
            Check(!ExtendedPolicy.RunComplete(false, 29, 500), "early quick pass");
            Check(ExtendedPolicy.RunComplete(false, 30, 0), "complete quick rejected");
            Check(!ExtendedPolicy.RunComplete(true, 30, 1199.99), "shortened soak pass");
            Check(!ExtendedPolicy.RunComplete(true, 29, 1200), "too few cycles pass");
            Check(ExtendedPolicy.RunComplete(true, 30, 1200), "complete soak rejected");
            foreach (double seconds in new[] { -1.0, double.NaN, double.PositiveInfinity, double.NegativeInfinity })
            {
                Check(!ExtendedPolicy.RunComplete(false, 30, seconds), "invalid time accepted");
                Check(!ExtendedPolicy.CycleGapAccepted(seconds), "invalid gap accepted");
            }
            Check(ExtendedPolicy.CycleGapAccepted(0) && ExtendedPolicy.CycleGapAccepted(30), "valid cycle gap rejected");
            Check(!ExtendedPolicy.CycleGapAccepted(30.001) && !ExtendedPolicy.CycleGapAccepted(1200), "suspended interval counted as active repetition");
        });
        Add("extended final outcome requires every file scenario binding duration and cleanup condition", () =>
        {
            Equal("automated-checks-passed-ime-and-release-pending", ExtendedPolicy.Outcome(false, true, true, true, true, 0, true));
            for (int disabled = 0; disabled < 5; disabled++)
                Equal("not-passed", ExtendedPolicy.Outcome(false, disabled != 0, disabled != 1, disabled != 2, disabled != 3, 0, disabled != 4));
            Equal("not-passed", ExtendedPolicy.Outcome(false, true, true, true, true, 1, true));
            Equal("stopped-not-passed", ExtendedPolicy.Outcome(true, true, true, true, true, 0, true));
        });
    }
}
