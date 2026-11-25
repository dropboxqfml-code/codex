using System;
using System.Diagnostics;
using System.Collections.Generic;
using System.IO;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Automation.Peers;
using ATIVBatteryGuard.Controls;
using System.Windows.Threading;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Services;
using ATIVBatteryGuard.ViewModels;
using ATIVBatteryGuard.Views;

namespace ATIVBatteryGuard.Diagnostics
{
	internal static class WindowsSmokeTest
	{
		private sealed class SmokeFailure : Exception
		{
			public string Code { get; }

			public SmokeFailure(string code)
			{
				Code = code;
			}
		}

		private sealed class SyntheticBattery : IBatteryStatusProvider
		{
			public BatterySnapshot Read()
			{
				return new BatterySnapshot(80, ExternalPowerStatus.Connected, BatteryChargeState.NotCharging, string.Empty);
			}
		}

		private sealed class SmokeInteraction : IUserInteraction
		{
			public bool Copied { get; private set; }

			public bool Saved { get; private set; }

			public DeviceDiagnosticsResult ReadDiagnostics()
			{
				return new DeviceDiagnostics().ReadResult();
			}

			public void CopyDiagnostics(string text)
			{
				Copied = !string.IsNullOrEmpty(text);
			}

			public string SaveDiagnostics(string text)
			{
				Saved = !string.IsNullOrEmpty(text);
				return "시험 결과 저장 경로 확인";
			}

			public void OpenSettingsFolder()

			{
				throw new SmokeFailure("UNEXPECTED_SHELL_ACTION");
			}

			public string SaveSamsungFileInspection(string text)
			{
				throw new SmokeFailure("UNEXPECTED_FILE_INSPECTION");
			}

			public string SaveBatteryObservation(string text)
			{
				return "관찰 기록 저장 모의 처리";
			}

            public string BundleFile;
            public string ExportObservationBundle(SavedBatteryObservation record, string noteText)
            {
                BundleFile = Path.Combine(SourceDirectory, Guid.NewGuid().ToString("N") + ObservationBundle.Extension);
                ObservationBundle.Create(record, noteText).Export(BundleFile);
                return Path.GetFileName(BundleFile);
            }
            public ObservationBundle OpenObservationBundle() { return ObservationBundle.ReadFile(BundleFile); }
            public SavedBatteryObservation ImportObservationBundle(ObservationBundle bundle)
            {
                var record = bundle.Import(SourceDirectory);
                RecentEntries = new RecentObservationStore(SourceDirectory).Record(record.SourcePath, record);
                return record;
            }
            public string SourceDirectory;
            public ObservationNoteStore Notes;
            public ObservationLossChoice NoteChoice = ObservationLossChoice.Discard;
            public ObservationNote LoadObservationNote(SavedBatteryObservation record) { return Notes.Load(record.NoteKey); }
            public ObservationNote SaveObservationNote(SavedBatteryObservation record, string text, string expectedRevision)
            { return Notes.Save(record.NoteKey, text, expectedRevision); }
            public ObservationLossChoice ConfirmUnsavedObservationNote(string fileName, string action) { return NoteChoice; }

            public ObservationLossChoice ObservationChoice = ObservationLossChoice.Discard;
            public IReadOnlyList<RecentObservationEntry> RecentEntries = Array.AsReadOnly(new RecentObservationEntry[0]);
            public ObservationLossChoice ConfirmUnsavedObservation(string action) { return ObservationChoice; }
            public string RecentObservationNotice => "";
            public IReadOnlyList<RecentObservationEntry> ReadRecentObservations()
            {
                var rows = new List<RecentObservationEntry>();
                foreach (var entry in RecentEntries) rows.Add(entry.WithNote(Notes.Load(entry.NoteKey)));
                return rows.AsReadOnly();
            }
            public SavedBatteryObservation OpenRecentObservation(RecentObservationEntry entry) { return OpenBatteryObservation(); }

            public int ObservationEndSeconds;
            public SavedBatteryObservation OpenBatteryObservation()
            {
                var session = new BatteryObservationSession();
                session.Start();
                session.Record(TimeSpan.Zero, new BatterySnapshot(80, ExternalPowerStatus.Connected, BatteryChargeState.NotCharging, ""));
                if (ObservationEndSeconds > 0)
                    session.Record(TimeSpan.FromSeconds(ObservationEndSeconds),
                        new BatterySnapshot(85, ExternalPowerStatus.Connected, BatteryChargeState.Charging, ""));
                session.Stop();
                return SavedBatteryObservation.Parse(session.ExportText(), "smoke-observation.txt", Path.Combine(SourceDirectory, "smoke-observation.txt"));
            }

