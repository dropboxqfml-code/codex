using System;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // One entry, one durable reservation, at most one fixed request. The host
    // process supplies independent hard watchdogs; this layer never retries,
    // resets a reservation, selects another instance or changes privileges.
    public sealed class WsabiWmiOneShotExperiment
    {
        private readonly IWsabiWmiOneShotBackend backend;
        private readonly IWsabiWmiOneShotReservation reservation;
        private int entered;

        public WsabiWmiOneShotExperiment(IWsabiWmiOneShotBackend backend,
            IWsabiWmiOneShotReservation reservation)
        {
            this.backend = backend ?? throw new ArgumentNullException(nameof(backend));
            this.reservation = reservation ?? throw new ArgumentNullException(nameof(reservation));
        }

        public async Task<WsabiWmiOneShotReport> RunAsync()
        {
            if (Interlocked.CompareExchange(ref entered, 1, 0) != 0)
                return Report(WsabiWmiOneShotStatus.AlreadyRun, ProcessElevationState.Unknown,
                    WsabiWmiMetadataStatus.NotChecked);
            ProcessElevationState elevation;
            try { elevation = backend.ReadElevation(); }
            catch { elevation = ProcessElevationState.Unknown; }
            if (elevation != ProcessElevationState.Elevated)
                return Report(elevation == ProcessElevationState.NotElevated
                    ? WsabiWmiOneShotStatus.NotElevated : WsabiWmiOneShotStatus.ElevationUnknown,
                    elevation, WsabiWmiMetadataStatus.NotChecked);

            bool requested = false;
            var preflightStatus = WsabiWmiMetadataStatus.Unavailable;
            var preflightStage = WsabiWmiOneShotPreflightStage.Unknown;
            try
            {
                WsabiWmiOneShotPreflight preflight = backend.Prepare();
                if (preflight == null)
                    return Report(WsabiWmiOneShotStatus.PreflightFailed, elevation, preflightStatus, stage: preflightStage);
                preflightStatus = preflight.Status;
                preflightStage = preflight.Stage;
                if (preflightStatus != WsabiWmiMetadataStatus.Complete)
                    return Report(WsabiWmiOneShotStatus.PreflightFailed, elevation, preflightStatus, stage: preflightStage);
                if (preflight.DeviceMatches != true)
                    return Report(WsabiWmiOneShotStatus.DeviceMismatch, elevation, preflightStatus, stage: preflightStage);

                WsabiWmiMethodBinder binder;
                if (!WsabiWmiMethodBinder.TryCreate(preflight.Metadata, out binder) ||
                    binder.ObservedMethodId != WsabiWmiOneShotPolicy.RequiredMethodId)
                    return Report(WsabiWmiOneShotStatus.MetadataMismatch, elevation, preflightStatus, stage: preflightStage);
                if (!preflight.EnumerationComplete || preflight.MethodInstanceCount != 1 ||
                    preflight.SoleInstanceActive != true || !preflight.InputReady)
                    return Report(WsabiWmiOneShotStatus.TargetMismatch, elevation, preflightStatus, stage: preflightStage);

                WsabiWmiMethodRequest request;
                if (!binder.TryPrepareRequest(WsabiWmiOneShotPolicy.CandidateCommand,
                    WsabiWmiOneShotPolicy.CreatePayload(), out request) ||
                    !WsabiWmiOneShotPolicy.IsApprovedRequest(request))
                    return Report(WsabiWmiOneShotStatus.PreflightFailed, elevation, preflightStatus, stage: preflightStage);

                WsabiWmiOneShotReservationStatus claim;
                try { claim = reservation.TryClaim(); }
                catch { claim = WsabiWmiOneShotReservationStatus.Unavailable; }
                if (claim != WsabiWmiOneShotReservationStatus.Claimed)
                    return Report(claim == WsabiWmiOneShotReservationStatus.AlreadyUsed
                        ? WsabiWmiOneShotStatus.ReservationAlreadyUsed : WsabiWmiOneShotStatus.ReservationUnavailable,
                        elevation, preflightStatus, stage: preflightStage);

                var channel = new WsabiWmiBoundFrameChannel(binder, backend);
                requested = true;
                // Do not pretend a cooperative timeout can stop a firmware
                // operation. The separate process host enforces its lifetime.
                WsabiWmiReplyResult reply = await channel.ExchangeAsync(request.Frame, CancellationToken.None)
                    .ConfigureAwait(false);
                return new WsabiWmiOneShotReport(WsabiWmiOneShotStatus.ResponseReceived,
                    elevation, preflightStatus, true, reply, preflightStage);
            }
            catch
            {
                return Report(requested ? WsabiWmiOneShotStatus.TransportFailure : WsabiWmiOneShotStatus.PreflightFailed,
                    elevation, preflightStatus, requested, preflightStage);
            }
        }

        private static WsabiWmiOneShotReport Report(WsabiWmiOneShotStatus status,
            ProcessElevationState elevation, WsabiWmiMetadataStatus preflightStatus, bool requested = false,
            WsabiWmiOneShotPreflightStage stage = WsabiWmiOneShotPreflightStage.Unknown)
            => new WsabiWmiOneShotReport(status, elevation, preflightStatus, requested, preflightStage: stage);
    }
}
