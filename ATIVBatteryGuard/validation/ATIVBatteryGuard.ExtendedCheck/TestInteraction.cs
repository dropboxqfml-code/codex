using System;
using System.Collections.Generic;
using System.IO;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Services;

namespace ATIVBatteryGuard.ExtendedValidation
{
    internal sealed class SyntheticBattery : IBatteryStatusProvider
    {
        public BatterySnapshot Read() => new BatterySnapshot(80, ExternalPowerStatus.Connected,
            BatteryChargeState.NotCharging, "");
    }
    internal sealed class TestInteraction : IUserInteraction
    {
        private readonly string root;
        private readonly LocalUserInteraction dialogs;
        private readonly ObservationNoteStore notes;
        private readonly RecentObservationStore recent;
        public SavedBatteryObservation NextRecord;
        public ObservationLossChoice NextChoice = ObservationLossChoice.Cancel;
        public string LastBundle;
        public int Confirmations;
        public bool DialogAutomationFailed;
        public TestInteraction(string root)
        {
            this.root = root;
            notes = new ObservationNoteStore(root); recent = new RecentObservationStore(root);
            dialogs = new LocalUserInteraction(root, new LocalLog(root));
        }
        public ObservationNote ReadNote(SavedBatteryObservation record) => notes.Load(record.NoteKey);
        public DeviceDiagnosticsResult ReadDiagnostics() { throw new InvalidOperationException(); }
        public void OpenSettingsFolder() { throw new InvalidOperationException(); }
        public void ShowLog() { throw new InvalidOperationException(); }
        public void CopyDiagnostics(string text) { throw new InvalidOperationException(); }
        public string SaveDiagnostics(string text) { throw new InvalidOperationException(); }
        public string SaveSamsungFileInspection(string text) { throw new InvalidOperationException(); }
        public string SaveBatteryObservation(string text) { throw new InvalidOperationException(); }
        public string SaveManualProtectionResult(string text) { throw new InvalidOperationException(); }
        public SavedBatteryObservation OpenBatteryObservation() => NextRecord;
        public string ExportObservationBundle(SavedBatteryObservation record, string noteText)
        {
            LastBundle = Path.Combine(root, "backup-" + Guid.NewGuid().ToString("N") + ".ativrecord");
            ObservationBundle.Create(record, noteText).Export(LastBundle); return LastBundle;
        }
        public ObservationBundle OpenObservationBundle() { throw new InvalidOperationException(); }
        public SavedBatteryObservation ImportObservationBundle(ObservationBundle bundle) { throw new InvalidOperationException(); }
        public ObservationLossChoice ConfirmUnsavedObservation(string action) { throw new InvalidOperationException(); }
        public IReadOnlyList<RecentObservationEntry> ReadRecentObservations() => recent.Load();
        public SavedBatteryObservation OpenRecentObservation(RecentObservationEntry entry)
        { using (var file = File.OpenRead(entry.Path)) return SavedBatteryObservation.Read(file, Path.GetFileName(entry.Path), entry.Path); }
        public string RecentObservationNotice => "";
        public ObservationNote LoadObservationNote(SavedBatteryObservation record) => notes.Load(record.NoteKey);
        public ObservationNote SaveObservationNote(SavedBatteryObservation record, string text, string expectedRevision)
            => notes.Save(record.NoteKey, text, expectedRevision);
        public ObservationLossChoice ConfirmUnsavedObservationNote(string fileName, string action)
        {
            // Exercise the product's real modal dialog, selecting a button only in this
            // thread's owned dialog; no global keyboard or mouse events are sent.
            try
            {
                var selected = OwnedDialog.Choose(() => dialogs.ConfirmUnsavedObservationNote(fileName, action), NextChoice);
                Confirmations++; return selected;
            }
            catch { DialogAutomationFailed = true; throw; }
        }
    }
}
