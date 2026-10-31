using System;
using System.Collections.Generic;
using System.Globalization;
using System.Management;
using System.Runtime.InteropServices;
using System.Security;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Diagnostics
{
	public sealed class DeviceDiagnostics
	{
		public string Read()
		{
			return ReadResult().ToDisplayText();
		}

		public DeviceDiagnosticsResult ReadResult()
		{
			List<string> list = new List<string>();
			if (Environment.OSVersion.Platform != PlatformID.Win32NT)
			{
				return new DeviceDiagnosticsResult(null, null, null, null, null, null, new string[1] { "WMI 진단은 Windows에서만 사용할 수 있습니다." });
			}
			Dictionary<string, string> values = Query("장치", "SELECT Name, Vendor FROM Win32_ComputerSystemProduct", new Dictionary<string, string>
			{
				{ "Name", "모델" },
				{ "Vendor", "제조사" }
			}, list);
			Dictionary<string, string> values2 = Query("BIOS", "SELECT SMBIOSBIOSVersion FROM Win32_BIOS", new Dictionary<string, string> { { "SMBIOSBIOSVersion", "BIOS 버전" } }, list);
			Dictionary<string, string> values3 = Query("운영체제", "SELECT Caption, Version, OSArchitecture FROM Win32_OperatingSystem", new Dictionary<string, string>
			{
				{ "Caption", "Windows 이름" },
				{ "Version", "Windows 버전" },
				{ "OSArchitecture", "시스템 아키텍처" }
			}, list);
			return new DeviceDiagnosticsResult(Value(values, "Vendor"), Value(values, "Name"), Value(values2, "SMBIOSBIOSVersion"), Value(values3, "Caption"), Value(values3, "Version"), Value(values3, "OSArchitecture"), list.ToArray());
		}

		private static Dictionary<string, string> Query(string section, string query, IDictionary<string, string> properties, IList<string> errors)
		{
			Dictionary<string, string> dictionary = new Dictionary<string, string>(StringComparer.Ordinal);
			try
			{
				using (ManagementObjectSearcher managementObjectSearcher = new ManagementObjectSearcher(new ManagementScope("\\\\.\\root\\cimv2"), options: new EnumerationOptions
				{
					ReturnImmediately = true,
					Rewindable = false,
					Timeout = TimeSpan.FromSeconds(3.0)
				}, query: new ObjectQuery(query)))
				{
					using (ManagementObjectCollection managementObjectCollection = managementObjectSearcher.Get())
					{
						bool flag = false;
						using (ManagementObjectCollection.ManagementObjectEnumerator managementObjectEnumerator = managementObjectCollection.GetEnumerator())
						{
							if (managementObjectEnumerator.MoveNext())
							{
								ManagementObject managementObject = (ManagementObject)managementObjectEnumerator.Current;
								using (managementObject)
								{
									foreach (KeyValuePair<string, string> property in properties)
									{
										try
										{
											string value = Convert.ToString(managementObject[property.Key], CultureInfo.InvariantCulture);
											dictionary[property.Key] = value;
											if (Unavailable(value))
											{
												errors.Add(section + ": " + property.Value + " 정보가 제공되지 않았습니다.");
											}
										}
										catch (ManagementException)
										{
											errors.Add(section + ": " + property.Value + " 정보를 읽을 수 없습니다.");
										}
									}
									flag = true;
								}
							}
						}
						if (!flag)
						{
							errors.Add(section + ": 장치 정보 행이 제공되지 않았습니다.");
						}
					}
				}
			}
			catch (ManagementException)
			{
				errors.Add(section + ": WMI 조회 실패로 정보를 확인할 수 없습니다.");
			}
			catch (UnauthorizedAccessException)
			{
				errors.Add(section + ": WMI 조회 권한이 없습니다.");
			}
			catch (SecurityException)
			{
				errors.Add(section + ": WMI 보안 정책으로 조회할 수 없습니다.");
			}
			catch (COMException)
			{
				errors.Add(section + ": 로컬 WMI 서비스를 사용할 수 없습니다.");
			}
			catch (InvalidOperationException)
			{
				errors.Add(section + ": WMI 조회를 완료하지 못했습니다.");
			}
			catch (TimeoutException)
			{
				errors.Add(section + ": WMI 조회 시간을 초과했습니다.");
			}
			return dictionary;
		}

		private static string Value(IDictionary<string, string> values, string key)
		{
			if (!values.TryGetValue(key, out var value))
			{
				return string.Empty;
			}
			return value;
		}

		private static bool Unavailable(string value)
		{
			if (string.IsNullOrWhiteSpace(value))
			{
				return true;
			}
			string[] array = new string[7] { "unknown", "n/a", "none", "default string", "system product name", "to be filled by o.e.m.", "알 수 없음" };
			foreach (string b in array)
			{
				if (string.Equals(value.Trim(), b, StringComparison.OrdinalIgnoreCase))
				{
					return true;
				}
			}
			return false;
		}
	}
}
