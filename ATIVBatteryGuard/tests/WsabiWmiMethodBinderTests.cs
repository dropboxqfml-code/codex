using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiMethodBinderTests()
    {
        Add("offline WMI binding accepts detailed observed CIMTYPE definitions without enabling calls", () =>
        {
            foreach (uint id in new uint[] { 0, 1, uint.MaxValue })
            {
                var report = BinderCompleteMetadata(id);
                WsabiWmiMethodBinder binder;
                Check(WsabiWmiMethodBinder.TryCreate(report, out binder), "complete detailed metadata rejected");
                Equal(id, binder.ObservedMethodId);
                Equal(WsabiWmiContractMetadataPolicy.LocalNamespace, binder.Namespace);
                Equal("WmiAcpiMethod", binder.ClassName);
                Equal("CallSabiFunction", binder.MethodName);
                Equal("inData", binder.InputName);
                Equal("outData", binder.OutputName);
                Equal("DataBuffer", binder.BufferClass);
                Equal("Bytes", binder.BytesName);
                Check(!binder.CanInvokeMethods && !binder.CanReadHardware && !binder.CanWriteHardware,
                    "metadata binding became a hardware permission");
            }
        });
        Add("offline WMI binding rejects earlier partial observations and bool-only compatibility reports", () =>
        {
            var partial = new WsabiWmiContractMetadataReport(new WsabiWmiContractMethodMetadata(
                WsabiWmiMetadataStatus.Partial, WsabiWmiGuidMatch.MatchesPublicCandidate, 1, null, null, true),
                new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, true));
            var legacy = new WsabiWmiContractMetadataReport(new WsabiWmiContractMethodMetadata(
                WsabiWmiMetadataStatus.Complete, WsabiWmiGuidMatch.MatchesPublicCandidate, 1, true, true, true),
                new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, true));
            foreach (var report in new[] { null, partial, legacy, new WsabiWmiContractMetadataReport() })
            {
                WsabiWmiMethodBinder binder = BinderCreate();
                Check(!WsabiWmiMethodBinder.TryCreate(report, out binder), "incomplete or legacy report established a binding");
                Check(binder == null, "failed binding retained a prior plan");
            }
            var match = BinderMatchedParameter();
            foreach (WsabiWmiMetadataStatus status in Enum.GetValues(typeof(WsabiWmiMetadataStatus)))
            {
                if (status == WsabiWmiMetadataStatus.Complete) continue;
                var badMethod = new WsabiWmiContractMetadataReport(WsabiWmiContractMethodMetadata.FromParameters(
                    status, WsabiWmiGuidMatch.MatchesPublicCandidate, 1, true, match, match),
                    new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, true));
                var badBuffer = new WsabiWmiContractMetadataReport(WsabiWmiContractMethodMetadata.FromParameters(
                    WsabiWmiMetadataStatus.Complete, WsabiWmiGuidMatch.MatchesPublicCandidate, 1, true, match, match),
                    new WsabiWmiContractBufferMetadata(status, true));
                WsabiWmiMethodBinder binder;
                Check(!WsabiWmiMethodBinder.TryCreate(badMethod, out binder) && binder == null, "method partial/failure accepted");
                Check(!WsabiWmiMethodBinder.TryCreate(badBuffer, out binder) && binder == null, "buffer partial/failure accepted");
            }
        });
        Add("offline WMI binding requires both detailed parameter shapes and every fixed contract fact", () =>
        {
            var match = BinderMatchedParameter();
            var badParameters = new[] {
                new WsabiWmiParameterMetadata(),
                WsabiWmiContractMetadataPolicy.InspectParameter(false, false, null, null),
                WsabiWmiContractMetadataPolicy.InspectParameter(true, false, "DataBuffer", "object:DataBuffer"),
                WsabiWmiContractMetadataPolicy.InspectParameter(true, true, null, null),
                WsabiWmiContractMetadataPolicy.InspectParameter(true, true, null, "object"),
                WsabiWmiContractMetadataPolicy.InspectParameter(true, true, "OtherBuffer", "object:DataBuffer"),
                WsabiWmiContractMetadataPolicy.InspectParameter(true, true, null, "object:OtherBuffer"),
                WsabiWmiContractMetadataPolicy.InspectParameter(true, true, "DataBuffer", "private malformed definition")
            };
            foreach (var invalid in badParameters)
            foreach (bool inputSide in new[] { false, true })
            {
                var report = new WsabiWmiContractMetadataReport(WsabiWmiContractMethodMetadata.FromParameters(
                    WsabiWmiMetadataStatus.Complete, WsabiWmiGuidMatch.MatchesPublicCandidate, 1, true,
                    inputSide ? invalid : match, inputSide ? match : invalid),
                    new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, true));
                WsabiWmiMethodBinder binder;
                Check(!WsabiWmiMethodBinder.TryCreate(report, out binder) && binder == null, "invalid parameter accepted");
            }
            foreach (var report in new[] {
                BinderMetadata(WsabiWmiGuidMatch.Other, 1, true, true),
                BinderMetadata(WsabiWmiGuidMatch.Missing, 1, true, true),
                BinderMetadata(WsabiWmiGuidMatch.Invalid, 1, true, true),
                BinderMetadata(WsabiWmiGuidMatch.MatchesPublicCandidate, null, true, true),
                BinderMetadata(WsabiWmiGuidMatch.MatchesPublicCandidate, 1, false, true),
                BinderMetadata(WsabiWmiGuidMatch.MatchesPublicCandidate, 1, true, false) })
            {
                WsabiWmiMethodBinder binder;
                Check(!WsabiWmiMethodBinder.TryCreate(report, out binder) && binder == null, "missing fixed fact accepted");
            }
        });
        Add("offline WMI request packages canonical nested bytes while preserving independent method and command numbers", () =>
        {
            var binder = BinderCreate();
            byte[] payload = new byte[16];
            for (int index = 0; index < payload.Length; index++) payload[index] = (byte)(index * 11 + 3);
            WsabiWmiMethodRequest request;
            Check(binder.TryPrepareRequest(0x1234, payload, out request), "valid structural request rejected");
            Equal((uint)1, request.ObservedMethodId);
            Equal((ushort)0x1234, request.FirmwareCommand);
            byte[] frame = request.Frame;
            Equal(21, frame.Length);
            Equal((byte)0x43, frame[0]); Equal((byte)0x58, frame[1]);
            Equal((byte)0x34, frame[2]); Equal((byte)0x12, frame[3]); Equal((byte)0, frame[4]);
            for (int index = 0; index < payload.Length; index++) Equal(payload[index], frame[index + 5]);
            var arguments = request.Arguments;
            Equal(1, arguments.Count);
            var buffer = arguments["inData"] as IReadOnlyDictionary<string, object>;
            Check(buffer != null, "inData embedded snapshot absent");
            Equal(1, buffer.Count);
            byte[] nested = buffer["Bytes"] as byte[];
            Check(nested != null && nested.Length == 21, "Bytes is not the complete frame");
            for (int index = 0; index < frame.Length; index++) Equal(frame[index], nested[index]);
            Check(!request.CanInvokeMethods && !request.CanReadHardware && !request.CanWriteHardware,
                "request preparation enabled an OEM call");
        });
        Add("offline WMI request snapshots are deeply independent and their dictionaries reject replacement", () =>
        {
            var binder = BinderCreate();
            byte[] payload = new byte[16]; payload[0] = 7;
            WsabiWmiMethodRequest request;
            Check(binder.TryPrepareRequest(0x1234, payload, out request), "request rejected");
            var first = request.Arguments;
            var firstBuffer = (IReadOnlyDictionary<string, object>)first["inData"];
            byte[] firstBytes = (byte[])firstBuffer["Bytes"];
            payload[0] = 99; firstBytes[5] = 88;
            byte[] exposed = request.Frame; exposed[5] = 77;
            var second = request.Arguments;
            var secondBuffer = (IReadOnlyDictionary<string, object>)second["inData"];
            byte[] secondBytes = (byte[])secondBuffer["Bytes"];
            Equal((byte)7, secondBytes[5]); Equal((byte)7, request.Frame[5]);
            Check(!ReferenceEquals(first, second) && !ReferenceEquals(firstBuffer, secondBuffer) &&
                !ReferenceEquals(firstBytes, secondBytes), "nested request storage shared across snapshots");
            BinderMustBeReadOnly(() => ((IDictionary<string, object>)first)["inData"] = null);
            BinderMustBeReadOnly(() => ((IDictionary<string, object>)firstBuffer)["Bytes"] = null);
            Equal((byte)7, ((byte[])((IReadOnlyDictionary<string, object>)request.Arguments["inData"])["Bytes"])[5]);
        });
        Add("offline WMI invalid request clears a previous prepared envelope", () =>
        {
            var binder = BinderCreate();
            WsabiWmiMethodRequest request;
            Check(binder.TryPrepareRequest(0, new byte[16], out request), "baseline request rejected");
            foreach (int command in new[] { -1, int.MinValue, ushort.MaxValue + 1, int.MaxValue })
            {
                Check(!binder.TryPrepareRequest(command, new byte[16], out request), "out of range command accepted");
                Check(request == null, "invalid command retained earlier request");
            }
            foreach (object payload in new object[] { null, "private bytes", new int[16], new byte[15], new byte[17], new byte[1, 16],
                Array.CreateInstance(typeof(byte), new[] { 16 }, new[] { 1 }) })
            {
                Check(binder.TryPrepareRequest(ushort.MaxValue, new byte[16], out request), "valid boundary request rejected");
                Check(!binder.TryPrepareRequest(1, payload, out request), "invalid payload accepted");
                Check(request == null, "invalid payload retained earlier request");
            }
        });
        Add("offline WMI method API failure wins without reading any output field", () =>
        {
            var binder = BinderCreate();
            var output = new BinderLookupOnlyDictionary(key => { throw new InvalidOperationException("private provider detail"); });
            foreach (int code in new[] { 1, 2, -1, int.MinValue, int.MaxValue, unchecked((int)0x80041003) })
            foreach (object value in new object[] { null, new object(), output, BinderOutput(BinderReply()) })
            {
                var result = binder.DecodeOutput(code, value);
                BinderAssertEnvelopeFailure(result, WsabiWmiMethodReplyStatus.ApiNotSuccessful);
            }
            Equal(0, output.Calls);
        });
        Add("offline WMI method output distinguishes missing containers members and failed fixed reads", () =>
        {
            var binder = BinderCreate();
            BinderAssertEnvelopeFailure(binder.DecodeOutput(0, null), WsabiWmiMethodReplyStatus.MissingOutput);
            foreach (object output in new object[] { "private output", new object(), new byte[21], new Dictionary<string, byte[]>() })
                BinderAssertEnvelopeFailure(binder.DecodeOutput(0, output), WsabiWmiMethodReplyStatus.InvalidOutputType);
            BinderAssertEnvelopeFailure(binder.DecodeOutput(0, new Dictionary<string, object>()), WsabiWmiMethodReplyStatus.MissingOutData);
            foreach (object nested in new object[] { null, "private nested output", new object(), new byte[21], new Dictionary<string, byte[]>() })
                BinderAssertEnvelopeFailure(binder.DecodeOutput(0, new Dictionary<string, object> { { "outData", nested } }),
                    WsabiWmiMethodReplyStatus.InvalidOutDataType);
            BinderAssertEnvelopeFailure(binder.DecodeOutput(0, new Dictionary<string, object> {
                { "outData", new Dictionary<string, object> { { "OtherBytes", BinderReply() } } } }), WsabiWmiMethodReplyStatus.MissingBytes);
            var outerFailure = new BinderLookupOnlyDictionary(key => { throw new InvalidOperationException("private outer provider text"); });
            BinderAssertEnvelopeFailure(binder.DecodeOutput(0, outerFailure), WsabiWmiMethodReplyStatus.PropertyReadFailure);
            Equal(1, outerFailure.Calls);
            var nestedFailure = new BinderLookupOnlyDictionary(key => { throw new InvalidOperationException("private inner provider text"); });
            BinderAssertEnvelopeFailure(binder.DecodeOutput(0, new Dictionary<string, object> { { "outData", nestedFailure } }),
                WsabiWmiMethodReplyStatus.PropertyReadFailure);
            Equal(1, nestedFailure.Calls);
        });
        Add("offline WMI decoder performs only two canonical lookups and ignores unrelated return fields", () =>
        {
            var binder = BinderCreate();
            byte[] frame = BinderReply();
            var inner = new BinderLookupOnlyDictionary(key => {
                Equal("Bytes", key); return new KeyValuePair<bool, object>(true, frame);
            });
            var outer = new BinderLookupOnlyDictionary(key => {
                Equal("outData", key); return new KeyValuePair<bool, object>(true, inner);
            });
            var result = binder.DecodeOutput(0, outer);
            Equal(WsabiWmiMethodReplyStatus.FrameChecked, result.Status);
            Check(result.IsValidFrame, "valid fixed lookup path rejected");
            Equal(1, outer.Calls); Equal(1, inner.Calls);
            var unrelated = new Dictionary<string, object> {
                { "outData", new Dictionary<string, object> { { "Bytes", frame }, { "PrivateField", new object() } } },
                { "ReturnValue", 99 }, { "PrivatePath", @"C:\Users\PrivateName" } };
            Check(binder.DecodeOutput(0, unrelated).IsValidFrame, "unverified ReturnValue became an API success criterion");
            var wrongCase = new Dictionary<string, object>(StringComparer.Ordinal) { { "OUTDATA", inner } };
            BinderAssertEnvelopeFailure(binder.DecodeOutput(0, wrongCase), WsabiWmiMethodReplyStatus.MissingOutData);
            var insensitive = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase) { { "OUTDATA", inner } };
            Check(binder.DecodeOutput(0, insensitive).IsValidFrame, "detached snapshot comparer semantics were changed");
        });
        Add("offline WMI nested Bytes preserves every structural decoder error instead of treating envelope presence as success", () =>
        {
            var binder = BinderCreate();
            object[] values = { null, "private byte text", new int[21], new byte[1, 21],
                Array.CreateInstance(typeof(byte), new[] { 21 }, new[] { 1 }), new byte[0], new byte[16], new byte[22], new byte[21] };
            WsabiWmiReplyStatus[] expected = { WsabiWmiReplyStatus.MissingResponse, WsabiWmiReplyStatus.InvalidType,
                WsabiWmiReplyStatus.InvalidType, WsabiWmiReplyStatus.InvalidShape, WsabiWmiReplyStatus.InvalidShape,
                WsabiWmiReplyStatus.UnsupportedLength, WsabiWmiReplyStatus.UnsupportedLength, WsabiWmiReplyStatus.UnsupportedLength,
                WsabiWmiReplyStatus.InvalidAcknowledgement };
            for (int index = 0; index < values.Length; index++)
            {
                var result = binder.DecodeOutput(0, BinderOutput(values[index]));
                Equal(WsabiWmiMethodReplyStatus.FrameChecked, result.Status);
                Equal(expected[index], result.FrameReply.Status);
                Check(!result.IsValidFrame && !result.CanInvokeMethods && !result.CanReadHardware && !result.CanWriteHardware,
                    "invalid nested frame enabled a hardware path");
                Equal(0, result.Payload.Length);
            }
        });
        Add("offline WMI reply copies opaque payloads and retains neither output objects nor raw errors", () =>
        {
            var binder = BinderCreate();
            foreach (byte marker in new byte[] { 0, 1, 0xff })
            {
                byte[] frame = BinderReply();
                for (int index = 5; index < frame.Length; index++) frame[index] = marker;
                var output = BinderOutput(frame);
                var result = binder.DecodeOutput(0, output);
                Equal(WsabiWmiMethodReplyStatus.FrameChecked, result.Status);
                Equal(WsabiWmiReplyStatus.ValidFrame, result.FrameReply.Status);
                Check(result.IsValidFrame && !result.CanInvokeMethods && !result.CanReadHardware && !result.CanWriteHardware,
                    "payload interpreted as hardware state or permission");
                byte[] first = result.Payload;
                foreach (byte value in first) Equal(marker, value);
                first[0] = (byte)(marker ^ 0xff); frame[5] = (byte)(marker ^ 0xff);
                ((Dictionary<string, object>)output["outData"])["Bytes"] = "private replacement";
                Equal(marker, result.Payload[0]); Equal(marker, result.FrameReply.Payload[0]);
                Check(!ReferenceEquals(first, result.Payload), "reply payload storage leaked");
                BinderAssertEnvelopeFailure(binder.DecodeOutput(1, output), WsabiWmiMethodReplyStatus.ApiNotSuccessful);
                Equal(marker, result.Payload[0]);
            }
            foreach (var property in typeof(WsabiWmiMethodReplyResult).GetProperties())
                Check(!property.CanWrite && property.PropertyType != typeof(string) && property.PropertyType != typeof(object),
                    "reply has mutable or raw output property");
            foreach (var field in typeof(WsabiWmiMethodReplyResult).GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                Check(field.FieldType != typeof(object) && field.FieldType != typeof(string), "reply retained raw output or exception text");
        });
    }

    private static WsabiWmiParameterMetadata BinderMatchedParameter()
        => WsabiWmiContractMetadataPolicy.InspectParameter(true, true, null, "object:DataBuffer");

    private static WsabiWmiContractMetadataReport BinderCompleteMetadata(uint id = 1)
        => BinderMetadata(WsabiWmiGuidMatch.MatchesPublicCandidate, id, true, true);

    private static WsabiWmiContractMetadataReport BinderMetadata(WsabiWmiGuidMatch guid, uint? id, bool? found, bool? bytes)
    {
        var parameter = BinderMatchedParameter();
        return new WsabiWmiContractMetadataReport(WsabiWmiContractMethodMetadata.FromParameters(
            WsabiWmiMetadataStatus.Complete, guid, id, found, parameter, parameter),
            new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, bytes));
    }

    private static WsabiWmiMethodBinder BinderCreate()
    {
        WsabiWmiMethodBinder binder;
        Check(WsabiWmiMethodBinder.TryCreate(BinderCompleteMetadata(), out binder), "test setup could not bind metadata");
        return binder;
    }

    private static byte[] BinderReply()
    {
        byte[] frame = new byte[21]; frame[4] = 0xaa;
        for (int index = 5; index < frame.Length; index++) frame[index] = (byte)(index * 7 + 3);
        return frame;
    }

    private static Dictionary<string, object> BinderOutput(object bytes)
        => new Dictionary<string, object> { { "outData", new Dictionary<string, object> { { "Bytes", bytes } } } };

    private static void BinderAssertEnvelopeFailure(WsabiWmiMethodReplyResult result, WsabiWmiMethodReplyStatus status)
    {
        Equal(status, result.Status);
        Check(!result.IsValidFrame && result.FrameReply == null && !result.CanInvokeMethods &&
            !result.CanReadHardware && !result.CanWriteHardware, "envelope failure retained data or enabled hardware");
        Equal(0, result.Payload.Length);
    }

    private static void BinderMustBeReadOnly(Action mutate)
    {
        bool rejected = false;
        try { mutate(); } catch (NotSupportedException) { rejected = true; }
        Check(rejected, "snapshot dictionary accepted replacement");
    }

    private sealed class BinderLookupOnlyDictionary : IReadOnlyDictionary<string, object>
    {
        private readonly Func<string, KeyValuePair<bool, object>> lookup;
        internal int Calls { get; private set; }
        internal BinderLookupOnlyDictionary(Func<string, KeyValuePair<bool, object>> lookup) { this.lookup = lookup; }
        public bool TryGetValue(string key, out object value)
        {
            Calls++;
            var result = lookup(key);
            value = result.Value;
            return result.Key;
        }
        public object this[string key] => throw new InvalidOperationException("indexer must not be used");
        public int Count => throw new InvalidOperationException("count must not be read");
        public IEnumerable<string> Keys => throw new InvalidOperationException("keys must not be enumerated");
        public IEnumerable<object> Values => throw new InvalidOperationException("values must not be enumerated");
        public bool ContainsKey(string key) { throw new InvalidOperationException("only fixed TryGetValue is supported"); }
        public IEnumerator<KeyValuePair<string, object>> GetEnumerator() { throw new InvalidOperationException("members must not be enumerated"); }
        IEnumerator IEnumerable.GetEnumerator() { return GetEnumerator(); }
    }
}
