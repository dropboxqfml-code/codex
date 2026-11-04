namespace ATIVBatteryGuard.Core.Models
{
    // Fixed preparation locations only. A stage identifies the last attempted
    // step; it is neither a provider error string nor a firmware observation.
    public enum WsabiWmiOneShotPreflightStage
    {
        Unknown, DeviceScope, ModelRead, BiosRead, ContractMetadata, MethodScope,
        MethodEnumeration, TargetRead, InputParameters, BufferInstance, Ready
    }
}
