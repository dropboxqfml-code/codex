using System;
using System.Diagnostics;
using System.Management;
using System.Runtime.InteropServices;
using System.Security;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Diagnostics
{
    // Fixed class definitions and allowlisted qualifiers only. No instance access.
    internal static class WsabiWmiContractMetadataProbe
    {
        private static readonly TimeSpan TotalBudget = TimeSpan.FromSeconds(4);
        private static readonly TimeSpan QueryTimeout = TimeSpan.FromSeconds(2);

        internal static WsabiWmiContractMetadataReport Collect()
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
                return WsabiWmiContractMetadataReport.Failure(WsabiWmiMetadataStatus.UnsupportedPlatform);
            var elapsed = Stopwatch.StartNew();
            var method = ReadMethod(elapsed);
            var buffer = ReadBuffer(elapsed);
            return new WsabiWmiContractMetadataReport(method, buffer);
        }

        private static WsabiWmiContractMethodMetadata ReadMethod(Stopwatch elapsed)
        {
            if (elapsed.Elapsed >= TotalBudget) return new WsabiWmiContractMethodMetadata(WsabiWmiMetadataStatus.TimedOut);
            try
            {
                using (var schema = OpenClass(WsabiWmiContractMetadataPolicy.MethodClass, elapsed))
                {
                    schema.Get();
                    if (elapsed.Elapsed >= TotalBudget) return new WsabiWmiContractMethodMetadata(WsabiWmiMetadataStatus.TimedOut);
                    var guid = WsabiWmiContractMetadataPolicy.CompareGuid(ReadQualifier(schema.Qualifiers, "Guid"));
                    if (elapsed.Elapsed >= TotalBudget) return new WsabiWmiContractMethodMetadata(WsabiWmiMetadataStatus.TimedOut);
                    try
                    {
                        MethodData method = schema.Methods[WsabiWmiContractMetadataPolicy.MethodName];
                        if (elapsed.Elapsed >= TotalBudget) return new WsabiWmiContractMethodMetadata(WsabiWmiMetadataStatus.TimedOut);
                        if (method == null) return new WsabiWmiContractMethodMetadata(
                            WsabiWmiMetadataStatus.Partial, guidMatch: guid, methodFound: false);
                        uint? id = WsabiWmiContractMetadataPolicy.NormalizeMethodId(ReadQualifier(method.Qualifiers, "WmiMethodId"));
                        if (elapsed.Elapsed >= TotalBudget) return new WsabiWmiContractMethodMetadata(WsabiWmiMetadataStatus.TimedOut);
                        bool? input, output;
                        using (var definition = method.InParameters) input = ParameterIsDataBuffer(definition, "inData");
                        if (elapsed.Elapsed >= TotalBudget) return new WsabiWmiContractMethodMetadata(WsabiWmiMetadataStatus.TimedOut);
                        using (var definition = method.OutParameters) output = ParameterIsDataBuffer(definition, "outData");
                        if (elapsed.Elapsed >= TotalBudget) return new WsabiWmiContractMethodMetadata(WsabiWmiMetadataStatus.TimedOut);
                        return new WsabiWmiContractMethodMetadata(WsabiWmiMetadataStatus.Complete, guid, id, input, output, true);
                    }
                    catch (ManagementException exception) when (exception.ErrorCode == ManagementStatus.NotFound ||
                        exception.ErrorCode == ManagementStatus.InvalidMethod)
                    {
                        // A missing method is not a missing class; preserve the class GUID comparison.
                        if (elapsed.Elapsed >= TotalBudget) return new WsabiWmiContractMethodMetadata(WsabiWmiMetadataStatus.TimedOut);
                        return new WsabiWmiContractMethodMetadata(WsabiWmiMetadataStatus.Partial, guidMatch: guid, methodFound: false);
                    }
                }
            }
            catch (Exception exception) { return new WsabiWmiContractMethodMetadata(Classify(exception)); }
        }

        private static WsabiWmiContractBufferMetadata ReadBuffer(Stopwatch elapsed)
        {
            if (elapsed.Elapsed >= TotalBudget) return new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.TimedOut);
            try
            {
                using (var schema = OpenClass(WsabiWmiContractMetadataPolicy.BufferClass, elapsed))
                {
                    schema.Get();
                    if (elapsed.Elapsed >= TotalBudget) return new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.TimedOut);
                    PropertyData property = ReadProperty(schema, "Bytes");
                    bool matches = property != null && property.Type == CimType.UInt8 && property.IsArray;
                    if (elapsed.Elapsed >= TotalBudget) return new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.TimedOut);
                    return new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, matches);
                }
            }
            catch (Exception exception) { return new WsabiWmiContractBufferMetadata(Classify(exception)); }
        }

        private static ManagementClass OpenClass(string name, Stopwatch elapsed)
        {
            TimeSpan remaining = TotalBudget - elapsed.Elapsed;
            TimeSpan timeout = remaining < QueryTimeout ? remaining : QueryTimeout;
            if (timeout <= TimeSpan.Zero) throw new TimeoutException();
            var scope = new ManagementScope(@"\\.\" + WsabiWmiContractMetadataPolicy.LocalNamespace,
                new ConnectionOptions
                {
                    Timeout = timeout, EnablePrivileges = false,
                    Authentication = AuthenticationLevel.PacketPrivacy,
                    Impersonation = ImpersonationLevel.Impersonate
                });
            return new ManagementClass(scope, new ManagementPath(name),
                new ObjectGetOptions { UseAmendedQualifiers = false, Timeout = timeout });
        }

        private static object ReadQualifier(QualifierDataCollection qualifiers, string name)
        {
            if (qualifiers == null) return null;
            try
            {
                QualifierData qualifier = qualifiers[name];
                // Only Guid, WmiMethodId or EmbeddedInstance reaches this function.
                return qualifier == null ? null : qualifier.Value;
            }
            catch (ManagementException exception) when (exception.ErrorCode == ManagementStatus.NotFound) { return null; }
        }

        private static PropertyData ReadProperty(ManagementBaseObject definition, string name)
        {
            if (definition == null) return null;
            try { return definition.Properties[name]; }
            catch (ManagementException exception) when (exception.ErrorCode == ManagementStatus.NotFound) { return null; }
        }

        private static bool? ParameterIsDataBuffer(ManagementBaseObject definition, string name)
        {
            PropertyData property = ReadProperty(definition, name);
            if (property == null || property.Type != CimType.Object || property.IsArray) return false;
            // Property.Value is deliberately never read: this is a definition, not a request.
            return WsabiWmiContractMetadataPolicy.NormalizeEmbeddedClass(ReadQualifier(property.Qualifiers, "EmbeddedInstance"));
        }

        private static WsabiWmiMetadataStatus Classify(Exception exception)
        {
            var management = exception as ManagementException;
            if (management != null)
            {
                switch (management.ErrorCode)
                {
                    case ManagementStatus.InvalidClass:
                    case ManagementStatus.NotFound: return WsabiWmiMetadataStatus.ClassNotFound;
                    case ManagementStatus.InvalidNamespace: return WsabiWmiMetadataStatus.NamespaceNotFound;
                    case ManagementStatus.AccessDenied: return WsabiWmiMetadataStatus.AccessDenied;
                    case ManagementStatus.Timedout: return WsabiWmiMetadataStatus.TimedOut;
                    default: return WsabiWmiMetadataStatus.Unavailable;
                }
            }
            if (exception is UnauthorizedAccessException || exception is SecurityException) return WsabiWmiMetadataStatus.AccessDenied;
            if (exception is TimeoutException) return WsabiWmiMetadataStatus.TimedOut;
            var com = exception as COMException;
            if (com != null)
            {
                switch (unchecked((uint)com.ErrorCode))
                {
                    case 0x80070005:
                    case 0x80041003: return WsabiWmiMetadataStatus.AccessDenied;
                    case 0x80041002:
                    case 0x80041010: return WsabiWmiMetadataStatus.ClassNotFound;
                    case 0x8004100E: return WsabiWmiMetadataStatus.NamespaceNotFound;
                    case 0x80043001:
                    case 0x800705B4: return WsabiWmiMetadataStatus.TimedOut;
                }
            }
            return WsabiWmiMetadataStatus.Unavailable;
        }
    }
}
