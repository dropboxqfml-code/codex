using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
	public static class SamsungServicePathResolver
	{
		private sealed class Roots
		{
			private readonly string windows;

			private readonly string programFiles;

			private readonly string programFilesX86;

			private readonly string programData;

			public Roots(string windows, string programFiles, string programFilesX86, string programData)
			{
				this.windows = Root(windows);
				this.programFiles = Root(programFiles);
				this.programFilesX86 = Root(programFilesX86);
				this.programData = Root(programData);
			}

			public bool Expand(string token, out string expanded, out string reason)
			{
				reason = "UNKNOWN_ENVIRONMENT_VARIABLE";
				bool known = true;
				expanded = Regex.Replace(token, "%([^%]+)%", delegate(Match match)
				{
					string value = match.Groups[1].Value;
					string text = null;
					if (Same(value, "SystemRoot") || Same(value, "windir"))
					{
						text = windows;
					}
					else if (Same(value, "SystemDrive") && windows.Length >= 2)
					{
						text = windows.Substring(0, 2);
					}
					else if (Same(value, "ProgramFiles") || Same(value, "ProgramW6432"))
					{
						text = programFiles;
					}
					else if (Same(value, "ProgramFiles(x86)"))
					{
						text = programFilesX86;
					}
					else if (Same(value, "ProgramData"))
					{
						text = programData;
					}
					if (string.IsNullOrEmpty(text))
					{
						known = false;
						return string.Empty;
					}
					return text;
				});
				if (!known || expanded.IndexOf('%') >= 0)
				{
					return false;
				}
				expanded = expanded.Replace('/', '\\');
				if (expanded.StartsWith("\\SystemRoot\\", StringComparison.OrdinalIgnoreCase))
				{
					if (windows.Length == 0)
					{
						return false;
					}
					expanded = windows + expanded.Substring("\\SystemRoot".Length);
				}
				else if (expanded.StartsWith("System32\\", StringComparison.OrdinalIgnoreCase) || expanded.StartsWith("SysWOW64\\", StringComparison.OrdinalIgnoreCase))
				{
					if (windows.Length == 0)
					{
						return false;
					}
					expanded = windows + "\\" + expanded;
				}
				reason = string.Empty;
				return true;
			}

			public string Classify(string path, out bool enumerate)
			{
				enumerate = false;
				if (VendorSubtree(path, programData, "Samsung") || VendorSubtree(path, programData, "Samsung Electronics"))
				{
					enumerate = true;
					return "ProgramDataSamsung";
				}
				string[] array = new string[3] { "Samsung", "SamsungSettings", "Samsung Electronics" };
				foreach (string vendor in array)
				{
					if (VendorSubtree(path, windows, vendor) || VendorSubtree(path, Combine(windows, "System32"), vendor) || VendorSubtree(path, Combine(windows, "SysWOW64"), vendor))
					{
						enumerate = true;
						return "WindowsSamsung";
					}
				}
				if (DirectChild(path, Combine(windows, "System32")))
				{
					return "System32";
				}
				if (DirectChild(path, Combine(windows, "SysWOW64")))
				{
					return "SysWOW64";
				}
				if (DirectChild(path, windows))
				{
					return "WindowsRoot";
				}
				if (Child(path, programFilesX86))
				{
					enumerate = !DirectChild(path, programFilesX86);
					return "ProgramFilesX86";
				}
				if (Child(path, programFiles))
				{
					enumerate = !DirectChild(path, programFiles);
					return "ProgramFiles";
				}
				return "OtherLocalRoot";
			}

			private static string Root(string value)
			{
				if (!Normalize(value, out var full))
				{
					return string.Empty;
				}
				return full.TrimEnd(new char[1] { '\\' });
			}

			private static bool VendorSubtree(string path, string root, string vendor)
			{
				return Child(path, Combine(root, vendor));
			}

			private static string Combine(string root, string child)
			{
				if (root.Length != 0)
				{
					return root + "\\" + child;
				}
				return string.Empty;
			}

			private static bool Child(string path, string root)
			{
				if (root.Length != 0 && path.Length > root.Length + 1)
				{
					return path.StartsWith(root + "\\", StringComparison.OrdinalIgnoreCase);
				}
				return false;
			}

			private static bool DirectChild(string path, string root)
			{
				if (Child(path, root))
				{
					return path.IndexOf('\\', root.Length + 1) < 0;
				}
				return false;
			}

			private static bool Same(string left, string right)
			{
				return string.Equals(left, right, StringComparison.OrdinalIgnoreCase);
			}
		}

		public static SamsungServiceLocation Resolve(string wmiImagePath, string registryImagePath, string serviceDllPath, string windowsDirectory, string programFiles, string programFilesX86, string commonApplicationData, Func<string, bool> exists, Func<string, bool> safePath)
		{
			Roots roots = new Roots(windowsDirectory, programFiles, programFilesX86, commonApplicationData);
			SamsungServiceLocation current = Failure("None", "Invalid", "PATH_NOT_PROVIDED");
			SamsungServiceLocation samsungServiceLocation = TryCandidate(wmiImagePath, dll: false, "WMI", roots, exists, safePath);
			if (samsungServiceLocation.Found)
			{
				return samsungServiceLocation;
			}
			current = MoreUseful(current, samsungServiceLocation);
			bool flag = samsungServiceLocation.ReasonCode == "HOST_EXECUTABLE_REQUIRES_SERVICE_DLL";
			if (flag)
			{
				SamsungServiceLocation samsungServiceLocation2 = TryCandidate(serviceDllPath, dll: true, "RegistryServiceDll", roots, exists, safePath);
				if (samsungServiceLocation2.Found)
				{
					return samsungServiceLocation2;
				}
				current = MoreUseful(current, samsungServiceLocation2);
			}
			SamsungServiceLocation samsungServiceLocation3 = TryCandidate(registryImagePath, dll: false, "RegistryImagePath", roots, exists, safePath);
			if (samsungServiceLocation3.Found)
			{
				return samsungServiceLocation3;
			}
			current = MoreUseful(current, samsungServiceLocation3);
			if (!flag)
			{
				SamsungServiceLocation samsungServiceLocation4 = TryCandidate(serviceDllPath, dll: true, "RegistryServiceDll", roots, exists, safePath);
				if (samsungServiceLocation4.Found)
				{
					return samsungServiceLocation4;
				}
				current = MoreUseful(current, samsungServiceLocation4);
			}
			return current;
		}

		private static SamsungServiceLocation TryCandidate(string value, bool dll, string source, Roots roots, Func<string, bool> exists, Func<string, bool> safePath)
		{
			if (!Extract(value, dll, out var token, out var reason))
			{
				return Failure(source, "Invalid", reason);
			}
			string text = FileName(token);
			if (!dll && IsHost(text))
			{
				return Failure(source, "Invalid", "HOST_EXECUTABLE_REQUIRES_SERVICE_DLL", text);
			}
			if (!roots.Expand(token, out var expanded, out reason))
			{
				return Failure(source, "Invalid", reason, text);
			}
			if (!Normalize(expanded, out var full))
			{
				return Failure(source, "Invalid", "PATH_SYNTAX_INVALID", text);
			}
			string text2 = FileName(full);
			if (SamsungServiceLocation.SafeFileName(text2).Length == 0)
			{
				return Failure(source, "Invalid", "PATH_SYNTAX_INVALID");
			}
			bool enumerate;
			string text3 = roots.Classify(full, out enumerate);
			if (text3 == "OtherLocalRoot")
			{
				return Failure(source, text3, "OUTSIDE_ALLOWED_ROOT", text2);
			}
			if (safePath == null || exists == null)
			{
				return Failure(source, text3, "UNSAFE_PATH", text2);
			}
			try
			{
				if (!safePath(full))
				{
					return Failure(source, text3, "UNSAFE_PATH", text2);
				}
			}
			catch
			{
				return Failure(source, text3, "UNSAFE_PATH", text2);
			}
			try
			{
				if (!exists(full))
				{
					return Failure(source, text3, "FILE_NOT_FOUND", text2);
				}
			}
			catch
			{
				return Failure(source, text3, "FILE_LOOKUP_FAILED", text2);
			}
			return new SamsungServiceLocation(found: true, full, text2, source, text3, "FOUND", enumerate);
		}

		private static bool Extract(string value, bool dll, out string token, out string reason)
		{
			token = string.Empty;
			reason = "PATH_NOT_PROVIDED";
			if (string.IsNullOrWhiteSpace(value))
			{
				return false;
			}
			reason = "PATH_SYNTAX_INVALID";
			if (value.Length > 8192)
			{
				return false;
			}
			foreach (char c in value)
			{
				if (!char.IsControl(c))
				{
					switch (c)
					{
					default:
						if (c < '\u2066' || c > '\u2069')
						{
							continue;
						}
						break;
					case '\u2028':
					case '\u2029':
					case '\u202a':
					case '\u202b':
					case '\u202c':
					case '\u202d':
					case '\u202e':
						break;
					}
				}
				return false;
			}
			string text = value.Trim();
			if (text[0] == '"')
			{
				int num = text.IndexOf('"', 1);
				if (num <= 1 || (num + 1 < text.Length && !char.IsWhiteSpace(text[num + 1])))
				{
					return false;
				}
				if (dll && text.Substring(num + 1).Trim().Length != 0)
				{
					return false;
				}
				token = text.Substring(1, num - 1);
			}
			else if (dll)
			{
				token = text;
				if (token.IndexOf('"') >= 0)
				{
					return false;
				}
			}
			else
			{
				int num2 = 0;
				while (num2 < text.Length)
				{
					int num3 = text.IndexOf(".exe", num2, StringComparison.OrdinalIgnoreCase);
					if (num3 < 0)
					{
						return false;
					}
					num3 += 4;
					if (num3 == text.Length || char.IsWhiteSpace(text[num3]))
					{
						token = text.Substring(0, num3);
						break;
					}
					num2 = num3;
				}
				if (token.IndexOf('"') >= 0)
				{
					return false;
				}
			}
			if (!token.EndsWith(dll ? ".dll" : ".exe", StringComparison.OrdinalIgnoreCase))
			{
				return false;
			}
			return true;
		}

		private static bool IsHost(string name)
		{
			string[] array = new string[15]
			{
				"svchost.exe", "dllhost.exe", "rundll32.exe", "regsvr32.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe", "msiexec.exe",
				"taskhost.exe", "taskhostw.exe", "services.exe", "wmiprvse.exe", "conhost.exe"
			};
			foreach (string b in array)
			{
				if (string.Equals(name, b, StringComparison.OrdinalIgnoreCase))
				{
					return true;
				}
			}
			return false;
		}

		private static string FileName(string path)
		{
			if (string.IsNullOrEmpty(path))
			{
				return string.Empty;
			}
			int num = Math.Max(path.LastIndexOf('\\'), path.LastIndexOf('/'));
			return SamsungServiceLocation.SafeFileName(path.Substring(num + 1));
		}

		private static bool Normalize(string value, out string full)
		{
			full = string.Empty;
			if (string.IsNullOrWhiteSpace(value) || value.Length > 4096)
			{
				return false;
			}
			string text = value.Replace('/', '\\');
			if (text.StartsWith("\\??\\", StringComparison.Ordinal) || text.StartsWith("\\\\?\\", StringComparison.Ordinal))
			{
				text = text.Substring(4);
			}
			if (text.Length < 3 || !IsDriveLetter(text[0]) || text[1] != ':' || text[2] != '\\')
			{
				return false;
			}
			List<string> list = new List<string>();
			string[] array = text.Substring(3).Split(new char[1] { '\\' });
			foreach (string text2 in array)
			{
				if (text2.Length == 0 || text2 == ".")
				{
					continue;
				}
				if (text2 == "..")
				{
					if (list.Count == 0)
					{
						return false;
					}
					list.RemoveAt(list.Count - 1);
					continue;
				}
				if (text2 != text2.Trim() || text2.EndsWith(".", StringComparison.Ordinal))
				{
					return false;
				}
				if (ReservedDeviceComponent(text2))
				{
					return false;
				}
				string text3 = text2;
				foreach (char c in text3)
				{
					if (!char.IsControl(c))
					{
						switch (c)
						{
						default:
							if (c < '\u2066' || c > '\u2069')
							{
								continue;
							}
							break;
						case '"':
						case '%':
						case '*':
						case ':':
						case '<':
						case '>':
						case '?':
						case '|':
						case '\u2028':
						case '\u2029':
						case '\u202a':
						case '\u202b':
						case '\u202c':
						case '\u202d':
						case '\u202e':
							break;
						}
					}
					return false;
				}
				list.Add(text2);
			}
			full = char.ToUpperInvariant(text[0]) + ":\\" + string.Join("\\", list);
			return true;
		}

		private static bool ReservedDeviceComponent(string component)
		{
			int num = component.IndexOf('.');
			string text = ((num < 0) ? component : component.Substring(0, num)).TrimEnd(new char[1] { ' ' }).ToUpperInvariant();
			switch (text)
			{
			case "CON":
			case "PRN":
			case "AUX":
			case "NUL":
			case "CONIN$":
			case "CONOUT$":
				return true;
			default:
			{
				if (text.Length != 4 || (!text.StartsWith("COM", StringComparison.Ordinal) && !text.StartsWith("LPT", StringComparison.Ordinal)))
				{
					return false;
				}
				char c = text[3];
				if ((c < '1' || c > '9') && c != '¹' && c != '²')
				{
					return c == '³';
				}
				return true;
			}
			}
		}

		private static bool IsDriveLetter(char value)
		{
			if (value < 'A' || value > 'Z')
			{
				if (value >= 'a')
				{
					return value <= 'z';
				}
				return false;
			}
			return true;
		}

		private static SamsungServiceLocation Failure(string source, string category, string reason, string fileName = null)
		{
			return new SamsungServiceLocation(found: false, null, fileName, source, category, reason);
		}

		private static SamsungServiceLocation MoreUseful(SamsungServiceLocation current, SamsungServiceLocation next)
		{
			if (Rank(next.ReasonCode) <= Rank(current.ReasonCode))
			{
				return current;
			}
			return next;
		}

		private static int Rank(string reason)
		{
			switch (reason)
			{
			case "UNSAFE_PATH":
				return 100;
			case "FILE_LOOKUP_FAILED":
				return 95;
			case "FILE_NOT_FOUND":
				return 90;
			case "OUTSIDE_ALLOWED_ROOT":
				return 80;
			case "UNKNOWN_ENVIRONMENT_VARIABLE":
				return 70;
			case "PATH_SYNTAX_INVALID":
				return 60;
			case "HOST_EXECUTABLE_REQUIRES_SERVICE_DLL":
				return 50;
			default:
				return 0;
			}
		}
	}
}
