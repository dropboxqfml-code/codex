using System;
using System.Linq;
using System.Reflection;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterAcpiExtendedSyntaxTests()
    {
        Add("extended static syntax parses Acquire raw Word timeout and Release without interpreting timeout bytes as FF", () =>
        {
            var report = InspectAcpiFlow(AcpiReturn(AcpiName("HLP0")),
                AcpiMethod("HLP0", 0, AcpiJoin(
                    AcpiExtended(0x23, AcpiName("MUT0"), new byte[] { 0xff, 0xff }),
                    AcpiExtended(0x27, AcpiName("MUT0")), new byte[] { 0xa4, 0 })),
                AcpiExtended(0x01, AcpiName("MUT0"), new byte[] { 0 }));
            Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
            Equal<int?>(1, report.Flow.RootCallSites);
            Equal(1, report.Flow.ParsedHelpers); Equal(0, report.Flow.UnsupportedHelpers);
            Equal(AcpiSyntaxFailureKind.None, report.Flow.RootSyntaxFailure);
            Equal(AcpiSyntaxFailureKind.None, report.Flow.HelperSyntaxFailures);
            Equal<AcpiSyntaxOperation?>(AcpiSyntaxOperation.Acquire | AcpiSyntaxOperation.Release,
                report.Flow.ParsedHelperExtendedSyntax);
            Equal<int?>(1, report.Flow.ParsedHelperReturnStatements);
            Equal<AcpiReturnSyntax?>(AcpiReturnSyntax.IntegerLiteral, report.Flow.ParsedHelperReturnSyntax);
            Equal<bool?>(false, report.Flow.ParsedHelperLiteralFfReturn);
            Equal<bool?>(false, report.LiteralFfReturn);
        });
        Add("extended static syntax records event and timing operands as syntax without executing waits", () =>
        {
            byte[] body = AcpiJoin(
                AcpiExtended(0x22, new byte[] { 0x0c, 0xff, 0xff, 0xff, 0xff }),
                AcpiExtended(0x21, new byte[] { 0x0a, 0xff }),
                AcpiExtended(0x25, AcpiName("EVT0"), new byte[] { 0x0b, 0xff, 0xff }),
                AcpiExtended(0x24, AcpiName("EVT0")), AcpiExtended(0x26, AcpiName("EVT0")),
                new byte[] { 0xa4, 0x6a });
            var report = InspectAcpiFlow(body, AcpiExtended(0x02, AcpiName("EVT0")));
            Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
            Equal<AcpiSyntaxOperation?>(AcpiSyntaxOperation.Sleep | AcpiSyntaxOperation.Stall |
                AcpiSyntaxOperation.Wait | AcpiSyntaxOperation.Signal | AcpiSyntaxOperation.Reset,
                report.Flow.RootExtendedSyntax);
            Equal<int?>(0, report.Flow.RootCallSites); Equal<int?>(1, report.Flow.RootReturnStatements);
            Equal<AcpiReturnSyntax?>(AcpiReturnSyntax.Argument2, report.Flow.RootReturnSyntax);
            Equal(AcpiSyntaxFailureKind.None, report.Flow.RootSyntaxFailure);
            Equal<bool?>(false, report.LiteralFfReturn);
            Equal<AcpiSyntaxOperation?>(null, report.Flow.ParsedHelperExtendedSyntax);
            Check(!report.Flow.CanInvokeMethods && !report.Flow.CanWriteHardware, "timing syntax granted execution");
        });
        Add("extended static reference and target operands never invoke a method with the referenced name", () =>
        {
            byte[][] bodies = {
                AcpiJoin(AcpiExtended(0x23, AcpiName("HLP0"), new byte[] { 0xff, 0xff }), new byte[] { 0xa4, 0x6a }),
                AcpiJoin(AcpiExtended(0x27, AcpiName("HLP0")), new byte[] { 0xa4, 0x6a }),
                AcpiJoin(AcpiExtended(0x25, AcpiName("HLP0"), new byte[] { 0 }), new byte[] { 0xa4, 0x6a }),
                AcpiJoin(AcpiExtended(0x24, AcpiName("HLP0")), new byte[] { 0xa4, 0x6a }),
                AcpiJoin(AcpiExtended(0x26, AcpiName("HLP0")), new byte[] { 0xa4, 0x6a }),
                AcpiJoin(AcpiExtended(0x12, AcpiName("HLP0"), new byte[] { 0x60 }), new byte[] { 0xa4, 0x6a }),
                AcpiJoin(AcpiExtended(0x28, new byte[] { 0 }, AcpiName("HLP0")), new byte[] { 0xa4, 0x6a }),
                AcpiJoin(AcpiExtended(0x29, new byte[] { 0 }, AcpiName("HLP0")), new byte[] { 0xa4, 0x6a }) };
            foreach (byte arguments in new byte[] { 0, 1 })
                foreach (byte[] body in bodies)
                {
                    var report = InspectAcpiFlow(body, AcpiMethod("HLP0", arguments, new byte[] { 0xa4, 0x0a, 0xff }));
                    Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
                    Equal<int?>(0, report.Flow.RootCallSites); Equal<int?>(1, report.Flow.RootReturnStatements);
                    Equal(0, report.Flow.InspectedHelpers);
                    Equal<bool?>(null, report.Flow.ParsedHelperLiteralFfReturn);
                    Equal<bool?>(null, report.Flow.HelperLiteralFfReturn);
                    Equal<bool?>(false, report.LiteralFfReturn);
                }
        });
        Add("extended static syntax consumes BCD fixed values debug target CreateField and Fatal raw data without evaluation", () =>
        {
            byte[] body = AcpiJoin(
                new byte[] { 0x70 }, AcpiExtended(0x30), new byte[] { 0x60 },
                new byte[] { 0x70 }, AcpiExtended(0x33), new byte[] { 0x61 },
                new byte[] { 0x70, 0 }, AcpiExtended(0x31),
                AcpiExtended(0x28, new byte[] { 0x0a, 0x99, 0x62 }),
                AcpiExtended(0x29, new byte[] { 0x0a, 9, 0x63 }),
                AcpiExtended(0x13, new byte[] { 0x6a, 0, 0x0a, 8 }, AcpiName("FLD0")),
                AcpiExtended(0x32, new byte[] { 1, 0xff, 0xff, 0xff, 0xff, 0 }),
                new byte[] { 0xa4, 0x6a });
            var report = InspectAcpiFlow(body);
            Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
            Equal<AcpiSyntaxOperation?>(AcpiSyntaxOperation.Revision | AcpiSyntaxOperation.Timer |
                AcpiSyntaxOperation.Debug | AcpiSyntaxOperation.FromBcd | AcpiSyntaxOperation.ToBcd |
                AcpiSyntaxOperation.CreateField | AcpiSyntaxOperation.Fatal, report.Flow.RootExtendedSyntax);
            Equal(AcpiSyntaxFailureKind.None, report.Flow.RootSyntaxFailure);
            Equal<int?>(0, report.Flow.RootCallSites); Equal<int?>(1, report.Flow.RootReturnStatements);
            Equal<bool?>(false, report.LiteralFfReturn);
        });
        Add("extended syntax rejects value-only statements invalid SimpleName and CreateField method collisions", () =>
        {
            foreach (var sample in new[] {
                new System.Collections.Generic.KeyValuePair<byte, AcpiSyntaxOperation>(0x30, AcpiSyntaxOperation.Revision),
                new System.Collections.Generic.KeyValuePair<byte, AcpiSyntaxOperation>(0x33, AcpiSyntaxOperation.Timer),
                new System.Collections.Generic.KeyValuePair<byte, AcpiSyntaxOperation>(0x31, AcpiSyntaxOperation.Debug) })
                CheckAcpiRootFailure(InspectAcpiFlow(AcpiJoin(AcpiExtended(sample.Key), new byte[] { 0xa4, 0x6a })),
                    AcpiSyntaxFailureKind.UnresolvedStatement, sample.Value);

            CheckAcpiRootFailure(InspectAcpiFlow(AcpiJoin(
                AcpiExtended(0x12, AcpiExtended(0x31), new byte[] { 0x60 }), new byte[] { 0xa4, 0x6a })),
                AcpiSyntaxFailureKind.UnsupportedReference, AcpiSyntaxOperation.CondRefOf);
            var collision = InspectAcpiFlow(AcpiJoin(
                AcpiExtended(0x13, new byte[] { 0x6a, 0, 0x0a, 8 }, AcpiName("HLP0")),
                new byte[] { 0xa4, 0x6a }), AcpiMethod("HLP0", 0, new byte[] { 0xa4, 0x0a, 0xff }));
            CheckAcpiRootFailure(collision, AcpiSyntaxFailureKind.MethodNameCollision, AcpiSyntaxOperation.CreateField);
        });
        Add("extended static analysis keeps table loads and dynamic namespace definitions closed with fixed reasons", () =>
        {
            var loads = new[] {
                new System.Collections.Generic.KeyValuePair<byte[], AcpiSyntaxOperation>(
                    AcpiExtended(0x1f, new byte[6]), AcpiSyntaxOperation.LoadTable),
                new System.Collections.Generic.KeyValuePair<byte[], AcpiSyntaxOperation>(
                    AcpiExtended(0x20, AcpiName("TAB0"), new byte[] { 0x60 }), AcpiSyntaxOperation.Load),
                new System.Collections.Generic.KeyValuePair<byte[], AcpiSyntaxOperation>(
                    AcpiExtended(0x2a, AcpiName("TAB0")), AcpiSyntaxOperation.Unload) };
            foreach (var sample in loads)
                CheckAcpiRootFailure(InspectAcpiFlow(AcpiJoin(sample.Key, new byte[] { 0xa4, 0x6a })),
                    AcpiSyntaxFailureKind.UnsupportedExtendedOpcode, sample.Value);
            CheckAcpiRootFailure(InspectAcpiFlow(AcpiJoin(new byte[] { 8 }, AcpiName("DATA"),
                new byte[] { 0, 0xa4, 0x6a })), AcpiSyntaxFailureKind.DynamicNamespace, AcpiSyntaxOperation.NameDefinition);
            CheckAcpiRootFailure(InspectAcpiFlow(AcpiJoin(new byte[] { 6 }, AcpiName("SRC0"), AcpiName("DST0"),
                new byte[] { 0xa4, 0x6a })), AcpiSyntaxFailureKind.DynamicNamespace, AcpiSyntaxOperation.OtherNamespaceDefinition);
        });
        Add("extended syntax classifies unknown root and helper operations without exporting raw opcodes or firmware strings", () =>
        {
            var root = InspectAcpiFlow(new byte[] { 0xfe });
            CheckAcpiRootFailure(root, AcpiSyntaxFailureKind.UnsupportedOpcode, AcpiSyntaxOperation.UnrecognizedPrimary);
            var helper = InspectAcpiFlow(AcpiReturn(AcpiName("HLP0")), AcpiMethod("HLP0", 0, new byte[] { 0x5b, 0xfe }));
            Equal(AcpiMethodSyntaxStatus.Parsed, helper.MethodSyntax);
            Equal(AcpiMethodFlowStatus.Partial, helper.Flow.Status);
            Check((helper.Flow.HelperSyntaxFailures & AcpiSyntaxFailureKind.UnsupportedExtendedOpcode) != 0, "unknown helper reason lost");
            Check((helper.Flow.HelperFailureOperations & AcpiSyntaxOperation.UnrecognizedExtended) != 0, "unknown helper operation category lost");
            Equal<AcpiSyntaxOperation?>(null, helper.Flow.ParsedHelperExtendedSyntax);
            foreach (string text in new[] { root.ToDisplayText(), helper.ToDisplayText() })
                foreach (string raw in new[] { "0xFE", "0xfe", "HLP0", "WMAB", "PRIVATE", "C16C47BA" })
                    Check(!text.Contains(raw), "a raw firmware value escaped fixed failure categories");
        });
        Add("extended syntax rejects truncated Acquire Word Fatal raw data and CreateField names without partial facts", () =>
        {
            var malformed = new[] {
                new System.Collections.Generic.KeyValuePair<byte[], AcpiSyntaxOperation>(
                    AcpiExtended(0x23, AcpiName("MUT0"), new byte[] { 0xff }), AcpiSyntaxOperation.Acquire),
                new System.Collections.Generic.KeyValuePair<byte[], AcpiSyntaxOperation>(
                    AcpiExtended(0x32, new byte[] { 1, 2, 3, 4 }), AcpiSyntaxOperation.Fatal),
                new System.Collections.Generic.KeyValuePair<byte[], AcpiSyntaxOperation>(
                    AcpiExtended(0x32, new byte[] { 1, 2, 3, 4, 5 }), AcpiSyntaxOperation.Fatal),
                new System.Collections.Generic.KeyValuePair<byte[], AcpiSyntaxOperation>(
                    AcpiExtended(0x13, new byte[] { 0x6a, 0, 0x0a, 8 }, AcpiName("BAD")), AcpiSyntaxOperation.CreateField) };
            foreach (var sample in malformed)
                CheckAcpiRootFailure(InspectAcpiFlow(sample.Key), AcpiSyntaxFailureKind.InvalidEncoding, sample.Value);
        });
        Add("extended flow retains scoped facts from parsed helpers while discarding every unsupported helper prefix fact", () =>
        {
            var partial = InspectAcpiFlow(AcpiJoin(new byte[] { 0x70 }, AcpiName("UNKN"), new byte[] { 0x60 },
                AcpiReturn(AcpiName("HLP0"))), AcpiMethod("HLP0", 0, new byte[] { 0xa4, 0x0a, 0xff }));
            Equal(AcpiMethodFlowStatus.Partial, partial.Flow.Status);
            Equal<bool?>(null, partial.Flow.HelperLiteralFfReturn);
            Equal<bool?>(true, partial.Flow.ParsedHelperLiteralFfReturn);
            Equal<int?>(1, partial.Flow.ParsedHelperReturnStatements);
            Equal<AcpiReturnSyntax?>(AcpiReturnSyntax.IntegerLiteral, partial.Flow.ParsedHelperReturnSyntax);
            Equal<AcpiSyntaxOperation?>(AcpiSyntaxOperation.None, partial.Flow.ParsedHelperExtendedSyntax);
            Equal(AcpiSyntaxFailureKind.None, partial.Flow.HelperSyntaxFailures);
            Equal<bool?>(false, partial.LiteralFfReturn);

            var unsupported = InspectAcpiFlow(AcpiReturn(AcpiName("HLP0")),
                AcpiMethod("HLP0", 0, AcpiJoin(AcpiExtended(0x22, new byte[] { 0 }), AcpiName("HLP1"),
                    new byte[] { 0xa4, 0x0a, 0xff, 0x5b, 0xfe })),
                AcpiMethod("HLP1", 0, new byte[] { 0xa4, 0x0a, 0xff }));
            Equal(AcpiMethodFlowStatus.Partial, unsupported.Flow.Status);
            Equal(1, unsupported.Flow.InspectedHelpers); Equal(0, unsupported.Flow.ParsedHelpers);
            Equal(1, unsupported.Flow.UnsupportedHelpers);
            Equal<bool?>(null, unsupported.Flow.HelperLiteralFfReturn);
            Equal<bool?>(null, unsupported.Flow.ParsedHelperLiteralFfReturn);
            Equal<int?>(null, unsupported.Flow.ParsedHelperReturnStatements);
            Equal<AcpiReturnSyntax?>(null, unsupported.Flow.ParsedHelperReturnSyntax);
            Equal<AcpiSyntaxOperation?>(null, unsupported.Flow.ParsedHelperExtendedSyntax);
            Check((unsupported.Flow.HelperSyntaxFailures & AcpiSyntaxFailureKind.UnsupportedExtendedOpcode) != 0,
                "unsupported helper reason was discarded with speculative prefix facts");
        });
        Add("extended failure and helper evidence remains immutable and cannot retain operands identifiers or execution capability", () =>
        {
            var report = InspectAcpiFlow(AcpiJoin(AcpiExtended(0x22, new byte[] { 0 }),
                AcpiReturn(AcpiName("HLP0"))), AcpiMethod("HLP0", 0, new byte[] { 0xa4, 0x0a, 0xff }));
            foreach (var field in typeof(AcpiMethodFlowReport).GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
            {
                Type type = Nullable.GetUnderlyingType(field.FieldType) ?? field.FieldType;
                Check(field.IsInitOnly && (type.IsEnum || type == typeof(int) || type == typeof(bool)),
                    "extended syntax report retained a raw operand or mutable object");
            }
            Check(!report.Flow.CanInvokeMethods && !report.Flow.CanWriteHardware, "static extension enabled execution");
            foreach (string raw in new[] { "HLP0", "WMAB", "PRIVATE", "C16C47BA" })
                Check(!report.ToDisplayText().Contains(raw), "extended syntax exported firmware identity");
        });
    }

    private static byte[] AcpiExtended(byte opcode, params byte[][] operands)
        => AcpiJoin(new[] { new byte[] { 0x5b, opcode } }.Concat(operands).ToArray());

    private static void CheckAcpiRootFailure(AcpiWmiRoutingReport report, AcpiSyntaxFailureKind kind, AcpiSyntaxOperation operation)
    {
        Equal(AcpiMethodSyntaxStatus.UnsupportedSyntax, report.MethodSyntax);
        Equal(AcpiMethodFlowStatus.NotInspected, report.Flow.Status);
        Check((report.Flow.RootSyntaxFailure & kind) != 0, "root failure category was lost");
        Check((report.Flow.RootFailureOperations & operation) != 0, "root failure operation was lost");
        Equal<int?>(null, report.Flow.RootCallSites); Equal<int?>(null, report.Flow.RootReturnStatements);
        Equal<AcpiSyntaxOperation?>(null, report.Flow.RootExtendedSyntax);
        Equal<bool?>(null, report.LiteralFfReturn);
        Equal<bool?>(null, report.Flow.ParsedHelperLiteralFfReturn);
    }
}
