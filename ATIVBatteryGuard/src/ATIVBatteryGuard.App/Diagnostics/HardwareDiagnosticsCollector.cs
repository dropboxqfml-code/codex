using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Management;
using System.Runtime.InteropServices;
using System.Security;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Services;
using Microsoft.Win32;

namespace ATIVBatteryGuard.Diagnostics
{
	public sealed class HardwareDiagnosticsCollector : IHardwareDiagnosticsProvider
	{
		private const string UninstallKey = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall";

		public HardwareProbeReport Collect()
		{
			List<string> errors = new List<string>();
			if (Environment.OSVersion.Platform != PlatformID.Win32NT)
			{
				return new HardwareProbeReport(null, null, null, null, null, null, new string[1] { "이 읽기 전용 수집은 Windows에서만 사용할 수 있습니다." });
			}
			DeviceDiagnosticsResult device;
			try
			{
				device = new DeviceDiagnostics().ReadResult();
			}
			catch (Exception exception) when (ReadFailure(exception))
			{
				device = new DeviceDiagnosticsResult(null, null, null, null, null, null, new string[1] { "기본 장치 정보를 조회하지 못했습니다." });
			}
			NativePowerReading power = new WindowsBatteryStatusProvider().ReadRaw();
			List<WmiBatteryReading> batteries = new List<WmiBatteryReading>();
			ReadRows("root\\cimv2", "SELECT EstimatedChargeRemaining, BatteryStatus FROM Win32_Battery", 8, "배터리 WMI", delegate(ManagementBaseObject entry)
			{
				int? estimatedChargeRemaining = Integer(entry, "EstimatedChargeRemaining");
				int? batteryStatus = Integer(entry, "BatteryStatus");
				batteries.Add(new WmiBatteryReading(estimatedChargeRemaining, batteryStatus));
				if (!estimatedChargeRemaining.HasValue || !batteryStatus.HasValue)
				{
					AddError(errors, "배터리 WMI: 일부 측정값이 제공되지 않았습니다.");
				}
			}, errors);
			List<string> list = new List<string>();
			ReadPrograms(RegistryView.Registry64, list, errors);
			ReadPrograms(RegistryView.Registry32, list, errors);
			List<string> services = new List<string>();
			ReadRows("root\\cimv2", "SELECT Name, DisplayName, State FROM Win32_Service WHERE Name LIKE '%Samsung%' OR DisplayName LIKE '%Samsung%' OR Name LIKE 'SABI%'", 24, "서비스 목록", delegate(ManagementBaseObject entry)
			{
				services.Add("이름: " + Display(Value(entry, "Name")) + " · 표시 이름: " + Display(Value(entry, "DisplayName")) + " · 상태: " + Display(Value(entry, "State")));
			}, errors);
			List<string> classes = new List<string>();
			ReadRows("root\\WMI", "SELECT * FROM meta_class WHERE __CLASS LIKE 'Samsung%' OR __CLASS LIKE 'SABI%'", 24, "OEM WMI 클래스 목록", delegate(ManagementBaseObject entry)
			{
				string text = Value(entry, "__CLASS");
				if (!string.IsNullOrWhiteSpace(text))
				{
					classes.Add(text);
				}
			}, errors);
			WmiSchemaInspectionReport schema = WmiSchemaInspector.Inspect(new WindowsWmiSchemaSource());
			var capabilities = new WindowsBatteryCapabilitiesProvider().Collect();
			return new HardwareProbeReport(device, power, batteries, list, services, classes, errors, schema, capabilities);
		}

