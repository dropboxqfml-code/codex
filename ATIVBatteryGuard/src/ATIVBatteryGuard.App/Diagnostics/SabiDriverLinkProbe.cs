using System;
using System.Runtime.InteropServices;
using System.Text;

namespace ATIVBatteryGuard.Diagnostics
{
    // Passive lookup of one DOS-device name. This does not open the device,
    // load Samsung code, send IOCTLs, or establish driver/firmware compatibility.
    internal static class SabiDriverLinkProbe
    {
        // Shared numeric contract: 0 NotChecked, 1 Present, 2 NotFound,
        // 3 AccessDenied, 4 Unavailable, 5 UnsupportedPlatform.
        internal static int CollectCode()
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) return 5;
            try
            {
                const int capacity = 4096;
                var target = new StringBuilder(capacity);
                uint count = QueryDosDeviceW("SABI", target, capacity);
                if (count == 0)
                {
                    int error = Marshal.GetLastWin32Error();
                    if (error == 2 || error == 3) return 2;
                    if (error == 5) return 3;
                    // Includes ERROR_INSUFFICIENT_BUFFER. Never enumerate other
                    // devices or widen the requested name to work around failure.
                    return 4;
                }
                if (count > capacity || target.Length == 0 || target.Length >= capacity) return 4;
                // The target mapping may contain device identifiers. Only this
                // status escapes; no target string is logged or serialized.
                return 1;
            }
            catch { return 4; }
        }

        [DllImport("kernel32.dll", ExactSpelling = true, CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern uint QueryDosDeviceW(string deviceName, StringBuilder targetPath, uint maximumCharacters);
    }
}
