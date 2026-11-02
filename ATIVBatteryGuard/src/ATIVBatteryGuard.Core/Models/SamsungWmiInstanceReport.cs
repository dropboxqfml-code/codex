using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Core.Models
{
    public enum SamsungWmiClass { Version, Method }
    public enum SamsungWmiQueryStatus
    {
        NotChecked, Complete, Partial, ClassNotFound, NamespaceNotFound, AccessDenied, TimedOut, Unavailable, UnsupportedPlatform, InvalidResponse
    }

    // Only observed public property values; there is no instance key or provider path.
    public sealed class SamsungWmiInstanceEntry
    {
        public bool? Active { get; }
        public uint? Version { get; }
        public SamsungWmiInstanceEntry(bool? active, uint? version = null)
        {
            Active = active;
            Version = version;
        }
    }

    public sealed class SamsungWmiClassObservation
    {
        public const int MaximumEntries = 8;
        private readonly SamsungWmiInstanceEntry[] entries;
        public SamsungWmiClass Kind { get; }
        public SamsungWmiQueryStatus Status { get; }
        public SamsungWmiInstanceEntry[] Entries => (SamsungWmiInstanceEntry[])entries.Clone();

        public SamsungWmiClassObservation(SamsungWmiClass kind, SamsungWmiQueryStatus status,
            IEnumerable<SamsungWmiInstanceEntry> entries = null)
        {
            if (!Enum.IsDefined(typeof(SamsungWmiClass), kind)) throw new ArgumentOutOfRangeException(nameof(kind));
            Kind = kind;
            Status = Enum.IsDefined(typeof(SamsungWmiQueryStatus), status) ? status : SamsungWmiQueryStatus.InvalidResponse;
            var copy = new List<SamsungWmiInstanceEntry>();
            if (entries != null && (Status == SamsungWmiQueryStatus.Complete || Status == SamsungWmiQueryStatus.Partial))
            {
                int visited = 0;
                foreach (var entry in entries)
                {
                    if (++visited > MaximumEntries) { Status = SamsungWmiQueryStatus.Partial; break; }
                    if (entry == null || (kind == SamsungWmiClass.Method && entry.Version.HasValue))
                    {
                        Status = SamsungWmiQueryStatus.InvalidResponse; copy.Clear(); break;
                    }
                    copy.Add(entry);
                    if (Status == SamsungWmiQueryStatus.Complete && (!entry.Active.HasValue || (kind == SamsungWmiClass.Version && !entry.Version.HasValue)))
                        Status = SamsungWmiQueryStatus.Partial;
                }
            }
            this.entries = copy.ToArray();
        }
    }

    public sealed class SamsungWmiInstanceReport
    {
        public SamsungWmiClassObservation VersionClass { get; }
        public SamsungWmiClassObservation MethodClass { get; }
        public bool HardwareWriteAllowed => false;
        public bool CanInvokeMethods => false;

        public SamsungWmiInstanceReport(SamsungWmiClassObservation versionClass = null, SamsungWmiClassObservation methodClass = null)
        {
            VersionClass = FixedClass(versionClass, SamsungWmiClass.Version);
            MethodClass = FixedClass(methodClass, SamsungWmiClass.Method);
        }

        public static SamsungWmiInstanceReport Failure(SamsungWmiQueryStatus status)
        {
            // Complete/Partial require actual collection and cannot be manufactured as a failure.
            if (status == SamsungWmiQueryStatus.Complete || status == SamsungWmiQueryStatus.Partial)
                status = SamsungWmiQueryStatus.InvalidResponse;
            return new SamsungWmiInstanceReport(new SamsungWmiClassObservation(SamsungWmiClass.Version, status),
                new SamsungWmiClassObservation(SamsungWmiClass.Method, status));
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("삼성 WMI 인스턴스 — 읽기 전용 버전·활성 상태");
            text.AppendLine(@"조회 범위: 로컬 ROOT\WMI의 WmiAcpiVersion.Active/version 및 WmiAcpiMethod.Active 속성만 읽습니다.");
            text.AppendLine("연결은 현재 사용자 권한으로 암호화 인증(PacketPrivacy)을 요청합니다. 조회 실패 시 권한 상승이나 보안 설정 변경으로 전환하지 않습니다.");
            AppendClass(text, VersionClass);
            AppendClass(text, MethodClass);
            text.AppendLine("Active=True는 WMI 인스턴스가 보고한 활성 값이며 배터리 보호가 켜졌다는 뜻이 아닙니다. 버전 값은 관측한 UInt32 원값이며 모델·명령 호환성을 해석하지 않습니다.");
            text.AppendLine("여러 인스턴스는 모두 별도 관측으로 표시하며 하나를 선택하거나 두 클래스의 행을 서로 대응시키지 않습니다. 행 번호는 보고서 안의 순서일 뿐 고유 식별자가 아닙니다.");
            text.AppendLine("WMI 인스턴스, 드라이버 등록·실행 상태, SABI 연결 이름은 다른 범위의 관측입니다. 어느 결과도 DLL 초기화·OEM 명령 성공이나 충전 제한 지원을 입증하지 않습니다.");
            text.AppendLine("인스턴스 이름·WMI 경로·사용자 이름·고유 식별자·예외 원문은 보고하지 않습니다. WMI 메서드 호출·삼성 DLL 초기화·하드웨어 쓰기는 하지 않습니다.");
            text.AppendLine("실제 충전 제어: 미지원. 하드웨어 쓰기 허용: false.");
            return text.ToString();
        }

        public static string StatusText(SamsungWmiQueryStatus status)
        {
            switch (status)
            {
                case SamsungWmiQueryStatus.Complete: return "정상 조회 완료";
                case SamsungWmiQueryStatus.Partial: return "일부 관측 또는 속성·조회 한도 제한";
                case SamsungWmiQueryStatus.ClassNotFound: return "대상 클래스를 찾지 못함";
                case SamsungWmiQueryStatus.NamespaceNotFound: return "대상 네임스페이스를 찾지 못함";
                case SamsungWmiQueryStatus.AccessDenied: return "조회 권한 없음";
                case SamsungWmiQueryStatus.TimedOut: return "조회 시간 초과";
                case SamsungWmiQueryStatus.Unavailable: return "조회 오류로 확인할 수 없음";
                case SamsungWmiQueryStatus.UnsupportedPlatform: return "Windows에서만 조회 가능";
                case SamsungWmiQueryStatus.InvalidResponse: return "응답 형식 확인 실패";
                default: return "아직 조회하지 않음";
            }
        }

        private static SamsungWmiClassObservation FixedClass(SamsungWmiClassObservation value, SamsungWmiClass expected)
        {
            if (value == null) return new SamsungWmiClassObservation(expected, SamsungWmiQueryStatus.NotChecked);
            return value.Kind == expected ? value : new SamsungWmiClassObservation(expected, SamsungWmiQueryStatus.InvalidResponse);
        }

        private static void AppendClass(StringBuilder text, SamsungWmiClassObservation observation)
        {
            text.AppendLine(SamsungWmiInstancePolicy.GetClassName(observation.Kind) + ": " + StatusText(observation.Status));
            var entries = observation.Entries;
            if (observation.Status == SamsungWmiQueryStatus.Complete && entries.Length == 0)
                text.AppendLine("  정상 조회에서 인스턴스가 관측되지 않았습니다. 클래스 없음·조회 오류와 구분하며 펌웨어 기능 부재 판정은 아닙니다.");
            else if (observation.Status != SamsungWmiQueryStatus.Complete)
                text.AppendLine("  완전한 조회가 아니므로 표시되지 않은 인스턴스의 부재를 판단하지 않습니다.");
            for (int i = 0; i < entries.Length; i++)
            {
                var entry = entries[i];
                string line = "  관측 " + (i + 1) + ": Active=" + (entry.Active.HasValue ? (entry.Active.Value ? "True" : "False") : "Unknown");
                if (observation.Kind == SamsungWmiClass.Version)
                    line += ", version=" + (entry.Version.HasValue ? entry.Version.Value.ToString(CultureInfo.InvariantCulture) + " (0x" + entry.Version.Value.ToString("X8", CultureInfo.InvariantCulture) + ")" : "Unknown");
                text.AppendLine(line);
            }
        }
    }
}
