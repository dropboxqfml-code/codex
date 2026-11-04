using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterAcpiMethodFlowTests()
    {
        Add("static method flow separates a returned helper and immediate Arg2 syntax from the caller FF hint", () =>
        {
            var report = InspectAcpiFlow(
                AcpiReturn(AcpiJoin(AcpiName("HLP0"), new byte[] { 0x6a })),
                AcpiMethod("HLP0", 1, new byte[] { 0xa4, 0x0a, 0xff }));
            Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
            Equal<bool?>(false, report.LiteralFfReturn);
            var flow = report.Flow;
            Equal(AcpiMethodFlowStatus.ParsedObservedDefinitions, flow.Status);
            Equal<int?>(1, flow.RootCallSites); Equal<int?>(1, flow.RootArg2CallArguments);
            Equal<int?>(1, flow.RootReturnStatements);
            Equal<AcpiReturnSyntax?>(AcpiReturnSyntax.KnownMethodCall, flow.RootReturnSyntax);
            Equal(1, flow.InspectedHelpers); Equal(1, flow.ParsedHelpers); Equal(0, flow.UnsupportedHelpers);
            Equal<bool?>(true, flow.HelperLiteralFfReturn);
            Check(!flow.CycleObserved && !flow.CanInvokeMethods && !flow.CanWriteHardware, "static helper facts granted execution");
        });
        Add("static method flow reports direct Arg2 returns without inventing helper calls or implicit argument aliases", () =>
        {
            var direct = InspectAcpiFlow(new byte[] { 0xa4, 0x6a });
            Equal(AcpiMethodFlowStatus.ParsedObservedDefinitions, direct.Flow.Status);
            Equal<int?>(0, direct.Flow.RootCallSites); Equal<int?>(0, direct.Flow.RootArg2CallArguments);
            Equal<AcpiReturnSyntax?>(AcpiReturnSyntax.Argument2, direct.Flow.RootReturnSyntax);
            Equal(0, direct.Flow.InspectedHelpers); Equal<bool?>(null, direct.Flow.HelperLiteralFfReturn);

            byte[] helper = AcpiMethod("HLP0", 1, new byte[] { 0xa4, 0x00 });
            foreach (byte[] argument in new[] { new byte[] { 0x60 }, new byte[] { 0x87, 0x6a }, new byte[] { 0x69 } })
            {
                var indirect = InspectAcpiFlow(AcpiReturn(AcpiJoin(AcpiName("HLP0"), argument)), helper);
                Equal<int?>(1, indirect.Flow.RootCallSites);
                Equal<int?>(0, indirect.Flow.RootArg2CallArguments);
            }
        });
        Add("static method flow aggregates return syntax in conditional branches without choosing an execution path", () =>
        {
            byte[] body = AcpiJoin(
                AcpiPackage(new byte[] { 0xa0 }, new byte[] { 1, 0xa4, 0x6a }),
                AcpiPackage(new byte[] { 0xa1 }, new byte[] { 0xa4, 0x0a, 0xff }),
                AcpiReturn(AcpiBuffer(new byte[] { 0x21, 0x43 })));
            var result = InspectAcpiFlow(body);
            Equal<int?>(3, result.Flow.RootReturnStatements);
            Equal<AcpiReturnSyntax?>(AcpiReturnSyntax.Argument2 | AcpiReturnSyntax.IntegerLiteral | AcpiReturnSyntax.BufferLiteral,
                result.Flow.RootReturnSyntax);
            Equal<bool?>(true, result.LiteralFfReturn);
            Equal<bool?>(null, result.Flow.HelperLiteralFfReturn);
        });
        Add("static method flow preserves unresolved names as uncertainty rather than zero-argument helpers", () =>
        {
            var report = InspectAcpiFlow(AcpiReturn(AcpiName("UNKN")));
            Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
            Equal(AcpiMethodFlowStatus.Partial, report.Flow.Status);
            Equal<int?>(0, report.Flow.RootCallSites);
            Equal<AcpiReturnSyntax?>(AcpiReturnSyntax.UnresolvedName, report.Flow.RootReturnSyntax);
            Check(report.Flow.UnresolvedNameReferences > 0, "an unresolved object or call became a resolved helper");
            Equal(0, report.Flow.InspectedHelpers); Equal<bool?>(null, report.Flow.HelperLiteralFfReturn);
        });
        Add("static method flow never treats opaque buffer package or string content as helper calls", () =>
        {
            byte[] hidden = AcpiJoin(AcpiName("HLP0"), new byte[] { 0x6a, 0xa4, 0x0a, 0xff });
            byte[] helper = AcpiMethod("HLP0", 1, new byte[] { 0xa4, 0x0a, 0xff });
            foreach (byte[] value in new[] {
                AcpiBuffer(hidden),
                AcpiPackage(new byte[] { 0x12 }, AcpiJoin(new byte[] { 1 }, hidden)),
                AcpiJoin(new byte[] { 0x0d }, AcpiName("HLP0"), new byte[] { 0 }) })
            {
                var report = InspectAcpiFlow(AcpiReturn(value), helper);
                Equal<int?>(0, report.Flow.RootCallSites);
                Equal(0, report.Flow.InspectedHelpers);
                Equal<bool?>(null, report.Flow.HelperLiteralFfReturn);
                Equal<bool?>(false, report.LiteralFfReturn);
            }
        });
        Add("static method flow discards all root flow facts when the root syntax arity or binding is not usable", () =>
        {
            byte[] helpful = AcpiReturn(AcpiJoin(AcpiName("HLP0"), new byte[] { 0x6a }));
            byte[] helper = AcpiMethod("HLP0", 1, new byte[] { 0xa4, 0x0a, 0xff });
            var reports = new[] {
                InspectAcpiFlow(AcpiJoin(helpful, new byte[] { 0xfe }), helper),
                AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 2, new byte[] { 0xa4, 0x6a })))),
                AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(AcpiWdg(AcpiJoin(AcpiDescriptor(), AcpiDescriptor())),
                    AcpiMethod("WMAB", 3, helpful), helper))),
                AcpiWmiRoutingInspector.Inspect(new byte[36]) };
            foreach (var report in reports)
            {
                Equal(AcpiMethodFlowStatus.NotInspected, report.Flow.Status);
                Equal<int?>(null, report.Flow.RootCallSites); Equal<int?>(null, report.Flow.RootReturnStatements);
                Equal<AcpiReturnSyntax?>(null, report.Flow.RootReturnSyntax);
                Equal(0, report.Flow.InspectedHelpers); Equal<bool?>(null, report.Flow.HelperLiteralFfReturn);
            }
        });
        Add("static method flow discards unsupported helper hints and does not substitute helper arguments for WMI inputs", () =>
        {
            var unsupported = InspectAcpiFlow(AcpiReturn(AcpiJoin(AcpiName("HLP0"), new byte[] { 0x6a })),
                AcpiMethod("HLP0", 1, new byte[] { 0xa4, 0x0a, 0xff, 0xfe }));
            Equal(AcpiMethodSyntaxStatus.Parsed, unsupported.MethodSyntax);
            Equal(AcpiMethodFlowStatus.Partial, unsupported.Flow.Status);
            Equal(1, unsupported.Flow.InspectedHelpers); Equal(0, unsupported.Flow.ParsedHelpers);
            Equal(1, unsupported.Flow.UnsupportedHelpers); Equal<bool?>(null, unsupported.Flow.HelperLiteralFfReturn);
            Equal<bool?>(false, unsupported.LiteralFfReturn);

            var helperComparison = InspectAcpiFlow(AcpiReturn(AcpiJoin(AcpiName("HLP0"), new byte[] { 0, 0 })), AcpiMethod("HLP0", 2,
                AcpiJoin(AcpiPackage(new byte[] { 0xa0 }, new byte[] { 0x93, 0x69, 1, 0xa3 }), new byte[] { 0xa4, 0xff })));
            Equal<bool?>(false, helperComparison.DirectMethodIdOneComparison);
            Equal<bool?>(false, helperComparison.Flow.HelperLiteralFfReturn);
        });
        Add("static method flow stops cycles and reuses shared helper definitions without falsely reporting a cycle", () =>
        {
            var cycle = InspectAcpiFlow(AcpiReturn(AcpiName("HLP0")),
                AcpiMethod("HLP0", 0, AcpiReturn(AcpiName("HLP0"))));
            Equal(AcpiMethodFlowStatus.Partial, cycle.Flow.Status);
            Check(cycle.Flow.CycleObserved, "recursive helper cycle was not bounded");
            Equal<bool?>(null, cycle.Flow.HelperLiteralFfReturn);

            var shared = InspectAcpiFlow(AcpiJoin(AcpiName("ONE0"), AcpiReturn(AcpiName("TWO0"))),
                AcpiMethod("ONE0", 0, AcpiReturn(AcpiName("BOTH"))),
                AcpiMethod("TWO0", 0, AcpiReturn(AcpiName("BOTH"))),
                AcpiMethod("BOTH", 0, new byte[] { 0xa4, 0x00 }));
            Equal(AcpiMethodFlowStatus.ParsedObservedDefinitions, shared.Flow.Status);
            Equal(3, shared.Flow.InspectedHelpers); Equal(3, shared.Flow.ParsedHelpers);
            Check(!shared.Flow.CycleObserved, "a shared helper was mistaken for recursion");
            Equal<bool?>(false, shared.Flow.HelperLiteralFfReturn);
        });
        Add("static method flow enforces helper depth definition and call-site bounds separately from root syntax", () =>
        {
            var depth = InspectAcpiFlow(AcpiReturn(AcpiName("ONE0")),
                AcpiMethod("ONE0", 0, AcpiReturn(AcpiName("TWO0"))),
                AcpiMethod("TWO0", 0, AcpiReturn(AcpiName("THRE"))),
                AcpiMethod("THRE", 0, new byte[] { 0xa4, 0x00 }));
            Equal(AcpiMethodFlowStatus.LimitExceeded, depth.Flow.Status);
            Equal(AcpiMethodSyntaxStatus.Parsed, depth.MethodSyntax);

            var calls = new List<byte>(); var methods = new List<byte[]>();
            for (int i = 0; i < 9; i++)
            {
                string name = "H" + i.ToString("D3");
                calls.AddRange(AcpiName(name)); methods.Add(AcpiMethod(name, 0, new byte[] { 0xa4, 0 }));
            }
            var count = InspectAcpiFlow(calls.ToArray(), methods.ToArray());
            Equal(AcpiMethodFlowStatus.LimitExceeded, count.Flow.Status);
            Equal(AcpiMethodSyntaxStatus.Parsed, count.MethodSyntax);

            byte[] sites = AcpiJoin(Enumerable.Range(0, 33).Select(_ => AcpiName("HLP0")).ToArray());
            var edges = InspectAcpiFlow(sites, AcpiMethod("HLP0", 0, new byte[] { 0xa4, 0 }));
            Equal(AcpiMethodFlowStatus.LimitExceeded, edges.Flow.Status);
            Equal(AcpiMethodSyntaxStatus.Parsed, edges.MethodSyntax);
            Equal<bool?>(null, edges.Flow.HelperLiteralFfReturn);

            byte[] repeatedCalls = AcpiJoin(Enumerable.Range(0, 16).Select(_ => AcpiName("LEAF")).ToArray());
            var totalSites = InspectAcpiFlow(AcpiJoin(AcpiName("ONE0"), AcpiName("TWO0")),
                AcpiMethod("ONE0", 0, repeatedCalls), AcpiMethod("TWO0", 0, repeatedCalls),
                AcpiMethod("LEAF", 0, new byte[] { 0xa4, 0 }));
            Equal(AcpiMethodFlowStatus.LimitExceeded, totalSites.Flow.Status);
            Equal<int?>(2, totalSites.Flow.RootCallSites);
            Equal<bool?>(null, totalSites.Flow.HelperLiteralFfReturn);

            var objects = new List<byte>();
            for (int i = 0; i <= AcpiWmiRoutingInspector.MaximumNamespaceObjects; i++)
            {
                string name = ((char)('A' + i / 4096)).ToString() + (i % 4096).ToString("X3");
                objects.AddRange(AcpiJoin(new byte[] { 8 }, AcpiName(name), new byte[] { 0 }));
            }
            var objectLimit = AcpiWmiRoutingInspector.Inspect(AcpiTable(objects.ToArray()));
            Equal(AcpiRoutingStatus.LimitExceeded, objectLimit.Status);
            Equal(AcpiMethodFlowStatus.NotInspected, objectLimit.Flow.Status);
        });
        Add("static method flow rejects duplicate helper definitions and prevents explicit name parent fallback", () =>
        {
            var duplicate = InspectAcpiFlow(AcpiReturn(AcpiName("HLP0")),
                AcpiMethod("HLP0", 0, new byte[] { 0xa4, 0 }), AcpiMethod("HLP0", 0, new byte[] { 0xa4, 1 }));
            Equal(AcpiMethodSyntaxStatus.UnsupportedSyntax, duplicate.MethodSyntax);
            Equal(AcpiMethodFlowStatus.NotInspected, duplicate.Flow.Status);

            byte[] rootHelper = AcpiMethod("HLP0", 0, new byte[] { 0xa4, 0x0a, 0xff });
            byte[] relative = AcpiDevice("DEV0", AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 3, AcpiReturn(AcpiName("HLP0")))));
            var validRelative = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(rootHelper, relative)));
            Equal<int?>(1, validRelative.Flow.RootCallSites); Equal<bool?>(true, validRelative.Flow.HelperLiteralFfReturn);

            byte[] explicitMissing = AcpiJoin(new byte[] { 0x5c, 0x2e }, AcpiName("DEV0"), AcpiName("HLP0"));
            byte[] scoped = AcpiDevice("DEV0", AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 3, AcpiReturn(explicitMissing))));
            var missing = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(rootHelper, scoped)));
            Equal(AcpiMethodFlowStatus.Partial, missing.Flow.Status);
            Equal<int?>(0, missing.Flow.RootCallSites); Equal(0, missing.Flow.InspectedHelpers);
            Equal<AcpiReturnSyntax?>(AcpiReturnSyntax.UnresolvedName, missing.Flow.RootReturnSyntax);

            foreach (byte[] opaque in new[] {
                AcpiJoin(new byte[] { 8 }, AcpiName("HLP0"), new byte[] { 0 }),
                AcpiJoin(new byte[] { 8 }, AcpiName("SRC0"), new byte[] { 0, 6 }, AcpiName("SRC0"), AcpiName("HLP0")),
                AcpiJoin(new byte[] { 0x15 }, AcpiName("HLP0"), new byte[] { 8, 0 }) })
            {
                byte[] local = AcpiDevice("DEV0", AcpiJoin(opaque, AcpiWdg(),
                    AcpiMethod("WMAB", 3, AcpiReturn(AcpiName("HLP0")))));
                var shadow = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(rootHelper, local)));
                Equal(AcpiMethodSyntaxStatus.Parsed, shadow.MethodSyntax);
                Equal(AcpiMethodFlowStatus.Partial, shadow.Flow.Status);
                Equal<int?>(0, shadow.Flow.RootCallSites); Equal(0, shadow.Flow.InspectedHelpers);
                Equal<AcpiReturnSyntax?>(AcpiReturnSyntax.UnresolvedName, shadow.Flow.RootReturnSyntax);
            }
        });
        Add("static method flow rejects runtime field creation that could shadow a known local or parent method", () =>
        {
            byte[] helper = AcpiMethod("HLP0", 0, new byte[] { 0xa4, 0x0a, 0xff });
            foreach (byte opcode in new byte[] { 0x8a, 0x8b, 0x8c, 0x8d, 0x8f })
            {
                byte[] create = AcpiJoin(new byte[] { opcode, 0x6a, 0 }, AcpiName("HLP0"));
                byte[] body = AcpiJoin(create, AcpiReturn(AcpiName("HLP0")));
                var local = InspectAcpiFlow(body, helper);
                var parent = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(helper,
                    AcpiDevice("DEV0", AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 3, body))))));
                foreach (var report in new[] { local, parent })
                {
                    Equal(AcpiMethodSyntaxStatus.UnsupportedSyntax, report.MethodSyntax);
                    Equal(AcpiMethodFlowStatus.NotInspected, report.Flow.Status);
                    Equal<int?>(null, report.Flow.RootCallSites); Equal<bool?>(null, report.LiteralFfReturn);
                }
                var safe = InspectAcpiFlow(AcpiJoin(new byte[] { opcode, 0x6a, 0 }, AcpiName("FLD0"),
                    new byte[] { 0xa4, 0x6a }), helper);
                Equal(AcpiMethodSyntaxStatus.Parsed, safe.MethodSyntax);
                Equal(AcpiMethodFlowStatus.ParsedObservedDefinitions, safe.Flow.Status);
                Equal<AcpiReturnSyntax?>(AcpiReturnSyntax.Argument2, safe.Flow.RootReturnSyntax);
                Equal<int?>(0, safe.Flow.RootCallSites);
            }

            var helperShadow = InspectAcpiFlow(AcpiReturn(AcpiJoin(AcpiName("HLP0"), new byte[] { 0x6a })),
                AcpiMethod("HLP0", 1, AcpiJoin(new byte[] { 0x8c, 0x68, 0 }, AcpiName("SIB0"),
                    new byte[] { 0xa4, 0x0a, 0xff })),
                AcpiMethod("SIB0", 0, new byte[] { 0xa4, 0 }));
            Equal(AcpiMethodSyntaxStatus.Parsed, helperShadow.MethodSyntax);
            Equal(AcpiMethodFlowStatus.Partial, helperShadow.Flow.Status);
            Equal(1, helperShadow.Flow.UnsupportedHelpers); Equal(0, helperShadow.Flow.ParsedHelpers);
            Equal<bool?>(null, helperShadow.Flow.HelperLiteralFfReturn);
        });
        Add("static method flow retains observed syntax under a partial namespace without proving global uniqueness", () =>
        {
            var report = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(AcpiWdg(),
                AcpiMethod("WMAB", 3, AcpiReturn(AcpiName("HLP0"))),
                AcpiMethod("HLP0", 0, new byte[] { 0xa4, 0x0a, 0xff }), new byte[] { 0xfe })));
            Equal(AcpiRoutingStatus.Partial, report.Status);
            Equal(AcpiMethodFlowStatus.ParsedObservedDefinitions, report.Flow.Status);
            Equal<bool?>(true, report.Flow.HelperLiteralFfReturn);
            Check(report.ToDisplayText().Contains("유일성 보장이 아닙니다"), "a partial namespace was promoted to global uniqueness");
        });
        Add("static method flow distinguishes reference operands from term argument method calls", () =>
        {
            byte[][] referenceBodies = {
                AcpiJoin(new byte[] { 0xa4, 0x8e }, AcpiName("HLP0")),
                AcpiJoin(new byte[] { 0xa4, 0x71 }, AcpiName("HLP0")),
                AcpiJoin(new byte[] { 0xa4, 0x87 }, AcpiName("HLP0")),
                AcpiJoin(new byte[] { 0x70, 0 }, AcpiName("HLP0"), new byte[] { 0xa4, 0x6a }),
                AcpiJoin(new byte[] { 0x86 }, AcpiName("HLP0"), new byte[] { 0, 0xa4, 0x6a }),
                AcpiJoin(new byte[] { 0x88, 0x6a, 0 }, AcpiName("HLP0"), new byte[] { 0xa4, 0x6a }),
                AcpiJoin(new byte[] { 0x75 }, AcpiName("HLP0"), new byte[] { 0xa4, 0x6a }),
                AcpiJoin(new byte[] { 0x76 }, AcpiName("HLP0"), new byte[] { 0xa4, 0x6a }) };
            foreach (byte arguments in new byte[] { 0, 1 })
            {
                byte[] helper = AcpiMethod("HLP0", arguments, new byte[] { 0xa4, 0x0a, 0xff });
                foreach (byte[] body in referenceBodies)
                {
                    var report = InspectAcpiFlow(body, helper);
                    if (report.MethodSyntax == AcpiMethodSyntaxStatus.UnsupportedSyntax)
                    {
                        Equal(AcpiMethodFlowStatus.NotInspected, report.Flow.Status);
                        Equal<int?>(null, report.Flow.RootCallSites);
                    }
                    else
                    {
                        Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
                        Equal<int?>(0, report.Flow.RootCallSites);
                        Equal<int?>(1, report.Flow.RootReturnStatements);
                    }
                    Equal(0, report.Flow.InspectedHelpers);
                    Equal<bool?>(null, report.Flow.HelperLiteralFfReturn);
                }
            }

            var dereference = InspectAcpiFlow(AcpiJoin(new byte[] { 0xa4, 0x83 }, AcpiName("HLP0")),
                AcpiMethod("HLP0", 0, new byte[] { 0xa4, 0x0a, 0xff }));
            if (dereference.MethodSyntax == AcpiMethodSyntaxStatus.Parsed)
            {
                Equal(AcpiMethodFlowStatus.Partial, dereference.Flow.Status);
                Equal<int?>(0, dereference.Flow.RootCallSites);
                Equal(0, dereference.Flow.InspectedHelpers);
                Equal<bool?>(null, dereference.Flow.HelperLiteralFfReturn);
            }
            else
            {
                Equal(AcpiMethodSyntaxStatus.UnsupportedSyntax, dereference.MethodSyntax);
                Equal(AcpiMethodFlowStatus.NotInspected, dereference.Flow.Status);
            }

            var termArgument = InspectAcpiFlow(AcpiJoin(new byte[] { 0xa4, 0x72 }, AcpiName("HLP0"),
                new byte[] { 0, 0x60 }), AcpiMethod("HLP0", 0, new byte[] { 0xa4, 0x0a, 0xff }));
            Equal(AcpiMethodSyntaxStatus.Parsed, termArgument.MethodSyntax);
            Equal<int?>(1, termArgument.Flow.RootCallSites);
            Equal(1, termArgument.Flow.InspectedHelpers);
            Equal<bool?>(true, termArgument.Flow.HelperLiteralFfReturn);
        });
        Add("static method flow reports are immutable contain no firmware identifiers and cannot enable execution", () =>
        {
            byte[] table = AcpiTable(AcpiDevice("DEV0", AcpiJoin(AcpiWdg(),
                AcpiMethod("WMAB", 3, AcpiReturn(AcpiJoin(AcpiName("HLP0"), new byte[] { 0x6a }))),
                AcpiMethod("HLP0", 1, new byte[] { 0xa4, 0x0a, 0xff }))));
            byte[] copy = (byte[])table.Clone();
            var report = AcpiWmiRoutingInspector.Inspect(table);
            Check(table.SequenceEqual(copy), "flow analysis modified caller table");
            Array.Clear(table, 0, table.Length);
            var flow = report.Flow;
            Equal<bool?>(true, flow.HelperLiteralFfReturn);
            foreach (var field in typeof(AcpiMethodFlowReport).GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
            {
                Type type = Nullable.GetUnderlyingType(field.FieldType) ?? field.FieldType;
                Check(field.IsInitOnly && (type.IsEnum || type == typeof(int) || type == typeof(bool)), "flow report retained raw firmware data");
            }
            string text = report.ToDisplayText();
            foreach (string identity in new[] { "DEV0", "HLP0", "WMAB", "PRIVATE", "C16C47BA" })
                Check(!text.Contains(identity), "flow report exported a firmware identity");
            Check(!flow.CanInvokeMethods && !flow.CanWriteHardware && !report.CanInvokeMethods && !report.CanWriteHardware,
                "static syntax enabled firmware access");
        });
    }

    private static byte[] AcpiReturn(byte[] expression) => AcpiJoin(new byte[] { 0xa4 }, expression);

    private static AcpiWmiRoutingReport InspectAcpiFlow(byte[] rootBody, params byte[][] helpers)
        => AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(new[] {
            AcpiWdg(), AcpiMethod("WMAB", 3, rootBody) }.Concat(helpers).ToArray())));
}
