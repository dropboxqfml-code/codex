using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json.Nodes;
using ATIVBatteryGuard.Core.Hardware;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWmiInstanceTests()
    {
        Add("WMI instance policy permits exactly two fixed property projections", () =>
        {
            Equal(@"root\WMI", SamsungWmiInstancePolicy.LocalNamespace);
            Equal("SELECT Active,version FROM WmiAcpiVersion", SamsungWmiInstancePolicy.GetQuery(SamsungWmiClass.Version));
            Equal("SELECT Active FROM WmiAcpiMethod", SamsungWmiInstancePolicy.GetQuery(SamsungWmiClass.Method));
            Equal(2, SamsungWmiInstancePolicy.AllowedClasses.Length);
            SamsungWmiInstancePolicy.AllowedClasses[0] = "Injected";
            Equal("WmiAcpiVersion", SamsungWmiInstancePolicy.AllowedClasses[0]);
            foreach (string rejected in new[] { null, "DataBuffer", "Win32_Battery", "WmiAcpiVersion;SELECT *", "wmiacpiversion", @"\\remote\root\WMI" })
                Check(!SamsungWmiInstancePolicy.IsAllowedClass(rejected), "widened WMI instance scope");
            BatteryThrows<ArgumentOutOfRangeException>(() => SamsungWmiInstancePolicy.GetQuery((SamsungWmiClass)999));
            Check(!SamsungWmiInstancePolicy.CanInvokeMethods && !SamsungWmiInstancePolicy.HardwareWriteAllowed, "policy permits control");
        });
        Add("WMI instance property normalization accepts only exact Boolean and UInt32 types", () =>
        {
            Equal<bool?>(true, SamsungWmiInstancePolicy.NormalizeActive(true));
            Equal<bool?>(false, SamsungWmiInstancePolicy.NormalizeActive(false));
            foreach (object value in new object[] { null, DBNull.Value, 0, 1u, "true", "False", new object() })
                Equal<bool?>(null, SamsungWmiInstancePolicy.NormalizeActive(value));
            Equal<uint?>(0u, SamsungWmiInstancePolicy.NormalizeVersion(0u));
            Equal<uint?>(uint.MaxValue, SamsungWmiInstancePolicy.NormalizeVersion(uint.MaxValue));
            foreach (object value in new object[] { null, DBNull.Value, 0, -1, (ushort)1, 1L, 1UL, "1", true, 1.0, new object() })
                Equal<uint?>(null, SamsungWmiInstancePolicy.NormalizeVersion(value));
        });
        Add("WMI normal empty instances differ from class namespace access and timeout failures", () =>
        {
            foreach (SamsungWmiQueryStatus status in Enum.GetValues(typeof(SamsungWmiQueryStatus)))
            {
                var report = new SamsungWmiInstanceReport(new SamsungWmiClassObservation(SamsungWmiClass.Version, status));
                string text = report.ToDisplayText();
                Check(text.Contains(SamsungWmiInstanceReport.StatusText(status)), "status missing");
                Equal(status == SamsungWmiQueryStatus.Complete, text.Contains("정상 조회에서 인스턴스가 관측되지 않았습니다"));
                if (status != SamsungWmiQueryStatus.Complete) Check(text.Contains("부재를 판단하지 않습니다"), "failure implies absence");
                Equal(SamsungWmiQueryStatus.NotChecked, report.MethodClass.Status);
            }
        });
        Add("WMI observations snapshot rows bound lookahead and reject method version or wrong class", () =>
        {
            var rows = new[] { new SamsungWmiInstanceEntry(false, 0u) };
            var observation = new SamsungWmiClassObservation(SamsungWmiClass.Version, SamsungWmiQueryStatus.Complete, rows);
            rows[0] = null; observation.Entries[0] = null; Check(observation.Entries[0] != null, "mutable rows");
            int visited = 0;
            var bounded = new SamsungWmiClassObservation(SamsungWmiClass.Version, SamsungWmiQueryStatus.Complete, BoundedWmiInstances(() => visited++));
            Equal(9, visited); Equal(8, bounded.Entries.Length); Equal(SamsungWmiQueryStatus.Partial, bounded.Status);
            var malformed = new SamsungWmiClassObservation(SamsungWmiClass.Method, SamsungWmiQueryStatus.Complete, new[] { new SamsungWmiInstanceEntry(true, 4u) });
            Equal(SamsungWmiQueryStatus.InvalidResponse, malformed.Status); Equal(0, malformed.Entries.Length);
            var wrongClass = new SamsungWmiInstanceReport(new SamsungWmiClassObservation(SamsungWmiClass.Method, SamsungWmiQueryStatus.Complete));
            Equal(SamsungWmiClass.Version, wrongClass.VersionClass.Kind); Equal(SamsungWmiQueryStatus.InvalidResponse, wrongClass.VersionClass.Status);
            var nullRow = new SamsungWmiClassObservation(SamsungWmiClass.Version, SamsungWmiQueryStatus.Complete, new SamsungWmiInstanceEntry[] { null });
            Equal(SamsungWmiQueryStatus.InvalidResponse, nullRow.Status); Equal(0, nullRow.Entries.Length);
        });
        Add("WMI failures discard earlier rows without converting them into no-instance success", () =>
        {
            foreach (SamsungWmiQueryStatus status in Enum.GetValues(typeof(SamsungWmiQueryStatus)))
            {
                var observation = new SamsungWmiClassObservation(SamsungWmiClass.Version, status, new[] { new SamsungWmiInstanceEntry(true, 1u) });
                Equal(status == SamsungWmiQueryStatus.Complete || status == SamsungWmiQueryStatus.Partial ? 1 : 0, observation.Entries.Length);
            }
            Equal(SamsungWmiQueryStatus.InvalidResponse, new SamsungWmiClassObservation(SamsungWmiClass.Version, (SamsungWmiQueryStatus)999).Status);
            Equal(SamsungWmiQueryStatus.InvalidResponse, SamsungWmiInstanceReport.Failure(SamsungWmiQueryStatus.Complete).VersionClass.Status);
        });
        Add("WMI multi-instance display preserves false zero unknown max version without choosing a target", () =>
        {
            var report = WmiObservedReport();
            string text = report.ToDisplayText();
            Check(text.Contains("Active=True") && text.Contains("Active=False") && text.Contains("Active=Unknown"), "active tri-state collapsed");
            Check(text.Contains("0 (0x00000000)") && text.Contains("4294967295 (0xFFFFFFFF)") && text.Contains("version=Unknown"), "version lost or interpreted");
            Check(text.Contains("하나를 선택하거나") && text.Contains("대응시키지 않습니다"), "instances correlated");
            Check(!report.HardwareWriteAllowed && !report.CanInvokeMethods, "metadata enables method access");
            Check(!new UnsupportedChargeLimitController().SetMode(ChargeMode.Protection80).Success, "WMI presence enables writes");
            var combined = new SamsungFileInspectionReport(SamsungFileInspectionStatus.DirectoryNotFound, wmiInstances: report);
            Check(combined.ToDisplayText().Contains("WmiAcpiVersion") && combined.ToDisplayText().Contains("실제 충전 제어: 미지원"), "combined report changes capability");
        });
        Add("WMI IPC v5 roundtrips nullable values and independent class outcomes", () =>
        {
            foreach (SamsungWmiQueryStatus versionStatus in Enum.GetValues(typeof(SamsungWmiQueryStatus)))
            foreach (SamsungWmiQueryStatus methodStatus in Enum.GetValues(typeof(SamsungWmiQueryStatus)))
            {
                var observed = WmiObservedReport();
                var wmi = new SamsungWmiInstanceReport(new SamsungWmiClassObservation(SamsungWmiClass.Version, versionStatus,
                    observed.VersionClass.Entries.Where(e => versionStatus != SamsungWmiQueryStatus.Complete || (e.Active.HasValue && e.Version.HasValue))),
                    new SamsungWmiClassObservation(SamsungWmiClass.Method, methodStatus,
                        observed.MethodClass.Entries.Where(e => methodStatus != SamsungWmiQueryStatus.Complete || e.Active.HasValue)));
                var report = new SamsungFileInspectionReport(SamsungFileInspectionStatus.DirectoryNotFound, wmiInstances: wmi);
                var decoded = SamsungFileInspectionProtocol.Decode(SamsungFileInspectionProtocol.Encode(report));
                Equal(SamsungFileInspectionStatus.DirectoryNotFound, decoded.Status);
                Equal(versionStatus, decoded.WmiInstances.VersionClass.Status); Equal(methodStatus, decoded.WmiInstances.MethodClass.Status);
                Equal(wmi.VersionClass.Entries.Length, decoded.WmiInstances.VersionClass.Entries.Length);
                Equal(wmi.MethodClass.Entries.Length, decoded.WmiInstances.MethodClass.Entries.Length);
                for (int i = 0; i < wmi.VersionClass.Entries.Length; i++)
                {
                    Equal(wmi.VersionClass.Entries[i].Active, decoded.WmiInstances.VersionClass.Entries[i].Active);
                    Equal(wmi.VersionClass.Entries[i].Version, decoded.WmiInstances.VersionClass.Entries[i].Version);
                }
            }
        });
        Add("WMI IPC requires both fixed classes and all fields while rejecting older versions", () =>
        {
            AssertInvalidInspectionPacket(MutateWmiPacket(root => root["Version"] = 4));
            AssertInvalidInspectionPacket(MutateWmiPacket(root => root.Remove("WmiInstances")));
            AssertInvalidInspectionPacket(MutateWmiPacket(root => root["WmiInstances"] = null));
            foreach (string name in new[] { "VersionClass", "MethodClass" })
            {
                AssertInvalidInspectionPacket(MutateWmiPacket(root => ((JsonObject)root["WmiInstances"]).Remove(name)));
                foreach (string field in new[] { "Kind", "Status", "Entries" })
                    AssertInvalidInspectionPacket(MutateWmiPacket(root => ((JsonObject)root["WmiInstances"][name]).Remove(field)));
                foreach (string field in new[] { "Active", "Version" })
                    AssertInvalidInspectionPacket(MutateWmiPacket(root => ((JsonObject)root["WmiInstances"][name]["Entries"][0]).Remove(field)));
            }
        });
        Add("WMI IPC rejects wrong class kinds row limits method versions and stale failure rows", () =>
        {
            foreach (string name in new[] { "VersionClass", "MethodClass" })
            {
                AssertInvalidInspectionPacket(MutateWmiPacket(root => root["WmiInstances"][name]["Kind"] = 999));
                AssertInvalidInspectionPacket(MutateWmiPacket(root => root["WmiInstances"][name]["Status"] = 999));
                AssertInvalidInspectionPacket(MutateWmiPacket(root => root["WmiInstances"][name]["Entries"] = null));
                AssertInvalidInspectionPacket(MutateWmiPacket(root => root["WmiInstances"][name]["Entries"][0] = null));
                AssertInvalidInspectionPacket(MutateWmiPacket(root => root["WmiInstances"][name]["Entries"] = new JsonArray(Enumerable.Range(0, 9).Select(i => root["WmiInstances"][name]["Entries"][0].DeepClone()).ToArray())));
                foreach (SamsungWmiQueryStatus status in Enum.GetValues(typeof(SamsungWmiQueryStatus)))
                    if (status != SamsungWmiQueryStatus.Complete && status != SamsungWmiQueryStatus.Partial)
                        AssertInvalidInspectionPacket(MutateWmiPacket(root => root["WmiInstances"][name]["Status"] = (int)status));
            }
            AssertInvalidInspectionPacket(MutateWmiPacket(root => root["WmiInstances"]["VersionClass"]["Kind"] = (int)SamsungWmiClass.Method));
            AssertInvalidInspectionPacket(MutateWmiPacket(root => root["WmiInstances"]["MethodClass"]["Entries"][0]["Version"] = 1));
        });
        Add("WMI IPC rejects coercible strings numeric booleans and out-of-range versions", () =>
        {
            foreach (JsonNode bad in new JsonNode[] { JsonValue.Create("true"), JsonValue.Create(1), JsonValue.Create("false") })
                AssertInvalidInspectionPacket(MutateWmiPacket(root => root["WmiInstances"]["VersionClass"]["Entries"][0]["Active"] = bad.DeepClone()));
            foreach (JsonNode bad in new JsonNode[] { JsonValue.Create("7"), JsonValue.Create(-1), JsonValue.Create(4294967296L), JsonValue.Create(true), JsonValue.Create(1.5) })
                AssertInvalidInspectionPacket(MutateWmiPacket(root => root["WmiInstances"]["VersionClass"]["Entries"][0]["Version"] = bad.DeepClone()));
        });
        Add("WMI Complete cannot contain unknown required properties", () =>
        {
            Equal(SamsungWmiQueryStatus.Partial, new SamsungWmiClassObservation(SamsungWmiClass.Version, SamsungWmiQueryStatus.Complete, new[] { new SamsungWmiInstanceEntry(true) }).Status);
            Equal(SamsungWmiQueryStatus.Partial, new SamsungWmiClassObservation(SamsungWmiClass.Method, SamsungWmiQueryStatus.Complete, new[] { new SamsungWmiInstanceEntry(null) }).Status);
            foreach (string name in new[] { "VersionClass", "MethodClass" })
                AssertInvalidInspectionPacket(MutateWmiPacket(root => root["WmiInstances"][name]["Status"] = (int)SamsungWmiQueryStatus.Complete));
        });
        Add("WMI IPC strips unknown raw instance names paths and identifiers", () =>
        {
            string secret = @"PrivateName-device-UUID-C:\Users\PrivateName";
            var decoded = SamsungFileInspectionProtocol.Decode(MutateWmiPacket(root =>
            {
                root["WmiInstances"]["VersionClass"]["Entries"][0]["InstanceName"] = secret;
                root["WmiInstances"]["MethodClass"]["Path"] = secret;
            }));
            Equal(SamsungFileInspectionStatus.Complete, decoded.Status);
            string output = decoded.ToDisplayText() + Encoding.UTF8.GetString(SamsungFileInspectionProtocol.Encode(decoded));
            Check(!output.Contains("PrivateName") && !output.Contains("device-UUID") && !output.Contains(@"C:\Users"), "private fields retained");
        });
    }

    private static SamsungWmiInstanceReport WmiObservedReport() => new SamsungWmiInstanceReport(
        new SamsungWmiClassObservation(SamsungWmiClass.Version, SamsungWmiQueryStatus.Partial, new[] { new SamsungWmiInstanceEntry(true, 0u), new SamsungWmiInstanceEntry(false, uint.MaxValue), new SamsungWmiInstanceEntry(null) }),
        new SamsungWmiClassObservation(SamsungWmiClass.Method, SamsungWmiQueryStatus.Partial, new[] { new SamsungWmiInstanceEntry(false), new SamsungWmiInstanceEntry(true), new SamsungWmiInstanceEntry(null) }));

    private static byte[] MutateWmiPacket(Action<JsonObject> mutation)
    {
        var report = new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, new[] { InspectionEntry() }, wmiInstances: WmiObservedReport());
        var root = (JsonObject)JsonNode.Parse(SamsungFileInspectionProtocol.Encode(report));
        mutation(root); return Encoding.UTF8.GetBytes(root.ToJsonString());
    }

    private static IEnumerable<SamsungWmiInstanceEntry> BoundedWmiInstances(Action visit)
    {
        for (int i = 0; i < 9; i++) { visit(); yield return new SamsungWmiInstanceEntry(true, (uint)i); }
        throw new Exception("instance enumeration exceeded bounded lookahead");
    }
}
