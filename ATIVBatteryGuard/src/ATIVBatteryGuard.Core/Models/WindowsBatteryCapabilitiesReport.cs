using System;
using System.Collections.Generic;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum BatteryProbeStatus
    {
        NotCollected, Complete, NoDevices, AccessDenied, TimedOut,
        Unavailable, InvalidResponse, UnsupportedPlatform, Partial
    }

    public enum BatteryRequestAssessment
    {
        NotCollected, Inconclusive, NoSupportAdvertised, SupportAdvertised
    }

    public sealed class BatteryCapabilityEntry
    {
        public int Index { get; }
        public BatteryProbeStatus Status { get; }
        public uint? Capabilities { get; }
        public bool? ChargeRequestSupported => Capabilities.HasValue ? (bool?)((Capabilities.Value & 1) != 0) : null;
        public bool? DischargeRequestSupported => Capabilities.HasValue ? (bool?)((Capabilities.Value & 2) != 0) : null;
        public bool HardwareWriteAllowed => false;

        public BatteryCapabilityEntry(int index, BatteryProbeStatus status, uint? capabilities = null)
        {
            if (index < 1 || index > WindowsBatteryCapabilitiesReport.MaximumDevices) throw new ArgumentOutOfRangeException(nameof(index));
            Index = index;
            Status = Enum.IsDefined(typeof(BatteryProbeStatus), status) ? status : BatteryProbeStatus.InvalidResponse;
            if (Status == BatteryProbeStatus.Complete && !capabilities.HasValue) Status = BatteryProbeStatus.InvalidResponse;
            Capabilities = Status == BatteryProbeStatus.Complete ? capabilities : null;
        }
    }

    public sealed class WindowsBatteryCapabilitiesReport
    {
        public const int MaximumDevices = 8;
        private readonly BatteryCapabilityEntry[] entries;
        public BatteryProbeStatus Status { get; }
        public BatteryCapabilityEntry[] Entries => (BatteryCapabilityEntry[])entries.Clone();
        public bool Limited { get; }
        public bool HardwareWriteAllowed => false;

        public BatteryRequestAssessment RequestAssessment
        {
            get
            {
                if (Status == BatteryProbeStatus.NotCollected) return BatteryRequestAssessment.NotCollected;
                if (Status != BatteryProbeStatus.Complete || Limited) return BatteryRequestAssessment.Inconclusive;
                bool foundSystemBattery = false;
                bool supportAdvertised = false;
                foreach (var entry in entries)
                {
                    uint flags = entry.Capabilities.Value;
                    // A short-term battery (for example a UPS) is not the laptop battery target.
                    if ((flags & 0x80000000u) == 0 || (flags & 0x20000000u) != 0) continue;
                    foundSystemBattery = true;
                    supportAdvertised |= (flags & 3u) != 0;
                }
                if (!foundSystemBattery) return BatteryRequestAssessment.Inconclusive;
                return supportAdvertised ? BatteryRequestAssessment.SupportAdvertised : BatteryRequestAssessment.NoSupportAdvertised;
            }
        }

        public string AssessmentText
        {
            get
            {
                switch (RequestAssessment)
                {
                    case BatteryRequestAssessment.NoSupportAdvertised:
                        return "현재 Windows 배터리 드라이버는 표준 충전·방전 요청 지원을 표시하지 않습니다. 이 경로를 제어에 사용하지 않습니다. 삼성 충전 상한 지원은 별도 미검증입니다.";
                    case BatteryRequestAssessment.SupportAdvertised:
                        return "표준 충전·방전 요청 중 지원 표시가 있습니다. 80%/100% 충전 상한 지원을 뜻하지 않으며 실제 제어는 활성화하지 않습니다.";
                    case BatteryRequestAssessment.Inconclusive:
                        return "일반 시스템 배터리의 표준 요청 지원 여부를 확정할 수 없습니다. " + StatusText(Status) + (Limited ? " · 조회 범위 제한" : string.Empty) + ". 조회 누락을 미지원으로 판단하지 않습니다.";
                    default:
                        return "아직 조회하지 않았습니다. ‘진단 파일 만들기’로 읽기 전용 결과를 확인할 수 있습니다.";
                }
            }
        }

        public WindowsBatteryCapabilitiesReport(BatteryProbeStatus status = BatteryProbeStatus.NotCollected,
            IEnumerable<BatteryCapabilityEntry> entries = null, bool limited = false)
        {
            Status = Enum.IsDefined(typeof(BatteryProbeStatus), status) ? status : BatteryProbeStatus.InvalidResponse;
            var copy = new List<BatteryCapabilityEntry>();
            var indices = new HashSet<int>();
            if (entries != null && (Status == BatteryProbeStatus.Complete || Status == BatteryProbeStatus.Partial))
            {
                int visited = 0;
                foreach (var entry in entries)
                {
                    if (++visited > MaximumDevices) { limited = true; break; }
                    if (entry == null || !indices.Add(entry.Index)) { Status = BatteryProbeStatus.InvalidResponse; copy.Clear(); break; }
                    copy.Add(entry);
                }
            }
            this.entries = copy.ToArray();
            if (Status == BatteryProbeStatus.Complete && copy.Count == 0) Status = BatteryProbeStatus.NoDevices;
            if (Status == BatteryProbeStatus.Complete && copy.Exists(x => x.Status != BatteryProbeStatus.Complete)) Status = BatteryProbeStatus.Partial;
            Limited = limited;
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("[Windows 표준 배터리 드라이버의 요청 지원 여부]");
            text.AppendLine("조회 결과: " + StatusText(Status));
            text.AppendLine("결과 해석: " + AssessmentText);
            foreach (var entry in entries)
            {
                text.AppendLine("배터리 인터페이스 " + entry.Index + ": " + StatusText(entry.Status));
                if (!entry.Capabilities.HasValue) continue;
                text.AppendLine("  Capabilities: 0x" + entry.Capabilities.Value.ToString("X8"));
                text.AppendLine("  BatteryCharge 요청: " + (entry.ChargeRequestSupported.Value ? "지원 표시" : "지원 표시 없음"));
                text.AppendLine("  BatteryDischarge 요청: " + (entry.DischargeRequestSupported.Value ? "지원 표시" : "지원 표시 없음"));
            }
            if (Limited) text.AppendLine("최대 8개 인터페이스만 확인했거나 일부 조회가 제한됐습니다.");
            text.AppendLine("이 플래그는 표준 충전/방전 요청의 지원 표시이며 80% 충전 상한이나 OEM 기능 지원의 증거가 아닙니다.");
            text.AppendLine("조회 실패는 미지원 판정으로 바꾸지 않습니다. 표시된 지원 요청도 실행하지 않았습니다.");
            text.AppendLine("QUERY_TAG 및 QUERY_INFORMATION(BatteryInformation)만 사용합니다. SET 요청과 OEM 메서드는 호출하지 않습니다.");
            text.AppendLine("장치 경로·배터리 태그·시리얼번호·고유 ID는 보고서에 기록하지 않습니다.");
            text.AppendLine("실제 충전 제어: 미지원. 하드웨어 쓰기 허용: false.");
            return text.ToString();
        }

        public static string StatusText(BatteryProbeStatus status)
        {
            switch (status)
            {
                case BatteryProbeStatus.Complete: return "읽기 전용 조회 완료";
                case BatteryProbeStatus.Partial: return "일부 조회 완료, 누락 결과 별도 표시";
                case BatteryProbeStatus.NoDevices: return "이 경로에서 현재 배터리 장치를 찾지 못함";
                case BatteryProbeStatus.AccessDenied: return "읽기 권한 없음 (권한 상승 요청 안 함)";
                case BatteryProbeStatus.TimedOut: return "조회 시간 초과 또는 이전 조회 종료 대기";
                case BatteryProbeStatus.Unavailable: return "조회할 수 없음";
                case BatteryProbeStatus.InvalidResponse: return "응답 형식 확인 실패";
                case BatteryProbeStatus.UnsupportedPlatform: return "Windows에서만 조회 가능";
                default: return "아직 조회하지 않음";
            }
        }
    }
}
