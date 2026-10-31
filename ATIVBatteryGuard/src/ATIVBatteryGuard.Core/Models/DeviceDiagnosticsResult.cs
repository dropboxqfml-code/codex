using System;
using System.Collections.Generic;
using System.Text;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Core.Models
{
	public sealed class DeviceDiagnosticsResult
	{
		private readonly string[] errors;

		public string Manufacturer { get; private set; }

		public string Model { get; private set; }

		public string BiosVersion { get; private set; }

		public string WindowsName { get; private set; }

		public string WindowsVersion { get; private set; }

		public string SystemArchitecture { get; private set; }

		public string[] Errors => (string[])errors.Clone();

		public DeviceDiagnosticsResult(string manufacturer = null, string model = null, string biosVersion = null, string windowsName = null, string windowsVersion = null, string systemArchitecture = null, string[] errors = null)
		{
			Manufacturer = Metadata(manufacturer);
			Model = Metadata(model);
			BiosVersion = Metadata(biosVersion);
			WindowsName = Metadata(windowsName);
			WindowsVersion = Metadata(windowsVersion);
			SystemArchitecture = Metadata(systemArchitecture);
			List<string> list = new List<string>();
			if (errors != null)
			{
				for (int i = 0; i < errors.Length; i++)
				{
					string text = Sanitize(errors[i]);
					if (text.Length > 0 && !list.Contains(text))
					{
						list.Add(text);
					}
					if (list.Count == 16)
					{
						break;
					}
				}
			}
			this.errors = list.ToArray();
		}

		public string ToDisplayText()
		{
			DeviceSupportAssessment deviceSupportAssessment = DeviceSupportAssessment.Evaluate(this);
			StringBuilder stringBuilder = new StringBuilder();
			stringBuilder.AppendLine("ATIV Battery Guard — 로컬 읽기 전용 진단");
			stringBuilder.AppendLine("제조사: " + Display(Manufacturer));
			stringBuilder.AppendLine("모델: " + Display(Model));
			stringBuilder.AppendLine("BIOS 버전: " + Display(BiosVersion));
			stringBuilder.AppendLine("Windows: " + Display(WindowsName));
			stringBuilder.AppendLine("Windows 버전: " + Display(WindowsVersion));
			stringBuilder.AppendLine("시스템 아키텍처: " + Display(SystemArchitecture));
			stringBuilder.AppendLine("프로세스 아키텍처: " + (Environment.Is64BitProcess ? "x64" : "x86"));
			stringBuilder.AppendLine();
			stringBuilder.AppendLine("연구 대상 판정: " + deviceSupportAssessment.StatusText);
			stringBuilder.AppendLine(deviceSupportAssessment.Reason);
			stringBuilder.AppendLine("실제 충전 제어: 미지원 (검증된 OEM 어댑터 없음)");
			stringBuilder.AppendLine("모델 일치 또는 배터리 잔량은 실제 충전 제한 지원의 증거가 아닙니다.");
			if (errors.Length != 0)
			{
				stringBuilder.AppendLine();
				stringBuilder.AppendLine("[조회하지 못한 정보 / 오류]");
				string[] array = errors;
				foreach (string text in array)
				{
					stringBuilder.AppendLine("- " + text);
				}
			}
			stringBuilder.AppendLine();
			stringBuilder.AppendLine("시리얼번호·UUID·사용자 이름은 조회하지 않습니다. 네트워크로 전송하지 않습니다.");
			return stringBuilder.ToString();
		}

		private static string Display(string value)
		{
			if (value.Length != 0)
			{
				return value;
			}
			return "알 수 없음";
		}

		private static string Metadata(string value)
		{
			string text = Sanitize(value);
			string[] array = new string[7] { "unknown", "n/a", "none", "default string", "system product name", "to be filled by o.e.m.", "알 수 없음" };
			foreach (string b in array)
			{
				if (string.Equals(text, b, StringComparison.OrdinalIgnoreCase))
				{
					return string.Empty;
				}
			}
			return text;
		}

		private static string Sanitize(string value)
		{
			if (string.IsNullOrWhiteSpace(value))
			{
				return string.Empty;
			}
			StringBuilder stringBuilder = new StringBuilder(200);
			foreach (char c in value)
			{
				if (char.IsControl(c) || c == '\u2028' || c == '\u2029' || (c >= '\u202a' && c <= '\u202e') || (c >= '\u2066' && c <= '\u2069'))
				{
					stringBuilder.Append(' ');
				}
				else
				{
					stringBuilder.Append(c);
				}
				if (stringBuilder.Length == 200)
				{
					break;
				}
			}
			return stringBuilder.ToString().Trim();
		}
	}
}
