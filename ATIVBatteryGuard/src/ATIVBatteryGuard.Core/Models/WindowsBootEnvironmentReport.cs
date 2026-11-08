using System;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum WindowsBootQueryStatus
    {
        NotCollected, Complete, AccessDenied, ApiUnavailable, Unavailable,
        TimedOut, UnsupportedPlatform, InvalidResponse
    }

    public enum WindowsBootFirmwareType
    {
        Unknown = 0, Bios = 1, Uefi = 2
    }

    // Current Windows boot metadata only; never a firmware or control capability.
    public sealed class WindowsBootEnvironmentReport
    {
        public WindowsBootQueryStatus Status { get; }
        public WindowsBootFirmwareType FirmwareType { get; }
        public bool HardwareWriteAllowed => false;

        public WindowsBootEnvironmentReport(WindowsBootQueryStatus status = WindowsBootQueryStatus.NotCollected,
            WindowsBootFirmwareType firmwareType = WindowsBootFirmwareType.Unknown)
        {
            Status = Enum.IsDefined(typeof(WindowsBootQueryStatus), status)
                ? status : WindowsBootQueryStatus.InvalidResponse;
            if (Status == WindowsBootQueryStatus.Complete &&
                !Enum.IsDefined(typeof(WindowsBootFirmwareType), firmwareType))
                Status = WindowsBootQueryStatus.InvalidResponse;
            FirmwareType = Status == WindowsBootQueryStatus.Complete
                ? firmwareType : WindowsBootFirmwareType.Unknown;
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("현재 Windows 부팅 방식 — 표준 API 읽기 전용 정보");
            text.AppendLine("조회 상태: " + StatusText(Status) + " (" + Status + ").");
            if (Status == WindowsBootQueryStatus.Complete && FirmwareType == WindowsBootFirmwareType.Bios)
            {
                text.AppendLine("관측: BIOS. 현재 Windows는 legacy BIOS 방식으로 부팅했습니다. UEFI 지원 하드웨어의 legacy 부팅도 포함합니다.");
                text.AppendLine("이 부팅에서는 표준 Windows EFI 변수 API 경로를 적용 대상에서 제외할 수 있습니다. 다른 펌웨어 호출자·SMM 경로·드라이버가 없다는 뜻은 아닙니다.");
            }
            else if (Status == WindowsBootQueryStatus.Complete && FirmwareType == WindowsBootFirmwareType.Uefi)
            {
                text.AppendLine("관측: UEFI. 현재 Windows는 UEFI 방식으로 부팅했습니다.");
                text.AppendLine("표준 EFI 변수 API 경로의 적용 범위 정보일 뿐, 실제 proxy·cache·처리기 선택·보호 순서나 배터리 보호 기능의 지원·설정 상태를 입증하지 않습니다.");
            }
            else
            {
                text.AppendLine("관측: Unknown. 현재 Windows 부팅 방식은 판정 보류입니다. 미관측·조회 실패를 BIOS 또는 UEFI로 바꾸지 않습니다.");
            }
            text.AppendLine("이 결과는 현재 Windows 부팅만 분류하며 충전 제한 지원·보호 설정·보안 설정을 판정하지 않습니다. 실제 충전 제어: 미지원. 하드웨어 쓰기 허용: false.");
            return text.ToString();
        }

        public static string StatusText(WindowsBootQueryStatus status)
        {
            switch (status)
            {
                case WindowsBootQueryStatus.Complete: return "정상 조회 완료";
                case WindowsBootQueryStatus.AccessDenied: return "조회 권한 없음";
                case WindowsBootQueryStatus.ApiUnavailable: return "표준 조회 API를 사용할 수 없음";
                case WindowsBootQueryStatus.Unavailable: return "조회 오류로 확인할 수 없음";
                case WindowsBootQueryStatus.TimedOut: return "조회 시간 초과";
                case WindowsBootQueryStatus.UnsupportedPlatform: return "Windows에서만 조회 가능";
                case WindowsBootQueryStatus.InvalidResponse: return "응답 형식 확인 실패";
                default: return "아직 조회하지 않음";
            }
        }
    }
}
