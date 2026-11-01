using System;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Hardware;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Services;

namespace ATIVBatteryGuard.ViewModels
{
	public sealed class MainViewModel : INotifyPropertyChanged, IDisposable
	{
		private readonly IBatteryStatusProvider battery;

		private readonly SettingsStore store;

		private readonly LocalLog log;

		private readonly IUserInteraction interaction;

		private readonly IHardwareDiagnosticsProvider hardwareDiagnostics;

		private readonly ISamsungAnalysisBundleService samsungAnalysis;

		private readonly Func<bool> confirmSamsungAnalysis;

		private readonly IChargeLimitController physical = new UnsupportedChargeLimitController();

		private MockChargeLimitController mock = new MockChargeLimitController();

		private readonly AppSettings settings;

		private readonly bool canSave;

		private BatterySnapshot snapshot = BatterySnapshot.Unknown(string.Empty);

		private string statusMessage;

		private string diagnosticsText = "‘진단 정보 보기’를 누르면 로컬 장치 정보를 조회합니다.";

		private bool mockMode;

		private bool diagnosticsBusy;

		private bool hasDiagnostics;

		private DeviceDiagnosticsResult device;

		private bool disposed;

		private bool hardwareReportBusy;

		private string hardwareReportText = string.Empty;

		private string standardBatteryRequestText = new WindowsBatteryCapabilitiesReport().AssessmentText;

		private string hardwareReportStatus = "‘진단 파일 만들기’를 누르면 배터리와 삼성 프로그램 정보를 읽어 로컬 파일로 저장합니다.";

		private bool samsungBundleBusy;

		private string samsungBundleStatus = "Samsung Settings 앱 파일을 분석 자료로 복사할 수 있습니다. 생성 전에 포함 내용을 안내합니다.";

		private string samsungBundleFileName = string.Empty;

		public RelayCommand ApplyCommand { get; }

		public RelayCommand SaveCommand { get; }

		public RelayCommand RefreshCommand { get; }

		public RelayCommand ShowDiagnosticsCommand { get; }

		public RelayCommand OpenSettingsFolderCommand { get; }

		public RelayCommand OpenLogCommand { get; }

		public RelayCommand CopyDiagnosticsCommand { get; }

		public RelayCommand CopySupportInquiryCommand { get; }

		public string SupportInquiryText => CanExportDiagnostics
			? SupportInquiryFormatter.Format(device) : "장치 정보 조회가 끝나면 공식 지원 문의 초안을 확인하고 복사할 수 있습니다.";

		public RelayCommand SaveDiagnosticsCommand { get; }

		public RelayCommand CreateHardwareReportCommand { get; }

		public RelayCommand CreateSamsungBundleCommand { get; }

		public bool SamsungBundleBusy => samsungBundleBusy;

		public string SamsungBundleStatus
		{
			get
			{
				return samsungBundleStatus;
			}
			private set
			{
				samsungBundleStatus = value;
				Changed("SamsungBundleStatus");
			}
		}

		public string SamsungBundleFileName
		{
			get
			{
				return samsungBundleFileName;
			}
			private set
			{
				samsungBundleFileName = value;
				Changed("SamsungBundleFileName");
			}
		}

		public bool HardwareReportBusy => hardwareReportBusy;

		public string StandardBatteryRequestText
		{
			get { return standardBatteryRequestText; }
			private set
			{
				standardBatteryRequestText = value;
				Changed("StandardBatteryRequestText");
			}
		}

		public string HardwareReportText
		{
			get
			{
				return hardwareReportText;
			}
			private set
			{
				hardwareReportText = value;
				Changed("HardwareReportText");
			}
		}

		public string HardwareReportStatus
		{
			get
			{
				return hardwareReportStatus;
			}
			private set
			{
				hardwareReportStatus = value;
				Changed("HardwareReportStatus");
			}
		}

		public string InitialWindowState => settings.LastUiState;

		public string SettingsWarning { get; }

		public string BatteryErrorText => snapshot.Error;

		public bool DiagnosticsBusy => diagnosticsBusy;

		public bool CanExportDiagnostics
		{
			get
			{
				if (!disposed && !diagnosticsBusy)
				{
					return hasDiagnostics;
				}
				return false;
			}
		}

