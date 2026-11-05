using System;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum WsabiWmiExperimentReviewStatus
    {
        NotLoaded, InvalidInput, Inconsistent, NoValidatedResponse, ValidatedFrameMeaningUnknown
    }

    // An offline classification of user-supplied historical text, never a live
    // observation or an authorization to repeat the one-shot experiment.
    public sealed class WsabiWmiExperimentReview
    {
        public static WsabiWmiExperimentReview Empty { get; } =
            new WsabiWmiExperimentReview(WsabiWmiExperimentReviewStatus.NotLoaded);

        public WsabiWmiExperimentReviewStatus Status { get; }
        public bool HasValidatedFrame => Status == WsabiWmiExperimentReviewStatus.ValidatedFrameMeaningUnknown;
        public WsabiWmiCandidateMarker Marker { get; }
        public bool? InvocationRequested { get; }
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;
        public bool CanInvokeMethods => false;

        internal WsabiWmiExperimentReview(WsabiWmiExperimentReviewStatus status,
            bool? invocationRequested = null, WsabiWmiCandidateMarker marker = WsabiWmiCandidateMarker.NotObserved)
        {
            if (!Enum.IsDefined(typeof(WsabiWmiExperimentReviewStatus), status))
                status = WsabiWmiExperimentReviewStatus.InvalidInput;
            if (status == WsabiWmiExperimentReviewStatus.ValidatedFrameMeaningUnknown &&
                (invocationRequested != true || marker == WsabiWmiCandidateMarker.NotObserved ||
                 !Enum.IsDefined(typeof(WsabiWmiCandidateMarker), marker)))
                status = WsabiWmiExperimentReviewStatus.Inconsistent;
            Status = status;
            if (status == WsabiWmiExperimentReviewStatus.ValidatedFrameMeaningUnknown)
            {
                InvocationRequested = true;
                Marker = marker;
            }
            else if (status == WsabiWmiExperimentReviewStatus.NoValidatedResponse)
                InvocationRequested = invocationRequested;
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("과거 WMI 실험 결과 · 오프라인 검토");
            switch (Status)
            {
                case WsabiWmiExperimentReviewStatus.NotLoaded:
                    text.AppendLine("이미 받은 실험 결과를 붙여넣고 검토할 수 있습니다.");
                    break;
                case WsabiWmiExperimentReviewStatus.InvalidInput:
                    text.AppendLine("지원하는 실험 결과 형식으로 확인하지 못했습니다. 원문은 결과에 보관하지 않습니다.");
                    break;
                case WsabiWmiExperimentReviewStatus.Inconsistent:
                    text.AppendLine("보고된 상태가 서로 맞지 않아 응답과 후보 표식을 채택하지 않았습니다.");
                    break;
                case WsabiWmiExperimentReviewStatus.NoValidatedResponse:
                    text.AppendLine("붙여넣은 결과에서 검증된 응답을 확인하지 못했습니다.");
                    break;
                case WsabiWmiExperimentReviewStatus.ValidatedFrameMeaningUnknown:
                    text.AppendLine("붙여넣은 결과에는 WMI 응답·프레임 검증 성공이 기록돼 있습니다.");
                    text.AppendLine("후보 표식: " + MarkerText(Marker) + " · 의미 미확정");
                    text.AppendLine("FF와 0/1은 보호 OFF/ON 또는 기능 미지원 판정이 아닙니다.");
                    if (Marker == WsabiWmiCandidateMarker.FF)
                    {
                        text.AppendLine("분석한 P05ACJ 이미지에는 ACK AA와 FF로 시작하는 공통 실패 응답 경로가 있습니다.");
                        text.AppendLine("명령 등록 부재·처리 오류 등 여러 조건이 같은 응답을 만들 수 있습니다.");
                        text.AppendLine("이 기록은 첫 바이트만 남겨 전체 실패 패턴·현재 펌웨어 일치·실패 원인을 확정할 수 없습니다.");
                    }
                    break;
            }
            if (InvocationRequested.HasValue)
                text.AppendLine("텍스트에 기록된 호출 요청: " + (InvocationRequested.Value ? "요청됨" : "없음"));
            text.AppendLine("사용자가 붙여넣은 과거 텍스트이며 진위·현재 장치 일치를 검증하지 않습니다.");
            text.AppendLine("배터리 보호 상태: 알 수 없음. 실제 충전 제어: 미지원.");
            text.AppendLine("이 검토는 장치·예약 파일에 접근하지 않으며 추가 실행을 허용하지 않습니다.");
            text.AppendLine("1회 실험을 다시 실행하거나 예약 표식을 삭제하지 마세요.");
            return text.ToString();
        }

        private static string MarkerText(WsabiWmiCandidateMarker marker)
        {
            switch (marker)
            {
                case WsabiWmiCandidateMarker.Zero: return "0";
                case WsabiWmiCandidateMarker.One: return "1";
                case WsabiWmiCandidateMarker.FF: return "FF";
                case WsabiWmiCandidateMarker.Other: return "Other (원문 제외)";
                default: return "미관측";
            }
        }
    }
}
