using System;
using System.Collections.Generic;
using System.Globalization;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Conservative successful-report grammar only. This parser never reads a
    // file, reconstructs a request, authenticates text or promotes actualMode.
    public static class WsabiWmiProtection0To1ReviewParser
    {
        public const int MaximumCharacters = 16384;
        public const int MaximumLines = 128;
        public const int MaximumLineCharacters = 512;
        private const string PrePrefix = "사전 모드/상한/하한 후보: ";
        private const string PostPrefix = "사후 모드/상한/하한 후보: ";
        private const string Pending = "관련 종료·정리 확인 불가: Pending. 참조와 수명을 유지하며 추가 해제·호출·재시도 없이 기다립니다.";
        private static readonly string[] ReadDiagnostic = {
            "PreMode / binding=ReadCandidate / read=CorrelatedStoredByteCandidate / setter=NotReviewed",
            "PreUpper / binding=ReadCandidate / read=CorrelatedStoredByteCandidate / setter=NotReviewed",
            "PreLower / binding=ReadCandidate / read=CorrelatedStoredByteCandidate / setter=NotReviewed",
            "SemanticSet1 / binding=ReceiptOnly / read=NotReviewed / setter=ReceiptOnly",
            "PostMode / binding=ReadCandidate / read=CorrelatedStoredByteCandidate / setter=NotReviewed",
            "PostUpper / binding=ReadCandidate / read=CorrelatedStoredByteCandidate / setter=NotReviewed",
            "PostLower / binding=ReadCandidate / read=CorrelatedStoredByteCandidate / setter=NotReviewed" };
        private static readonly string[] Expected = BuildExpected();

        public static WsabiWmiProtection0To1Review Parse(string input)
        {
            if (input == null || input.Length > MaximumCharacters || string.IsNullOrWhiteSpace(input)) return Invalid();
            if (input[0] == '\uFEFF') input = input.Substring(1);
            input = input.Replace("\r\n", "\n");
            if (input.IndexOf('\r') >= 0) return Invalid();
            foreach (char value in input)
                if (char.IsControl(value) && value != '\n' && value != '\t') return Invalid();
            var split = input.Split('\n');
            if (split.Length > MaximumLines) return Invalid();
            var lines = new List<string>();
            foreach (string original in split)
            {
                if (original.Length > MaximumLineCharacters) return Invalid();
                string line = original.Trim();
                if (line.Length != 0) lines.Add(line);
            }
            if (lines.Count == 0 || lines[0] != Expected[0]) return Invalid();
            if (lines.Count > Expected.Length) return Result(WsabiWmiProtection0To1ReviewStatus.Inconsistent);
            int[] pre = null, post = null;
            for (int i = 0; i < lines.Count; i++)
            {
                if (Expected[i] == PrePrefix || Expected[i] == PostPrefix)
                {
                    int[] tuple;
                    if (!Triple(lines[i], Expected[i], out tuple)) return Invalid();
                    if (Expected[i] == PrePrefix) pre = tuple; else post = tuple;
                    continue;
                }
                if (lines[i] == Expected[i]) continue;
                if (lines[i] == Pending || lines[i].StartsWith("전체 표시 결과: TimedOut", StringComparison.Ordinal) ||
                    lines[i].StartsWith("전체 표시 결과: Cancelled", StringComparison.Ordinal) ||
                    lines[i].StartsWith("전체 표시 결과: CompletionUnknown", StringComparison.Ordinal) ||
                    lines[i] == "시도 결과 확인 불가. 성공으로 해석하지 않고 관련 정리를 기다립니다.")
                    return Result(WsabiWmiProtection0To1ReviewStatus.IncompleteOrFailed);
                return Result(IsKnownField(lines[i]) ? WsabiWmiProtection0To1ReviewStatus.Inconsistent
                    : WsabiWmiProtection0To1ReviewStatus.InvalidInput);
            }
            if (lines.Count != Expected.Length) return Result(WsabiWmiProtection0To1ReviewStatus.IncompleteOrFailed);
            if (pre == null || post == null || pre[0] != 0 || post[0] != 1 || post[1] != 80 || post[2] != 75)
                return Result(WsabiWmiProtection0To1ReviewStatus.Inconsistent);
            return new WsabiWmiProtection0To1Review(WsabiWmiProtection0To1ReviewStatus.ReportedStoredTransitionMatched,
                pre[0], pre[1], pre[2], post[0], post[1], post[2]);
        }

        private static bool IsKnownField(string line)
        {
            int colon = line.IndexOf(':');
            if (colon > 0)
            {
                string prefix = line.Substring(0, colon + 1);
                foreach (string expected in Expected)
                    if (expected.StartsWith(prefix, StringComparison.Ordinal)) return true;
            }
            foreach (string role in new[] { "PreMode", "PreUpper", "PreLower", "SemanticSet1", "PostMode", "PostUpper", "PostLower" })
                if (line.StartsWith(role + " / ", StringComparison.Ordinal)) return true;
            return false;
        }

        private static bool Triple(string line, string prefix, out int[] values)
        {
            values = null;
            if (!line.StartsWith(prefix, StringComparison.Ordinal)) return false;
            string[] parts = line.Substring(prefix.Length).Split(new[] { " / " }, StringSplitOptions.None);
            if (parts.Length != 3) return false;
            var tuple = new int[3];
            for (int i = 0; i < parts.Length; i++)
                if (!int.TryParse(parts[i], NumberStyles.None, CultureInfo.InvariantCulture, out tuple[i]) ||
                    tuple[i] < 0 || tuple[i] > 255 || parts[i] != tuple[i].ToString(CultureInfo.InvariantCulture)) return false;
            values = tuple; return true;
        }

        private static string[] BuildExpected()
        {
            var lines = new List<string> {
                "ATIV Battery Guard — Protection0To1-v1",
                "현재 토큰: Elevated",
                "새 목적의 영속1회 예약: Claimed",
                "CallSabiFunction SDK진입 최대7 / 설정1 최대1 / 읽기 후보 최대6 / 초기화·handshake·재시도·fallback·역방향·복원0",
                "기존 임계값을80/75로 덮어쓸 수 있습니다. 끄기·원복 기능과 재부팅 원복 보장은 없습니다.",
                "실제 충전 제어: Unsupported. 저장 후보 일치는 충전기 적용·전기적 제한 성공이 아닙니다.",
                "사전 검증: Ready / 단계: Ready",
                "열거 세부 단계: None / 오류 범주: None",
                "열거 정리 오류 관측: No",
                "고정7단계 요청 준비: None",
                "고정 시험 준비 완료: 전체 owner 획득2초 / 전체 절차 표시10초 / 실제 종료·정리는 별도 대기.",
                "전체 표시 결과: StoredReadbackMatchedCandidate",
                "owner 획득 판정(표시 시점): Acquired",
                "전이 판정(표시 시점): StoredReadbackMatchedCandidate",
                "역할 입장 수: 7",
                "설정 역할 입장: Yes",
                "SDK 진입 수(표시 시점): 7",
                "설정 SDK 진입 수(표시 시점): 1",
                "마지막 SDK 준비: Ready",
                "단계별 응답 판정(표시 시점):" };
            lines.AddRange(ReadDiagnostic);
            lines.AddRange(new[] {
                "수용 저장 byte 후보 수: 6",
                "전이 모델 수용 읽기 단계 수: 6",
                "설정 응답 수용(ReceiptOnly): Yes",
                "독립 setter 성공 ACK로 판정하지 않습니다.", PrePrefix, PostPrefix,
                "모드1·상한80·하한75의 저장 후보 일치: Yes",
                "숫자 후보 일치는 전체 절차의 성공·충전기 적용·전기적 충전 제한의 증거가 아닙니다.",
                "설정 효과: Unknown. 입력echo·역할입장·SDK진입만으로 실제 변경 성공/미변경을 단정하지 않습니다.",
                "결과 표시는 실제 종료 보장이 아닙니다. 관련 정리가 끝날 때까지 기다립니다.",
                "SDK 진입 수(실제 종료 뒤): 7",
                "설정 SDK 진입 수(실제 종료 뒤): 1",
                "단계별 응답 판정(실제 종료 뒤):" });
            lines.AddRange(ReadDiagnostic);
            lines.AddRange(new[] {
                "SDK 진입은 EC 처리 성공 횟수가 아닙니다.",
                "관련 정리: Complete. 이번 시험 종료. 재실행·예약 변경·추가 호출을 하지 마세요.",
                "기존 앱의 보호 조회/충전 제어 지원은 활성화하지 않습니다. 이 새 TXT만 후속 분석에 사용합니다." });
            return lines.ToArray();
        }

        private static WsabiWmiProtection0To1Review Result(WsabiWmiProtection0To1ReviewStatus status)
            => new WsabiWmiProtection0To1Review(status);
        private static WsabiWmiProtection0To1Review Invalid() => Result(WsabiWmiProtection0To1ReviewStatus.InvalidInput);
    }
}
