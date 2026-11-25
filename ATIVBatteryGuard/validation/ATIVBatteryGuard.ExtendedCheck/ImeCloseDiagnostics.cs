using System.Runtime.Serialization;

namespace ATIVBatteryGuard.ExtendedValidation
{
    [DataContract]
    public sealed class ImeCloseState
    {
        [DataMember] public bool WindowVisible;
        [DataMember] public bool DraftModified;
        [DataMember] public bool ModelMatchesExpected;
        [DataMember] public bool DisplayMatchesExpected;
        [DataMember] public bool DisplayMatchesModel;
        [DataMember] public bool CompositionActive;
        [DataMember] public bool? StoredAvailable;
        [DataMember] public bool? StoredMatchesBaseline;
        public string FailureCode()
        {
            if (!WindowVisible) return "IME_CLOSE_WINDOW_NOT_VISIBLE";
            if (!DraftModified) return "IME_CLOSE_DRAFT_NOT_MODIFIED";
            if (!ModelMatchesExpected) return "IME_CLOSE_MODEL_TEXT_MISMATCH";
            if (!DisplayMatchesExpected) return "IME_CLOSE_DISPLAY_TEXT_MISMATCH";
            if (!DisplayMatchesModel) return "IME_CLOSE_BINDING_MISMATCH";
            if (StoredAvailable != true) return "IME_CLOSE_STORED_NOTE_UNAVAILABLE";
            if (StoredMatchesBaseline != true) return "IME_CLOSE_STORED_NOTE_CHANGED";
            return null;
        }
    }
    [DataContract]
    public sealed class ImeCloseDiagnostics
    {
        [DataMember] public bool NativeCloseRequestObserved;
        [DataMember] public bool ProductCancelledBeforeHostGuard;
        [DataMember] public bool GuardBlockedClose;
        [DataMember] public ImeCloseState BeforeProductClose;
        [DataMember] public ImeCloseState BeforeConfirmation;
        [DataMember] public ImeCloseState AfterCancellation;
    }
}
