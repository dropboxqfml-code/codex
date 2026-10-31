using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterBatteryCapabilitiesTests()
    {
        Add("standard battery query allowlist has only buffered read access", () =>
        {
            Equal(2, Enum.GetValues(typeof(ReadOnlyBatteryQuery)).Length);
            Equal(0x00294040u, ReadOnlyBatteryQueryPolicy.Code(ReadOnlyBatteryQuery.Tag));
            Equal(0x00294044u, ReadOnlyBatteryQueryPolicy.Code(ReadOnlyBatteryQuery.Information));
            foreach (ReadOnlyBatteryQuery query in Enum.GetValues(typeof(ReadOnlyBatteryQuery)))
            {
                uint code = ReadOnlyBatteryQueryPolicy.Code(query);
                Equal(0x29u, code >> 16); Equal(0u, code & 3); Equal(1u, (code >> 14) & 3);
                Check(code != 0x00298048u, "SET_INFORMATION exposed by query policy");
            }
            foreach (int unknown in new[] { -1, 2, int.MaxValue })
                BatteryThrows<ArgumentOutOfRangeException>(() => ReadOnlyBatteryQueryPolicy.Code((ReadOnlyBatteryQuery)unknown));
        });
        Add("battery information input preserves tag and leaves level and rate zero", () =>
        {
            byte[] request = ReadOnlyBatteryQueryPolicy.InformationRequest(0x89abcdef);
            Equal(12, request.Length);
            Check(request.Take(4).SequenceEqual(new byte[] { 0xef, 0xcd, 0xab, 0x89 }), "tag byte order changed");
            Check(request.Skip(4).All(value => value == 0), "nonzero information level or rate");
            request[4] = 0xff;
            Check(ReadOnlyBatteryQueryPolicy.InformationRequest(0x89abcdef).Skip(4).All(value => value == 0), "request buffer reused");
            BatteryThrows<ArgumentOutOfRangeException>(() => ReadOnlyBatteryQueryPolicy.InformationRequest(0));
        });
        Add("battery capabilities decode exact SDK response and preserve unknown flag bits", () =>
        {
            var response = new byte[36]; response[0] = 3; response[3] = 0x80;
            uint flags;
            Check(ReadOnlyBatteryQueryPolicy.TryCapabilities(response, 36, out flags), "valid BATTERY_INFORMATION rejected");
            Equal(0x80000003u, flags);
            response[0] = response[3] = 0;
            Check(ReadOnlyBatteryQueryPolicy.TryCapabilities(response, 36, out flags), "zero capabilities rejected");
            Equal(0u, flags);
            Equal(0x80000003u, ReadOnlyBatteryQueryPolicy.UInt32(new byte[] { 3, 0, 0, 0x80 }));
        });
        Add("battery malformed buffers clear prior flags and never accept partial structures", () =>
        {
            foreach (byte[] response in new[] { null, new byte[0], new byte[3], new byte[35], new byte[37], new byte[4096] })
            {
                uint flags = uint.MaxValue;
                Check(!ReadOnlyBatteryQueryPolicy.TryCapabilities(response, 36, out flags), "wrong buffer size accepted"); Equal(0u, flags);
            }
            foreach (uint returned in new[] { 0u, 4u, 35u, 37u, uint.MaxValue })
            {
                uint flags = uint.MaxValue;
                Check(!ReadOnlyBatteryQueryPolicy.TryCapabilities(new byte[36], returned, out flags), "wrong native byte count accepted"); Equal(0u, flags);
            }
            foreach (byte[] bytes in new[] { null, new byte[0], new byte[3] })
                BatteryThrows<ArgumentException>(() => ReadOnlyBatteryQueryPolicy.UInt32(bytes));
        });
        Add("battery absent flags stay unknown while successful zero is explicit absence", () =>
        {
            var zero = new BatteryCapabilityEntry(1, BatteryProbeStatus.Complete, 0);
            Equal<bool?>(false, zero.ChargeRequestSupported); Equal<bool?>(false, zero.DischargeRequestSupported);
            foreach (BatteryProbeStatus status in Enum.GetValues(typeof(BatteryProbeStatus)))
            {
                if (status == BatteryProbeStatus.Complete) continue;
                var missing = new BatteryCapabilityEntry(1, status, uint.MaxValue);
                Equal(status, missing.Status); Equal<uint?>(null, missing.Capabilities);
                Equal<bool?>(null, missing.ChargeRequestSupported); Equal<bool?>(null, missing.DischargeRequestSupported);
            }
            Equal(BatteryProbeStatus.InvalidResponse, new BatteryCapabilityEntry(1, BatteryProbeStatus.Complete).Status);
        });
        Add("battery entries reject invalid indices and normalize unknown status", () =>
        {
            foreach (int index in new[] { int.MinValue, 0, 9, int.MaxValue })
                BatteryThrows<ArgumentOutOfRangeException>(() => new BatteryCapabilityEntry(index, BatteryProbeStatus.Complete, 3));
            var invalid = new BatteryCapabilityEntry(1, (BatteryProbeStatus)999, 3);
            Equal(BatteryProbeStatus.InvalidResponse, invalid.Status); Equal<uint?>(null, invalid.Capabilities);
            Equal(8, new BatteryCapabilityEntry(8, BatteryProbeStatus.Complete, 3).Index);
        });
        Add("battery report keeps failures distinct and discards stale successful entries", () =>
        {
            var stale = new[] { new BatteryCapabilityEntry(1, BatteryProbeStatus.Complete, 3) };
            foreach (BatteryProbeStatus status in Enum.GetValues(typeof(BatteryProbeStatus)))
            {
                if (status == BatteryProbeStatus.Complete || status == BatteryProbeStatus.Partial) continue;
                var report = new WindowsBatteryCapabilitiesReport(status, stale);
                Equal(status, report.Status); Equal(0, report.Entries.Length);
                Check(report.ToDisplayText().Contains(WindowsBatteryCapabilitiesReport.StatusText(status)), "failure status hidden");
            }
            Equal(BatteryProbeStatus.InvalidResponse, new WindowsBatteryCapabilitiesReport((BatteryProbeStatus)999, stale).Status);
            Equal(BatteryProbeStatus.NoDevices, new WindowsBatteryCapabilitiesReport(BatteryProbeStatus.Complete).Status);
        });
        Add("battery partial reports preserve each missing result without reusing flags", () =>
        {
            var report = new WindowsBatteryCapabilitiesReport(BatteryProbeStatus.Complete, new[] {
                new BatteryCapabilityEntry(1, BatteryProbeStatus.Complete, 1),
                new BatteryCapabilityEntry(2, BatteryProbeStatus.AccessDenied, 3),
                new BatteryCapabilityEntry(3, BatteryProbeStatus.TimedOut, 3) });
            Equal(BatteryProbeStatus.Partial, report.Status); Equal(3, report.Entries.Length);
            Equal<uint?>(1, report.Entries[0].Capabilities); Equal<uint?>(null, report.Entries[1].Capabilities);
            Equal(BatteryProbeStatus.AccessDenied, report.Entries[1].Status); Equal(BatteryProbeStatus.TimedOut, report.Entries[2].Status);
            string text = report.ToDisplayText();
            Check(text.Contains("권한 없음") && text.Contains("시간 초과"), "partial failure reasons omitted");
        });
        Add("battery report rejects duplicate and null device entries", () =>
        {
            var entry = new BatteryCapabilityEntry(1, BatteryProbeStatus.Complete, 3);
            foreach (var entries in new[] { new[] { entry, entry }, new[] { entry, null }, new BatteryCapabilityEntry[] { null } })
            {
                var report = new WindowsBatteryCapabilitiesReport(BatteryProbeStatus.Complete, entries);
                Equal(BatteryProbeStatus.InvalidResponse, report.Status); Equal(0, report.Entries.Length);
            }
        });
        Add("battery report snapshots inputs and protects returned entry arrays", () =>
        {
            var original = new BatteryCapabilityEntry(1, BatteryProbeStatus.Complete, 3);
            var input = new[] { original };
            var report = new WindowsBatteryCapabilitiesReport(BatteryProbeStatus.Complete, input);
            input[0] = null; report.Entries[0] = null;
            Equal(1, report.Entries.Length); Equal(original, report.Entries[0]); Equal<uint?>(3, report.Entries[0].Capabilities);
        });
        Add("battery enumeration stops at eight and exposes the incomplete limit", () =>
        {
            int visited = 0;
            var report = new WindowsBatteryCapabilitiesReport(BatteryProbeStatus.Complete, BoundedBatteryEntries(() => visited++));
            Equal(8, report.Entries.Length); Equal(9, visited); Check(report.Limited, "enumeration truncation hidden");
            var exact = new WindowsBatteryCapabilitiesReport(BatteryProbeStatus.Complete,
                Enumerable.Range(1, 8).Select(index => new BatteryCapabilityEntry(index, BatteryProbeStatus.Complete, 0)));
            Equal(8, exact.Entries.Length); Check(!exact.Limited, "eight devices incorrectly treated as truncated");
            Check(report.ToDisplayText().Contains("최대 8개"), "limit missing from display");
        });
        Add("battery request flags never authorize writes or imply an 80 percent limit", () =>
        {
            foreach (uint flags in new[] { 0u, 1u, 2u, 3u, uint.MaxValue })
            {
                var entry = new BatteryCapabilityEntry(1, BatteryProbeStatus.Complete, flags);
                var report = new WindowsBatteryCapabilitiesReport(BatteryProbeStatus.Complete, new[] { entry });
                Check(!entry.HardwareWriteAllowed && !report.HardwareWriteAllowed, "capability flag grants write access");
                Equal<bool?>((flags & 1) != 0, entry.ChargeRequestSupported); Equal<bool?>((flags & 2) != 0, entry.DischargeRequestSupported);
                string text = report.ToDisplayText();
                Check(text.Contains("80% 충전 상한이나 OEM 기능 지원의 증거가 아닙니다") && text.Contains("실제 충전 제어: 미지원") &&
                    text.Contains("표시된 지원 요청도 실행하지 않았습니다"), "request support misrepresented as verified charge control");
                var diagnostics = new HardwareProbeReport(windowsBatteryCapabilities: report);
                Check(diagnostics.ToDisplayText().Contains(text) && !diagnostics.HardwareWriteAllowed, "detailed diagnostics omit the read-only capability assessment");
            }
        });
        Add("battery worker protocol round trips every status and eight flag results", () =>
        {
            foreach (BatteryProbeStatus status in Enum.GetValues(typeof(BatteryProbeStatus)))
            {
                var report = new WindowsBatteryCapabilitiesReport(status, new[] { new BatteryCapabilityEntry(1, BatteryProbeStatus.Complete, 0) }, true);
                AssertBatteryRoundTrip(report);
            }
            AssertBatteryRoundTrip(new WindowsBatteryCapabilitiesReport(BatteryProbeStatus.Partial, new[] {
                new BatteryCapabilityEntry(1, BatteryProbeStatus.Complete, uint.MaxValue), new BatteryCapabilityEntry(2, BatteryProbeStatus.TimedOut) }));
            AssertBatteryRoundTrip(new WindowsBatteryCapabilitiesReport(BatteryProbeStatus.Complete,
                Enumerable.Range(1, 8).Select(index => new BatteryCapabilityEntry(index, BatteryProbeStatus.Complete, (uint)index))));
            foreach (string entry in new[] { "{\"Index\":1,\"Status\":1,\"Flags\":null}", "{\"Index\":1,\"Status\":1}" })
            {
                var missing = BatteryCapabilitiesProtocol.Decode(Encoding.UTF8.GetBytes(BatteryPacket("[" + entry + "]")));
                Check(missing.Status != BatteryProbeStatus.Complete && missing.Entries.All(result =>
                    !result.Capabilities.HasValue && !result.ChargeRequestSupported.HasValue && !result.DischargeRequestSupported.HasValue),
                    "missing wire flags converted to successful zero or supported requests");
            }
            BatteryThrows<ArgumentNullException>(() => BatteryCapabilitiesProtocol.Encode(null));
        });
        Add("battery worker protocol rejects malformed packets and invalid fields", () =>
        {
            foreach (string packet in new[] {
                "", "{", "null", "[]", "{}", "not-json",
                BatteryPacket("[]", version: 0), BatteryPacket("[]", version: 2), BatteryPacket("[]", status: 999),
                BatteryPacket("null"), BatteryPacket("[null]"), BatteryPacket("[{\"Index\":0,\"Status\":1,\"Flags\":3}]"),
                BatteryPacket("[{\"Index\":9,\"Status\":1,\"Flags\":3}]"), BatteryPacket("[{\"Index\":1,\"Status\":999,\"Flags\":3}]"),
                BatteryPacket("[{\"Index\":1,\"Status\":1,\"Flags\":-1}]"), BatteryPacket("[{\"Index\":1,\"Status\":1,\"Flags\":4294967296}]"),
                BatteryPacket("[{\"Status\":1,\"Flags\":3}]"), BatteryPacket("[{\"Index\":1,\"Flags\":3}]"), BatteryPacket("[{\"Index\":1,\"Status\":1}]"),
                BatteryPacket("[{\"Index\":1,\"Status\":1,\"Flags\":3},{\"Index\":1,\"Status\":1,\"Flags\":3}]"),
                "{\"Version\":1,\"Status\":1,\"Limited\":false}",
                "{\"Status\":1,\"Limited\":false,\"Entries\":[]}", "{\"Version\":1,\"Limited\":false,\"Entries\":[]}",
                "{\"Version\":1,\"Status\":1,\"Entries\":[]}" })
                AssertInvalidBatteryPacket(Encoding.UTF8.GetBytes(packet));
            AssertInvalidBatteryPacket(null);
            AssertInvalidBatteryPacket(new byte[] { 0xff, 0xfe, 0xfd });
            foreach (string suffix in new[] { " {}", " []", " true", " garbage", "\0", BatteryPacket("[]") })
                AssertInvalidBatteryPacket(Encoding.UTF8.GetBytes(BatteryPacket("[]") + suffix), "trailing JSON data");
        });
        Add("battery worker protocol bounds byte count device count and object graph", () =>
        {
            AssertInvalidBatteryPacket(new byte[BatteryCapabilitiesProtocol.MaximumBytes + 1]);
            foreach (int count in new[] { 9, 128, 129, 200 })
            {
                string entries = "[" + string.Join(",", Enumerable.Repeat("{\"Index\":1,\"Status\":1,\"Flags\":3}", count)) + "]";
                byte[] bytes = Encoding.UTF8.GetBytes(BatteryPacket(entries));
                Check(bytes.Length < BatteryCapabilitiesProtocol.MaximumBytes, "graph quota test unexpectedly hits byte quota");
                AssertInvalidBatteryPacket(bytes);
            }
            string valid = BatteryPacket("[]", status: (int)BatteryProbeStatus.NoDevices);
            Equal(BatteryProbeStatus.NoDevices, BatteryCapabilitiesProtocol.Decode(Encoding.UTF8.GetBytes(" \r\n\t" + valid + "\t\r\n ")).Status);
            string nested = "0";
            for (int depth = 0; depth < 17; depth++) nested = "{\"Nested\":" + nested + "}";
            AssertInvalidBatteryPacket(Encoding.UTF8.GetBytes(valid.Replace("\"Version\":1", "\"Unknown\":" + nested + ",\"Version\":1")), "excessively nested worker field");
            byte[] exact = Encoding.UTF8.GetBytes(valid.PadRight(BatteryCapabilitiesProtocol.MaximumBytes));
            Equal(BatteryCapabilitiesProtocol.MaximumBytes, exact.Length);
            Equal(BatteryProbeStatus.NoDevices, BatteryCapabilitiesProtocol.Decode(exact).Status);
        });
        Add("battery worker packets disclose only bounded facts and cannot retain private fields", () =>
        {
            var report = new WindowsBatteryCapabilitiesReport(BatteryProbeStatus.Complete,
                new[] { new BatteryCapabilityEntry(1, BatteryProbeStatus.Complete, uint.MaxValue) });
            byte[] bytes = BatteryCapabilitiesProtocol.Encode(report);
            using (JsonDocument packet = JsonDocument.Parse(bytes))
            {
                Equal("Entries,Limited,Status,Version", string.Join(",", packet.RootElement.EnumerateObject().Select(property => property.Name).OrderBy(name => name, StringComparer.Ordinal)));
                Equal("Flags,Index,Status", string.Join(",", packet.RootElement.GetProperty("Entries")[0].EnumerateObject().Select(property => property.Name).OrderBy(name => name, StringComparer.Ordinal)));
            }
            string injected = BatteryPacket("[{\"Index\":1,\"Status\":1,\"Flags\":3,\"DevicePath\":\"C:\\\\Users\\\\PrivateName\\\\device\",\"Tag\":12345}]")
                .Replace("\"Version\":1", "\"Error\":\"private-exception-secret\",\"SerialNumber\":\"private-serial-secret\",\"Version\":1");
            var decoded = BatteryCapabilitiesProtocol.Decode(Encoding.UTF8.GetBytes(injected));
            string output = decoded.ToDisplayText() + Encoding.UTF8.GetString(BatteryCapabilitiesProtocol.Encode(decoded));
            Check(!output.Contains("PrivateName") && !output.Contains("private-exception-secret") && !output.Contains("private-serial-secret") && !output.Contains("12345"), "private worker fields retained");
            Check(!decoded.HardwareWriteAllowed && decoded.Entries.All(entry => !entry.HardwareWriteAllowed), "worker result grants hardware access");
            const string ignoredJson = "\"Ignored\":\"escaped quote: \\\" slash: \\\\ braces: }{][ private-token\",";
            string escaped = BatteryPacket("[]", status: (int)BatteryProbeStatus.NoDevices).Replace("\"Version\":1", ignoredJson + "\"Version\":1");
            var safe = BatteryCapabilitiesProtocol.Decode(Encoding.UTF8.GetBytes(escaped));
            Equal(BatteryProbeStatus.NoDevices, safe.Status);
            Check(!Encoding.UTF8.GetString(BatteryCapabilitiesProtocol.Encode(safe)).Contains("private-token"), "escaped unknown string retained");
        });
    }

    private static void BatteryThrows<TException>(Action action) where TException : Exception
    {
        try { action(); }
        catch (TException) { return; }
        throw new Exception("expected " + typeof(TException).Name);
    }

    private static IEnumerable<BatteryCapabilityEntry> BoundedBatteryEntries(Action visit)
    {
        for (int index = 1; index <= 8; index++)
        {
            visit(); yield return new BatteryCapabilityEntry(index, BatteryProbeStatus.Complete, 0);
        }
        visit(); yield return new BatteryCapabilityEntry(1, BatteryProbeStatus.Complete, 0);
        throw new Exception("enumeration continued after the bounded lookahead");
    }

    private static void AssertBatteryRoundTrip(WindowsBatteryCapabilitiesReport expected)
    {
        byte[] encoded = BatteryCapabilitiesProtocol.Encode(expected);
        Check(encoded.Length > 0 && encoded.Length <= BatteryCapabilitiesProtocol.MaximumBytes, "unbounded packet");
        var actual = BatteryCapabilitiesProtocol.Decode(encoded);
        Equal(expected.Status, actual.Status); Equal(expected.Limited, actual.Limited); Equal(expected.Entries.Length, actual.Entries.Length);
        for (int index = 0; index < expected.Entries.Length; index++)
        {
            Equal(expected.Entries[index].Index, actual.Entries[index].Index); Equal(expected.Entries[index].Status, actual.Entries[index].Status);
            Equal(expected.Entries[index].Capabilities, actual.Entries[index].Capabilities);
        }
        Check(!actual.HardwareWriteAllowed && actual.Entries.All(entry => !entry.HardwareWriteAllowed), "round trip enabled writes");
    }

    private static string BatteryPacket(string entries, int version = 1, int status = (int)BatteryProbeStatus.Complete)
    {
        return "{\"Version\":" + version + ",\"Status\":" + status + ",\"Limited\":false,\"Entries\":" + entries + "}";
    }

    private static void AssertInvalidBatteryPacket(byte[] bytes, string context = "packet")
    {
        var report = BatteryCapabilitiesProtocol.Decode(bytes);
        Check(report.Status == BatteryProbeStatus.InvalidResponse, context + " returned " + report.Status + " instead of InvalidResponse"); Equal(0, report.Entries.Length);
        Check(!report.HardwareWriteAllowed, "invalid packet grants write access");
    }
}
