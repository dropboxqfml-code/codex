using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Diagnostics;

namespace ATIVBatteryGuard.Services
{
	public sealed class LocalUserInteraction : IUserInteraction
	{
		private readonly string directory;

		private readonly LocalLog log;

		public LocalUserInteraction(string directory, LocalLog log)
		{
			this.directory = directory;
			this.log = log;
		}

		public DeviceDiagnosticsResult ReadDiagnostics()
		{
			return new DeviceDiagnostics().ReadResult();
		}

		public void CopyDiagnostics(string text)
		{
			Clipboard.SetText(text);
		}

		public void OpenSettingsFolder()
		{
			EnsureLocalDirectory();
			Process.Start(new ProcessStartInfo
			{
				FileName = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "explorer.exe"),
				Arguments = "\"" + directory + "\"",
				UseShellExecute = false
			});
		}

		public void ShowLog()
		{
			EnsureLocalDirectory();
			LocalPathPolicy.EnsureNoReparsePoints(log.LogPath);
			string text = "아직 로그 기록이 없습니다.";
			if (File.Exists(log.LogPath))
			{
				using (FileStream fileStream = new FileStream(log.LogPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
				{
					if (fileStream.Length > 1048576)
					{
						throw new IOException();
					}
					using (StreamReader streamReader = new StreamReader(fileStream, Encoding.UTF8))
					{
						text = streamReader.ReadToEnd();
					}
				}
			}
			Window window = new Window();
			window.Title = "ATIV Battery Guard · 로컬 로그";
			window.Width = 760.0;
			window.Height = 500.0;
			window.Owner = Application.Current.MainWindow;
			window.WindowStartupLocation = WindowStartupLocation.CenterOwner;
			window.Content = new TextBox
			{
				Text = text,
				IsReadOnly = true,
				AcceptsReturn = true,
				TextWrapping = TextWrapping.Wrap,
				VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
				Margin = new Thickness(16.0)
			};
			window.ShowDialog();
		}

		public string SaveDiagnostics(string text)
		{
			SaveLocalText("diagnostics-", text);
			return "진단을 설정 폴더의 새 diagnostics 파일에 저장했습니다. 업로드하지 않았습니다.";
		}

		public string SaveSamsungFileInspection(string text)
		{
			SaveLocalText("samsung-files-", text);
			return "삼성 파일 정보를 새 samsung-files TXT에 저장했습니다.";
		}

		private void SaveLocalText(string prefix, string text)
		{
			EnsureLocalDirectory();
			string path = prefix + DateTime.UtcNow.ToString("yyyyMMddTHHmmss") + "-" + Guid.NewGuid().ToString("N") + ".txt";
			using (FileStream stream = new FileStream(Path.Combine(directory, path), FileMode.CreateNew, FileAccess.Write, FileShare.None))
			{
				using (StreamWriter streamWriter = new StreamWriter(stream, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false)))
				{
					streamWriter.Write(text);
				}
			}
		}

		private void EnsureLocalDirectory()
		{
			LocalPathPolicy.NormalizeDirectory(directory);
			Directory.CreateDirectory(directory);
		}
	}
}
