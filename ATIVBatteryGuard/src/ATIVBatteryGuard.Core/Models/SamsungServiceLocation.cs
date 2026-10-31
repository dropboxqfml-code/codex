using System;

namespace ATIVBatteryGuard.Core.Models
{
	public sealed class SamsungServiceLocation
	{
		public bool Found { get; private set; }

		public string Path { get; private set; }

		public string FileName { get; private set; }

		public string Source { get; private set; }

		public string Category { get; private set; }

		public string ReasonCode { get; private set; }

		public bool CanEnumerateDirectory { get; private set; }

		// Local-only collection boundary. Never include this path in reports or logs.
		public string CollectionDirectory { get; private set; }

		public SamsungServiceLocation(bool found, string path, string fileName, string source, string category, string reasonCode, bool canEnumerateDirectory = false, string collectionDirectory = null)
		{
			FileName = SafeFileName(fileName);
			Found = found && !string.IsNullOrEmpty(path) && FileName.Length != 0;
			Path = (Found ? path : string.Empty);
			Source = Token(source, "None");
			Category = Token(category, "Invalid");
			ReasonCode = Token(reasonCode, "PATH_SYNTAX_INVALID");
			CanEnumerateDirectory = Found && canEnumerateDirectory;
			CollectionDirectory = Found ? (collectionDirectory ?? string.Empty) : string.Empty;
		}

		internal static string SafeFileName(string value)
		{
			if (string.IsNullOrWhiteSpace(value) || value.Length > 160 || value != value.Trim() || value.EndsWith(".", StringComparison.Ordinal))
			{
				return string.Empty;
			}
			foreach (char c in value)
			{
				if (c != '\\' && c != '/' && c != ':' && c != '*' && c != '?' && c != '"' && c != '<' && c != '>' && c != '|' && !char.IsControl(c))
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
				return string.Empty;
			}
			if (!(value == ".") && !(value == ".."))
			{
				return value;
			}
			return string.Empty;
		}

		private static string Token(string value, string fallback)
		{
			if (string.IsNullOrEmpty(value) || value.Length > 64)
			{
				return fallback;
			}
			foreach (char c in value)
			{
				if ((c < 'a' || c > 'z') && (c < 'A' || c > 'Z') && (c < '0' || c > '9') && c != '_')
				{
					return fallback;
				}
			}
			return value;
		}
	}
}
