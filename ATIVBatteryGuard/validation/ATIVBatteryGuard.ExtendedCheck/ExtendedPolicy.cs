using System;

namespace ATIVBatteryGuard.ExtendedValidation
{
    // Pure decisions shared with portable regressions. Measurements are observations,
    // never an assertion that a finite stress run proves absence of memory leaks.
    public static class ExtendedPolicy
    {
        public const int QuickCycles = 30;
        public const int SoakMinutes = 20;
        public static bool IsIme(string[] args) => args != null && args.Length == 1 && args[0] == "--ime";
        public static bool IsSoak(string[] args)
        {
            if (args == null || args.Length != 1 || (args[0] != "--quick" && args[0] != "--soak"))
                throw new ArgumentException();
            return args[0] == "--soak";
        }
        public static bool RunComplete(bool soak, int cycles, double elapsedSeconds)
        {
            return cycles >= QuickCycles && !double.IsNaN(elapsedSeconds) && !double.IsInfinity(elapsedSeconds)
                && elapsedSeconds >= (soak ? SoakMinutes * 60 : 0);
        }
        public static bool CycleGapAccepted(double seconds)
        {
            return !double.IsNaN(seconds) && !double.IsInfinity(seconds) && seconds >= 0 && seconds <= 30;
        }
        public static string Outcome(bool stopped, bool filesBefore, bool filesAfter, bool scenariosPassed,
            bool runComplete, int bindingErrors, bool cleanupSucceeded)
        {
            if (stopped) return "stopped-not-passed";
            return filesBefore && filesAfter && scenariosPassed && runComplete && bindingErrors == 0 && cleanupSucceeded
                ? "automated-checks-passed-ime-and-release-pending" : "not-passed";
        }
    }
}