		public bool DiagnosticsSucceeded
		{
			get
			{
				if (hasDiagnostics && device != null && device.Errors.Length == 0 && !string.IsNullOrWhiteSpace(device.Manufacturer) && !string.IsNullOrWhiteSpace(device.Model) && !string.IsNullOrWhiteSpace(device.BiosVersion) && !string.IsNullOrWhiteSpace(device.WindowsName) && !string.IsNullOrWhiteSpace(device.WindowsVersion))
				{
					return !string.IsNullOrWhiteSpace(device.SystemArchitecture);
				}
				return false;
			}
		}

		public string DeviceModelText
		{
			get
			{
				if (device == null || string.IsNullOrWhiteSpace(device.Model))
				{
					return "알 수 없음";
				}
				return device.Model;
			}
		}

		public string DeviceBiosText
		{
			get
			{
				if (device == null || string.IsNullOrWhiteSpace(device.BiosVersion))
				{
					return "알 수 없음";
				}
				return device.BiosVersion;
			}
		}

		public string DeviceAssessmentText => DeviceSupportAssessment.Evaluate(device).StatusText + " · " + DeviceSupportAssessment.Evaluate(device).Reason;

		public string BatteryPercentText
		{
			get
			{
				if (!snapshot.Percent.HasValue)
				{
					return "알 수 없음";
				}
				return snapshot.Percent.Value + "%";
			}
		}

		public string ExternalPowerText
		{
			get
			{
				if (snapshot.ExternalPower != ExternalPowerStatus.Connected)
				{
					if (snapshot.ExternalPower != ExternalPowerStatus.Disconnected)
					{
						return "알 수 없음";
					}
					return "AC 연결 안 됨";
				}
				return "AC 연결됨";
			}
		}

		public string ChargeStateText
		{
			get
			{
				switch (snapshot.ChargeState)
				{
				case BatteryChargeState.Charging:
					return "충전 중";
				case BatteryChargeState.NotCharging:
					return "충전 중 아님";
				case BatteryChargeState.Discharging:
					return "방전 중";
				case BatteryChargeState.NoBattery:
					return "배터리 없음";
				default:
					return "상태 알 수 없음";
				}
			}
		}

		public string ActualModeText
		{
			get
			{
				if (physical.GetCurrentMode() != ChargeMode.Unsupported)
				{
					return "알 수 없음";
				}
				return "미지원 · 실제 펌웨어 상태를 읽을 수 없음";
			}
		}

		public string SupportReason => physical.GetCapabilities().Reason;

		public string DesiredModeText => "사용자 희망값: " + ModeText(settings.DesiredMode) + " · 실제 적용과 별개";

		public string MockModeText
		{
			get
			{
				if (!IsMockMode)
				{
					return "시뮬레이션 꺼짐 · 실사용 어댑터는 미지원입니다.";
				}
				return "개발용 모의 어댑터가 켜져 있습니다.";
			}
		}

		public string MockActualModeText
		{
			get
			{
				if (!IsMockMode)
				{
					return "모의 상태: 사용 안 함";
				}
				return "모의 상태: " + ModeText(mock.GetCurrentMode());
			}
		}

		public bool CanApply
		{
			get
			{
				if (!disposed && IsMockMode)
				{
					return mock.GetCapabilities().CanWrite;
				}
				return false;
			}
		}

		public bool IsMockMode
		{
			get
			{
				return mockMode;
			}
			set
			{
				if (!disposed && mockMode != value)
				{
					mockMode = value;
					settings.MockModeEnabled = value;
					mock = new MockChargeLimitController();
					log.Write(value ? "MOCK_ENABLED" : "MOCK_DISABLED");
					StatusMessage = (value ? "시뮬레이션을 켰습니다. 실제 충전 제어는 없습니다." : "시뮬레이션을 껐습니다. 실제 장치 상태는 미지원입니다.");
					Changed("IsMockMode");
					Changed("MockModeText");
					Changed("MockActualModeText");
					Changed("CanApply");
					ApplyCommand.Refresh();
				}
			}
		}

