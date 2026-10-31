using System;
using System.Runtime.InteropServices;
using System.Security;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Services
{
	public sealed class WindowsBatteryStatusProvider : IBatteryStatusProvider
	{
		private struct SystemPowerStatus
		{
			public byte AcLineStatus;

			public byte BatteryFlag;

			public byte BatteryLifePercent;

			public byte SystemStatusFlag;

			public uint BatteryLifeTime;

			public uint BatteryFullLifeTime;
		}

		[DllImport("kernel32.dll", SetLastError = true)]
		[return: MarshalAs(UnmanagedType.Bool)]
		private static extern bool GetSystemPowerStatus(out SystemPowerStatus status);

		public BatterySnapshot Read()
		{
			return ReadRaw().ToSnapshot();
		}

		public NativePowerReading ReadRaw()
		{
			if (Environment.OSVersion.Platform != PlatformID.Win32NT)
			{
				return new NativePowerReading(success: false, null, null, null, null, "Windows 배터리 API는 Windows에서만 사용할 수 있습니다.");
			}
			try
			{
				if (!GetSystemPowerStatus(out var status))
				{
					int lastWin32Error = Marshal.GetLastWin32Error();
					int? win32Error = lastWin32Error;
					string error = "Windows 배터리 상태 조회 실패 (오류 코드 " + lastWin32Error + ").";
					return new NativePowerReading(success: false, null, null, null, win32Error, error);
				}
				return new NativePowerReading(success: true, status.AcLineStatus, status.BatteryFlag, status.BatteryLifePercent);
			}
			catch (DllNotFoundException)
			{
				return new NativePowerReading(success: false, null, null, null, null, "Windows 배터리 API를 찾을 수 없습니다.");
			}
			catch (EntryPointNotFoundException)
			{
				return new NativePowerReading(success: false, null, null, null, null, "Windows 배터리 API 진입점을 찾을 수 없습니다.");
			}
			catch (BadImageFormatException)
			{
				return new NativePowerReading(success: false, null, null, null, null, "Windows 배터리 API 아키텍처가 호환되지 않습니다.");
			}
			catch (SecurityException)
			{
				return new NativePowerReading(success: false, null, null, null, null, "Windows 배터리 상태 조회 권한이 없습니다.");
			}
		}
	}
}
