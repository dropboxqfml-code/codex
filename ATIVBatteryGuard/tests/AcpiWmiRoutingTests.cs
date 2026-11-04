using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterAcpiWmiRoutingTests()
    {
        Add("static ACPI reader binds the public descriptor to its scoped three-argument method without executing it", () =>
        {
            var result = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiDevice("DEV0", AcpiJoin(
                AcpiWdg(), AcpiMethod("WMAB", 3, AcpiEvidenceBody())))));
            Equal(AcpiRoutingStatus.Complete, result.Status);
            Equal(1, result.MatchingDescriptors); Equal(1, result.MatchingMethods);
            Equal<int?>(3, result.MethodArgumentCount);
            Equal(AcpiMethodSyntaxStatus.Parsed, result.MethodSyntax);
            Equal<bool?>(true, result.DirectMethodIdOneComparison);
            Equal<bool?>(true, result.DirectInputLength21Comparison);
            Equal<bool?>(true, result.LiteralFfReturn);
            Check(!result.CanInvokeMethods && !result.CanWriteHardware, "static syntax granted capabilities");
        });
        Add("static ACPI data buffers packages strings and fields cannot smuggle a fake descriptor or method", () =>
        {
            byte[] fake = AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 3, AcpiEvidenceBody()));
            foreach (byte[] data in new[] {
                AcpiJoin(new byte[] { 0x08 }, AcpiName("DATA"), AcpiBuffer(fake)),
                AcpiJoin(new byte[] { 0x08 }, AcpiName("PKG0"), AcpiPackage(new byte[] { 0x12 }, AcpiJoin(new byte[] { 1 }, fake))),
                AcpiPackage(new byte[] { 0x5b, 0x81 }, fake) })
            {
                var result = AcpiWmiRoutingInspector.Inspect(AcpiTable(data));
                Equal(AcpiRoutingStatus.Complete, result.Status);
                Equal(0, result.MatchingDescriptors); Equal(0, result.MatchingMethods);
                Equal<bool?>(null, result.DirectMethodIdOneComparison);
            }
            var text = AcpiJoin(new byte[] { 0x08 }, AcpiName("TEXT"), new byte[] { 0x0d }, Encoding.ASCII.GetBytes("_WDG WMAB PrivateName"), new byte[] { 0 });
            Equal(0, AcpiWmiRoutingInspector.Inspect(AcpiTable(text)).MatchingDescriptors);
        });
        Add("static ACPI reader never resynchronizes after unsupported or malformed namespace syntax", () =>
        {
            byte[] useful = AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 3, AcpiEvidenceBody()));
            foreach (byte[] prefix in new[] { new byte[] { 0xfe }, new byte[] { 0x08, 0x30, 0x42, 0x41, 0x44 }, new byte[] { 0x10, 0x3f } })
            {
                var result = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(prefix, useful)));
                Equal(AcpiRoutingStatus.Partial, result.Status);
                Equal(0, result.MatchingDescriptors);
                Equal<bool?>(null, result.LiteralFfReturn);
            }
            var invalidParent = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(
                new byte[] { 8, 0x5e }, AcpiName("_WDG"), AcpiBuffer(AcpiDescriptor()))));
            Equal(AcpiRoutingStatus.Partial, invalidParent.Status); Equal(0, invalidParent.MatchingDescriptors);
        });
        Add("static ACPI binding respects namespace and refuses ambiguous duplicate descriptors", () =>
        {
            var wrongScope = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(
                AcpiDevice("DEV0", AcpiWdg()), AcpiDevice("DEV1", AcpiMethod("WMAB", 3, AcpiEvidenceBody())))));
            Equal(1, wrongScope.MatchingDescriptors); Equal(0, wrongScope.MatchingMethods);
            Equal<int?>(null, wrongScope.MethodArgumentCount);
            var duplicate = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiDevice("DEV0", AcpiJoin(
                AcpiWdg(AcpiJoin(AcpiDescriptor(), AcpiDescriptor())), AcpiMethod("WMAB", 3, AcpiEvidenceBody())))));
            Equal(2, duplicate.MatchingDescriptors); Equal(2, duplicate.MatchingMethods);
            Equal(AcpiMethodSyntaxStatus.Ambiguous, duplicate.MethodSyntax);
            Equal<int?>(null, duplicate.MethodArgumentCount); Equal<bool?>(null, duplicate.LiteralFfReturn);
        });
        Add("static ACPI descriptor flags length and instance shape are validated independently", () =>
        {
            foreach (byte[] descriptor in new[] {
                AcpiDescriptor(flags: 0), AcpiDescriptor(flags: 6), AcpiDescriptor(instances: 0),
                AcpiDescriptor().Take(19).ToArray() })
            {
                var result = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiWdg(descriptor)));
                Equal(AcpiRoutingStatus.Partial, result.Status); Equal(0, result.MatchingDescriptors);
            }
            byte[] other = AcpiDescriptor(); other[0] ^= 1;
            var unrelated = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiWdg(other)));
            Equal(AcpiRoutingStatus.Complete, unrelated.Status); Equal(0, unrelated.MatchingDescriptors);
        });
        Add("static ACPI method syntax failure discards partial hints while preserving observed definition shape", () =>
        {
            foreach (byte[] body in new[] { AcpiJoin(AcpiEvidenceBody(), new byte[] { 0xfe }),
                AcpiJoin(new byte[] { 0xa4 }, AcpiPackage(new byte[] { 0x11 }, AcpiJoin(new byte[] { 0x0a, 20 }, new byte[21]))) })
            {
                var result = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 3, body))));
                Equal<int?>(3, result.MethodArgumentCount);
                Equal(AcpiMethodSyntaxStatus.UnsupportedSyntax, result.MethodSyntax);
                Equal<bool?>(null, result.DirectMethodIdOneComparison); Equal<bool?>(null, result.LiteralFfReturn);
            }
            var wrongArgs = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 2, AcpiEvidenceBody()))));
            Equal<int?>(2, wrongArgs.MethodArgumentCount); Equal<bool?>(null, wrongArgs.LiteralFfReturn);
            Equal(AcpiMethodSyntaxStatus.WrongArgumentCount, wrongArgs.MethodSyntax);
        });
        Add("static ACPI syntax hints do not infer helper behavior or reinterpret ones as a byte FF", () =>
        {
            byte[] helper = AcpiMethod("HLP0", 1, new byte[] { 0xa4, 0x0a, 0xff });
            byte[] caller = AcpiMethod("WMAB", 3, AcpiJoin(new byte[] { 0xa4 }, AcpiName("HLP0"), new byte[] { 0x69 }));
            var indirect = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(AcpiWdg(), caller, helper)));
            Equal<bool?>(false, indirect.LiteralFfReturn); Equal<bool?>(false, indirect.DirectMethodIdOneComparison);
            var ones = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 3, new byte[] { 0xa4, 0xff }))));
            Equal<bool?>(false, ones.LiteralFfReturn);
        });
        Add("static ACPI conditional definitions and aliases remain partial and never prove absence", () =>
        {
            foreach (byte[] data in new[] {
                AcpiPackage(new byte[] { 0xa0 }, AcpiJoin(new byte[] { 1 }, AcpiWdg())),
                AcpiJoin(new byte[] { 0x06 }, AcpiName("BUFF"), AcpiName("_WDG")) })
            {
                var result = AcpiWmiRoutingInspector.Inspect(AcpiTable(data));
                Equal(AcpiRoutingStatus.Partial, result.Status); Equal<bool?>(null, result.LiteralFfReturn);
            }
            var prefixEvidence = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(
                AcpiWdg(), AcpiMethod("WMAB", 3, AcpiEvidenceBody()), new byte[] { 0xfe })));
            Equal(AcpiRoutingStatus.Partial, prefixEvidence.Status);
            Equal(1, prefixEvidence.MatchingDescriptors); Equal<int?>(3, prefixEvidence.MethodArgumentCount);
            Check(prefixEvidence.ToDisplayText().Contains("유일성 보장이 아닙니다"), "partial candidates implied uniqueness");
        });
        Add("static ACPI reader checks checksum signature exact length and table limits before exposing facts", () =>
        {
            foreach (byte[] bad in new[] { null, new byte[0], new byte[35], new byte[36],
                AcpiTable(new byte[] { 0xa3 }, "FACP") })
                Equal(AcpiRoutingStatus.InvalidTable, AcpiWmiRoutingInspector.Inspect(bad).Status);
            byte[] corrupt = AcpiTable(AcpiWdg()); corrupt[10] ^= 1;
            Equal(AcpiRoutingStatus.InvalidTable, AcpiWmiRoutingInspector.Inspect(corrupt).Status);
            byte[] trailing = AcpiTable(AcpiWdg()).Concat(new byte[] { 0 }).ToArray();
            Equal(AcpiRoutingStatus.InvalidTable, AcpiWmiRoutingInspector.Inspect(trailing).Status);
            Equal(AcpiRoutingStatus.LimitExceeded, AcpiWmiRoutingInspector.Inspect(new byte[AcpiWmiRoutingInspector.MaximumTableBytes + 1]).Status);
        });
        Add("static ACPI recursive depth and definition count are bounded", () =>
        {
            byte[] nested = AcpiWdg();
            for (int i = 0; i < 35; i++) nested = AcpiDevice("DEV0", nested);
            Equal(AcpiRoutingStatus.LimitExceeded, AcpiWmiRoutingInspector.Inspect(AcpiTable(nested)).Status);
            var methods = new List<byte>();
            for (int i = 0; i < 4097; i++) methods.AddRange(AcpiMethod("MTH0", 0, new byte[0]));
            Equal(AcpiRoutingStatus.LimitExceeded, AcpiWmiRoutingInspector.Inspect(AcpiTable(methods.ToArray())).Status);
        });
        Add("static ACPI reports retain no firmware identities strings bytes paths or execution capability", () =>
        {
            byte[] input = AcpiTable(AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 3, AcpiEvidenceBody())));
            byte[] original = (byte[])input.Clone();
            var report = AcpiWmiRoutingInspector.Inspect(input);
            Check(input.SequenceEqual(original), "caller table mutated");
            Array.Clear(input, 0, input.Length);
            Equal(1, report.MatchingDescriptors);
            foreach (var field in typeof(AcpiWmiRoutingReport).GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                Check(field.IsInitOnly && field.FieldType != typeof(string) && field.FieldType != typeof(byte[]) && field.FieldType != typeof(object), "firmware retained");
            string text = report.ToDisplayText();
            Check(!text.Contains("DEV0") && !text.Contains("WMAB") && !text.Contains("C16C47") && !text.Contains("PRIVATE"), "identity escaped");
            Check(!report.CanInvokeMethods && !report.CanWriteHardware && text.Contains("증명하지 않습니다"), "syntax promoted to hardware evidence");
        });
    }

    private static byte[] AcpiDescriptor(byte flags = 2, byte instances = 1)
        => AcpiJoin(new Guid("C16C47BA-50E3-444A-AF3A-B1C348380001").ToByteArray(), new byte[] { (byte)'A', (byte)'B', instances, flags });
    private static byte[] AcpiWdg(byte[] entries = null)
        => AcpiJoin(new byte[] { 8 }, AcpiName("_WDG"), AcpiBuffer(entries ?? AcpiDescriptor()));
    private static byte[] AcpiName(string value) => Encoding.ASCII.GetBytes(value);
    private static byte[] AcpiDevice(string name, byte[] terms)
        => AcpiPackage(new byte[] { 0x5b, 0x82 }, AcpiJoin(AcpiName(name), terms));
    private static byte[] AcpiMethod(string name, byte args, byte[] body)
        => AcpiPackage(new byte[] { 0x14 }, AcpiJoin(AcpiName(name), new byte[] { args }, body));
    private static byte[] AcpiBuffer(byte[] bytes)
    {
        byte[] size = bytes.Length < 256 ? new byte[] { 0x0a, (byte)bytes.Length }
            : new byte[] { 0x0b, (byte)bytes.Length, (byte)(bytes.Length >> 8) };
        return AcpiPackage(new byte[] { 0x11 }, AcpiJoin(size, bytes));
    }
    private static byte[] AcpiEvidenceBody()
    {
        byte[] reply = new byte[21]; reply[4] = 0xaa; reply[5] = 0xff;
        return AcpiJoin(AcpiPackage(new byte[] { 0xa0 }, new byte[] { 0x93, 0x69, 1, 0xa3 }),
            AcpiPackage(new byte[] { 0xa0 }, new byte[] { 0x93, 0x87, 0x6a, 0x0a, 21, 0xa3 }),
            new byte[] { 0xa4 }, AcpiBuffer(reply));
    }
    private static byte[] AcpiPackage(byte[] opcode, byte[] contents)
    {
        int width = 1;
        while (contents.Length + width >= (width == 1 ? 64 : 1 << (4 + 8 * (width - 1)))) width++;
        int length = contents.Length + width;
        var encoding = new byte[width];
        encoding[0] = width == 1 ? (byte)length : (byte)(((width - 1) << 6) | (length & 15));
        for (int i = 1; i < width; i++) encoding[i] = (byte)(length >> (4 + 8 * (i - 1)));
        return AcpiJoin(opcode, encoding, contents);
    }
    private static byte[] AcpiTable(byte[] aml, string signature = "DSDT")
    {
        byte[] table = new byte[36 + aml.Length];
        Array.Copy(Encoding.ASCII.GetBytes(signature), table, 4);
        Array.Copy(BitConverter.GetBytes(table.Length), 0, table, 4, 4);
        table[8] = 2; Array.Copy(Encoding.ASCII.GetBytes("PRIVATE"), 0, table, 10, 7);
        Array.Copy(aml, 0, table, 36, aml.Length);
        int sum = 0; foreach (byte value in table) sum = (sum + value) & 255;
        table[9] = unchecked((byte)-sum);
        return table;
    }
    private static byte[] AcpiJoin(params byte[][] parts)
    {
        var result = new List<byte>(); foreach (var part in parts) result.AddRange(part); return result.ToArray();
    }
}
