using System;
using System.Globalization;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum WsabiWmiProtection0To1ReviewStatus
    {
        NotLoaded, InvalidInput, Inconsistent, IncompleteOrFailed, ReportedStoredTransitionMatched
    }

    // A sanitized historical text classification, never a current device
    // reading, setting authority, response authentication or charge proof.
    public sealed class WsabiWmiProtection0To1Review
    {
        public static WsabiWmiProtection0To1Review Empty { get; } =
            new WsabiWmiProtection0To1Review(WsabiWmiProtection0To1ReviewStatus.NotLoaded);
        public WsabiWmiProtection0To1ReviewStatus Status { get; }
        public bool HasReportedStoredTransition => Status == WsabiWmiProtection0To1ReviewStatus.ReportedStoredTransitionMatched;
        public int? PreMode { get; }
        public int? PreUpper { get; }
        public int? PreLower { get; }
        public int? PostMode { get; }
        public int? PostUpper { get; }
        public int? PostLower { get; }
        public int? SdkEntries { get; }
        public int? SetterEntries { get; }
        public int? ReadCandidateCount { get; }
        public bool IsHardwareObservation => false;
        public bool IsChargeLimitConfirmed => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;
        public bool CanInvokeMethods => false;

        internal WsabiWmiProtection0To1Review(WsabiWmiProtection0To1ReviewStatus status,
            int? preMode = null, int? preUpper = null, int? preLower = null,
            int? postMode = null, int? postUpper = null, int? postLower = null)
        {
            if (!Enum.IsDefined(typeof(WsabiWmiProtection0To1ReviewStatus), status))
                status = WsabiWmiProtection0To1ReviewStatus.InvalidInput;
            if (status == WsabiWmiProtection0To1ReviewStatus.ReportedStoredTransitionMatched &&
                (preMode != 0 || !Byte(preUpper) || !Byte(preLower) || postMode != 1 || postUpper != 80 || postLower != 75))
                status = WsabiWmiProtection0To1ReviewStatus.Inconsistent;
            Status = status;
            if (HasReportedStoredTransition)
            {
                PreMode = preMode; PreUpper = preUpper; PreLower = preLower;
                PostMode = postMode; PostUpper = postUpper; PostLower = postLower;
                SdkEntries = 7; SetterEntries = 1; ReadCandidateCount = 6;
            }
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("보호 설정0→1 시험 기록 · 오프라인 검토");
            switch (Status)
            {
                case WsabiWmiProtection0To1ReviewStatus.NotLoaded:
                    text.AppendLine("이미 받은 Protection0To1-v1 결과 TXT의 내용을 붙여넣어 검토할 수 있습니다. 새 설정 시험이나 자료 재제출은 필요하지 않습니다.");
                    break;
                case WsabiWmiProtection0To1ReviewStatus.ReportedStoredTransitionMatched:
                    text.AppendLine("로그의 형식·상태 조합에서 보고된 저장 후보 전환 일치를 확인했습니다.");
                    text.AppendLine("사전 모드/상한/하한 후보: " + Number(PreMode) + " / " + Number(PreUpper) + " / " + Number(PreLower));
                    text.AppendLine("사후 모드/상한/하한 후보: 1 / 80 / 75");
                    text.AppendLine("SDK 진입7회·설정 진입1회·읽기 후보6개와 관련 정리 Complete가 기록돼 있습니다.");
                    text.AppendLine("로그의 ‘설정 효과: Unknown’ 문구는 저장 후보 비교 일치를 취소하지 않습니다. 입력echo만으로 설정 성공을 보증하지 않는 문구이며 충전기 적용·전기적 충전 제한은 여전히 미검증입니다.");
                    break;
                case WsabiWmiProtection0To1ReviewStatus.Inconsistent:
                    text.AppendLine("상태·횟수·단계별 응답·후보 값의 필수 조합이 서로 맞지 않아 저장 전환 후보를 채택하지 않았습니다.");
                    break;
                case WsabiWmiProtection0To1ReviewStatus.IncompleteOrFailed:
                    text.AppendLine("완료된 저장 후보 일치 기록을 확인하지 못했습니다. 중단·실패·Pending을 설정 성공이나 미변경으로 해석하지 않습니다.");
                    break;
                default:
                    text.AppendLine("지원하는 Protection0To1-v1 완료 결과 형식을 확인하지 못했습니다. 후보를 채택하거나 원문을 결과에 보관하지 않습니다.");
                    break;
            }
            text.AppendLine("과거 텍스트의 도구 보고이며 현재 actualMode·같은 장치·계정·실행 시각을 인증하지 않습니다. 원문 frame·비교 내용의 독립 재검증도 아닙니다.");
            text.AppendLine("실제 충전 제어: 미지원. 저장 후보와 현재 배터리 잔량·충전기 적용·전기적 효과는 구분합니다.");
            text.AppendLine("이 검토는 WMI·장치·예약 파일에 접근하지 않습니다. 사용한 시험을 재실행하거나 예약을 변경하지 않습니다.");
            return text.ToString();
        }

        private static bool Byte(int? value) => value.HasValue && value.Value >= 0 && value.Value <= 255;
        private static string Number(int? value) => value.Value.ToString(CultureInfo.InvariantCulture);
    }
}
