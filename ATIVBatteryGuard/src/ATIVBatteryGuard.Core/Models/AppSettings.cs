using System;
using System.Runtime.Serialization;

namespace ATIVBatteryGuard.Core.Models
{
	[DataContract]
	public sealed class AppSettings
	{
		[DataMember(Name = "schemaVersion", IsRequired = true, Order = 0)]
		public int SchemaVersion { get; set; }

		[IgnoreDataMember]
		public ChargeMode DesiredMode { get; set; }

		[DataMember(Name = "desiredMode", IsRequired = true, Order = 1)]
		private string DesiredModeValue
		{
			get
			{
				return DesiredMode.ToString();
			}
			set
			{
				DesiredMode = ((Enum.TryParse<ChargeMode>(value, ignoreCase: false, out var result) && (result == ChargeMode.Normal100 || result == ChargeMode.Protection80) && value == result.ToString()) ? result : ChargeMode.Unknown);
			}
		}

		[DataMember(Name = "restoreOnBoot", IsRequired = true, Order = 2)]
		public bool RestoreOnBoot { get; set; }

		[DataMember(Name = "mockModeEnabled", IsRequired = true, Order = 3)]
		public bool MockModeEnabled { get; set; }

		[DataMember(Name = "lastUiState", IsRequired = true, Order = 4)]
		public string LastUiState { get; set; }

		public AppSettings()
		{
			SchemaVersion = 1;
			DesiredMode = ChargeMode.Normal100;
			LastUiState = "Normal";
		}

		public bool IsValid(out string reason)
		{
			if (SchemaVersion != 1)
			{
				reason = "지원하지 않는 설정 형식 버전입니다.";
				return false;
			}
			if (DesiredMode != ChargeMode.Normal100 && DesiredMode != ChargeMode.Protection80)
			{
				reason = "사용자 희망 설정 값이 올바르지 않습니다.";
				return false;
			}
			if (LastUiState != "Normal" && LastUiState != "Maximized")
			{
				reason = "저장된 창 상태가 올바르지 않습니다.";
				return false;
			}
			reason = string.Empty;
			return true;
		}
	}
}