		public bool IsProtectionSelected
		{
			get
			{
				return settings.DesiredMode == ChargeMode.Protection80;
			}
			set
			{
				if (value)
				{
					SelectMode(ChargeMode.Protection80);
				}
			}
		}

		public bool IsNormalSelected
		{
			get
			{
				return settings.DesiredMode == ChargeMode.Normal100;
			}
			set
			{
				if (value)
				{
					SelectMode(ChargeMode.Normal100);
				}
			}
		}

		public bool RestoreOnBoot
		{
			get
			{
				return settings.RestoreOnBoot;
			}
			set
			{
				if (!disposed)
				{
					settings.RestoreOnBoot = value;
					Changed("RestoreOnBoot");
					StatusMessage = "복원 희망값만 바꿨습니다. 저장 버튼으로 기억할 수 있으며, 자동 실행이나 펌웨어 복원은 수행하지 않습니다.";
				}
			}
		}

		public string StatusMessage
		{
			get
			{
				return statusMessage;
			}
			private set
			{
				statusMessage = value;
				Changed("StatusMessage");
			}
		}

		public string DiagnosticsText
		{
			get
			{
				return diagnosticsText;
			}
			private set
			{
				diagnosticsText = value;
				Changed("DiagnosticsText");
			}
		}

		public event PropertyChangedEventHandler PropertyChanged;

		public MainViewModel(IBatteryStatusProvider battery, SettingsStore store, LocalLog log, IUserInteraction interaction, IHardwareDiagnosticsProvider hardwareDiagnostics = null, ISamsungAnalysisBundleService samsungAnalysis = null, Func<bool> confirmSamsungAnalysis = null)
		{
			MainViewModel mainViewModel = this;
			this.battery = battery;
			this.store = store;
			this.log = log;
			this.interaction = interaction;
			this.hardwareDiagnostics = hardwareDiagnostics;
			this.samsungAnalysis = samsungAnalysis;
			this.confirmSamsungAnalysis = confirmSamsungAnalysis;
			if (samsungAnalysis == null || confirmSamsungAnalysis == null)
				samsungBundleStatus = "삼성 프로그램 파일 수집은 공식 지원·사용권 확인 전까지 보류되어 있습니다.";
			SettingsLoadResult settingsLoadResult = store.Load();
			settings = settingsLoadResult.Settings;
			canSave = settingsLoadResult.CanSave;
			SettingsWarning = settingsLoadResult.Warning;
			bool mockModeEnabled = settings.MockModeEnabled;
			settings.MockModeEnabled = false;
			statusMessage = ((!string.IsNullOrEmpty(settingsLoadResult.Warning)) ? settingsLoadResult.Warning : "사용자 희망값을 읽었습니다. 실제 충전 제한은 지원하지 않습니다.");
			if (mockModeEnabled)
			{
				statusMessage += " 이전 모의 모드는 꺼져 있습니다. 필요하면 직접 켜세요.";
			}
			ApplyCommand = new RelayCommand(Apply, () => mainViewModel.CanApply);
			SaveCommand = new RelayCommand(Save, () => mainViewModel.canSave && !mainViewModel.disposed);
			RefreshCommand = new RelayCommand(RefreshBattery, () => !mainViewModel.disposed);
			ShowDiagnosticsCommand = new RelayCommand(async delegate
			{
				await mainViewModel.RefreshDiagnosticsAsync();
			}, () => !mainViewModel.diagnosticsBusy && !mainViewModel.disposed);
			OpenSettingsFolderCommand = new RelayCommand(delegate
			{
				mainViewModel.SafeAction(interaction.OpenSettingsFolder);
			}, () => !mainViewModel.disposed);
			OpenLogCommand = new RelayCommand(delegate
			{
				mainViewModel.SafeAction(interaction.ShowLog);
			}, () => !mainViewModel.disposed);
			CopyDiagnosticsCommand = new RelayCommand(delegate
			{
				mainViewModel.SafeAction(delegate
				{
					interaction.CopyDiagnostics(mainViewModel.DiagnosticsText);
					mainViewModel.StatusMessage = "진단 정보를 클립보드에 복사했습니다. 앱은 전송하지 않습니다.";
				});
			}, () => mainViewModel.CanExportDiagnostics);
			CopySupportInquiryCommand = new RelayCommand(delegate
			{
				mainViewModel.SafeAction(delegate
				{
					interaction.CopyDiagnostics(mainViewModel.SupportInquiryText);
					mainViewModel.StatusMessage = "공식 문의 초안을 클립보드에 복사했습니다. 내용을 검토한 뒤 직접 전달할 수 있습니다.";
				});
			}, () => mainViewModel.CanExportDiagnostics);
			SaveDiagnosticsCommand = new RelayCommand(delegate
			{
				mainViewModel.SafeAction(delegate
				{
					mainViewModel.StatusMessage = interaction.SaveDiagnostics(mainViewModel.DiagnosticsText);
				});
			}, () => mainViewModel.CanExportDiagnostics);
			CreateHardwareReportCommand = new RelayCommand(async delegate
			{
				await mainViewModel.CreateHardwareReportAsync();
			}, () => !mainViewModel.disposed && !mainViewModel.hardwareReportBusy && mainViewModel.hardwareDiagnostics != null);
			CreateSamsungBundleCommand = new RelayCommand(async delegate
			{
				await mainViewModel.CreateSamsungBundleAsync();
			}, () => !mainViewModel.disposed && !mainViewModel.samsungBundleBusy && mainViewModel.samsungAnalysis != null && mainViewModel.confirmSamsungAnalysis != null);
			log.Write("APP_STARTED");
			log.Write(string.IsNullOrEmpty(settingsLoadResult.Warning) ? "SETTINGS_LOADED" : "SETTINGS_RECOVERED");
			RefreshBattery();
		}

