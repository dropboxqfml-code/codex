using System;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum WsabiWmiFixedReadAccess1ReviewStatus
    {
        NotLoaded, InvalidInput, Inconsistent, NoReportedCandidate,
        CompletionPending, ReportedStoredModeCandidate
    }

    // Sanitized classification of submitted historical text only. No raw text,
    // device identity, response bytes, comparison content or execution authority.
    public sealed class WsabiWmiFixedReadAccess1Review
    {
        public static WsabiWmiFixedReadAccess1Review Empty { get; } =
            new WsabiWmiFixedReadAccess1Review(WsabiWmiFixedReadAccess1ReviewStatus.NotLoaded);

        public WsabiWmiFixedReadAccess1ReviewStatus Status { get; }
        public bool HasReportedStoredModeCandidate => Status == WsabiWmiFixedReadAccess1ReviewStatus.ReportedStoredModeCandidate;
        public int? StoredModeCandidate { get; }
        public bool IsHardwareObservation => false;
        public bool IsChargeLimitConfirmed => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;
        public bool CanInvokeMethods => false;

        internal WsabiWmiFixedReadAccess1Review(WsabiWmiFixedReadAccess1ReviewStatus status, int? candidate = null)
        {
            if (!Enum.IsDefined(typeof(WsabiWmiFixedReadAccess1ReviewStatus), status))
                status = WsabiWmiFixedReadAccess1ReviewStatus.InvalidInput;
            if ((status == WsabiWmiFixedReadAccess1ReviewStatus.ReportedStoredModeCandidate) != candidate.HasValue ||
                (candidate.HasValue && candidate.Value != 0 && candidate.Value != 1))
                status = WsabiWmiFixedReadAccess1ReviewStatus.Inconsistent;
            Status = status;
            StoredModeCandidate = HasReportedStoredModeCandidate ? candidate : null;
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("추가 단발 조회 Access1 결과 · 오프라인 검토");
            switch (Status)
            {
                case WsabiWmiFixedReadAccess1ReviewStatus.NotLoaded:
                    text.AppendLine("이미 받은 Access1 결과 TXT의 내용을 붙여넣어 검토할 수 있습니다. 새 시험이나 자료 재제출은 필요하지 않습니다.");
                    break;
                case WsabiWmiFixedReadAccess1ReviewStatus.InvalidInput:
                    text.AppendLine("지원하는 Access1 결과 형식을 확인하지 못했습니다. 후보를 채택하지 않으며 원문은 결과에 보관하지 않습니다.");
                    break;
                case WsabiWmiFixedReadAccess1ReviewStatus.Inconsistent:
                    text.AppendLine("필수 상태들이 서로 맞지 않아 저장 후보를 채택하지 않았습니다.");
                    break;
                case WsabiWmiFixedReadAccess1ReviewStatus.CompletionPending:
                    text.AppendLine("관련 종료·정리 Pending이 기록돼 있어 저장 후보를 채택하지 않았습니다. 표시 결과만으로 실제 종료를 추론하지 않습니다.");
                    break;
                case WsabiWmiFixedReadAccess1ReviewStatus.ReportedStoredModeCandidate:
                    text.AppendLine("제출된 로그의 형식·상태 조합과 도구 판정 기록을 확인했습니다.");
                    text.AppendLine("로그에 보고된 저장 모드 후보: " + StoredModeCandidate.Value.ToString(System.Globalization.CultureInfo.InvariantCulture));
                    text.AppendLine("관련 정리 Complete가 기록돼 있습니다. 원문 frame·비교 내용이 없어 응답 바이트나 귀속 비교를 다시 검증한 결과는 아닙니다.");
                    break;
                default:
                    text.AppendLine("제출된 로그에서 채택할 수 있는 완료된 저장 후보를 확인하지 못했습니다.");
                    break;
            }
            text.AppendLine("사용자가 제출한 과거 텍스트이며 진위·현재 장치·같은 계정·실행 시각을 인증하지 않습니다.");
            text.AppendLine("후보 0/1은 현재 임계값·80% 충전 제한 적용·충전기 상태를 입증하지 않습니다.");
            text.AppendLine("배터리 보호 상태: 알 수 없음. 실제 충전 제어: 미지원.");
            text.AppendLine("이 검토는 WMI·장치·예약 파일에 접근하지 않으며 추가 실행이나 예약 변경을 허용하지 않습니다.");
            return text.ToString();
        }
    }
}
