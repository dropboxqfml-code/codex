using System;
using System.Collections.Generic;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum SamsungFileInspectionStatus
    {
        NotCollected, Complete, Partial, DirectoryNotFound, Unavailable, TimedOut, UnsupportedPlatform, InvalidResponse
    }

    public enum SamsungFileEntryStatus
    {
        Inspected, NotFound, AccessDenied, TooLarge, InvalidPe, Unavailable, PathRejected
    }

    public enum OfflineSignatureStatus
    {
        NotChecked, ValidOffline, Unsigned, Invalid, Inconclusive
    }

    public enum SabiDriverLinkStatus
    {
        NotChecked, Present, NotFound, AccessDenied, Unavailable, UnsupportedPlatform
    }

    public sealed class SamsungFileInspectionEntry
    {
        public string FileName { get; }
        public string LocationLabel { get; }
        public SamsungFileEntryStatus Status { get; }
        public long Length { get; }
        public string FileVersion { get; }
        public string ProductVersion { get; }
        public string CompanyName { get; }
        public string Description { get; }
        public string Sha256 { get; }
        public PeModuleInfo Pe { get; }
        public OfflineSignatureStatus Signature { get; }
        public bool HardwareWriteAllowed => false;

        public SamsungFileInspectionEntry(string fileName, string locationLabel, SamsungFileEntryStatus status,
            long length = 0, string fileVersion = null, string productVersion = null, string companyName = null,
            string description = null, string sha256 = null, PeModuleInfo pe = null,
            OfflineSignatureStatus signature = OfflineSignatureStatus.NotChecked)
        {
            FileName = CanonicalFileName(fileName);
            if (FileName == null) throw new ArgumentException("Unsupported inspection target.", nameof(fileName));
            if (!IsLocationLabel(locationLabel)) throw new ArgumentException("Unsupported location label.", nameof(locationLabel));
            LocationLabel = locationLabel;
            Status = Enum.IsDefined(typeof(SamsungFileEntryStatus), status) ? status : SamsungFileEntryStatus.Unavailable;
            if (Status == SamsungFileEntryStatus.Inspected && (length < 1 || length > SamsungFileInspectionReport.MaximumFileBytes ||
                pe == null || !pe.IsValid || (pe.Architecture != "x86" && pe.Architecture != "x64") || !IsSha256(sha256))) Status = SamsungFileEntryStatus.Unavailable;
            bool inspected = Status == SamsungFileEntryStatus.Inspected;
            Length = inspected ? length : 0;
            FileVersion = inspected ? CleanMetadata(fileVersion) : string.Empty;
            ProductVersion = inspected ? CleanMetadata(productVersion) : string.Empty;
            CompanyName = inspected ? CleanMetadata(companyName) : string.Empty;
            Description = inspected ? CleanMetadata(description) : string.Empty;
            Sha256 = inspected ? sha256.ToLowerInvariant() : string.Empty;
            // Snapshot the PE result and keep only fixed parser diagnostics, not arbitrary error text.
            Pe = inspected ? new PeModuleInfo(true, pe.IsManaged, pe.Architecture, pe.ImportedModules, pe.ExportedNames,
                string.IsNullOrEmpty(pe.Error) ? string.Empty : "표시 또는 분석 범위가 제한됐습니다.", pe.ImportedFunctions)
                : new PeModuleInfo(false, false, "Unknown");
            Signature = inspected && Enum.IsDefined(typeof(OfflineSignatureStatus), signature) ? signature : OfflineSignatureStatus.NotChecked;
        }

        public static string CanonicalFileName(string name)
        {
            foreach (string allowed in new[] { "Sabi3.dll", "wsabi.dll", "BatteryToast.exe", "PowerAudit.exe" })
                if (string.Equals(name, allowed, StringComparison.OrdinalIgnoreCase)) return allowed;
            return null;
        }

        public static bool IsLocationLabel(string value)
        {
            return value == "Setting" || value == "Settings" || value == "Setting 하위 폴더" || value == "Settings 하위 폴더";
        }

        public static string CleanMetadata(string value)
        {
            if (string.IsNullOrWhiteSpace(value)) return string.Empty;
            if (value.Length > 120) return string.Empty;
            foreach (char item in value)
                if (!char.IsLetterOrDigit(item) && " .,-_()+&©®™".IndexOf(item) < 0) return string.Empty;
            return value.Trim();
        }

        public static bool IsSha256(string value)
        {
            if (value == null || value.Length != 64) return false;
            foreach (char item in value)
                if (!(item >= '0' && item <= '9') && !(item >= 'a' && item <= 'f') && !(item >= 'A' && item <= 'F')) return false;
            return true;
        }
    }

    public sealed class SamsungFileInspectionReport
    {
        public const int MaximumEntries = 16;
        public const int MaximumFileBytes = 16777216;
        private readonly SamsungFileInspectionEntry[] entries;
        public SamsungFileInspectionStatus Status { get; }
        public SamsungFileInspectionEntry[] Entries => (SamsungFileInspectionEntry[])entries.Clone();
        public bool Limited { get; }
        public SabiDriverLinkStatus DriverLink { get; }
        public bool HardwareWriteAllowed => false;

        public SamsungFileInspectionReport(SamsungFileInspectionStatus status = SamsungFileInspectionStatus.NotCollected,
            IEnumerable<SamsungFileInspectionEntry> entries = null, bool limited = false,
            SabiDriverLinkStatus driverLink = SabiDriverLinkStatus.NotChecked)
        {
            DriverLink = Enum.IsDefined(typeof(SabiDriverLinkStatus), driverLink) ? driverLink : SabiDriverLinkStatus.Unavailable;
            Status = Enum.IsDefined(typeof(SamsungFileInspectionStatus), status) ? status : SamsungFileInspectionStatus.InvalidResponse;
            var copy = new List<SamsungFileInspectionEntry>();
            if (entries != null && (Status == SamsungFileInspectionStatus.Complete || Status == SamsungFileInspectionStatus.Partial))
            {
                int visited = 0;
                foreach (var entry in entries)
                {
                    if (++visited > MaximumEntries) { limited = true; break; }
                    if (entry == null) { Status = SamsungFileInspectionStatus.InvalidResponse; copy.Clear(); break; }
                    copy.Add(entry);
                }
            }
            this.entries = copy.ToArray();
            if (Status == SamsungFileInspectionStatus.Complete && copy.Count == 0) Status = SamsungFileInspectionStatus.DirectoryNotFound;
            if (Status == SamsungFileInspectionStatus.Complete && copy.Exists(entry => entry.Status != SamsungFileEntryStatus.Inspected && entry.Status != SamsungFileEntryStatus.NotFound))
                Status = SamsungFileInspectionStatus.Partial;
            Limited = limited;
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("ATIV Battery Guard — 삼성 파일의 읽기 전용 식별 보고서");
            text.AppendLine("조회 결과: " + StatusText(Status));
            text.AppendLine("대상: Sabi3.dll / wsabi.dll / BatteryToast.exe / PowerAudit.exe");
            text.AppendLine("SABI 장치 연결 이름: " + DriverLinkText(DriverLink));
            text.AppendLine("장치 이름 조회만 수행합니다. 연결 이름의 존재는 장치 접근·드라이버 규약·배터리 기능 지원의 증거가 아닙니다.");
            text.AppendLine(ATIVBatteryGuard.Core.Services.Sabi3PreparationAssessment.Evaluate(this).ToDisplayText());
            text.AppendLine("Setting·Settings의 고정 범위에서 대상 파일의 정보만 읽습니다. 원본 파일은 복사·로드·실행하지 않습니다.");
            foreach (var entry in entries)
            {
                text.AppendLine();
                text.AppendLine("[" + entry.FileName + " · " + entry.LocationLabel + "]");
                text.AppendLine("파일 상태: " + EntryStatusText(entry.Status));
                if (entry.Status != SamsungFileEntryStatus.Inspected) continue;
                text.AppendLine("크기: " + entry.Length + " bytes");
                text.AppendLine("파일 버전: " + Display(entry.FileVersion));
                text.AppendLine("제품 버전: " + Display(entry.ProductVersion));
                text.AppendLine("회사 표시: " + Display(entry.CompanyName));
                text.AppendLine("파일 설명: " + Display(entry.Description));
                text.AppendLine("SHA-256: " + entry.Sha256);
                text.AppendLine("PE 구조: " + entry.Pe.Architecture + (entry.Pe.IsManaged ? " · 관리 코드 (실제 실행 비트 수는 이 표시만으로 확정하지 않음)" : " · 네이티브 코드"));
                text.AppendLine("서명: " + SignatureText(entry.Signature));
                text.AppendLine("정적 DLL 참조: " + Join(entry.Pe.ImportedModules));
                text.AppendLine("정적 import 함수 (이름 또는 ordinal):");
                foreach (var function in entry.Pe.ImportedFunctions) text.AppendLine("  " + function.DisplayName);
                if (entry.Pe.ImportedFunctions.Length == 0) text.AppendLine("  표시된 함수 없음");
                text.AppendLine(ATIVBatteryGuard.Core.Services.Sabi3PreparationAssessment.DescribeObservedImports(entry.Pe));
                text.AppendLine("이름으로 내보낸 함수: " + Join(entry.Pe.ExportedNames));
                if (!string.IsNullOrEmpty(entry.Pe.Error)) text.AppendLine("PE 이름 목록은 표시 또는 분석 범위가 제한됐습니다.");
                if (entry.FileName == "Sabi3.dll") AppendSabiFunctions(text, entry.Pe.ExportedNames);
                if (entry.FileName == "Sabi3.dll" && entry.Pe.Architecture == "x64" && !entry.Pe.IsManaged &&
                    entry.Sha256 == ATIVBatteryGuard.Core.Services.Sabi3X64Abi.AnalyzedSha256)
                    text.AppendLine("정적 분석 대상과 같은 x64 DLL입니다. 관측된 호출자 버퍼는 11바이트이며 공개 4바이트 예제를 그대로 사용하지 않습니다. 실제 함수 호출은 하지 않았습니다.");
            }
            if (Limited) text.AppendLine("조회 범위 또는 표시 한도에 도달했습니다. 누락 항목을 부재로 판단하지 않습니다.");
            text.AppendLine();
            text.AppendLine("Sabi3.dll: 공개 구현에서 배터리 보호 조회·변경에 사용하나 현재 파일의 ABI·모델 지원은 미검증입니다.");
            text.AppendLine("wsabi.dll: 삼성 펌웨어 중계 후보이며 배터리 제어 역할은 미확인입니다.");
            text.AppendLine("BatteryToast.exe: 이름상 배터리 알림, PowerAudit.exe: 이름상 전원 점검으로 추정합니다. 실제 기능은 미확인입니다.");
            text.AppendLine("정적 참조에는 지연·동적 로드, 관리 코드의 P/Invoke·어셈블리 참조, 프로세스 간 통신이 모두 포함되지 않습니다.");
            text.AppendLine("함수 이름과 서명 검증 성공은 호출 규약·배터리 제어 지원·실행 안전성의 증거가 아닙니다.");
            text.AppendLine("서명 확인은 로컬 캐시만 사용하며 온라인 인증서 폐기 여부는 확인하지 않습니다.");
            text.AppendLine("전체 설치 경로·사용자 이름·시리얼번호·예외 원문·삼성 파일 원본은 보고하지 않습니다. 자동 전송하지 않습니다.");
            text.AppendLine("실제 충전 제어: 미지원. 하드웨어 쓰기 허용: false.");
            return text.ToString();
        }

        private static void AppendSabiFunctions(StringBuilder text, string[] exportedNames)
        {
            var found = new HashSet<string>(exportedNames, StringComparer.Ordinal);
            var present = new List<string>();
            foreach (string name in new[] { "InitBIOSInterface", "UninitBIOSInterface", "CheckSamsung", "CallBIOSInterface", "CallBIOSInterfaceEx" })
                if (found.Contains(name)) present.Add(name);
            text.AppendLine("공개 예제의 함수 이름과 일치: " + (present.Count == 0 ? "표시된 이름에서 일치 없음" : string.Join(", ", present.ToArray())));
            text.AppendLine("함수 목록의 한도·이름 장식·이름 없는 export에 따라 빠질 수 있습니다. 일치 여부만으로 호출하지 않습니다.");
        }

        private static string Display(string value) => string.IsNullOrEmpty(value) ? "제공되지 않음 또는 표시 제외" : value;

        public static string DriverLinkText(SabiDriverLinkStatus status)
        {
            switch (status)
            {
                case SabiDriverLinkStatus.Present: return "현재 이름 조회에서 SABI 연결 발견 (장치를 열지 않음)";
                case SabiDriverLinkStatus.NotFound: return "현재 이름 조회에서 SABI 연결을 찾지 못함 (펌웨어 기능 부재 판정 아님)";
                case SabiDriverLinkStatus.AccessDenied: return "이름 조회 권한 없음";
                case SabiDriverLinkStatus.Unavailable: return "이름 조회 결과를 확인할 수 없음";
                case SabiDriverLinkStatus.UnsupportedPlatform: return "Windows에서만 이름 조회 가능";
                default: return "이름 조회를 수행하지 않음";
            }
        }
        private static string Join(string[] values) => values.Length == 0 ? "표시된 이름 없음" : string.Join(", ", values);

        public static string StatusText(SamsungFileInspectionStatus status)
        {
            switch (status)
            {
                case SamsungFileInspectionStatus.Complete: return "파일별 읽기 전용 확인 완료";
                case SamsungFileInspectionStatus.Partial: return "일부 확인 완료, 누락·오류는 파일별 표시";
                case SamsungFileInspectionStatus.DirectoryNotFound: return "고정 조회 범위에서 대상 폴더를 찾지 못함";
                case SamsungFileInspectionStatus.TimedOut: return "조회 시간 초과 또는 이전 조회 종료 대기";
                case SamsungFileInspectionStatus.UnsupportedPlatform: return "Windows에서만 조회 가능";
                case SamsungFileInspectionStatus.InvalidResponse: return "응답 형식 확인 실패";
                case SamsungFileInspectionStatus.Unavailable: return "조회할 수 없음";
                default: return "아직 조회하지 않음";
            }
        }

        public static string EntryStatusText(SamsungFileEntryStatus status)
        {
            switch (status)
            {
                case SamsungFileEntryStatus.Inspected: return "파일 정보 확인 완료";
                case SamsungFileEntryStatus.NotFound: return "조회 범위에서 찾지 못함";
                case SamsungFileEntryStatus.AccessDenied: return "읽기 권한 없음";
                case SamsungFileEntryStatus.TooLarge: return "파일 크기 한도 초과";
                case SamsungFileEntryStatus.InvalidPe: return "지원 범위의 PE 구조 확인 실패";
                case SamsungFileEntryStatus.PathRejected: return "허용 범위·링크 검사에서 제외";
                default: return "파일 정보를 읽을 수 없음";
            }
        }

        public static string SignatureText(OfflineSignatureStatus status)
        {
            switch (status)
            {
                case OfflineSignatureStatus.ValidOffline: return "로컬 캐시 기반 서명 검증 성공 (온라인 폐기 확인 안 함)";
                case OfflineSignatureStatus.Unsigned: return "검증 가능한 내장 서명 없음 (카탈로그 서명 별도 미확인)";
                case OfflineSignatureStatus.Invalid: return "서명 검증 불일치";
                case OfflineSignatureStatus.Inconclusive: return "오프라인 환경에서 서명 신뢰 확인 불가";
                default: return "확인하지 않음";
            }
        }
    }
}
