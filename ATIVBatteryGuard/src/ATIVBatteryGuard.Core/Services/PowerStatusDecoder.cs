using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
	public static class PowerStatusDecoder
	{
		public static BatterySnapshot Decode(byte ac, byte flags, byte percent)
		{
			int num;
			switch (ac)
			{
			default:
				num = 0;
				break;
			case 0:
				num = 2;
				break;
			case 1:
				num = 1;
				break;
			}
			ExternalPowerStatus externalPowerStatus = (ExternalPowerStatus)num;
			int? percent2 = ((percent <= 100) ? new int?(percent) : ((int?)null));
			if (flags == byte.MaxValue)
			{
				return new BatterySnapshot(percent2, externalPowerStatus, BatteryChargeState.Unknown, "배터리 충전 상태가 제공되지 않았습니다.");
			}
			if ((flags & 0x80) != 0)
			{
				return new BatterySnapshot(null, externalPowerStatus, BatteryChargeState.NoBattery, string.Empty);
			}
			if ((flags & 0x70) != 0)
			{
				return new BatterySnapshot(percent2, externalPowerStatus, BatteryChargeState.Unknown, "알 수 없는 배터리 상태 값입니다.");
			}
			if ((flags & 8) != 0)
			{
				if (externalPowerStatus == ExternalPowerStatus.Disconnected)
				{
					return new BatterySnapshot(percent2, externalPowerStatus, BatteryChargeState.Unknown, "전원과 충전 상태 값이 일치하지 않습니다.");
				}
				return new BatterySnapshot(percent2, externalPowerStatus, BatteryChargeState.Charging, string.Empty);
			}
			bool flag = percent2.HasValue || (flags & 7) != 0;
			if (flag && externalPowerStatus == ExternalPowerStatus.Disconnected)
			{
				return new BatterySnapshot(percent2, externalPowerStatus, BatteryChargeState.Discharging, string.Empty);
			}
			if (flag && externalPowerStatus == ExternalPowerStatus.Connected)
			{
				return new BatterySnapshot(percent2, externalPowerStatus, BatteryChargeState.NotCharging, string.Empty);
			}
			return new BatterySnapshot(percent2, externalPowerStatus, BatteryChargeState.Unknown, "배터리 충전 상태를 확인할 수 없습니다.");
		}
	}
}
