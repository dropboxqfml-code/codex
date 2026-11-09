using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.CompilerServices;
using System.Threading;
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

		private readonly ISamsungFileInspectionProvider samsungFiles;

		private bool samsungFileInspectionBusy;

		private string samsungFileInspectionText = "‘삼성 파일 정보 만들기’를 누르면 설치된 파일의 정보만 읽습니다.";

		private string samsungFileInspectionStatus = "파일을 실행하거나 충전 설정을 변경하지 않습니다.";

		private string samsungTransportSummary = "전송 경로의 관측 요약은 아직 없습니다. 실제 충전 제어는 미지원입니다.";

		private string experimentReviewInput = string.Empty;

		private WsabiWmiExperimentReview experimentReview = WsabiWmiExperimentReview.Empty;

		private string fixedReadReviewInput = string.Empty;

		private WsabiWmiFixedReadAccess1Review fixedReadReview = WsabiWmiFixedReadAccess1Review.Empty;

		private string protectionReviewInput = string.Empty;

		private WsabiWmiProtection0To1Review protectionReview = WsabiWmiProtection0To1Review.Empty;

		private readonly BatteryObservationSession observation = new BatteryObservationSession();

		private readonly Stopwatch observationClock = new Stopwatch();

		private long observationSession;

		private long savedObservationSession = -1;

		private int savedObservationSamples = -1;

		private string observationSaveStatusText = "저장은 ‘관찰 TXT 저장’을 누를 때만 합니다. 저장 폴더를 바로 열어 새 파일을 확인할 수 있습니다.";

		private bool observationSaveFailed;

		private readonly IManualProtectionOperationService manualProtectionService;

		private readonly SynchronizationContext manualSynchronizationContext;

		private ManualProtectionResult manualProtectionResult;

		private ManualProtectionResult manualReportResult;

		private ManualProtectionResult savedManualReportResult;

		private string manualSaveStatusText = "마지막 제어 요청의 결과가 도착하면 TXT로 한 번 저장할 수 있습니다. 자동 저장·업로드하지 않습니다.";

		private bool manualSaveFailed;

		private ManualProtectionPhase manualProtectionPhase = ManualProtectionPhase.Idle;

		private bool manualProtectionBusy;

		private bool manualProtectionPending;

		private long manualStateVersion;

		private long manualOperationSequence;

		private string manualProtectionNotice = "먼저 보호 상태 확인을 누르세요. 앱 시작과 배터리 갱신은 OEM 호출을 하지 않습니다.";

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

		public RelayCommand InspectSamsungFilesCommand { get; }

		public RelayCommand ReviewExperimentResultCommand { get; }

		public RelayCommand ClearExperimentReviewCommand { get; }

		public string ExperimentReviewInput
		{
			get { return experimentReviewInput; }
			set
			{
				if (disposed) return;
				string input = value ?? string.Empty;
				if (input == experimentReviewInput) return;
				if (input.Length > WsabiWmiExperimentReviewParser.MaximumCharacters)
				{
					// Reject the complete value rather than turning a truncated
					// report into apparently valid historical evidence.
					experimentReviewInput = string.Empty;
					experimentReview = WsabiWmiExperimentReviewParser.Parse(input);
				}
				else
				{
					experimentReviewInput = input;
					experimentReview = WsabiWmiExperimentReview.Empty;
				}
				NotifyExperimentReview();
			}
		}

		public string ExperimentReviewText => experimentReview.ToDisplayText();

		public WsabiWmiExperimentReviewStatus ExperimentReviewStatus => experimentReview.Status;

		public bool ExperimentReviewHasValidatedFrame => experimentReview.HasValidatedFrame;

		public RelayCommand ReviewFixedReadResultCommand { get; }

		public RelayCommand ClearFixedReadReviewCommand { get; }

		public string FixedReadReviewInput
		{
			get { return fixedReadReviewInput; }
			set
			{
				if (disposed) return;
				string input = value ?? string.Empty;
				if (input == fixedReadReviewInput) return;
				if (input.Length > WsabiWmiFixedReadAccess1ReviewParser.MaximumCharacters)
				{
					fixedReadReviewInput = string.Empty;
					fixedReadReview = WsabiWmiFixedReadAccess1ReviewParser.Parse(input);
				}
				else
				{
					fixedReadReviewInput = input;
					fixedReadReview = WsabiWmiFixedReadAccess1Review.Empty;
				}
				NotifyFixedReadReview();
			}
		}

		public string FixedReadReviewText => fixedReadReview.ToDisplayText();

		public WsabiWmiFixedReadAccess1ReviewStatus FixedReadReviewStatus => fixedReadReview.Status;

		public bool FixedReadReviewHasReportedStoredModeCandidate => fixedReadReview.HasReportedStoredModeCandidate;

		public int? FixedReadReviewStoredModeCandidate => fixedReadReview.StoredModeCandidate;

		public RelayCommand ReviewProtectionResultCommand { get; }

		public RelayCommand ClearProtectionReviewCommand { get; }

		public string ProtectionReviewInput
		{
			get { return protectionReviewInput; }
			set
			{
				if (disposed) return;
				string input = value ?? string.Empty;
				if (input == protectionReviewInput) return;
				if (input.Length > WsabiWmiProtection0To1ReviewParser.MaximumCharacters)
				{
					protectionReviewInput = string.Empty;
					protectionReview = WsabiWmiProtection0To1ReviewParser.Parse(input);
				}
				else
				{
					protectionReviewInput = input;
					protectionReview = WsabiWmiProtection0To1Review.Empty;
				}
				NotifyProtectionReview();
			}
		}

		public string ProtectionReviewText => protectionReview.ToDisplayText();

		public WsabiWmiProtection0To1ReviewStatus ProtectionReviewStatus => protectionReview.Status;

		public bool ProtectionReviewHasReportedStoredTransition => protectionReview.HasReportedStoredTransition;

		public RelayCommand StartBatteryObservationCommand { get; }

		public RelayCommand StopBatteryObservationCommand { get; }

		public RelayCommand ClearBatteryObservationCommand { get; }

		public RelayCommand SaveBatteryObservationCommand { get; }

		public string ObservationText => observation.ToDisplayText();

		public bool ObservationActive => observation.IsRecording;

		public int ObservationSampleCount => observation.SampleCount;

		public int ObservationGapCount => observation.GapCount;

		public string ObservationSaveStatusText => observationSaveStatusText;

		public bool ObservationSaveFailed => observationSaveFailed;

		public RelayCommand ManualReadProtectionCommand { get; }

		public RelayCommand ManualEnableProtectionCommand { get; }

		public RelayCommand ManualDisableProtectionCommand { get; }

		public RelayCommand ManualSaveResultCommand { get; }

		public string ManualSaveStatusText => manualSaveStatusText;

		public bool ManualSaveFailed => manualSaveFailed;

		public bool ManualProtectionAvailable => manualProtectionService != null;

		public bool ManualProtectionBusy => manualProtectionBusy || manualProtectionPending;

		public bool ManualProtectionPending => manualProtectionPending;

		public bool CanChangeMockMode => !ManualProtectionBusy && !disposed;

		public ManualProtectionResult ManualProtectionLastResult => manualProtectionResult;

		public ManualProtectionPhase ManualProtectionCurrentPhase => manualProtectionPhase;

		public string ManualProtectionPhaseText => PhaseText(manualProtectionPhase);

		public string ManualProtectionNotice => manualProtectionNotice;

		public string ManualProtectionStateText
		{
			get
			{
				if (IsMockMode) return "시뮬레이션 중 · 실제 보호 조회·제어는 중지했습니다";
				if (ManualProtectionBusy) return manualProtectionPending ? "장치 작업의 실제 종료 미확인 · 추가 동작 차단" : "조회·설정·실제 정리 중";
				if (manualProtectionResult == null || !manualProtectionResult.HasKnownMode)
					return "마지막 보호 조회: 미조회 또는 알 수 없음";
				return manualProtectionResult.ModeCandidate == 1
					? "마지막 조회 후보: 보호 모드1" : "마지막 조회 후보: 보호 모드0 · 일반 충전";
			}
		}

		public string ManualProtectionText
		{
			get
			{
				var value = manualProtectionResult;
				if (value == null)
					return "보호 모드·상한·하한의 마지막 조회 결과는 아직 없습니다. 사용자 희망 설정과 Windows 배터리 잔량은 각각 별개입니다.";
				string text = "요청 결과: " + ResultText(value.Status) + "\n";
				if (!value.CleanupComplete)
					return text + "실제 호출·출력·입력 정리가 확인되지 않았습니다. 카운터나 창 종료로 완료를 추정하지 않습니다. 추가 조회·설정·자동 재시도 없이 기다립니다.";
				text += "관련 정리: Complete\n";
				text += "모드 후보: " + ManualNumber(value.ModeCandidate) + " / 상한 후보: " + ManualNumber(value.UpperCandidate) +
					" / 하한 후보: " + ManualNumber(value.LowerCandidate) + "\n";
				text += "SDK 진입: " + value.SdkEntries.ToString(CultureInfo.InvariantCulture) + " / 설정 진입: " +
					value.SetterEntries.ToString(CultureInfo.InvariantCulture) + " / 수용 읽기: " + value.ReadCandidates.ToString(CultureInfo.InvariantCulture) + "\n";
				if (value.Status == ManualProtectionStatus.AlreadyDesiredCandidate)
					text += "이미 요청한 모드 후보여서 설정하지 않았습니다. 상한·하한은 이번 동작에서 조회하지 않았습니다.\n";
				return text + "이는 해당 요청에서 읽은 저장 후보입니다. 모드0은100% 충전 보장이 아니며, 전류·충전기 적용·재부팅 지속성을 확인한 값은 아닙니다.";
			}
		}

		public bool SamsungFileInspectionBusy => samsungFileInspectionBusy;

		public string SamsungFileInspectionText
		{
			get { return samsungFileInspectionText; }
			private set { samsungFileInspectionText = value; Changed(); }
		}

		public string SamsungFileInspectionStatus
		{
			get { return samsungFileInspectionStatus; }
			private set { samsungFileInspectionStatus = value; Changed(); }
		}

		public string SamsungTransportSummary
		{
			get { return samsungTransportSummary; }
			private set { samsungTransportSummary = value; Changed(); }
		}

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
				if (ManualProtectionAvailable) return ManualProtectionStateText;
				if (physical.GetCurrentMode() != ChargeMode.Unsupported)
				{
					return "알 수 없음";
				}
				return "미지원 · 앱에서 실시간 보호 상태를 조회하지 않습니다";
			}
		}

		public string SupportReason => ManualProtectionAvailable
			? "수동 제어 베타 · 해당 요청에서 Windows10 x64·940X3G/930X3G·P05ACJ profile과 고정 WMI 계약을 확인합니다. 지원 범위가 확인되기 전에는 설정하지 않습니다."
			: physical.GetCapabilities().Reason;

		public string DesiredModeText => "사용자 희망값: " + ModeText(settings.DesiredMode) + " · 실제 적용과 별개";

		public string MockModeText
		{
			get
			{
				if (!IsMockMode)
				{
					if (ManualProtectionAvailable) return "시뮬레이션 꺼짐 · 실제 수동 제어는 위 보호 제어 버튼에서만 요청합니다.";
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
				if (!disposed && mockMode != value && ManualProtectionBusy)
				{
					manualProtectionNotice = "장치 작업과 실제 정리를 기다리는 동안 시뮬레이션을 변경할 수 없습니다.";
					Changed("IsMockMode");
					NotifyManualProtection();
					return;
				}
				if (!disposed && mockMode != value)
				{
					mockMode = value;
					InvalidateManualState();
					if (value) StopBatteryObservation();
					settings.MockModeEnabled = value;
					mock = new MockChargeLimitController();
					log.Write(value ? "MOCK_ENABLED" : "MOCK_DISABLED");
					StatusMessage = value ? "시뮬레이션을 켰습니다. 실제 충전 제어는 없습니다."
						: ManualProtectionAvailable ? "시뮬레이션을 껐습니다. 실제 설정은 보호 상태 확인에서 다시 읽으세요."
						: "시뮬레이션을 껐습니다. 실제 장치 상태는 미지원입니다.";
					Changed("IsMockMode");
					Changed("MockModeText");
					Changed("MockActualModeText");
					Changed("CanApply");
					ApplyCommand.Refresh();
					StartBatteryObservationCommand.Refresh();
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

		public MainViewModel(IBatteryStatusProvider battery, SettingsStore store, LocalLog log, IUserInteraction interaction, IHardwareDiagnosticsProvider hardwareDiagnostics = null, ISamsungAnalysisBundleService samsungAnalysis = null, Func<bool> confirmSamsungAnalysis = null, ISamsungFileInspectionProvider samsungFiles = null, IManualProtectionOperationService manualProtectionService = null)
		{
			MainViewModel mainViewModel = this;
			this.battery = battery;
			this.store = store;
			this.log = log;
			this.interaction = interaction;
			this.hardwareDiagnostics = hardwareDiagnostics;
			this.samsungFiles = samsungFiles;
			this.samsungAnalysis = samsungAnalysis;
			this.confirmSamsungAnalysis = confirmSamsungAnalysis;
			this.manualProtectionService = manualProtectionService;
			manualSynchronizationContext = SynchronizationContext.Current;
			if (samsungAnalysis == null || confirmSamsungAnalysis == null)
				samsungBundleStatus = "삼성 프로그램 파일 수집은 공식 지원·사용권 확인 전까지 보류되어 있습니다.";
			SettingsLoadResult settingsLoadResult = store.Load();
			settings = settingsLoadResult.Settings;
			canSave = settingsLoadResult.CanSave;
			SettingsWarning = settingsLoadResult.Warning;
			bool mockModeEnabled = settings.MockModeEnabled;
			settings.MockModeEnabled = false;
			statusMessage = ((!string.IsNullOrEmpty(settingsLoadResult.Warning)) ? settingsLoadResult.Warning :
				ManualProtectionAvailable ? "사용자 희망값을 읽었습니다. 수동 제어는 먼저 보호 상태 확인을 눌러 지원 범위와 저장 후보를 확인하세요."
				: "사용자 희망값을 읽었습니다. 실제 충전 제한은 지원하지 않습니다.");
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
			InspectSamsungFilesCommand = new RelayCommand(async delegate
			{
				await mainViewModel.InspectSamsungFilesAsync();
			}, () => !mainViewModel.disposed && !mainViewModel.samsungFileInspectionBusy && mainViewModel.samsungFiles != null);
			ReviewExperimentResultCommand = new RelayCommand(ReviewExperimentResult,
				() => !mainViewModel.disposed && !string.IsNullOrWhiteSpace(mainViewModel.experimentReviewInput));
			ClearExperimentReviewCommand = new RelayCommand(ClearExperimentReview,
				() => !mainViewModel.disposed);
			ReviewFixedReadResultCommand = new RelayCommand(ReviewFixedReadResult,
				() => !mainViewModel.disposed && !string.IsNullOrWhiteSpace(mainViewModel.fixedReadReviewInput));
			ClearFixedReadReviewCommand = new RelayCommand(ClearFixedReadReview,
				() => !mainViewModel.disposed);
			ReviewProtectionResultCommand = new RelayCommand(ReviewProtectionResult,
				() => !mainViewModel.disposed && !string.IsNullOrWhiteSpace(mainViewModel.protectionReviewInput));
			ClearProtectionReviewCommand = new RelayCommand(ClearProtectionReview,
				() => !mainViewModel.disposed);
			StartBatteryObservationCommand = new RelayCommand(StartBatteryObservation,
				() => !mainViewModel.disposed && !mainViewModel.IsMockMode && !mainViewModel.observation.IsRecording);
			StopBatteryObservationCommand = new RelayCommand(StopBatteryObservation,
				() => !mainViewModel.disposed && mainViewModel.observation.IsRecording);
			ClearBatteryObservationCommand = new RelayCommand(ClearBatteryObservation,
				() => !mainViewModel.disposed);
			SaveBatteryObservationCommand = new RelayCommand(SaveBatteryObservation,
				() => mainViewModel.CanSaveBatteryObservation());
			ManualReadProtectionCommand = new RelayCommand(async () => await RunManualProtectionAsync(ManualProtectionOperation.ReadState),
				() => CanReadManualProtection());
			ManualEnableProtectionCommand = new RelayCommand(async () => await RunManualProtectionAsync(ManualProtectionOperation.Enable80),
				() => CanWriteManualProtection());
			ManualDisableProtectionCommand = new RelayCommand(async () => await RunManualProtectionAsync(ManualProtectionOperation.DisableProtection),
				() => CanWriteManualProtection());
			ManualSaveResultCommand = new RelayCommand(SaveManualProtectionResult,
				() => !disposed && !manualProtectionBusy && manualReportResult != null && !ReferenceEquals(manualReportResult, savedManualReportResult));
			log.Write("APP_STARTED");
			log.Write(string.IsNullOrEmpty(settingsLoadResult.Warning) ? "SETTINGS_LOADED" : "SETTINGS_RECOVERED");
			RefreshBattery();
		}

		public void ReviewExperimentResult()
		{
			if (disposed) return;
			// Only fixed classifications leave the parser. The source text is
			// not sent to settings, diagnostics, logs, files or a live provider.
			experimentReview = WsabiWmiExperimentReviewParser.Parse(experimentReviewInput);
			experimentReviewInput = string.Empty;
			NotifyExperimentReview();
		}

		private void ClearExperimentReview()
		{
			if (disposed) return;
			experimentReviewInput = string.Empty;
			experimentReview = WsabiWmiExperimentReview.Empty;
			NotifyExperimentReview();
		}

		private void NotifyExperimentReview()
		{
			Changed("ExperimentReviewInput");
			Changed("ExperimentReviewText");
			Changed("ExperimentReviewStatus");
			Changed("ExperimentReviewHasValidatedFrame");
			ReviewExperimentResultCommand?.Refresh();
			ClearExperimentReviewCommand?.Refresh();
		}

		public void ReviewFixedReadResult()
		{
			if (disposed) return;
			// Historical text only. No provider, reservation, controller,
			// settings, log or file is reached by this review action.
			fixedReadReview = WsabiWmiFixedReadAccess1ReviewParser.Parse(fixedReadReviewInput);
			fixedReadReviewInput = string.Empty;
			NotifyFixedReadReview();
		}

		private void ClearFixedReadReview()
		{
			if (disposed) return;
			fixedReadReviewInput = string.Empty;
			fixedReadReview = WsabiWmiFixedReadAccess1Review.Empty;
			NotifyFixedReadReview();
		}

		private void NotifyFixedReadReview()
		{
			Changed("FixedReadReviewInput");
			Changed("FixedReadReviewText");
			Changed("FixedReadReviewStatus");
			Changed("FixedReadReviewHasReportedStoredModeCandidate");
			Changed("FixedReadReviewStoredModeCandidate");
			ReviewFixedReadResultCommand?.Refresh();
			ClearFixedReadReviewCommand?.Refresh();
		}

		public void ReviewProtectionResult()
		{
			if (disposed) return;
			// This is a historical text review, never a live read or a replay.
			protectionReview = WsabiWmiProtection0To1ReviewParser.Parse(protectionReviewInput);
			protectionReviewInput = string.Empty;
			NotifyProtectionReview();
		}

		private void ClearProtectionReview()
		{
			if (disposed) return;
			protectionReviewInput = string.Empty;
			protectionReview = WsabiWmiProtection0To1Review.Empty;
			NotifyProtectionReview();
		}

		private void NotifyProtectionReview()
		{
			Changed("ProtectionReviewInput");
			Changed("ProtectionReviewText");
			Changed("ProtectionReviewStatus");
			Changed("ProtectionReviewHasReportedStoredTransition");
			ReviewProtectionResultCommand?.Refresh();
			ClearProtectionReviewCommand?.Refresh();
		}

		private bool ManualServiceBlocked
		{
			get
			{
				try { return manualProtectionService == null || manualProtectionService.IsBlocked; }
				catch { return true; }
			}
		}

		private bool CanReadManualProtection()
			=> !disposed && !IsMockMode && !ManualProtectionBusy && !ManualServiceBlocked;

		private bool CanWriteManualProtection()
			=> CanReadManualProtection() && manualProtectionResult != null &&
				manualProtectionResult.ProfileValidated && manualProtectionResult.HasKnownMode;

		public async Task RunManualProtectionAsync(ManualProtectionOperation operation)
		{
			if (!Enum.IsDefined(typeof(ManualProtectionOperation), operation)) return;
			if (operation == ManualProtectionOperation.ReadState ? !CanReadManualProtection() : !CanWriteManualProtection()) return;
			long sequence = ++manualOperationSequence;
			long version = manualStateVersion;
			manualProtectionBusy = true;
			manualProtectionPending = false;
			manualProtectionResult = null;
			manualReportResult = null;
			manualSaveFailed = false;
			manualSaveStatusText = "이번 요청의 결과를 기다립니다. 저장은 제어 결과가 도착한 뒤 직접 누를 때만 합니다.";
			manualProtectionPhase = ManualProtectionPhase.WaitingAdministrator;
			manualProtectionNotice = "요청한 동작의 관리자 확인과 장치 작업·실제 정리를 기다립니다. 같은 동작을 다시 누르지 마세요.";
			NotifyManualProtection();
			log.Write("MANUAL_PROTECTION_REQUESTED");
			try
			{
				ManualProtectionResult result = await manualProtectionService.RunAsync(operation,
					phase => ReportManualProgress(sequence, phase));
				if (disposed) return;
				if (result == null || result.Operation != operation)
					result = ManualProtectionResult.Failure(operation, ManualProtectionStatus.Unknown);
				manualReportResult = result;
				manualSaveStatusText = "이번 요청의 결과를 받았습니다. ‘제어 결과 TXT 저장’으로 보고서를 저장할 수 있습니다.";
				manualProtectionPending = !result.CleanupComplete;
				manualProtectionPhase = result.IsSuccess ? ManualProtectionPhase.Completed
					: result.CleanupComplete && result.Status != ManualProtectionStatus.Unknown
						? ManualProtectionPhase.Completed : ManualProtectionPhase.Uncertain;
				if (version == manualStateVersion && !IsMockMode)
				{
					manualProtectionResult = result;
					manualProtectionNotice = ResultNotice(result);
				}
				else
				{
					manualProtectionResult = null;
					manualProtectionNotice = result.CleanupComplete
						? "작업은 정리됐지만 절전 복귀·상태 초기화와 겹친 조회값은 현재값으로 표시하지 않습니다. 보호 상태 확인을 다시 누르세요."
						: "복귀 중 작업의 실제 종료가 확인되지 않았습니다. 추가 조회·설정 없이 기다립니다.";
				}
				log.Write(result.IsSuccess ? "MANUAL_PROTECTION_COMPLETED" : "MANUAL_PROTECTION_NOT_CONFIRMED");
			}
			catch
			{
				if (!disposed)
				{
					manualProtectionResult = ManualProtectionResult.Failure(operation, ManualProtectionStatus.Unknown);
					manualReportResult = manualProtectionResult;
					manualSaveStatusText = "결과·실제 정리가 불명확합니다. 제어 결과 TXT에는 미관측·미확인으로 표시하며 저장할 수 있습니다.";
					manualProtectionPending = true;
					manualProtectionPhase = ManualProtectionPhase.Uncertain;
					manualProtectionNotice = "요청 결과와 실제 정리를 확인할 수 없습니다. 추가 동작·자동 재시도 없이 기다립니다.";
					log.Write("MANUAL_PROTECTION_UNCERTAIN");
				}
			}
			finally
			{
				manualProtectionBusy = false;
				if (!disposed) NotifyManualProtection();
			}
		}

		private void ReportManualProgress(long sequence, ManualProtectionPhase phase)
		{
			if (!Enum.IsDefined(typeof(ManualProtectionPhase), phase)) return;
			Action apply = () =>
			{
				if (disposed || !manualProtectionBusy || sequence != manualOperationSequence) return;
				manualProtectionPhase = phase;
				NotifyManualProtection();
			};
			try
			{
				if (manualSynchronizationContext != null && !ReferenceEquals(SynchronizationContext.Current, manualSynchronizationContext))
					manualSynchronizationContext.Post(state => apply(), null);
				else apply();
			}
			catch { /* Progress delivery cannot cancel or complete a device operation. */ }
		}

		public void InvalidateManualState()
		{
			if (disposed) return;
			manualStateVersion++;
			manualProtectionResult = null;
			if (!manualProtectionBusy) manualProtectionPhase = manualProtectionPending ? ManualProtectionPhase.Uncertain : ManualProtectionPhase.Idle;
			manualProtectionNotice = manualProtectionPending
				? "장치 작업의 실제 종료가 확인되지 않았습니다. 상태를 초기화해도 추가 동작 차단은 유지합니다."
				: "보호 조회 후보를 비웠습니다. 실제 제어 전에 보호 상태 확인을 직접 눌러 다시 읽으세요.";
			NotifyManualProtection();
		}

		public void NotifyManualCloseBlocked()
		{
			if (disposed || !ManualProtectionBusy) return;
			manualProtectionNotice = "장치 작업·실제 정리를 기다리는 동안 창을 닫지 않습니다. Pending이면 강제 종료하거나 다시 실행하지 마세요.";
			NotifyManualProtection();
		}

		private void SaveManualProtectionResult()
		{
			if (disposed || manualProtectionBusy || manualReportResult == null || ReferenceEquals(manualReportResult, savedManualReportResult)) return;
			ManualProtectionResult report = manualReportResult;
			string text = "ATIV Battery Guard — 수동 보호 제어 결과\n" +
				"해당 요청의 저장 후보·정리 보고입니다. 현재 설정이나 전기적 충전 효과를 보장하지 않습니다.\n";
			if (report.CleanupComplete) text += report.ToDisplayText();
			else
				text += "수동 보호 작업: " + ManualProtectionResult.OperationText(report.Operation) + "\n" +
					"결과: " + ResultText(report.Status) + "\n" +
					"관련 정리: 미확인 · 실제 종료 대기\n" +
					"SDK 진입·설정 진입·수용 읽기: 미관측. 수신된 값만으로 실제 호출0회를 추정하지 않습니다.\n" +
					"현재 보호 상태: 미확인. 추가 조회·설정·자동 재시도 없이 기다립니다.\n";
			try
			{
				string message = interaction.SaveManualProtectionResult(text);
				if (string.IsNullOrWhiteSpace(message)) throw new InvalidOperationException();
				savedManualReportResult = report;
				manualSaveFailed = false;
				manualSaveStatusText = message + " 같은 요청 결과는 중복 저장하지 않습니다.";
			}
			catch
			{
				manualSaveFailed = true;
				manualSaveStatusText = "제어 결과 TXT 저장을 완료하지 못했습니다. 폴더와 권한을 확인한 뒤 저장만 다시 누르세요. 장치 요청은 반복하지 않습니다.";
				log.Write("UI_ACTION_FAILED");
			}
			NotifyManualProtection();
		}

		private void NotifyManualProtection()
		{
			Changed("ManualProtectionAvailable");
			Changed("ManualProtectionBusy");
			Changed("ManualProtectionPending");
			Changed("CanChangeMockMode");
			Changed("ManualProtectionLastResult");
			Changed("ManualProtectionCurrentPhase");
			Changed("ManualProtectionPhaseText");
			Changed("ManualProtectionNotice");
			Changed("ManualProtectionStateText");
			Changed("ManualProtectionText");
			Changed("ManualSaveStatusText");
			Changed("ManualSaveFailed");
			Changed("ActualModeText");
			ManualReadProtectionCommand?.Refresh();
			ManualEnableProtectionCommand?.Refresh();
			ManualDisableProtectionCommand?.Refresh();
			ManualSaveResultCommand?.Refresh();
		}

		private static string ManualNumber(int? value)
			=> value.HasValue ? value.Value.ToString(CultureInfo.InvariantCulture) : "미조회";

		private static string PhaseText(ManualProtectionPhase phase)
		{
			switch (phase)
			{
				case ManualProtectionPhase.WaitingAdministrator: return "관리자 확인 대기";
				case ManualProtectionPhase.Preparing: return "요청·장치 조건 확인 중";
				case ManualProtectionPhase.Running: return "장치 작업·정리 중";
				case ManualProtectionPhase.WaitingForActualCompletion: return "실제 호출·출력·입력 종료 대기";
				case ManualProtectionPhase.Completed: return "요청 종료";
				case ManualProtectionPhase.Uncertain: return "상태 또는 실제 종료 미확인";
				default: return "대기";
			}
		}

		private static string ResultText(ManualProtectionStatus status)
		{
			switch (status)
			{
				case ManualProtectionStatus.StateRead: return "보호 저장 후보 조회 완료";
				case ManualProtectionStatus.ChangedCandidate: return "요청한 저장 후보 전환 확인";
				case ManualProtectionStatus.AlreadyDesiredCandidate: return "이미 요청한 모드 후보 · 설정 없음";
				case ManualProtectionStatus.Cancelled: return "사용자가 시작을 취소함";
				case ManualProtectionStatus.Unsupported: return "지원 범위 불일치 · 제어 차단";
				case ManualProtectionStatus.PreflightFailed: return "사전 확인 실패 · 제어 차단";
				case ManualProtectionStatus.Rejected: return "요청·응답을 수용하지 않음";
				case ManualProtectionStatus.TimedOut: return "표시 시간 초과 · 실제 종료는 별도 확인";
				case ManualProtectionStatus.Busy: return "다른 작업이 진행 중";
				default: return "결과 불명";
			}
		}

		private static string ResultNotice(ManualProtectionResult result)
		{
			if (!result.CleanupComplete) return "실제 정리가 확인되지 않아 추가 조회·설정을 차단합니다. 창을 강제로 닫거나 다시 실행하지 말고 기다리세요.";
			if (result.Status == ManualProtectionStatus.StateRead) return "이번 요청의 보호 저장 후보를 읽었습니다. 켜기·해제는 각각 직접 선택할 때만 요청합니다.";
			if (result.Status == ManualProtectionStatus.ChangedCandidate) return "저장 후보 전환과 관련 정리를 확인했습니다. 실제 충전 효과는 Windows 배터리 경과와 구분해 확인하세요.";
			if (result.Status == ManualProtectionStatus.AlreadyDesiredCandidate) return "이미 요청한 모드 후보이므로 설정하지 않았습니다. 임계값 확인이 필요하면 보호 상태 확인을 직접 누르세요.";
			if (result.Status == ManualProtectionStatus.Cancelled) return "시작 확인을 취소했습니다. 상태가 필요한 경우 보호 상태 확인을 직접 누르세요.";
			return "저장 상태를 확인하지 못했습니다. 자동 재시도하지 않으며, 정리가 끝난 경우에만 보호 상태 확인을 직접 요청할 수 있습니다.";
		}

		private void StartBatteryObservation()
		{
			if (disposed || IsMockMode || observation.IsRecording) return;
			observation.Start();
			observationSession++;
			observationSaveFailed = false;
			observationSaveStatusText = "새 관찰을 시작했습니다. 다음 배터리 갱신부터 기록하고 저장은 직접 누를 때만 합니다.";
			observationClock.Restart();
			// The next existing refresh supplies the first sample. Starting a
			// session must not perform an extra battery or firmware read.
			NotifyBatteryObservation();
		}

		private void StopBatteryObservation()
		{
			if (disposed) return;
			observationClock.Stop();
			if (observation.IsRecording) observation.Stop();
			NotifyBatteryObservation();
		}

		private void ClearBatteryObservation()
		{
			if (disposed) return;
			observationClock.Reset();
			observation.Clear();
			observationSession++;
			observationSaveFailed = false;
			observationSaveStatusText = "관찰 메모리를 비웠습니다. 이미 저장한 TXT는 삭제하지 않았습니다.";
			NotifyBatteryObservation();
		}

		private void SaveBatteryObservation()
		{
			if (!CanSaveBatteryObservation()) return;
			try
			{
				string message = interaction.SaveBatteryObservation(observation.ExportText());
				if (string.IsNullOrWhiteSpace(message)) throw new InvalidOperationException();
				savedObservationSession = observationSession;
				savedObservationSamples = observation.SampleCount;
				observationSaveFailed = false;
				observationSaveStatusText = message + " 새 샘플이 추가되기 전에는 중복 저장하지 않습니다.";
				StatusMessage = observationSaveStatusText;
			}
			catch
			{
				observationSaveFailed = true;
				observationSaveStatusText = "관찰 TXT 저장을 완료하지 못했습니다. 폴더와 권한을 확인한 뒤 저장을 다시 눌러주세요. 기록은 보관 중입니다.";
				StatusMessage = observationSaveStatusText;
				log.Write("UI_ACTION_FAILED");
			}
			NotifyBatteryObservation();
		}

		private bool CanSaveBatteryObservation()
			=> !disposed && observation.CanExport &&
				(savedObservationSession != observationSession || savedObservationSamples != observation.SampleCount);

		private void NotifyBatteryObservation()
		{
			Changed("ObservationText");
			Changed("ObservationActive");
			Changed("ObservationSampleCount");
			Changed("ObservationGapCount");
			Changed("ObservationSaveStatusText");
			Changed("ObservationSaveFailed");
			StartBatteryObservationCommand?.Refresh();
			StopBatteryObservationCommand?.Refresh();
			ClearBatteryObservationCommand?.Refresh();
			SaveBatteryObservationCommand?.Refresh();
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
				if (observation.IsRecording && !IsMockMode)
				{
					observation.Record(observationClock.Elapsed, snapshot);
					if (!observation.IsRecording) observationClock.Stop();
					NotifyBatteryObservation();
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

		public async Task InspectSamsungFilesAsync()
		{
			if (disposed || samsungFileInspectionBusy || samsungFiles == null) return;
			samsungFileInspectionBusy = true;
			SamsungFileInspectionText = "삼성 파일·SABI 연결·커널 드라이버 후보·WMI 인스턴스의 읽기 전용 정보를 확인하고 있습니다…";
			SamsungFileInspectionStatus = "조회 중입니다. 이전 결과를 사용하지 않습니다.";
			SamsungTransportSummary = "조회 중입니다. 이전 전송 경로 요약을 사용하지 않습니다.";
			Changed("SamsungFileInspectionBusy");
			InspectSamsungFilesCommand.Refresh();
			log.Write("SAMSUNG_FILE_INSPECTION_STARTED");
			bool collected = false;
			try
			{
				SamsungFileInspectionReport report = await Task.Run(() => samsungFiles.Collect());
				if (disposed) return;
				if (report == null) throw new InvalidOperationException();
				SamsungFileInspectionText = report.ToDisplayText();
				SamsungTransportSummary = SamsungTransportAssessment.Evaluate(report).Summary;
				collected = true;
				interaction.SaveSamsungFileInspection(SamsungFileInspectionText);
				SamsungFileInspectionStatus = "결과를 새 samsung-files TXT에 저장했습니다. ‘정보 파일 위치 열기’에서 확인하세요. 파일별 조회 상태도 함께 확인할 수 있습니다.";
				StatusMessage = SamsungFileInspectionStatus;
				log.Write("SAMSUNG_FILE_INSPECTION_SAVED");
			}
			catch
			{
				if (!disposed)
				{
					if (!collected)
					{
						var failedReport = new SamsungFileInspectionReport(
						ATIVBatteryGuard.Core.Models.SamsungFileInspectionStatus.Unavailable,
						driverLink: SabiDriverLinkStatus.Unavailable,
						kernelDrivers: new SamsungKernelDriverReport(SamsungDriverQueryStatus.Unavailable),
						wmiInstances: SamsungWmiInstanceReport.Failure(SamsungWmiQueryStatus.Unavailable));
						SamsungFileInspectionText = failedReport.ToDisplayText();
						SamsungTransportSummary = SamsungTransportAssessment.Evaluate(failedReport).Summary;
					}
					SamsungFileInspectionStatus = collected
						? "조회 결과는 화면에 있지만 TXT를 저장하지 못했습니다. 저장 위치와 권한을 확인하세요."
						: "삼성 파일 정보를 확인하지 못했습니다. 실제 충전 제어는 차단되어 있습니다.";
					StatusMessage = SamsungFileInspectionStatus;
					log.Write("SAMSUNG_FILE_INSPECTION_FAILED");
				}
			}
			finally
			{
				samsungFileInspectionBusy = false;
				if (!disposed)
				{
					Changed("SamsungFileInspectionBusy");
					InspectSamsungFilesCommand.Refresh();
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
				manualStateVersion++;
				manualOperationSequence++;
				manualProtectionResult = null;
				manualReportResult = null;
				observationClock.Stop();
				if (observation.IsRecording) observation.Stop();
				experimentReviewInput = string.Empty;
				fixedReadReviewInput = string.Empty;
				protectionReviewInput = string.Empty;
				NotifyProtectionReview();
				NotifyBatteryObservation();
				NotifyManualProtection();
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
				InspectSamsungFilesCommand.Refresh();
				ReviewExperimentResultCommand.Refresh();
				ClearExperimentReviewCommand.Refresh();
				ReviewFixedReadResultCommand.Refresh();
				ClearFixedReadReviewCommand.Refresh();
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
