using System;
using System.Runtime.InteropServices;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Diagnostics
{
    // Calls only GetFirmwareType, once. No firmware-variable or OEM API access.
    internal static class WindowsBootEnvironmentProbe
    {
        internal static WindowsBootEnvironmentReport Collect()
        {
            return Read(Environment.OSVersion.Platform == PlatformID.Win32NT, ReadNative);
        }

        internal static WindowsBootEnvironmentReport Read(bool isWindows, Func<NativeBootFirmwareReading> read)
        {
            if (!isWindows)
                return new WindowsBootEnvironmentReport(WindowsBootQueryStatus.UnsupportedPlatform);
            if (read == null)
                return new WindowsBootEnvironmentReport(WindowsBootQueryStatus.Unavailable);
            try
            {
                NativeBootFirmwareReading native = read();
                if (native.Success)
                {
                    if (native.FirmwareType > (uint)WindowsBootFirmwareType.Uefi)
                        return new WindowsBootEnvironmentReport(WindowsBootQueryStatus.InvalidResponse);
                    return new WindowsBootEnvironmentReport(WindowsBootQueryStatus.Complete,
                        (WindowsBootFirmwareType)native.FirmwareType);
                }

                // A failure never preserves the output value, even if it looks valid.
                switch (native.ErrorCode)
                {
                    case 5:
                        return new WindowsBootEnvironmentReport(WindowsBootQueryStatus.AccessDenied);
                    case 1:
                    case 50:
                    case 120:
                    case 127:
                        return new WindowsBootEnvironmentReport(WindowsBootQueryStatus.ApiUnavailable);
                    default:
                        return new WindowsBootEnvironmentReport(WindowsBootQueryStatus.Unavailable);
                }
            }
            catch (EntryPointNotFoundException)
            {
                return new WindowsBootEnvironmentReport(WindowsBootQueryStatus.ApiUnavailable);
            }
            catch (DllNotFoundException)
            {
                return new WindowsBootEnvironmentReport(WindowsBootQueryStatus.ApiUnavailable);
            }
            catch
            {
                return new WindowsBootEnvironmentReport(WindowsBootQueryStatus.Unavailable);
            }
        }

        private static NativeBootFirmwareReading ReadNative()
        {
            uint firmwareType;
            bool success = GetFirmwareType(out firmwareType);
            int errorCode = success ? 0 : Marshal.GetLastWin32Error();
            return new NativeBootFirmwareReading(success, firmwareType, errorCode);
        }

        [DllImport("kernel32.dll", ExactSpelling = true, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool GetFirmwareType(out uint firmwareType);
    }

    // Raw native result is transient and never retained by a public report.
    internal struct NativeBootFirmwareReading
    {
        internal bool Success { get; }
        internal uint FirmwareType { get; }
        internal int ErrorCode { get; }

        internal NativeBootFirmwareReading(bool success, uint firmwareType, int errorCode = 0)
        {
            Success = success;
            FirmwareType = firmwareType;
            ErrorCode = errorCode;
        }
    }
}