		private static void ReadPrograms(RegistryView view, IList<string> programs, IList<string> errors)
		{
			if (programs.Count >= 24)
			{
				return;
			}
			try
			{
				using (RegistryKey registryKey = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, view))
				{
					using (RegistryKey registryKey2 = registryKey.OpenSubKey("SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall", writable: false))
					{
						if (registryKey2 == null)
						{
							AddError(errors, "프로그램 목록: 로컬 제거 목록이 제공되지 않았습니다.");
							return;
						}
						int num = 0;
						string[] subKeyNames = registryKey2.GetSubKeyNames();
						foreach (string name in subKeyNames)
						{
							if (++num > 1024)
							{
								AddError(errors, "프로그램 목록: 조회 한도에 도달해 일부만 조사했습니다.");
								break;
							}
							try
							{
								using (RegistryKey registryKey3 = registryKey2.OpenSubKey(name, writable: false))
								{
									if (registryKey3 == null)
									{
										continue;
									}
									string text = RegistryValue(registryKey3, "DisplayName");
									string text2 = RegistryValue(registryKey3, "Publisher");
									if (SettingsCandidate(text, text2))
									{
										string item = Display(text) + " · 버전: " + Display(RegistryValue(registryKey3, "DisplayVersion")) + " · 게시자: " + Display(text2);
										if (!programs.Contains(item))
										{
											programs.Add(item);
										}
										if (programs.Count == 24)
										{
											AddError(errors, "프로그램 목록: 최대 24개 후보만 포함했습니다.");
											break;
										}
									}
								}
							}
							catch (Exception exception) when (ReadFailure(exception))
							{
								AddError(errors, "프로그램 목록: 일부 항목의 읽기 권한 또는 제공 상태를 확인하지 못했습니다.");
							}
						}
					}
				}
			}
			catch (Exception exception2) when (ReadFailure(exception2))
			{
				AddError(errors, "프로그램 목록: 로컬 제거 목록을 읽을 수 없습니다.");
			}
		}

		private static bool SettingsCandidate(string name, string publisher)
		{
			if (string.IsNullOrWhiteSpace(name))
			{
				return false;
			}
			if (Contains(publisher, "samsung") || Contains(publisher, "삼성") || Contains(name, "samsung") || Contains(name, "삼성"))
			{
				if (!Contains(name, "settings") && !Contains(name, "battery") && !Contains(name, "설정"))
				{
					return Contains(name, "배터리");
				}
				return true;
			}
			return false;
		}

		private static bool Contains(string value, string word)
		{
			if (value != null)
			{
				return value.IndexOf(word, StringComparison.OrdinalIgnoreCase) >= 0;
			}
			return false;
		}

		private static string RegistryValue(RegistryKey key, string name)
		{
			return Convert.ToString(key.GetValue(name, null, RegistryValueOptions.DoNotExpandEnvironmentNames), CultureInfo.InvariantCulture);
		}

		private static void ReadRows(string localNamespace, string query, int maximum, string section, Action<ManagementBaseObject> read, IList<string> errors)
		{
			try
			{
				using (ManagementObjectSearcher managementObjectSearcher = new ManagementObjectSearcher(new ManagementScope("\\\\.\\" + localNamespace, new ConnectionOptions
				{
					Timeout = TimeSpan.FromSeconds(3.0)
				}), options: new EnumerationOptions
				{
					ReturnImmediately = true,
					Rewindable = false,
					Timeout = TimeSpan.FromSeconds(3.0)
				}, query: new ObjectQuery(query)))
				{
					using (ManagementObjectCollection managementObjectCollection = managementObjectSearcher.Get())
					{
						int num = 0;
						foreach (ManagementBaseObject item in managementObjectCollection)
						{
							using (item)
							{
								if (num++ >= maximum)
								{
									AddError(errors, section + ": 조회 한도에 도달해 일부만 포함했습니다.");
									break;
								}
								try
								{
									read(item);
								}
								catch (Exception exception) when (ReadFailure(exception))
								{
									AddError(errors, section + ": 일부 필드를 읽을 수 없습니다.");
								}
							}
						}
					}
				}
			}
			catch (Exception exception2) when (ReadFailure(exception2))
			{
				AddError(errors, section + ": 로컬 읽기 전용 조회에 실패했습니다. 권한 또는 정보 제공 여부를 확인하세요.");
			}
		}

		private static int? Integer(ManagementBaseObject row, string property)
		{
			if (!int.TryParse(Value(row, property), NumberStyles.Integer, CultureInfo.InvariantCulture, out var result))
			{
				return null;
			}
			return result;
		}

		private static string Value(ManagementBaseObject row, string property)
		{
			return Convert.ToString(row[property], CultureInfo.InvariantCulture);
		}

		private static string Display(string value)
		{
			if (!string.IsNullOrWhiteSpace(value))
			{
				return value;
			}
			return "알 수 없음";
		}

		private static void AddError(IList<string> errors, string error)
		{
			if (errors.Count < 16 && !errors.Contains(error))
			{
				errors.Add(error);
			}
		}

		private static bool ReadFailure(Exception exception)
		{
			if (!(exception is ManagementException) && !(exception is UnauthorizedAccessException) && !(exception is SecurityException) && !(exception is COMException) && !(exception is InvalidOperationException) && !(exception is TimeoutException) && !(exception is IOException) && !(exception is ArgumentException))
			{
				return exception is NotSupportedException;
			}
			return true;
		}
	}
}
