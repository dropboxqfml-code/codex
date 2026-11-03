using System.Collections.Generic;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Offline binding of detached field snapshots only. This class has no WMI
    // connection, native object factory, method invocation or default channel.
    // A snapshot must provide bounded in-memory lookups, never live provider
    // getters. Fixed canonical names are used without enumeration or coercion;
    // the snapshot's own comparer determines its lookup case sensitivity.
    public sealed class WsabiWmiMethodBinder
    {
        internal const string InputPropertyName = "inData";
        internal const string OutputPropertyName = "outData";
        internal const string BufferPropertyName = "Bytes";

        public string Namespace => WsabiWmiContractMetadataPolicy.LocalNamespace;
        public string ClassName => WsabiWmiContractMetadataPolicy.MethodClass;
        public string MethodName => WsabiWmiContractMetadataPolicy.MethodName;
        public string InputName => InputPropertyName;
        public string OutputName => OutputPropertyName;
        public string BufferClass => WsabiWmiContractMetadataPolicy.BufferClass;
        public string BytesName => BufferPropertyName;
        public uint ObservedMethodId { get; }
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        private WsabiWmiMethodBinder(uint observedMethodId)
        {
            ObservedMethodId = observedMethodId;
        }

        public static bool TryCreate(WsabiWmiContractMetadataReport report, out WsabiWmiMethodBinder binder)
        {
            binder = null;
            if (report == null || report.MethodMetadata.Status != WsabiWmiMetadataStatus.Complete ||
                report.BufferMetadata.Status != WsabiWmiMetadataStatus.Complete ||
                report.BindingStatus != WsabiWmiContractBindingStatus.MetadataShapeMatched ||
                !IsDetailedMatch(report.MethodMetadata.InputParameter) ||
                !IsDetailedMatch(report.MethodMetadata.OutputParameter)) return false;

            // The Windows dispatch number is metadata only. It neither chooses
            // a firmware command nor maps a different OS's dispatch numbering.
            binder = new WsabiWmiMethodBinder(report.MethodMetadata.MethodId.Value);
            return true;
        }

        private static bool IsDetailedMatch(WsabiWmiParameterMetadata parameter)
            => parameter != null && parameter.Shape == WsabiWmiParameterShape.ScalarObject &&
                parameter.Binding == WsabiWmiParameterBinding.MatchesDataBuffer && parameter.IsDataBuffer == true;

        public bool TryPrepareRequest(int command, object payload, out WsabiWmiMethodRequest request)
        {
            request = null;
            byte[] frame;
            if (!WsabiWmiRequestEncoder.TryEncode(command, payload, out frame)) return false;
            request = new WsabiWmiMethodRequest(ObservedMethodId, (ushort)command, frame);
            return true;
        }

        public WsabiWmiMethodReplyResult DecodeOutput(int apiResult, object output)
        {
            // S_FALSE and failed HRESULTs take priority over every output
            // lookup. ReturnValue is not an established success contract here.
            if (apiResult != 0) return Result(WsabiWmiMethodReplyStatus.ApiNotSuccessful);
            if (output == null) return Result(WsabiWmiMethodReplyStatus.MissingOutput);
            var fields = output as IReadOnlyDictionary<string, object>;
            if (fields == null) return Result(WsabiWmiMethodReplyStatus.InvalidOutputType);
            try
            {
                object embedded;
                if (!fields.TryGetValue(OutputPropertyName, out embedded))
                    return Result(WsabiWmiMethodReplyStatus.MissingOutData);
                var buffer = embedded as IReadOnlyDictionary<string, object>;
                if (buffer == null) return Result(WsabiWmiMethodReplyStatus.InvalidOutDataType);
                object bytes;
                if (!buffer.TryGetValue(BufferPropertyName, out bytes))
                    return Result(WsabiWmiMethodReplyStatus.MissingBytes);

                // Keep the existing exact byte-array, length and ACK rules.
                // No header echo, battery meaning or ReturnValue is inferred.
                return new WsabiWmiMethodReplyResult(WsabiWmiMethodReplyStatus.FrameChecked,
                    WsabiWmiReplyDecoder.Decode(apiResult, bytes));
            }
            catch
            {
                // Discard raw snapshots, errors and any partially read bytes.
                return Result(WsabiWmiMethodReplyStatus.PropertyReadFailure);
            }
        }

        private static WsabiWmiMethodReplyResult Result(WsabiWmiMethodReplyStatus status)
            => new WsabiWmiMethodReplyResult(status);
    }
}
