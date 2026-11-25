using System;
using System.IO;
using System.Runtime.Serialization.Json;
using ATIVBatteryGuard.ExtendedValidation;

internal static partial class Program
{
    private static ImeEvidence CompleteImeEvidence() => new ImeEvidence {
        SaveCompositionStarts = 1, SaveCompositionUpdates = 2, CloseCompositionStarts = 1, CloseCompositionUpdates = 2,
        SaveKoreanImeObserved = true, CloseKoreanImeObserved = true, SavePointerObserved = true,
        SaveRoundtripPassed = true, CloseCancelPassed = true, UserConfirmedCompositionActions = true };
    private static void RegisterImeEvidenceTests()
    {
        Add("guided IME needs actual composition evidence from both phases even when roundtrips pass", () =>
        {
            var e = CompleteImeEvidence(); Equal("user-assisted-ime-checks-passed-release-pending", e.Outcome(false, true, true, true, null));
            foreach (Action<ImeEvidence> clear in new Action<ImeEvidence>[] { x=>x.SaveCompositionStarts=0, x=>x.SaveCompositionUpdates=0,
                x=>x.CloseCompositionStarts=0, x=>x.CloseCompositionUpdates=0, x=>x.SaveKoreanImeObserved=false,
                x=>x.CloseKoreanImeObserved=false, x=>x.SavePointerObserved=false })
            { var changed=CompleteImeEvidence(); clear(changed); Equal("roundtrip-passed-ime-evidence-incomplete", changed.Outcome(false,true,true,true,null)); }
        });
        Add("guided IME does not confuse focus commit with missing composition and requires explicit user confirmation", () =>
        {
            var e=CompleteImeEvidence(); e.SaveCompositionActiveAtPointer=false; e.CloseCompositionActiveAtRequest=false;
            Equal("user-assisted-ime-checks-passed-release-pending",e.Outcome(false,true,true,true,null));
            e.UserConfirmedCompositionActions=false; Equal("user-confirmation-pending",e.Outcome(false,true,true,true,null));
        });
        Add("guided IME refuses synthetic input cancellation incomplete actions file changes and cleanup failure", () =>
        {
            var e=CompleteImeEvidence(); e.SyntheticKoreanInputInjected=true; Equal("not-passed",e.Outcome(false,true,true,true,null));
            e=CompleteImeEvidence(); e.SaveRoundtripPassed=false; Equal("not-completed",e.Outcome(false,true,true,true,null));
            e=CompleteImeEvidence(); e.CloseCancelPassed=false; Equal("not-completed",e.Outcome(false,true,true,true,null));
            e=CompleteImeEvidence(); Equal("stopped-not-passed",e.Outcome(true,true,true,true,null));
            Equal("not-passed",e.Outcome(false,false,true,true,null)); Equal("not-passed",e.Outcome(false,true,false,true,null));
            Equal("not-passed",e.Outcome(false,true,true,false,null)); Equal("not-passed",e.Outcome(false,true,true,true,"ERROR"));
        });
        Add("IME close diagnostics distinguish every failed predicate without serializing characters", () =>
        {
            Func<ImeCloseState> valid = () => new ImeCloseState { WindowVisible=true, DraftModified=true,
                ModelMatchesExpected=true, DisplayMatchesExpected=true, DisplayMatchesModel=true, StoredAvailable=true, StoredMatchesBaseline=true };
            Check(valid().FailureCode() == null, "valid close state rejected");
            Action<ImeCloseState>[] clear = { x=>x.WindowVisible=false, x=>x.DraftModified=false, x=>x.ModelMatchesExpected=false,
                x=>x.DisplayMatchesExpected=false, x=>x.DisplayMatchesModel=false, x=>x.StoredAvailable=false, x=>x.StoredMatchesBaseline=false };
            string[] codes = { "IME_CLOSE_WINDOW_NOT_VISIBLE", "IME_CLOSE_DRAFT_NOT_MODIFIED", "IME_CLOSE_MODEL_TEXT_MISMATCH",
                "IME_CLOSE_DISPLAY_TEXT_MISMATCH", "IME_CLOSE_BINDING_MISMATCH", "IME_CLOSE_STORED_NOTE_UNAVAILABLE", "IME_CLOSE_STORED_NOTE_CHANGED" };
            for(int index=0;index<clear.Length;index++) { var state=valid(); clear[index](state); Equal(codes[index],state.FailureCode()); }
            using(var output=new MemoryStream())
            {
                new DataContractJsonSerializer(typeof(ImeCloseDiagnostics)).WriteObject(output,new ImeCloseDiagnostics { BeforeProductClose=valid(), BeforeConfirmation=valid(), AfterCancellation=valid() });
                string json=System.Text.Encoding.UTF8.GetString(output.ToArray());
                Check(!json.Contains(ImeEvidence.ClosePhrase) && !json.Contains(ImeEvidence.SavePhrase),"characters persisted");
            }
        });
        Add("focused IME close mode retains prior save evidence without fabricating a fresh save test", () =>
        {
            var evidence=CompleteImeEvidence(); evidence.SaveRoundtripPassed=false; evidence.SaveCompositionStarts=0;
            evidence.SaveCompositionUpdates=0; evidence.SaveKoreanImeObserved=false; evidence.SavePointerObserved=false;
            Equal("user-assisted-ime-close-checks-passed-release-pending",evidence.CloseOnlyOutcome(false,true,true,true,null));
            Check(evidence.Outcome(false,true,true,true,null)!="user-assisted-ime-checks-passed-release-pending","full IME pass fabricated");
            evidence.CloseCompositionUpdates=0; Equal("close-passed-ime-evidence-incomplete",evidence.CloseOnlyOutcome(false,true,true,true,null));
            evidence.CloseCompositionUpdates=1; evidence.UserConfirmedCompositionActions=false;
            Equal("user-confirmation-pending",evidence.CloseOnlyOutcome(false,true,true,true,null));
            Equal("not-passed",evidence.CloseOnlyOutcome(false,true,false,true,null));
            Equal("not-passed",evidence.CloseOnlyOutcome(false,true,true,true,"ERROR"));
            Equal("stopped-not-passed",evidence.CloseOnlyOutcome(true,true,true,true,null));
            Check(ExtendedPolicy.IsImeClose(new[]{"--ime-close"}) && !ExtendedPolicy.IsImeClose(new[]{"--ime-close","extra"}),"close mode arguments incorrect");
            using(var f=new Fixture()) { var journal=new StartupJournal(f.DirectoryPath); journal.SelectImeCloseMode(); Equal("guided-ime-close",ReadStartup(journal.ReportPath).Mode); }
        });

        Add("guided IME mode does not accept extra arguments and evidence never serializes typed text", () =>
        {
            Check(ExtendedPolicy.IsIme(new[]{"--ime"}),"IME mode missing");
            Check(!ExtendedPolicy.IsIme(new[]{"--ime","private"}) && !ExtendedPolicy.IsIme(new[]{"--ime;run"}) && !ExtendedPolicy.IsIme(null),"unexpected arguments accepted");
            using(var output=new MemoryStream())
            {
                new DataContractJsonSerializer(typeof(ImeEvidence)).WriteObject(output,CompleteImeEvidence());
                string text=System.Text.Encoding.UTF8.GetString(output.ToArray());
                Check(!text.Contains(ImeEvidence.SavePhrase) && !text.Contains(ImeEvidence.ClosePhrase) && !text.Contains("Text\":"),"text persisted");
            }
            using(var f=new Fixture())
            {
                var journal=new StartupJournal(f.DirectoryPath); journal.SelectImeMode();
                Equal("guided-ime",ReadStartup(journal.ReportPath).Mode);
            }
        });
    }
}
