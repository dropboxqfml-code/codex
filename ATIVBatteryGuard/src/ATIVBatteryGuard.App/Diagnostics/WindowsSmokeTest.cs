using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
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
				SmokeInteraction interaction = new SmokeInteraction();
				model = new MainViewModel(new SyntheticBattery(), store, new LocalLog(temporary), interaction);
				window = (MainWindow)(app.MainWindow = new MainWindow
				{
					DataContext = model,
					ShowActivated = false
				});
				window.Show();
				window.UpdateLayout();
				await Idle(app);
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
