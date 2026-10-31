using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Storage
{
	public sealed class SettingsLoadResult
	{
		public AppSettings Settings { get; private set; }

		public string Warning { get; private set; }

		public bool CanSave { get; private set; }

		public SettingsLoadResult(AppSettings settings, string warning, bool canSave)
		{
			Settings = settings;
			Warning = warning;
			CanSave = canSave;
		}
	}
}
