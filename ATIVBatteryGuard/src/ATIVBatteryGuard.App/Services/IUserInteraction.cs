using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Services
{
	public interface IUserInteraction
	{
		DeviceDiagnosticsResult ReadDiagnostics();

		void OpenSettingsFolder();

		void ShowLog();

		void CopyDiagnostics(string text);

		string SaveDiagnostics(string text);

		string SaveSamsungFileInspection(string text);

		string SaveBatteryObservation(string text);

		SavedBatteryObservation OpenBatteryObservation();

		string SaveManualProtectionResult(string text);
	}
}
