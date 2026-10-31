using System;
using System.Collections.Generic;

namespace ATIVBatteryGuard.Core.Services
{
    // This allowlist is derived from the user's wsabi.dll static analysis.
    // It authorizes schema inspection only, never method or instance access.
    public static class WmiSchemaPolicy
    {
        private static readonly string[] allowedClasses = { "WmiAcpiVersion", "WmiAcpiMethod", "DataBuffer" };
        public const string LocalNamespace = @"root\WMI";
        public const int MaxProperties = 24;
        public const int MaxMethods = 12;
        public const int MaxParameters = 12;
        public const int MaxIdentifierLength = 96;
        public static string[] AllowedClasses => (string[])allowedClasses.Clone();
        public static bool HardwareWriteAllowed => false;

        public static bool IsAllowedClass(string name)
        {
            return Array.IndexOf(allowedClasses, name) >= 0;
        }

        public static string Identifier(string name)
        {
            if (string.IsNullOrEmpty(name) || name.Length > MaxIdentifierLength) return "InvalidIdentifier";
            for (int i = 0; i < name.Length; i++)
            {
                char c = name[i];
                if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == '_' ||
                    (i > 0 && c >= '0' && c <= '9'))) return "InvalidIdentifier";
            }
            return name;
        }

        public static string TypeName(string name)
        {
            switch (name)
            {
                case "SInt8": case "UInt8": case "SInt16": case "UInt16":
                case "SInt32": case "UInt32": case "SInt64": case "UInt64":
                case "Real32": case "Real64": case "Boolean": case "String":
                case "DateTime": case "Reference": case "Char16": case "Object":
                case "None": return name;
                default: return "UnknownType";
            }
        }

        internal static T[] CopyBounded<T>(IEnumerable<T> values, int maximum, out bool truncated) where T : class
        {
            truncated = false;
            var result = new List<T>();
            if (values == null) return result.ToArray();
            int visited = 0;
            foreach (T value in values)
            {
                if (++visited > maximum)
                {
                    truncated = true;
                    break;
                }
                if (value != null) result.Add(value);
            }
            return result.ToArray();
        }
    }
}
