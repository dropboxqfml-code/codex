using System;

namespace ATIVBatteryGuard.Core.Models
{
    public enum WsabiWmiOneShotReservationStatus { Claimed, AlreadyUsed, Unavailable }

    // Only fixed, bounded preflight facts. Device strings, instance paths and
    // provider objects remain private to the separate experiment backend.
    public sealed class WsabiWmiOneShotPreflight
    {
        public WsabiWmiMetadataStatus Status { get; }
        public bool? DeviceMatches { get; }
        public WsabiWmiContractMetadataReport Metadata { get; }
        public bool EnumerationComplete { get; }
        public int MethodInstanceCount { get; }
        public bool? SoleInstanceActive { get; }
        public bool InputReady { get; }

        public WsabiWmiOneShotPreflight(WsabiWmiMetadataStatus status, bool? deviceMatches,
            WsabiWmiContractMetadataReport metadata, bool enumerationComplete,
            int methodInstanceCount, bool? soleInstanceActive, bool inputReady)
        {
            Status = Enum.IsDefined(typeof(WsabiWmiMetadataStatus), status)
                ? status : WsabiWmiMetadataStatus.Unavailable;
            // Two is the bounded multiple-instance observation. Invalid counts
            // cannot masquerade as a completed enumeration of one target.
            if (methodInstanceCount < 0 || methodInstanceCount > 2)
                Status = WsabiWmiMetadataStatus.Unavailable;
            if (Status != WsabiWmiMetadataStatus.Complete)
            {
                Metadata = WsabiWmiContractMetadataReport.Failure(Status);
                return;
            }
            DeviceMatches = deviceMatches;
            Metadata = metadata ?? WsabiWmiContractMetadataReport.Failure(WsabiWmiMetadataStatus.Unavailable);
            EnumerationComplete = enumerationComplete;
            MethodInstanceCount = methodInstanceCount;
            SoleInstanceActive = enumerationComplete && methodInstanceCount == 1 ? soleInstanceActive : null;
            InputReady = inputReady;
        }
    }
}
