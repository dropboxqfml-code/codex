using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Diagnostics
{
    // Runs only in our finite worker process. The parent enforces a time limit.
    // Microsoft public SDK: shared/poclass.h. No OEM commands or SET IOCTLs.
    internal static class NativeBatteryCapabilitiesReader
    {
        private static readonly Guid BatteryInterface = new Guid("72631e54-78a4-11d0-bcf7-00aa00b7b32a");
        private static readonly IntPtr InvalidHandle = new IntPtr(-1);

        [StructLayout(LayoutKind.Sequential)]
        private struct InterfaceData
        {
            public uint Size;
            public Guid ClassGuid;
            public uint Flags;
            public IntPtr Reserved;
        }

        internal static WindowsBatteryCapabilitiesReport Collect()
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
                return new WindowsBatteryCapabilitiesReport(BatteryProbeStatus.UnsupportedPlatform);
            Guid guid = BatteryInterface;
            IntPtr list = SetupDiGetClassDevsW(ref guid, null, IntPtr.Zero, 0x12); // PRESENT | DEVICEINTERFACE
            if (list == InvalidHandle || list == IntPtr.Zero) return new WindowsBatteryCapabilitiesReport(Failure(Marshal.GetLastWin32Error()));
            var entries = new List<BatteryCapabilityEntry>();
            bool limited = false;
            try
            {
                for (uint index = 0; index < WindowsBatteryCapabilitiesReport.MaximumDevices; index++)
                {
                    var data = new InterfaceData { Size = (uint)Marshal.SizeOf(typeof(InterfaceData)) };
                    if (!SetupDiEnumDeviceInterfaces(list, IntPtr.Zero, ref guid, index, ref data))
                    {
                        int error = Marshal.GetLastWin32Error();
                        if (error != 259) entries.Add(new BatteryCapabilityEntry((int)index + 1, Failure(error)));
                        break;
                    }
                    entries.Add(ReadEntry(list, ref data, (int)index + 1));
                    if (index + 1 == WindowsBatteryCapabilitiesReport.MaximumDevices) limited = true;
                }
            }
            finally { SetupDiDestroyDeviceInfoList(list); }
            return new WindowsBatteryCapabilitiesReport(entries.Count == 0 ? BatteryProbeStatus.NoDevices : BatteryProbeStatus.Complete, entries, limited);
        }

        private static BatteryCapabilityEntry ReadEntry(IntPtr list, ref InterfaceData data, int index)
        {
            uint required;
            SetupDiGetDeviceInterfaceDetailW(list, ref data, IntPtr.Zero, 0, out required, IntPtr.Zero);
            if (Marshal.GetLastWin32Error() != 122 || required < 8 || required > 32768 || (required & 1) != 0)
                return new BatteryCapabilityEntry(index, BatteryProbeStatus.InvalidResponse);
            IntPtr detail = Marshal.AllocHGlobal((int)required);
            try
            {
                Marshal.Copy(new byte[(int)required], 0, detail, (int)required);
                Marshal.WriteInt32(detail, IntPtr.Size == 8 ? 8 : 6);
                uint returned;
                if (!SetupDiGetDeviceInterfaceDetailW(list, ref data, detail, required, out returned, IntPtr.Zero))
                    return new BatteryCapabilityEntry(index, Failure(Marshal.GetLastWin32Error()));
                if (returned < 8 || returned > required) return new BatteryCapabilityEntry(index, BatteryProbeStatus.InvalidResponse);
                // cbSize differs by architecture; DevicePath starts after DWORD.
                // Read only inside the allocated buffer, never an unbounded string.
                string path = Marshal.PtrToStringUni(IntPtr.Add(detail, 4), ((int)required - 4) / 2);
                int terminator = path.IndexOf('\0');
                if (terminator < 1) return new BatteryCapabilityEntry(index, BatteryProbeStatus.InvalidResponse);
                path = path.Substring(0, terminator);
                if (!path.StartsWith(@"\\?\", StringComparison.Ordinal) ||
                    !path.EndsWith("#{" + BatteryInterface + "}", StringComparison.OrdinalIgnoreCase))
                    return new BatteryCapabilityEntry(index, BatteryProbeStatus.InvalidResponse);
                using (SafeFileHandle battery = CreateFileW(path, 0x80000000, 3, IntPtr.Zero, 3, 0x80, IntPtr.Zero))
                {
                    if (battery.IsInvalid) return new BatteryCapabilityEntry(index, Failure(Marshal.GetLastWin32Error()));
                    var tagBytes = new byte[4];
                    uint bytes;
                    // Input wait = 0 ms. Tag is used transiently and never exported.
                    if (!Query(battery, ReadOnlyBatteryQuery.Tag, new byte[4], tagBytes, out bytes))
                        return new BatteryCapabilityEntry(index, Failure(Marshal.GetLastWin32Error()));
                    if (bytes != 4) return new BatteryCapabilityEntry(index, BatteryProbeStatus.InvalidResponse);
                    uint tag = ReadOnlyBatteryQueryPolicy.UInt32(tagBytes);
                    if (tag == 0) return new BatteryCapabilityEntry(index, BatteryProbeStatus.NoDevices);
                    var information = new byte[36];
                    if (!Query(battery, ReadOnlyBatteryQuery.Information, ReadOnlyBatteryQueryPolicy.InformationRequest(tag), information, out bytes))
                        return new BatteryCapabilityEntry(index, Failure(Marshal.GetLastWin32Error()));
                    uint flags;
                    return ReadOnlyBatteryQueryPolicy.TryCapabilities(information, bytes, out flags)
                        ? new BatteryCapabilityEntry(index, BatteryProbeStatus.Complete, flags)
                        : new BatteryCapabilityEntry(index, BatteryProbeStatus.InvalidResponse);
                }
            }
            finally { Marshal.FreeHGlobal(detail); }
        }

        private static bool Query(SafeFileHandle handle, ReadOnlyBatteryQuery query, byte[] input, byte[] output, out uint returned)
        {
            return DeviceIoControl(handle, ReadOnlyBatteryQueryPolicy.Code(query), input, (uint)input.Length,
                output, (uint)output.Length, out returned, IntPtr.Zero);
        }

        private static BatteryProbeStatus Failure(int code)
        {
            if (code == 5) return BatteryProbeStatus.AccessDenied;
            if (code == 2 || code == 433 || code == 1167) return BatteryProbeStatus.NoDevices;
            if (code == 1460) return BatteryProbeStatus.TimedOut;
            return BatteryProbeStatus.Unavailable;
        }

        [DllImport("setupapi.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
        private static extern IntPtr SetupDiGetClassDevsW(ref Guid guid, string enumerator, IntPtr parent, uint flags);
        [DllImport("setupapi.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool SetupDiEnumDeviceInterfaces(IntPtr list, IntPtr device, ref Guid guid, uint index, ref InterfaceData data);
        [DllImport("setupapi.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool SetupDiGetDeviceInterfaceDetailW(IntPtr list, ref InterfaceData data, IntPtr detail, uint size, out uint required, IntPtr device);
        [DllImport("setupapi.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool SetupDiDestroyDeviceInfoList(IntPtr list);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
        private static extern SafeFileHandle CreateFileW(string path, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);
        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool DeviceIoControl(SafeFileHandle file, uint code, byte[] input, uint inputLength,
            [Out] byte[] output, uint outputLength, out uint returned, IntPtr overlapped);
    }
}
