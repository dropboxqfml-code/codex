using System;
using System.Text;
using System.Text.RegularExpressions;

namespace ATIVBatteryGuard.Core.Models
{
	public sealed class SamsungBundleResult
	{
		public bool Success { get; private set; }

		public string Message { get; private set; }

		public string FileName { get; private set; }

		public bool ContainsModules { get; private set; }

		public SamsungBundleResult(bool success, string message, string fileName = null, bool containsModules = true)
		{
			FileName = SafeFileName(fileName);
			Success = success && FileName.Length != 0;
			ContainsModules = Success && containsModules;
			Message = SafeMessage(message);
		}

		private static string SafeFileName(string value)
		{
			if (string.IsNullOrWhiteSpace(value) || value.Length > 160)
			{
				return string.Empty;
			}
			foreach (char c in value)
			{
				if (c == '/' || c == '\\' || c == ':' || c == '*' || c == '?' || c == '"' || c == '<' || c == '>' || c == '|' || char.IsControl(c) || (c >= '\u202a' && c <= '\u202e') || (c >= '\u2066' && c <= '\u2069'))
				{
					return string.Empty;
				}
			}
			if (value == "." || value == ".." || value != value.Trim() || value.EndsWith(".", StringComparison.Ordinal))
			{
				return string.Empty;
			}
			return value;
		}

		private static string SafeMessage(string value)
		{
			if (string.IsNullOrWhiteSpace(value))
			{
				return string.Empty;
			}
			if (Regex.IsMatch(value, "[A-Za-z]:[\\\\/]") || value.IndexOf('\\') >= 0 || value.IndexOf('/') >= 0 || value.IndexOf("/home/", StringComparison.OrdinalIgnoreCase) >= 0 || value.IndexOf("/Users/", StringComparison.OrdinalIgnoreCase) >= 0)
			{
				return "분석 파일 작업 결과를 확인하세요. 저장 폴더 경로는 표시하지 않습니다.";
			}
			StringBuilder stringBuilder = new StringBuilder(400);
			foreach (char c in value)
			{
				stringBuilder.Append((char.IsControl(c) || c == '\u2028' || c == '\u2029' || (c >= '\u202a' && c <= '\u202e') || (c >= '\u2066' && c <= '\u2069')) ? ' ' : c);
				if (stringBuilder.Length == 400)
				{
					break;
				}
			}
			return stringBuilder.ToString().Trim();
		}
	}
}
