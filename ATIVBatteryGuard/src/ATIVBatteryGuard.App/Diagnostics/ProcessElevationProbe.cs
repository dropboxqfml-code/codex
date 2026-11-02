using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Diagnostics
{
    // Reads the current process token only; does not enable or request privileges.
    // The main GUI does not invoke this probe. No names, groups or SIDs are read.
    internal static class ProcessElevationProbe
    {
        private const uint TokenQuery = 0x0008;
        private const int TokenElevation = 20;

        internal static ProcessElevationState Read()
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) return ProcessElevationState.Unknown;
            try
            {
                SafeTokenHandle token;
                bool opened = OpenProcessToken(GetCurrentProcess(), TokenQuery, out token);
                using (token)
                {
                    if (!opened || token == null || token.IsInvalid) return ProcessElevationState.Unknown;
                    int elevation, returned;
                    if (!GetTokenInformation(token, TokenElevation, out elevation, sizeof(int), out returned) ||
                        returned != sizeof(int)) return ProcessElevationState.Unknown;
                    return elevation == 0 ? ProcessElevationState.NotElevated : ProcessElevationState.Elevated;
                }
            }
            catch { return ProcessElevationState.Unknown; }
        }

        private sealed class SafeTokenHandle : SafeHandleZeroOrMinusOneIsInvalid
        {
            private SafeTokenHandle() : base(true) { }
            protected override bool ReleaseHandle() => CloseHandle(handle);
        }

        [DllImport("kernel32.dll", ExactSpelling = true)]
        private static extern IntPtr GetCurrentProcess();

        [DllImport("advapi32.dll", ExactSpelling = true, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool OpenProcessToken(IntPtr process, uint desiredAccess, out SafeTokenHandle token);

        [DllImport("advapi32.dll", ExactSpelling = true, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool GetTokenInformation(SafeTokenHandle token, int informationClass,
            out int information, int informationLength, out int returnLength);

        [DllImport("kernel32.dll", ExactSpelling = true, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool CloseHandle(IntPtr handle);
    }
}
