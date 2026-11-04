using System;
using System.Linq;
using System.Reflection;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiExperimentReviewTests()
    {
        Add("offline experiment review keeps zero one FF and other markers opaque and cannot authorize hardware", () =>
        {
            byte[] bytes = { 0, 1, 0xff, 0x34 };
            WsabiWmiCandidateMarker[] markers = { WsabiWmiCandidateMarker.Zero, WsabiWmiCandidateMarker.One,
                WsabiWmiCandidateMarker.FF, WsabiWmiCandidateMarker.Other };
            for (int index = 0; index < bytes.Length; index++)
            {
                var review = WsabiWmiExperimentReviewParser.Parse(ExperimentReviewFixture(bytes[index]));
                Equal(WsabiWmiExperimentReviewStatus.ValidatedFrameMeaningUnknown, review.Status);
                Equal(markers[index], review.Marker); Equal<bool?>(true, review.InvocationRequested);
                Check(review.HasValidatedFrame, "synthetic validated frame was not recognized");
                ExperimentReviewAssertNoHardware(review);
                string display = review.ToDisplayText();
                Check(display.Contains("배터리 보호 상태: 알 수 없음") && display.Contains("의미 미확정")
                    && display.Contains("FF와 0/1은 보호 OFF/ON 또는 기능 미지원 판정이 아닙니다."),
                    "opaque marker was given a protection meaning");
            }
        });
        Add("offline experiment review requires the entire fixed report and rejects missing or repeated required fields", () =>
        {
            string valid = ExperimentReviewFixture(0xff);
            string[] fields = { "수정판:", "ATIV Battery Guard", "범위:", "현재 토큰:", "결과:", "사전 검증:",
                "사전 검증 단계:", "OEM 호출 요청:", "메서드 응답 판정:", "프레임 판정:", "후보 표식:" };
            foreach (string prefix in fields)
            {
                string[] lines = valid.Split('\n');
                string field = lines.Single(line => line.StartsWith(prefix, StringComparison.Ordinal));
                string omitted = string.Join("\n", lines.Where(line => line != field));
                ExperimentReviewAssertRejected(omitted, WsabiWmiExperimentReviewStatus.InvalidInput);
                ExperimentReviewAssertRejected(valid + "\n" + field, WsabiWmiExperimentReviewStatus.InvalidInput);
            }
        });
        Add("offline experiment review rejects different revisions scopes numeric enums and unknown enum combinations", () =>
        {
            string valid = ExperimentReviewFixture(0xff);
            foreach (var change in new[] {
                new[] { "Query65-locator-v2", "Query65-locator-v3" },
                new[] { "고정 후보 0x65", "고정 후보 0x66" },
                new[] { "현재 토큰: Elevated", "현재 토큰: 2" },
                new[] { "(ResponseReceived)", "(9)" },
                new[] { "(Complete)", "(0)" },
                new[] { "(Ready)", "(999)" },
                new[] { "메서드 응답 판정: FrameChecked", "메서드 응답 판정: 7" },
                new[] { "프레임 판정: ValidFrame", "프레임 판정: ValidFrame, ApiNotSuccessful" },
                new[] { "후보 표식: FF", "후보 표식: 255" } })
            {
                Check(valid.Contains(change[0]), "fixture mutation target absent");
                ExperimentReviewAssertRejected(valid.Replace(change[0], change[1]), WsabiWmiExperimentReviewStatus.InvalidInput);
            }
        });
        Add("offline experiment review discards contradictory requests preflights replies and markers", () =>
        {
            string valid = ExperimentReviewFixture(0xff);
            foreach (var change in new[] {
                new[] { "OEM 호출 요청: 요청됨", "OEM 호출 요청: 없음" },
                new[] { "현재 토큰: Elevated", "현재 토큰: NotElevated" },
                new[] { "(Complete)", "(Partial)" },
                new[] { "(Ready)", "(Unknown)" },
                new[] { "(ResponseReceived)", "(PreflightFailed)" },
                new[] { "(ResponseReceived)", "(TransportFailure)" },
                new[] { "메서드 응답 판정: FrameChecked", "메서드 응답 판정: MissingOutput" },
                new[] { "메서드 응답 판정: FrameChecked", "메서드 응답 판정: 미관측" },
                new[] { "프레임 판정: ValidFrame", "프레임 판정: InvalidAcknowledgement" },
                new[] { "후보 표식: FF", "후보 표식: 미관측" } })
            {
                Check(valid.Contains(change[0]), "fixture mutation target absent");
                ExperimentReviewAssertRejected(valid.Replace(change[0], change[1]), WsabiWmiExperimentReviewStatus.Inconsistent);
            }
        });
        Add("offline experiment review preserves negative complete reports without upgrading absent rejected or faulted replies", () =>
        {
            var binder = OneShotExperimentBinder(1);
            var malformed = OneShotExperimentReply(0xff); malformed[4] = 0;
            var replies = new[] {
                WsabiWmiReplyResult.FromMethodReply(binder.DecodeOutput(1, OneShotExperimentOutput(OneShotExperimentReply(0xff)))),
                WsabiWmiReplyResult.FromMethodReply(binder.DecodeOutput(0, OneShotExperimentOutput(malformed))),
                WsabiWmiReplyResult.FromMethodReply(binder.DecodeOutput(0, null)),
                null };
            foreach (var reply in replies)
            {
                string text = ExperimentReviewText(new WsabiWmiOneShotReport(WsabiWmiOneShotStatus.ResponseReceived,
                    ProcessElevationState.Elevated, WsabiWmiMetadataStatus.Complete, true, reply,
                    WsabiWmiOneShotPreflightStage.Ready));
                var review = WsabiWmiExperimentReviewParser.Parse(text);
                Equal(WsabiWmiExperimentReviewStatus.NoValidatedResponse, review.Status);
                Equal<bool?>(true, review.InvocationRequested);
                Equal(WsabiWmiCandidateMarker.NotObserved, review.Marker);
                ExperimentReviewAssertNoHardware(review);
            }
            foreach (var report in new[] {
                new WsabiWmiOneShotReport(WsabiWmiOneShotStatus.PreflightFailed,
                    ProcessElevationState.Elevated, WsabiWmiMetadataStatus.Unavailable,
                    preflightStage: WsabiWmiOneShotPreflightStage.MethodEnumeration),
                new WsabiWmiOneShotReport(WsabiWmiOneShotStatus.ReservationAlreadyUsed,
                    ProcessElevationState.Elevated, WsabiWmiMetadataStatus.Complete,
                    preflightStage: WsabiWmiOneShotPreflightStage.Ready),
                new WsabiWmiOneShotReport(WsabiWmiOneShotStatus.TransportFailure,
                    ProcessElevationState.Elevated, WsabiWmiMetadataStatus.Complete, true,
                    preflightStage: WsabiWmiOneShotPreflightStage.Ready) })
            {
                var review = WsabiWmiExperimentReviewParser.Parse(ExperimentReviewText(report));
                Equal(WsabiWmiExperimentReviewStatus.NoValidatedResponse, review.Status);
                Equal<bool?>(report.InvocationRequested, review.InvocationRequested);
                Equal(WsabiWmiCandidateMarker.NotObserved, review.Marker);
                ExperimentReviewAssertNoHardware(review);
            }
        });
        Add("offline experiment review accepts bounded BOM and Windows newlines but rejects oversized or control-bearing text", () =>
        {
            string valid = ExperimentReviewFixture(0xff).Replace("\r\n", "\n");
            foreach (string text in new[] { valid, valid.Replace("\n", "\r\n"), "\uFEFF" + valid.Replace("\n", "\r\n") })
                Check(WsabiWmiExperimentReviewParser.Parse(text).HasValidatedFrame, "supported newline/BOM changed the result");
            Check(WsabiWmiExperimentReviewParser.Parse(valid + "\n" + new string('x', 512)).HasValidatedFrame,
                "bounded ignored line was not accepted");
            foreach (string text in new[] { null, "", " ", new string('x', 8193), valid + "\n" + new string('x', 513),
                valid + new string('\n', 65), valid + "\0", valid + "\r", valid + "\u0001" })
                ExperimentReviewAssertRejected(text, WsabiWmiExperimentReviewStatus.InvalidInput);
        });
        Add("offline experiment review retains only immutable classifications and never echoes ignored identities or claims authentication", () =>
        {
            string valid = ExperimentReviewFixture(0xff);
            string untrusted = valid.Replace("결과: ", "결과: PrivateDescription ") +
                "\nPrivateName C:\\Users\\PrivateName\\PrivateFile S-1-5-21-PrivateSid PrivateInstance";
            var review = WsabiWmiExperimentReviewParser.Parse(untrusted);
            Check(review.HasValidatedFrame, "ignored text affected fixed classifications");
            string display = review.ToDisplayText();
            foreach (string secret in new[] { "PrivateName", "PrivateFile", "PrivateSid", "PrivateInstance", "PrivateDescription", @"C:\Users" })
                Check(!display.Contains(secret), "untrusted identity echoed in sanitized review");
            Check(display.Contains("과거 텍스트") && display.Contains("진위·현재 장치 일치를 검증하지 않습니다")
                && display.Contains("추가 실행을 허용하지 않습니다"), "pasted text was presented as authenticated live evidence");
            Type type = typeof(WsabiWmiExperimentReview);
            Equal(0, type.GetConstructors().Length);
            foreach (var property in type.GetProperties()) Check(!property.CanWrite, "review publicly mutable");
            foreach (var field in type.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                Check(field.IsInitOnly && (field.FieldType.IsEnum || field.FieldType == typeof(bool?)),
                    "review retains raw text, raw output or mutable state");
            Equal(WsabiWmiExperimentReviewStatus.NotLoaded, WsabiWmiExperimentReview.Empty.Status);
            Equal<bool?>(null, WsabiWmiExperimentReview.Empty.InvocationRequested);
            ExperimentReviewAssertNoHardware(WsabiWmiExperimentReview.Empty);
            var inconsistent = new WsabiWmiExperimentReview(WsabiWmiExperimentReviewStatus.ValidatedFrameMeaningUnknown,
                true, (WsabiWmiCandidateMarker)999);
            Equal(WsabiWmiExperimentReviewStatus.Inconsistent, inconsistent.Status);
            ExperimentReviewAssertNoHardware(inconsistent);
        });
    }

    private static string ExperimentReviewFixture(byte marker)
    {
        var reply = WsabiWmiReplyResult.FromMethodReply(OneShotExperimentBinder(1).DecodeOutput(0,
            OneShotExperimentOutput(OneShotExperimentReply(marker))));
        return ExperimentReviewText(new WsabiWmiOneShotReport(WsabiWmiOneShotStatus.ResponseReceived,
            ProcessElevationState.Elevated, WsabiWmiMetadataStatus.Complete, true, reply,
            WsabiWmiOneShotPreflightStage.Ready));
    }

    private static string ExperimentReviewText(WsabiWmiOneShotReport report)
        => "수정판: 승인된 단1회 조회 · 경로 정보 확보 보완 (Query65-locator-v2)\n" + report.ToDisplayText();

    private static void ExperimentReviewAssertRejected(string text, WsabiWmiExperimentReviewStatus status)
    {
        var review = WsabiWmiExperimentReviewParser.Parse(text);
        Equal(status, review.Status);
        Equal(WsabiWmiCandidateMarker.NotObserved, review.Marker);
        Equal<bool?>(null, review.InvocationRequested);
        Check(!review.HasValidatedFrame, "rejected text retained a validated frame");
        ExperimentReviewAssertNoHardware(review);
    }

    private static void ExperimentReviewAssertNoHardware(WsabiWmiExperimentReview review)
        => Check(!review.CanReadHardware && !review.CanWriteHardware && !review.CanInvokeMethods,
            "offline text review authorized a hardware operation");
}
