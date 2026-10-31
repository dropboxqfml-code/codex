using System;
using System.Collections.Generic;
using System.Text;
using System.Text.RegularExpressions;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Core.Models
{
	public sealed class HardwareProbeReport
	{
		private readonly WmiBatteryReading[] batteries;

		private readonly string[] oemPrograms;

		private readonly string[] oemServices;

		private readonly string[] oemWmiClasses;

		private readonly string[] errors;

		public DeviceDiagnosticsResult Device { get; private set; }

		public NativePowerReading Power { get; private set; }

		public WmiBatteryReading[] Batteries => (WmiBatteryReading[])batteries.Clone();

		public string[] OemPrograms => (string[])oemPrograms.Clone();

		public string[] OemServices => (string[])oemServices.Clone();

		public string[] OemWmiClasses => (string[])oemWmiClasses.Clone();

		public string[] Errors => (string[])errors.Clone();

		public bool HardwareWriteAllowed => false;

		public WmiSchemaInspectionReport OemWmiSchema { get; }

		public HardwareProbeReport(DeviceDiagnosticsResult device = null, NativePowerReading power = null, IEnumerable<WmiBatteryReading> batteries = null, IEnumerable<string> oemPrograms = null, IEnumerable<string> oemServices = null, IEnumerable<string> oemWmiClasses = null, IEnumerable<string> errors = null, WmiSchemaInspectionReport oemWmiSchema = null)
		{
			Device = device ?? new DeviceDiagnosticsResult();
			Power = power ?? new NativePowerReading(success: false, null, null, null, null, "배터리 API 관측값이 없습니다.");
			this.batteries = CopyBatteries(batteries);
			this.oemPrograms = CopyLines(oemPrograms, 24);
			this.oemServices = CopyLines(oemServices, 24);
			this.oemWmiClasses = CopyLines(oemWmiClasses, 24);
			this.errors = CopyLines(errors, 16);
			OemWmiSchema = oemWmiSchema ?? new WmiSchemaInspectionReport(null);
		}

		public string ToDisplayText()
		{
			StringBuilder stringBuilder = new StringBuilder();
			stringBuilder.AppendLine("ATIV Battery Guard — 충전 제어 경로 확인용 읽기 전용 보고서");
			stringBuilder.AppendLine("실제 충전 제어: 미지원. 이 수집은 펌웨어·설정·서비스·드라이버를 변경하지 않습니다.");
			stringBuilder.AppendLine("프로그램/서비스/클래스가 발견돼도 충전 제한 API 또는 안전성이 검증된 것은 아닙니다.");
			stringBuilder.AppendLine();
			stringBuilder.Append(Device.ToDisplayText());
			stringBuilder.AppendLine();
			stringBuilder.AppendLine("[Windows 배터리 API / WMI 관측 비교]");
			stringBuilder.AppendLine(BatteryCrossCheck.Format(Power, batteries));
			stringBuilder.AppendLine("순차적으로 읽은 값이므로 두 측정 시점은 다를 수 있습니다. 0%는 유효한 값이며 고장이나 충전 제한의 증거로 단정하지 않습니다.");
			stringBuilder.AppendLine();
			AppendList(stringBuilder, "Samsung 설정 관련 프로그램 후보", oemPrograms);
			stringBuilder.AppendLine("프로그램 목록은 HKLM의 32/64비트 제거 목록만 확인했습니다. Microsoft Store 앱·사용자별 앱을 모두 조사한 결과가 아닙니다.");
			stringBuilder.AppendLine("발견된 항목이 없다는 사실만으로 Samsung Settings가 설치되지 않았다고 판단하지 않습니다.");
			stringBuilder.AppendLine();
			AppendList(stringBuilder, "Samsung / SABI 관련 서비스 표시 정보", oemServices);
			stringBuilder.AppendLine("서비스 이름·표시 이름·상태만 읽었습니다. 시작·중지·재시작·구성 변경은 하지 않았습니다.");
			stringBuilder.AppendLine();
			AppendList(stringBuilder, "OEM WMI 클래스 이름 (메타데이터만)", oemWmiClasses);
			stringBuilder.AppendLine("클래스 이름만 조사했으며 OEM 인스턴스 값·메서드·펌웨어 인터페이스는 호출하지 않았습니다.");
			stringBuilder.AppendLine();
			stringBuilder.Append(OemWmiSchema.ToDisplayText());
			stringBuilder.AppendLine();
			AppendList(stringBuilder, "수집 누락 / 조회 오류", errors);
			stringBuilder.AppendLine("조회되지 않은 정보는 권한·제공 여부·조회 범위 제한의 영향을 받을 수 있습니다.");
			stringBuilder.AppendLine("시리얼번호·UUID·배터리 DeviceID·사용자 이름·전체 사용자 경로는 수집하지 않습니다. 자동 전송하지 않습니다.");
			return stringBuilder.ToString();
		}

		private static void AppendList(StringBuilder text, string title, string[] values)
		{
			text.AppendLine("[" + title + "]");
			if (values.Length == 0)
			{
				text.AppendLine("이 조회 경로에서 발견한 항목이 없습니다.");
				return;
			}
			foreach (string text2 in values)
			{
				text.AppendLine("- " + text2);
			}
		}

		private static WmiBatteryReading[] CopyBatteries(IEnumerable<WmiBatteryReading> source)
		{
			List<WmiBatteryReading> list = new List<WmiBatteryReading>();
			if (source != null)
			{
				int num = 0;
				foreach (WmiBatteryReading item in source)
				{
					if (++num > 128)
					{
						break;
					}
					if (item != null)
					{
						list.Add(item);
					}
					if (list.Count == 8)
					{
						break;
					}
				}
			}
			return list.ToArray();
		}

		private static string[] CopyLines(IEnumerable<string> source, int maximum)
		{
			List<string> list = new List<string>();
			if (source != null)
			{
				int num = 0;
				foreach (string item in source)
				{
					if (++num > 128)
					{
						break;
					}
					string text = Sanitize(item);
					if (text.Length != 0 && !list.Contains(text))
					{
						list.Add(text);
					}
					if (list.Count == maximum)
					{
						break;
					}
				}
			}
			return list.ToArray();
		}

		private static string Sanitize(string value)
		{
			if (string.IsNullOrWhiteSpace(value))
			{
				return string.Empty;
			}
			if (Regex.IsMatch(value, "[A-Za-z]:[\\\\/]") || value.Contains("\\\\") || value.IndexOf("/home/", StringComparison.OrdinalIgnoreCase) >= 0 || value.IndexOf("/Users/", StringComparison.OrdinalIgnoreCase) >= 0 || value.IndexOf("file:", StringComparison.OrdinalIgnoreCase) >= 0)
			{
				return "경로가 포함된 값은 기록하지 않았습니다.";
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
