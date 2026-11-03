using System;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    public static class WsabiWmiContractMetadataPolicy
    {
        public const string LocalNamespace = @"root\WMI";
        public const string MethodClass = "WmiAcpiMethod";
        public const string BufferClass = "DataBuffer";
        public const string MethodName = "CallSabiFunction";
        public const string PublicCandidateGuid = "C16C47BA-50E3-444A-AF3A-B1C348380001";
        public static bool CanInvokeMethods => false;

        public static WsabiWmiGuidMatch CompareGuid(object value)
        {
            if (value == null) return WsabiWmiGuidMatch.Missing;
            string text = value as string;
            Guid parsed;
            if (text == null || text.Length > 38 || !Guid.TryParse(text, out parsed))
                return WsabiWmiGuidMatch.Invalid;
            return parsed == new Guid(PublicCandidateGuid) ? WsabiWmiGuidMatch.MatchesPublicCandidate : WsabiWmiGuidMatch.Other;
        }

        public static uint? NormalizeMethodId(object value)
        {
            if (value is uint) return (uint)value;
            if (value is int && (int)value >= 0) return (uint)(int)value;
            return null;
        }

        public static bool? NormalizeEmbeddedClass(object value)
        {
            string text = value as string;
            if (text == null || text.Length > 96) return null;
            // WMI class identifiers are case-insensitive. Do not trim or
            // reinterpret paths, namespaces or arbitrary type names.
            return string.Equals(text, BufferClass, StringComparison.OrdinalIgnoreCase);
        }
    }
}