		private void SelectMode(ChargeMode mode)
		{
			if (!disposed && settings.DesiredMode != mode)
			{
				settings.DesiredMode = mode;
				Changed("IsProtectionSelected");
				Changed("IsNormalSelected");
				Changed("DesiredModeText");
				StatusMessage = "사용자 희망값을 변경했습니다. 저장하거나 모의 상태만 전환할 수 있습니다.";
			}
		}

		private void Apply()
		{
			if (CanApply)
			{
				OperationResult operationResult = mock.SetMode(settings.DesiredMode);
				StatusMessage = (operationResult.Success ? "모의 상태를 전환했습니다. 실제 하드웨어에는 적용하지 않았습니다." : operationResult.Message);
				log.Write(operationResult.Success ? "MOCK_MODE_CHANGED" : "HARDWARE_WRITE_REJECTED");
				Changed("MockActualModeText");
			}
		}

		private void Save()
		{
			OperationResult operationResult = store.Save(settings);
			StatusMessage = operationResult.Message;
			log.Write(operationResult.Success ? "SETTINGS_SAVED" : "SETTINGS_SAVE_FAILED");
		}

		public void RefreshBattery()
		{
			if (!disposed)
			{
				try
				{
					snapshot = battery.Read() ?? BatterySnapshot.Unknown("배터리 데이터를 받지 못했습니다.");
				}
				catch
				{
					snapshot = BatterySnapshot.Unknown("배터리 조회 중 오류가 발생했습니다.");
				}
				if (!string.IsNullOrEmpty(snapshot.Error))
				{
					log.Write("BATTERY_READ_FAILED");
				}
				Changed("BatteryPercentText");
				Changed("ExternalPowerText");
				Changed("ChargeStateText");
				Changed("BatteryErrorText");
			}
		}

