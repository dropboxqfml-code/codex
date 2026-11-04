using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterAcpiObjectReferenceTests()
    {
        Add("static object references classify observed literal and synchronization declarations without rewriting old flow counts", () =>
        {
            string[] names = { "BUF0", "INT0", "STR0", "PKG0", "MUT0", "EVT0" };
            byte[] body = AcpiJoin(names.Select(name => AcpiObjectStore(AcpiName(name), new byte[] { 0x60 }))
                .Concat(new[] { new byte[] { 0xa4, 0x6a } }).ToArray());
            var report = InspectAcpiFlow(body,
                AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 1, 2 })),
                AcpiObjectName("INT0", new byte[] { 0x0a, 0x42 }),
                AcpiObjectName("STR0", AcpiJoin(new byte[] { 0x0d }, Encoding.ASCII.GetBytes("PrivateOwner"), new byte[] { 0 })),
                AcpiObjectName("PKG0", AcpiPackage(new byte[] { 0x12 }, new byte[] { 1, 0 })),
                AcpiExtended(0x01, AcpiName("MUT0"), new byte[] { 0 }), AcpiExtended(0x02, AcpiName("EVT0")));
            var objects = report.ObjectReferences;
            Equal(AcpiReferenceAnalysisStatus.ClassifiedObservedSyntax, objects.Status);
            Equal<int?>(6, objects.RootNamedReferences); Equal<int?>(6, objects.RootClassifiedReferences);
            Equal<AcpiNamedObjectKinds?>(AcpiNamedObjectKinds.Buffer | AcpiNamedObjectKinds.Integer |
                AcpiNamedObjectKinds.String | AcpiNamedObjectKinds.Package | AcpiNamedObjectKinds.Mutex | AcpiNamedObjectKinds.Event,
                objects.RootReferencedKinds);
            Equal<AcpiNamedObjectKinds?>(AcpiNamedObjectKinds.None, objects.RootReturnKinds);
            Equal<AcpiNamedObjectKinds?>(AcpiNamedObjectKinds.None, objects.RootArg2StoreKinds);
            Equal<int?>(0, report.Flow.RootCallSites); Equal(6, report.Flow.UnresolvedNameReferences);
            Equal(AcpiMethodFlowStatus.Partial, report.Flow.Status);
            Equal<int?>(null, objects.ParsedHelperNamedReferences);
        });
        Add("static object references identify direct Arg2 store return and parsed helper references to the same observed object", () =>
        {
            var report = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("BUF0")),
                AcpiName("HLP0"), AcpiReturn(AcpiName("BUF0"))),
                AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })), AcpiObjectName("OTHR", AcpiBuffer(new byte[] { 1 })),
                AcpiMethod("HLP0", 0, AcpiJoin(AcpiObjectStore(new byte[] { 0 }, AcpiName("BUF0")), AcpiReturn(AcpiName("OTHR")))));
            var objects = report.ObjectReferences;
            Equal<bool?>(true, objects.RootStoresArg2ToReturnedObject);
            Equal<bool?>(true, objects.RootReturnedObjectReferencedByParsedHelper);
            Equal<bool?>(true, objects.RootArg2StoreObjectReferencedByParsedHelper);
            Equal<AcpiNamedObjectKinds?>(AcpiNamedObjectKinds.Buffer, objects.RootReturnKinds);
            Equal<AcpiNamedObjectKinds?>(AcpiNamedObjectKinds.Buffer, objects.RootArg2StoreKinds);
            Equal(1, objects.ParsedHelpers);
            Equal<int?>(2, objects.ParsedHelperNamedReferences); Equal<int?>(2, objects.ParsedHelperClassifiedReferences);
            Equal<AcpiNamedObjectKinds?>(AcpiNamedObjectKinds.Buffer, objects.ParsedHelperReferencedKinds);
            Equal<AcpiNamedObjectKinds?>(AcpiNamedObjectKinds.Buffer, objects.ParsedHelperStoreTargetKinds);
            Equal<AcpiAddressSpaceKinds?>(AcpiAddressSpaceKinds.None, objects.ParsedHelperFieldStoreSpaces);
            Equal<int?>(1, report.Flow.RootCallSites); Equal<bool?>(false, report.LiteralFfReturn);
        });
        Add("static object relations do not propagate Arg2 through locals SizeOf named values or distinct objects", () =>
        {
            byte[][] sources = { new byte[] { 0x60 }, new byte[] { 0x87, 0x6a }, AcpiName("SRC0") };
            foreach (byte[] source in sources)
            {
                var report = InspectAcpiFlow(AcpiJoin(new byte[] { 0x70, 0x6a, 0x60 },
                    AcpiObjectStore(source, AcpiName("BUF0")), AcpiReturn(AcpiName("BUF0"))),
                    AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })), AcpiObjectName("SRC0", AcpiBuffer(new byte[] { 0 })));
                Equal<AcpiNamedObjectKinds?>(AcpiNamedObjectKinds.None, report.ObjectReferences.RootArg2StoreKinds);
                Check(report.ObjectReferences.RootStoresArg2ToReturnedObject != true, "a derived source became a direct Arg2 store");
            }
            var distinct = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("BUF0")),
                AcpiReturn(AcpiName("OTHR"))), AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })),
                AcpiObjectName("OTHR", AcpiBuffer(new byte[] { 0 })));
            Equal<bool?>(false, distinct.ObjectReferences.RootStoresArg2ToReturnedObject);
        });
        Add("static Field stores report only observed address space kinds without reading or writing a region", () =>
        {
            var spaces = new[] {
                new KeyValuePair<byte, AcpiAddressSpaceKinds>(0, AcpiAddressSpaceKinds.SystemMemory),
                new KeyValuePair<byte, AcpiAddressSpaceKinds>(1, AcpiAddressSpaceKinds.SystemIo),
                new KeyValuePair<byte, AcpiAddressSpaceKinds>(2, AcpiAddressSpaceKinds.PciConfiguration),
                new KeyValuePair<byte, AcpiAddressSpaceKinds>(3, AcpiAddressSpaceKinds.EmbeddedControl),
                new KeyValuePair<byte, AcpiAddressSpaceKinds>(4, AcpiAddressSpaceKinds.SmBus),
                new KeyValuePair<byte, AcpiAddressSpaceKinds>(5, AcpiAddressSpaceKinds.Other) };
            foreach (var space in spaces)
            {
                var report = InspectAcpiFlow(AcpiReturn(AcpiName("HLP0")),
                    AcpiMethod("HLP0", 0, AcpiObjectStore(new byte[] { 0 }, AcpiName("FLD0"))),
                    AcpiObjectRegion("REG0", space.Key), AcpiObjectField("REG0", AcpiObjectFieldName("FLD0", 8)));
                var objects = report.ObjectReferences;
                Equal(1, objects.ParsedHelpers);
                Equal<AcpiNamedObjectKinds?>(AcpiNamedObjectKinds.Field, objects.ParsedHelperReferencedKinds);
                Equal<AcpiNamedObjectKinds?>(AcpiNamedObjectKinds.Field, objects.ParsedHelperStoreTargetKinds);
                Equal<AcpiAddressSpaceKinds?>(space.Value, objects.ParsedHelperFieldStoreSpaces);
                Check(!objects.CanInvokeMethods && !objects.CanWriteHardware, "an observed Field store enabled hardware");
            }
            var unknown = InspectAcpiFlow(AcpiReturn(AcpiName("HLP0")),
                AcpiMethod("HLP0", 0, AcpiObjectStore(new byte[] { 0 }, AcpiName("FLD0"))),
                AcpiObjectField("MISS", AcpiObjectFieldName("FLD0", 8)));
            Equal(AcpiReferenceAnalysisStatus.Partial, unknown.ObjectReferences.Status);
            Equal<AcpiNamedObjectKinds?>(AcpiNamedObjectKinds.Field, unknown.ObjectReferences.ParsedHelperStoreTargetKinds);
            Equal<AcpiAddressSpaceKinds?>(AcpiAddressSpaceKinds.Unknown, unknown.ObjectReferences.ParsedHelperFieldStoreSpaces);
        });
        Add("static Field bit lengths use encoded bit counts independently of remaining table byte counts", () =>
        {
            byte[] fields = AcpiObjectField("REG0", AcpiJoin(new byte[] { 0 }, AcpiObjectFieldBitLength(8192)),
                new byte[] { 1, 1, 0 }, new byte[] { 3, 1, 0, 4 }, AcpiObjectFieldName("FLD0", 4096));
            var report = InspectAcpiFlow(AcpiReturn(AcpiName("HLP0")),
                AcpiMethod("HLP0", 0, AcpiObjectStore(new byte[] { 0 }, AcpiName("FLD0"))),
                AcpiObjectRegion("REG0", 0), fields);
            Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
            Equal<AcpiNamedObjectKinds?>(AcpiNamedObjectKinds.Field, report.ObjectReferences.ParsedHelperStoreTargetKinds);
            Equal<AcpiAddressSpaceKinds?>(AcpiAddressSpaceKinds.SystemMemory, report.ObjectReferences.ParsedHelperFieldStoreSpaces);
        });
        Add("static Field analysis discards typed prefixes when a FieldList is truncated connected or otherwise unsupported", () =>
        {
            byte[] prefix = AcpiObjectFieldName("FLD0", 8);
            byte[][] invalidLists = {
                AcpiJoin(prefix, AcpiName("BAD0"), new byte[] { 0x40 }),
                AcpiJoin(prefix, new byte[] { 2 }, AcpiName("CONN")),
                AcpiJoin(prefix, new byte[] { 1, 1 }),
                AcpiJoin(prefix, new byte[] { 3, 1, 0 }) };
            foreach (byte[] list in invalidLists)
            {
                var report = InspectAcpiFlow(AcpiReturn(AcpiName("HLP0")),
                    AcpiMethod("HLP0", 0, AcpiObjectStore(new byte[] { 0 }, AcpiName("FLD0"))),
                    AcpiObjectRegion("REG0", 1), AcpiObjectField("REG0", list));
                Equal(AcpiReferenceAnalysisStatus.Partial, report.ObjectReferences.Status);
                Check(((report.ObjectReferences.ParsedHelperStoreTargetKinds ?? AcpiNamedObjectKinds.None) & AcpiNamedObjectKinds.Field) == 0,
                    "an invalid FieldList retained a typed prefix");
            }
            foreach (byte opcode in new byte[] { 0x86, 0x87 })
            {
                var report = InspectAcpiFlow(AcpiReturn(AcpiName("FLD0")),
                    AcpiPackage(new byte[] { 0x5b, opcode }, AcpiJoin(AcpiName("REG0"), prefix)));
                Check(((report.ObjectReferences.RootReturnKinds ?? AcpiNamedObjectKinds.None) & AcpiNamedObjectKinds.Field) == 0,
                    "an unsupported IndexField or BankField acquired a typed Field");
            }

            byte[] hiddenFieldScope = AcpiDevice("DEV0", AcpiJoin(AcpiWdg(),
                AcpiMethod("WMAB", 3, AcpiReturn(AcpiName("BUF0"))),
                AcpiObjectField("REG0", new byte[] { 2 })));
            var hiddenField = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(
                AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })), AcpiObjectRegion("REG0", 1), hiddenFieldScope)));
            Equal(AcpiMethodSyntaxStatus.Parsed, hiddenField.MethodSyntax);
            Equal(AcpiReferenceAnalysisStatus.Partial, hiddenField.ObjectReferences.Status);
            Check(((hiddenField.ObjectReferences.RootReturnKinds ?? AcpiNamedObjectKinds.None) & AcpiNamedObjectKinds.Buffer) == 0,
                "a partially read Field scope was skipped to bind an outer Buffer");
        });
        Add("static object analysis never discovers Field definitions or references inside opaque data", () =>
        {
            byte[] fake = AcpiJoin(AcpiObjectRegion("REG0", 1), AcpiObjectField("REG0", AcpiObjectFieldName("FLD0", 8)),
                AcpiObjectStore(new byte[] { 0x6a }, AcpiName("FLD0")));
            foreach (byte[] value in new[] { AcpiBuffer(fake), AcpiPackage(new byte[] { 0x12 }, AcpiJoin(new byte[] { 1 }, fake)) })
            {
                var report = InspectAcpiFlow(AcpiReturn(AcpiName("FLD0")), AcpiObjectName("DATA", value));
                Check(((report.ObjectReferences.RootReferencedKinds ?? AcpiNamedObjectKinds.None) & AcpiNamedObjectKinds.Field) == 0,
                    "opaque data smuggled an observed Field");
                Equal<int?>(0, report.ObjectReferences.RootClassifiedReferences);
                Equal<bool?>(null, report.ObjectReferences.RootStoresArg2ToReturnedObject);
            }
        });
        Add("static object classification respects duplicate opaque and explicitly scoped declarations", () =>
        {
            byte[] returning = AcpiReturn(AcpiName("BUF0"));
            var duplicate = InspectAcpiFlow(returning,
                AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })), AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 1 })));
            Check(((duplicate.ObjectReferences.RootReturnKinds ?? AcpiNamedObjectKinds.None) & AcpiNamedObjectKinds.Buffer) == 0,
                "duplicate declarations produced a unique Buffer");
            byte[][] opaque = {
                AcpiJoin(new byte[] { 6 }, AcpiName("SRC0"), AcpiName("BUF0")),
                AcpiJoin(new byte[] { 0x15 }, AcpiName("BUF0"), new byte[] { 1, 0 }) };
            foreach (byte[] declaration in opaque)
            {
                var report = InspectAcpiFlow(returning, AcpiObjectName("SRC0", AcpiBuffer(new byte[] { 0 })), declaration);
                Check(((report.ObjectReferences.RootReturnKinds ?? AcpiNamedObjectKinds.None) & AcpiNamedObjectKinds.Buffer) == 0,
                    "an alias or External declaration inferred a Buffer value");
            }

            byte[] rootBuffer = AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 }));
            foreach (var sample in new[] {
                new KeyValuePair<byte[], AcpiNamedObjectKinds>(AcpiName("BUF0"), AcpiNamedObjectKinds.Integer),
                new KeyValuePair<byte[], AcpiNamedObjectKinds>(AcpiJoin(new byte[] { 0x5c }, AcpiName("BUF0")), AcpiNamedObjectKinds.Buffer) })
            {
                byte[] nested = AcpiDevice("DEV0", AcpiJoin(AcpiObjectName("BUF0", new byte[] { 0x0a, 9 }),
                    AcpiWdg(), AcpiMethod("WMAB", 3, AcpiReturn(sample.Key))));
                var report = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(rootBuffer, nested)));
                Equal<AcpiNamedObjectKinds?>(sample.Value, report.ObjectReferences.RootReturnKinds);
            }
            byte[] missing = AcpiJoin(new byte[] { 0x5c, 0x2e }, AcpiName("DEV0"), AcpiName("BUF0"));
            var absent = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(rootBuffer,
                AcpiDevice("DEV0", AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 3, AcpiReturn(missing)))))));
            Equal<int?>(0, absent.ObjectReferences.RootClassifiedReferences);
            Equal<bool?>(null, absent.ObjectReferences.RootStoresArg2ToReturnedObject);
        });
        Add("runtime-created fields make static declaration relations uncertain without executing namespace changes", () =>
        {
            var report = InspectAcpiFlow(AcpiJoin(new byte[] { 0x8c, 0x6a, 0 }, AcpiName("BUF0"),
                AcpiObjectStore(new byte[] { 0x6a }, AcpiName("BUF0")), AcpiReturn(AcpiName("BUF0"))),
                AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })));
            Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
            Equal<int?>(0, report.Flow.RootCallSites);
            Equal(AcpiReferenceAnalysisStatus.Partial, report.ObjectReferences.Status);
            Check(((report.ObjectReferences.RootReturnKinds ?? AcpiNamedObjectKinds.None) & AcpiNamedObjectKinds.Buffer) == 0,
                "a runtime-created field retained the hidden Buffer classification");
            Equal<bool?>(null, report.ObjectReferences.RootStoresArg2ToReturnedObject);

            var helperCreation = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("BUF0")),
                AcpiName("HLP0"), AcpiReturn(AcpiName("BUF0"))),
                AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })),
                AcpiMethod("HLP0", 0, AcpiJoin(new byte[] { 0x8c }, AcpiBuffer(new byte[] { 0 }),
                    new byte[] { 0 }, AcpiName("BUF0"))));
            Equal(AcpiMethodSyntaxStatus.Parsed, helperCreation.MethodSyntax);
            Equal(1, helperCreation.Flow.ParsedHelpers); Equal(1, helperCreation.ObjectReferences.ParsedHelpers);
            Equal(AcpiReferenceAnalysisStatus.Partial, helperCreation.ObjectReferences.Status);
            Equal<bool?>(null, helperCreation.ObjectReferences.RootStoresArg2ToReturnedObject);
            Check(((helperCreation.ObjectReferences.RootReturnKinds ?? AcpiNamedObjectKinds.None) & AcpiNamedObjectKinds.Buffer) == 0,
                "a parsed helper's created name did not invalidate a hidden root declaration");
        });
        Add("static named method references are classified without invoking or following the referenced method", () =>
        {
            var report = InspectAcpiFlow(AcpiJoin(new byte[] { 0xa4, 0x8e }, AcpiName("HLP0")),
                AcpiMethod("HLP0", 1, new byte[] { 0xa4, 0x0a, 0xff }));
            Equal(AcpiMethodSyntaxStatus.Parsed, report.MethodSyntax);
            Equal<int?>(0, report.Flow.RootCallSites); Equal(0, report.Flow.InspectedHelpers);
            Equal<AcpiNamedObjectKinds?>(AcpiNamedObjectKinds.MethodReference, report.ObjectReferences.RootReferencedKinds);
            Equal<bool?>(null, report.Flow.ParsedHelperLiteralFfReturn);
            Equal<bool?>(false, report.LiteralFfReturn);
        });
        Add("static object analysis discards unsupported root and helper prefix relations", () =>
        {
            byte[] relation = AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("BUF0")), AcpiReturn(AcpiName("BUF0")));
            var root = InspectAcpiFlow(AcpiJoin(relation, new byte[] { 0xfe }), AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })));
            Equal(AcpiReferenceAnalysisStatus.NotInspected, root.ObjectReferences.Status);
            Equal<int?>(null, root.ObjectReferences.RootNamedReferences);
            Equal<AcpiNamedObjectKinds?>(null, root.ObjectReferences.RootReferencedKinds);
            Equal<bool?>(null, root.ObjectReferences.RootStoresArg2ToReturnedObject);

            var helper = InspectAcpiFlow(AcpiJoin(AcpiName("HLP0"), AcpiReturn(AcpiName("BUF0"))),
                AcpiMethod("HLP0", 0, AcpiJoin(AcpiObjectStore(new byte[] { 0 }, AcpiName("BUF0")), new byte[] { 0xfe })),
                AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })));
            Equal(0, helper.ObjectReferences.ParsedHelpers);
            Equal<int?>(null, helper.ObjectReferences.ParsedHelperNamedReferences);
            Equal<AcpiNamedObjectKinds?>(null, helper.ObjectReferences.ParsedHelperStoreTargetKinds);
            Equal<bool?>(null, helper.ObjectReferences.RootReturnedObjectReferencedByParsedHelper);
            Equal<bool?>(null, helper.ObjectReferences.RootArg2StoreObjectReferencedByParsedHelper);
        });
        Add("static object relation limits count unique names while preserving old root syntax and repeated reference counts", () =>
        {
            var declarations = new List<byte[]>(); var references = new List<byte[]>();
            for (int i = 0; i < 65; i++)
            {
                string name = "B" + i.ToString("D3");
                declarations.Add(AcpiObjectName(name, AcpiBuffer(new byte[] { 0 })));
                references.Add(AcpiObjectStore(AcpiName(name), new byte[] { 0x60 }));
            }
            references.Add(new byte[] { 0xa4, 0x6a });
            var limited = InspectAcpiFlow(AcpiJoin(references.ToArray()), declarations.ToArray());
            Equal(AcpiReferenceAnalysisStatus.LimitExceeded, limited.ObjectReferences.Status);
            Equal(AcpiRoutingStatus.Complete, limited.Status); Equal(AcpiMethodSyntaxStatus.Parsed, limited.MethodSyntax);
            Equal<bool?>(false, limited.LiteralFfReturn); Equal<int?>(1, limited.Flow.RootReturnStatements);

            byte[] repeated = AcpiJoin(Enumerable.Range(0, 100)
                .Select(_ => AcpiObjectStore(AcpiName("BUF0"), new byte[] { 0x60 }))
                .Concat(new[] { new byte[] { 0xa4, 0x6a } }).ToArray());
            var repeat = InspectAcpiFlow(repeated, AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })));
            Equal(AcpiReferenceAnalysisStatus.ClassifiedObservedSyntax, repeat.ObjectReferences.Status);
            Equal<int?>(100, repeat.ObjectReferences.RootNamedReferences); Equal<int?>(100, repeat.ObjectReferences.RootClassifiedReferences);
            Equal(100, repeat.Flow.UnresolvedNameReferences);
        });
        Add("partial namespaces retain observed object relations and unknown references stay indeterminate", () =>
        {
            var report = AcpiWmiRoutingInspector.Inspect(AcpiTable(AcpiJoin(AcpiWdg(),
                AcpiMethod("WMAB", 3, AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("BUF0")), AcpiReturn(AcpiName("BUF0")))),
                AcpiObjectName("BUF0", AcpiBuffer(new byte[] { 0 })), new byte[] { 0xfe })));
            Equal(AcpiRoutingStatus.Partial, report.Status);
            Equal(AcpiReferenceAnalysisStatus.Partial, report.ObjectReferences.Status);
            Equal<bool?>(true, report.ObjectReferences.RootStoresArg2ToReturnedObject);
            Equal<AcpiNamedObjectKinds?>(AcpiNamedObjectKinds.Buffer, report.ObjectReferences.RootReturnKinds);

            var unknown = InspectAcpiFlow(AcpiJoin(AcpiObjectStore(new byte[] { 0x6a }, AcpiName("MISS")), AcpiReturn(AcpiName("MISS"))));
            Equal(AcpiReferenceAnalysisStatus.Partial, unknown.ObjectReferences.Status);
            Equal<bool?>(null, unknown.ObjectReferences.RootStoresArg2ToReturnedObject);
            Equal<bool?>(null, unknown.ObjectReferences.RootReturnedObjectReferencedByParsedHelper);
        });
        Add("static object reports are immutable and omit names paths addresses operands and hardware capabilities", () =>
        {
            byte[] table = AcpiTable(AcpiJoin(AcpiWdg(), AcpiMethod("WMAB", 3,
                AcpiJoin(AcpiObjectStore(AcpiName("STR0"), new byte[] { 0x60 }), AcpiReturn(AcpiName("HLP0")))),
                AcpiMethod("HLP0", 0, AcpiObjectStore(new byte[] { 0 }, AcpiName("FLD0"))),
                AcpiObjectRegion("REG0", 1), AcpiObjectField("REG0", AcpiObjectFieldName("FLD0", 8)),
                AcpiObjectName("STR0", AcpiJoin(new byte[] { 0x0d }, Encoding.ASCII.GetBytes("C:\\Users\\PrivateOwner\\Firmware"), new byte[] { 0 }))));
            byte[] copy = (byte[])table.Clone(); var report = AcpiWmiRoutingInspector.Inspect(table);
            Check(table.SequenceEqual(copy), "object classification changed the caller table");
            Array.Clear(table, 0, table.Length);
            foreach (var field in report.ObjectReferences.GetType().GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
            {
                Type type = Nullable.GetUnderlyingType(field.FieldType) ?? field.FieldType;
                Check(field.IsInitOnly && (type.IsEnum || type == typeof(int) || type == typeof(bool)), "object report retained raw data");
            }
            string text = report.ToDisplayText();
            foreach (string raw in new[] { "HLP0", "REG0", "FLD0", "WMAB", "PRIVATE", "PrivateOwner", "C:\\Users", "DEADBEEF", "deadbeef", "C16C47BA" })
                Check(!text.Contains(raw), "object report exported a firmware identifier or address");
            Check(!report.ObjectReferences.CanInvokeMethods && !report.ObjectReferences.CanWriteHardware &&
                !report.CanInvokeMethods && !report.CanWriteHardware, "static declarations enabled hardware access");
        });
    }

    private static byte[] AcpiObjectName(string name, byte[] value)
        => AcpiJoin(new byte[] { 8 }, AcpiName(name), value);

    private static byte[] AcpiObjectStore(byte[] source, byte[] target)
        => AcpiJoin(new byte[] { 0x70 }, source, target);

    private static byte[] AcpiObjectRegion(string name, byte space)
        => AcpiExtended(0x80, AcpiName(name), new byte[] { space, 0x0c, 0xef, 0xbe, 0xad, 0xde, 0x0a, 0x80 });

    private static byte[] AcpiObjectField(string region, params byte[][] entries)
        => AcpiPackage(new byte[] { 0x5b, 0x81 }, AcpiJoin(new[] { AcpiName(region), new byte[] { 0 } }.Concat(entries).ToArray()));

    private static byte[] AcpiObjectFieldName(string name, int bits) => AcpiJoin(AcpiName(name), AcpiObjectFieldBitLength(bits));

    private static byte[] AcpiObjectFieldBitLength(int value)
    {
        if (value < 64) return new byte[] { (byte)value };
        if (value < 4096) return new byte[] { (byte)(0x40 | (value & 15)), (byte)(value >> 4) };
        if (value < 1048576) return new byte[] { (byte)(0x80 | (value & 15)), (byte)(value >> 4), (byte)(value >> 12) };
        return new byte[] { (byte)(0xc0 | (value & 15)), (byte)(value >> 4), (byte)(value >> 12), (byte)(value >> 20) };
    }
}
