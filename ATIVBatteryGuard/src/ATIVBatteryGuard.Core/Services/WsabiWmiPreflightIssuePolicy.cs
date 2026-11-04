using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    public static class WsabiWmiPreflightIssuePolicy
    {
        // Consume the error value here; reports retain only this fixed class.
        // Success and unrecognized values must never imply preparation success.
        public static WsabiWmiPreflightIssue FromHResult(int value)
        {
            switch (value)
            {
                case unchecked((int)0x80070005):
                case unchecked((int)0x80041003): return WsabiWmiPreflightIssue.AccessDenied;
                case unchecked((int)0x80043001):
                case unchecked((int)0x800705B4): return WsabiWmiPreflightIssue.TimedOut;
                case unchecked((int)0x80041010): return WsabiWmiPreflightIssue.ClassNotFound;
                case unchecked((int)0x8004100E): return WsabiWmiPreflightIssue.NamespaceNotFound;
                case unchecked((int)0x80041002): return WsabiWmiPreflightIssue.NotFound;
                case unchecked((int)0x80041008): return WsabiWmiPreflightIssue.InvalidParameter;
                case unchecked((int)0x8004100C): return WsabiWmiPreflightIssue.NotSupported;
                case unchecked((int)0x80041004): return WsabiWmiPreflightIssue.ProviderFailure;
                case unchecked((int)0x80041024): return WsabiWmiPreflightIssue.ProviderNotCapable;
                default: return WsabiWmiPreflightIssue.OtherError;
            }
        }
    }
}
