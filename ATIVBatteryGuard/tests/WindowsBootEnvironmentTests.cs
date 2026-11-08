using System;
using System.Reflection;
using System.Runtime.InteropServices;
using ATIVBatteryGuard.Core.Hardware;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Diagnostics;

internal static partial class Program
{
    private static void RegisterWindowsBootEnvironmentTests()
    {
        Add("boot metadata defaults remain uncollected and undecided", () =>
        {
            var report = new WindowsBootEnvironmentReport();
            Equal(WindowsBootQueryStatus.NotCollected, report.Status);
            Equal(WindowsBootFirmwareType.Unknown, report.FirmwareType);
            Check(report.ToDisplayText().Contains("판정 보류"), "default inferred boot mode");
            Check(!report.HardwareWriteAllowed, "metadata enabled write");
        });
        Add("boot metadata distinguishes current BIOS UEFI and successful unknown", () =>
        {
            var bios = new WindowsBootEnvironmentReport(WindowsBootQueryStatus.Complete, WindowsBootFirmwareType.Bios);
            var uefi = new WindowsBootEnvironmentReport(WindowsBootQueryStatus.Complete, WindowsBootFirmwareType.Uefi);
            var unknown = new WindowsBootEnvironmentReport(WindowsBootQueryStatus.Complete);
            Check(bios.ToDisplayText().Contains("관측: BIOS") && bios.ToDisplayText().Contains("다른 펌웨어 호출자"), "BIOS scope missing");
            Check(uefi.ToDisplayText().Contains("관측: UEFI") && uefi.ToDisplayText().Contains("실제 proxy·cache"), "UEFI overclaims path");
            Equal(WindowsBootQueryStatus.Complete, unknown.Status);
            Equal(WindowsBootFirmwareType.Unknown, unknown.FirmwareType);
            Check(unknown.ToDisplayText().Contains("판정 보류"), "successful unknown inferred mode");
        });
        Add("boot report rejects invalid completed enums and discards failed output", () =>
        {
            var badStatus = new WindowsBootEnvironmentReport((WindowsBootQueryStatus)999, WindowsBootFirmwareType.Bios);
            var badType = new WindowsBootEnvironmentReport(WindowsBootQueryStatus.Complete, (WindowsBootFirmwareType)999);
            foreach (var report in new[] { badStatus, badType })
            {
                Equal(WindowsBootQueryStatus.InvalidResponse, report.Status);
                Equal(WindowsBootFirmwareType.Unknown, report.FirmwareType);
            }
            foreach (WindowsBootQueryStatus status in Enum.GetValues(typeof(WindowsBootQueryStatus)))
            {
                if (status == WindowsBootQueryStatus.Complete) continue;
                var report = new WindowsBootEnvironmentReport(status, WindowsBootFirmwareType.Uefi);
                Equal(status, report.Status); Equal(WindowsBootFirmwareType.Unknown, report.FirmwareType);
                Check(report.ToDisplayText().Contains("판정 보류"), "failed report inferred mode");
            }
        });
        Add("boot probe accepts only documented success values with one read each", () =>
        {
            for (uint value = 0; value <= 2; value++)
            {
                int calls = 0;
                uint captured = value;
                var report = WindowsBootEnvironmentProbe.Read(true, () =>
                {
                    calls++;
                    return new NativeBootFirmwareReading(true, captured, 5);
                });
                Equal(1, calls); Equal(WindowsBootQueryStatus.Complete, report.Status);
                Equal((WindowsBootFirmwareType)value, report.FirmwareType);
            }
        });
        Add("boot probe rejects success sentinel and unknown numeric values", () =>
        {
            foreach (uint value in new[] { 3u, uint.MaxValue })
            {
                int calls = 0;
                var report = WindowsBootEnvironmentProbe.Read(true, () => { calls++; return new NativeBootFirmwareReading(true, value); });
                Equal(1, calls); Equal(WindowsBootQueryStatus.InvalidResponse, report.Status);
                Equal(WindowsBootFirmwareType.Unknown, report.FirmwareType);
            }
        });
        Add("boot probe classifies failures once and never retains apparent output", () =>
        {
            foreach (int error in new[] { 5, 1, 50, 120, 127, 0, 87, -1 })
            {
                int calls = 0;
                var report = WindowsBootEnvironmentProbe.Read(true, () => { calls++; return new NativeBootFirmwareReading(false, 2, error); });
                var expected = error == 5 ? WindowsBootQueryStatus.AccessDenied :
                    error == 1 || error == 50 || error == 120 || error == 127
                        ? WindowsBootQueryStatus.ApiUnavailable : WindowsBootQueryStatus.Unavailable;
                Equal(1, calls); Equal(expected, report.Status);
                Equal(WindowsBootFirmwareType.Unknown, report.FirmwareType);
            }
        });
        Add("boot probe unsupported platform performs no native read", () =>
        {
            int calls = 0;
            var report = WindowsBootEnvironmentProbe.Read(false, () => { calls++; throw new InvalidOperationException("must not run"); });
            Equal(0, calls); Equal(WindowsBootQueryStatus.UnsupportedPlatform, report.Status);
            Equal(WindowsBootFirmwareType.Unknown, report.FirmwareType);
        });
        Add("boot probe missing APIs and private exception text remain sanitized", () =>
        {
            const string privateText = @"C:\Users\PrivatePerson\serial-ABC";
            foreach (Exception error in new Exception[]
                { new EntryPointNotFoundException(privateText), new DllNotFoundException(privateText), new InvalidOperationException(privateText) })
            {
                int calls = 0;
                var report = WindowsBootEnvironmentProbe.Read(true, () => { calls++; throw error; });
                Equal(1, calls);
                Equal(error is InvalidOperationException ? WindowsBootQueryStatus.Unavailable : WindowsBootQueryStatus.ApiUnavailable, report.Status);
                Equal(WindowsBootFirmwareType.Unknown, report.FirmwareType);
                string text = report.ToDisplayText();
                Check(!text.Contains("PrivatePerson") && !text.Contains("serial-ABC") && !text.Contains(@"C:\Users"), "exception detail leaked");
            }
            Equal(WindowsBootQueryStatus.Unavailable, WindowsBootEnvironmentProbe.Read(true, null).Status);
        });
        Add("boot classifications cannot enable charge access or hardware writes", () =>
        {
            foreach (WindowsBootQueryStatus status in Enum.GetValues(typeof(WindowsBootQueryStatus)))
            foreach (WindowsBootFirmwareType type in Enum.GetValues(typeof(WindowsBootFirmwareType)))
            {
                var report = new WindowsBootEnvironmentReport(status, type);
                Check(!report.HardwareWriteAllowed && report.ToDisplayText().Contains("실제 충전 제어: 미지원"), "boot mode became control support");
                var controller = new UnsupportedChargeLimitController();
                Check(!controller.GetCapabilities().CanRead && !controller.GetCapabilities().CanWrite, "metadata enabled capabilities");
                Check(!controller.SetMode(ChargeMode.Protection80).Success, "metadata enabled writes");
            }
        });
        Add("boot native declaration is the exact readonly standard API", () =>
        {
            var method = typeof(WindowsBootEnvironmentProbe).GetMethod("GetFirmwareType", BindingFlags.Static | BindingFlags.NonPublic);
            Check(method != null, "native declaration missing");
            var import = method.GetCustomAttribute<DllImportAttribute>();
            Check(import != null && import.Value == "kernel32.dll" && import.ExactSpelling && import.SetLastError, "native binding changed");
            Equal(typeof(bool), method.ReturnType);
            Equal(UnmanagedType.Bool, method.ReturnParameter.GetCustomAttribute<MarshalAsAttribute>().Value);
            var parameters = method.GetParameters();
            Equal(1, parameters.Length); Check(parameters[0].IsOut, "firmware output is not out");
            Equal(typeof(uint).MakeByRefType(), parameters[0].ParameterType);
        });
    }
}
