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

		public bool ConfirmSamsungAnalysisExport()
		{
			return MessageBox.Show(Application.Current.MainWindow,
				"설치된 Samsung Settings 앱의 실행 파일·DLL 복사본과 파일 정보가 로컬 ZIP에 포함됩니다.\n\n"
				+ "등록된 Samsung Settings의 전용 설치 폴더만 조사합니다. 위치 정보가 비어 있으면 전용 후보 폴더 최대 6곳을 확인합니다. 최대 16개 파일, 파일당 16MiB, 총 24MiB로 제한합니다.\n\n"
				+ "파일은 실행하거나 변경하지 않습니다. 설정·로그·개인 문서·드라이버는 포함하지 않으며 자동 업로드하지 않습니다.\n"
				+ "위치나 파일을 확인하지 못하면 원인을 담은 점검 보고서만 ZIP에 포함합니다.\n\n분석 자료 ZIP을 만들까요?",
				"Samsung Settings 분석 자료", MessageBoxButton.YesNo, MessageBoxImage.Question, MessageBoxResult.No) == MessageBoxResult.Yes;
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
			EnsureLocalDirectory();
			string path = "diagnostics-" + DateTime.UtcNow.ToString("yyyyMMddTHHmmss") + "-" + Guid.NewGuid().ToString("N") + ".txt";
			using (FileStream stream = new FileStream(Path.Combine(directory, path), FileMode.CreateNew, FileAccess.Write, FileShare.None))
			{
				using (StreamWriter streamWriter = new StreamWriter(stream, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false)))
				{
					streamWriter.Write(text);
				}
			}
			return "진단을 설정 폴더의 새 diagnostics 파일에 저장했습니다. 업로드하지 않았습니다.";
		}

		private void EnsureLocalDirectory()
		{
			LocalPathPolicy.NormalizeDirectory(directory);
			Directory.CreateDirectory(directory);
		}
	}
}
