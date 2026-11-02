using System;
using System.Text;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Core.Models
{
    public enum ProcessElevationState { Unknown, NotElevated, Elevated }
    public enum SamsungWmiAccessStage { NotStarted, Connect, Query, Enumerate, ReadProperties, Completed }
    public enum SamsungWmiAccessCode
    {
        None, WmiAccessDenied, WindowsAccessDenied, WmiClassNotFound, WmiNamespaceNotFound,
        WmiNotFound, WmiTimedOut, WindowsTimedOut, Other
    }

    // Only fixed phase/error categories; no exception message, identifier or path.
    public sealed class SamsungWmiAccessTrace
    {
        public SamsungWmiClass Kind { get; }
        public SamsungWmiAccessStage Stage { get; }
        public SamsungWmiAccessCode Code { get; }

        public SamsungWmiAccessTrace(SamsungWmiClass kind, SamsungWmiAccessStage stage, SamsungWmiAccessCode code)
        {
            if (!Enum.IsDefined(typeof(SamsungWmiClass), kind)) throw new ArgumentOutOfRangeException(nameof(kind));
            Kind = kind;
            Stage = Enum.IsDefined(typeof(SamsungWmiAccessStage), stage) ? stage : SamsungWmiAccessStage.NotStarted;
            Code = Enum.IsDefined(typeof(SamsungWmiAccessCode), code) ? code : SamsungWmiAccessCode.Other;
        }
    }

    public sealed class SamsungWmiAccessProbeResult
    {
        public SamsungWmiInstanceReport Observation { get; }
        public SamsungWmiAccessTrace VersionTrace { get; }
        public SamsungWmiAccessTrace MethodTrace { get; }
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;
        public bool CanInvokeMethods => false;

        public SamsungWmiAccessProbeResult(SamsungWmiInstanceReport observation,
            SamsungWmiAccessTrace versionTrace, SamsungWmiAccessTrace methodTrace)
        {
            var source = observation ?? SamsungWmiInstanceReport.Failure(SamsungWmiQueryStatus.Unavailable);
            bool invalidVersion = versionTrace != null && versionTrace.Kind != SamsungWmiClass.Version;
            bool invalidMethod = methodTrace != null && methodTrace.Kind != SamsungWmiClass.Method;
            VersionTrace = FixedTrace(versionTrace, SamsungWmiClass.Version);
            MethodTrace = FixedTrace(methodTrace, SamsungWmiClass.Method);
            Observation = new SamsungWmiInstanceReport(
                invalidVersion ? new SamsungWmiClassObservation(SamsungWmiClass.Version, SamsungWmiQueryStatus.InvalidResponse) : source.VersionClass,
                invalidMethod ? new SamsungWmiClassObservation(SamsungWmiClass.Method, SamsungWmiQueryStatus.InvalidResponse) : source.MethodClass);
        }

        public string ToDisplayText(ProcessElevationState elevation)
        {
            var text = new StringBuilder();
            text.AppendLine("ATIV Battery Guard — 고정 WMI 속성 읽기 권한 비교");
            text.AppendLine("현재 프로세스 토큰 상승 상태: " + ElevationText(elevation));
            AppendTrace(text, Observation.VersionClass, VersionTrace);
            AppendTrace(text, Observation.MethodClass, MethodTrace);
            text.AppendLine("단계는 조회가 진행되거나 실패한 위치이며 거부 원인을 확정하지 않습니다. None도 권한 허용이나 전체 조회 성공의 증거가 아닙니다.");
            text.AppendLine("상승된 토큰 또는 조회 성공은 관리자 실행이 문제를 해결한다는 일반적 증거나 배터리 제어 지원의 증거가 아닙니다.");
            text.AppendLine("이 도구는 권한 상승·UAC 요청·ACL 변경을 수행하지 않습니다. 관리자 비교 실행은 별도 승인이 필요한 작업입니다.");
            text.AppendLine("사용자 이름·SID·그룹·인스턴스 이름·장치 식별자·경로·원문 예외는 출력하지 않습니다.");
            text.AppendLine(Observation.ToDisplayText());
            text.AppendLine("OEM 메서드·삼성 DLL·드라이버/서비스 변경·펌웨어 쓰기는 실행하지 않습니다.");
            return text.ToString();
        }

        public static string ElevationText(ProcessElevationState elevation)
        {
            switch (elevation)
            {
                case ProcessElevationState.NotElevated: return "상승되지 않음 (NotElevated)";
                case ProcessElevationState.Elevated: return "상승됨 (Elevated)";
                default: return "확인 불가 (Unknown)";
            }
        }

        public static string StageText(SamsungWmiAccessStage stage)
        {
            switch (stage)
            {
                case SamsungWmiAccessStage.Connect: return "연결 (Connect)";
                case SamsungWmiAccessStage.Query: return "쿼리 요청 (Query)";
                case SamsungWmiAccessStage.Enumerate: return "인스턴스 열거 (Enumerate)";
                case SamsungWmiAccessStage.ReadProperties: return "속성 읽기 (ReadProperties)";
                case SamsungWmiAccessStage.Completed: return "속성 조회 완료 (Completed)";
                default: return "미시작 또는 확인 불가 (NotStarted)";
            }
        }

        public static string CodeText(SamsungWmiAccessCode code)
        {
            switch (code)
            {
                case SamsungWmiAccessCode.None: return "None — 오류 코드 없음 또는 확인하지 않음";
                case SamsungWmiAccessCode.WmiAccessDenied: return "WBEM_E_ACCESS_DENIED (0x80041003)";
                case SamsungWmiAccessCode.WindowsAccessDenied: return "E_ACCESSDENIED (0x80070005)";
                case SamsungWmiAccessCode.WmiClassNotFound: return "WBEM_E_INVALID_CLASS (0x80041010)";
                case SamsungWmiAccessCode.WmiNamespaceNotFound: return "WBEM_E_INVALID_NAMESPACE (0x8004100E)";
                case SamsungWmiAccessCode.WmiNotFound: return "WBEM_E_NOT_FOUND (0x80041002)";
                case SamsungWmiAccessCode.WmiTimedOut: return "WBEM_E_TIMED_OUT (0x80043001)";
                case SamsungWmiAccessCode.WindowsTimedOut: return "ERROR_TIMEOUT HRESULT (0x800705B4)";
                default: return "Other — 분류되지 않은 오류 (원문 제외)";
            }
        }

        private static SamsungWmiAccessTrace FixedTrace(SamsungWmiAccessTrace trace, SamsungWmiClass expected)
        {
            if (trace == null) return new SamsungWmiAccessTrace(expected, SamsungWmiAccessStage.NotStarted, SamsungWmiAccessCode.None);
            return trace.Kind == expected ? trace : new SamsungWmiAccessTrace(expected, SamsungWmiAccessStage.NotStarted, SamsungWmiAccessCode.Other);
        }

        private static void AppendTrace(StringBuilder text, SamsungWmiClassObservation observation, SamsungWmiAccessTrace trace)
        {
            text.AppendLine(SamsungWmiInstancePolicy.GetClassName(observation.Kind) + ": " + SamsungWmiInstanceReport.StatusText(observation.Status));
            text.AppendLine("  단계: " + StageText(trace.Stage) + " / 오류 분류: " + CodeText(trace.Code));
        }
    }
}
