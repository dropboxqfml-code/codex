using System;
using System.Collections.Generic;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum SamsungDriverQueryStatus
    {
        NotChecked, Complete, AccessDenied, TimedOut, Unavailable, UnsupportedPlatform, Partial, InvalidResponse
    }

    public enum SamsungDriverCategory { SabiName, SamsungName }
    public enum SamsungDriverState { Unknown, Stopped, StartPending, StopPending, Running, ContinuePending, PausePending, Paused }
    public enum SamsungDriverStartMode { Unknown, Boot, System, Auto, Manual, Disabled }

    // Deliberately contains no raw service name, display name, path or machine identifier.
    public sealed class SamsungKernelDriverEntry
    {
        public SamsungDriverCategory Category { get; }
        public SamsungDriverState State { get; }
        public SamsungDriverStartMode StartMode { get; }

        public SamsungKernelDriverEntry(SamsungDriverCategory category, SamsungDriverState state, SamsungDriverStartMode startMode)
        {
            if (!Enum.IsDefined(typeof(SamsungDriverCategory), category)) throw new ArgumentOutOfRangeException(nameof(category));
            Category = category;
            State = Enum.IsDefined(typeof(SamsungDriverState), state) ? state : SamsungDriverState.Unknown;
            StartMode = Enum.IsDefined(typeof(SamsungDriverStartMode), startMode) ? startMode : SamsungDriverStartMode.Unknown;
        }
    }

    public sealed class SamsungKernelDriverReport
    {
        public const int MaximumEntries = 32;
        private readonly SamsungKernelDriverEntry[] entries;
        public SamsungDriverQueryStatus Status { get; }
        public SamsungKernelDriverEntry[] Entries => (SamsungKernelDriverEntry[])entries.Clone();
        public bool HardwareWriteAllowed => false;

        public SamsungKernelDriverReport(SamsungDriverQueryStatus status = SamsungDriverQueryStatus.NotChecked,
            IEnumerable<SamsungKernelDriverEntry> entries = null)
        {
            Status = Enum.IsDefined(typeof(SamsungDriverQueryStatus), status) ? status : SamsungDriverQueryStatus.InvalidResponse;
            var copy = new List<SamsungKernelDriverEntry>();
            if (entries != null && (Status == SamsungDriverQueryStatus.Complete || Status == SamsungDriverQueryStatus.Partial))
            {
                int visited = 0;
                foreach (var entry in entries)
                {
                    if (++visited > MaximumEntries) { Status = SamsungDriverQueryStatus.Partial; break; }
                    if (entry == null) { Status = SamsungDriverQueryStatus.InvalidResponse; copy.Clear(); break; }
                    copy.Add(entry);
                }
            }
            this.entries = copy.ToArray();
        }

        public string ToDisplayText(SabiDriverLinkStatus driverLink)
        {
            var text = new StringBuilder();
            text.AppendLine("삼성/SABI 관련 커널 드라이버 — 읽기 전용 등록 상태");
            text.AppendLine("드라이버 조회 결과: " + StatusText(Status));
            text.AppendLine("범위: 로컬 Windows의 커널 드라이버 등록 중 이름 또는 표시 이름에 SABI/Samsung이 포함된 후보입니다. 제조사·장치 용도 검증은 아닙니다.");
            if (Status == SamsungDriverQueryStatus.Complete && entries.Length == 0)
                text.AppendLine("정상 조회 범위에서 이름 조건에 맞는 커널 드라이버 등록을 관측하지 못했습니다. 드라이버 미설치나 배터리 보호 기능 부재를 뜻하지 않습니다.");
            else if (Status != SamsungDriverQueryStatus.Complete)
                text.AppendLine("조회가 완료되지 않았습니다. 표시되지 않은 등록의 부재를 판단할 수 없습니다.");
            for (int i = 0; i < entries.Length; i++)
            {
                var entry = entries[i];
                text.AppendLine("후보 " + (i + 1) + " (" + (entry.Category == SamsungDriverCategory.SabiName ? "SABI 이름 일치" : "Samsung 이름 일치") + "): 등록 관측 / 실행 상태: " +
                    StateText(entry.State) + " / 시작 방식: " + StartModeText(entry.StartMode));
            }
            text.AppendLine("SABI 연결 이름과 비교: " + SamsungFileInspectionReport.DriverLinkText(driverLink));
            if (entries.Length > 0 && driverLink == SabiDriverLinkStatus.NotFound)
                text.AppendLine("드라이버 등록 관측과 SABI 이름 미관측은 동시에 가능합니다. 해당 등록이 SABI 연결을 제공하는지 확인되지 않았습니다.");
            else if (Status == SamsungDriverQueryStatus.Complete && entries.Length == 0 && driverLink == SabiDriverLinkStatus.Present)
                text.AppendLine("연결 이름은 관측됐지만 이름 조건에 맞는 등록은 관측되지 않았습니다. 서로 다른 조회 범위이므로 모순이나 드라이버 부재로 판정하지 않습니다.");
            else
                text.AppendLine("등록·실행 상태와 연결 이름은 서로 다른 시점·범위의 관측입니다. 연결·초기화 성공이나 충전 제한 지원을 보장하지 않습니다.");
            text.AppendLine("드라이버 실행 중이어도 실제 충전 제어는 미지원입니다. 하드웨어 쓰기 허용: false.");
            text.AppendLine("서비스 설치·시작·중지·시작 방식 변경, 삼성 DLL 초기화, OEM 명령은 실행하지 않습니다. 원래 서비스 이름·전체 경로·사용자 이름·고유 식별자는 보고하지 않습니다.");
            return text.ToString();
        }

        public static string StatusText(SamsungDriverQueryStatus status)
        {
            switch (status)
            {
                case SamsungDriverQueryStatus.Complete: return "정상 조회 완료";
                case SamsungDriverQueryStatus.Partial: return "일부 관측 또는 조회 한도 도달";
                case SamsungDriverQueryStatus.AccessDenied: return "조회 권한 없음";
                case SamsungDriverQueryStatus.TimedOut: return "조회 시간 초과";
                case SamsungDriverQueryStatus.Unavailable: return "조회 오류로 확인할 수 없음";
                case SamsungDriverQueryStatus.UnsupportedPlatform: return "Windows에서만 조회 가능";
                case SamsungDriverQueryStatus.InvalidResponse: return "응답 형식 확인 실패";
                default: return "아직 조회하지 않음";
            }
        }

        public static string StateText(SamsungDriverState state)
        {
            switch (state)
            {
                case SamsungDriverState.Stopped: return "중지 (Stopped)";
                case SamsungDriverState.StartPending: return "시작 대기 (Start Pending)";
                case SamsungDriverState.StopPending: return "중지 대기 (Stop Pending)";
                case SamsungDriverState.Running: return "실행 중 (Running)";
                case SamsungDriverState.ContinuePending: return "계속 대기 (Continue Pending)";
                case SamsungDriverState.PausePending: return "일시 중지 대기 (Pause Pending)";
                case SamsungDriverState.Paused: return "일시 중지 (Paused)";
                default: return "알 수 없음 (Unknown)";
            }
        }

        public static string StartModeText(SamsungDriverStartMode mode)
        {
            switch (mode)
            {
                case SamsungDriverStartMode.Boot: return "부팅 (Boot)";
                case SamsungDriverStartMode.System: return "시스템 (System)";
                case SamsungDriverStartMode.Auto: return "자동 (Auto)";
                case SamsungDriverStartMode.Manual: return "수동 (Manual)";
                case SamsungDriverStartMode.Disabled: return "사용 안 함 (Disabled)";
                default: return "알 수 없음 (Unknown)";
            }
        }
    }
}
