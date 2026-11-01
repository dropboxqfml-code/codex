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
    private static void RegisterSamsungKernelDriverTests()
    {
        Add("kernel driver candidate matching is bounded case insensitive and SABI first", () =>
        {
            Equal<SamsungDriverCategory?>(SamsungDriverCategory.SabiName, SamsungKernelDriverPolicy.Classify("SaBiDrv", "Samsung ACPI"));
            Equal<SamsungDriverCategory?>(SamsungDriverCategory.SamsungName, SamsungKernelDriverPolicy.Classify("other", "SAMSUNG device"));
            Equal<SamsungDriverCategory?>(SamsungDriverCategory.SabiName, SamsungKernelDriverPolicy.Classify(null, "SABI"));
            Equal<SamsungDriverCategory?>(null, SamsungKernelDriverPolicy.Classify("ACPI", null));
            Equal<SamsungDriverCategory?>(null, SamsungKernelDriverPolicy.Classify(null, null));
            Equal<SamsungDriverCategory?>(null, SamsungKernelDriverPolicy.Classify("SABI" + new string('a', 253), "Samsung"));
            Equal<SamsungDriverCategory?>(null, SamsungKernelDriverPolicy.Classify("SABI", new string('a', 257)));
            Equal<SamsungDriverCategory?>(SamsungDriverCategory.SabiName, SamsungKernelDriverPolicy.Classify("SABI" + new string('a', 252), null));
        });
        Add("kernel driver states preserve every documented execution condition", () =>
        {
            var states = new[] { "Unknown", "Stopped", "Start Pending", "Stop Pending", "Running", "Continue Pending", "Pause Pending", "Paused" };
            for (int i = 0; i < states.Length; i++) Equal((SamsungDriverState)i, SamsungKernelDriverPolicy.NormalizeState(states[i]));
            foreach (string invalid in new[] { null, "", "running", " Running", "Not Running", "private-user-ABC" })
                Equal(SamsungDriverState.Unknown, SamsungKernelDriverPolicy.NormalizeState(invalid));
        });
        Add("kernel driver startup modes preserve boot system auto manual disabled and unknown", () =>
        {
            var modes = new[] { "Unknown", "Boot", "System", "Auto", "Manual", "Disabled" };
            for (int i = 0; i < modes.Length; i++) Equal((SamsungDriverStartMode)i, SamsungKernelDriverPolicy.NormalizeStartMode(modes[i]));
            foreach (string invalid in new[] { null, "", "Automatic", "manual", "Boot ", @"C:\Users\PrivateName" })
                Equal(SamsungDriverStartMode.Unknown, SamsungKernelDriverPolicy.NormalizeStartMode(invalid));
        });
        Add("kernel driver normal no observation differs from incomplete error and timeout", () =>
        {
            foreach (SamsungDriverQueryStatus status in Enum.GetValues(typeof(SamsungDriverQueryStatus)))
            {
                var report = new SamsungKernelDriverReport(status);
                string text = report.ToDisplayText(SabiDriverLinkStatus.NotFound);
                Equal(status, report.Status);
                Equal(status == SamsungDriverQueryStatus.Complete, text.Contains("정상 조회 범위에서 이름 조건에 맞는 커널 드라이버 등록을 관측하지 못했습니다"));
                if (status != SamsungDriverQueryStatus.Complete) Check(text.Contains("부재를 판단할 수 없습니다"), "incomplete query implies absence");
                Check(text.Contains(SamsungKernelDriverReport.StatusText(status)), "query status omitted");
                Check(!report.HardwareWriteAllowed, "diagnostic enables write");
            }
        });
        Add("kernel driver errors discard earlier observations and invalid enums stay conservative", () =>
        {
            foreach (SamsungDriverQueryStatus status in Enum.GetValues(typeof(SamsungDriverQueryStatus)))
            {
                var report = new SamsungKernelDriverReport(status, new[] { DriverEntry() });
                Equal(status == SamsungDriverQueryStatus.Complete || status == SamsungDriverQueryStatus.Partial ? 1 : 0, report.Entries.Length);
            }
            Equal(SamsungDriverQueryStatus.InvalidResponse, new SamsungKernelDriverReport((SamsungDriverQueryStatus)999, new[] { DriverEntry() }).Status);
            var malformed = new SamsungKernelDriverReport(SamsungDriverQueryStatus.Complete, new[] { DriverEntry(), null });
            Equal(SamsungDriverQueryStatus.InvalidResponse, malformed.Status); Equal(0, malformed.Entries.Length);
            BatteryThrows<ArgumentOutOfRangeException>(() => new SamsungKernelDriverEntry((SamsungDriverCategory)999, SamsungDriverState.Running, SamsungDriverStartMode.Auto));
            var invalid = new SamsungKernelDriverEntry(SamsungDriverCategory.SabiName, (SamsungDriverState)999, (SamsungDriverStartMode)999);
            Equal(SamsungDriverState.Unknown, invalid.State); Equal(SamsungDriverStartMode.Unknown, invalid.StartMode);
        });
        Add("kernel driver reports snapshot entries and bounded lookahead marks partial", () =>
        {
            var source = new[] { DriverEntry() }; var report = new SamsungKernelDriverReport(SamsungDriverQueryStatus.Complete, source);
            source[0] = null; report.Entries[0] = null; Equal(1, report.Entries.Length); Check(report.Entries[0] != null, "entries mutable");
            int visited = 0;
            var bounded = new SamsungKernelDriverReport(SamsungDriverQueryStatus.Complete, BoundedDrivers(() => visited++));
            Equal(33, visited); Equal(32, bounded.Entries.Length); Equal(SamsungDriverQueryStatus.Partial, bounded.Status);
            Check(bounded.ToDisplayText(SabiDriverLinkStatus.NotFound).Contains("부재를 판단할 수 없습니다"), "entry cap implies absence");
        });
        Add("kernel driver and SABI link comparison never promotes any state into control", () =>
        {
            foreach (SabiDriverLinkStatus link in Enum.GetValues(typeof(SabiDriverLinkStatus)))
            foreach (SamsungDriverState state in Enum.GetValues(typeof(SamsungDriverState)))
            foreach (SamsungDriverStartMode mode in Enum.GetValues(typeof(SamsungDriverStartMode)))
            {
                var kernel = new SamsungKernelDriverReport(SamsungDriverQueryStatus.Complete, new[] { DriverEntry(state, mode) });
                var report = new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, new[] { InspectionEntry() }, driverLink: link, kernelDrivers: kernel);
                string text = report.ToDisplayText();
                Check(text.Contains("등록 관측") && text.Contains(SamsungKernelDriverReport.StateText(state)) && text.Contains(SamsungKernelDriverReport.StartModeText(mode)), "observation omitted");
                Check(text.Contains(SamsungFileInspectionReport.DriverLinkText(link)), "link comparison omitted");
                Check(text.Contains("실제 충전 제어는 미지원") && !report.HardwareWriteAllowed && !kernel.HardwareWriteAllowed, "state enabled control");
                Check(!new UnsupportedChargeLimitController().SetMode(ChargeMode.Protection80).Success, "unsupported write became available");
            }
            Check(new SamsungKernelDriverReport(SamsungDriverQueryStatus.Complete, new[] { DriverEntry() }).ToDisplayText(SabiDriverLinkStatus.NotFound).Contains("동시에 가능합니다"), "registration/link distinction missing");
            Check(new SamsungKernelDriverReport(SamsungDriverQueryStatus.Complete).ToDisplayText(SabiDriverLinkStatus.Present).Contains("서로 다른 조회 범위"), "link/no candidate distinction missing");
        });
        Add("kernel driver IPC roundtrips statuses categories states and startup modes", () =>
        {
            foreach (SamsungDriverQueryStatus status in Enum.GetValues(typeof(SamsungDriverQueryStatus)))
            foreach (SamsungDriverCategory category in Enum.GetValues(typeof(SamsungDriverCategory)))
            foreach (SamsungDriverState state in Enum.GetValues(typeof(SamsungDriverState)))
            foreach (SamsungDriverStartMode mode in Enum.GetValues(typeof(SamsungDriverStartMode)))
            {
                var kernel = new SamsungKernelDriverReport(status, new[] { new SamsungKernelDriverEntry(category, state, mode) });
                var report = new SamsungFileInspectionReport(SamsungFileInspectionStatus.DirectoryNotFound, kernelDrivers: kernel);
                var decoded = SamsungFileInspectionProtocol.Decode(SamsungFileInspectionProtocol.Encode(report));
                Equal(SamsungFileInspectionStatus.DirectoryNotFound, decoded.Status); Equal(status, decoded.KernelDrivers.Status);
                Equal(kernel.Entries.Length, decoded.KernelDrivers.Entries.Length);
                if (kernel.Entries.Length != 0)
                {
                    var entry = decoded.KernelDrivers.Entries[0]; Equal(category, entry.Category); Equal(state, entry.State); Equal(mode, entry.StartMode);
                }
            }
        });
        Add("kernel driver IPC requires v4 driver result fields and rejects nulls", () =>
        {
            foreach (string field in new[] { "KernelDrivers" }) AssertInvalidInspectionPacket(MutateDriverPacket(root => root.Remove(field)));
            AssertInvalidInspectionPacket(MutateDriverPacket(root => root["Version"] = 3));
            AssertInvalidInspectionPacket(MutateDriverPacket(root => root["KernelDrivers"] = null));
            foreach (string field in new[] { "Status", "Entries" })
                AssertInvalidInspectionPacket(MutateDriverPacket(root => ((JsonObject)root["KernelDrivers"]).Remove(field)));
            foreach (string field in new[] { "Category", "State", "StartMode" })
                AssertInvalidInspectionPacket(MutateDriverPacket(root => ((JsonObject)root["KernelDrivers"]["Entries"][0]).Remove(field)));
            AssertInvalidInspectionPacket(MutateDriverPacket(root => root["KernelDrivers"]["Entries"] = null));
            AssertInvalidInspectionPacket(MutateDriverPacket(root => root["KernelDrivers"]["Entries"][0] = null));
        });
        Add("kernel driver IPC rejects invalid typed observations quotas and contradictory failures", () =>
        {
            AssertInvalidInspectionPacket(MutateDriverPacket(root => root["KernelDrivers"]["Status"] = 999));
            foreach (string field in new[] { "Category", "State", "StartMode" })
            {
                AssertInvalidInspectionPacket(MutateDriverPacket(root => root["KernelDrivers"]["Entries"][0][field] = 999));
                AssertInvalidInspectionPacket(MutateDriverPacket(root => root["KernelDrivers"]["Entries"][0][field] = "private-user"));
            }
            AssertInvalidInspectionPacket(MutateDriverPacket(root => root["KernelDrivers"]["Entries"] = new JsonArray(Enumerable.Range(0, 33).Select(i => root["KernelDrivers"]["Entries"][0].DeepClone()).ToArray())));
            foreach (SamsungDriverQueryStatus status in Enum.GetValues(typeof(SamsungDriverQueryStatus)))
                if (status != SamsungDriverQueryStatus.Complete && status != SamsungDriverQueryStatus.Partial)
                    AssertInvalidInspectionPacket(MutateDriverPacket(root => root["KernelDrivers"]["Status"] = (int)status));
            var maximum = new SamsungFileInspectionReport(kernelDrivers: new SamsungKernelDriverReport(SamsungDriverQueryStatus.Complete, Enumerable.Repeat(DriverEntry(), 32)));
            Equal(32, SamsungFileInspectionProtocol.Decode(SamsungFileInspectionProtocol.Encode(maximum)).KernelDrivers.Entries.Length);
        });
        Add("kernel driver reports and IPC retain no raw names paths usernames or identifiers", () =>
        {
            string privateName = @"Samsung-PrivateName-C:\Users\PrivateName\device-1234";
            var category = SamsungKernelDriverPolicy.Classify(privateName, "private-serial-1234");
            var entry = new SamsungKernelDriverEntry(category.Value, SamsungKernelDriverPolicy.NormalizeState(privateName), SamsungKernelDriverPolicy.NormalizeStartMode(privateName));
            var report = new SamsungFileInspectionReport(kernelDrivers: new SamsungKernelDriverReport(SamsungDriverQueryStatus.Complete, new[] { entry }));
            string output = report.ToDisplayText() + Encoding.UTF8.GetString(SamsungFileInspectionProtocol.Encode(report));
            Check(!output.Contains("PrivateName") && !output.Contains("device-1234") && !output.Contains("private-serial") && !output.Contains(@"C:\Users"), "private driver fields retained");
            byte[] injected = MutateDriverPacket(root => { root["KernelDrivers"]["Entries"][0]["Name"] = privateName; root["KernelDrivers"]["PathName"] = privateName; });
            var decoded = SamsungFileInspectionProtocol.Decode(injected);
            Equal(SamsungFileInspectionStatus.Complete, decoded.Status);
            string clean = decoded.ToDisplayText() + Encoding.UTF8.GetString(SamsungFileInspectionProtocol.Encode(decoded));
            Check(!clean.Contains("PrivateName") && !clean.Contains("device-1234"), "unknown private IPC fields retained");
        });
    }

    private static SamsungKernelDriverEntry DriverEntry(SamsungDriverState state = SamsungDriverState.Running,
        SamsungDriverStartMode mode = SamsungDriverStartMode.Manual)
        => new SamsungKernelDriverEntry(SamsungDriverCategory.SabiName, state, mode);

    private static byte[] MutateDriverPacket(Action<JsonObject> mutation)
    {
        var report = new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, new[] { InspectionEntry() },
            kernelDrivers: new SamsungKernelDriverReport(SamsungDriverQueryStatus.Complete, new[] { DriverEntry() }));
        var root = (JsonObject)JsonNode.Parse(SamsungFileInspectionProtocol.Encode(report));
        mutation(root);
        return Encoding.UTF8.GetBytes(root.ToJsonString());
    }

    private static IEnumerable<SamsungKernelDriverEntry> BoundedDrivers(Action visit)
    {
        for (int i = 0; i < 33; i++) { visit(); yield return DriverEntry(); }
        throw new Exception("driver entry enumeration exceeded bounded lookahead");
    }
}
