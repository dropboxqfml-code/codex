using System;
using System.Reflection;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiParameterMetadataTests()
    {
        Add("WMI parameter metadata preserves unresolved legacy object definitions", () =>
        {
            var unobserved = new WsabiWmiParameterMetadata();
            Equal(WsabiWmiParameterShape.NotChecked, unobserved.Shape);
            Equal(WsabiWmiParameterBinding.Unknown, unobserved.Binding);
            Equal<bool?>(null, unobserved.IsDataBuffer);
            var unresolved = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, null, null);
            Equal(WsabiWmiParameterShape.ScalarObject, unresolved.Shape);
            Equal(WsabiWmiQualifierMatch.Missing, unresolved.EmbeddedInstanceMatch);
            Equal(WsabiWmiQualifierMatch.Missing, unresolved.CimTypeMatch);
            Equal(WsabiWmiParameterBinding.Unknown, unresolved.Binding);
            Equal<bool?>(null, unresolved.IsDataBuffer);
            var generic = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, null, "object");
            Equal(WsabiWmiQualifierMatch.UnspecifiedObject, generic.CimTypeMatch);
            Equal(WsabiWmiParameterBinding.Unknown, generic.Binding);
            Equal<bool?>(null, generic.IsDataBuffer);
        });
        Add("WMI parameter binding supports standard CIMTYPE and embedded class representations", () =>
        {
            foreach (string value in new[] { "object:DataBuffer", "OBJECT:DATABUFFER", "ObJeCt:dAtAbUfFeR" })
            {
                Equal(WsabiWmiQualifierMatch.MatchesDataBuffer, WsabiWmiContractMetadataPolicy.NormalizeCimType(value));
                var metadata = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, null, value);
                Equal(WsabiWmiQualifierMatch.Missing, metadata.EmbeddedInstanceMatch);
                Equal(WsabiWmiParameterBinding.MatchesDataBuffer, metadata.Binding);
                Equal<bool?>(true, metadata.IsDataBuffer);
            }
            foreach (object cim in new object[] { null, "object", "object:DataBuffer" })
            {
                var metadata = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, "databuffer", cim);
                Equal(WsabiWmiQualifierMatch.MatchesDataBuffer, metadata.EmbeddedInstanceMatch);
                Equal(WsabiWmiParameterBinding.MatchesDataBuffer, metadata.Binding);
                Equal<bool?>(true, metadata.IsDataBuffer);
            }
        });
        Add("WMI qualifier conflicts stay unresolved and explicit other definitions remain false", () =>
        {
            foreach (var values in new[] {
                new object[] { "DataBuffer", "object:OtherBuffer" },
                new object[] { "OtherBuffer", "object:DataBuffer" },
                new object[] { "DataBuffer", "string" } })
            {
                var metadata = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, values[0], values[1]);
                Equal(WsabiWmiParameterBinding.ConflictingQualifiers, metadata.Binding);
                Equal<bool?>(null, metadata.IsDataBuffer);
            }
            foreach (var values in new[] {
                new object[] { "OtherBuffer", null },
                new object[] { null, "object:OtherBuffer" },
                new object[] { "OtherBuffer", "object" },
                new object[] { "OtherBuffer", "object:AnotherBuffer" },
                new object[] { null, "uint8" } })
            {
                var metadata = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, values[0], values[1]);
                Equal(WsabiWmiParameterBinding.OtherDefinition, metadata.Binding);
                Equal<bool?>(false, metadata.IsDataBuffer);
            }
        });
        Add("WMI malformed qualifiers cannot be overridden by a matching class qualifier", () =>
        {
            foreach (object invalid in new object[] { DBNull.Value, 1, true, new object(), new[] { "DataBuffer" },
                "", " DataBuffer", "DataBuffer ", "Data Buffer", "DataBuffer\n", "DataBuffer\0", "1DataBuffer",
                @"root\WMI:DataBuffer", @"C:\Users\PrivateName", "DataBuffer[]", "DataBuffer.Other", new string('x', 97) })
            {
                Equal(WsabiWmiQualifierMatch.Invalid, WsabiWmiContractMetadataPolicy.NormalizeEmbeddedInstance(invalid));
                var metadata = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, invalid, "object:DataBuffer");
                Equal(WsabiWmiParameterBinding.InvalidMetadata, metadata.Binding);
                Equal<bool?>(null, metadata.IsDataBuffer);
            }
            foreach (object invalid in new object[] { DBNull.Value, 1, new object(), new[] { "object:DataBuffer" },
                "", " object:DataBuffer", "object:DataBuffer ", "object:Data Buffer", "object:DataBuffer\n",
                "object:", "object:1Buffer", "object:DataBuffer:Other", @"object:root\WMI:DataBuffer",
                "object:DataBuffer[]", "DataBuffer", "object[]", new string('x', 97) })
            {
                Equal(WsabiWmiQualifierMatch.Invalid, WsabiWmiContractMetadataPolicy.NormalizeCimType(invalid));
                var metadata = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, "DataBuffer", invalid);
                Equal(WsabiWmiParameterBinding.InvalidMetadata, metadata.Binding);
                Equal<bool?>(null, metadata.IsDataBuffer);
            }
        });
        Add("WMI parameter shape prevents qualifiers from establishing a mismatched type", () =>
        {
            foreach (bool exists in new[] { false, true })
            foreach (bool scalar in new[] { false, true })
            {
                var metadata = WsabiWmiContractMetadataPolicy.InspectParameter(exists, scalar, "DataBuffer", "object:DataBuffer");
                if (exists && scalar) continue;
                Equal(exists ? WsabiWmiParameterShape.Other : WsabiWmiParameterShape.Missing, metadata.Shape);
                Equal(WsabiWmiQualifierMatch.Missing, metadata.EmbeddedInstanceMatch);
                Equal(WsabiWmiQualifierMatch.Missing, metadata.CimTypeMatch);
                Equal(WsabiWmiParameterBinding.OtherDefinition, metadata.Binding);
                Equal<bool?>(false, metadata.IsDataBuffer);
            }
        });
        Add("WMI qualifier normalization keeps strict identifier and length boundaries", () =>
        {
            Equal(WsabiWmiQualifierMatch.Missing, WsabiWmiContractMetadataPolicy.NormalizeEmbeddedInstance(null));
            Equal(WsabiWmiQualifierMatch.Missing, WsabiWmiContractMetadataPolicy.NormalizeCimType(null));
            foreach (string value in new[] { "OtherBuffer", "_Other_2", new string('a', 96) })
                Equal(WsabiWmiQualifierMatch.Other, WsabiWmiContractMetadataPolicy.NormalizeEmbeddedInstance(value));
            Equal(WsabiWmiQualifierMatch.Other, WsabiWmiContractMetadataPolicy.NormalizeCimType("object:" + new string('a', 89)));
            Equal(WsabiWmiQualifierMatch.Invalid, WsabiWmiContractMetadataPolicy.NormalizeCimType("object:" + new string('a', 90)));
            Equal(WsabiWmiQualifierMatch.Invalid, WsabiWmiContractMetadataPolicy.NormalizeEmbeddedInstance(new string('a', 97)));
            foreach (string type in new[] { "boolean", "char16", "datetime", "real32", "real64", "sint8", "sint16",
                "sint32", "sint64", "string", "uint8", "uint16", "uint32", "uint64", "reference" })
                Equal(WsabiWmiQualifierMatch.Other, WsabiWmiContractMetadataPolicy.NormalizeCimType(type.ToUpperInvariant()));
        });
        Add("WMI parameter metadata has no mutable or raw text state and never permits hardware calls", () =>
        {
            foreach (var metadata in new[] {
                new WsabiWmiParameterMetadata(),
                WsabiWmiContractMetadataPolicy.InspectParameter(false, false, null, null),
                WsabiWmiContractMetadataPolicy.InspectParameter(true, false, null, null),
                WsabiWmiContractMetadataPolicy.InspectParameter(true, true, null, null),
                WsabiWmiContractMetadataPolicy.InspectParameter(true, true, null, "object:DataBuffer"),
                WsabiWmiContractMetadataPolicy.InspectParameter(true, true, "DataBuffer", "object:OtherBuffer"),
                WsabiWmiContractMetadataPolicy.InspectParameter(true, true, "DataBuffer", "PrivateName is invalid") })
            {
                Check(!metadata.CanInvokeMethods && !metadata.CanReadHardware && !metadata.CanWriteHardware,
                    "parameter metadata enabled a hardware path");
            }
            foreach (var property in typeof(WsabiWmiParameterMetadata).GetProperties())
                Check(!property.CanWrite && property.PropertyType != typeof(string), "mutable or raw parameter metadata");
            foreach (var field in typeof(WsabiWmiParameterMetadata).GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                Check(field.FieldType != typeof(string) && field.FieldType != typeof(object), "raw qualifier state retained");
        });
        Add("WMI parameter metadata rejects impossible enum inputs without producing a match", () =>
        {
            var invalidShape = new WsabiWmiParameterMetadata((WsabiWmiParameterShape)999,
                WsabiWmiQualifierMatch.MatchesDataBuffer, WsabiWmiQualifierMatch.MatchesDataBuffer);
            Equal(WsabiWmiParameterBinding.InvalidMetadata, invalidShape.Binding);
            Equal<bool?>(null, invalidShape.IsDataBuffer);
            foreach (WsabiWmiQualifierMatch embedded in new[] { (WsabiWmiQualifierMatch)999, WsabiWmiQualifierMatch.UnspecifiedObject })
            {
                var invalid = new WsabiWmiParameterMetadata(WsabiWmiParameterShape.ScalarObject, embedded,
                    WsabiWmiQualifierMatch.MatchesDataBuffer);
                Equal(WsabiWmiParameterBinding.InvalidMetadata, invalid.Binding);
                Equal<bool?>(null, invalid.IsDataBuffer);
            }
            var invalidCim = new WsabiWmiParameterMetadata(WsabiWmiParameterShape.ScalarObject,
                WsabiWmiQualifierMatch.MatchesDataBuffer, (WsabiWmiQualifierMatch)999);
            Equal(WsabiWmiParameterBinding.InvalidMetadata, invalidCim.Binding);
            Equal<bool?>(null, invalidCim.IsDataBuffer);
        });
    }
}
