using System;
using System.Linq;
using System.Reflection;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiProtection0To1ReviewTests()
    {
        Add("protection transition historical review accepts complete stored transition without promoting hardware or electrical success", () =>
        {
            var review = WsabiWmiProtection0To1ReviewParser.Parse(Protection0To1ReviewFixture());
            Equal(WsabiWmiProtection0To1ReviewStatus.ReportedStoredTransitionMatched, review.Status);
            Check(review.HasReportedStoredTransition, "reported transition omitted");
            Equal<int?>(0, review.PreMode); Equal<int?>(0, review.PreUpper); Equal<int?>(0, review.PreLower);
            Equal<int?>(1, review.PostMode); Equal<int?>(80, review.PostUpper); Equal<int?>(75, review.PostLower);
            Equal<int?>(7, review.SdkEntries); Equal<int?>(1, review.SetterEntries); Equal<int?>(6, review.ReadCandidateCount);
            Protection0To1ReviewNoHardware(review);
            string text = review.ToDisplayText();
            Check(text.Contains("로그의 형식·상태 조합") && text.Contains("저장 후보 전환 일치") &&
                text.Contains("현재 actualMode") && text.Contains("독립 재검증도 아닙니다") &&
                text.Contains("전기적 충전 제한은 여전히 미검증"), "historical record became an authenticated current charge limit");
        });

        Add("protection transition historical pre thresholds are arbitrary bounded baselines including inverted values", () =>
        {
            foreach (var pair in new[] { new[] { 255, 0 }, new[] { 0, 255 }, new[] { 90, 10 }, new[] { 75, 80 }, new[] { 80, 75 } })
            {
                var result = WsabiWmiProtection0To1ReviewParser.Parse(Protection0To1ReviewFixture(pair[0], pair[1]));
                Check(result.HasReportedStoredTransition, "valid baseline was constrained to old expected thresholds");
                Equal<int?>(pair[0], result.PreUpper); Equal<int?>(pair[1], result.PreLower);
                Equal<int?>(80, result.PostUpper); Equal<int?>(75, result.PostLower); Protection0To1ReviewNoHardware(result);
            }
        });

        Add("protection transition historical review requires every fixed line and refuses every duplicate", () =>
        {
            string[] lines = Protection0To1ReviewFixture().Split('\n');
            for (int index = 0; index < lines.Length; index++)
            {
                Protection0To1ReviewNoCandidate(string.Join("\n", lines.Where((line, row) => row != index)));
                var duplicate = lines.ToList(); duplicate.Insert(index, lines[index]);
                Protection0To1ReviewNoCandidate(string.Join("\n", duplicate));
            }
        });

        Add("protection transition historical review rejects reordered fields and swapped diagnostic blocks", () =>
        {
            var lines = Protection0To1ReviewFixture().Split('\n');
            for (int index = 0; index < lines.Length - 1; index++)
            {
                var swapped = (string[])lines.Clone(); string first = swapped[index]; swapped[index] = swapped[index + 1]; swapped[index + 1] = first;
                Protection0To1ReviewNoCandidate(string.Join("\n", swapped));
            }
            string valid = Protection0To1ReviewFixture();
            Protection0To1ReviewNoCandidate(valid.Replace("단계별 응답 판정(표시 시점):", "단계별 응답 판정(실제 종료 뒤):"));
            Protection0To1ReviewNoCandidate(valid.Replace("단계별 응답 판정(실제 종료 뒤):", "단계별 응답 판정(표시 시점):"));
        });

        Add("protection transition historical review refuses mismatching status counts and missing strict preflight proof", () =>
        {
            string valid = Protection0To1ReviewFixture();
            foreach (var pair in new[] {
                new[] { "현재 토큰: Elevated", "현재 토큰: NotElevated" },
                new[] { "새 목적의 영속1회 예약: Claimed", "새 목적의 영속1회 예약: AlreadyUsed" },
                new[] { "사전 검증: Ready / 단계: Ready", "사전 검증: AccessDenied / 단계: MethodEnumeration" },
                new[] { "열거 세부 단계: None / 오류 범주: None", "열거 세부 단계: MoveNext / 오류 범주: WmiAccessDenied" },
                new[] { "열거 정리 오류 관측: No", "열거 정리 오류 관측: Yes" },
                new[] { "고정7단계 요청 준비: None", "고정7단계 요청 준비: ZeroComparisonContent" },
                new[] { "owner 획득 판정(표시 시점): Acquired", "owner 획득 판정(표시 시점): Abandoned" },
                new[] { "전이 판정(표시 시점): StoredReadbackMatchedCandidate", "전이 판정(표시 시점): PostUpperMismatch" },
                new[] { "역할 입장 수: 7", "역할 입장 수: 6" }, new[] { "설정 역할 입장: Yes", "설정 역할 입장: No" },
                new[] { "SDK 진입 수(표시 시점): 7", "SDK 진입 수(표시 시점): 6" },
                new[] { "설정 SDK 진입 수(표시 시점): 1", "설정 SDK 진입 수(표시 시점): 0" },
                new[] { "SDK 진입 수(실제 종료 뒤): 7", "SDK 진입 수(실제 종료 뒤): 8" },
                new[] { "설정 SDK 진입 수(실제 종료 뒤): 1", "설정 SDK 진입 수(실제 종료 뒤): 2" },
                new[] { "수용 저장 byte 후보 수: 6", "수용 저장 byte 후보 수: 5" },
                new[] { "전이 모델 수용 읽기 단계 수: 6", "전이 모델 수용 읽기 단계 수: 5" },
                new[] { "설정 응답 수용(ReceiptOnly): Yes", "설정 응답 수용(ReceiptOnly): No" },
                new[] { "마지막 SDK 준비: Ready", "마지막 SDK 준비: InputRejected" },
                new[] { "모드1·상한80·하한75의 저장 후보 일치: Yes", "모드1·상한80·하한75의 저장 후보 일치: No" } })
                Protection0To1ReviewNoCandidate(valid.Replace(pair[0], pair[1]));
        });

        Add("protection transition historical review requires each role and exact strict read or receipt verdict in both blocks", () =>
        {
            string[] lines = Protection0To1ReviewFixture().Split('\n');
            for (int index = 0; index < lines.Length; index++)
            {
                if (!lines[index].Contains(" / binding=")) continue;
                var changed = (string[])lines.Clone();
                changed[index] = changed[index].Contains("binding=ReceiptOnly")
                    ? changed[index].Replace("setter=ReceiptOnly", "setter=ReceiptRejected")
                    : changed[index].Replace("read=CorrelatedStoredByteCandidate", "read=AmbiguousInputEcho");
                Protection0To1ReviewNoCandidate(string.Join("\n", changed));
                changed[index] = lines[index].Replace("binding=ReadCandidate", "binding=ReadRejected").Replace("binding=ReceiptOnly", "binding=ReceiptRejected");
                Protection0To1ReviewNoCandidate(string.Join("\n", changed));
            }
        });

        Add("protection transition historical candidates require canonical byte syntax pre mode zero and exact post one eighty seventy five", () =>
        {
            string valid = Protection0To1ReviewFixture();
            foreach (string pre in new[] { "1 / 0 / 0", "255 / 0 / 0", "0 / 256 / 0", "0 / -1 / 0", "0 / 00 / 0", "0/0/0", "0 / 未観測 / 0", "0 / 0 / 0 / 0" })
                Protection0To1ReviewNoCandidate(valid.Replace("사전 모드/상한/하한 후보: 0 / 0 / 0", "사전 모드/상한/하한 후보: " + pre));
            foreach (string post in new[] { "0 / 80 / 75", "1 / 79 / 75", "1 / 80 / 74", "1 / 80 / 076", "01 / 80 / 75", "1 / 80 / 미관측" })
                Protection0To1ReviewNoCandidate(valid.Replace("사후 모드/상한/하한 후보: 1 / 80 / 75", "사후 모드/상한/하한 후보: " + post));
        });

        Add("protection transition historical pending stopped and failed outcomes cannot be overwritten by later numeric or complete text", () =>
        {
            string valid = Protection0To1ReviewFixture();
            foreach (string status in new[] { "TimedOut", "Cancelled", "CompletionUnknown", "CleanupFailed", "StageRejected", "GateRejected" })
                Protection0To1ReviewNoCandidate(valid.Replace("전체 표시 결과: StoredReadbackMatchedCandidate", "전체 표시 결과: " + status));
            const string pending = "관련 종료·정리 확인 불가: Pending. 참조와 수명을 유지하며 추가 해제·호출·재시도 없이 기다립니다.";
            string complete = "관련 정리: Complete. 이번 시험 종료. 재실행·예약 변경·추가 호출을 하지 마세요.";
            Protection0To1ReviewNoCandidate(valid.Replace(complete, pending));
            Protection0To1ReviewNoCandidate(valid + "\n" + pending);
            Protection0To1ReviewNoCandidate(valid.Replace(complete, pending + "\n" + complete));
            Protection0To1ReviewNoCandidate(valid.Replace(complete, "시도 결과 확인 불가. 성공으로 해석하지 않고 관련 정리를 기다립니다.\n" + complete));
            foreach (int count in new[] { 1, 11, 20, 37, 49 })
                Protection0To1ReviewNoCandidate(string.Join("\n", valid.Split('\n').Take(count)));
        });

        Add("protection transition historical review bounds purpose bytes lines controls and ignores no unknown warning or private text", () =>
        {
            string valid = Protection0To1ReviewFixture();
            foreach (string text in new[] { null, "", " ", valid.Replace("Protection0To1-v1", "Protection0To1-v2"),
                valid.Replace("현재 토큰: Elevated", "현재 토큰: elevated"), valid.Replace("현재 토큰: Elevated", "현재 토큰: 2"),
                valid + "\nPRIVATE-PATH-ACCOUNT-ID", valid.Replace("현재 토큰:", "PRIVATE-PATH-ACCOUNT-ID\n현재 토큰:"),
                valid + "\0", valid.Replace("\n", "\r"), new string('a', WsabiWmiProtection0To1ReviewParser.MaximumCharacters + 1),
                valid + new string('\n', WsabiWmiProtection0To1ReviewParser.MaximumLines + 1),
                valid + "\n" + new string('x', WsabiWmiProtection0To1ReviewParser.MaximumLineCharacters + 1) })
            {
                var result = WsabiWmiProtection0To1ReviewParser.Parse(text);
                Check(!result.HasReportedStoredTransition && !result.ToDisplayText().Contains("PRIVATE-PATH-ACCOUNT-ID"), "untrusted raw text escaped its parse scope");
                Protection0To1ReviewNoHardware(result);
            }
        });

        Add("protection transition historical review accepts CRLF BOM and blank formatting without loosening fixed field values", () =>
        {
            string valid = Protection0To1ReviewFixture();
            foreach (string text in new[] { "\uFEFF" + valid.Replace("\n", "\r\n") + "\r\n", "\n\n" + valid + "\n\n",
                string.Join("\n", valid.Split('\n').Select(line => "  " + line + "  ")) })
                Check(WsabiWmiProtection0To1ReviewParser.Parse(text).HasReportedStoredTransition, "supported formatting lost its complete record");
            Protection0To1ReviewNoCandidate(valid.Replace("SDK 진입 수(표시 시점): 7", "SDK 진입 수(표시 시점): 07"));
        });

        Add("protection transition historical generic unknown effect line is required but does not erase independent stored comparison", () =>
        {
            const string note = "설정 효과: Unknown. 입력echo·역할입장·SDK진입만으로 실제 변경 성공/미변경을 단정하지 않습니다.";
            string valid = Protection0To1ReviewFixture();
            var review = WsabiWmiProtection0To1ReviewParser.Parse(valid);
            Check(review.HasReportedStoredTransition && review.ToDisplayText().Contains("저장 후보 비교 일치를 취소하지 않습니다"), "generic message erased stored transition evidence");
            Protection0To1ReviewNoCandidate(valid.Replace(note + "\n", ""));
            Protection0To1ReviewNoCandidate(valid.Replace(note, "설정 효과: Confirmed. 충전 제한 성공"));
        });

        Add("protection transition historical model keeps only immutable sanitized scalars and never supplies execution authority", () =>
        {
            var type = typeof(WsabiWmiProtection0To1Review);
            Check(type.IsSealed && type.GetConstructors().Length == 0, "historical model has public mutable construction");
            foreach (var property in type.GetProperties(BindingFlags.Instance | BindingFlags.Public))
                Check(!property.CanWrite && (property.PropertyType.IsEnum || property.PropertyType == typeof(bool) || property.PropertyType == typeof(int?)),
                    "historical model retained raw or mutable data");
            var old = WsabiWmiProtection0To1ReviewParser.Parse(Protection0To1ReviewFixture());
            var failed = WsabiWmiProtection0To1ReviewParser.Parse("PRIVATE-PATH-ACCOUNT-ID");
            Check(old.HasReportedStoredTransition && !failed.HasReportedStoredTransition, "a later parse mutated earlier results");
            Equal(WsabiWmiProtection0To1ReviewStatus.NotLoaded, WsabiWmiProtection0To1Review.Empty.Status);
            Protection0To1ReviewNoHardware(old); Protection0To1ReviewNoHardware(failed); Protection0To1ReviewNoHardware(WsabiWmiProtection0To1Review.Empty);
        });
    }

    private static void Protection0To1ReviewNoCandidate(string input)
    {
        var review = WsabiWmiProtection0To1ReviewParser.Parse(input);
        Check(!review.HasReportedStoredTransition && review.PreMode == null && review.PreUpper == null && review.PreLower == null &&
            review.PostMode == null && review.PostUpper == null && review.PostLower == null && review.SdkEntries == null &&
            review.SetterEntries == null && review.ReadCandidateCount == null, "rejected or partial text retained a successful tuple");
        Protection0To1ReviewNoHardware(review);
    }

    private static void Protection0To1ReviewNoHardware(WsabiWmiProtection0To1Review review)
        => Check(!review.IsHardwareObservation && !review.IsChargeLimitConfirmed && !review.CanReadHardware &&
            !review.CanWriteHardware && !review.CanInvokeMethods, "text classification granted hardware authority");

    private static string Protection0To1ReviewFixture(int preUpper = 0, int preLower = 0)
    {
        // Independent fixed-format historical output fixture, without a file
        // name, actual timestamp, device ID, frame or comparison byte content.
        string[] stages = {
            "PreMode / binding=ReadCandidate / read=CorrelatedStoredByteCandidate / setter=NotReviewed",
            "PreUpper / binding=ReadCandidate / read=CorrelatedStoredByteCandidate / setter=NotReviewed",
            "PreLower / binding=ReadCandidate / read=CorrelatedStoredByteCandidate / setter=NotReviewed",
            "SemanticSet1 / binding=ReceiptOnly / read=NotReviewed / setter=ReceiptOnly",
            "PostMode / binding=ReadCandidate / read=CorrelatedStoredByteCandidate / setter=NotReviewed",
            "PostUpper / binding=ReadCandidate / read=CorrelatedStoredByteCandidate / setter=NotReviewed",
            "PostLower / binding=ReadCandidate / read=CorrelatedStoredByteCandidate / setter=NotReviewed" };
        var rows = new System.Collections.Generic.List<string> {
            "ATIV Battery Guard — Protection0To1-v1", "현재 토큰: Elevated", "새 목적의 영속1회 예약: Claimed",
            "CallSabiFunction SDK진입 최대7 / 설정1 최대1 / 읽기 후보 최대6 / 초기화·handshake·재시도·fallback·역방향·복원0",
            "기존 임계값을80/75로 덮어쓸 수 있습니다. 끄기·원복 기능과 재부팅 원복 보장은 없습니다.",
            "실제 충전 제어: Unsupported. 저장 후보 일치는 충전기 적용·전기적 제한 성공이 아닙니다.",
            "사전 검증: Ready / 단계: Ready", "열거 세부 단계: None / 오류 범주: None", "열거 정리 오류 관측: No",
            "고정7단계 요청 준비: None", "고정 시험 준비 완료: 전체 owner 획득2초 / 전체 절차 표시10초 / 실제 종료·정리는 별도 대기.",
            "전체 표시 결과: StoredReadbackMatchedCandidate", "owner 획득 판정(표시 시점): Acquired",
            "전이 판정(표시 시점): StoredReadbackMatchedCandidate", "역할 입장 수: 7", "설정 역할 입장: Yes",
            "SDK 진입 수(표시 시점): 7", "설정 SDK 진입 수(표시 시점): 1", "마지막 SDK 준비: Ready",
            "단계별 응답 판정(표시 시점):" };
        rows.AddRange(stages);
        rows.AddRange(new[] {
            "수용 저장 byte 후보 수: 6", "전이 모델 수용 읽기 단계 수: 6", "설정 응답 수용(ReceiptOnly): Yes",
            "독립 setter 성공 ACK로 판정하지 않습니다.",
            "사전 모드/상한/하한 후보: 0 / " + preUpper.ToString(System.Globalization.CultureInfo.InvariantCulture) + " / " + preLower.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "사후 모드/상한/하한 후보: 1 / 80 / 75", "모드1·상한80·하한75의 저장 후보 일치: Yes",
            "숫자 후보 일치는 전체 절차의 성공·충전기 적용·전기적 충전 제한의 증거가 아닙니다.",
            "설정 효과: Unknown. 입력echo·역할입장·SDK진입만으로 실제 변경 성공/미변경을 단정하지 않습니다.",
            "결과 표시는 실제 종료 보장이 아닙니다. 관련 정리가 끝날 때까지 기다립니다.",
            "SDK 진입 수(실제 종료 뒤): 7", "설정 SDK 진입 수(실제 종료 뒤): 1", "단계별 응답 판정(실제 종료 뒤):" });
        rows.AddRange(stages);
        rows.AddRange(new[] { "SDK 진입은 EC 처리 성공 횟수가 아닙니다.",
            "관련 정리: Complete. 이번 시험 종료. 재실행·예약 변경·추가 호출을 하지 마세요.",
            "기존 앱의 보호 조회/충전 제어 지원은 활성화하지 않습니다. 이 새 TXT만 후속 분석에 사용합니다." });
        return string.Join("\n", rows);
    }
}
