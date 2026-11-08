using System;
using System.Linq;
using System.Reflection;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiFixedReadAccess1ReviewTests()
    {
        Add("Access1 offline review recognizes reported zero and one only after the complete fixed tuple", () =>
        {
            foreach (int candidate in new[] { 0, 1 })
            {
                var review = WsabiWmiFixedReadAccess1ReviewParser.Parse(FixedReadAccess1ReviewFixture(candidate));
                Equal(WsabiWmiFixedReadAccess1ReviewStatus.ReportedStoredModeCandidate, review.Status);
                Equal<int?>(candidate, review.StoredModeCandidate); Check(review.HasReportedStoredModeCandidate, "reported candidate omitted");
                FixedReadReviewAssertNoHardware(review);
                string text = review.ToDisplayText();
                Check(text.Contains("로그의 형식·상태 조합") && text.Contains("다시 검증한 결과는 아닙니다") &&
                    text.Contains("배터리 보호 상태: 알 수 없음") && text.Contains("임계값·80% 충전 제한 적용"), "log became a live protection observation");
            }
        });

        Add("Access1 review rejects every missing or duplicated required field and wrong field order", () =>
        {
            var lines = FixedReadAccess1ReviewFixture().Split('\n');
            foreach (int index in Enumerable.Range(0, 17).Concat(new[] { 18 }))
            {
                FixedReadReviewAssertNoCandidate(string.Join("\n", lines.Where((line, row) => row != index)));
                var duplicate = lines.ToList(); duplicate.Insert(index, lines[index]);
                Equal(WsabiWmiFixedReadAccess1ReviewStatus.InvalidInput,
                    WsabiWmiFixedReadAccess1ReviewParser.Parse(string.Join("\n", duplicate)).Status);
            }
            var reversed = (string[])lines.Clone();
            string temporary = reversed[15]; reversed[15] = reversed[16]; reversed[16] = temporary;
            FixedReadReviewAssertNoCandidate(string.Join("\n", reversed));
            var premature = lines.ToList(); premature.RemoveAt(18); premature.Insert(14, lines[18]);
            Equal(WsabiWmiFixedReadAccess1ReviewStatus.Inconsistent,
                WsabiWmiFixedReadAccess1ReviewParser.Parse(string.Join("\n", premature)).Status);
        });

        Add("Access1 review rejects other purposes numeric enums case coercion and invalid candidate syntax", () =>
        {
            string valid = FixedReadAccess1ReviewFixture();
            foreach (var mutation in new[] {
                new[] { "FixedModeReadA-Access1", "FixedModeReadA-v1" }, new[] { "FixedModeReadA-Access1", "FixedModeReadA-Access2" },
                new[] { "현재 토큰: Elevated", "현재 토큰: 2" }, new[] { "현재 토큰: Elevated", "현재 토큰: elevated" },
                new[] { "새 목적의 영속 1회 예약: Claimed", "새 목적의 영속 1회 예약: 0" },
                new[] { "SDK 준비: Ready", "SDK 준비: Ready, PreparationNotReady" },
                new[] { "고정 요청 준비: Created", "고정 요청 준비: true" }, new[] { "교환 상태: ReplyReceived", "교환 상태: 0" },
                new[] { "저장 모드 후보: 0", "저장 모드 후보: 00" }, new[] { "저장 모드 후보: 0", "저장 모드 후보: FF" },
                new[] { "저장 모드 후보: 0", "저장 모드 후보: -1" }, new[] { "저장 모드 후보: 0", "저장 모드 후보: 2" },
                new[] { "관련 정리: Complete.", "관련 정리: Failed." } })
                FixedReadReviewAssertNoCandidate(valid.Replace(mutation[0], mutation[1]));
        });

        Add("Access1 review discards plausible candidates with contradictory preparation exchange or cleanup records", () =>
        {
            string valid = FixedReadAccess1ReviewFixture();
            foreach (var mutation in new[] {
                new[] { "현재 토큰: Elevated", "현재 토큰: NotElevated" },
                new[] { "새 목적의 영속 1회 예약: Claimed", "새 목적의 영속 1회 예약: AlreadyUsed" },
                new[] { "사전 검증: Ready / 단계: Ready", "사전 검증: AccessDenied / 단계: MethodEnumeration" },
                new[] { "사전 검증: Ready / 단계: Ready", "사전 검증: Ready / 단계: ModelRead" },
                new[] { "열거 세부 단계: None / 오류 범주: None", "열거 세부 단계: QueryGet / 오류 범주: WmiAccessDenied" },
                new[] { "열거 정리 오류 관측: No", "열거 정리 오류 관측: Yes" },
                new[] { "SDK 준비: Ready", "SDK 준비: PreparationNotReady" }, new[] { "대상 연결: Ready", "대상 연결: NotConnected" },
                new[] { "등록: Ready", "등록: Cancelled" }, new[] { "입력: Populated", "입력: ShapeMismatch" },
                new[] { "교환 상태: ReplyReceived", "교환 상태: TimedOut" },
                new[] { "조회 판정: StoredModeCandidate", "조회 판정: DispatchFailurePrefix" },
                new[] { "저장 모드 후보: 0", "저장 모드 후보: 미관측" } })
                FixedReadReviewAssertNoCandidate(valid.Replace(mutation[0], mutation[1]));
            FixedReadReviewAssertNoCandidate(valid.Replace("교환 상태:",
                "호출 없음. 이번 시험은 종료하며 재시도하지 않습니다.\n교환 상태:"));
        });

        Add("Access1 review preserves terminal failure tuples without a stored candidate", () =>
        {
            foreach (var pair in new[] {
                new[] { "InvalidRequest", "ExchangeInvalidRequest" }, new[] { "Cancelled", "ExchangeCancelled" },
                new[] { "Busy", "ExchangeBusy" }, new[] { "TimedOut", "ExchangeTimedOut" },
                new[] { "TransportFailure", "ExchangeTransportFailure" }, new[] { "ReplyReceived", "DispatchFailurePrefix" },
                new[] { "ReplyReceived", "FrameRejected" }, new[] { "ReplyReceived", "PreservedContentMismatch" } })
            {
                string text = FixedReadAccess1ReviewFixture().Replace("교환 상태: ReplyReceived", "교환 상태: " + pair[0])
                    .Replace("조회 판정: StoredModeCandidate", "조회 판정: " + pair[1])
                    .Replace("저장 모드 후보: 0", "저장 모드 후보: 미관측");
                var review = WsabiWmiFixedReadAccess1ReviewParser.Parse(text);
                Equal(WsabiWmiFixedReadAccess1ReviewStatus.NoReportedCandidate, review.Status);
                FixedReadReviewAssertNoHardware(review); Equal<int?>(null, review.StoredModeCandidate);
            }
        });

        Add("Access1 explicit pending discards earlier candidate and conflicts with any complete record", () =>
        {
            string valid = FixedReadAccess1ReviewFixture();
            const string complete = "관련 정리: Complete. 이번 시험 종료. 재시도하지 마세요.";
            const string pending = "관련 종료·소유권 확인 불가: Pending. 관련 참조를 유지하고 추가 해제·새 호출·강제 종료·재시도 없이 기다립니다.";
            string text = valid.Replace(complete, pending);
            var review = WsabiWmiFixedReadAccess1ReviewParser.Parse(text);
            Equal(WsabiWmiFixedReadAccess1ReviewStatus.CompletionPending, review.Status);
            Equal<int?>(null, review.StoredModeCandidate); FixedReadReviewAssertNoHardware(review);
            Equal(WsabiWmiFixedReadAccess1ReviewStatus.Inconsistent,
                WsabiWmiFixedReadAccess1ReviewParser.Parse(text + "\n" + complete).Status);
            Equal(WsabiWmiFixedReadAccess1ReviewStatus.Inconsistent,
                WsabiWmiFixedReadAccess1ReviewParser.Parse(valid + "\n" + pending).Status);
            var beforeResult = string.Join("\n", valid.Split('\n').Take(14)) + "\n" + pending;
            Equal(WsabiWmiFixedReadAccess1ReviewStatus.CompletionPending,
                WsabiWmiFixedReadAccess1ReviewParser.Parse(beforeResult).Status);
        });

        Add("Access1 run failure warning cannot be hidden by a later complete record or a candidate", () =>
        {
            const string warning = "시도 결과 확인 불가. 성공으로 해석하지 않고 관련 정리를 기다립니다.";
            string valid = FixedReadAccess1ReviewFixture();
            var review = WsabiWmiFixedReadAccess1ReviewParser.Parse(valid.Replace("관련 정리:", warning + "\n관련 정리:"));
            Equal(WsabiWmiFixedReadAccess1ReviewStatus.NoReportedCandidate, review.Status);
            Equal<int?>(null, review.StoredModeCandidate);
            FixedReadReviewAssertNoCandidate(valid + "\nCallCanceled");
            FixedReadReviewAssertNoCandidate(valid + "\n" + warning + "\n" + warning);
        });

        Add("Access1 complete preflight creation and registration failures remain noncandidate reports", () =>
        {
            string[] lines = FixedReadAccess1ReviewFixture().Split('\n');
            string denied = string.Join("\n", lines.Take(8)).Replace("사전 검증: Ready / 단계: Ready", "사전 검증: AccessDenied / 단계: MethodEnumeration")
                .Replace("열거 세부 단계: None / 오류 범주: None", "열거 세부 단계: MoveNext / 오류 범주: WmiAccessDenied")
                + "\n호출 없음. 이번 시험은 종료하며 재시도하지 않습니다.";
            string creation = string.Join("\n", lines.Take(9)).Replace("고정 요청 준비: Created", "고정 요청 준비: ZeroComparisonContent")
                + "\n호출 전 중단. 비교 내용·원문 요청은 기록하지 않습니다. 재시도 없음.";
            string registration = string.Join("\n", lines.Take(13)).Replace("SDK 준비: Ready", "SDK 준비: PreparationNotReady")
                .Replace("등록: Ready", "등록: RegistrationFailed")
                + "\nWMI method 호출 없음. 준비 종료. 이번 시험을 반복하지 마세요.";
            foreach (string text in new[] { denied, creation, registration })
            {
                var review = WsabiWmiFixedReadAccess1ReviewParser.Parse(text);
                Equal(WsabiWmiFixedReadAccess1ReviewStatus.NoReportedCandidate, review.Status);
                Equal<int?>(null, review.StoredModeCandidate); FixedReadReviewAssertNoHardware(review);
            }
        });

        Add("Access1 truncated success never becomes a candidate or an invented completed cleanup", () =>
        {
            string[] lines = FixedReadAccess1ReviewFixture().Split('\n');
            for (int count = 0; count < 19; count++)
                FixedReadReviewAssertNoCandidate(string.Join("\n", lines.Take(count)));
        });

        Add("Access1 bounded BOM and CRLF are accepted while oversized control or unknown records are rejected", () =>
        {
            string valid = FixedReadAccess1ReviewFixture();
            foreach (string text in new[] { valid, valid.Replace("\n", "\r\n"), "\uFEFF" + valid.Replace("\n", "\r\n") + "\r\n" })
                Check(WsabiWmiFixedReadAccess1ReviewParser.Parse(text).HasReportedStoredModeCandidate, "supported newline changed classification");
            foreach (string text in new[] { null, "", " ", new string('x', 8193), valid + "\n" + new string('x', 513),
                valid + new string('\n', 65), valid + "\0", valid + "\r", valid + "\u0001", valid + "\nUnknown status record" })
                FixedReadReviewAssertNoCandidate(text);
            string withNotice = valid.Replace("SDK 준비:", "SDK 준비 표시 시간 초과: 소유권과 실제 준비 종료를 기다립니다. 강제 종료·재시도 없음.\nSDK 준비:");
            Check(WsabiWmiFixedReadAccess1ReviewParser.Parse(withNotice).HasReportedStoredModeCandidate,
                "display notice alone replaced applicable final records");
        });

        Add("Access1 review stores immutable classifications only and never echoes private input", () =>
        {
            var review = WsabiWmiFixedReadAccess1ReviewParser.Parse(FixedReadAccess1ReviewFixture()
                + "\nPRIVATE-NAME C:\\Users\\PRIVATE-NAME\\result.txt S-1-5-21-PRIVATE raw-frame nonce");
            Equal(WsabiWmiFixedReadAccess1ReviewStatus.InvalidInput, review.Status);
            Check(!review.ToDisplayText().Contains("PRIVATE-NAME") && !review.ToDisplayText().Contains("S-1-5-21"), "private input retained");
            Type type = typeof(WsabiWmiFixedReadAccess1Review); Equal(0, type.GetConstructors().Length);
            foreach (var property in type.GetProperties()) Check(!property.CanWrite, "review publicly mutable");
            foreach (var field in type.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
                Check(field.IsInitOnly && (field.FieldType.IsEnum || field.FieldType == typeof(int?)), "review retained raw text or mutable state");
            Equal(WsabiWmiFixedReadAccess1ReviewStatus.NotLoaded, WsabiWmiFixedReadAccess1Review.Empty.Status);
            Equal<int?>(null, WsabiWmiFixedReadAccess1Review.Empty.StoredModeCandidate);
            FixedReadReviewAssertNoHardware(WsabiWmiFixedReadAccess1Review.Empty);
            foreach (var malformed in new[] {
                new WsabiWmiFixedReadAccess1Review(WsabiWmiFixedReadAccess1ReviewStatus.ReportedStoredModeCandidate),
                new WsabiWmiFixedReadAccess1Review(WsabiWmiFixedReadAccess1ReviewStatus.ReportedStoredModeCandidate, 2),
                new WsabiWmiFixedReadAccess1Review(WsabiWmiFixedReadAccess1ReviewStatus.CompletionPending, 0) })
                FixedReadReviewAssertNoHardware(malformed);
        });

        Add("Access1 and Query65 review formats remain separate", () =>
        {
            Equal(WsabiWmiExperimentReviewStatus.InvalidInput,
                WsabiWmiExperimentReviewParser.Parse(FixedReadAccess1ReviewFixture()).Status);
            Equal(WsabiWmiFixedReadAccess1ReviewStatus.InvalidInput,
                WsabiWmiFixedReadAccess1ReviewParser.Parse(ExperimentReviewFixture(0xff)).Status);
        });
    }

    private static string FixedReadAccess1ReviewFixture(int candidate = 0)
        => "ATIV Battery Guard — FixedModeReadA-Access1\n현재 토큰: Elevated\n새 목적의 영속 1회 예약: Claimed\n"
        + "method 최대1 / 저장 byte 샘플0~1 / 초기화·handshake·재시도·설정 변경·fallback 각각0\n"
        + "실제 충전 제어: Unsupported. 저장 후보는 실제 충전 제한 적용이나 임계값의 증거가 아닙니다.\n"
        + "사전 검증: Ready / 단계: Ready\n열거 세부 단계: None / 오류 범주: None\n열거 정리 오류 관측: No\n"
        + "고정 요청 준비: Created\nSDK 준비: Ready\n대상 연결: Ready\n등록: Ready\n입력: Populated\n"
        + "고정 시도 준비 완료: owner 획득 최대2초 / 응답 표시10초 / 실제 종료·정리는 별도 대기.\n"
        + "교환 상태: ReplyReceived\n조회 판정: StoredModeCandidate\n저장 모드 후보: " + candidate + "\n"
        + "결과 표시는 실제 종료 보장이 아닙니다. 관련 정리 완료를 기다립니다.\n"
        + "관련 정리: Complete. 이번 시험 종료. 재시도하지 마세요.\n"
        + "실제 보호 조회/충전 제어 지원은 활성화하지 않습니다. 원문 frame·비교 내용·경로·고유 ID는 기록하지 않습니다.";

    private static void FixedReadReviewAssertNoCandidate(string text)
    {
        var review = WsabiWmiFixedReadAccess1ReviewParser.Parse(text);
        Check(!review.HasReportedStoredModeCandidate && !review.StoredModeCandidate.HasValue, "invalid or incomplete log retained a candidate");
        FixedReadReviewAssertNoHardware(review);
    }

    private static void FixedReadReviewAssertNoHardware(WsabiWmiFixedReadAccess1Review review)
        => Check(!review.IsHardwareObservation && !review.IsChargeLimitConfirmed && !review.CanInvokeMethods &&
            !review.CanReadHardware && !review.CanWriteHardware, "offline log granted hardware authority");
}
