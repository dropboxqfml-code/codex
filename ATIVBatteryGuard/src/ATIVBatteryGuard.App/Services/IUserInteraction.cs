using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Services
{
	public interface IUserInteraction
	{
		DeviceDiagnosticsResult ReadDiagnostics();

		void OpenSettingsFolder();

		void ShowLog();

		void CopyDiagnostics(string text);

		string SaveDiagnostics(string text);
	}
}
