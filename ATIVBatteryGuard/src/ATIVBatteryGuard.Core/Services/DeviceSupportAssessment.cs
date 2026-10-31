using System;
using System.Collections.Generic;
using System.Text;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
	public sealed class DeviceSupportAssessment
	{
		public string StatusText { get; private set; }

		public string Reason { get; private set; }

		public bool IsResearchCandidate { get; private set; }

		public bool HardwareWriteAllowed => false;

		private DeviceSupportAssessment(string statusText, string reason, bool isResearchCandidate)
		{
			StatusText = statusText;
			Reason = reason;
			IsResearchCandidate = isResearchCandidate;
		}

		public static DeviceSupportAssessment Evaluate(DeviceDiagnosticsResult device)
		{
			if (device == null)
			{
				return new DeviceSupportAssessment("알 수 없음", "장치 진단 결과가 없습니다. 실제 충전 제어는 차단되어 있습니다.", isResearchCandidate: false);
			}
			List<string> list = new List<string>();
			if (!Known(device.Manufacturer))
			{
				list.Add("제조사");
			}
			if (!Known(device.Model))
			{
				list.Add("모델");
			}
			if (!Known(device.BiosVersion))
			{
				list.Add("BIOS 버전");
			}
			if (!Known(device.WindowsName) || !Known(device.WindowsVersion))
			{
				list.Add("Windows 이름/버전");
			}
			if (!Known(device.SystemArchitecture))
			{
				list.Add("시스템 아키텍처");
			}
			int num;
			int num2;
			if (Known(device.Manufacturer))
			{
				num = (Known(device.Model) ? 1 : 0);
				if (num != 0 && IsSamsung(device.Manufacturer))
				{
					num2 = (IsPriorityModel(device.Model) ? 1 : 0);
					goto IL_00d8;
				}
			}
			else
			{
				num = 0;
			}
			num2 = 0;
			goto IL_00d8;
			IL_00d8:
			bool flag = (byte)num2 != 0;
			string statusText = ((num == 0) ? "알 수 없음" : (flag ? "연구 우선 모델 일치 · 제어 미검증" : "연구 우선 모델과 불일치"));
			string text = (flag ? "Samsung NP940X3G/940X3G 계열의 연구 우선 범위입니다. 모델·BIOS별 OEM 인터페이스와 Windows 동작은 아직 검증되지 않았습니다." : "현재 진단으로 Samsung NP940X3G/940X3G 연구 우선 범위를 확인하지 못했습니다.");
			if (list.Count > 0)
			{
				text = text + " 확인하지 못한 정보: " + string.Join(", ", list) + ".";
			}
			if (device.Errors.Length != 0)
			{
				text += " 일부 장치 조회가 완료되지 않았습니다.";
			}
			text += " 실제 충전 제어는 미지원이며 모든 하드웨어 쓰기는 차단됩니다.";
			return new DeviceSupportAssessment(statusText, text, flag);
		}

		private static bool IsPriorityModel(string model)
		{
			string value = model.Trim();
			if (!HasModelPrefix(value, "NP940X3G"))
			{
				return HasModelPrefix(value, "940X3G");
			}
			return true;
		}

		private static bool HasModelPrefix(string value, string prefix)
		{
			if (!value.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
			{
				return false;
			}
			if (value.Length != prefix.Length && value[prefix.Length] != '-' && value[prefix.Length] != '/')
			{
				return char.IsWhiteSpace(value[prefix.Length]);
			}
			return true;
		}

		private static bool IsSamsung(string manufacturer)
		{
			StringBuilder stringBuilder = new StringBuilder();
			bool flag = false;
			foreach (char c in manufacturer)
			{
				if (char.IsLetterOrDigit(c))
				{
					if (flag && stringBuilder.Length > 0)
					{
						stringBuilder.Append(' ');
					}
					stringBuilder.Append(char.ToUpperInvariant(c));
					flag = false;
				}
				else
				{
					flag = true;
				}
			}
			string text = stringBuilder.ToString();
			switch (text)
			{
			default:
				return text == "SAMSUNG ELECTRONICS CO LIMITED";
			case "SAMSUNG":
			case "SAMSUNG ELECTRONICS":
			case "SAMSUNG ELECTRONICS CO LTD":
				return true;
			}
		}

		private static bool Known(string value)
		{
			if (string.IsNullOrWhiteSpace(value))
			{
				return false;
			}
			string a = value.Trim();
			string[] array = new string[7] { "unknown", "n/a", "none", "default string", "system product name", "to be filled by o.e.m.", "알 수 없음" };
			foreach (string b in array)
			{
				if (string.Equals(a, b, StringComparison.OrdinalIgnoreCase))
				{
					return false;
				}
			}
			return true;
		}
	}
}
