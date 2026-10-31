namespace ATIVBatteryGuard.Core.Models
{
	public sealed class ReferencedModuleDecision
	{
		public bool Allowed { get; private set; }

		public bool IsDataOnly => Allowed;

		public bool HardwareWriteAllowed => false;

		public bool ExecutionAllowed => false;

		public string ReasonCode { get; private set; }

		public string Architecture { get; private set; }

		public PeModuleInfo Metadata { get; private set; }

		public bool DetailedMetadataAvailable { get; private set; }

		internal ReferencedModuleDecision(bool allowed, string reasonCode, string architecture, PeModuleInfo metadata, bool detailedMetadataAvailable)
		{
			Allowed = allowed;
			ReasonCode = reasonCode;
			Architecture = ((architecture == "x86" || architecture == "x64") ? architecture : "Unknown");
			Metadata = metadata ?? new PeModuleInfo(isValid: false, isManaged: false, "Unknown", null, null, "상세 PE 정보가 없습니다.");
			DetailedMetadataAvailable = allowed && detailedMetadataAvailable && Metadata.IsValid;
		}
	}
}
