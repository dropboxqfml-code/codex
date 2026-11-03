namespace ATIVBatteryGuard.Core.Models
{
    // Transient boundary data. The caller supplies detached memory, not live
    // provider getters. Output is neither logged nor retained by the channel's
    // decoded result; this object is not a report or an authorization token.
    public sealed class WsabiWmiMethodSnapshot
    {
        public int ApiResult { get; }
        public object Output { get; }
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        public WsabiWmiMethodSnapshot(int apiResult, object output)
        {
            ApiResult = apiResult;
            Output = output;
        }
    }
}
