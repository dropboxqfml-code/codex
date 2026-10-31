using System;
using System.Collections.Generic;

namespace ATIVBatteryGuard.Core.Models
{
	public sealed class PeModuleInfo
	{
		private readonly string[] importedModules;

		private readonly string[] exportedNames;

		public bool IsValid { get; private set; }

		public bool IsManaged { get; private set; }

		public string Architecture { get; private set; }

		public string[] ImportedModules => (string[])importedModules.Clone();

		public string[] ExportedNames => (string[])exportedNames.Clone();

		public string Error { get; private set; }

		public PeModuleInfo(bool isValid, bool isManaged, string architecture, IEnumerable<string> importedModules = null, IEnumerable<string> exportedNames = null, string error = null)
		{
			IsValid = isValid;
			IsManaged = isValid && isManaged;
			Architecture = ((isValid && (architecture == "x86" || architecture == "x64")) ? architecture : "Unknown");
			this.importedModules = (isValid ? CopyNames(importedModules, 64, module: true) : new string[0]);
			this.exportedNames = (isValid ? CopyNames(exportedNames, 128, module: false) : new string[0]);
			Error = error ?? string.Empty;
		}

		internal static bool IsSafeName(string name, bool module)
		{
			if (string.IsNullOrEmpty(name) || name.Length > 128 || name == "." || name == "..")
			{
				return false;
			}
			foreach (char c in name)
			{
				bool flag = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '.' || c == '-';
				if (!module)
				{
					flag = flag || c == '?' || c == '@' || c == '$';
				}
				if (!flag)
				{
					return false;
				}
			}
			return true;
		}

		private static string[] CopyNames(IEnumerable<string> values, int maximum, bool module)
		{
			List<string> list = new List<string>();
			HashSet<string> hashSet = new HashSet<string>(module ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal);
			if (values != null)
			{
				int num = 0;
				foreach (string value in values)
				{
					if (++num > 4096)
					{
						break;
					}
					if (IsSafeName(value, module) && hashSet.Add(value))
					{
						list.Add(value);
					}
					if (list.Count == maximum)
					{
						break;
					}
				}
			}
			return list.ToArray();
		}
	}
}
