using System;
using System.Collections.Generic;
using System.IO;
using System.Security;
using System.Text;

namespace ATIVBatteryGuard.Core.Storage
{
	public sealed class LocalLog
	{
		private const long MaximumBytes = 262144L;

		private static readonly HashSet<string> AllowedEvents = new HashSet<string>(StringComparer.Ordinal)
		{
			"APP_STARTED", "APP_STOPPED", "SETTINGS_LOADED", "SETTINGS_RECOVERED", "SETTINGS_SAVED", "SETTINGS_SAVE_FAILED", "BATTERY_READ_FAILED", "DIAGNOSTICS_READ", "DIAGNOSTICS_FAILED", "MOCK_ENABLED",
			"MOCK_DISABLED", "MOCK_MODE_CHANGED", "HARDWARE_WRITE_REJECTED", "UI_ACTION_FAILED", "HARDWARE_PROBE_STARTED", "HARDWARE_PROBE_SAVED", "HARDWARE_PROBE_FAILED", "SAMSUNG_BUNDLE_STARTED", "SAMSUNG_BUNDLE_SAVED", "SAMSUNG_BUNDLE_FAILED",
			"SAMSUNG_BUNDLE_REPORT_ONLY", "SAMSUNG_FILE_INSPECTION_STARTED", "SAMSUNG_FILE_INSPECTION_SAVED", "SAMSUNG_FILE_INSPECTION_FAILED"
		};

		private readonly object sync = new object();

		private readonly string directory;

		public string LogPath { get; private set; }

		public string LastError { get; private set; }

		public LocalLog(string directory)
		{
			try
			{
				this.directory = LocalPathPolicy.NormalizeDirectory(directory);
				LogPath = Path.Combine(this.directory, "application.log");
			}
			catch (Exception ex) when (IsFileError(ex))
			{
				LogPath = string.Empty;
				LastError = "안전한 로그 저장 위치를 확인할 수 없습니다.";
			}
		}

		public void Write(string eventCode)
		{
			lock (sync)
			{
				if (string.IsNullOrEmpty(LogPath))
				{
					return;
				}
				string text = ((eventCode != null && AllowedEvents.Contains(eventCode)) ? eventCode : "UNRECOGNIZED_EVENT");
				try
				{
					LocalPathPolicy.EnsureNoReparsePoints(LogPath);
					Directory.CreateDirectory(directory);
					string text2 = LogPath + ".previous";
					LocalPathPolicy.EnsureNoReparsePoints(text2);
					if (File.Exists(LogPath) && new FileInfo(LogPath).Length >= 262144)
					{
						if (File.Exists(text2))
						{
							File.Delete(text2);
						}
						File.Move(LogPath, text2);
					}
					using (StreamWriter streamWriter = new StreamWriter(LogPath, append: true, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false)))
					{
						streamWriter.WriteLine(DateTime.UtcNow.ToString("o") + " " + text);
					}
					LastError = string.Empty;
				}
				catch (Exception ex) when (IsFileError(ex))
				{
					LastError = "로컬 로그를 기록하지 못했습니다.";
				}
			}
		}

		private static bool IsFileError(Exception ex)
		{
			if (!(ex is IOException) && !(ex is UnauthorizedAccessException) && !(ex is ArgumentException) && !(ex is NotSupportedException))
			{
				return ex is SecurityException;
			}
			return true;
		}
	}
}
