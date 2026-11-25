using System;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Services;

namespace ATIVBatteryGuard.ViewModels
{
    public sealed class ObservationNoteViewModel : INotifyPropertyChanged, IDisposable
    {
        private readonly IUserInteraction interaction;
        private readonly SavedBatteryObservation record;
        private ObservationNote saved = ObservationNote.Unavailable("메모를 읽어주세요.");
        private string text = "";
        private string status = "";
        private bool busy, confirming, disposed;
        public event PropertyChangedEventHandler PropertyChanged;
        public event EventHandler StoredNoteChanged;
        public string RecordKey => record.NoteKey;

        public ObservationNoteViewModel(IUserInteraction interaction, SavedBatteryObservation record)
        {
            this.interaction = interaction;
            this.record = record;
            SaveCommand = new RelayCommand(() => SaveCore(), () => !confirming && CanSave);
            ReloadCommand = new RelayCommand(Reload, () => !disposed && !busy && !confirming && ObservationNoteStore.IsValidKey(RecordKey));
            ReadLatest();
        }

        public RelayCommand SaveCommand { get; }
        public RelayCommand ReloadCommand { get; }
        public string Text
        {
            get { return text; }
            set
            {
                if (disposed || busy || confirming) return;
                string normalized = ObservationNote.Normalize(value);
                if (text == normalized) return;
                text = normalized;
                status = !ObservationNoteStore.IsValidText(text) ? "메모는 일반 텍스트로 최대 1000자까지 입력하세요."
                    : HasChanges ? "메모 수정 중 · 저장해 주세요." : "";
                Notify();
            }
        }
        public bool HasChanges => text != saved.Text;
        public bool IsReadOnly => disposed || busy || confirming || !saved.Available || !ObservationNoteStore.IsValidKey(RecordKey);
        public bool CanExport => !IsReadOnly && ObservationNoteStore.IsValidText(text);
        public bool CanSave => !disposed && !busy && !IsReadOnly && HasChanges && ObservationNoteStore.IsValidText(text);
        public string Preview => ObservationNote.Preview(saved.Text);
        public string CharacterCountText => text.Length + "/1000자";
        public string Status => status.Length > 0 ? status : !saved.Available ? "메모를 읽지 못했습니다. 다시 읽기로 확인하세요."
            : HasChanges ? "메모 수정 중 · 저장해 주세요."
            : saved.Text.Length == 0 ? "저장된 메모가 비어 있습니다." : "저장된 메모와 같습니다. 수정 사항이 없습니다.";

        private void ReadLatest()
        {
            try
            {
                var loaded = interaction.LoadObservationNote(record);
                if (disposed) return;
                if (loaded != null && loaded.Available)
                { saved = loaded; text = loaded.Text; status = ""; StoredNoteChanged?.Invoke(this, EventArgs.Empty); }
                else status = loaded?.Notice ?? "메모를 읽지 못했습니다.";
            }
            catch { status = "메모를 읽지 못했습니다. 입력한 내용은 보관 중입니다."; }
            Notify();
        }

        private void Reload()
        {
            if (disposed || busy || confirming || !TryPrepareToClose("메모 다시 읽기")) return;
            busy = true;
            try { ReadLatest(); }
            finally { busy = false; Notify(); }
        }

        private bool SaveCore()
        {
            if (disposed || busy || !saved.Available || !ObservationNoteStore.IsValidKey(RecordKey)
                || !HasChanges || !ObservationNoteStore.IsValidText(text)) return !HasChanges;
            busy = true;
            Notify();
            try
            {
                var result = interaction.SaveObservationNote(record, text, saved.Revision);
                if (disposed) return false;
                if (result == null || !result.Available)
                { status = result?.Notice ?? "메모를 저장하지 못했습니다."; return false; }
                saved = result;
                text = result.Text;
                status = "메모를 저장했습니다.";
                StoredNoteChanged?.Invoke(this, EventArgs.Empty);
                return true;
            }
            catch { status = "메모를 저장하지 못했습니다. 입력한 내용은 보관 중입니다."; return false; }
            finally { busy = false; Notify(); }
        }

        public bool TryPrepareToClose(string action)
        {
            if (disposed || busy || confirming) return false;
            if (!HasChanges) return true;
            confirming = true;
            Notify();
            try
            {
                var choice = interaction.ConfirmUnsavedObservationNote(record.FileName, action);
                if (disposed) return false;
                if (choice == ObservationLossChoice.Discard) return true;
                if (choice == ObservationLossChoice.Save) return SaveCore();
                return false;
            }
            catch { status = "메모 저장 확인을 완료하지 못했습니다. 입력한 내용은 보관 중입니다."; return false; }
            finally { confirming = false; Notify(); }
        }

        public void Dispose()
        {
            disposed = true;
            StoredNoteChanged = null;
            Notify();
        }

        private void Notify()
        {
            Changed("Text"); Changed("HasChanges"); Changed("IsReadOnly"); Changed("CanSave");
            Changed("CanExport"); Changed("Preview"); Changed("CharacterCountText"); Changed("Status");
            SaveCommand.Refresh(); ReloadCommand.Refresh();
        }

        private void Changed([CallerMemberName] string name = null)
        { PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name)); }
    }
}
