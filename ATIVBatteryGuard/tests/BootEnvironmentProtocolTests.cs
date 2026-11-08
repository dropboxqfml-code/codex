using System;
using System.Text;
using System.Text.Json.Nodes;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterBootEnvironmentProtocolTests()
    {
        Add("boot metadata round trips without granting any hardware capability", () =>
        {
            foreach (WindowsBootQueryStatus status in Enum.GetValues(typeof(WindowsBootQueryStatus)))
            foreach (WindowsBootFirmwareType kind in Enum.GetValues(typeof(WindowsBootFirmwareType)))
            {
                var boot = new WindowsBootEnvironmentReport(status, kind);
                var report = new SamsungFileInspectionReport(SamsungFileInspectionStatus.DirectoryNotFound, bootEnvironment: boot);
                var decoded = SamsungFileInspectionProtocol.Decode(SamsungFileInspectionProtocol.Encode(report));
                Equal(SamsungFileInspectionStatus.DirectoryNotFound, decoded.Status);
                Equal(boot.Status, decoded.BootEnvironment.Status);
                Equal(boot.FirmwareType, decoded.BootEnvironment.FirmwareType);
                var assessment = SamsungTransportAssessment.Evaluate(decoded);
                Check(!assessment.CanReadHardware && !assessment.CanWriteHardware && !assessment.CanInvokeMethods &&
                    !decoded.HardwareWriteAllowed && !decoded.BootEnvironment.HardwareWriteAllowed,
                    "boot observation changed control capability");
            }
        });
        Add("legacy inspection packet has no inferred boot observation", () =>
        {
            byte[] bytes = MutateInspectionPacket(root => { root["Version"] = 5; root.Remove("BootEnvironment"); });
            var decoded = SamsungFileInspectionProtocol.Decode(bytes);
            Equal(SamsungFileInspectionStatus.Complete, decoded.Status);
            Equal(WindowsBootQueryStatus.NotCollected, decoded.BootEnvironment.Status);
            Equal(WindowsBootFirmwareType.Unknown, decoded.BootEnvironment.FirmwareType);
            Check(!decoded.BootEnvironment.ToDisplayText().Contains("관측: BIOS") &&
                !decoded.BootEnvironment.ToDisplayText().Contains("관측: UEFI"), "old report guessed boot mode");
            AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["Version"] = 5));
        });
        Add("current inspection packet requires a complete typed boot object", () =>
        {
            AssertInvalidInspectionPacket(MutateInspectionPacket(root => root.Remove("BootEnvironment")));
            AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["BootEnvironment"] = null));
            foreach (string field in new[] { "Status", "FirmwareType" })
                AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["BootEnvironment"].AsObject().Remove(field)));
            foreach (JsonNode invalid in new JsonNode[] { JsonValue.Create("private-value"), new JsonArray(), JsonValue.Create(0) })
                AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["BootEnvironment"] = invalid.DeepClone()));
        });
        Add("boot IPC rejects failed observations carrying plausible firmware types", () =>
        {
            foreach (WindowsBootQueryStatus status in Enum.GetValues(typeof(WindowsBootQueryStatus)))
            {
                if (status == WindowsBootQueryStatus.Complete) continue;
                foreach (int kind in new[] { 1, 2 })
                    AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["BootEnvironment"] =
                        new JsonObject { ["Status"] = (int)status, ["FirmwareType"] = kind }));
            }
            foreach (string field in new[] { "Status", "FirmwareType" })
            foreach (int invalid in new[] { -1, 99, int.MaxValue })
                AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["BootEnvironment"][field] = invalid));
        });
        Add("boot IPC rejects coerced primitive types and noninteger numeric syntax", () =>
        {
            foreach (string field in new[] { "Status", "FirmwareType" })
            foreach (JsonNode value in new JsonNode[] { null, JsonValue.Create("1"), JsonValue.Create(true),
                JsonValue.Create(1.5), new JsonArray(1), new JsonObject() })
                AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["BootEnvironment"][field] = value?.DeepClone()));
            foreach (string number in new[] { "1.0", "1e0", "4294967296" })
            {
                string json = Encoding.UTF8.GetString(MutateInspectionPacket(root => root["BootEnvironment"] =
                    new JsonObject { ["Status"] = 1, ["FirmwareType"] = 1 }));
                Check(json.Contains("\"FirmwareType\":1"), "numeric mutation did not select firmware field");
                AssertInvalidInspectionPacket(Encoding.UTF8.GetBytes(json.Replace("\"FirmwareType\":1", "\"FirmwareType\":" + number)));
            }
        });
        Add("boot IPC ignores unreported extra text without retaining source identifiers", () =>
        {
            const string sentinel = "private-user-path-not-for-report";
            var decoded = SamsungFileInspectionProtocol.Decode(MutateInspectionPacket(root =>
            {
                root["BootEnvironment"] = new JsonObject { ["Status"] = 1, ["FirmwareType"] = 2,
                    ["OriginalPath"] = sentinel, ["Exception"] = sentinel };
            }));
            Equal(WindowsBootFirmwareType.Uefi, decoded.BootEnvironment.FirmwareType);
            Check(!decoded.ToDisplayText().Contains(sentinel) &&
                !Encoding.UTF8.GetString(SamsungFileInspectionProtocol.Encode(decoded)).Contains(sentinel),
                "unreported boot source text leaked");
        });
        Add("boot observations remain independent of Samsung file and driver failures", () =>
        {
            var report = new SamsungFileInspectionReport(SamsungFileInspectionStatus.Unavailable,
                kernelDrivers: new SamsungKernelDriverReport(SamsungDriverQueryStatus.AccessDenied),
                bootEnvironment: new WindowsBootEnvironmentReport(WindowsBootQueryStatus.Complete, WindowsBootFirmwareType.Bios));
            var decoded = SamsungFileInspectionProtocol.Decode(SamsungFileInspectionProtocol.Encode(report));
            Equal(SamsungFileInspectionStatus.Unavailable, decoded.Status);
            Equal(SamsungDriverQueryStatus.AccessDenied, decoded.KernelDrivers.Status);
            Equal(WindowsBootQueryStatus.Complete, decoded.BootEnvironment.Status);
            Check(decoded.ToDisplayText().Contains("관측: BIOS"), "independent completed boot observation lost");
            var failedBoot = new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete,
                new[] { InspectionEntry() }, bootEnvironment: new WindowsBootEnvironmentReport(WindowsBootQueryStatus.TimedOut));
            var files = SamsungFileInspectionProtocol.Decode(SamsungFileInspectionProtocol.Encode(failedBoot));
            Equal(SamsungFileInspectionStatus.Complete, files.Status);
            Equal(1, files.Entries.Length);
            Equal(WindowsBootQueryStatus.TimedOut, files.BootEnvironment.Status);
        });
        Add("invalid boot packet clears observations and retains explicit invalid status", () =>
        {
            var decoded = SamsungFileInspectionProtocol.Decode(MutateInspectionPacket(root => root["BootEnvironment"]["FirmwareType"] = 3));
            Equal(SamsungFileInspectionStatus.InvalidResponse, decoded.Status);
            Equal(WindowsBootQueryStatus.InvalidResponse, decoded.BootEnvironment.Status);
            Equal(WindowsBootFirmwareType.Unknown, decoded.BootEnvironment.FirmwareType);
            Equal(0, decoded.Entries.Length);
        });
    }
}
