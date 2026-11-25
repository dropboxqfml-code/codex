using System.Collections.Generic;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Services
{
    public enum ObservationLossChoice { Cancel, Save, Discard }

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

        ObservationLossChoice ConfirmUnsavedObservation(string action);
        IReadOnlyList<RecentObservationEntry> ReadRecentObservations();
        SavedBatteryObservation OpenRecentObservation(RecentObservationEntry entry);
        string RecentObservationNotice { get; }
        ObservationNote LoadObservationNote(SavedBatteryObservation record);
        ObservationNote SaveObservationNote(SavedBatteryObservation record, string text, string expectedRevision);
        ObservationLossChoice ConfirmUnsavedObservationNote(string fileName, string action);

		string SaveManualProtectionResult(string text);
	}
}
