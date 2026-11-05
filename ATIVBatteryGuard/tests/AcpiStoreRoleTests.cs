using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterAcpiStoreRoleTests()
    {
        Add("Store roles classify the extra literal target separately from the input return and helper declarations", () =>
        {
            var report = InspectAcpiFlow(AcpiStoreRoleBody(), AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations());
            var roles = report.StoreRoles;
            Equal(AcpiStoreRoleStatus.ObservedSyntax, roles.Status);
            Equal<int?>(1, roles.RootLiteralStoreSites);
            Equal<AcpiLiteralSyntaxKinds?>(AcpiLiteralSyntaxKinds.Integer, roles.RootLiteralSyntax);
            Equal<AcpiAddressSpaceKinds?>(AcpiAddressSpaceKinds.SystemMemory, roles.RootLiteralFieldSpaces);
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, roles.RootLiteralFieldWidth);
            Equal(AcpiDefinitionRelation.DifferentObservedDefinitions, roles.LiteralAndArg2Fields);
            Equal(AcpiDefinitionRelation.DifferentObservedDefinitions, roles.LiteralAndReturnFields);
            Equal(AcpiDefinitionRelation.DifferentObservedDefinitions, roles.LiteralAndHelperStoreFields);
            Equal(AcpiRegionDefinitionRelation.SameObservedDefinition, roles.LiteralAndArg2Regions);
            Equal(AcpiRegionDefinitionRelation.SameObservedDefinition, roles.LiteralAndReturnRegions);
            Equal(AcpiRegionDefinitionRelation.DifferentObservedDefinitions, roles.LiteralAndHelperStoreRegions);
            Equal(1, roles.ParsedHelpers);
            Equal(AcpiRootLayoutStatus.SingleDirectList, roles.LayoutStatus);
            Equal(AcpiStatementOrder.BeforeInSameList, roles.Arg2StoreAndLiteralStoreOrder);
            Equal(AcpiStatementOrder.BeforeInSameList, roles.Arg2StoreAndHelperCallOrder);
            Equal(AcpiStatementOrder.BeforeInSameList, roles.LiteralStoreAndHelperCallOrder);
            Equal(AcpiStatementOrder.BeforeInSameList, roles.HelperCallAndReturnOrder);
            Equal<int?>(2, report.FieldChannel.RootFieldStoreSites);
            Equal<int?>(1, report.FieldChannel.RootArg2FieldStoreSites);
            Equal<bool?>(true, report.ObjectReferences.RootStoresArg2ToReturnedObject);
            Equal<bool?>(false, report.LiteralFfReturn);
        });
        Add("Store roles count immediate literal syntax without resolving names locals or computed values", () =>
        {
            byte[][] literalSources = {
                new byte[] { 0 }, new byte[] { 0x0a, 0xff },
                AcpiJoin(new byte[] { 0x0d }, Encoding.ASCII.GetBytes("SyntheticLiteral"), new byte[] { 0 }),
                AcpiBuffer(new byte[] { 0x70, 0, 0x60 }),
                AcpiPackage(new byte[] { 0x12 }, new byte[] { 1, 0 }),
                AcpiPackage(new byte[] { 0x13 }, new byte[] { 1, 0 }) };
            byte[][] otherSources = { AcpiName("INT0"), new byte[] { 0x60 }, new byte[] { 0x68 },
                new byte[] { 0x69 }, new byte[] { 0x6a }, new byte[] { 0x87, 0x6a },
                new byte[] { 0x72, 0, 0, 0x60 }, AcpiName("HLP1") };
            var body = literalSources.Concat(otherSources).Select(source => AcpiObjectStore(source, AcpiName("STAT")))
                .Concat(new[] { AcpiReturn(AcpiName("INPT")) }).ToArray();
            var report = InspectAcpiFlow(AcpiJoin(body), AcpiStoreRoleDeclarations(),
                AcpiObjectName("INT0", new byte[] { 0 }), AcpiMethod("HLP1", 0, AcpiReturn(new byte[] { 0 })));
            Equal<int?>(literalSources.Length, report.StoreRoles.RootLiteralStoreSites);
            Equal<AcpiLiteralSyntaxKinds?>(AcpiLiteralSyntaxKinds.Integer | AcpiLiteralSyntaxKinds.String |
                AcpiLiteralSyntaxKinds.Buffer | AcpiLiteralSyntaxKinds.Package, report.StoreRoles.RootLiteralSyntax);
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, report.StoreRoles.RootLiteralFieldWidth);
            Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
            Equal<int?>(1, report.Flow.RootCallSites);

            var helperOnlyLiteral = InspectAcpiFlow(AcpiJoin(AcpiName("HLP0"), AcpiReturn(AcpiName("INPT"))),
                AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations());
            Equal<int?>(0, helperOnlyLiteral.StoreRoles.RootLiteralStoreSites);
            Equal<AcpiLiteralSyntaxKinds?>(AcpiLiteralSyntaxKinds.None, helperOnlyLiteral.StoreRoles.RootLiteralSyntax);
        });
        Add("Store role identity uses observed definitions rather than store occurrence counts or equal addresses", () =>
        {
            var same = InspectAcpiFlow(AcpiStoreRoleBody("INPT"),
                AcpiMethod("HLP0", 0, AcpiObjectStore(new byte[] { 0 }, AcpiName("INPT"))), AcpiStoreRoleDeclarations());
            Equal(AcpiDefinitionRelation.SameObservedDefinition, same.StoreRoles.LiteralAndArg2Fields);
            Equal(AcpiDefinitionRelation.SameObservedDefinition, same.StoreRoles.LiteralAndReturnFields);
            Equal(AcpiDefinitionRelation.SameObservedDefinition, same.StoreRoles.LiteralAndHelperStoreFields);
            Equal(AcpiRegionDefinitionRelation.SameObservedDefinition, same.StoreRoles.LiteralAndHelperStoreRegions);

            var repeated = InspectAcpiFlow(AcpiJoin(AcpiStoreRoleBody(), AcpiObjectStore(new byte[] { 1 }, AcpiName("STAT"))),
                AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations());
            Equal<int?>(2, repeated.StoreRoles.RootLiteralStoreSites);
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, repeated.StoreRoles.RootLiteralFieldWidth);
            Equal(AcpiDefinitionRelation.DifferentObservedDefinitions, repeated.StoreRoles.LiteralAndArg2Fields);
            Equal(AcpiRootLayoutStatus.MultipleCandidates, repeated.StoreRoles.LayoutStatus);
        });
        Add("Store role widths retain mismatch zero multiple equal and mixed declarations", () =>
        {
            foreach (var sample in new[] {
                Tuple.Create(8, AcpiFieldWidthAssessment.DoesNotMatch21ByteFrame),
                Tuple.Create(0, AcpiFieldWidthAssessment.Unknown),
                Tuple.Create(8192, AcpiFieldWidthAssessment.DoesNotMatch21ByteFrame) })
            {
                var report = InspectAcpiFlow(AcpiStoreRoleBody(), AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations(sample.Item1));
                Equal(sample.Item2, report.StoreRoles.RootLiteralFieldWidth);
            }
            foreach (var sample in new[] {
                Tuple.Create(168, AcpiFieldWidthAssessment.MultipleCandidates),
                Tuple.Create(8, AcpiFieldWidthAssessment.Mixed) })
            {
                var report = InspectAcpiFlow(AcpiJoin(AcpiStoreRoleBody(), AcpiObjectStore(new byte[] { 0 }, AcpiName("SAT1"))),
                    AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations(),
                    AcpiObjectField("REG0", AcpiObjectFieldName("SAT1", sample.Item1)));
                Equal(sample.Item2, report.StoreRoles.RootLiteralFieldWidth);
                Equal(AcpiDefinitionRelation.Mixed, report.StoreRoles.LiteralAndArg2Fields);
                Equal(AcpiRegionDefinitionRelation.SameObservedDefinition, report.StoreRoles.LiteralAndArg2Regions);
            }
        });
        Add("Store role literal counts include unknown non-Field and nonnamed targets without selecting a matching subset", () =>
        {
            foreach (byte[] target in new[] { AcpiName("MISS"), AcpiName("BUF0"), new byte[] { 0x60 } })
            {
                var report = InspectAcpiFlow(AcpiJoin(AcpiStoreRoleBody(), AcpiObjectStore(new byte[] { 0 }, target)),
                    AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations(), AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })));
                Equal<int?>(2, report.StoreRoles.RootLiteralStoreSites);
                Equal(AcpiFieldWidthAssessment.Unknown, report.StoreRoles.RootLiteralFieldWidth);
                Equal(AcpiDefinitionRelation.Unknown, report.StoreRoles.LiteralAndArg2Fields);
                Equal(AcpiRegionDefinitionRelation.Unknown, report.StoreRoles.LiteralAndArg2Regions);
                Check(report.StoreRoles.LayoutStatus != AcpiRootLayoutStatus.SingleDirectList, "an alternative literal target was discarded");
            }
            var knownOther = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0 }, AcpiName("BUF0")), AcpiReturn(new byte[] { 0x6a })),
                AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })));
            Equal<int?>(1, knownOther.StoreRoles.RootLiteralStoreSites);
            Equal(AcpiFieldWidthAssessment.NotObserved, knownOther.StoreRoles.RootLiteralFieldWidth);
            Equal(AcpiDefinitionRelation.NotObserved, knownOther.StoreRoles.LiteralAndArg2Fields);
            var unknownOnly = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0 }, AcpiName("MISS")), AcpiReturn(new byte[] { 0x6a })));
            Equal(AcpiFieldWidthAssessment.Unknown, unknownOnly.StoreRoles.RootLiteralFieldWidth);
            Equal(AcpiDefinitionRelation.Unknown, unknownOnly.StoreRoles.LiteralAndReturnFields);
        });
        Add("Store roles respect aliases duplicate declarations dynamic creation and opaque parent lookup barriers", () =>
        {
            byte[][] uncertain = {
                AcpiJoin(new byte[] { 6 }, AcpiName("SRC0"), AcpiName("STAT")),
                AcpiJoin(new byte[] { 0x15 }, AcpiName("STAT"), new byte[] { 1, 0 }),
                AcpiObjectField("REG0", AcpiObjectFieldName("STAT", 168)) };
            foreach (byte[] extra in uncertain)
            {
                var report = InspectAcpiFlow(AcpiStoreRoleBody(), AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations(), extra);
                Equal(AcpiFieldWidthAssessment.Unknown, report.StoreRoles.RootLiteralFieldWidth);
                Equal(AcpiDefinitionRelation.Unknown, report.StoreRoles.LiteralAndArg2Fields);
            }
            foreach (bool fromHelper in new[] { false, true })
            {
                byte[] creation = AcpiJoin(new byte[] { 0x8c }, AcpiBuffer(new byte[] { 0 }), new byte[] { 0 }, AcpiName("STAT"));
                var report = InspectAcpiFlow(fromHelper ? AcpiStoreRoleBody() : AcpiJoin(creation, AcpiStoreRoleBody()),
                    fromHelper ? AcpiMethod("HLP0", 0, AcpiJoin(creation, AcpiObjectStore(new byte[] { 0 }, AcpiName("TRIG")))) : AcpiStoreRoleHelper(),
                    AcpiStoreRoleDeclarations());
                Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
                Equal(AcpiFieldWidthAssessment.Unknown, report.StoreRoles.RootLiteralFieldWidth);
                Equal(AcpiDefinitionRelation.Unknown, report.StoreRoles.LiteralAndReturnFields);
            }
            byte[] nested = AcpiDevice("DEV0", AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 3,
                AcpiJoin(AcpiObjectStore(new byte[] { 0 }, AcpiName("STAT")), AcpiReturn(new byte[] { 0x6a }))),
                AcpiObjectField("REGX", AcpiJoin(new byte[] { 2 }, AcpiName("CONN")))));
            var opaque = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(AcpiStoreRoleDeclarations(), nested)));
            Equal(AcpiMethodSyntaxStatus.Parsed, opaque.MethodSyntax);
            Equal(AcpiFieldWidthAssessment.Unknown, opaque.StoreRoles.RootLiteralFieldWidth);
        });
        Add("Store role Region relations retain missing and mixed declarations rather than comparing physical addresses", () =>
        {
            var missing = InspectAcpiFlow(AcpiStoreRoleBody(), AcpiStoreRoleHelper(),
                AcpiObjectRegion("REG0", 0), AcpiObjectRegion("REG1", 1),
                AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168)),
                AcpiObjectField("MISS", AcpiObjectFieldName("STAT", 168)),
                AcpiObjectField("REG1", AcpiObjectFieldName("TRIG", 8)));
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, missing.StoreRoles.RootLiteralFieldWidth);
            Equal<AcpiAddressSpaceKinds?>(AcpiAddressSpaceKinds.Unknown, missing.StoreRoles.RootLiteralFieldSpaces);
            Equal(AcpiRegionDefinitionRelation.Unknown, missing.StoreRoles.LiteralAndArg2Regions);
            var mixed = InspectAcpiFlow(AcpiJoin(AcpiStoreRoleBody(), AcpiObjectStore(new byte[] { 1 }, AcpiName("SAT1"))),
                AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations(),
                AcpiObjectField("REG1", AcpiObjectFieldName("SAT1", 168)));
            Equal(AcpiRegionDefinitionRelation.Mixed, mixed.StoreRoles.LiteralAndArg2Regions);
            Equal<AcpiAddressSpaceKinds?>(AcpiAddressSpaceKinds.SystemMemory | AcpiAddressSpaceKinds.SystemIo,
                mixed.StoreRoles.RootLiteralFieldSpaces);
        });
        Add("direct Store layout reports source order including reversed syntax without claiming execution", () =>
        {
            byte[] input = AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT"));
            byte[] literal = AcpiObjectStore(new byte[] { 0 }, AcpiName("STAT"));
            byte[] call = AcpiName("HLP0"); byte[] returning = AcpiReturn(AcpiName("INPT"));
            var reversed = InspectAcpiFlow(AcpiJoin(returning, call, literal, input), AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations());
            Equal(AcpiRootLayoutStatus.SingleDirectList, reversed.StoreRoles.LayoutStatus);
            Equal(AcpiStatementOrder.AfterInSameList, reversed.StoreRoles.Arg2StoreAndLiteralStoreOrder);
            Equal(AcpiStatementOrder.AfterInSameList, reversed.StoreRoles.Arg2StoreAndHelperCallOrder);
            Equal(AcpiStatementOrder.AfterInSameList, reversed.StoreRoles.LiteralStoreAndHelperCallOrder);
            Equal(AcpiStatementOrder.AfterInSameList, reversed.StoreRoles.HelperCallAndReturnOrder);
            var interleaved = InspectAcpiFlow(AcpiJoin(literal, input, call, returning), AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations());
            Equal(AcpiRootLayoutStatus.SingleDirectList, interleaved.StoreRoles.LayoutStatus);
            Equal(AcpiStatementOrder.AfterInSameList, interleaved.StoreRoles.Arg2StoreAndLiteralStoreOrder);
            Equal(AcpiStatementOrder.BeforeInSameList, interleaved.StoreRoles.LiteralStoreAndHelperCallOrder);
        });
        Add("missing direct layout roles remain unobserved or unknown without manufacturing a complete pattern", () =>
        {
            byte[][] terms = { AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")),
                AcpiObjectStore(new byte[] { 0 }, AcpiName("STAT")), AcpiName("HLP0"), AcpiReturn(AcpiName("INPT")) };
            for (int missing = 0; missing < terms.Length; missing++)
            {
                var report = InspectAcpiFlow(AcpiJoin(terms.Where((_, index) => index != missing).ToArray()),
                    AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations());
                Equal(AcpiRootLayoutStatus.NotObserved, report.StoreRoles.LayoutStatus);
            }
            var partial = InspectAcpiFlow(AcpiJoin(terms.Take(3).ToArray()), AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations(), new byte[] { 0xfe });
            Equal(AcpiRootLayoutStatus.Unknown, partial.StoreRoles.LayoutStatus);
        });
        Add("duplicate direct input literal helper and return sites are multiple candidates even for one declaration", () =>
        {
            byte[][] duplicates = { AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")),
                AcpiObjectStore(new byte[] { 0 }, AcpiName("STAT")), AcpiName("HLP0"), AcpiReturn(AcpiName("INPT")) };
            foreach (byte[] duplicate in duplicates)
            {
                var report = InspectAcpiFlow(AcpiJoin(AcpiStoreRoleBody(), duplicate), AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations());
                Equal(AcpiRootLayoutStatus.MultipleCandidates, report.StoreRoles.LayoutStatus);
                Check(report.StoreRoles.Arg2StoreAndLiteralStoreOrder != AcpiStatementOrder.BeforeInSameList,
                    "multiple candidate sites were collapsed to one order");
                Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, report.StoreRoles.RootLiteralFieldWidth);
            }
        });
        Add("branches loops and nested blocks cannot be flattened into one direct Store layout", () =>
        {
            byte[] input = AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT"));
            byte[] rest = AcpiJoin(AcpiObjectStore(new byte[] { 0 }, AcpiName("STAT")), AcpiName("HLP0"), AcpiReturn(AcpiName("INPT")));
            foreach (byte opcode in new byte[] { 0xa0, 0xa2 })
            {
                byte[] conditional = AcpiPackage(new byte[] { opcode }, AcpiJoin(new byte[] { 1 }, input));
                var report = InspectAcpiFlow(AcpiJoin(conditional, rest), AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations());
                Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
                Equal(AcpiRootLayoutStatus.Unknown, report.StoreRoles.LayoutStatus);
                Equal(AcpiDefinitionRelation.DifferentObservedDefinitions, report.StoreRoles.LiteralAndArg2Fields);
            }
            byte[] ifElse = AcpiJoin(AcpiPackage(new byte[] { 0xa0 }, new byte[] { 1, 0xa3 }),
                AcpiPackage(new byte[] { 0xa1 }, input), rest);
            Equal(AcpiRootLayoutStatus.Unknown, InspectAcpiFlow(ifElse, AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations()).StoreRoles.LayoutStatus);
        });
        Add("nested Store calls and complex operands never masquerade as direct helper layout events", () =>
        {
            byte[][] extraExpressions = {
                AcpiObjectStore(AcpiJoin(new byte[] { 0x70, 0 }, AcpiName("STAT")), AcpiName("STAT")),
                AcpiObjectStore(AcpiJoin(new byte[] { 0x72 }, AcpiName("HLP1"), new byte[] { 0, 0x60 }), AcpiName("STAT")),
                AcpiObjectStore(AcpiJoin(new byte[] { 0x8e }, AcpiName("HLP1")), AcpiName("STAT")),
                AcpiObjectStore(new byte[] { 0 }, AcpiJoin(new byte[] { 0x83, 0x60 })) };
            foreach (byte[] expression in extraExpressions)
            {
                var report = InspectAcpiFlow(AcpiJoin(AcpiStoreRoleBody(), expression), AcpiStoreRoleHelper(),
                    AcpiMethod("HLP1", 0, AcpiReturn(new byte[] { 0 })), AcpiStoreRoleDeclarations());
                Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
                Equal(AcpiRootLayoutStatus.Unknown, report.StoreRoles.LayoutStatus);
            }
            foreach (byte[] source in new[] {
                AcpiPackage(new byte[] { 0x12 }, new byte[] { 1, 0 }),
                AcpiPackage(new byte[] { 0x13 }, new byte[] { 1, 0 }) })
            {
                var report = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")),
                    AcpiObjectStore(source, AcpiName("STAT")), AcpiName("HLP0"), AcpiReturn(AcpiName("INPT"))),
                    AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations());
                Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
                Equal<int?>(1, report.StoreRoles.RootLiteralStoreSites);
                Equal<AcpiLiteralSyntaxKinds?>(AcpiLiteralSyntaxKinds.Package, report.StoreRoles.RootLiteralSyntax);
                Equal(AcpiRootLayoutStatus.Unknown, report.StoreRoles.LayoutStatus);
                Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, report.StoreRoles.RootLiteralFieldWidth);
            }
            foreach (byte[] source in new[] { new byte[] { 0 },
                AcpiJoin(new byte[] { 0x0d }, Encoding.ASCII.GetBytes("SimpleLiteral"), new byte[] { 0 }),
                AcpiBuffer(new byte[] { 0x70, 0, 0x60 }) })
            {
                var report = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")),
                    AcpiObjectStore(source, AcpiName("STAT")), AcpiName("HLP0"), AcpiReturn(AcpiName("INPT"))),
                    AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations());
                Equal(AcpiRootLayoutStatus.SingleDirectList, report.StoreRoles.LayoutStatus);
                Equal(AcpiStatementOrder.BeforeInSameList, report.StoreRoles.LiteralStoreAndHelperCallOrder);
            }
        });
        Add("Store layout event limits affect only the new report and preserve old parsed root and relation facts", () =>
        {
            byte[] repeated = AcpiJoin(Enumerable.Range(0, 65)
                .Select(_ => AcpiObjectStore(new byte[] { 0 }, AcpiName("STAT")))
                .Concat(new[] { AcpiReturn(AcpiName("INPT")) }).ToArray());
            var report = InspectAcpiFlow(repeated, AcpiStoreRoleDeclarations());
            Equal(AcpiStoreRoleStatus.LimitExceeded, report.StoreRoles.Status);
            Equal(AcpiRootLayoutStatus.LimitExceeded, report.StoreRoles.LayoutStatus);
            Equal<int?>(null, report.StoreRoles.RootLiteralStoreSites);
            Equal<AcpiLiteralSyntaxKinds?>(null, report.StoreRoles.RootLiteralSyntax);
            Equal(AcpiFieldWidthAssessment.Unknown, report.StoreRoles.RootLiteralFieldWidth);
            Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
            Equal<int?>(1, report.Flow.RootReturnStatements); Equal<bool?>(false, report.LiteralFfReturn);
            Equal(AcpiReferenceAnalysisStatus.ClassifiedObservedSyntax, report.ObjectReferences.Status);
            Check(report.FieldChannel.Status != AcpiFieldChannelStatus.LimitExceeded, "new event limit changed the old Field analysis");
            Equal<int?>(65, report.FieldChannel.RootFieldStoreSites);
        });
        Add("unsupported root prefixes are discarded and unsupported or cyclic helpers cannot confirm helper Store relations", () =>
        {
            var root = InspectAcpiFlow(AcpiJoin(AcpiStoreRoleBody(), new byte[] { 0xfe }), AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations());
            Equal(AcpiStoreRoleStatus.NotInspected, root.StoreRoles.Status);
            Equal(AcpiRootLayoutStatus.NotInspected, root.StoreRoles.LayoutStatus);
            Equal<int?>(null, root.StoreRoles.RootLiteralStoreSites);
            Equal<AcpiLiteralSyntaxKinds?>(null, root.StoreRoles.RootLiteralSyntax);
            Equal(AcpiDefinitionRelation.Unknown, root.StoreRoles.LiteralAndArg2Fields);
            foreach (byte[] helperBody in new[] {
                AcpiJoin(AcpiObjectStore(new byte[] { 0 }, AcpiName("STAT")), new byte[] { 0xfe }),
                AcpiJoin(AcpiObjectStore(new byte[] { 0 }, AcpiName("STAT")), AcpiName("HLP0")) })
            {
                var report = InspectAcpiFlow(AcpiStoreRoleBody(), AcpiMethod("HLP0", 0, helperBody), AcpiStoreRoleDeclarations());
                Equal(AcpiDefinitionRelation.Unknown, report.StoreRoles.LiteralAndHelperStoreFields);
                Equal(AcpiRegionDefinitionRelation.Unknown, report.StoreRoles.LiteralAndHelperStoreRegions);
                Equal(AcpiDefinitionRelation.DifferentObservedDefinitions, report.StoreRoles.LiteralAndArg2Fields);
                Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, report.StoreRoles.RootLiteralFieldWidth);
            }
        });
        Add("partial namespace observations retain known Store role identity without claiming complete firmware resolution", () =>
        {
            var report = InspectAcpiFlow(AcpiStoreRoleBody(), AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations(), new byte[] { 0xfe });
            Equal(AcpiRoutingStatus.Partial, report.Status);
            Equal(AcpiStoreRoleStatus.Partial, report.StoreRoles.Status);
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, report.StoreRoles.RootLiteralFieldWidth);
            Equal(AcpiDefinitionRelation.DifferentObservedDefinitions, report.StoreRoles.LiteralAndArg2Fields);
            Equal(AcpiRegionDefinitionRelation.SameObservedDefinition, report.StoreRoles.LiteralAndArg2Regions);
            Equal(AcpiRegionDefinitionRelation.DifferentObservedDefinitions, report.StoreRoles.LiteralAndHelperStoreRegions);
        });
        Add("Store role reports are immutable omit raw literals identities and positions and cannot grant execution", () =>
        {
            byte[] secret = AcpiJoin(new byte[] { 0x0d }, Encoding.ASCII.GetBytes("C:\\Users\\PrivateStoreOwner\\RawLiteral"), new byte[] { 0 });
            byte[] table = AcpiTable(AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 3,
                AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")), AcpiObjectStore(secret, AcpiName("STAT")),
                    AcpiName("HLP0"), AcpiReturn(AcpiName("INPT")))), AcpiStoreRoleHelper(), AcpiStoreRoleDeclarations(137)));
            byte[] original = (byte[])table.Clone(); var report = AcpiWmiRoutingInspector.Inspect(table);
            Check(table.SequenceEqual(original), "Store role analysis changed input bytes");
            Array.Clear(table, 0, table.Length);
            Equal(AcpiFieldWidthAssessment.DoesNotMatch21ByteFrame, report.StoreRoles.RootLiteralFieldWidth);
            foreach (var field in report.StoreRoles.GetType().GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
            {
                Type type = Nullable.GetUnderlyingType(field.FieldType) ?? field.FieldType;
                Check(field.IsInitOnly && (type.IsEnum || type == typeof(int) || type == typeof(bool)), "Store roles retained raw syntax details");
            }
            foreach (string raw in new[] { "INPT", "STAT", "REG0", "HLP0", "WMAB", "137", "DEADBEEF", "deadbeef", "PrivateStoreOwner", "C:\\Users" })
                Check(!report.ToDisplayText().Contains(raw), "Store roles exported a raw value identity or path");
            Check(!report.StoreRoles.CanInvokeMethods && !report.StoreRoles.CanWriteHardware &&
                !report.CanInvokeMethods && !report.CanWriteHardware, "Store roles enabled hardware access");
        });
    }

    private static byte[] AcpiStoreRoleBody(string literalTarget = "STAT")
        => AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")),
            AcpiObjectStore(new byte[] { 0 }, AcpiName(literalTarget)), AcpiName("HLP0"), AcpiReturn(AcpiName("INPT")));

    private static byte[] AcpiStoreRoleHelper()
        => AcpiMethod("HLP0", 0, AcpiObjectStore(new byte[] { 0 }, AcpiName("TRIG")));

    private static byte[] AcpiStoreRoleDeclarations(int literalBits = 168)
        => AcpiJoin(AcpiObjectRegion("REG0", 0), AcpiObjectRegion("REG1", 1),
            AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168), AcpiObjectFieldName("STAT", literalBits)),
            AcpiObjectField("REG1", AcpiObjectFieldName("TRIG", 8)));
}
