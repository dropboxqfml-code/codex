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

        public static WsabiWmiParameterMetadata InspectParameter(bool exists, bool isScalarObject,
            object embeddedInstance, object cimType)
        {
            if (!exists) return new WsabiWmiParameterMetadata(WsabiWmiParameterShape.Missing,
                WsabiWmiQualifierMatch.Missing, WsabiWmiQualifierMatch.Missing);
            if (!isScalarObject) return new WsabiWmiParameterMetadata(WsabiWmiParameterShape.Other,
                WsabiWmiQualifierMatch.Missing, WsabiWmiQualifierMatch.Missing);
            return new WsabiWmiParameterMetadata(WsabiWmiParameterShape.ScalarObject,
                NormalizeEmbeddedInstance(embeddedInstance), NormalizeCimType(cimType));
        }

        public static WsabiWmiQualifierMatch NormalizeEmbeddedInstance(object value)
        {
            if (value == null) return WsabiWmiQualifierMatch.Missing;
            string text = value as string;
            if (!IsIdentifier(text)) return WsabiWmiQualifierMatch.Invalid;
            return string.Equals(text, BufferClass, StringComparison.OrdinalIgnoreCase)
                ? WsabiWmiQualifierMatch.MatchesDataBuffer : WsabiWmiQualifierMatch.Other;
        }

        public static WsabiWmiQualifierMatch NormalizeCimType(object value)
        {
            if (value == null) return WsabiWmiQualifierMatch.Missing;
            string text = value as string;
            if (text == null || text.Length == 0 || text.Length > 96) return WsabiWmiQualifierMatch.Invalid;
            // Standard CIMTYPE represents an embedded object as object:Class.
            // A bare object says nothing about the embedded class. Never trim,
            // coerce arrays, or interpret namespaces/paths as class names.
            if (string.Equals(text, "object", StringComparison.OrdinalIgnoreCase))
                return WsabiWmiQualifierMatch.UnspecifiedObject;
            const string prefix = "object:";
            if (text.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                string className = text.Substring(prefix.Length);
                if (!IsIdentifier(className)) return WsabiWmiQualifierMatch.Invalid;
                return string.Equals(className, BufferClass, StringComparison.OrdinalIgnoreCase)
                    ? WsabiWmiQualifierMatch.MatchesDataBuffer : WsabiWmiQualifierMatch.Other;
            }
            // Recognize fixed CIM primitive names only. A syntactically valid
            // but unknown token is not proof of a different CIM definition.
            switch (text.ToLowerInvariant())
            {
                case "boolean": case "char16": case "datetime": case "real32": case "real64":
                case "sint8": case "sint16": case "sint32": case "sint64": case "string":
                case "uint8": case "uint16": case "uint32": case "uint64": case "reference":
                    return WsabiWmiQualifierMatch.Other;
                default: return WsabiWmiQualifierMatch.Invalid;
            }
        }

        private static bool IsIdentifier(string text)
        {
            if (text == null || text.Length == 0 || text.Length > 96 || !IsIdentifierStart(text[0])) return false;
            for (int index = 1; index < text.Length; index++)
                if (!IsIdentifierStart(text[index]) && (text[index] < '0' || text[index] > '9')) return false;
            return true;
        }

        private static bool IsIdentifierStart(char value)
            => value == '_' || value >= 'A' && value <= 'Z' || value >= 'a' && value <= 'z';
    }
}
