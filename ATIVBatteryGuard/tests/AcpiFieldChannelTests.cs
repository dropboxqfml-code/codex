using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterAcpiFieldChannelTests()
    {
        Add("Field channel syntax compares one observed input and return declaration with a 21-byte frame", () =>
        {
            var report = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")), AcpiReturn(AcpiName("INPT"))),
                AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168)));
            var channel = report.FieldChannel;
            Equal(AcpiFieldChannelStatus.ObservedDeclarations, channel.Status);
            Equal<int?>(1, channel.RootFieldStoreSites); Equal<int?>(1, channel.RootArg2FieldStoreSites);
            Equal<AcpiStoreSourceKinds?>(AcpiStoreSourceKinds.Arg2, channel.RootFieldStoreSourceKinds);
            Equal<AcpiAddressSpaceKinds?>(AcpiAddressSpaceKinds.SystemMemory, channel.RootArg2FieldSpaces);
            Equal<AcpiAddressSpaceKinds?>(AcpiAddressSpaceKinds.SystemMemory, channel.RootReturnFieldSpaces);
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, channel.RootArg2FieldWidth);
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, channel.RootReturnFieldWidth);
            Equal(AcpiRegionDefinitionRelation.NotObserved, channel.Arg2FieldAndHelperStoreRegions);
            Equal(AcpiRegionDefinitionRelation.NotObserved, channel.ReturnFieldAndHelperStoreRegions);
            Equal<int?>(0, report.Flow.RootCallSites); Equal<bool?>(false, report.LiteralFfReturn);
            Equal<bool?>(true, report.ObjectReferences.RootStoresArg2ToReturnedObject);

            var buffer = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("BUF0")), AcpiReturn(AcpiName("BUF0"))),
                AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })));
            Equal<int?>(0, buffer.FieldChannel.RootFieldStoreSites); Equal<int?>(0, buffer.FieldChannel.RootArg2FieldStoreSites);
            Equal<AcpiStoreSourceKinds?>(AcpiStoreSourceKinds.None, buffer.FieldChannel.RootFieldStoreSourceKinds);
            Equal(AcpiFieldWidthAssessment.NotObserved, buffer.FieldChannel.RootArg2FieldWidth);
            Equal(AcpiFieldWidthAssessment.NotObserved, buffer.FieldChannel.RootReturnFieldWidth);
        });
        Add("Field channel width handles mismatch zero and large encoded bit counts without allocating a field buffer", () =>
        {
            foreach (int bits in new[] { 8, 63, 64, 167, 169, 4095, 4096, 8192, 0xfffff, 0x100000, 0x0fffffff })
            {
                var report = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")), AcpiReturn(AcpiName("INPT"))),
                    AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0", AcpiObjectFieldName("INPT", bits)));
                Equal(AcpiFieldWidthAssessment.DoesNotMatch21ByteFrame, report.FieldChannel.RootArg2FieldWidth);
                Equal(AcpiFieldWidthAssessment.DoesNotMatch21ByteFrame, report.FieldChannel.RootReturnFieldWidth);
                Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
            }
            var zero = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")), AcpiReturn(AcpiName("INPT"))),
                AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 0)));
            Equal(AcpiFieldWidthAssessment.Unknown, zero.FieldChannel.RootArg2FieldWidth);
            Equal(AcpiFieldWidthAssessment.Unknown, zero.FieldChannel.RootReturnFieldWidth);
            var access = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")), AcpiReturn(AcpiName("INPT"))),
                AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0", AcpiJoin(new byte[] { 0 }, AcpiObjectFieldBitLength(8192)),
                    new byte[] { 1, 1, 0 }, new byte[] { 3, 1, 0, 4 }, AcpiObjectFieldName("INPT", 168)));
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, access.FieldChannel.RootArg2FieldWidth);
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, access.FieldChannel.RootReturnFieldWidth);
        });
        Add("Field channel width distinguishes repeated declarations multiple equal candidates and mixed widths", () =>
        {
            var repeated = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")),
                AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")), AcpiReturn(AcpiName("INPT")), AcpiReturn(AcpiName("INPT"))),
                AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168)));
            Equal<int?>(2, repeated.FieldChannel.RootArg2FieldStoreSites);
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, repeated.FieldChannel.RootArg2FieldWidth);
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, repeated.FieldChannel.RootReturnFieldWidth);
            foreach (var sample in new[] {
                new KeyValuePair<int, AcpiFieldWidthAssessment>(168, AcpiFieldWidthAssessment.MultipleCandidates),
                new KeyValuePair<int, AcpiFieldWidthAssessment>(8, AcpiFieldWidthAssessment.Mixed) })
            {
                var report = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INP0")),
                    AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INP1")), AcpiReturn(AcpiName("INP0")), AcpiReturn(AcpiName("INP1"))),
                    AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0", AcpiObjectFieldName("INP0", 168), AcpiObjectFieldName("INP1", sample.Key)));
                Equal(sample.Value, report.FieldChannel.RootArg2FieldWidth);
                Equal(sample.Value, report.FieldChannel.RootReturnFieldWidth);
            }
        });
        Add("Field Store sources preserve direct Arg0 Arg1 and Arg2 roles without promoting them into each other", () =>
        {
            foreach (var sample in new[] {
                new KeyValuePair<byte, AcpiStoreSourceKinds>(0x68, AcpiStoreSourceKinds.Arg0),
                new KeyValuePair<byte, AcpiStoreSourceKinds>(0x69, AcpiStoreSourceKinds.Arg1),
                new KeyValuePair<byte, AcpiStoreSourceKinds>(0x6a, AcpiStoreSourceKinds.Arg2) })
            {
                var report = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { sample.Key }, AcpiName("INPT")), AcpiReturn(AcpiName("INPT"))),
                    AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168)));
                Equal<int?>(1, report.FieldChannel.RootFieldStoreSites);
                Equal<AcpiStoreSourceKinds?>(sample.Value, report.FieldChannel.RootFieldStoreSourceKinds);
                Equal<int?>(sample.Key == 0x6a ? 1 : 0, report.FieldChannel.RootArg2FieldStoreSites);
                Equal(sample.Key == 0x6a ? AcpiFieldWidthAssessment.Matches21ByteFrame : AcpiFieldWidthAssessment.NotObserved,
                    report.FieldChannel.RootArg2FieldWidth);
                Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, report.FieldChannel.RootReturnFieldWidth);
            }
            var helperArg2 = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x69 }, AcpiName("INPT")),
                AcpiName("HLP0"), AcpiReturn(AcpiName("INPT"))),
                AcpiMethod("HLP0", 0, AcpiObjectStore(new byte[] { 0x6a }, AcpiName("TRIG"))),
                AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168), AcpiObjectFieldName("TRIG", 8)));
            Equal(1, helperArg2.FieldChannel.ParsedHelpers);
            Equal<int?>(0, helperArg2.FieldChannel.RootArg2FieldStoreSites);
            Equal<AcpiStoreSourceKinds?>(AcpiStoreSourceKinds.Arg1, helperArg2.FieldChannel.RootFieldStoreSourceKinds);
            Equal(AcpiFieldWidthAssessment.NotObserved, helperArg2.FieldChannel.RootArg2FieldWidth);
        });
        Add("mixed root roles retain unknown and non-Field alternatives instead of selecting a matching Field", () =>
        {
            byte[] declarations = AcpiJoin(AcpiObjectRegion("REG0", 0),
                AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168), AcpiObjectFieldName("TRIG", 8)),
                AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })));
            foreach (byte[] otherTarget in new[] { AcpiName("MISS"), AcpiName("BUF0"), new byte[] { 0x60 } })
            {
                var mixedStore = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")),
                    AcpiObjectStore(new byte[] { 0x6a }, otherTarget), AcpiName("HLP0"), AcpiReturn(AcpiName("INPT"))),
                    AcpiFieldChannelHelper(), declarations);
                Equal<int?>(1, mixedStore.FieldChannel.RootArg2FieldStoreSites);
                Equal(AcpiFieldWidthAssessment.Unknown, mixedStore.FieldChannel.RootArg2FieldWidth);
                Equal(AcpiRegionDefinitionRelation.Unknown, mixedStore.FieldChannel.Arg2FieldAndHelperStoreRegions);
                Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, mixedStore.FieldChannel.RootReturnFieldWidth);
            }
            foreach (byte[] otherReturn in new[] { AcpiName("MISS"), AcpiName("BUF0"), new byte[] { 0 }, new byte[] { 0x6a } })
            {
                var mixedReturn = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")),
                    AcpiName("HLP0"), AcpiReturn(AcpiName("INPT")), AcpiReturn(otherReturn)), AcpiFieldChannelHelper(), declarations);
                Equal(AcpiFieldWidthAssessment.Unknown, mixedReturn.FieldChannel.RootReturnFieldWidth);
                Equal(AcpiRegionDefinitionRelation.Unknown, mixedReturn.FieldChannel.ReturnFieldAndHelperStoreRegions);
                Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, mixedReturn.FieldChannel.RootArg2FieldWidth);
            }
            var unknownOnly = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("MISS")),
                AcpiReturn(AcpiName("MISS"))), declarations);
            Equal(AcpiFieldWidthAssessment.Unknown, unknownOnly.FieldChannel.RootArg2FieldWidth);
            Equal(AcpiFieldWidthAssessment.Unknown, unknownOnly.FieldChannel.RootReturnFieldWidth);
            var knownOtherOnly = InspectAcpiFlow(AcpiJoin(new byte[] { 0x70, 0x6a, 0x60 }, AcpiReturn(new byte[] { 0x6a })), declarations);
            Equal(AcpiFieldWidthAssessment.NotObserved, knownOtherOnly.FieldChannel.RootArg2FieldWidth);
            Equal(AcpiFieldWidthAssessment.NotObserved, knownOtherOnly.FieldChannel.RootReturnFieldWidth);
        });
        Add("Field Store syntax classifies literals and other expressions without tracing values or counting non-Field targets", () =>
        {
            byte[][] sources = {
                new byte[] { 0x0a, 1 }, AcpiJoin(new byte[] { 0x0d }, Encoding.ASCII.GetBytes("SyntheticLiteral"), new byte[] { 0 }),
                AcpiBuffer(new byte[] { 0 }), AcpiPackage(new byte[] { 0x12 }, new byte[] { 1, 0 }),
                new byte[] { 0x60 }, AcpiName("BUF0"), AcpiName("INT0"), new byte[] { 0x87, 0x6a },
                AcpiJoin(new byte[] { 0x71 }, AcpiName("BUF0")), AcpiJoin(new byte[] { 0x83 }, AcpiName("BUF0")),
                new byte[] { 0x72, 0, 0, 0x60 }, AcpiName("HLP0") };
            byte[] declarations = AcpiJoin(AcpiMethod("HLP0", 0, new byte[] { 0xa4, 0 }),
                AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })), AcpiObjectName("INT0", new byte[] { 0x0a, 1 }),
                AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168)));
            for (int i = 0; i < sources.Length; i++)
            {
                var single = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(sources[i], AcpiName("INPT")), AcpiReturn(AcpiName("INPT"))), declarations);
                Equal<AcpiStoreSourceKinds?>(i < 4 ? AcpiStoreSourceKinds.Literal : AcpiStoreSourceKinds.Other,
                    single.FieldChannel.RootFieldStoreSourceKinds);
            }
            byte[] body = AcpiJoin(sources.Select(source => AcpiObjectStore(source, AcpiName("INPT")))
                .Concat(new[] { AcpiObjectStore(new byte[] { 0x6a }, AcpiName("BUF0")), new byte[] { 0x70, 0x69, 0x60 }, AcpiReturn(AcpiName("INPT")) }).ToArray());
            var report = InspectAcpiFlow(body, declarations);
            Equal<int?>(sources.Length, report.FieldChannel.RootFieldStoreSites);
            Equal<int?>(0, report.FieldChannel.RootArg2FieldStoreSites);
            Equal<AcpiStoreSourceKinds?>(AcpiStoreSourceKinds.Literal | AcpiStoreSourceKinds.Other, report.FieldChannel.RootFieldStoreSourceKinds);
            Equal(AcpiFieldWidthAssessment.NotObserved, report.FieldChannel.RootArg2FieldWidth);
            Equal<int?>(1, report.Flow.RootCallSites);
            var returnedExpression = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")),
                new byte[] { 0xa4, 0x87 }, AcpiName("INPT")), AcpiObjectRegion("REG0", 0),
                AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168)));
            Equal(AcpiFieldWidthAssessment.NotObserved, returnedExpression.FieldChannel.RootReturnFieldWidth);
        });
        Add("different Field names can reference the same observed Region declaration without proving physical behavior", () =>
        {
            var report = InspectAcpiFlow(AcpiFieldChannelRootBody(), AcpiMethod("HLP0", 0,
                AcpiJoin(AcpiObjectStore(new byte[] { 0 }, AcpiName("TRIG")), AcpiObjectStore(new byte[] { 0 }, AcpiName("TRIG")))),
                AcpiObjectRegion("REG0", 0),
                AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168), AcpiObjectFieldName("RESP", 168), AcpiObjectFieldName("TRIG", 8)));
            Equal(AcpiRegionDefinitionRelation.SameObservedDefinition, report.FieldChannel.Arg2FieldAndHelperStoreRegions);
            Equal(AcpiRegionDefinitionRelation.SameObservedDefinition, report.FieldChannel.ReturnFieldAndHelperStoreRegions);
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, report.FieldChannel.RootArg2FieldWidth);
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, report.FieldChannel.RootReturnFieldWidth);
            Equal(1, report.FieldChannel.ParsedHelpers);
            Check(!report.FieldChannel.CanInvokeMethods && !report.FieldChannel.CanWriteHardware, "Region identity enabled hardware access");
        });
        Add("Field Region comparison distinguishes declaration identity and mixed candidates from physical address equality", () =>
        {
            foreach (byte helperSpace in new byte[] { 0, 1 })
            {
                var report = InspectAcpiFlow(AcpiFieldChannelRootBody(), AcpiFieldChannelHelper(),
                    AcpiObjectRegion("REG0", 0), AcpiObjectRegion("REG1", helperSpace),
                    AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168), AcpiObjectFieldName("RESP", 168)),
                    AcpiObjectField("REG1", AcpiObjectFieldName("TRIG", 8)));
                Equal(AcpiRegionDefinitionRelation.DifferentObservedDefinitions, report.FieldChannel.Arg2FieldAndHelperStoreRegions);
                Equal(AcpiRegionDefinitionRelation.DifferentObservedDefinitions, report.FieldChannel.ReturnFieldAndHelperStoreRegions);
                Equal<AcpiAddressSpaceKinds?>(AcpiAddressSpaceKinds.SystemMemory, report.FieldChannel.RootArg2FieldSpaces);
                Equal<AcpiAddressSpaceKinds?>(helperSpace == 0 ? AcpiAddressSpaceKinds.SystemMemory : AcpiAddressSpaceKinds.SystemIo,
                    report.FieldChannel.ParsedHelperFieldStoreSpaces);
            }
            var mixed = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")),
                AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INP1")), AcpiName("HLP0"), AcpiReturn(AcpiName("RESP"))),
                AcpiMethod("HLP0", 0, AcpiJoin(AcpiObjectStore(new byte[] { 0 }, AcpiName("TRIG")), AcpiObjectStore(new byte[] { 0 }, AcpiName("TRG1")))),
                AcpiObjectRegion("REG0", 0), AcpiObjectRegion("REG1", 1),
                AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168), AcpiObjectFieldName("RESP", 168), AcpiObjectFieldName("TRIG", 8)),
                AcpiObjectField("REG1", AcpiObjectFieldName("INP1", 168), AcpiObjectFieldName("TRG1", 8)));
            Equal(AcpiRegionDefinitionRelation.Mixed, mixed.FieldChannel.Arg2FieldAndHelperStoreRegions);
            Equal(AcpiRegionDefinitionRelation.Mixed, mixed.FieldChannel.ReturnFieldAndHelperStoreRegions);
            Equal(AcpiFieldWidthAssessment.MultipleCandidates, mixed.FieldChannel.RootArg2FieldWidth);
        });
        Add("unknown aliased duplicate and missing Region declarations cannot become a confirmed Field channel", () =>
        {
            byte[][] uncertain = {
                new byte[0],
                AcpiJoin(new byte[] { 6 }, AcpiName("INP0"), AcpiName("INPT")),
                AcpiJoin(AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168)), AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 8))) };
            foreach (byte[] declaration in uncertain)
            {
                var report = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")),
                    AcpiName("HLP0"), AcpiReturn(AcpiName("INPT"))), AcpiFieldChannelHelper(), AcpiObjectRegion("REG0", 0),
                    AcpiObjectField("REG0", AcpiObjectFieldName("INP0", 168), AcpiObjectFieldName("TRIG", 8)), declaration);
                Equal(AcpiFieldWidthAssessment.Unknown, report.FieldChannel.RootArg2FieldWidth);
                Equal(AcpiFieldWidthAssessment.Unknown, report.FieldChannel.RootReturnFieldWidth);
                Equal(AcpiRegionDefinitionRelation.Unknown, report.FieldChannel.Arg2FieldAndHelperStoreRegions);
            }
            var missingRegion = InspectAcpiFlow(AcpiFieldChannelRootBody(), AcpiFieldChannelHelper(),
                AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0", AcpiObjectFieldName("TRIG", 8)),
                AcpiObjectField("MISS", AcpiObjectFieldName("INPT", 168), AcpiObjectFieldName("RESP", 168)));
            Equal(AcpiRegionDefinitionRelation.Unknown, missingRegion.FieldChannel.Arg2FieldAndHelperStoreRegions);
            Equal(AcpiRegionDefinitionRelation.Unknown, missingRegion.FieldChannel.ReturnFieldAndHelperStoreRegions);
            Equal<AcpiAddressSpaceKinds?>(AcpiAddressSpaceKinds.Unknown, missingRegion.FieldChannel.RootArg2FieldSpaces);
        });
        Add("runtime-created root and parsed helper names invalidate hidden static Field widths and Region relations", () =>
        {
            byte[] declarations = AcpiJoin(AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0",
                AcpiObjectFieldName("INPT", 168), AcpiObjectFieldName("RESP", 168), AcpiObjectFieldName("TRIG", 8)));
            var rootCreation = InspectAcpiFlow(AcpiJoin(new byte[] { 0x8c, 0x6a, 0 }, AcpiName("INPT"), AcpiFieldChannelRootBody()),
                AcpiFieldChannelHelper(), declarations);
            Equal(AcpiMethodSyntaxStatus.Parsed, rootCreation.MethodSyntax);
            Equal(AcpiFieldWidthAssessment.Unknown, rootCreation.FieldChannel.RootArg2FieldWidth);
            Equal(AcpiRegionDefinitionRelation.Unknown, rootCreation.FieldChannel.Arg2FieldAndHelperStoreRegions);

            var helperCreation = InspectAcpiFlow(AcpiFieldChannelRootBody(), AcpiMethod("HLP0", 0,
                AcpiJoin(new byte[] { 0x8c }, AcpiBuffer(new byte[] { 0 }), new byte[] { 0 }, AcpiName("INPT"),
                    AcpiObjectStore(new byte[] { 0 }, AcpiName("TRIG")))), declarations);
            Equal(1, helperCreation.Flow.ParsedHelpers); Equal(1, helperCreation.FieldChannel.ParsedHelpers);
            Equal(AcpiFieldWidthAssessment.Unknown, helperCreation.FieldChannel.RootArg2FieldWidth);
            Equal(AcpiRegionDefinitionRelation.Unknown, helperCreation.FieldChannel.Arg2FieldAndHelperStoreRegions);
        });
        Add("malformed and opaque Field lists discard width prefixes instead of creating frame matches", () =>
        {
            foreach (byte[] tail in new[] {
                AcpiJoin(new byte[] { 2 }, AcpiName("CONN")), AcpiJoin(AcpiName("BAD0"), new byte[] { 0x40 }),
                AcpiJoin(AcpiName("BAD0"), new byte[] { 0x70, 0 }), new byte[] { 1, 1 },
                new byte[] { 3, 1, 0 }, new byte[] { 0, 0xc0, 1 } })
            {
                var report = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")), AcpiReturn(AcpiName("INPT"))),
                    AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168), tail));
                Equal(AcpiFieldWidthAssessment.Unknown, report.FieldChannel.RootArg2FieldWidth);
                Equal(AcpiFieldWidthAssessment.Unknown, report.FieldChannel.RootReturnFieldWidth);
            }
            byte[] fakeField = AcpiJoin(AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168)));
            var opaque = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")), AcpiReturn(AcpiName("INPT"))),
                AcpiObjectName("DATA", AcpiBuffer(fakeField)));
            Equal(AcpiFieldWidthAssessment.Unknown, opaque.FieldChannel.RootArg2FieldWidth);
        });
        Add("unsupported roots helpers and cyclic helper connections never promote incomplete Field relations", () =>
        {
            byte[] declarations = AcpiJoin(AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0",
                AcpiObjectFieldName("INPT", 168), AcpiObjectFieldName("RESP", 168), AcpiObjectFieldName("TRIG", 8)));
            var root = InspectAcpiFlow(AcpiJoin(AcpiFieldChannelRootBody(), new byte[] { 0xfe }), AcpiFieldChannelHelper(), declarations);
            Equal(AcpiFieldChannelStatus.NotInspected, root.FieldChannel.Status);
            Equal<int?>(null, root.FieldChannel.RootFieldStoreSites);
            Equal<AcpiStoreSourceKinds?>(null, root.FieldChannel.RootFieldStoreSourceKinds);
            Equal(AcpiFieldWidthAssessment.Unknown, root.FieldChannel.RootArg2FieldWidth);

            var helper = InspectAcpiFlow(AcpiFieldChannelRootBody(), AcpiMethod("HLP0", 0,
                AcpiJoin(AcpiObjectStore(new byte[] { 0 }, AcpiName("TRIG")), new byte[] { 0xfe })), declarations);
            Equal(0, helper.FieldChannel.ParsedHelpers);
            Equal<AcpiAddressSpaceKinds?>(null, helper.FieldChannel.ParsedHelperFieldStoreSpaces);
            Equal(AcpiRegionDefinitionRelation.Unknown, helper.FieldChannel.Arg2FieldAndHelperStoreRegions);
            Equal(AcpiRegionDefinitionRelation.Unknown, helper.FieldChannel.ReturnFieldAndHelperStoreRegions);
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, helper.FieldChannel.RootArg2FieldWidth);

            var cycle = InspectAcpiFlow(AcpiFieldChannelRootBody(), AcpiMethod("HLP0", 0,
                AcpiJoin(AcpiObjectStore(new byte[] { 0 }, AcpiName("TRIG")), AcpiName("HLP0"))), declarations);
            Check(cycle.Flow.CycleObserved, "a cyclic helper was not represented as incomplete");
            Equal(AcpiRegionDefinitionRelation.Unknown, cycle.FieldChannel.Arg2FieldAndHelperStoreRegions);
        });
        Add("Field channel analysis reuses the unique-name bound without discarding old parsed root facts", () =>
        {
            var stores = new List<byte[]>(); var fields = new List<byte[]>();
            for (int i = 0; i < 65; i++)
            {
                string name = "F" + i.ToString("D3");
                stores.Add(AcpiObjectStore(new byte[] { 0x6a }, AcpiName(name)));
                fields.Add(AcpiObjectFieldName(name, 168));
            }
            stores.Add(AcpiReturn(AcpiName("F000")));
            var report = InspectAcpiFlow(AcpiJoin(stores.ToArray()), AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0", fields.ToArray()));
            Equal(AcpiFieldChannelStatus.LimitExceeded, report.FieldChannel.Status);
            Equal<int?>(null, report.FieldChannel.RootFieldStoreSites);
            Equal(AcpiFieldWidthAssessment.Unknown, report.FieldChannel.RootArg2FieldWidth);
            Equal(AcpiRegionDefinitionRelation.Unknown, report.FieldChannel.Arg2FieldAndHelperStoreRegions);
            Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax); Equal<bool?>(false, report.LiteralFfReturn);
            Equal(AcpiReferenceAnalysisStatus.LimitExceeded, report.ObjectReferences.Status);
        });
        Add("partial namespaces retain local observed Field widths and Region declaration relations", () =>
        {
            var report = InspectAcpiFlow(AcpiFieldChannelRootBody(), AcpiFieldChannelHelper(), AcpiObjectRegion("REG0", 0),
                AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 168), AcpiObjectFieldName("RESP", 168), AcpiObjectFieldName("TRIG", 8)),
                new byte[] { 0xfe });
            Equal(AcpiRoutingStatus.Partial, report.Status);
            Equal(AcpiFieldChannelStatus.Partial, report.FieldChannel.Status);
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, report.FieldChannel.RootArg2FieldWidth);
            Equal(AcpiFieldWidthAssessment.Matches21ByteFrame, report.FieldChannel.RootReturnFieldWidth);
            Equal(AcpiRegionDefinitionRelation.SameObservedDefinition, report.FieldChannel.Arg2FieldAndHelperStoreRegions);
            Equal(AcpiRegionDefinitionRelation.SameObservedDefinition, report.FieldChannel.ReturnFieldAndHelperStoreRegions);
        });
        Add("Field channel reports retain only immutable categories and omit widths addresses paths and execution capabilities", () =>
        {
            byte[] literal = AcpiJoin(new byte[] { 0x0d }, Encoding.ASCII.GetBytes("C:\\Users\\PrivateChannelOwner\\RawField"), new byte[] { 0 });
            byte[] table = AcpiTable(AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 3,
                AcpiJoin(AcpiObjectStore(literal, AcpiName("INPT")), AcpiReturn(AcpiName("INPT")))),
                AcpiObjectRegion("REG0", 0), AcpiObjectField("REG0", AcpiObjectFieldName("INPT", 137))));
            byte[] original = (byte[])table.Clone(); var report = AcpiWmiRoutingInspector.Inspect(table);
            Check(table.SequenceEqual(original), "Field declaration analysis changed input bytes");
            Array.Clear(table, 0, table.Length);
            Equal(AcpiFieldWidthAssessment.DoesNotMatch21ByteFrame, report.FieldChannel.RootReturnFieldWidth);
            foreach (var field in report.FieldChannel.GetType().GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
            {
                Type type = Nullable.GetUnderlyingType(field.FieldType) ?? field.FieldType;
                Check(field.IsInitOnly && (type.IsEnum || type == typeof(int) || type == typeof(bool)), "a raw field detail was retained");
            }
            foreach (string raw in new[] { "INPT", "REG0", "WMAB", "PRIVATE", "137", "DEADBEEF", "deadbeef", "PrivateChannelOwner", "C:\\Users" })
                Check(!report.ToDisplayText().Contains(raw), "a raw field detail was exported");
            Check(!report.FieldChannel.CanInvokeMethods && !report.FieldChannel.CanWriteHardware &&
                !report.CanInvokeMethods && !report.CanWriteHardware, "Field syntax enabled execution");
        });
    }

    private static byte[] AcpiFieldChannelRootBody()
        => AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("INPT")), AcpiName("HLP0"), AcpiReturn(AcpiName("RESP")));

    private static byte[] AcpiFieldChannelHelper()
        => AcpiMethod("HLP0", 0, AcpiObjectStore(new byte[] { 0 }, AcpiName("TRIG")));
}
