using System;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum WsabiWmiOneShotStatus
    {
        NotElevated, ElevationUnknown, PreflightFailed, DeviceMismatch, MetadataMismatch,
        TargetMismatch, ReservationAlreadyUsed, ReservationUnavailable, AlreadyRun,
        ResponseReceived, TransportFailure
    }

    public enum WsabiWmiCandidateMarker { NotObserved, Zero, One, FF, Other }

    // Reports contain fixed classifications only. A marker remains an opaque
    // candidate byte, never actual protection mode or a supported charge limit.
    public sealed class WsabiWmiOneShotReport
    {
        public WsabiWmiOneShotStatus Status { get; }
        public ProcessElevationState Elevation { get; }
        public bool InvocationRequested { get; }
        public WsabiWmiMetadataStatus PreflightStatus { get; }
        public WsabiWmiReplyStatus? ReplyStatus { get; }
        public WsabiWmiMethodReplyStatus? MethodReplyStatus { get; }
        public WsabiWmiCandidateMarker Marker { get; }
        public bool IsHardwareObservation => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        internal WsabiWmiOneShotReport(WsabiWmiOneShotStatus status, ProcessElevationState elevation,
            WsabiWmiMetadataStatus preflightStatus, bool invocationRequested = false,
            WsabiWmiReplyResult reply = null)
        {
            Status = Enum.IsDefined(typeof(WsabiWmiOneShotStatus), status) ? status : WsabiWmiOneShotStatus.PreflightFailed;
            Elevation = Enum.IsDefined(typeof(ProcessElevationState), elevation) ? elevation : ProcessElevationState.Unknown;
            PreflightStatus = Enum.IsDefined(typeof(WsabiWmiMetadataStatus), preflightStatus)
                ? preflightStatus : WsabiWmiMetadataStatus.Unavailable;
            InvocationRequested = invocationRequested;
            if (Status != WsabiWmiOneShotStatus.ResponseReceived || !invocationRequested || reply == null) return;
            ReplyStatus = reply.Status;
            MethodReplyStatus = reply.MethodReplyStatus;
            if (!reply.IsValidFrame) return;
            byte[] payload = reply.Payload;
            switch (payload[0])
            {
                case 0: Marker = WsabiWmiCandidateMarker.Zero; break;
                case 1: Marker = WsabiWmiCandidateMarker.One; break;
                case 0xff: Marker = WsabiWmiCandidateMarker.FF; break;
                default: Marker = WsabiWmiCandidateMarker.Other; break;
            }
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("ATIV Battery Guard — 승인된 한정 WMI 조회 후보 실험");
            text.AppendLine("범위: 고정 후보 0x65, 최대 1회. 자동 재시도 없음.");
            text.AppendLine("현재 토큰: " + Elevation);
            text.AppendLine("결과: " + StatusText(Status) + " (" + Status + ")");
            text.AppendLine("사전 검증: " + WsabiWmiContractMetadataReport.StatusText(PreflightStatus));
            text.AppendLine("OEM 호출 요청: " + (InvocationRequested ? "요청됨" : "없음"));
            text.AppendLine("호출 요청 여부는 실제 실행·완료를 보장하지 않습니다.");
            text.AppendLine("메서드 응답 판정: " + (MethodReplyStatus.HasValue ? MethodReplyStatus.Value.ToString() : "미관측"));
            text.AppendLine("프레임 판정: " + (ReplyStatus.HasValue ? ReplyStatus.Value.ToString() : "미관측"));
            text.AppendLine("후보 표식: " + MarkerText(Marker));
            text.AppendLine("표식 0/1/FF는 후보 응답의 분류이며 실제 보호 OFF/ON/미지원 판정이 아닙니다.");
            text.AppendLine("실제 보호 설정·80%/100% 상한을 확인한 결과가 아닙니다. 실제 충전 제어: 미지원.");
            text.AppendLine("1회 예약 표식을 삭제하지 말고, 호출 요청 뒤에는 결과와 관계없이 재실행하지 마세요.");
            text.AppendLine("설정 명령·삼성 DLL·드라이버/서비스/ACL 변경은 포함하지 않습니다.");
            text.AppendLine("사용자 이름·SID·인스턴스 이름·경로·원문 오류·전체 응답 바이트는 출력하지 않습니다.");
            return text.ToString();
        }

        public static string StatusText(WsabiWmiOneShotStatus status)
        {
            switch (status)
            {
                case WsabiWmiOneShotStatus.NotElevated: return "수동 관리자 실행 조건 미충족·무호출";
                case WsabiWmiOneShotStatus.ElevationUnknown: return "현재 토큰 확인 불가·무호출";
                case WsabiWmiOneShotStatus.PreflightFailed: return "사전 검증 실패·무호출";
                case WsabiWmiOneShotStatus.DeviceMismatch: return "대상 모델/BIOS 조건 불일치 또는 확인 불가·무호출";
                case WsabiWmiOneShotStatus.MetadataMismatch: return "고정 메서드/입출력 규약 조건 미충족·무호출";
                case WsabiWmiOneShotStatus.TargetMismatch: return "단일 활성 인스턴스/입력 준비 조건 미충족·무호출";
                case WsabiWmiOneShotStatus.ReservationAlreadyUsed: return "1회 예약 표식이 이미 있음·무호출";
                case WsabiWmiOneShotStatus.ReservationUnavailable: return "1회 예약을 안전하게 확보하지 못함·무호출";
                case WsabiWmiOneShotStatus.AlreadyRun: return "이 실험 객체가 이미 사용됨·추가 호출 없음";
                case WsabiWmiOneShotStatus.ResponseReceived: return "후보 요청의 응답 판정 수신";
                case WsabiWmiOneShotStatus.TransportFailure: return "호출 요청 후 결과 확인 불가·재시도 금지";
                default: return "결과 확인 불가";
            }
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
