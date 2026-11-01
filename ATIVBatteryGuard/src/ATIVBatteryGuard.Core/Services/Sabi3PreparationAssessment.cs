using System;
using System.Collections.Generic;
using System.Text;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Metadata preparation only: this is never a hardware capability adapter.
    public sealed class Sabi3PreparationAssessment
    {
        private bool hasAnalyzedNativeX64Candidate;
        private SabiDriverLinkStatus driverLink;
        public int NativeX64Candidates { get; private set; }
        public int NativeX86Candidates { get; private set; }
        public int X64CandidatesWithExpectedNames { get; private set; }
        public bool SearchIncomplete { get; private set; }
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        public static Sabi3PreparationAssessment Evaluate(SamsungFileInspectionReport report)
        {
            var result = new Sabi3PreparationAssessment();
            result.SearchIncomplete = report == null || report.Limited || report.Status != SamsungFileInspectionStatus.Complete;
            if (report == null) return result;
            result.driverLink = report.DriverLink;
            var hashes = new HashSet<string>(StringComparer.Ordinal);
            foreach (var file in report.Entries)
            {
                if (file.FileName != "Sabi3.dll" || file.Status != SamsungFileEntryStatus.Inspected || file.Pe.IsManaged || !hashes.Add(file.Sha256)) continue;
                if (file.Pe.Architecture == "x86") result.NativeX86Candidates++;
                if (file.Pe.Architecture != "x64") continue;
                result.NativeX64Candidates++;
                if (file.Sha256 == Sabi3X64Abi.AnalyzedSha256) result.hasAnalyzedNativeX64Candidate = true;
                var exports = new HashSet<string>(file.Pe.ExportedNames, StringComparer.Ordinal);
                if (exports.Contains("InitBIOSInterface") && exports.Contains("UninitBIOSInterface") &&
                    exports.Contains("CheckSamsung") && exports.Contains("CallBIOSInterface")) result.X64CandidatesWithExpectedNames++;
            }
            return result;
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("[Sabi3 연동 준비 판정 · 메타데이터 기준]");
            text.AppendLine("서로 다른 SHA-256 기준 네이티브 후보: x64 " + NativeX64Candidates + "개 / x86 " + NativeX86Candidates + "개");
            text.AppendLine("x64 후보 중 공개 예제의 기본 함수 이름 4개가 모두 표시된 후보: " + X64CandidatesWithExpectedNames + "개");
            if (NativeX64Candidates > 0) text.AppendLine("현재 x64 앱과 같은 구조의 후보가 있습니다. Settings EXE가 x86이라는 이유만으로 x86 보조 앱이 필요한 것은 아닙니다.");
            if (NativeX64Candidates > 1) text.AppendLine("서로 다른 x64 후보가 여러 개입니다. 첫 번째 파일이나 버전 문자열만으로 호출 대상을 선택하지 않습니다.");
            if (hasAnalyzedNativeX64Candidate) AppendAnalyzedDevicePrecondition(text);
            if (SearchIncomplete) text.AppendLine("조회 범위에 누락·제한이 있습니다. 관측한 후보의 존재만 확인하며 전체 부재나 유일성을 확정하지 않습니다.");
            text.AppendLine("함수 이름은 매개변수·반환 형식·초기화 부작용·드라이버·런타임 의존성의 검증이 아닙니다.");
            text.AppendLine("DLL 로드·초기화·OEM 조회는 수행하지 않습니다. 실제 설정 읽기: 미검증 / 실제 충전 제어: 미지원.");
            return text.ToString();
        }

        private void AppendAnalyzedDevicePrecondition(StringBuilder text)
        {
            text.AppendLine("정적 분석된 x64 DLL의 초기화에는 SABI 장치 연결 경로가 필요합니다.");
            switch (driverLink)
            {
                case SabiDriverLinkStatus.NotFound:
                    text.AppendLine("현재 이름 조회에서는 필요한 SABI 경로를 확인하지 못했습니다. DLL 파일·함수 이름이 있어도 초기화 가능으로 판정하지 않습니다. 드라이버 미설치나 펌웨어 기능 부재를 확정하지 않습니다.");
                    break;
                case SabiDriverLinkStatus.Present:
                    text.AppendLine("필요한 SABI 연결 이름은 관측했지만 장치 접근·초기화·배터리 기능 지원은 미검증입니다.");
                    break;
                case SabiDriverLinkStatus.AccessDenied:
                    text.AppendLine("이름 조회 권한이 없어 SABI 경로의 존재를 판정할 수 없습니다.");
                    break;
                case SabiDriverLinkStatus.Unavailable:
                    text.AppendLine("이름 조회 결과를 확인하지 못해 SABI 경로의 존재를 판정할 수 없습니다.");
                    break;
                case SabiDriverLinkStatus.UnsupportedPlatform:
                    text.AppendLine("이 플랫폼에서는 Windows SABI 이름 조회를 지원하지 않아 경로의 존재를 판정할 수 없습니다.");
                    break;
                default:
                    text.AppendLine("SABI 이름 조회를 수행하지 않아 경로의 존재를 판정할 수 없습니다.");
                    break;
            }
        }

        public static string DescribeObservedImports(PeModuleInfo pe)
        {
            var hits = new List<string>();
            foreach (var function in pe.ImportedFunctions)
            {
                string name = function.FunctionName;
                if (name == "DeviceIoControl" || name == "ReadFile" || name == "WriteFile" || name == "GetProcAddress" ||
                    name.StartsWith("CreateFile", StringComparison.Ordinal) || name.StartsWith("LoadLibrary", StringComparison.Ordinal) ||
                    name.StartsWith("OpenSCManager", StringComparison.Ordinal) || name.StartsWith("CreateService", StringComparison.Ordinal) ||
                    name.StartsWith("StartService", StringComparison.Ordinal) || name.StartsWith("RegSetValue", StringComparison.Ordinal))
                    hits.Add(function.DisplayName);
            }
            return "초기화·장치·동적 로드 관련 함수 이름의 정적 참조: " + (hits.Count == 0 ? "표시된 목록에서 일치 없음" : string.Join(", ", hits.ToArray())) +
                "\n참조 관측은 해당 작업이 실행됐다는 증거가 아닙니다. 누락·동적 로드 및 어느 함수에서 쓰는지는 별도 확인이 필요합니다.";
        }
    }
}
