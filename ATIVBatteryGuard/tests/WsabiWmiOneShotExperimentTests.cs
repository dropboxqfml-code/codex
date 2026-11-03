using System;
using System.Collections.Generic;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiOneShotExperimentTests()
    {
        Add("approved one-shot query requires explicit dependencies and rejects every other request shape", () =>
        {
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiOneShotExperiment(null, new OneShotExperimentReservation()));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiOneShotExperiment(new OneShotExperimentBackend(), null));
            Equal(0x65, (int)WsabiWmiOneShotPolicy.CandidateCommand);
            Equal((uint)1, (uint)WsabiWmiOneShotPolicy.RequiredMethodId);
            Equal(1, WsabiWmiOneShotPolicy.MaximumInvocations);
            byte[] payload = WsabiWmiOneShotPolicy.CreatePayload();
            Equal(16, payload.Length); Equal((byte)0x80, payload[0]);
            for (int index = 1; index < payload.Length; index++) Equal((byte)0, payload[index]);
            payload[0] = 0x81;
            Equal((byte)0x80, WsabiWmiOneShotPolicy.CreatePayload()[0]);
            WsabiWmiMethodRequest request;
            var binder = OneShotExperimentBinder(1);
            Check(binder.TryPrepareRequest(0x65, WsabiWmiOneShotPolicy.CreatePayload(), out request), "candidate fixture failed");
            Check(WsabiWmiOneShotPolicy.IsApprovedRequest(request), "fixed candidate rejected");
            Check(!WsabiWmiOneShotPolicy.IsApprovedRequest(null), "missing request accepted");
            foreach (int command in new[] { 0, 1, 0x64, 0x66, 0xffff })
            {
                Check(binder.TryPrepareRequest(command, WsabiWmiOneShotPolicy.CreatePayload(), out request), "structural fixture failed");
                Check(!WsabiWmiOneShotPolicy.IsApprovedRequest(request), "another firmware command accepted");
            }
            foreach (uint id in new uint[] { 0, 2, uint.MaxValue })
            {
                Check(OneShotExperimentBinder(id).TryPrepareRequest(0x65, WsabiWmiOneShotPolicy.CreatePayload(), out request), "dispatch fixture failed");
                Check(!WsabiWmiOneShotPolicy.IsApprovedRequest(request), "another Windows dispatch accepted");
            }
            for (int offset = 0; offset < 16; offset++)
            {
                byte[] changed = WsabiWmiOneShotPolicy.CreatePayload(); changed[offset] ^= 1;
                Check(binder.TryPrepareRequest(0x65, changed, out request), "payload fixture failed");
                Check(!WsabiWmiOneShotPolicy.IsApprovedRequest(request), "changed candidate input accepted");
            }
            var malformed = new WsabiWmiMethodRequest(1, 0x65, new byte[21]);
            Check(!WsabiWmiOneShotPolicy.IsApprovedRequest(malformed), "invalid complete frame accepted");
        });
        AddAsync("approved one-shot query never prepares or reserves without a confirmed elevated token", async () =>
        {
            foreach (var elevation in new[] { ProcessElevationState.NotElevated, ProcessElevationState.Unknown, (ProcessElevationState)999 })
            {
                var backend = new OneShotExperimentBackend { Elevation = elevation };
                var reservation = new OneShotExperimentReservation();
                var result = await new WsabiWmiOneShotExperiment(backend, reservation).RunAsync();
                Equal(elevation == ProcessElevationState.NotElevated ? WsabiWmiOneShotStatus.NotElevated :
                    WsabiWmiOneShotStatus.ElevationUnknown, result.Status);
                OneShotExperimentAssertNoCall(result, backend, reservation);
                Equal(0, backend.Prepares);
            }
            var throwing = new OneShotExperimentBackend { ElevationReader = () => { throw new Exception(@"C:\Users\PrivateName"); } };
            var denied = new OneShotExperimentReservation();
            var failure = await new WsabiWmiOneShotExperiment(throwing, denied).RunAsync();
            Equal(WsabiWmiOneShotStatus.ElevationUnknown, failure.Status);
            OneShotExperimentAssertNoCall(failure, throwing, denied);
            Equal(0, throwing.Prepares);
            Check(!failure.ToDisplayText().Contains("PrivateName"), "token exception detail leaked");
        });
        AddAsync("approved one-shot query discards failed preflight facts and never reserves on incomplete preparation", async () =>
        {
            foreach (WsabiWmiMetadataStatus status in Enum.GetValues(typeof(WsabiWmiMetadataStatus)))
            {
                if (status == WsabiWmiMetadataStatus.Complete) continue;
                var preflight = new WsabiWmiOneShotPreflight(status, true, OneShotExperimentMetadata(), true, 1, true, true);
                Equal<bool?>(null, preflight.DeviceMatches);
                Check(!preflight.EnumerationComplete && !preflight.InputReady, "failure retained ready facts");
                Equal(0, preflight.MethodInstanceCount);
                Equal<bool?>(null, preflight.SoleInstanceActive);
                Check(preflight.Metadata.BindingStatus != WsabiWmiContractBindingStatus.MetadataShapeMatched,
                    "failed preparation retained a binding");
                var backend = new OneShotExperimentBackend { Preparer = () => preflight };
                var reservation = new OneShotExperimentReservation();
                var report = await new WsabiWmiOneShotExperiment(backend, reservation).RunAsync();
                OneShotExperimentAssertNoCall(report, backend, reservation);
            }
            foreach (Func<WsabiWmiOneShotPreflight> prepare in new Func<WsabiWmiOneShotPreflight>[] {
                () => null, () => { throw new InvalidOperationException("private preflight error"); } })
            {
                var backend = new OneShotExperimentBackend { Preparer = prepare };
                var reservation = new OneShotExperimentReservation();
                var report = await new WsabiWmiOneShotExperiment(backend, reservation).RunAsync();
                Equal(WsabiWmiOneShotStatus.PreflightFailed, report.Status);
                OneShotExperimentAssertNoCall(report, backend, reservation);
                Check(!report.ToDisplayText().Contains("private preflight error"), "preflight error leaked");
            }
            foreach (var property in typeof(WsabiWmiOneShotPreflight).GetProperties())
                Check(!property.CanWrite, "preflight publicly mutable");
        });
        AddAsync("approved one-shot query refuses unknown or different device matches", async () =>
        {
            foreach (bool? device in new bool?[] { null, false })
            {
                var backend = new OneShotExperimentBackend { Preparer = () => OneShotExperimentPreflight(deviceMatches: device) };
                var reservation = new OneShotExperimentReservation();
                var report = await new WsabiWmiOneShotExperiment(backend, reservation).RunAsync();
                OneShotExperimentAssertNoCall(report, backend, reservation);
                Check(report.Status != WsabiWmiOneShotStatus.ResponseReceived, "device mismatch became an observation");
            }
        });
        AddAsync("approved one-shot query requires detailed matching schema and the observed dispatch one", async () =>
        {
            var unknownParameters = new WsabiWmiContractMetadataReport(new WsabiWmiContractMethodMetadata(
                WsabiWmiMetadataStatus.Partial, WsabiWmiGuidMatch.MatchesPublicCandidate, 1, null, null, true),
                new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, true));
            var legacy = new WsabiWmiContractMetadataReport(new WsabiWmiContractMethodMetadata(
                WsabiWmiMetadataStatus.Complete, WsabiWmiGuidMatch.MatchesPublicCandidate, 1, true, true, true),
                new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, true));
            foreach (var metadata in new[] { null, new WsabiWmiContractMetadataReport(), unknownParameters, legacy,
                OneShotExperimentMetadata(id: 0), OneShotExperimentMetadata(id: 2),
                OneShotExperimentMetadata(guid: WsabiWmiGuidMatch.Other), OneShotExperimentMetadata(found: false),
                OneShotExperimentMetadata(bytes: false) })
            {
                var backend = new OneShotExperimentBackend { Preparer = () => OneShotExperimentPreflight(metadata: metadata, useDefaultMetadata: false) };
                var reservation = new OneShotExperimentReservation();
                var report = await new WsabiWmiOneShotExperiment(backend, reservation).RunAsync();
                Equal(WsabiWmiOneShotStatus.MetadataMismatch, report.Status);
                OneShotExperimentAssertNoCall(report, backend, reservation);
            }
        });
        AddAsync("approved one-shot query requires complete enumeration with exactly one active prepared target", async () =>
        {
            foreach (var preflight in new[] {
                OneShotExperimentPreflight(enumerationComplete: false),
                OneShotExperimentPreflight(instanceCount: 0), OneShotExperimentPreflight(instanceCount: 2),
                OneShotExperimentPreflight(active: false), OneShotExperimentPreflight(active: null),
                OneShotExperimentPreflight(inputReady: false), OneShotExperimentPreflight(instanceCount: -1),
                OneShotExperimentPreflight(instanceCount: 3) })
            {
                var backend = new OneShotExperimentBackend { Preparer = () => preflight };
                var reservation = new OneShotExperimentReservation();
                var report = await new WsabiWmiOneShotExperiment(backend, reservation).RunAsync();
                OneShotExperimentAssertNoCall(report, backend, reservation);
                Check(report.Status != WsabiWmiOneShotStatus.ResponseReceived, "incomplete target became a query result");
            }
        });
        AddAsync("approved one-shot query never dispatches when the durable reservation is refused or unavailable", async () =>
        {
            foreach (var status in new[] { WsabiWmiOneShotReservationStatus.AlreadyUsed,
                WsabiWmiOneShotReservationStatus.Unavailable, (WsabiWmiOneShotReservationStatus)999 })
            {
                var backend = new OneShotExperimentBackend();
                var reservation = new OneShotExperimentReservation { Status = status };
                var report = await new WsabiWmiOneShotExperiment(backend, reservation).RunAsync();
                Equal(status == WsabiWmiOneShotReservationStatus.AlreadyUsed ? WsabiWmiOneShotStatus.ReservationAlreadyUsed :
                    WsabiWmiOneShotStatus.ReservationUnavailable, report.Status);
                Check(!report.InvocationRequested, "refused reservation marked dispatched");
                Equal(1, reservation.Claims); Equal(0, backend.Calls);
                Equal(WsabiWmiCandidateMarker.NotObserved, report.Marker);
            }
            var throwing = new OneShotExperimentReservation { Handler = () => { throw new Exception(@"C:\Users\PrivateName\marker"); } };
            var failedBackend = new OneShotExperimentBackend();
            var failure = await new WsabiWmiOneShotExperiment(failedBackend, throwing).RunAsync();
            Equal(WsabiWmiOneShotStatus.ReservationUnavailable, failure.Status);
            Equal(1, throwing.Claims); Equal(0, failedBackend.Calls);
            Check(!failure.InvocationRequested && !failure.ToDisplayText().Contains("PrivateName"), "reservation error leaked or dispatched");
        });
        AddAsync("approved one-shot query reserves before its one fixed request and reports only a candidate marker", async () =>
        {
            var order = new List<string>();
            var backend = new OneShotExperimentBackend { Order = order, Handler = (request, token) => {
                Check(!token.CanBeCanceled, "unexpected soft timeout token reached the single query");
                Check(WsabiWmiOneShotPolicy.IsApprovedRequest(request), "unapproved request reached backend");
                byte[] expected = { 0x43, 0x58, 0x65, 0, 0, 0x80, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0 };
                byte[] actual = request.Frame;
                Equal(expected.Length, actual.Length);
                for (int index = 0; index < expected.Length; index++) Equal(expected[index], actual[index]);
                Equal((uint)1, request.ObservedMethodId); Equal((ushort)0x65, request.FirmwareCommand);
                return Task.FromResult(OneShotExperimentSnapshot(1));
            } };
            var reservation = new OneShotExperimentReservation { Order = order };
            var report = await new WsabiWmiOneShotExperiment(backend, reservation).RunAsync();
            Equal("Elevation,Prepare,Claim,Invoke", string.Join(",", order));
            Equal(1, backend.Calls); Equal(1, reservation.Claims);
            Equal(WsabiWmiOneShotStatus.ResponseReceived, report.Status);
            Equal(ProcessElevationState.Elevated, report.Elevation);
            Check(report.InvocationRequested, "reserved request not recorded");
            Equal<WsabiWmiReplyStatus?>(WsabiWmiReplyStatus.ValidFrame, report.ReplyStatus);
            Equal<WsabiWmiMethodReplyStatus?>(WsabiWmiMethodReplyStatus.FrameChecked, report.MethodReplyStatus);
            Equal(WsabiWmiCandidateMarker.One, report.Marker);
            OneShotExperimentAssertNoHardwareMeaning(report);
        });
        AddAsync("approved one-shot query atomically rejects concurrent and later reentry without another reservation", async () =>
        {
            var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var completion = new TaskCompletionSource<WsabiWmiMethodSnapshot>(TaskCreationOptions.RunContinuationsAsynchronously);
            var backend = new OneShotExperimentBackend { Handler = (request, token) => { entered.TrySetResult(true); return completion.Task; } };
            var reservation = new OneShotExperimentReservation();
            var experiment = new WsabiWmiOneShotExperiment(backend, reservation);
            var first = experiment.RunAsync();
            Check(await Task.WhenAny(entered.Task, Task.Delay(5000)) == entered.Task, "fixture did not enter transport");
            var second = await experiment.RunAsync();
            Equal(WsabiWmiOneShotStatus.AlreadyRun, second.Status);
            Check(!second.InvocationRequested, "reentry attempted a call");
            Equal(1, backend.Calls); Equal(1, reservation.Claims);
            completion.SetResult(OneShotExperimentSnapshot(0));
            var primary = await first;
            Equal(WsabiWmiOneShotStatus.ResponseReceived, primary.Status);
            Equal(WsabiWmiCandidateMarker.Zero, primary.Marker);
            var third = await experiment.RunAsync();
            Equal(WsabiWmiOneShotStatus.AlreadyRun, third.Status);
            Equal(1, backend.ElevationReads); Equal(1, backend.Prepares);
            Equal(1, backend.Calls); Equal(1, reservation.Claims);
        });
        AddAsync("approved one-shot query consumes a dispatch attempt on transport faults without retry or raw errors", async () =>
        {
            foreach (Func<WsabiWmiMethodRequest, CancellationToken, Task<WsabiWmiMethodSnapshot>> handler in
                new Func<WsabiWmiMethodRequest, CancellationToken, Task<WsabiWmiMethodSnapshot>>[] {
                    (request, token) => { throw new Exception(@"C:\Users\PrivateName\provider"); },
                    (request, token) => Task.FromException<WsabiWmiMethodSnapshot>(new InvalidOperationException("private backend")),
                    (request, token) => null,
                    (request, token) => Task.FromResult<WsabiWmiMethodSnapshot>(null),
                    (request, token) => Task.FromCanceled<WsabiWmiMethodSnapshot>(new CancellationToken(true)) })
            {
                var backend = new OneShotExperimentBackend { Handler = handler };
                var reservation = new OneShotExperimentReservation();
                var experiment = new WsabiWmiOneShotExperiment(backend, reservation);
                var report = await experiment.RunAsync();
                Equal(WsabiWmiOneShotStatus.TransportFailure, report.Status);
                Check(report.InvocationRequested, "transport request not conservatively recorded");
                Equal(WsabiWmiCandidateMarker.NotObserved, report.Marker);
                Equal(1, backend.Calls); Equal(1, reservation.Claims);
                Equal(WsabiWmiOneShotStatus.AlreadyRun, (await experiment.RunAsync()).Status);
                Equal(1, backend.Calls); Equal(1, reservation.Claims);
                string text = report.ToDisplayText();
                Check(!text.Contains("PrivateName") && !text.Contains("private backend"), "raw provider error leaked");
                OneShotExperimentAssertNoHardwareMeaning(report);
            }
        });
        AddAsync("approved one-shot query suppresses candidate markers after every API envelope or byte validation failure", async () =>
        {
            byte[] wrongLength = new byte[20]; wrongLength[4] = 0xaa;
            var snapshots = new[] {
                new WsabiWmiMethodSnapshot(1, OneShotExperimentOutput(OneShotExperimentReply(1))),
                new WsabiWmiMethodSnapshot(0, null),
                new WsabiWmiMethodSnapshot(0, new Dictionary<string, object>()),
                new WsabiWmiMethodSnapshot(0, OneShotExperimentOutput("private byte value")),
                new WsabiWmiMethodSnapshot(0, OneShotExperimentOutput(wrongLength)),
                new WsabiWmiMethodSnapshot(0, OneShotExperimentOutput(new byte[21])) };
            WsabiWmiReplyStatus[] expected = { WsabiWmiReplyStatus.ApiNotSuccessful, WsabiWmiReplyStatus.InvalidEnvelope,
                WsabiWmiReplyStatus.InvalidEnvelope, WsabiWmiReplyStatus.InvalidType, WsabiWmiReplyStatus.UnsupportedLength,
                WsabiWmiReplyStatus.InvalidAcknowledgement };
            for (int index = 0; index < snapshots.Length; index++)
            {
                var snapshot = snapshots[index];
                var backend = new OneShotExperimentBackend { Handler = (request, token) => Task.FromResult(snapshot) };
                var reservation = new OneShotExperimentReservation();
                var report = await new WsabiWmiOneShotExperiment(backend, reservation).RunAsync();
                Equal(WsabiWmiOneShotStatus.ResponseReceived, report.Status);
                Equal<WsabiWmiReplyStatus?>(expected[index], report.ReplyStatus);
                Equal(WsabiWmiCandidateMarker.NotObserved, report.Marker);
                Check(report.InvocationRequested, "response lost prior invocation request");
                Equal(1, backend.Calls); Equal(1, reservation.Claims);
                Check(!report.ToDisplayText().Contains("private byte value"), "raw invalid bytes leaked");
                OneShotExperimentAssertNoHardwareMeaning(report);
            }
        });
        AddAsync("approved one-shot query never treats opaque zero one FF or other markers as battery protection", async () =>
        {
            byte[] values = { 0, 1, 0xff, 0x34 };
            WsabiWmiCandidateMarker[] expected = { WsabiWmiCandidateMarker.Zero, WsabiWmiCandidateMarker.One,
                WsabiWmiCandidateMarker.FF, WsabiWmiCandidateMarker.Other };
            for (int index = 0; index < values.Length; index++)
            {
                byte marker = values[index];
                var backend = new OneShotExperimentBackend { Handler = (request, token) => Task.FromResult(OneShotExperimentSnapshot(marker)) };
                var report = await new WsabiWmiOneShotExperiment(backend, new OneShotExperimentReservation()).RunAsync();
                Equal(expected[index], report.Marker);
                Equal<WsabiWmiReplyStatus?>(WsabiWmiReplyStatus.ValidFrame, report.ReplyStatus);
                OneShotExperimentAssertNoHardwareMeaning(report);
                string text = report.ToDisplayText();
                Check(!text.Contains("PrivateName") && !text.Contains("PrivatePath"), "unrelated output retained");
            }
            foreach (var property in typeof(WsabiWmiOneShotReport).GetProperties())
                Check(!property.CanWrite && property.PropertyType != typeof(byte[]) && property.PropertyType != typeof(object),
                    "report exposes mutable or raw response state");
            foreach (var field in typeof(WsabiWmiOneShotReport).GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                Check(field.FieldType != typeof(string) && field.FieldType != typeof(object) && field.FieldType != typeof(byte[]),
                    "report retains raw data or provider text");
        });
    }

    private static WsabiWmiOneShotPreflight OneShotExperimentPreflight(bool? deviceMatches = true,
        WsabiWmiContractMetadataReport metadata = null, bool enumerationComplete = true,
        int instanceCount = 1, bool? active = true, bool inputReady = true, bool useDefaultMetadata = true)
        => new WsabiWmiOneShotPreflight(WsabiWmiMetadataStatus.Complete, deviceMatches,
            useDefaultMetadata ? metadata ?? OneShotExperimentMetadata() : metadata,
            enumerationComplete, instanceCount, active, inputReady);

    private static WsabiWmiContractMetadataReport OneShotExperimentMetadata(WsabiWmiGuidMatch guid = WsabiWmiGuidMatch.MatchesPublicCandidate,
        uint? id = 1, bool? found = true, bool? bytes = true)
    {
        var parameter = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, null, "object:DataBuffer");
        return new WsabiWmiContractMetadataReport(WsabiWmiContractMethodMetadata.FromParameters(
            WsabiWmiMetadataStatus.Complete, guid, id, found, parameter, parameter),
            new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, bytes));
    }

    private static WsabiWmiMethodBinder OneShotExperimentBinder(uint id)
    {
        WsabiWmiMethodBinder binder;
        Check(WsabiWmiMethodBinder.TryCreate(OneShotExperimentMetadata(id: id), out binder), "binder fixture failed");
        return binder;
    }

    private static byte[] OneShotExperimentReply(byte marker)
    {
        var bytes = new byte[21]; bytes[4] = 0xaa;
        for (int index = 5; index < bytes.Length; index++) bytes[index] = marker;
        return bytes;
    }

    private static Dictionary<string, object> OneShotExperimentOutput(object bytes)
        => new Dictionary<string, object> {
            { "outData", new Dictionary<string, object> { { "Bytes", bytes } } },
            { "PrivatePath", @"C:\Users\PrivateName" }, { "ReturnValue", 99 } };

    private static WsabiWmiMethodSnapshot OneShotExperimentSnapshot(byte marker)
        => new WsabiWmiMethodSnapshot(0, OneShotExperimentOutput(OneShotExperimentReply(marker)));

    private static void OneShotExperimentAssertNoCall(WsabiWmiOneShotReport report,
        OneShotExperimentBackend backend, OneShotExperimentReservation reservation)
    {
        Check(!report.InvocationRequested, "a failed gate requested an invocation");
        Equal(0, backend.Calls); Equal(0, reservation.Claims);
        Equal(WsabiWmiCandidateMarker.NotObserved, report.Marker);
        Equal<WsabiWmiReplyStatus?>(null, report.ReplyStatus);
        Equal<WsabiWmiMethodReplyStatus?>(null, report.MethodReplyStatus);
        OneShotExperimentAssertNoHardwareMeaning(report);
    }

    private static void OneShotExperimentAssertNoHardwareMeaning(WsabiWmiOneShotReport report)
        => Check(!report.CanInvokeMethods && !report.CanReadHardware && !report.CanWriteHardware &&
            !report.IsHardwareObservation, "experiment result enabled control or a verified hardware observation");

    private sealed class OneShotExperimentBackend : IWsabiWmiOneShotBackend
    {
        internal ProcessElevationState Elevation = ProcessElevationState.Elevated;
        internal Func<ProcessElevationState> ElevationReader;
        internal Func<WsabiWmiOneShotPreflight> Preparer;
        internal Func<WsabiWmiMethodRequest, CancellationToken, Task<WsabiWmiMethodSnapshot>> Handler;
        internal List<string> Order;
        internal int ElevationReads, Prepares, Calls;
        public ProcessElevationState ReadElevation()
        {
            Interlocked.Increment(ref ElevationReads); if (Order != null) Order.Add("Elevation");
            return ElevationReader == null ? Elevation : ElevationReader();
        }
        public WsabiWmiOneShotPreflight Prepare()
        {
            Interlocked.Increment(ref Prepares); if (Order != null) Order.Add("Prepare");
            return Preparer == null ? OneShotExperimentPreflight() : Preparer();
        }
        public Task<WsabiWmiMethodSnapshot> ExchangeAsync(WsabiWmiMethodRequest request, CancellationToken token)
        {
            Interlocked.Increment(ref Calls); if (Order != null) Order.Add("Invoke");
            return Handler == null ? Task.FromResult(OneShotExperimentSnapshot(0)) : Handler(request, token);
        }
    }

    private sealed class OneShotExperimentReservation : IWsabiWmiOneShotReservation
    {
        internal WsabiWmiOneShotReservationStatus Status = WsabiWmiOneShotReservationStatus.Claimed;
        internal Func<WsabiWmiOneShotReservationStatus> Handler;
        internal List<string> Order;
        internal int Claims;
        public WsabiWmiOneShotReservationStatus TryClaim()
        {
            Interlocked.Increment(ref Claims); if (Order != null) Order.Add("Claim");
            return Handler == null ? Status : Handler();
        }
    }
}