		public async Task RefreshDiagnosticsAsync()
		{
			if (disposed || diagnosticsBusy)
			{
				return;
			}
			diagnosticsBusy = true;
			hasDiagnostics = false;
			device = null;
			DiagnosticsText = "로컬 장치 정보를 조회하고 있습니다…";
			NotifyDiagnostics();
			try
			{
				DeviceDiagnosticsResult deviceDiagnosticsResult = await Task.Run(() => interaction.ReadDiagnostics());
				if (!disposed)
				{
					device = deviceDiagnosticsResult ?? new DeviceDiagnosticsResult(null, null, null, null, null, null, new string[1] { "장치 진단 결과를 받지 못했습니다." });
					hasDiagnostics = true;
					DiagnosticsText = device.ToDisplayText();
					StatusMessage = (DiagnosticsSucceeded ? "읽기 전용 진단을 완료했습니다. 하드웨어 쓰기는 하지 않았습니다." : "진단 정보에 누락 또는 오류가 있습니다. 상세 결과를 확인하거나 로컬에 저장할 수 있습니다.");
					log.Write(DiagnosticsSucceeded ? "DIAGNOSTICS_READ" : "DIAGNOSTICS_FAILED");
				}
			}
			catch
			{
				if (!disposed)
				{
					device = new DeviceDiagnosticsResult(null, null, null, null, null, null, new string[1] { "장치 정보를 조회할 수 없습니다. 하드웨어 제어는 차단되어 있습니다." });
					hasDiagnostics = true;
					DiagnosticsText = device.ToDisplayText();
					StatusMessage = "장치 진단에 실패했습니다. 오류 결과를 로컬에 저장할 수 있습니다.";
					log.Write("DIAGNOSTICS_FAILED");
				}
			}
			finally
			{
				diagnosticsBusy = false;
				if (!disposed)
				{
					NotifyDiagnostics();
				}
			}
		}

		private void NotifyDiagnostics()
		{
			Changed("DiagnosticsBusy");
			Changed("DiagnosticsSucceeded");
			Changed("CanExportDiagnostics");
			Changed("SupportInquiryText");
			Changed("DeviceModelText");
			Changed("DeviceBiosText");
			Changed("DeviceAssessmentText");
			ShowDiagnosticsCommand.Refresh();
			CopyDiagnosticsCommand.Refresh();
			CopySupportInquiryCommand.Refresh();
			SaveDiagnosticsCommand.Refresh();
		}

		public async Task CreateHardwareReportAsync()
		{
			if (disposed || hardwareReportBusy || hardwareDiagnostics == null)
			{
				return;
			}
			hardwareReportBusy = true;
			HardwareReportText = string.Empty;
			StandardBatteryRequestText = "읽기 전용 조회 중입니다. 이전 결과는 사용하지 않습니다…";
			HardwareReportStatus = "배터리와 삼성 프로그램 정보를 읽고 있습니다. 충전 설정은 변경하지 않습니다…";
			Changed("HardwareReportBusy");
			CreateHardwareReportCommand.Refresh();
			log.Write("HARDWARE_PROBE_STARTED");
			bool collected = false;
			try
			{
				HardwareProbeReport hardwareProbeReport = await Task.Run(() => hardwareDiagnostics.Collect());
				if (!disposed)
				{
					if (hardwareProbeReport == null)
					{
						throw new InvalidOperationException();
					}
					HardwareReportText = hardwareProbeReport.ToDisplayText();
					StandardBatteryRequestText = hardwareProbeReport.WindowsBatteryCapabilities.AssessmentText;
					collected = true;
					interaction.SaveDiagnostics(HardwareReportText);
					HardwareReportStatus = "진단 파일을 만들었습니다. ‘진단 파일 위치 열기’에서 새 diagnostics 파일을 확인하세요.";
					StatusMessage = HardwareReportStatus;
					log.Write("HARDWARE_PROBE_SAVED");
				}
			}
			catch
			{
				if (!disposed)
				{
					if (!collected) StandardBatteryRequestText = new WindowsBatteryCapabilitiesReport(BatteryProbeStatus.Unavailable).AssessmentText;
					HardwareReportStatus = collected
						? "읽기 전용 조회는 완료했지만 진단 파일을 저장하지 못했습니다. 조회 결과는 화면에서 확인할 수 있습니다."
						: "진단 정보를 조회하지 못했습니다. 이전 결과를 사용하지 않으며 실제 제어는 차단되어 있습니다.";
					StatusMessage = HardwareReportStatus;
					log.Write("HARDWARE_PROBE_FAILED");
				}
			}
			finally
			{
				hardwareReportBusy = false;
				if (!disposed)
				{
					Changed("HardwareReportBusy");
					CreateHardwareReportCommand.Refresh();
				}
			}
		}

