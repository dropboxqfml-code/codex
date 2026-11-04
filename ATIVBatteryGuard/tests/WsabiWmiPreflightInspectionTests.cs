using System;
using System.Reflection;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiPreflightInspectionTests()
    {
        Add("preflight inspection classifies only the fixed HRESULT allowlist and treats unknown success codes as errors", () =>
        {
            int[] values = {
                unchecked((int)0x80070005), unchecked((int)0x80041003),
                unchecked((int)0x80043001), unchecked((int)0x800705B4),
                unchecked((int)0x80041010), unchecked((int)0x8004100E),
                unchecked((int)0x80041002), unchecked((int)0x80041008),
                unchecked((int)0x8004100C), unchecked((int)0x80041004),
                unchecked((int)0x80041024) };
            WsabiWmiPreflightIssue[] expected = {
                WsabiWmiPreflightIssue.AccessDenied, WsabiWmiPreflightIssue.AccessDenied,
                WsabiWmiPreflightIssue.TimedOut, WsabiWmiPreflightIssue.TimedOut,
                WsabiWmiPreflightIssue.ClassNotFound, WsabiWmiPreflightIssue.NamespaceNotFound,
                WsabiWmiPreflightIssue.NotFound, WsabiWmiPreflightIssue.InvalidParameter,
                WsabiWmiPreflightIssue.NotSupported, WsabiWmiPreflightIssue.ProviderFailure,
                WsabiWmiPreflightIssue.ProviderNotCapable };
            for (int i = 0; i < values.Length; i++)
                Equal(expected[i], WsabiWmiPreflightIssuePolicy.FromHResult(values[i]));
            foreach (int value in new[] { 0, 1, -1, int.MinValue, int.MaxValue,
                unchecked((int)0x80004005), unchecked((int)0x80131539) })
            {
                Equal(WsabiWmiPreflightIssue.OtherError, WsabiWmiPreflightIssuePolicy.FromHResult(value));
                var report = new WsabiWmiPreflightInspectionReport(ProcessElevationState.Elevated,
                    WsabiWmiMetadataStatus.Complete, WsabiWmiOneShotPreflightStage.Ready,
                    WsabiWmiPreflightIssuePolicy.FromHResult(value));
                Check(!report.PreparationReady, "unrecognized HRESULT authorized preparation");
            }
        });
        Add("preflight readiness requires every fixed condition and never grants OEM hardware or reservation access", () =>
        {
            int readyCount = 0;
            foreach (ProcessElevationState elevation in Enum.GetValues(typeof(ProcessElevationState)))
            foreach (WsabiWmiMetadataStatus status in Enum.GetValues(typeof(WsabiWmiMetadataStatus)))
            foreach (WsabiWmiOneShotPreflightStage stage in Enum.GetValues(typeof(WsabiWmiOneShotPreflightStage)))
            foreach (WsabiWmiPreflightIssue issue in Enum.GetValues(typeof(WsabiWmiPreflightIssue)))
            {
                var report = new WsabiWmiPreflightInspectionReport(elevation, status, stage, issue);
                bool expected = elevation == ProcessElevationState.Elevated
                    && status == WsabiWmiMetadataStatus.Complete
                    && stage == WsabiWmiOneShotPreflightStage.Ready
                    && issue == WsabiWmiPreflightIssue.None;
                Equal(expected, report.PreparationReady);
                Equal(elevation, report.Elevation); Equal(status, report.Status);
                Equal(stage, report.Stage); Equal(issue, report.Issue);
                Check(!report.CanInvokeMethods && !report.CanWriteHardware && !report.TouchesReservation,
                    "preflight report granted an execution capability");
                if (report.PreparationReady) readyCount++;
            }
            Equal(1, readyCount);
        });
        Add("invalid preflight enums discard readiness while valid failures retain only fixed classifications", () =>
        {
            foreach (int invalid in new[] { -1, int.MaxValue })
            foreach (var report in new[] {
                new WsabiWmiPreflightInspectionReport((ProcessElevationState)invalid,
                    WsabiWmiMetadataStatus.Complete, WsabiWmiOneShotPreflightStage.Ready, WsabiWmiPreflightIssue.None),
                new WsabiWmiPreflightInspectionReport(ProcessElevationState.Elevated,
                    (WsabiWmiMetadataStatus)invalid, WsabiWmiOneShotPreflightStage.Ready, WsabiWmiPreflightIssue.None),
                new WsabiWmiPreflightInspectionReport(ProcessElevationState.Elevated,
                    WsabiWmiMetadataStatus.Complete, (WsabiWmiOneShotPreflightStage)invalid, WsabiWmiPreflightIssue.None),
                new WsabiWmiPreflightInspectionReport(ProcessElevationState.Elevated,
                    WsabiWmiMetadataStatus.Complete, WsabiWmiOneShotPreflightStage.Ready, (WsabiWmiPreflightIssue)invalid) })
            {
                Equal(WsabiWmiMetadataStatus.Unavailable, report.Status);
                Equal(WsabiWmiOneShotPreflightStage.Unknown, report.Stage);
                Equal(WsabiWmiPreflightIssue.OtherError, report.Issue);
                Check(!report.PreparationReady, "invalid report retained readiness");
                Check(!report.ToDisplayText().Contains(invalid.ToString()), "invalid enum value leaked");
            }
            var failed = new WsabiWmiPreflightInspectionReport(ProcessElevationState.Elevated,
                WsabiWmiMetadataStatus.Unavailable, WsabiWmiOneShotPreflightStage.InputParameters,
                WsabiWmiPreflightIssue.InputCimTypeMissing);
            Equal(WsabiWmiOneShotPreflightStage.InputParameters, failed.Stage);
            Equal(WsabiWmiPreflightIssue.InputCimTypeMissing, failed.Issue);
            string failureText = failed.ToDisplayText();
            Check(failureText.Contains("(InputParameters)") && failureText.Contains("(InputCimTypeMissing)"),
                "fixed failure stage or reason lost from display");
            Check(!failed.PreparationReady, "failed inspection reported preparation success");
        });
        Add("preflight reports are immutable fixed classifications with explicit non-hardware meaning and no raw identity channel", () =>
        {
            Type type = typeof(WsabiWmiPreflightInspectionReport);
            foreach (var property in type.GetProperties())
                Check(!property.CanWrite, "inspection report publicly mutable");
            foreach (var field in type.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                Check(field.IsInitOnly && field.FieldType.IsEnum, "inspection report retains raw data or mutable state");
            var constructors = type.GetConstructors();
            Equal(1, constructors.Length);
            Equal(4, constructors[0].GetParameters().Length);
            foreach (var parameter in constructors[0].GetParameters())
                Check(parameter.ParameterType.IsEnum, "inspection accepts raw values or exception details");
            Equal("사전검증 전용 · OEM 호출 없음", WsabiWmiPreflightInspectionReport.ConsoleTitle);
            foreach (WsabiWmiPreflightIssue issue in Enum.GetValues(typeof(WsabiWmiPreflightIssue)))
            {
                string text = new WsabiWmiPreflightInspectionReport(ProcessElevationState.Elevated,
                    WsabiWmiMetadataStatus.Complete, WsabiWmiOneShotPreflightStage.Ready, issue).ToDisplayText();
                Check(text.Contains("(" + issue + ")") && text.Contains("OEM 호출: 없음")
                    && text.Contains("1회 예약 표식 접근: 없음")
                    && text.Contains("준비 완료는 OEM 실행이나 충전 제한 성공을 의미하지 않습니다.")
                    && text.Contains("실제 충전 제어: 미지원"), "inspection meaning is ambiguous");
                Check(!text.Contains("0x800") && !text.Contains(@"C:\")
                    && !text.Contains("S-1-5-") && !text.Contains("PrivateName"), "raw error or identity detail leaked");
            }
        });
    }
}
