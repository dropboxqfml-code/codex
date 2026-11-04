using System;
using System.Reflection;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiOneShotPreflightTraceTests()
    {
        AddAsync("one-shot failed preparation preserves its fixed location while clearing ready facts and making no claim", async () =>
        {
            foreach (WsabiWmiOneShotPreflightStage stage in Enum.GetValues(typeof(WsabiWmiOneShotPreflightStage)))
            {
                var failed = new WsabiWmiOneShotPreflight(WsabiWmiMetadataStatus.Unavailable,
                    true, OneShotExperimentMetadata(), true, 1, true, true, stage);
                Equal(stage, failed.Stage);
                Equal<bool?>(null, failed.DeviceMatches);
                Check(!failed.EnumerationComplete && !failed.InputReady, "failed trace retained readiness");
                Equal(0, failed.MethodInstanceCount);
                Equal<bool?>(null, failed.SoleInstanceActive);
                Check(failed.Metadata.BindingStatus != WsabiWmiContractBindingStatus.MetadataShapeMatched,
                    "trace restored failed metadata facts");
                var backend = new OneShotExperimentBackend { Preparer = () => failed };
                var reservation = new OneShotExperimentReservation();
                var report = await new WsabiWmiOneShotExperiment(backend, reservation).RunAsync();
                Equal(WsabiWmiOneShotStatus.PreflightFailed, report.Status);
                Equal(WsabiWmiMetadataStatus.Unavailable, report.PreflightStatus);
                Equal(stage, report.PreflightStage);
                OneShotExperimentAssertNoCall(report, backend, reservation);
                string text = report.ToDisplayText();
                Check(text.Contains("사전 검증 단계:") && text.Contains("(" + stage + ")"), "preparation location lost");
                Check(!text.Contains("메타데이터 조회 결과 확인 불가"), "generic failure was attributed to metadata");
            }
        });
        AddAsync("one-shot legacy invalid and thrown preparations remain unknown without leaking raw provider information", async () =>
        {
            var legacy = new WsabiWmiOneShotPreflight(WsabiWmiMetadataStatus.Unavailable,
                null, null, false, 0, null, false);
            var invalid = new WsabiWmiOneShotPreflight(WsabiWmiMetadataStatus.Unavailable,
                true, OneShotExperimentMetadata(), true, 1, true, true, (WsabiWmiOneShotPreflightStage)999);
            Equal(WsabiWmiOneShotPreflightStage.Unknown, legacy.Stage);
            Check(typeof(WsabiWmiOneShotPreflight).GetConstructor(new[] {
                typeof(WsabiWmiMetadataStatus), typeof(bool?), typeof(WsabiWmiContractMetadataReport),
                typeof(bool), typeof(int), typeof(bool?), typeof(bool) }) != null,
                "the original binary constructor signature was removed");
            Equal(WsabiWmiOneShotPreflightStage.Unknown, invalid.Stage);
            foreach (Func<WsabiWmiOneShotPreflight> prepare in new Func<WsabiWmiOneShotPreflight>[] {
                () => legacy, () => invalid, () => null,
                () => { throw new InvalidOperationException(@"C:\Users\PrivateName\PrivateInstance"); } })
            {
                var backend = new OneShotExperimentBackend { Preparer = prepare };
                var reservation = new OneShotExperimentReservation();
                var report = await new WsabiWmiOneShotExperiment(backend, reservation).RunAsync();
                Equal(WsabiWmiOneShotPreflightStage.Unknown, report.PreflightStage);
                OneShotExperimentAssertNoCall(report, backend, reservation);
                string text = report.ToDisplayText();
                Check(!text.Contains("PrivateName") && !text.Contains("PrivateInstance") && !text.Contains(@"C:\Users"),
                    "raw preparation detail leaked");
            }
            var invalidReport = new WsabiWmiOneShotReport(WsabiWmiOneShotStatus.PreflightFailed,
                ProcessElevationState.Elevated, WsabiWmiMetadataStatus.Unavailable,
                preflightStage: (WsabiWmiOneShotPreflightStage)999);
            Equal(WsabiWmiOneShotPreflightStage.Unknown, invalidReport.PreflightStage);
            foreach (var property in typeof(WsabiWmiOneShotPreflight).GetProperties())
                Check(!property.CanWrite, "preparation trace publicly mutable");
            foreach (var field in typeof(WsabiWmiOneShotReport).GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                Check(field.FieldType != typeof(string) && field.FieldType != typeof(object) && field.FieldType != typeof(byte[]),
                    "trace report stores raw values or errors");
        });
        AddAsync("one-shot fixed locations propagate through existing gates and synthetic replies without authorizing another request", async () =>
        {
            foreach (var preflight in new[] {
                new WsabiWmiOneShotPreflight(WsabiWmiMetadataStatus.Complete, false,
                    OneShotExperimentMetadata(), true, 1, true, true, WsabiWmiOneShotPreflightStage.ModelRead),
                new WsabiWmiOneShotPreflight(WsabiWmiMetadataStatus.Complete, true,
                    OneShotExperimentMetadata(id: 2), true, 1, true, true, WsabiWmiOneShotPreflightStage.ContractMetadata),
                new WsabiWmiOneShotPreflight(WsabiWmiMetadataStatus.Complete, true,
                    OneShotExperimentMetadata(), false, 2, true, true, WsabiWmiOneShotPreflightStage.MethodEnumeration),
                new WsabiWmiOneShotPreflight(WsabiWmiMetadataStatus.Complete, true,
                    OneShotExperimentMetadata(), true, 1, true, false, WsabiWmiOneShotPreflightStage.InputParameters) })
            {
                var backend = new OneShotExperimentBackend { Preparer = () => preflight };
                var reservation = new OneShotExperimentReservation();
                var report = await new WsabiWmiOneShotExperiment(backend, reservation).RunAsync();
                Equal(preflight.Stage, report.PreflightStage);
                OneShotExperimentAssertNoCall(report, backend, reservation);
            }
            var readyBackend = new OneShotExperimentBackend { Preparer = () => new WsabiWmiOneShotPreflight(
                WsabiWmiMetadataStatus.Complete, true, OneShotExperimentMetadata(), true, 1, true, true,
                WsabiWmiOneShotPreflightStage.Ready) };
            var readyReservation = new OneShotExperimentReservation();
            var experiment = new WsabiWmiOneShotExperiment(readyBackend, readyReservation);
            var readyReport = await experiment.RunAsync();
            Equal(WsabiWmiOneShotPreflightStage.Ready, readyReport.PreflightStage);
            Equal(WsabiWmiOneShotStatus.ResponseReceived, readyReport.Status);
            Equal(1, readyBackend.Calls); Equal(1, readyReservation.Claims);
            OneShotExperimentAssertNoHardwareMeaning(readyReport);
            var duplicate = await experiment.RunAsync();
            Equal(WsabiWmiOneShotStatus.AlreadyRun, duplicate.Status);
            Equal(WsabiWmiOneShotPreflightStage.Unknown, duplicate.PreflightStage);
            Equal(1, readyBackend.Calls); Equal(1, readyReservation.Claims);
        });
    }
}
