using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
	public static class BatteryCrossCheck
	{
		public static string Format(NativePowerReading raw, IEnumerable<WmiBatteryReading> batteries)
		{
			List<WmiBatteryReading> list = new List<WmiBatteryReading>();
			bool flag = false;
			if (batteries != null)
			{
				foreach (WmiBatteryReading battery in batteries)
				{
					if (list.Count == 16)
					{
						flag = true;
						break;
					}
					list.Add(battery);
				}
			}
			StringBuilder stringBuilder = new StringBuilder();
			stringBuilder.AppendLine("[Windows 배터리 API 원시 값]");
			BatterySnapshot batterySnapshot = ((raw == null) ? BatterySnapshot.Unknown(string.Empty) : raw.ToSnapshot());
			stringBuilder.AppendLine("GetSystemPowerStatus 호출: " + ((raw != null && raw.Success) ? "성공" : "실패 / 제공되지 않음"));
			stringBuilder.AppendLine("ACLineStatus: " + ByteText(raw?.AcLineStatus));
			stringBuilder.AppendLine("BatteryFlag: " + ((raw != null && raw.BatteryFlag.HasValue) ? (raw.BatteryFlag.Value.ToString(CultureInfo.InvariantCulture) + " (0x" + raw.BatteryFlag.Value.ToString("X2", CultureInfo.InvariantCulture) + ")") : "알 수 없음"));
			stringBuilder.AppendLine("BatteryLifePercent: " + ByteText(raw?.BatteryLifePercent));
			if (raw != null && raw.Win32Error.HasValue)
			{
				stringBuilder.AppendLine("Win32 오류 코드: " + raw.Win32Error.Value.ToString(CultureInfo.InvariantCulture));
			}
			stringBuilder.AppendLine("해석된 Windows 잔량: " + PercentText(batterySnapshot.Percent));
			stringBuilder.AppendLine("해석된 충전 상태: " + ChargeText(batterySnapshot.ChargeState));
			stringBuilder.AppendLine("255는 해당 API의 값 없음 표시입니다. 0%는 유효한 측정값으로 보존합니다.");
			stringBuilder.AppendLine();
			stringBuilder.AppendLine("[Win32_Battery 교차 조회]");
			if (list.Count == 0)
			{
				stringBuilder.AppendLine("WMI 배터리 행이 제공되지 않았습니다. 배터리 부재나 고장으로 단정하지 않습니다.");
			}
			for (int i = 0; i < list.Count; i++)
			{
				WmiBatteryReading wmiBatteryReading = list[i];
				stringBuilder.AppendLine("배터리 " + (i + 1).ToString(CultureInfo.InvariantCulture) + ": EstimatedChargeRemaining=" + PercentText(wmiBatteryReading?.EstimatedChargeRemaining) + ", BatteryStatus=" + ((wmiBatteryReading != null && wmiBatteryReading.BatteryStatus.HasValue) ? wmiBatteryReading.BatteryStatus.Value.ToString(CultureInfo.InvariantCulture) : "알 수 없음"));
			}
			if (flag)
			{
				stringBuilder.AppendLine("WMI 배터리 표시는 최대 16개로 제한했습니다.");
			}
			stringBuilder.AppendLine();
			if (list.Count > 1 || flag)
			{
				stringBuilder.AppendLine("여러 배터리: Windows API의 시스템 집계와 개별 WMI 배터리 값은 직접 비교하지 않습니다.");
				stringBuilder.AppendLine("특정 WMI 행이나 평균값으로 Windows 표시를 대체하지 않습니다.");
			}
			else if (list.Count == 1 && list[0] != null && batterySnapshot.Percent.HasValue && list[0].EstimatedChargeRemaining.HasValue)
			{
				int num = Math.Abs(batterySnapshot.Percent.Value - list[0].EstimatedChargeRemaining.Value);
				stringBuilder.AppendLine("단일 배터리 잔량 차이: " + num.ToString(CultureInfo.InvariantCulture) + "%p");
				if (num > 3)
				{
					stringBuilder.AppendLine("측정값 차이 확인 필요: 3%p를 초과했습니다. 조회 시점과 드라이버 보고 범위를 확인해야 합니다.");
				}
				else
				{
					stringBuilder.AppendLine("관측 잔량 차이는 3%p 이하입니다. 조회 시점은 서로 다를 수 있습니다.");
				}
				stringBuilder.AppendLine("어느 한쪽을 정답으로 선택하거나 다른 소스의 잔량으로 덮어쓰지 않습니다.");
			}
			else
			{
				stringBuilder.AppendLine("한쪽 이상의 잔량 정보가 없어 비교할 수 없습니다. 없는 값을 0%로 바꾸지 않습니다.");
			}
			stringBuilder.AppendLine("0% 또는 ‘충전 중 아님’만으로 배터리 고장이나 실제 충전 제한을 판정하지 않습니다.");
			stringBuilder.AppendLine("이 보고서는 읽기 전용 관측이며 실제 펌웨어의 충전 상한 상태는 알 수 없습니다.");
			stringBuilder.AppendLine("실제 충전 제어: 미지원. 이 조회 결과는 충전 제한 지원 또는 적용 성공의 증거가 아닙니다.");
			return stringBuilder.ToString();
		}

		private static string ByteText(byte? value)
		{
			if (!value.HasValue)
			{
				return "알 수 없음";
			}
			return value.Value.ToString(CultureInfo.InvariantCulture);
		}

		private static string PercentText(int? value)
		{
			if (!value.HasValue)
			{
				return "알 수 없음";
			}
			return value.Value.ToString(CultureInfo.InvariantCulture) + "%";
		}

		private static string ChargeText(BatteryChargeState state)
		{
			switch (state)
			{
			case BatteryChargeState.Charging:
				return "충전 중";
			case BatteryChargeState.NotCharging:
				return "충전 중 아님";
			case BatteryChargeState.Discharging:
				return "방전 중";
			case BatteryChargeState.NoBattery:
				return "배터리 없음";
			default:
				return "상태 알 수 없음";
			}
		}
	}
}
