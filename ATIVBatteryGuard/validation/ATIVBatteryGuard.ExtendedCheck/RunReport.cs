using System;
using System.Collections.Generic;
using System.Runtime.Serialization;

namespace ATIVBatteryGuard.ExtendedValidation
{
    [DataContract]
    internal sealed class RunReport
    {
        [DataMember] public int SchemaVersion = 1;
        [DataMember] public string ToolRevision = "extended-v3";
        [DataMember] public string ReleaseVersion = "0.3.0-rc.2";
        [DataMember] public string SourceFingerprintSha256;
        [DataMember] public string StartedUtc = DateTime.UtcNow.ToString("O");
        [DataMember] public string UpdatedUtc;
        [DataMember] public string CompletedUtc;
        [DataMember] public string Outcome = "running-not-passed";
        [DataMember] public string Phase = "starting";
        [DataMember] public string LastActivePhase;
        [DataMember] public string Mode;
        [DataMember] public bool FilesVerifiedBefore;
        [DataMember] public bool FilesVerifiedAfter;
        [DataMember] public bool CommittedKoreanBindingPassed;
        [DataMember] public bool OwnedNativeConfirmationDialogsPassed;
        [DataMember] public bool WindowCloseCancelPassed;
        [DataMember] public bool BothDraftsCancelPassed;
        [DataMember] public bool TwoWindowConflictAndBackupPassed;
        [DataMember] public bool LockedSaveRetryPassed;
        [DataMember] public int CompletedCycles;
        [DataMember] public double RepetitionSeconds;
        [DataMember] public double MaximumCycleGapSeconds;
        [DataMember] public int BindingErrors;
        [DataMember] public int AutomatedDialogCount;
        [DataMember] public bool CleanupSucceeded;
        [DataMember] public bool StopRequested;
        [DataMember] public string ErrorCode;
        [DataMember] public bool ImeCompositionEngineTested = false;
        [DataMember] public bool NativeFilePickersAutomated = false;
        [DataMember] public bool SeparateProcessContentionTested = false;
        [DataMember] public bool HardwareWritesPerformed = false;
        [DataMember] public bool BatteryOrOemQueriesPerformed = false;
        [DataMember] public bool DefenderScanExecuted = false;
        [DataMember] public bool AuthenticodeSigningPerformed = false;
        [DataMember] public bool FinalReleaseApproved = false;
        [DataMember] public string MemoryVerdict = "observations-only-no-leak-free-claim";
        [DataMember] public List<MemorySample> Samples = new List<MemorySample>();
    }
    [DataContract]
    internal sealed class MemorySample
    {
        [DataMember] public double ElapsedSeconds;
        [DataMember] public int Cycles;
        [DataMember] public long PrivateBytes;
        [DataMember] public long WorkingSetBytes;
        [DataMember] public long ManagedBytes;
        [DataMember] public int HandleCount;
        [DataMember] public double DispatcherRoundTripMilliseconds;
    }
}
