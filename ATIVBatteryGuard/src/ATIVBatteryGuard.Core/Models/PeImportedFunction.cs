using System;

namespace ATIVBatteryGuard.Core.Models
{
    public sealed class PeImportedFunction
    {
        public string ModuleName { get; }
        public string FunctionName { get; }
        public int? Ordinal { get; }
        public string DisplayName => ModuleName + "!" + (Ordinal.HasValue ? "#" + Ordinal.Value : FunctionName);

        public PeImportedFunction(string moduleName, string functionName, int? ordinal = null)
        {
            if (!PeModuleInfo.IsSafeName(moduleName, true)) throw new ArgumentException("Invalid import module name.", nameof(moduleName));
            if (ordinal.HasValue)
            {
                if (ordinal.Value < 0 || ordinal.Value > ushort.MaxValue || !string.IsNullOrEmpty(functionName))
                    throw new ArgumentException("Invalid ordinal import.", nameof(ordinal));
            }
            else if (!PeModuleInfo.IsSafeName(functionName, false)) throw new ArgumentException("Invalid import function name.", nameof(functionName));
            ModuleName = moduleName;
            FunctionName = ordinal.HasValue ? string.Empty : functionName;
            Ordinal = ordinal;
        }
    }
}
