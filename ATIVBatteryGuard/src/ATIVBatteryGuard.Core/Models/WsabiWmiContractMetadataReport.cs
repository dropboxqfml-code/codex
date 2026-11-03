using System;
using System.Globalization;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum WsabiWmiMetadataStatus
    {
        NotChecked, Complete, Partial, ClassNotFound, NamespaceNotFound,
        AccessDenied, TimedOut, UnsupportedPlatform, Unavailable
    }

    public enum WsabiWmiGuidMatch { Missing, MatchesPublicCandidate, Other, Invalid }

    public sealed class WsabiWmiContractMethodMetadata
    {
        public WsabiWmiMetadataStatus Status { get; }
        public WsabiWmiGuidMatch GuidMatch { get; }
        public uint? MethodId { get; }
        public bool? InputIsDataBuffer { get; }
        public bool? OutputIsDataBuffer { get; }
        public bool? MethodFound { get; }

        public WsabiWmiContractMethodMetadata(WsabiWmiMetadataStatus status = WsabiWmiMetadataStatus.NotChecked,
            WsabiWmiGuidMatch guidMatch = WsabiWmiGuidMatch.Missing, uint? methodId = null,
            bool? inputIsDataBuffer = null, bool? outputIsDataBuffer = null, bool? methodFound = null)
        {
            Status = Enum.IsDefined(typeof(WsabiWmiMetadataStatus), status) ? status : WsabiWmiMetadataStatus.Unavailable;
            if (Status != WsabiWmiMetadataStatus.Complete && Status != WsabiWmiMetadataStatus.Partial)
            {
                GuidMatch = WsabiWmiGuidMatch.Missing;
                return;
            }
            GuidMatch = Enum.IsDefined(typeof(WsabiWmiGuidMatch), guidMatch) ? guidMatch : WsabiWmiGuidMatch.Invalid;
            MethodFound = methodFound;
            if (methodFound == true)
            {
                MethodId = methodId;
                InputIsDataBuffer = inputIsDataBuffer;
                OutputIsDataBuffer = outputIsDataBuffer;
            }
            if (Status == WsabiWmiMetadataStatus.Complete &&
                (GuidMatch == WsabiWmiGuidMatch.Missing || GuidMatch == WsabiWmiGuidMatch.Invalid ||
                 MethodFound != true || !MethodId.HasValue || !InputIsDataBuffer.HasValue || !OutputIsDataBuffer.HasValue))
                Status = WsabiWmiMetadataStatus.Partial;
        }
    }

    public sealed class WsabiWmiContractBufferMetadata
    {
        public WsabiWmiMetadataStatus Status { get; }
        public bool? BytesIsUInt8Array { get; }

        public WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus status = WsabiWmiMetadataStatus.NotChecked,
            bool? bytesIsUInt8Array = null)
        {
            Status = Enum.IsDefined(typeof(WsabiWmiMetadataStatus), status) ? status : WsabiWmiMetadataStatus.Unavailable;
            if (Status == WsabiWmiMetadataStatus.Complete || Status == WsabiWmiMetadataStatus.Partial)
                BytesIsUInt8Array = bytesIsUInt8Array;
            if (Status == WsabiWmiMetadataStatus.Complete && !BytesIsUInt8Array.HasValue)
                Status = WsabiWmiMetadataStatus.Partial;
        }
    }

    // Fixed metadata observations only: actual GUID strings and instance data cannot be stored.
    public sealed class WsabiWmiContractMetadataReport
    {
        public WsabiWmiContractMethodMetadata MethodMetadata { get; }
        public WsabiWmiContractBufferMetadata BufferMetadata { get; }
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        public WsabiWmiContractMetadataReport(WsabiWmiContractMethodMetadata methodMetadata = null,
            WsabiWmiContractBufferMetadata bufferMetadata = null)
        {
            MethodMetadata = methodMetadata ?? new WsabiWmiContractMethodMetadata();
            BufferMetadata = bufferMetadata ?? new WsabiWmiContractBufferMetadata();
        }

        public static WsabiWmiContractMetadataReport Failure(WsabiWmiMetadataStatus status)
        {
            if (status == WsabiWmiMetadataStatus.Complete || status == WsabiWmiMetadataStatus.Partial)
                status = WsabiWmiMetadataStatus.Unavailable;
            return new WsabiWmiContractMetadataReport(new WsabiWmiContractMethodMetadata(status),
                new WsabiWmiContractBufferMetadata(status));
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("ATIV Battery Guard — 고정 WMI 클래스 전송 규약 메타데이터");
            text.AppendLine(@"범위: 로컬 ROOT\WMI의 WmiAcpiMethod·DataBuffer 클래스 정의만 읽습니다.");
            text.AppendLine("WmiAcpiMethod 정의: " + StatusText(MethodMetadata.Status));
            text.AppendLine("  클래스 GUID와 공개 후보의 일치: " + GuidText(MethodMetadata.GuidMatch));
            text.AppendLine("  CallSabiFunction 정의 존재: " + BoolText(MethodMetadata.MethodFound));
            text.AppendLine("  WmiMethodId: " + (MethodMetadata.MethodId.HasValue
                ? MethodMetadata.MethodId.Value.ToString(CultureInfo.InvariantCulture) + " (0x" +
                  MethodMetadata.MethodId.Value.ToString("X8", CultureInfo.InvariantCulture) + ")"
                : "Unknown"));
            text.AppendLine("  inData가 단일 Object·EmbeddedInstance=DataBuffer: " + BoolText(MethodMetadata.InputIsDataBuffer));
            text.AppendLine("  outData가 단일 Object·EmbeddedInstance=DataBuffer: " + BoolText(MethodMetadata.OutputIsDataBuffer));
            text.AppendLine("DataBuffer 정의: " + StatusText(BufferMetadata.Status));
            text.AppendLine("  Bytes가 UInt8[]: " + BoolText(BufferMetadata.BytesIsUInt8Array));
            text.AppendLine("WmiMethodId는 WMI 메서드의 디스패치 번호이며 배터리 명령 번호가 아닙니다. UInt8[] 정의는 실제 배열 길이나 ACK를 확인한 결과가 아닙니다.");
            text.AppendLine("False는 관측한 정의의 필수 필드나 형식이 기대와 일치하지 않음을 뜻합니다. Unknown은 미관측·qualifier 누락·형식 확인 불가이며 기능 부재로 바꾸지 않습니다.");
            text.AppendLine("실제 클래스 GUID는 출력하지 않습니다. WmiMethodId는 고정 메서드 정의의 번호이며 장치 고유 식별자가 아닙니다.");
            text.AppendLine("정의 일치는 인스턴스 연계·메서드 실행 권한·모델별 명령 안전성·배터리 지원의 증거가 아닙니다.");
            text.AppendLine("인스턴스의 속성 값·DataBuffer 내용·사용자 이름·SID·경로·예외 원문은 읽거나 출력하지 않습니다.");
            text.AppendLine("OEM 메서드·삼성 DLL·장치·서비스·ACL·펌웨어 쓰기를 실행하지 않습니다. 실제 충전 제어: 미지원.");
            return text.ToString();
        }

        public static string StatusText(WsabiWmiMetadataStatus status)
        {
            switch (status)
            {
                case WsabiWmiMetadataStatus.Complete: return "메타데이터 조회 완료";
                case WsabiWmiMetadataStatus.Partial: return "일부 정의 관측·누락 또는 형식 확인 불가";
                case WsabiWmiMetadataStatus.ClassNotFound: return "대상 클래스 정의를 찾지 못함";
                case WsabiWmiMetadataStatus.NamespaceNotFound: return "대상 네임스페이스를 찾지 못함";
                case WsabiWmiMetadataStatus.AccessDenied: return "메타데이터 조회 권한 없음";
                case WsabiWmiMetadataStatus.TimedOut: return "메타데이터 조회 시간 초과";
                case WsabiWmiMetadataStatus.UnsupportedPlatform: return "Windows에서만 조회 가능";
                case WsabiWmiMetadataStatus.Unavailable: return "메타데이터 조회 결과 확인 불가";
                default: return "아직 조회하지 않음";
            }
        }

        public static string GuidText(WsabiWmiGuidMatch value)
        {
            switch (value)
            {
                case WsabiWmiGuidMatch.MatchesPublicCandidate: return "공개 후보와 일치";
                case WsabiWmiGuidMatch.Other: return "공개 후보와 다름 (실제 값 제외)";
                case WsabiWmiGuidMatch.Invalid: return "형식 확인 불가 (실제 값 제외)";
                default: return "미관측 또는 qualifier 없음";
            }
        }

        private static string BoolText(bool? value) => value.HasValue ? (value.Value ? "True" : "False") : "Unknown";
    }
}
