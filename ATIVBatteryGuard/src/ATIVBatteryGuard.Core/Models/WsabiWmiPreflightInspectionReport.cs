using System;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum WsabiWmiPreflightIssue
    {
        None, NotElevated, PlatformUnsupported, DeviceMismatch, SchemaMismatch,
        RowCountMismatch, InactiveOrInvalidTarget, InputShapeMismatch,
        InputCimTypeMissing, InputCimTypeInvalid, InputCimTypeMismatch,
        BufferUnavailable, FieldUnavailable, FieldTypeMismatch, InvalidValue,
        AccessDenied, TimedOut, ClassNotFound, NamespaceNotFound, NotFound,
        InvalidParameter, NotSupported, ProviderFailure, ProviderNotCapable,
        FrameworkNotSupported, OtherError,
        // Keep the earlier values stable for historical reports. Detailed
        // locator failures must not be interpreted as an inactive target.
        RowObjectUnavailable, PathMissing, PathNotInstance, PathClassMismatch,
        RelativePathMissing, RelativePathTooLong, TargetInactive
    }

    // Only fixed classifications cross this boundary. No provider message,
    // native error value, target identity or reservation state is retained.
    public sealed class WsabiWmiPreflightInspectionReport
    {
        public const string ConsoleTitle = "사전검증 전용 · OEM 호출 없음";
        public const string InspectionVersion = "Locator-v2";

        public ProcessElevationState Elevation { get; }
        public WsabiWmiMetadataStatus Status { get; }
        public WsabiWmiOneShotPreflightStage Stage { get; }
        public WsabiWmiPreflightIssue Issue { get; }
        public bool PreparationReady => Elevation == ProcessElevationState.Elevated
            && Status == WsabiWmiMetadataStatus.Complete
            && Stage == WsabiWmiOneShotPreflightStage.Ready
            && Issue == WsabiWmiPreflightIssue.None;
        public bool CanInvokeMethods => false;
        public bool CanWriteHardware => false;
        public bool TouchesReservation => false;

        public WsabiWmiPreflightInspectionReport(ProcessElevationState elevation,
            WsabiWmiMetadataStatus status, WsabiWmiOneShotPreflightStage stage,
            WsabiWmiPreflightIssue issue)
        {
            bool validElevation = Enum.IsDefined(typeof(ProcessElevationState), elevation);
            bool validStatus = Enum.IsDefined(typeof(WsabiWmiMetadataStatus), status);
            bool validStage = Enum.IsDefined(typeof(WsabiWmiOneShotPreflightStage), stage);
            bool validIssue = Enum.IsDefined(typeof(WsabiWmiPreflightIssue), issue);
            Elevation = validElevation ? elevation : ProcessElevationState.Unknown;
            if (!validElevation || !validStatus || !validStage || !validIssue)
            {
                Status = WsabiWmiMetadataStatus.Unavailable;
                Stage = WsabiWmiOneShotPreflightStage.Unknown;
                Issue = WsabiWmiPreflightIssue.OtherError;
                return;
            }
            Status = status;
            Stage = stage;
            Issue = issue;
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("ATIV Battery Guard — " + ConsoleTitle);
            text.AppendLine("점검판: 경로 정보 확보 보완판 (" + InspectionVersion + ")");
            text.AppendLine("현재 토큰: " + ElevationText(Elevation) + " (" + Elevation + ")");
            text.AppendLine("사전 검증: " + StatusText(Status) + " (" + Status + ")");
            text.AppendLine("사전 검증 단계: " + StageText(Stage) + " (" + Stage + ")");
            text.AppendLine("원인 분류: " + IssueText(Issue) + " (" + Issue + ")");
            text.AppendLine("준비 조건: " + (PreparationReady ? "고정 사전 검사 조건 충족" : "미충족 또는 확인 불가"));
            text.AppendLine("단계는 마지막으로 시도한 준비 위치이며 이전 단계의 모든 사실을 보증하지 않습니다.");
            text.AppendLine("OEM 호출: 없음. 1회 예약 표식 접근: 없음.");
            text.AppendLine("준비 완료는 OEM 실행이나 충전 제한 성공을 의미하지 않습니다. 실제 충전 제어: 미지원.");
            text.AppendLine("삼성 DLL 실행·드라이버/서비스/ACL 변경·펌웨어 쓰기는 포함하지 않습니다.");
            text.AppendLine("사용자 이름·SID·인스턴스 이름·경로·원문 오류·원문 오류 코드는 출력하지 않습니다.");
            return text.ToString();
        }

        private static string ElevationText(ProcessElevationState elevation)
        {
            switch (elevation)
            {
                case ProcessElevationState.Elevated: return "관리자 권한 확인";
                case ProcessElevationState.NotElevated: return "일반 권한 확인";
                default: return "권한 확인 불가";
            }
        }

        private static string StatusText(WsabiWmiMetadataStatus status)
        {
            switch (status)
            {
                case WsabiWmiMetadataStatus.NotChecked: return "미실시 또는 미관측";
                case WsabiWmiMetadataStatus.Complete: return "관측 단계 판정 완료";
                case WsabiWmiMetadataStatus.Partial: return "일부 정보만 확인";
                case WsabiWmiMetadataStatus.ClassNotFound: return "대상 클래스 정의를 찾지 못함";
                case WsabiWmiMetadataStatus.NamespaceNotFound: return "대상 네임스페이스를 찾지 못함";
                case WsabiWmiMetadataStatus.AccessDenied: return "사전 검사의 권한 거부";
                case WsabiWmiMetadataStatus.TimedOut: return "사전 검사 시간 초과";
                case WsabiWmiMetadataStatus.UnsupportedPlatform: return "지원되지 않는 실행 환경";
                default: return "사전 검사 결과 확인 불가";
            }
        }

        private static string StageText(WsabiWmiOneShotPreflightStage stage)
        {
            switch (stage)
            {
                case WsabiWmiOneShotPreflightStage.DeviceScope: return "로컬 장치 정보 연결";
                case WsabiWmiOneShotPreflightStage.ModelRead: return "모델 정보 읽기";
                case WsabiWmiOneShotPreflightStage.BiosRead: return "BIOS 정보 읽기";
                case WsabiWmiOneShotPreflightStage.ContractMetadata: return "고정 클래스·메서드 정의 확인";
                case WsabiWmiOneShotPreflightStage.MethodScope: return "로컬 메서드 정보 연결";
                case WsabiWmiOneShotPreflightStage.MethodEnumeration: return "메서드 인스턴스 확인";
                case WsabiWmiOneShotPreflightStage.TargetRead: return "관측한 단일 대상 읽기";
                case WsabiWmiOneShotPreflightStage.InputParameters: return "메모리 입력 매개변수 준비";
                case WsabiWmiOneShotPreflightStage.BufferInstance: return "메모리 DataBuffer 준비";
                case WsabiWmiOneShotPreflightStage.Ready: return "고정 입력 준비 완료 위치";
                default: return "미관측";
            }
        }

        private static string IssueText(WsabiWmiPreflightIssue issue)
        {
            switch (issue)
            {
                case WsabiWmiPreflightIssue.None: return "고정 사전 검사에서 문제 분류 없음";
                case WsabiWmiPreflightIssue.NotElevated: return "수동 관리자 실행 조건 미충족";
                case WsabiWmiPreflightIssue.PlatformUnsupported: return "실행 플랫폼 조건 미충족";
                case WsabiWmiPreflightIssue.DeviceMismatch: return "모델 또는 BIOS 조건 불일치";
                case WsabiWmiPreflightIssue.SchemaMismatch: return "고정 클래스·메서드 규약 불일치";
                case WsabiWmiPreflightIssue.RowCountMismatch: return "단일 대상 개수 조건 불일치";
                case WsabiWmiPreflightIssue.InactiveOrInvalidTarget: return "대상 활성 상태 또는 식별 구조 조건 미충족";
                case WsabiWmiPreflightIssue.InputShapeMismatch: return "입력 매개변수 구조 불일치";
                case WsabiWmiPreflightIssue.InputCimTypeMissing: return "입력 CIM 형식 한정자 미관측";
                case WsabiWmiPreflightIssue.InputCimTypeInvalid: return "입력 CIM 형식 한정자 값이 유효하지 않음";
                case WsabiWmiPreflightIssue.InputCimTypeMismatch: return "입력 CIM 형식 한정자 불일치";
                case WsabiWmiPreflightIssue.BufferUnavailable: return "메모리 입력 버퍼 준비 불가";
                case WsabiWmiPreflightIssue.FieldUnavailable: return "필수 필드 미관측";
                case WsabiWmiPreflightIssue.FieldTypeMismatch: return "필수 필드 형식 불일치";
                case WsabiWmiPreflightIssue.InvalidValue: return "고정 검증 조건에 맞지 않는 값";
                case WsabiWmiPreflightIssue.AccessDenied: return "권한 거부";
                case WsabiWmiPreflightIssue.TimedOut: return "시간 초과";
                case WsabiWmiPreflightIssue.ClassNotFound: return "클래스 정의를 찾지 못함";
                case WsabiWmiPreflightIssue.NamespaceNotFound: return "네임스페이스를 찾지 못함";
                case WsabiWmiPreflightIssue.NotFound: return "요청한 정의 또는 정보를 찾지 못함";
                case WsabiWmiPreflightIssue.InvalidParameter: return "매개변수 오류 분류";
                case WsabiWmiPreflightIssue.NotSupported: return "작업 지원 불가 분류";
                case WsabiWmiPreflightIssue.ProviderFailure: return "공급자 실패 분류";
                case WsabiWmiPreflightIssue.ProviderNotCapable: return "공급자가 작업을 처리할 수 없음";
                case WsabiWmiPreflightIssue.FrameworkNotSupported: return "현재 프레임워크에서 준비 작업 지원 불가";
                case WsabiWmiPreflightIssue.RowObjectUnavailable: return "반환 행을 대상 객체로 확인할 수 없음";
                case WsabiWmiPreflightIssue.PathMissing: return "대상 경로 정보 미관측";
                case WsabiWmiPreflightIssue.PathNotInstance: return "대상 경로가 인스턴스를 가리키지 않음";
                case WsabiWmiPreflightIssue.PathClassMismatch: return "대상 경로의 클래스 불일치";
                case WsabiWmiPreflightIssue.RelativePathMissing: return "대상 상대 경로 정보 미관측";
                case WsabiWmiPreflightIssue.RelativePathTooLong: return "대상 상대 경로 길이 제한 초과";
                case WsabiWmiPreflightIssue.TargetInactive: return "대상 Active 속성이 false";
                default: return "기타 오류 또는 원인 확인 불가";
            }
        }
    }
}
