using System;
using ATIVBatteryGuard.Core.Hardware;
using ATIVBatteryGuard.Core.Models;

internal static partial class Program
{
    private static void RegisterWmiAccessTraceTests()
    {
        Add("observed normal and elevated WMI pair preserves selective enumeration denial without granting OEM access", () =>
        {
            var version = new SamsungWmiClassObservation(SamsungWmiClass.Version, SamsungWmiQueryStatus.Complete,
                new[] { new SamsungWmiInstanceEntry(true, 16u) });
            var completedVersion = new SamsungWmiAccessTrace(SamsungWmiClass.Version,
                SamsungWmiAccessStage.Completed, SamsungWmiAccessCode.None);
            var normal = new SamsungWmiAccessProbeResult(new SamsungWmiInstanceReport(version,
                new SamsungWmiClassObservation(SamsungWmiClass.Method, SamsungWmiQueryStatus.AccessDenied)),
                completedVersion, new SamsungWmiAccessTrace(SamsungWmiClass.Method,
                    SamsungWmiAccessStage.Enumerate, SamsungWmiAccessCode.WmiAccessDenied));
            var elevated = new SamsungWmiAccessProbeResult(new SamsungWmiInstanceReport(version,
                new SamsungWmiClassObservation(SamsungWmiClass.Method, SamsungWmiQueryStatus.Complete,
                    new[] { new SamsungWmiInstanceEntry(true) })),
                completedVersion, new SamsungWmiAccessTrace(SamsungWmiClass.Method,
                    SamsungWmiAccessStage.Completed, SamsungWmiAccessCode.None));
            Equal(SamsungWmiQueryStatus.AccessDenied, normal.Observation.MethodClass.Status);
            Equal(0, normal.Observation.MethodClass.Entries.Length);
            Equal(SamsungWmiQueryStatus.Complete, normal.Observation.VersionClass.Status);
            Equal<uint?>(16u, normal.Observation.VersionClass.Entries[0].Version);
            Equal<uint?>(16u, elevated.Observation.VersionClass.Entries[0].Version);
            Equal(1, elevated.Observation.MethodClass.Entries.Length);
            string normalText = normal.ToDisplayText(ProcessElevationState.NotElevated);
            string elevatedText = elevated.ToDisplayText(ProcessElevationState.Elevated);
            Check(normalText.Contains("Enumerate") && normalText.Contains("0x80041003") &&
                normalText.Contains("16 (0x00000010)"), "observed normal facts lost");
            Check(elevatedText.Contains("Active=True") && elevatedText.Contains("Completed") &&
                elevatedText.Contains("모델·명령 호환성을 해석하지 않습니다"), "opaque version interpreted as protocol support");
            Check(!normal.CanReadHardware && !elevated.CanReadHardware &&
                !elevated.CanWriteHardware && !elevated.CanInvokeMethods, "metadata access enabled hardware commands");
            var assessment = ATIVBatteryGuard.Core.Services.SamsungTransportAssessment.Evaluate(
                new SamsungFileInspectionReport(wmiInstances: normal.Observation));
            Check(assessment.HasWmiAccessDenied && assessment.Summary.Contains("WMI 버전: 정상 조회 완료") &&
                assessment.Summary.Contains("WMI 메서드 인스턴스: 조회 권한 없음"), "selective denial collapsed into whole-namespace failure");
        });
        Add("access trace null input is unavailable and unknown rather than non-elevated success", () =>
        {
            var result = new SamsungWmiAccessProbeResult(null, null, null);
            Equal(SamsungWmiQueryStatus.Unavailable, result.Observation.VersionClass.Status);
            Equal(SamsungWmiQueryStatus.Unavailable, result.Observation.MethodClass.Status);
            Equal(SamsungWmiClass.Version, result.VersionTrace.Kind);
            Equal(SamsungWmiClass.Method, result.MethodTrace.Kind);
            Equal(SamsungWmiAccessStage.NotStarted, result.VersionTrace.Stage);
            Equal(SamsungWmiAccessCode.None, result.MethodTrace.Code);
            string text = result.ToDisplayText(ProcessElevationState.Unknown);
            Check(text.Contains("확인 불가 (Unknown)") && !text.Contains("상승되지 않음 (NotElevated)"), "unknown elevation became ordinary token");
        });
        Add("access traces preserve distinct class outcomes and bounded immutable observed values", () =>
        {
            var rows = new[] { new SamsungWmiInstanceEntry(false, 0u) };
            var observation = new SamsungWmiInstanceReport(
                new SamsungWmiClassObservation(SamsungWmiClass.Version, SamsungWmiQueryStatus.Complete, rows),
                new SamsungWmiClassObservation(SamsungWmiClass.Method, SamsungWmiQueryStatus.AccessDenied));
            var version = new SamsungWmiAccessTrace(SamsungWmiClass.Version, SamsungWmiAccessStage.Completed, SamsungWmiAccessCode.None);
            var method = new SamsungWmiAccessTrace(SamsungWmiClass.Method, SamsungWmiAccessStage.Query, SamsungWmiAccessCode.WmiAccessDenied);
            var result = new SamsungWmiAccessProbeResult(observation, version, method);
            rows[0] = null;
            result.Observation.VersionClass.Entries[0] = null;
            Equal(SamsungWmiQueryStatus.Complete, result.Observation.VersionClass.Status);
            Equal<uint?>(0u, result.Observation.VersionClass.Entries[0].Version);
            Equal(SamsungWmiQueryStatus.AccessDenied, result.Observation.MethodClass.Status);
            Equal(SamsungWmiAccessStage.Query, result.MethodTrace.Stage);
            Check(result.ToDisplayText(ProcessElevationState.NotElevated).Contains("0x80041003"), "WMI denial category missing");
        });
        Add("access trace wrong class or invalid enums never fabricate a successful phase", () =>
        {
            var observation = new SamsungWmiInstanceReport(
                new SamsungWmiClassObservation(SamsungWmiClass.Version, SamsungWmiQueryStatus.Complete, new[] { new SamsungWmiInstanceEntry(true, 1u) }),
                new SamsungWmiClassObservation(SamsungWmiClass.Method, SamsungWmiQueryStatus.TimedOut));
            var wrong = new SamsungWmiAccessTrace(SamsungWmiClass.Method, SamsungWmiAccessStage.Completed, SamsungWmiAccessCode.None);
            var result = new SamsungWmiAccessProbeResult(observation, wrong, null);
            Equal(SamsungWmiQueryStatus.InvalidResponse, result.Observation.VersionClass.Status);
            Equal(0, result.Observation.VersionClass.Entries.Length);
            Equal(SamsungWmiAccessStage.NotStarted, result.VersionTrace.Stage);
            Equal(SamsungWmiAccessCode.Other, result.VersionTrace.Code);
            Equal(SamsungWmiQueryStatus.TimedOut, result.Observation.MethodClass.Status);
            var invalid = new SamsungWmiAccessTrace(SamsungWmiClass.Version, (SamsungWmiAccessStage)999, (SamsungWmiAccessCode)999);
            Equal(SamsungWmiAccessStage.NotStarted, invalid.Stage); Equal(SamsungWmiAccessCode.Other, invalid.Code);
            BatteryThrows<ArgumentOutOfRangeException>(() => new SamsungWmiAccessTrace((SamsungWmiClass)999, SamsungWmiAccessStage.Connect, SamsungWmiAccessCode.None));
        });
        Add("access trace stages and errors explain locations without authorizing any action", () =>
        {
            foreach (SamsungWmiAccessStage stage in Enum.GetValues(typeof(SamsungWmiAccessStage)))
            foreach (SamsungWmiAccessCode code in Enum.GetValues(typeof(SamsungWmiAccessCode)))
            foreach (ProcessElevationState elevation in Enum.GetValues(typeof(ProcessElevationState)))
            {
                var result = new SamsungWmiAccessProbeResult(SamsungWmiInstanceReport.Failure(SamsungWmiQueryStatus.AccessDenied),
                    new SamsungWmiAccessTrace(SamsungWmiClass.Version, stage, code),
                    new SamsungWmiAccessTrace(SamsungWmiClass.Method, stage, code));
                string text = result.ToDisplayText(elevation);
                Check(text.Contains(SamsungWmiAccessProbeResult.StageText(stage)) && text.Contains(SamsungWmiAccessProbeResult.CodeText(code)), "trace detail missing");
                Check(text.Contains("원인을 확정하지 않습니다") && text.Contains("문제를 해결한다는 일반적 증거"), "location or elevation promoted to cause");
                Check(!result.CanReadHardware && !result.CanWriteHardware && !result.CanInvokeMethods, "trace enabled hardware");
            }
            Check(!new UnsupportedChargeLimitController().SetMode(ChargeMode.Protection80).Success, "trace changed unsupported controller");
        });
        Add("access trace deadline errors clear prior values and retain each failure location", () =>
        {
            var observation = new SamsungWmiInstanceReport(
                new SamsungWmiClassObservation(SamsungWmiClass.Version, SamsungWmiQueryStatus.TimedOut, new[] { new SamsungWmiInstanceEntry(true, 7u) }),
                new SamsungWmiClassObservation(SamsungWmiClass.Method, SamsungWmiQueryStatus.AccessDenied, new[] { new SamsungWmiInstanceEntry(true) }));
            var result = new SamsungWmiAccessProbeResult(observation,
                new SamsungWmiAccessTrace(SamsungWmiClass.Version, SamsungWmiAccessStage.Enumerate, SamsungWmiAccessCode.None),
                new SamsungWmiAccessTrace(SamsungWmiClass.Method, SamsungWmiAccessStage.Connect, SamsungWmiAccessCode.WindowsAccessDenied));
            Equal(0, result.Observation.VersionClass.Entries.Length); Equal(0, result.Observation.MethodClass.Entries.Length);
            Equal(SamsungWmiAccessStage.Enumerate, result.VersionTrace.Stage);
            Equal(SamsungWmiAccessStage.Connect, result.MethodTrace.Stage);
            string text = result.ToDisplayText(ProcessElevationState.Unknown);
            Check(text.Contains("조회 시간 초과") && text.Contains("0x80070005") && !text.Contains("version=7"), "failure lost or stale value retained");
        });
        Add("access trace output has fixed categories and no identity or raw exception fields", () =>
        {
            string[] expected =
            {
                "None", "0x80041003", "0x80070005", "0x80041010", "0x8004100E",
                "0x80041002", "0x80043001", "0x800705B4", "Other"
            };
            foreach (SamsungWmiAccessCode code in Enum.GetValues(typeof(SamsungWmiAccessCode)))
                Check(SamsungWmiAccessProbeResult.CodeText(code).Contains(expected[(int)code]), "wrong fixed HRESULT mapping");
            var result = new SamsungWmiAccessProbeResult(null, null, null);
            string text = result.ToDisplayText((ProcessElevationState)999);
            Check(text.Contains("확인 불가 (Unknown)") && text.Contains("별도 승인"), "unknown elevation or consent note missing");
            Check(text.Length < 8192 && !text.Contains(@"C:\Users\") && !text.Contains("S-1-5-") && !text.Contains("PrivateName"), "unbounded/private output");
            foreach (var property in typeof(SamsungWmiAccessTrace).GetProperties())
                Check(property.PropertyType != typeof(string), "trace accepts raw string metadata");
        });
    }
}
