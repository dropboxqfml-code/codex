using System;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // This instance allowlist is separate from schema discovery: no DataBuffer or methods.
    public static class SamsungWmiInstancePolicy
    {
        public const string LocalNamespace = @"root\WMI";
        private static readonly string[] allowedClasses = { "WmiAcpiVersion", "WmiAcpiMethod" };
        public static string[] AllowedClasses => (string[])allowedClasses.Clone();
        public static bool HardwareWriteAllowed => false;
        public static bool CanInvokeMethods => false;
        public static bool IsAllowedClass(string value) => Array.IndexOf(allowedClasses, value) >= 0;

        public static string GetClassName(SamsungWmiClass kind)
        {
            switch (kind)
            {
                case SamsungWmiClass.Version: return "WmiAcpiVersion";
                case SamsungWmiClass.Method: return "WmiAcpiMethod";
                default: throw new ArgumentOutOfRangeException(nameof(kind));
            }
        }

        public static string GetQuery(SamsungWmiClass kind)
        {
            switch (kind)
            {
                case SamsungWmiClass.Version: return "SELECT Active,version FROM WmiAcpiVersion";
                case SamsungWmiClass.Method: return "SELECT Active FROM WmiAcpiMethod";
                default: throw new ArgumentOutOfRangeException(nameof(kind));
            }
        }

        public static bool? NormalizeActive(object value) => value is bool ? (bool?)value : null;
        public static uint? NormalizeVersion(object value) => value is uint ? (uint?)value : null;
    }
}
