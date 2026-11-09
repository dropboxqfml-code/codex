using System;
using System.Collections.Generic;
using System.Globalization;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.ProtectionDisableTrial
{
    internal static class DisableTrialReport
    {
        internal static void WriteUserSteps(Action<string> write)
        {
            write("사용 순서1: 기존 일반 GUI에서 평소 충전기를 연결하고 새 관찰 시작을 눌러 충전 진행과 상한 근처 동작을 먼저 기록하세요.");
            write("사용 순서2: 관찰 중단 뒤 관찰 TXT 저장을 한 번 누르세요. AppData의 ATIVBatteryGuard 폴더에 생긴 새 battery-observation TXT를 보관하세요.");
            write("사용 순서3: 충전기를 연결한 상태를 유지하고 이 새 해제 도구의 목적·Elevated를 확인한 뒤 START를 한 번만 입력하세요.");
            write("사용 순서4: 사전1→사후0 후보 일치와 관련 정리 Complete 뒤에는 기존 일반 GUI로 같은 AC 조건의 새 관찰을 기록·한 번 저장합니다.");
            write("이번 해제 TXT와 새 전후 관찰 TXT만 전달하면 됩니다. 기존 진단·삼성 DLL·EXE는 다시 제출하지 않습니다.");
        }

        internal static void WriteAfterCloseSteps(DisableTrialJournal journal, bool storedTransitionMatched)
        {
            if (storedTransitionMatched)
            {
                journal.Write("다음 작업: 기존 일반 GUI를 일반 권한으로 실행하고 같은 충전기 연결 상태에서 새 관찰 시작을 누르세요.");
                journal.Write("일상 사용 중 충전 표시·잔량 변화를 관찰한 뒤 관찰 중단 → 관찰 TXT 저장을 한 번 누르세요.");
                journal.Write("이 해제 TXT와 새 전후 battery-observation TXT를 전달하세요. 80%·NotCharging 한 가지 표시만으로 전기적 결과를 확정하지 않습니다.");
            }
            else
            {
                journal.Write("예상한 저장 모드 전환의 완료 조건을 확인하지 못했습니다. 이 TXT를 먼저 전달하고 해제·ON·추가 시험을 반복하지 마세요.");
            }
        }

        internal static void WriteDiagnostics(DisableTrialJournal journal,
            IReadOnlyList<WsabiWmiProtectionDisableStageDiagnostic> diagnostics)
        {
            if (diagnostics == null) { journal.Write("단계별 판정: 미관측"); return; }
            foreach (var value in diagnostics)
            {
                if (value == null) { journal.Write("단계별 판정: 미관측"); continue; }
                journal.Write(value.Role + " / binding=" + value.BindingVerdict +
                    " / read=" + value.ReadVerdict + " / setter=" + value.SetterVerdict);
            }
        }

        internal static int CandidateCount(WsabiWmiProtectionDisableSnapshot value)
        {
            if (value == null) return 0;
            return Present(value.ObservedPreModeByte) + Present(value.ObservedPostModeByte);
        }

        internal static void WriteSnapshot(DisableTrialJournal journal, WsabiWmiProtectionDisableSnapshot value)
        {
            if (value == null) { journal.Write("저장 후보: 미관측"); return; }
            journal.Write("수용 저장 byte 후보 수: " + CandidateCount(value).ToString(CultureInfo.InvariantCulture));
            journal.Write("전이 모델 수용 읽기 단계 수: " + value.BoundReadCandidateCount.ToString(CultureInfo.InvariantCulture));
            journal.Write("설정 응답 수용(ReceiptOnly): " + (value.SetterReceiptAccepted ? "Yes" : "No"));
            journal.Write("독립 setter 성공 ACK로 판정하지 않습니다.");
            journal.Write("사전 모드 후보: " + Candidate(value.ObservedPreModeByte));
            journal.Write("사후 모드 후보: " + Candidate(value.ObservedPostModeByte));
            journal.Write("모드1→0 저장 후보 일치: " + (value.IsStoredReadbackMatchedCandidate ? "Yes" : "No"));
            if (value.ObservedPreModeByte == 0 && !value.SetterReceiptAccepted && !value.ObservedPostModeByte.HasValue)
                journal.Write("사전 모드0 후보: 이미 해제된 후보이므로 이 시험의 설정0 요청은 없습니다. 현재 충전 재개·100% 성공 판정이 아닙니다.");
            journal.Write("임계값은 조회·변경하지 않았으며 이전값 복원·100% 충전을 확인한 것이 아닙니다.");
            journal.Write("숫자 후보 일치는 전체 절차의 성공·충전기 적용·전기적 충전 재개의 증거가 아닙니다.");
        }

        private static int Present(int? value) => value.HasValue ? 1 : 0;
        private static string Candidate(int? value)
            => value.HasValue && value.Value >= 0 && value.Value <= 255 ? value.Value.ToString(CultureInfo.InvariantCulture) : "미관측";
    }
}
