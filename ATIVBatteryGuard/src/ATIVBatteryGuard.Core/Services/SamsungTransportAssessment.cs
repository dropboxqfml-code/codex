using System;
using System.Text;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // A pure explanation of independent observations, never a transport selector.
    public sealed class SamsungTransportAssessment
    {
        private readonly SabiDriverLinkStatus link;
        private readonly SamsungWmiQueryStatus versionStatus;
        private readonly SamsungWmiQueryStatus methodStatus;
        public int DriverCandidates { get; private set; }
        public int StoppedManualCandidates { get; private set; }
        public bool DriverInventoryComplete { get; private set; }
        public bool HasWmiAccessDenied => versionStatus == SamsungWmiQueryStatus.AccessDenied || methodStatus == SamsungWmiQueryStatus.AccessDenied;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;
        public bool CanInvokeMethods => false;

        private SamsungTransportAssessment(SamsungFileInspectionReport report)
        {
            link = report.DriverLink;
            versionStatus = report.WmiInstances.VersionClass.Status;
            methodStatus = report.WmiInstances.MethodClass.Status;
            DriverInventoryComplete = report.KernelDrivers.Status == SamsungDriverQueryStatus.Complete;
            foreach (var entry in report.KernelDrivers.Entries)
            {
                DriverCandidates++;
                if (entry.State == SamsungDriverState.Stopped && entry.StartMode == SamsungDriverStartMode.Manual)
                    StoppedManualCandidates++;
            }
        }

        public static SamsungTransportAssessment Evaluate(SamsungFileInspectionReport report)
            => new SamsungTransportAssessment(report ?? new SamsungFileInspectionReport());

        public string Summary => "SABI 이름: " + LinkSummary(link) +
            " / WMI 버전: " + SamsungWmiInstanceReport.StatusText(versionStatus) +
            " / WMI 메서드 인스턴스: " + SamsungWmiInstanceReport.StatusText(methodStatus) +
            " / 실제 충전 제어: 미지원";

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("[삼성 전송 경로 관측 요약]");
            text.AppendLine(Summary);
            text.AppendLine("TXT 저장 성공과 각 조회 성공은 별개입니다. 이 요약은 현재 보고서의 관측만 설명하며 사용할 제어 경로를 선택하지 않습니다.");
            if (link == SabiDriverLinkStatus.NotFound)
                text.AppendLine("SABI 이름은 현재 조회에서 미관측입니다. 분석한 x64 DLL의 연결 선행 조건을 확인하지 못했지만 드라이버 미설치나 펌웨어 기능 부재는 확정하지 않습니다.");
            if (HasWmiAccessDenied)
                text.AppendLine("WMI 속성 조회가 권한 거부됐습니다. 해당 클래스의 Active·version을 알 수 없으며 비활성·미지원·클래스 부재로 바꾸지 않습니다. 거부 지점·원인은 이 결과만으로 특정할 수 없고 관리자 실행이 해결한다는 근거도 없습니다.");
            if (DriverCandidates > 0)
            {
                text.AppendLine("관측한 이름 후보 " + DriverCandidates + "개 중 중지·수동 시작 조합은 " + StoppedManualCandidates + "개입니다.");
                text.AppendLine("이 후보가 SABI 연결이나 충전 기능을 제공하는지 확인되지 않았습니다. 중지·수동 설정을 고장으로 단정하거나 시작 대상으로 선택하지 않습니다.");
            }
            if (!DriverInventoryComplete)
                text.AppendLine("드라이버 목록이 정상 완료되지 않았으므로 표시하지 않은 등록의 부재를 판단하지 않습니다.");
            text.AppendLine("SABI 이름 조회와 WMI 속성 조회는 독립된 경로입니다. 이름 미관측이나 후보 중지 상태를 WMI 권한 거부의 원인으로 단정하지 않습니다.");
            text.AppendLine("권한 상승·ACL 변경·드라이버/서비스 시작·삼성 DLL 초기화·OEM 명령 실행으로 자동 전환하지 않습니다.");
            text.AppendLine("실제 설정 읽기와 충전 제어는 미검증·미지원이며 하드웨어 쓰기 허용은 false입니다.");
            return text.ToString();
        }

        private static string LinkSummary(SabiDriverLinkStatus status)
        {
            switch (status)
            {
                case SabiDriverLinkStatus.Present: return "관측 (접근 미검증)";
                case SabiDriverLinkStatus.NotFound: return "미관측";
                case SabiDriverLinkStatus.AccessDenied: return "조회 권한 없음";
                case SabiDriverLinkStatus.Unavailable: return "조회 결과 확인 불가";
                case SabiDriverLinkStatus.UnsupportedPlatform: return "Windows 전용";
                default: return "미조회";
            }
        }
    }
}
