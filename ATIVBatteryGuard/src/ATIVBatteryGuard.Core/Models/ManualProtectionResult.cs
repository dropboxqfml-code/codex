using System;
using System.Globalization;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum ManualProtectionOperation { ReadState, Enable80, DisableProtection }
    public enum ManualProtectionStatus
    {
        StateRead, ChangedCandidate, AlreadyDesiredCandidate, Cancelled, Unsupported,
        PreflightFailed, Rejected, TimedOut, Unknown, Busy
    }
    public enum ManualProtectionPhase
    {
        Idle, WaitingAdministrator, Preparing, Running, WaitingForActualCompletion, Completed, Uncertain
    }

    public static class ManualProtectionLimits
    {
        public static int MaximumSdkEntries(ManualProtectionOperation operation)
        { Validate(operation); return operation == ManualProtectionOperation.Enable80 ? 7 : 3; }
        public static int MaximumReadCandidates(ManualProtectionOperation operation)
        { Validate(operation); return operation == ManualProtectionOperation.ReadState ? 3 : operation == ManualProtectionOperation.Enable80 ? 6 : 2; }
        public static int MaximumSetterEntries(ManualProtectionOperation operation)
        { Validate(operation); return operation == ManualProtectionOperation.ReadState ? 0 : 1; }
        internal static void Validate(ManualProtectionOperation operation)
        { if (!Enum.IsDefined(typeof(ManualProtectionOperation), operation)) throw new ArgumentOutOfRangeException(nameof(operation)); }
    }

    // A bounded detached result, never an authority to execute a request, a
    // continuous current-state guarantee, or a measurement of charger current.
    public sealed class ManualProtectionResult
    {
        public ManualProtectionOperation Operation { get; }
        public ManualProtectionStatus Status { get; }
        public bool CleanupComplete { get; }
        public bool ProfileValidated { get; }
        public int SdkEntries { get; }
        public int SetterEntries { get; }
        public int ReadCandidates { get; }
        public int? PreModeCandidate { get; }
        public int? ModeCandidate { get; }
        public int? UpperCandidate { get; }
        public int? LowerCandidate { get; }
        public bool IsSuccess => CleanupComplete && ProfileValidated &&
            (Status == ManualProtectionStatus.StateRead || Status == ManualProtectionStatus.ChangedCandidate ||
             Status == ManualProtectionStatus.AlreadyDesiredCandidate);
        public bool HasKnownMode => IsSuccess && CleanupComplete && ProfileValidated && ModeCandidate.HasValue;
        public bool IsPending => !CleanupComplete;
        public bool IsUncertain => !CleanupComplete || Status == ManualProtectionStatus.Unknown || Status == ManualProtectionStatus.TimedOut;
        public bool IsChargeLimitConfirmed => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        public ManualProtectionResult(ManualProtectionOperation operation, ManualProtectionStatus status,
            bool cleanupComplete, bool profileValidated, int sdkEntries = 0, int setterEntries = 0,
            int readCandidates = 0, int? preModeCandidate = null, int? modeCandidate = null,
            int? upperCandidate = null, int? lowerCandidate = null)
        {
            ManualProtectionLimits.Validate(operation);
            if (!Enum.IsDefined(typeof(ManualProtectionStatus), status)) throw new ArgumentOutOfRangeException(nameof(status));
            if (sdkEntries < 0 || sdkEntries > ManualProtectionLimits.MaximumSdkEntries(operation) ||
                setterEntries < 0 || setterEntries > ManualProtectionLimits.MaximumSetterEntries(operation) ||
                readCandidates < 0 || readCandidates > ManualProtectionLimits.MaximumReadCandidates(operation) ||
                setterEntries > sdkEntries || readCandidates > sdkEntries - setterEntries)
                throw new ArgumentException("The fixed manual operation counters are inconsistent.");
            if (!Mode(preModeCandidate) || !Mode(modeCandidate) || !Byte(upperCandidate) || !Byte(lowerCandidate))
                throw new ArgumentException("The supplied detached candidates are outside their bounds.");
            if (preModeCandidate.HasValue && readCandidates == 0)
                throw new ArgumentException("A pre-mode candidate requires a read candidate.");
            bool success = status == ManualProtectionStatus.StateRead || status == ManualProtectionStatus.ChangedCandidate ||
                status == ManualProtectionStatus.AlreadyDesiredCandidate;
            if (!cleanupComplete && status != ManualProtectionStatus.Unknown && status != ManualProtectionStatus.TimedOut)
                throw new ArgumentException("Unconfirmed cleanup cannot be represented as a completed operation.");
            if (success)
            {
                if (!cleanupComplete || !profileValidated) throw new ArgumentException("A successful shape requires completed cleanup and the fixed profile.");
                bool shape;
                if (status == ManualProtectionStatus.StateRead)
                    shape = operation == ManualProtectionOperation.ReadState && sdkEntries == 3 && setterEntries == 0 &&
                        readCandidates == 3 && modeCandidate.HasValue && upperCandidate.HasValue && lowerCandidate.HasValue &&
                        (!preModeCandidate.HasValue || preModeCandidate == modeCandidate);
                else if (status == ManualProtectionStatus.AlreadyDesiredCandidate)
                    shape = operation != ManualProtectionOperation.ReadState && sdkEntries == 1 && setterEntries == 0 && readCandidates == 1 &&
                        modeCandidate == (operation == ManualProtectionOperation.Enable80 ? 1 : 0) && preModeCandidate == modeCandidate &&
                        !upperCandidate.HasValue && !lowerCandidate.HasValue;
                else if (operation == ManualProtectionOperation.Enable80)
                    shape = sdkEntries == 7 && setterEntries == 1 && readCandidates == 6 && preModeCandidate == 0 &&
                        modeCandidate == 1 && upperCandidate == 80 && lowerCandidate == 75;
                else
                    shape = operation == ManualProtectionOperation.DisableProtection && sdkEntries == 3 && setterEntries == 1 &&
                        readCandidates == 2 && preModeCandidate == 1 && modeCandidate == 0 && !upperCandidate.HasValue && !lowerCandidate.HasValue;
                if (!shape) throw new ArgumentException("The result does not match a complete fixed manual operation.");
            }
            else
            {
                if (modeCandidate.HasValue || upperCandidate.HasValue || lowerCandidate.HasValue)
                    throw new ArgumentException("A failed or uncertain result cannot publish a new mode or threshold snapshot.");
                if ((status == ManualProtectionStatus.Cancelled || status == ManualProtectionStatus.Unsupported ||
                     status == ManualProtectionStatus.PreflightFailed || status == ManualProtectionStatus.Busy) &&
                    (profileValidated || sdkEntries != 0 || setterEntries != 0 || readCandidates != 0 || preModeCandidate.HasValue))
                    throw new ArgumentException("A no-entry result cannot contain execution counters or candidates.");
            }
            Operation = operation; Status = status; CleanupComplete = cleanupComplete; ProfileValidated = profileValidated;
            SdkEntries = sdkEntries; SetterEntries = setterEntries; ReadCandidates = readCandidates;
            PreModeCandidate = preModeCandidate; ModeCandidate = modeCandidate; UpperCandidate = upperCandidate; LowerCandidate = lowerCandidate;
        }

        public static ManualProtectionResult Failure(ManualProtectionOperation operation, ManualProtectionStatus status)
            => Failure(operation, status, status != ManualProtectionStatus.Unknown && status != ManualProtectionStatus.TimedOut);

        public static ManualProtectionResult Failure(ManualProtectionOperation operation, ManualProtectionStatus status,
            bool cleanupComplete, bool profileValidated = false, int sdkEntries = 0, int setterEntries = 0,
            int readCandidates = 0, int? preModeCandidate = null)
        {
            if (status == ManualProtectionStatus.StateRead || status == ManualProtectionStatus.ChangedCandidate ||
                status == ManualProtectionStatus.AlreadyDesiredCandidate)
                throw new ArgumentException("A failure factory cannot create successful state.");
            return new ManualProtectionResult(operation, status, cleanupComplete, profileValidated,
                sdkEntries, setterEntries, readCandidates, preModeCandidate);
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("수동 보호 작업: " + OperationText(Operation));
            text.AppendLine("결과: " + StatusText(Status));
            text.AppendLine("관련 정리: " + (CleanupComplete ? "Complete" : "미확인 · 추가 작업 대기"));
            text.AppendLine("SDK 진입: " + Number(SdkEntries) + " / 설정 진입: " + Number(SetterEntries) + " / 읽기 후보: " + Number(ReadCandidates));
            if (!CleanupComplete) text.AppendLine("이 횟수는 수신된 보고 범위이며 실제 호출이0회였다는 보장이 아닙니다.");
            if (PreModeCandidate.HasValue) text.AppendLine("사전 모드 후보: " + Number(PreModeCandidate.Value));
            if (HasKnownMode)
            {
                text.AppendLine("마지막 모드 후보: " + Number(ModeCandidate.Value));
                text.AppendLine("상한 / 하한 후보: " + Candidate(UpperCandidate) + " / " + Candidate(LowerCandidate));
                if (Status == ManualProtectionStatus.AlreadyDesiredCandidate)
                    text.AppendLine("이미 요청한 모드 후보여서 설정하지 않았습니다. 임계값은 이번 작업에서 조회하지 않았습니다.");
                if (ModeCandidate == 0) text.AppendLine("보호 해제 후보입니다. 100% 충전 완료나 이전 임계값 복원을 뜻하지 않습니다.");
            }
            else text.AppendLine("새 보호 상태: 미확인. 과거 조회나 입력값을 현재 설정으로 표시하지 않습니다.");
            text.AppendLine("마지막 조회 후보와 Windows 배터리 잔량은 별개이며 전기적 충전 효과를 측정한 결과가 아닙니다.");
            if (IsUncertain) text.AppendLine("불명 결과에서 자동 재시도·반대 방향 설정을 하지 않습니다.");
            return text.ToString();
        }

        public static string OperationText(ManualProtectionOperation operation)
        {
            ManualProtectionLimits.Validate(operation);
            return operation == ManualProtectionOperation.ReadState ? "보호 상태 확인" :
                operation == ManualProtectionOperation.Enable80 ? "80% 보호 켜기" : "보호 해제 · 일반 충전";
        }
        private static string StatusText(ManualProtectionStatus status)
        {
            switch (status)
            {
                case ManualProtectionStatus.StateRead: return "고정 상태 조회 후보 수용";
                case ManualProtectionStatus.ChangedCandidate: return "사전·사후 저장 후보 일치";
                case ManualProtectionStatus.AlreadyDesiredCandidate: return "이미 요청한 모드 후보 · 쓰기 없음";
                case ManualProtectionStatus.Cancelled: return "사용자가 시작을 취소함";
                case ManualProtectionStatus.Unsupported: return "지원 대상 확인 실패 · 호출 없음";
                case ManualProtectionStatus.PreflightFailed: return "사전 검증 실패 · 호출 없음";
                case ManualProtectionStatus.Rejected: return "요청 또는 응답 조건 불일치";
                case ManualProtectionStatus.TimedOut: return "표시 시간 초과 · 실제 종료 별도 확인";
                case ManualProtectionStatus.Busy: return "다른 작업 진행 또는 차단 중 · 새 호출 없음";
                default: return "결과 불명";
            }
        }
        private static bool Mode(int? value) => !value.HasValue || value == 0 || value == 1;
        private static bool Byte(int? value) => !value.HasValue || value.Value >= 0 && value.Value <= 255;
        private static string Number(int value) => value.ToString(CultureInfo.InvariantCulture);
        private static string Candidate(int? value) => value.HasValue ? Number(value.Value) : "미조회";
    }
}
