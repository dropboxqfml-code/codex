using System;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Name matching identifies candidates only; it does not prove ownership or device support.
    public static class SamsungKernelDriverPolicy
    {
        public const int MaximumNameCharacters = 256;

        public static SamsungDriverCategory? Classify(string name, string displayName)
        {
            if (!Bounded(name) || !Bounded(displayName)) return null;
            if (Contains(name, "sabi") || Contains(displayName, "sabi")) return SamsungDriverCategory.SabiName;
            if (Contains(name, "samsung") || Contains(displayName, "samsung")) return SamsungDriverCategory.SamsungName;
            return null;
        }

        public static SamsungDriverState NormalizeState(string value)
        {
            switch (value)
            {
                case "Stopped": return SamsungDriverState.Stopped;
                case "Start Pending": return SamsungDriverState.StartPending;
                case "Stop Pending": return SamsungDriverState.StopPending;
                case "Running": return SamsungDriverState.Running;
                case "Continue Pending": return SamsungDriverState.ContinuePending;
                case "Pause Pending": return SamsungDriverState.PausePending;
                case "Paused": return SamsungDriverState.Paused;
                default: return SamsungDriverState.Unknown;
            }
        }

        public static SamsungDriverStartMode NormalizeStartMode(string value)
        {
            switch (value)
            {
                case "Boot": return SamsungDriverStartMode.Boot;
                case "System": return SamsungDriverStartMode.System;
                case "Auto": return SamsungDriverStartMode.Auto;
                case "Manual": return SamsungDriverStartMode.Manual;
                case "Disabled": return SamsungDriverStartMode.Disabled;
                default: return SamsungDriverStartMode.Unknown;
            }
        }

        private static bool Bounded(string value) => value == null || value.Length <= MaximumNameCharacters;
        private static bool Contains(string value, string token) => value != null && value.IndexOf(token, StringComparison.OrdinalIgnoreCase) >= 0;
    }
}