		public async Task CreateSamsungBundleAsync()
		{
			if (disposed || samsungBundleBusy || samsungAnalysis == null || confirmSamsungAnalysis == null)
			{
				return;
			}
			samsungBundleBusy = true;
			SamsungBundleFileName = string.Empty;
			Changed("SamsungBundleBusy");
			CreateSamsungBundleCommand.Refresh();
			try
			{
				bool flag = confirmSamsungAnalysis();
				if (disposed)
				{
					return;
				}
				if (!flag)
				{
					SamsungBundleStatus = "분석 파일 생성을 취소했습니다.";
				}
				else
				{
					if (disposed)
					{
						return;
					}
					SamsungBundleStatus = "삼성 프로그램의 복사본과 파일 정보를 모으고 있습니다. 원본 파일은 실행하거나 변경하지 않습니다…";
					log.Write("SAMSUNG_BUNDLE_STARTED");
					SamsungBundleResult samsungBundleResult = await Task.Run(() => samsungAnalysis.Create());
					if (!disposed)
					{
						if (samsungBundleResult == null || !samsungBundleResult.Success || string.IsNullOrWhiteSpace(samsungBundleResult.FileName))
						{
							SamsungBundleStatus = ((samsungBundleResult == null || string.IsNullOrWhiteSpace(samsungBundleResult.Message)) ? "삼성 분석 파일을 만들지 못했습니다. 원본 파일은 변경하지 않았습니다." : samsungBundleResult.Message);
							log.Write("SAMSUNG_BUNDLE_FAILED");
							return;
						}
						SamsungBundleFileName = samsungBundleResult.FileName;
						SamsungBundleStatus = (samsungBundleResult.ContainsModules ? ("삼성 파일이 포함된 분석 ZIP을 만들었습니다. ‘파일 위치 열기’에서 새 samsung-analysis ZIP을 확인하세요. " + samsungBundleResult.Message) : ("삼성 파일은 복사하지 않고 위치 점검 보고서 ZIP을 만들었습니다. ‘파일 위치 열기’에서 새 samsung-analysis ZIP을 확인하세요. " + samsungBundleResult.Message));
						StatusMessage = SamsungBundleStatus;
						log.Write(samsungBundleResult.ContainsModules ? "SAMSUNG_BUNDLE_SAVED" : "SAMSUNG_BUNDLE_REPORT_ONLY");
					}
				}
			}
			catch
			{
				if (!disposed)
				{
					SamsungBundleStatus = "삼성 분석 파일을 만들지 못했습니다. 원본 파일은 변경하지 않았습니다.";
					log.Write("SAMSUNG_BUNDLE_FAILED");
				}
			}
			finally
			{
				samsungBundleBusy = false;
				if (!disposed)
				{
					Changed("SamsungBundleBusy");
					CreateSamsungBundleCommand.Refresh();
				}
			}
		}

		private void SafeAction(Action action)
		{
			if (disposed)
			{
				return;
			}
			try
			{
				action();
			}
			catch
			{
				StatusMessage = "로컬 작업을 완료하지 못했습니다. 저장 위치와 권한을 확인하세요.";
				log.Write("UI_ACTION_FAILED");
			}
		}

		public void RememberWindowState(bool maximized)
		{
			if (!disposed)
			{
				settings.LastUiState = (maximized ? "Maximized" : "Normal");
			}
		}

		public void Dispose()
		{
			if (!disposed)
			{
				if (canSave)
				{
					Save();
				}
				disposed = true;
				ApplyCommand.Refresh();
				SaveCommand.Refresh();
				RefreshCommand.Refresh();
				ShowDiagnosticsCommand.Refresh();
				CopyDiagnosticsCommand.Refresh();
				CopySupportInquiryCommand.Refresh();
				SaveDiagnosticsCommand.Refresh();
				OpenSettingsFolderCommand.Refresh();
				OpenLogCommand.Refresh();
				CreateHardwareReportCommand.Refresh();
				CreateSamsungBundleCommand.Refresh();
				log.Write("APP_STOPPED");
			}
		}

		private static string ModeText(ChargeMode mode)
		{
			if (mode != ChargeMode.Protection80)
			{
				return "보호 OFF (일반 100%)";
			}
			return "보호 ON (80%)";
		}

		private void Changed([CallerMemberName] string name = null)
		{
			this.PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
		}
	}
}
