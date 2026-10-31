using System;
using System.Text;
using System.Text.RegularExpressions;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    public static class SupportInquiryFormatter
    {
        public static string Format(DeviceDiagnosticsResult device)
        {
            device = device ?? new DeviceDiagnosticsResult();
            var text = new StringBuilder();
            text.AppendLine("삼성 지원 문의 초안 — 직접 검토 후 전달하세요. 앱은 자동 전송하지 않습니다.");
            Append(text, "제조사", device.Manufacturer);
            Append(text, "모델", device.Model);
            Append(text, "BIOS", device.BiosVersion);
            Append(text, "Windows", device.WindowsName);
            Append(text, "Windows 버전", device.WindowsVersion);
            Append(text, "아키텍처", device.SystemArchitecture);
            text.AppendLine();
            text.AppendLine("1. 이 모델·BIOS·Windows 조합에서 배터리 충전 상한 제한이 공식 지원되나요? 공식 설명서와 지원 프로그램·드라이버 버전을 알려주세요.");
            text.AppendLine("2. 같은 모델에서 Windows 8에 제공되던 기능이 Windows 10 또는 Samsung Settings 2.2 이후 변경됐다는 보고가 적용되나요? 공식 지원 정책이나 변경 기록이 있나요?");
            text.AppendLine("3. 제3자 앱에 공개된 상태 조회·제어 API/SDK가 있나요? 지원한다면 앱 종료·재부팅 이후 설정 유지 방식도 알려주세요.");
            text.AppendLine("4. 설치된 Settings 버전에 적용되는 사용권 계약 원문과 파일 복제·제3자 전달·정적 분석·인터페이스 사용의 허용 범위는 어디에서 확인할 수 있나요?");
            text.AppendLine();
            text.AppendLine("현재 ATIV Battery Guard의 실제 충전 제어는 미지원입니다. 삼성 실행 파일·DLL은 이 문의문에 포함하지 않습니다.");
            return text.ToString();
        }

        private static void Append(StringBuilder text, string label, string value)
        {
            string safe = string.IsNullOrWhiteSpace(value) ? "알 수 없음" : value;
            if (Regex.IsMatch(safe, @"[A-Za-z]:[\\/]") || safe.Contains(@"\\") ||
                safe.IndexOf("/home/", StringComparison.OrdinalIgnoreCase) >= 0 ||
                safe.IndexOf("/Users/", StringComparison.OrdinalIgnoreCase) >= 0)
                safe = "경로가 포함된 정보는 생략했습니다.";
            text.AppendLine(label + ": " + safe);
        }
    }
}
