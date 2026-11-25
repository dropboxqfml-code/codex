using System;
using System.Diagnostics;
using System.Collections.Generic;
using System.Linq;
using System.IO;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using Microsoft.Win32;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Diagnostics;

namespace ATIVBatteryGuard.Services
{
	public sealed class LocalUserInteraction : IUserInteraction
	{
		private readonly string directory;

		private readonly LocalLog log;
        private string recentObservationNotice = "";
        public string RecentObservationNotice
        {
            get
            {
                string recovery = ObservationBundle.RecoveryNotice(directory);
                return recentObservationNotice + (recentObservationNotice.Length > 0 && recovery.Length > 0 ? "\n" : "") + recovery;
            }
        }

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

		public string SaveBatteryObservation(string text)
		{
			string fileName = SaveLocalText("battery-observation-", text);
            RememberObservation(Path.Combine(directory, fileName), SavedBatteryObservation.Parse(text, fileName, Path.Combine(directory, fileName)));
			return "관찰 TXT 저장 완료: " + fileName + " · ‘관찰 저장 폴더 열기’에서 확인하세요. 업로드하지 않았습니다.";
		}

        public SavedBatteryObservation OpenBatteryObservation()
        {
            var dialog = new OpenFileDialog
            {
                Title = "저장된 배터리 관찰 TXT 열기",
                InitialDirectory = directory,
                Filter = "배터리 관찰 TXT (*.txt)|*.txt",
                CheckFileExists = true,
                Multiselect = false
            };
            if (dialog.ShowDialog(Application.Current.MainWindow) != true) return null;
            return ReadObservationFile(dialog.FileName);
        }

        public string ExportObservationBundle(SavedBatteryObservation record, string noteText)
        {
            var bundle = ObservationBundle.Create(record, noteText);
            var dialog = new SaveFileDialog
            {
                Title = "관찰 TXT와 현재 입력한 메모를 함께 내보내기",
                Filter = "ATIV 관찰 묶음 (*.ativrecord)|*.ativrecord",
                DefaultExt = ObservationBundle.Extension, AddExtension = true,
                FileName = Path.GetFileNameWithoutExtension(record.FileName) + ObservationBundle.Extension,
                InitialDirectory = directory, OverwritePrompt = false
            };
            if (dialog.ShowDialog(Application.Current.MainWindow) != true) return null;
            if (!dialog.FileName.EndsWith(ObservationBundle.Extension, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException(".ativrecord 확장자로 새 파일 이름을 지정하세요.");
            if (File.Exists(dialog.FileName))
                throw new InvalidDataException("기존 파일을 보존합니다. 다른 파일 이름으로 다시 내보내세요.");
            bundle.Export(dialog.FileName);
            return Path.GetFileName(dialog.FileName);
        }

        public ObservationBundle OpenObservationBundle()
        {
            var dialog = new OpenFileDialog
            {
                Title = "TXT·메모 묶음 불러오기",
                Filter = "ATIV 관찰 묶음 (*.ativrecord)|*.ativrecord",
                InitialDirectory = directory, CheckFileExists = true, Multiselect = false
            };
            return dialog.ShowDialog(Application.Current.MainWindow) == true
                ? ObservationBundle.ReadFile(dialog.FileName) : null;
        }

        public SavedBatteryObservation ImportObservationBundle(ObservationBundle bundle)
        {
            var record = bundle.Import(directory);
            // A recent-index failure does not undo a successfully restored TXT and note.
            // The snapshot carries its exact, internally generated destination path.
            RememberObservation(record.SourcePath, record);
            return record;
        }

        private SavedBatteryObservation ReadObservationFile(string path)
        {
            path = LocalPathPolicy.NormalizeFile(path);
            SavedBatteryObservation observation;
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
                observation = SavedBatteryObservation.Read(stream, Path.GetFileName(path), path);
            if (observation.Success) RememberObservation(path, observation);
            return observation;
        }

        private void RememberObservation(string path, SavedBatteryObservation observation)
        {
            try
            {
                new RecentObservationStore(directory).Record(path, observation);
                recentObservationNotice = "";
            }
            catch
            {
                recentObservationNotice = "TXT 작업은 완료했지만 최근 기록 목록을 갱신하지 못했습니다.";
            }
        }

        public IReadOnlyList<RecentObservationEntry> ReadRecentObservations()
        {
            var notes = new ObservationNoteStore(directory);
            return new RecentObservationStore(directory).Load()
                .Select(entry => entry.WithNote(string.IsNullOrEmpty(entry.NoteKey) ? ObservationNote.Empty : notes.Load(entry.NoteKey)))
                .ToList().AsReadOnly();
        }

        public SavedBatteryObservation OpenRecentObservation(RecentObservationEntry entry)
        {
            return ReadObservationFile(entry.Path);
        }

        public ObservationNote LoadObservationNote(SavedBatteryObservation record)
        {
            return new ObservationNoteStore(directory).Load(record.NoteKey);
        }

        public ObservationNote SaveObservationNote(SavedBatteryObservation record, string text, string expectedRevision)
        {
            return new ObservationNoteStore(directory).Save(record.NoteKey, text, expectedRevision);
        }

        public ObservationLossChoice ConfirmUnsavedObservationNote(string fileName, string action)
        {
            string message = fileName + "의 수정 중인 메모를 확인하세요.\n\n"
                + "예를 누르면 메모를 저장한 뒤 " + action + " 작업을 진행합니다.\n"
                + "아니요를 누르면 저장 없이 진행하고, 취소를 누르면 메모로 돌아갑니다.";
            var choice = MessageBox.Show(Application.Current.MainWindow, message, "관찰 메모 저장 확인",
                MessageBoxButton.YesNoCancel, MessageBoxImage.Question, MessageBoxResult.Cancel);
            return choice == MessageBoxResult.Yes ? ObservationLossChoice.Save
                : choice == MessageBoxResult.No ? ObservationLossChoice.Discard : ObservationLossChoice.Cancel;
        }

        public ObservationLossChoice ConfirmUnsavedObservation(string action)
        {
            string message = "저장 확인이 필요한 관찰 기록이 있습니다.\n\n"
                + "예를 누르면 관찰을 중단하고 TXT를 저장한 뒤 " + action + " 작업을 진행합니다.\n"
                + "아니요를 누르면 저장 없이 진행합니다.\n취소를 누르면 현재 기록으로 돌아갑니다.";
            var result = MessageBox.Show(Application.Current.MainWindow, message, "관찰 기록 저장 확인",
                MessageBoxButton.YesNoCancel, MessageBoxImage.Question, MessageBoxResult.Cancel);
            return result == MessageBoxResult.Yes ? ObservationLossChoice.Save
                : result == MessageBoxResult.No ? ObservationLossChoice.Discard : ObservationLossChoice.Cancel;
        }

		public string SaveManualProtectionResult(string text)
		{
			string fileName = SaveLocalText("manual-control-", text);
			return "제어 결과 TXT 저장 완료: " + fileName + " · ‘결과 저장 폴더 열기’에서 확인하세요. 업로드하지 않았습니다.";
		}

		private string SaveLocalText(string prefix, string text)
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
			return path;
		}

		private void EnsureLocalDirectory()
		{
			LocalPathPolicy.NormalizeDirectory(directory);
			Directory.CreateDirectory(directory);
		}
	}
}