			public string SaveManualProtectionResult(string text)
			{
				throw new SmokeFailure("UNEXPECTED_MANUAL_RESULT_SAVE");
			}

			public void ShowLog()
			{
				throw new SmokeFailure("UNEXPECTED_LOG_ACTION");
			}
		}

		private sealed class BindingErrorListener : TraceListener
		{
			private int errors;

			public int ErrorCount => Volatile.Read(ref errors);

			public override void Write(string message)
			{
			}

			public override void WriteLine(string message)
			{
			}

			public override void TraceEvent(TraceEventCache cache, string source, TraceEventType type, int id, string message)
			{
				if ((type & (TraceEventType)3) != 0)
				{
					Interlocked.Increment(ref errors);
				}
			}

			public override void TraceEvent(TraceEventCache cache, string source, TraceEventType type, int id, string format, params object[] args)
			{
				TraceEvent(cache, source, type, id, string.Empty);
			}
		}

		[DataContract]
		private sealed class SmokeReport
		{
			[DataMember(Name = "schemaVersion")]
			public int SchemaVersion = 1;

			[DataMember(Name = "status")]
			public string Status = "failed";

			[DataMember(Name = "guiPassed")]
			public bool GuiPassed;

			[DataMember(Name = "hardwareWritesPerformed")]
			public bool HardwareWritesPerformed = false;

			[DataMember(Name = "bindingErrors")]
			public int BindingErrors;

			[DataMember(Name = "nativePowerStatus")]
			public string NativePowerStatus = "not-run";

			[DataMember(Name = "nativeWmiStatus")]
			public string NativeWmiStatus = "not-run";

			[DataMember(Name = "errors")]
			public string[] Errors = new string[0];
		}

