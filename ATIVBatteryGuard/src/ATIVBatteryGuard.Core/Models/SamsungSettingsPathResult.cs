namespace ATIVBatteryGuard.Core.Models
{
    // Paths stay local to the locator. Reports use fixed categories/reason codes only.
    public sealed class SamsungSettingsPathResult
    {
        public bool Accepted { get; }
        public string Path { get; }
        public string Category { get; }
        public string ReasonCode { get; }

        internal SamsungSettingsPathResult(bool accepted, string path, string category, string reasonCode)
        {
            Accepted = accepted;
            Path = accepted ? path : string.Empty;
            Category = category;
            ReasonCode = reasonCode;
        }
    }
}
