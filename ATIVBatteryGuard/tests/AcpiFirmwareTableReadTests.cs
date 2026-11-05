using System;
using System.Collections.Generic;
using System.Linq;
using ATIVBatteryGuard.AcpiRoutingCheck;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private const uint AcpiTestProvider = 0x41435049;
    private const uint AcpiTestDsdt = 0x54445344;
    private const uint AcpiTestSsdt = 0x54445353;

    private static void RegisterAcpiFirmwareTableReadTests()
    {
        Add("ACPI collection directly reads an unenumerated DSDT and reads only the first of four SSDT entries", () =>
        {
            var fake = new FakeAcpiFirmwareTables(AcpiTestSsdt, AcpiTestSsdt, AcpiTestSsdt, AcpiTestSsdt);
            fake.Dsdt = AcpiTable(AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 3, AcpiEvidenceBody())));
            string text = fake.Collect();
            Equal(2, fake.EnumerationCalls);
            Check(fake.ReadCalls.Select(c => c.Key).SequenceEqual(new[] { AcpiTestDsdt, AcpiTestDsdt, AcpiTestSsdt, AcpiTestSsdt }), "DSDT skipped or duplicate SSDT entries reread");
            Check(fake.ReadCalls.Select(c => c.Value).SequenceEqual(new[] { 0u, (uint)fake.Dsdt.Length, 0u, (uint)fake.Ssdt.Length }), "table size/data passes changed");
            Check(text.Contains("Acpi-routing-v6") && text.Contains("DSDT 목록 항목 수: 0") && text.Contains("SSDT 목록 항목 수: 4"), "revision or observed inventory lost");
            Check(AcpiReadSection(text, "DSDT").Contains("관측한 알려진 SABI WMI 설명자 수: 1"), "the direct DSDT bytes were not inspected");
            Check(text.Contains("모든 SSDT를 확인한 결과가 아닙니다"), "partial table coverage overstated");
            Equal(0, fake.ErrorReads);
            Check(!text.Contains("PRIVATE") && !text.Contains("WMAB") && !text.Contains("C16C47BA"), "firmware identity escaped");
        });
        Add("ACPI collection distinguishes a missing inventory entry from direct DSDT read failures", () =>
        {
            foreach (var sample in new[] {
                new KeyValuePair<int, string>(2, "NotFound"), new KeyValuePair<int, string>(1168, "NotFound"),
                new KeyValuePair<int, string>(5, "AccessDenied"), new KeyValuePair<int, string>(50, "NotSupported"),
                new KeyValuePair<int, string>(999, "Unavailable") })
            {
                var fake = new FakeAcpiFirmwareTables(0x50434146) { Error = sample.Key };
                fake.ReadOverride = (provider, id, buffer, size) => 0;
                string section = AcpiReadSection(fake.Collect(), "DSDT");
                Equal(1, fake.ReadCalls.Count); Equal(AcpiTestDsdt, fake.ReadCalls[0].Key);
                Equal(1, fake.ErrorReads);
                Check(section.Contains("조회: " + sample.Value), "direct read error category lost");
                Check(!section.Contains("조회: 목록에서 미관측"), "unlisted DSDT was not directly queried");
            }
        });
        Add("ACPI enumeration failures malformed sizes and changing lengths never trigger table reads", () =>
        {
            var overrides = new WindowsAcpiRoutingProbe.EnumerateTables[] {
                (provider, buffer, size) => 0,
                (provider, buffer, size) => 4097,
                (provider, buffer, size) => 6,
                (provider, buffer, size) => buffer == null ? 16u : 12u,
                (provider, buffer, size) => buffer == null ? 16u : 20u,
                (provider, buffer, size) => buffer == null ? 16u : 0u,
                (provider, buffer, size) => throw new InvalidOperationException("C:\\Users\\PrivateOwner\\raw-firmware")
            };
            foreach (var enumerate in overrides)
            {
                var fake = new FakeAcpiFirmwareTables(AcpiTestSsdt) { EnumerateOverride = enumerate, Error = 5 };
                string text = fake.Collect();
                Equal(0, fake.ReadCalls.Count);
                Check(!text.Contains("테이블 정의 구문 탐색:") && !text.Contains("PrivateOwner") && !text.Contains("raw-firmware"), "failed inventory exposed table facts or a raw error");
                Check(text.Contains("AccessDenied") || text.Contains("InvalidOrExcessiveResult") || text.Contains("Incomplete") || text.Contains("Unavailable"), "inventory failure became unobserved success");
            }
        });
        Add("ACPI table size bounds reject undersized or excessive results before allocating a data buffer", () =>
        {
            foreach (uint needed in new[] { 1u, 35u, (uint)AcpiWmiRoutingInspector.MaximumTableBytes + 1 })
            {
                var fake = new FakeAcpiFirmwareTables(0x50434146);
                fake.ReadOverride = (provider, id, buffer, size) => needed;
                string section = AcpiReadSection(fake.Collect(), "DSDT");
                Equal(1, fake.ReadCalls.Count); Equal(0, fake.TableBuffers.Count);
                Check(section.Contains("InvalidOrExcessiveResult") && !section.Contains("테이블 정의 구문 탐색:"), "invalid size reached the parser");
            }
        });
        Add("ACPI changed truncated and failed table copies discard bytes instead of exposing partial facts", () =>
        {
            foreach (int adjustment in new[] { -1, 1, int.MinValue })
            {
                var fake = new FakeAcpiFirmwareTables(0x50434146) { Error = 5 };
                fake.ReadOverride = (provider, id, buffer, size) =>
                {
                    if (buffer == null) return (uint)fake.Dsdt.Length;
                    Array.Copy(fake.Dsdt, buffer, fake.Dsdt.Length);
                    return adjustment == int.MinValue ? 0u : (uint)(buffer.Length + adjustment);
                };
                string section = AcpiReadSection(fake.Collect(), "DSDT");
                Equal(2, fake.ReadCalls.Count);
                Check(section.Contains(adjustment == int.MinValue ? "AccessDenied" : "Incomplete"), "copy failure classification lost");
                Check(!section.Contains("테이블 정의 구문 탐색:") && !section.Contains("PRIVATE"), "partial firmware bytes were interpreted or exported");
                Check(fake.TableBuffers.All(b => b.All(value => value == 0)), "failed copy buffer was retained");
            }
        });
        Add("ACPI collector clears inventory and table buffers on success exceptions and enumeration failure", () =>
        {
            var success = new FakeAcpiFirmwareTables(AcpiTestSsdt);
            success.Collect();
            Check(success.InventoryBuffers.Count == 1 && success.TableBuffers.Count == 2, "success did not exercise allocated buffers");
            Check(success.InventoryBuffers.Concat(success.TableBuffers).All(b => b.All(value => value == 0)), "successful collection retained raw bytes");

            var readFailure = new FakeAcpiFirmwareTables(AcpiTestSsdt);
            readFailure.ReadOverride = (provider, id, buffer, size) =>
            {
                if (buffer == null) return 36;
                for (int i = 0; i < buffer.Length; i++) buffer[i] = 0xa5;
                throw new InvalidOperationException("PRIVATE-firmware-error");
            };
            string failed = readFailure.Collect();
            Check(readFailure.InventoryBuffers.Concat(readFailure.TableBuffers).All(b => b.All(value => value == 0)), "exception retained raw bytes");
            Check(failed.Contains("Unavailable") && !failed.Contains("PRIVATE-firmware-error"), "raw read exception escaped");

            var enumerationFailure = new FakeAcpiFirmwareTables(AcpiTestSsdt);
            enumerationFailure.EnumerateOverride = (provider, buffer, size) =>
            {
                if (buffer == null) return 4;
                buffer[0] = 0xa5;
                throw new InvalidOperationException();
            };
            enumerationFailure.Collect();
            Check(enumerationFailure.InventoryBuffers.Count == 1 && enumerationFailure.InventoryBuffers[0].All(value => value == 0), "inventory exception retained raw bytes");
            Equal(0, enumerationFailure.ReadCalls.Count);
        });
        Add("ACPI collector restricts reads to fixed ACPI table IDs and rejects corrupt table headers", () =>
        {
            foreach (byte[] table in new[] { AcpiTable(AcpiWdg(), "FACP"), CorruptAcpiReadTable() })
            {
                var fake = new FakeAcpiFirmwareTables(AcpiTestDsdt, 0x424d5352, 0x50434146) { Dsdt = table };
                string section = AcpiReadSection(fake.Collect(), "DSDT");
                Check(fake.ReadCalls.Select(c => c.Key).SequenceEqual(new[] { AcpiTestDsdt, AcpiTestDsdt }), "another table or provider was requested");
                Check(section.Contains("InvalidTable") && section.Contains("설명자 수: 0"), "corrupt header supplied routing evidence");
                Check(!section.Contains("PRIVATE") && !section.Contains("C16C47BA"), "invalid table content escaped");
            }
        });
    }

    private static byte[] CorruptAcpiReadTable()
    {
        byte[] table = AcpiTable(AcpiWdg()); table[9] ^= 1; return table;
    }

    private static string AcpiReadSection(string text, string label)
    {
        int start = text.IndexOf("[" + label + "]", StringComparison.Ordinal);
        Check(start >= 0, "expected table section absent");
        int end = text.IndexOf("[", start + label.Length + 2, StringComparison.Ordinal);
        return end < 0 ? text.Substring(start) : text.Substring(start, end - start);
    }

    // Memory-only callbacks. The linked probe's parameterless native entry point
    // is never called by these tests, including on Windows test hosts.
    private sealed class FakeAcpiFirmwareTables
    {
        private readonly byte[] ids;
        internal byte[] Dsdt = AcpiTable(new byte[] { 0xa3 });
        internal byte[] Ssdt = AcpiTable(new byte[] { 0xa3 }, "SSDT");
        internal int Error, EnumerationCalls, ErrorReads;
        internal readonly List<KeyValuePair<uint, uint>> ReadCalls = new List<KeyValuePair<uint, uint>>();
        internal readonly List<byte[]> InventoryBuffers = new List<byte[]>();
        internal readonly List<byte[]> TableBuffers = new List<byte[]>();
        internal WindowsAcpiRoutingProbe.EnumerateTables EnumerateOverride;
        internal WindowsAcpiRoutingProbe.ReadFirmwareTable ReadOverride;

        internal FakeAcpiFirmwareTables(params uint[] tables)
        {
            ids = new byte[tables.Length * 4];
            for (int i = 0; i < tables.Length; i++) Array.Copy(BitConverter.GetBytes(tables[i]), 0, ids, i * 4, 4);
        }

        internal string Collect() => WindowsAcpiRoutingProbe.Collect(Enumerate, Read, LastError);

        private uint Enumerate(uint provider, byte[] buffer, uint size)
        {
            Equal(AcpiTestProvider, provider); EnumerationCalls++;
            if (buffer != null) { InventoryBuffers.Add(buffer); Equal((uint)buffer.Length, size); }
            if (EnumerateOverride != null) return EnumerateOverride(provider, buffer, size);
            if (buffer != null) Array.Copy(ids, buffer, ids.Length);
            return (uint)ids.Length;
        }

        private uint Read(uint provider, uint id, byte[] buffer, uint size)
        {
            Equal(AcpiTestProvider, provider);
            Check(id == AcpiTestDsdt || id == AcpiTestSsdt, "non-allowlisted table requested");
            ReadCalls.Add(new KeyValuePair<uint, uint>(id, size));
            if (buffer != null) { TableBuffers.Add(buffer); Equal((uint)buffer.Length, size); }
            if (ReadOverride != null) return ReadOverride(provider, id, buffer, size);
            byte[] source = id == AcpiTestDsdt ? Dsdt : Ssdt;
            if (buffer != null) Array.Copy(source, buffer, source.Length);
            return (uint)source.Length;
        }

        private int LastError() { ErrorReads++; return Error; }
    }
}
