using System;
using System.Collections.Generic;
using System.Globalization;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.ProtectionTransitionTrial
{
    internal static class ProtectionTrialReport
    {
        internal static void WriteDiagnostics(ProtectionTrialJournal journal,
            IReadOnlyList<WsabiWmiProtectionStageDiagnostic> diagnostics)
        {
            if (diagnostics == null) { journal.Write("단계별 판정: 미관측"); return; }
            foreach (var value in diagnostics)
            {
                if (value == null) { journal.Write("단계별 판정: 미관측"); continue; }
                // These sealed snapshots contain fixed enum names only. They
                // never format provider objects, exception text or raw bytes.
                journal.Write(value.Role + " / binding=" + value.BindingVerdict +
                    " / read=" + value.ReadVerdict + " / setter=" + value.SetterVerdict);
            }
        }

        internal static int CandidateCount(WsabiWmiProtectionTransitionSnapshot value)
        {
            if (value == null) return 0;
            return Present(value.ObservedPreModeByte) + Present(value.ObservedPreUpperByte) + Present(value.ObservedPreLowerByte) +
                Present(value.ObservedPostModeByte) + Present(value.ObservedPostUpperByte) + Present(value.ObservedPostLowerByte);
        }

        internal static void WriteSnapshot(ProtectionTrialJournal journal, WsabiWmiProtectionTransitionSnapshot value)
        {
            if (value == null) { journal.Write("저장 후보: 미관측"); return; }
            journal.Write("수용 저장 byte 후보 수: " + CandidateCount(value).ToString(CultureInfo.InvariantCulture));
            journal.Write("전이 모델 수용 읽기 단계 수: " + value.BoundReadCandidateCount.ToString(CultureInfo.InvariantCulture));
            journal.Write("설정 응답 수용(ReceiptOnly): " + (value.SetterReceiptAccepted ? "Yes" : "No"));
            journal.Write("독립 setter 성공 ACK로 판정하지 않습니다.");
            journal.Write("사전 모드/상한/하한 후보: " + Candidate(value.ObservedPreModeByte) + " / " +
                Candidate(value.ObservedPreUpperByte) + " / " + Candidate(value.ObservedPreLowerByte));
            journal.Write("사후 모드/상한/하한 후보: " + Candidate(value.ObservedPostModeByte) + " / " +
                Candidate(value.ObservedPostUpperByte) + " / " + Candidate(value.ObservedPostLowerByte));
            journal.Write("모드1·상한80·하한75의 저장 후보 일치: " + (value.IsStoredReadbackMatchedCandidate ? "Yes" : "No"));
            journal.Write("숫자 후보 일치는 전체 절차의 성공·충전기 적용·전기적 충전 제한의 증거가 아닙니다.");
        }

        private static int Present(int? value) => value.HasValue ? 1 : 0;
        private static string Candidate(int? value)
            => value.HasValue && value.Value >= 0 && value.Value <= 255 ? value.Value.ToString(CultureInfo.InvariantCulture) : "미관측";
    }
}
