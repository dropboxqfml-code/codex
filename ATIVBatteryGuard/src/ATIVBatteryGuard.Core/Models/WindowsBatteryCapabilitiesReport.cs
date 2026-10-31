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
