using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Core.Models
{
	public sealed class NativePowerReading
	{
		public bool Success { get; private set; }

		public byte? AcLineStatus { get; private set; }

		public byte? BatteryFlag { get; private set; }

		public byte? BatteryLifePercent { get; private set; }

		public int? Win32Error { get; private set; }

		public string Error { get; private set; }

		public NativePowerReading(bool success, byte? acLineStatus = null, byte? batteryFlag = null, byte? batteryLifePercent = null, int? win32Error = null, string error = null)
		{
			Success = success;
			AcLineStatus = acLineStatus;
			BatteryFlag = batteryFlag;
			BatteryLifePercent = batteryLifePercent;
			Win32Error = win32Error;
			Error = error ?? string.Empty;
		}

		public BatterySnapshot ToSnapshot()
		{
			if (!Success)
			{
				return BatterySnapshot.Unknown(string.IsNullOrEmpty(Error) ? "Windows 배터리 상태 조회에 실패했습니다." : Error);
			}
			if (!AcLineStatus.HasValue || !BatteryFlag.HasValue || !BatteryLifePercent.HasValue)
			{
				return BatterySnapshot.Unknown("Windows 배터리 API의 필수 값이 제공되지 않았습니다.");
			}
			return PowerStatusDecoder.Decode(AcLineStatus.Value, BatteryFlag.Value, BatteryLifePercent.Value);
		}
	}
}