		public static async Task<int> RunAsync(Application app, string reportPath)
		{
			FileStream output;
			try
			{
				if (!Path.IsPathRooted(reportPath) || !reportPath.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
				{
					return 2;
				}
				LocalPathPolicy.NormalizeDirectory(Path.GetDirectoryName(reportPath));
				LocalPathPolicy.EnsureNoReparsePoints(reportPath);
				output = new FileStream(reportPath, FileMode.CreateNew, FileAccess.Write, FileShare.None);
			}
			catch
			{
				return 2;
			}
			SmokeReport report = new SmokeReport();
			BindingErrorListener bindingListener = new BindingErrorListener();
			SourceLevels originalTraceLevel = PresentationTraceSources.DataBindingSource.Switch.Level;
			string temporary = null;
			MainViewModel model = null;
			MainWindow window = null;
			app.ShutdownMode = ShutdownMode.OnExplicitShutdown;
			try
			{
				PresentationTraceSources.DataBindingSource.Listeners.Add(bindingListener);
				PresentationTraceSources.DataBindingSource.Switch.Level = SourceLevels.Error;
				string path = LocalPathPolicy.NormalizeDirectory(Path.GetTempPath());
				temporary = Path.Combine(path, "ativ-gui-smoke-" + Guid.NewGuid().ToString("N"));
				Directory.CreateDirectory(temporary);
				SettingsStore store = new SettingsStore(temporary);
				SmokeInteraction interaction = new SmokeInteraction { SourceDirectory = temporary, Notes = new ObservationNoteStore(temporary) };
                interaction.RecentEntries = new RecentObservationStore(temporary).Record(
                    Path.Combine(temporary, "smoke-observation.txt"), interaction.OpenBatteryObservation());
				model = new MainViewModel(new SyntheticBattery(), store, new LocalLog(temporary), interaction);
				window = (MainWindow)(app.MainWindow = new MainWindow
				{
					DataContext = model,
					ShowActivated = false
				});
				window.Show();
				window.UpdateLayout();
				await Idle(app);
                await CheckChartInputAsync(app, window, model);
                Execute(Find<Button>(window, "OpenSavedObservationButton"));
                await Idle(app);
                Require(model.SavedObservationVisible && model.SavedObservationName == "smoke-observation.txt"
                    && !model.ObservationActive, "SAVED_OBSERVATION_BINDING_INVALID");
                var savedChart = Find<BatteryObservationChart>(window, "SavedObservationChart");
                Require(savedChart.IsSavedRecord && savedChart.Graph.Points.Count == 1, "SAVED_GRAPH_BINDING_INVALID");
                SendChartKey(savedChart, Key.Home);
                Require(savedChart.SelectedPointText.Contains("80%"), "SAVED_GRAPH_SELECTION_INVALID");
                var savedPeer = UIElementAutomationPeer.CreatePeerForElement(savedChart);
                Require(savedPeer.GetHelpText().Contains("파일에 저장된 과거"), "SAVED_GRAPH_PROVENANCE_INVALID");
                var noteA = Find<TextBox>(window, "ANoteText");
                noteA.SetCurrentValue(TextBox.TextProperty, "보호 켜기 관찰");
                noteA.GetBindingExpression(TextBox.TextProperty)?.UpdateSource();
                await Idle(app);
                Require(model.SavedObservationNote.HasChanges, "NOTE_A_EDIT_BINDING_INVALID");
                Execute(Find<Button>(window, "SaveANoteButton"));
                await Idle(app);
                Require(!model.SavedObservationNote.HasChanges && model.SavedObservationNote.Preview.Contains("보호 켜기"),
                    "NOTE_A_SAVE_INVALID");
                Require(model.RecentObservations[0].NotePreview.Contains("보호 켜기"), "NOTE_RECENT_PREVIEW_INVALID");
                interaction.ObservationEndSeconds = 120;
                Execute(Find<Button>(window, "OpenComparisonObservationButton"));
                await Idle(app);
                window.UpdateLayout();
                var comparisonChart = Find<BatteryObservationChart>(window, "ComparisonObservationChart");
                Require(model.ComparisonObservationVisible && model.SavedObservationDomainSeconds == 120
                    && savedChart.MinimumDomainSeconds == 120 && comparisonChart.MinimumDomainSeconds == 120,
                    "COMPARISON_SHARED_AXIS_INVALID");
                Require(savedChart.Graph.Points.Count == 1 && comparisonChart.Graph.Points.Count == 2,
                    "COMPARISON_FILE_BINDING_INVALID");
                SendChartKey(comparisonChart, Key.End);
                Require(comparisonChart.SelectedPointText.Contains("2:00") && comparisonChart.SelectedPointText.Contains("85%"),
                    "COMPARISON_SELECTION_INVALID");
                comparisonChart.SelectAt(new Point(comparisonChart.ActualWidth - 18,
                    32 + (comparisonChart.ActualHeight - 80) * 0.15));
                Require(comparisonChart.SelectedPointText.Contains("2/2"), "COMPARISON_POINTER_SCALE_INVALID");
                var noteB = Find<TextBox>(window, "BNoteText");
                noteB.SetCurrentValue(TextBox.TextProperty, "보호 해제 관찰");
                noteB.GetBindingExpression(TextBox.TextProperty)?.UpdateSource();
                await Idle(app);
                interaction.NoteChoice = ObservationLossChoice.Cancel;
                Require(!model.TryPrepareToClose() && model.ComparisonObservationNote.HasChanges, "NOTE_CLOSE_CANCEL_INVALID");
                Execute(Find<Button>(window, "SaveBNoteButton"));
                await Idle(app);
                Require(model.SavedObservationNote.Text == "보호 켜기 관찰" && model.ComparisonObservationNote.Text == "보호 해제 관찰",
                    "NOTE_AB_IDENTITY_INVALID");
                interaction.NoteChoice = ObservationLossChoice.Discard;
                Execute(Find<Button>(window, "CloseComparisonObservationButton"));
                await Idle(app);
                Require(!model.ComparisonObservationVisible && model.SavedObservationVisible
                    && savedChart.MinimumDomainSeconds == 60 && comparisonChart.Graph.Points.Count == 0,
                    "COMPARISON_CLOSE_INVALID");
                interaction.ObservationEndSeconds = 0;
                model.CloseSavedObservationCommand.Execute(null);
                await Idle(app);
                Require(!model.SavedObservationVisible && savedChart.Graph.Points.Count == 0, "SAVED_GRAPH_CLOSE_INVALID");
                Require(Find<ListBox>(window, "RecentObservationsList").Items.Count == 1, "RECENT_LIST_BINDING_INVALID");
                var recentList = Find<ListBox>(window, "RecentObservationsList");
                recentList.SelectedIndex = 0;
                recentList.GetBindingExpression(Selector.SelectedItemProperty)?.UpdateSource();
                await Idle(app);
                Execute(Find<Button>(window, "OpenRecentObservationButton"));
                await Idle(app);
                Require(model.SavedObservationVisible, "RECENT_OPEN_BINDING_INVALID");
                Require(model.SavedObservationNote.Text == "보호 켜기 관찰", "NOTE_REOPEN_INVALID");
                Execute(Find<Button>(window, "ExportObservationBundleButton"));
                await Idle(app);
                Require(File.Exists(interaction.BundleFile), "BUNDLE_EXPORT_BUTTON_INVALID");
                model.SavedObservationNote.Text = "메모 초안 보관";
                interaction.NoteChoice = ObservationLossChoice.Cancel;
                Execute(Find<Button>(window, "ImportObservationBundleButton"));
                await Idle(app);
                Require(model.SavedObservationNote.Text == "메모 초안 보관", "BUNDLE_IMPORT_CANCEL_LOST_DRAFT");
                interaction.NoteChoice = ObservationLossChoice.Discard;
                Execute(Find<Button>(window, "ImportObservationBundleButton"));
                await Idle(app);
                Require(model.SavedObservationNote.Text == "보호 켜기 관찰" && savedChart.Graph.SampleCount == 1,
                    "BUNDLE_IMPORT_NOTE_OR_GRAPH_INVALID");
                Execute(Find<Button>(window, "ImportComparisonBundleButton"));
                await Idle(app);
                Require(model.ComparisonObservationNote.Text == "보호 켜기 관찰" && model.ComparisonObservationVisible,
                    "BUNDLE_COMPARISON_IMPORT_INVALID");
                Execute(Find<Button>(window, "ExportComparisonBundleButton"));
                await Idle(app);
                Require(ObservationBundle.ReadFile(interaction.BundleFile).NoteText == "보호 켜기 관찰",
                    "BUNDLE_COMPARISON_EXPORT_INVALID");
                model.CloseSavedObservationCommand.Execute(null);
                model.StartBatteryObservationCommand.Execute(null); model.RefreshBattery();
                interaction.ObservationChoice = ObservationLossChoice.Cancel;
                Require(!model.TryPrepareToClose() && model.ObservationActive, "OBSERVATION_CANCEL_INVALID");
                interaction.ObservationChoice = ObservationLossChoice.Save;
                Require(model.TryPrepareToClose() && !model.HasUnsavedObservation, "OBSERVATION_FINAL_SAVE_INVALID");
                interaction.ObservationChoice = ObservationLossChoice.Discard;
                model.ClearBatteryObservationCommand.Execute(null);
				Button apply = Find<Button>(window, "MockApplyButton");
				Button save = Find<Button>(window, "SavePreferencesButton");
				CheckBox mock = Find<CheckBox>(window, "MockSwitch");
				RadioButton protection = Find<RadioButton>(window, "ProtectionChoice");
				RadioButton normal = Find<RadioButton>(window, "NormalChoice");
				TextBlock actual = Find<TextBlock>(window, "ActualHardwareState");
				TextBlock textBlock = Find<TextBlock>(window, "BatteryChargeStateLabel");
				Require(!apply.IsEnabled && !model.CanApply && !model.IsMockMode, "REAL_APPLY_NOT_DISABLED");
				string physicalText = actual.Text;
				Require(physicalText.Contains("미지원") && textBlock.Text == "충전 중 아님", "INITIAL_STATE_INVALID");
				Require(!model.CanExportDiagnostics && !model.CopyDiagnosticsCommand.CanExecute(null), "STALE_DIAGNOSTICS_EXPORT_ENABLED");
				Select(protection, value: true);
				Select(mock, value: true);
				await Idle(app);
				Require(model.IsProtectionSelected && model.IsMockMode && apply.IsEnabled, "MOCK_BINDINGS_INVALID");
				Execute(apply);
				Require(model.MockActualModeText.Contains("80%") && actual.Text == physicalText, "MOCK_ON_INVALID");
				Select(normal, value: true);
				Execute(apply);
				Require(model.MockActualModeText.Contains("100%") && actual.Text == physicalText, "MOCK_OFF_INVALID");
				Select(mock, value: false);
				await Idle(app);
				Require(!apply.IsEnabled && !model.CanApply, "MOCK_DISABLE_INVALID");
				Select(protection, value: true);
				Execute(save);
				Require(new SettingsStore(temporary).Load().Settings.DesiredMode == ChargeMode.Protection80, "PREFERENCE_SAVE_INVALID");
				await model.RefreshDiagnosticsAsync();
				report.NativeWmiStatus = (model.DiagnosticsSucceeded ? "complete" : "partial-or-unavailable");
				Require(model.CanExportDiagnostics && !model.DiagnosticsBusy && actual.Text == physicalText, "DIAGNOSTICS_STATE_INVALID");
				model.CopyDiagnosticsCommand.Execute(null);
				model.SaveDiagnosticsCommand.Execute(null);
				Require(interaction.Copied && interaction.Saved, "LOCAL_DIAGNOSTIC_ACTION_INVALID");
				BatterySnapshot batterySnapshot = new WindowsBatteryStatusProvider().Read();
				report.NativePowerStatus = (string.IsNullOrEmpty(batterySnapshot.Error) ? "available" : "unavailable");
				model.Dispose();
				using (MainViewModel mainViewModel = new MainViewModel(new SyntheticBattery(), new SettingsStore(temporary), new LocalLog(temporary), interaction))
				{
					Require(mainViewModel.IsProtectionSelected && !mainViewModel.IsMockMode && !mainViewModel.CanApply && mainViewModel.ActualModeText.Contains("미지원"), "RESTART_STATE_INVALID");
				}
				await Idle(app);
				Require(bindingListener.ErrorCount == 0, "WPF_BINDING_ERRORS");
				report.GuiPassed = true;
				report.Status = "passed";
			}
			catch (SmokeFailure smokeFailure)
			{
				report.Errors = new string[1] { smokeFailure.Code };
			}
			catch
			{
				report.Errors = new string[1] { "GUI_SMOKE_FAILED" };
			}
			finally
			{
				try
				{
					model?.Dispose();
					window?.Close();
				}
				catch
				{
					report.Status = "failed";
					report.Errors = new string[1] { "GUI_CLEANUP_FAILED" };
				}
				PresentationTraceSources.DataBindingSource.Listeners.Remove(bindingListener);
				PresentationTraceSources.DataBindingSource.Switch.Level = originalTraceLevel;
				report.BindingErrors = bindingListener.ErrorCount;
				if (report.BindingErrors != 0)
				{
					report.Status = "failed";
					report.Errors = new string[1] { "WPF_BINDING_ERRORS" };
				}
				try
				{
					if (temporary != null)
					{
						Directory.Delete(temporary, recursive: true);
					}
				}
				catch
				{
					report.Status = "failed";
					report.Errors = new string[1] { "TEMP_CLEANUP_FAILED" };
				}
			}
			try
			{
				using (output)
				{
					new DataContractJsonSerializer(typeof(SmokeReport)).WriteObject((Stream)output, (object)report);
					output.Flush(flushToDisk: true);
				}
			}
			catch
			{
				output.Dispose();
				return 2;
			}
			return (!(report.Status == "passed") || report.BindingErrors != 0) ? 1 : 0;
		}

        private static async Task CheckChartInputAsync(Application app, MainWindow window, MainViewModel model)
        {
            var chart = Find<BatteryObservationChart>(window, "ObservationChart");
            var caption = Find<TextBlock>(window, "ObservationChartSelectionText");
            model.StartBatteryObservationCommand.Execute(null);
            await Idle(app);
            window.UpdateLayout();
            chart.BringIntoView();
            Require(chart.Focusable && chart.IsTabStop, "CHART_NOT_KEYBOARD_REACHABLE");
            try
            {
                var session = new BatteryObservationSession();
                session.Start();
                session.Record(TimeSpan.Zero,
                    new BatterySnapshot(0, ExternalPowerStatus.Disconnected, BatteryChargeState.Discharging, ""));
                session.Record(TimeSpan.FromSeconds(10),
                    new BatterySnapshot(null, ExternalPowerStatus.Unknown, BatteryChargeState.Unknown, ""));
                session.Record(TimeSpan.FromSeconds(40),
                    new BatterySnapshot(100, ExternalPowerStatus.Connected, BatteryChargeState.NotCharging, ""));
                session.Stop();
                chart.SetCurrentValue(BatteryObservationChart.GraphProperty,
                    BatteryObservationGraph.FromSamples(session.Samples, session.Status));
                window.UpdateLayout();
                double plotWidth = Math.Max(0, chart.ActualWidth - 72);
                double plotHeight = Math.Max(0, chart.ActualHeight - 80);
                Require(plotWidth > 0 && plotHeight > 0, "CHART_NOT_LAID_OUT");
                chart.SelectAt(new Point(54, 32 + plotHeight));
                Require(chart.SelectedPointText.Contains("1/2") && chart.SelectedPointText.Contains("0%"),
                    "CHART_MOUSE_FIRST_POINT_INVALID");
                chart.SelectAt(new Point(10, 10));
                Require(chart.SelectedPointText.Contains("1/2"), "CHART_BLANK_CLICK_CHANGED_SELECTION");
                chart.SelectAt(new Point(54 + plotWidth * 40 / 60, 32));
                Require(chart.SelectedPointText.Contains("2/2") && chart.SelectedPointText.Contains("100%"),
                    "CHART_MOUSE_LAST_POINT_INVALID");
                SendChartKey(chart, Key.Left);
                Require(chart.SelectedPointText.Contains("1/2"), "CHART_MOUSE_KEYBOARD_SELECTION_NOT_SHARED");
                SendChartKey(chart, Key.Home);
                Require(chart.SelectedPointText.Contains("1/2") && chart.SelectedPointText.Contains("0%")
                    && chart.SelectedPointText.Contains("방전 중"), "CHART_FIRST_POINT_INVALID");
                SendChartKey(chart, Key.Right);
                Require(chart.SelectedPointText.Contains("2/2") && chart.SelectedPointText.Contains("100%")
                    && chart.SelectedPointText.Contains("0:40"), "CHART_NEXT_POINT_INVALID");
                SendChartKey(chart, Key.Right);
                Require(chart.SelectedPointText.Contains("2/2"), "CHART_MOVED_BEYOND_END");
                SendChartKey(chart, Key.Left);
                Require(chart.SelectedPointText.Contains("1/2"), "CHART_PREVIOUS_POINT_INVALID");
                SendChartKey(chart, Key.End);
                var peer = UIElementAutomationPeer.CreatePeerForElement(chart);
                Require(peer != null && peer.GetItemStatus() == chart.SelectedPointText, "CHART_ACCESSIBILITY_SELECTION_INVALID");
                await Idle(app);
                Require(caption.Text == chart.SelectedPointText, "CHART_SELECTION_BINDING_INVALID");
                chart.SetCurrentValue(BatteryObservationChart.GraphProperty, BatteryObservationGraph.Empty);
                Require(!chart.SelectedPointText.Contains("선택 표본"), "CHART_CLEAR_RETAINED_SELECTION");
                SendChartKey(chart, Key.End);
                Require(!chart.SelectedPointText.Contains("선택 표본"), "CHART_EMPTY_INVENTED_SELECTION");
            }
            finally
            {
                model.ClearBatteryObservationCommand.Execute(null);
            }
        }

        private static void SendChartKey(BatteryObservationChart chart, Key key)
        {
            chart.RaiseEvent(new KeyEventArgs(Keyboard.PrimaryDevice, PresentationSource.FromVisual(chart), 0, key)
            { RoutedEvent = Keyboard.KeyDownEvent });
        }

		private static Task Idle(Application app)
		{
			return app.Dispatcher.InvokeAsync(delegate
			{
			}, DispatcherPriority.ApplicationIdle).Task;
		}

		private static T Find<T>(MainWindow window, string name) where T : FrameworkElement
		{
			return (window.FindName(name) as T) ?? throw new SmokeFailure("MISSING_UI_CONTROL");
		}

		private static void Select(ToggleButton control, bool value)
		{
			control.SetCurrentValue(ToggleButton.IsCheckedProperty, value);
			control.GetBindingExpression(ToggleButton.IsCheckedProperty)?.UpdateSource();
		}

		private static void Execute(Button button)
		{
			Require(button.IsEnabled && button.Command != null && button.Command.CanExecute(button.CommandParameter), "BOUND_COMMAND_DISABLED");
			button.Command.Execute(button.CommandParameter);
		}

		private static void Require(bool condition, string code)
		{
			if (!condition)
			{
				throw new SmokeFailure(code);
			}
		}
	}
}
