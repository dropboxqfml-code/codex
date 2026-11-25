using System.Runtime.Serialization;

namespace ATIVBatteryGuard.ExtendedValidation
{
    [DataContract]
    public sealed class ImeEvidence
    {
        public const string SavePhrase = "한글 입력 확인";
        public const string ClosePhrase = "종료 취소 확인";
        [DataMember] public int SaveCompositionStarts;
        [DataMember] public int SaveCompositionUpdates;
        [DataMember] public int CloseCompositionStarts;
        [DataMember] public int CloseCompositionUpdates;
        [DataMember] public bool SaveKoreanImeObserved;
        [DataMember] public bool CloseKoreanImeObserved;
        [DataMember] public bool SavePointerObserved;
        [DataMember] public bool SaveCompositionActiveAtPointer;
        [DataMember] public bool CloseCompositionActiveAtRequest;
        [DataMember] public bool SaveExpectedTextVisibleBeforePointer;
        [DataMember] public bool SaveRoundtripPassed;
        [DataMember] public bool CloseCancelPassed;
        [DataMember] public bool UserConfirmedCompositionActions;
        [DataMember] public bool SyntheticKoreanInputInjected = false;
        public string CloseOnlyOutcome(bool stopped, bool filesBefore, bool filesAfter, bool cleanup, string error)
        {
            if (stopped) return "stopped-not-passed";
            if (error != null || !filesBefore || !filesAfter || !cleanup || SyntheticKoreanInputInjected) return "not-passed";
            if (!CloseCancelPassed) return "not-completed";
            if (!UserConfirmedCompositionActions) return "user-confirmation-pending";
            if (!CloseKoreanImeObserved || CloseCompositionStarts < 1 || CloseCompositionUpdates < 1)
                return "close-passed-ime-evidence-incomplete";
            return "user-assisted-ime-close-checks-passed-release-pending";
        }
        public string Outcome(bool stopped, bool filesBefore, bool filesAfter, bool cleanup, string error)
        {
            if (stopped) return "stopped-not-passed";
            if (error != null || !filesBefore || !filesAfter || !cleanup || SyntheticKoreanInputInjected) return "not-passed";
            if (!SaveRoundtripPassed || !CloseCancelPassed) return "not-completed";
            if (!UserConfirmedCompositionActions) return "user-confirmation-pending";
            if (!SavePointerObserved || !SaveKoreanImeObserved || !CloseKoreanImeObserved
                || SaveCompositionStarts < 1 || SaveCompositionUpdates < 1 || CloseCompositionStarts < 1 || CloseCompositionUpdates < 1)
                return "roundtrip-passed-ime-evidence-incomplete";
            return "user-assisted-ime-checks-passed-release-pending";
        }
    }
}
