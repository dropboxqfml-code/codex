using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterManualProtectionClientSessionTests()
    {
        AddAsync("manual GUI exchange requires matching hello closed result ack and released without accepting process exit", async () =>
        {
            foreach (var operation in new[] { ManualProtectionOperation.ReadState, ManualProtectionOperation.Enable80, ManualProtectionOperation.DisableProtection })
            {
                var context = ManualClientContext(operation); var expected = ManualClientSuccess(operation);
                using (var wire = new ManualClientStream(ManualProtectionWireMessage.Hello(context),
                    ManualProtectionWireMessage.Progress(context, ManualProtectionPhase.Running),
                    ManualProtectionWireMessage.ForResult(context, expected), ManualProtectionWireMessage.Released(context)))
                {
                    var phases = new List<ManualProtectionPhase>(); var client = new ManualProtectionClientSession(context);
                    var result = await client.RunAsync(wire, phases.Add);
                    Check(result.IsSuccess && !client.IsUncertain && client.RequestMayHaveBeenSent, "normal exchange did not complete");
                    Equal(expected.ModeCandidate, result.ModeCandidate); Equal(expected.SdkEntries, result.SdkEntries);
                    var written = await wire.WrittenMessages();
                    Equal(2, written.Count); Equal(ManualProtectionWireKind.Request, written[0].Kind); Equal(ManualProtectionWireKind.Ack, written[1].Kind);
                    Check(written.All(value => context.Matches(value.Context)), "outgoing context changed");
                    Equal(ManualProtectionPhase.Completed, phases.Last());
                }
            }
        });
        AddAsync("manual GUI exchange keeps a live operation pending instead of imposing a transport deadline on hardware", async () =>
        {
            var context = ManualClientContext(ManualProtectionOperation.Enable80);
            using (var wire = new ManualClientStream(ManualProtectionWireMessage.Hello(context),
                ManualProtectionWireMessage.ForResult(context, ManualClientSuccess(context.Operation)),
                ManualProtectionWireMessage.Released(context)))
            {
                wire.BlockAfterHello = true;
                var client = new ManualProtectionClientSession(context);
                var pending = client.RunAsync(wire);
                await wire.RequestWritten.Task.WaitAsync(TimeSpan.FromSeconds(3));
                Check(!pending.IsCompleted && client.RequestMayHaveBeenSent, "live operation was synthesized as completed");
                wire.ReleaseRead.TrySetResult(true);
                Check((await pending).IsSuccess && !client.IsUncertain, "actual completion could not finish the exchange");
            }
        });
        AddAsync("manual GUI exchange refuses foreign hello before request without pretending firmware was entered", async () =>
        {
            var context = ManualClientContext(ManualProtectionOperation.ReadState);
            var foreign = new ManualProtectionContext(new string('b', 32), new string('c', 64), context.Operation);
            using (var wire = new ManualClientStream(ManualProtectionWireMessage.Hello(foreign)))
            {
                var client = new ManualProtectionClientSession(context); var result = await client.RunAsync(wire);
                Equal(ManualProtectionStatus.Rejected, result.Status); Check(result.CleanupComplete && !client.RequestMayHaveBeenSent && !client.IsUncertain, "foreign hello became an admitted request");
                Equal(0, (await wire.WrittenMessages()).Count);
            }
        });
        AddAsync("manual GUI exchange rejects stale result operation or nonce after request and never acknowledges it", async () =>
        {
            var context = ManualClientContext(ManualProtectionOperation.ReadState);
            foreach (var foreign in new[] {
                new ManualProtectionContext(context.JobId, new string('c', 64), context.Operation),
                ManualClientContext(ManualProtectionOperation.DisableProtection) })
            using (var wire = new ManualClientStream(ManualProtectionWireMessage.Hello(context),
                ManualProtectionWireMessage.ForResult(foreign, ManualClientSuccess(foreign.Operation))))
            {
                var client = new ManualProtectionClientSession(context); var result = await client.RunAsync(wire);
                Equal(ManualProtectionStatus.Unknown, result.Status); Check(!result.CleanupComplete && client.IsUncertain && !result.HasKnownMode, "stale reply became new state");
                Equal(1, (await wire.WrittenMessages()).Count);
            }
        });
        AddAsync("manual GUI exchange never substitutes EOF or a progress notice for an actual closed result", async () =>
        {
            var context = ManualClientContext(ManualProtectionOperation.Enable80);
            using (var wire = new ManualClientStream(ManualProtectionWireMessage.Hello(context),
                ManualProtectionWireMessage.Progress(context, ManualProtectionPhase.WaitingForActualCompletion)))
            {
                var client = new ManualProtectionClientSession(context); var result = await client.RunAsync(wire);
                Check(client.IsUncertain && !result.CleanupComplete && !result.HasKnownMode, "transport exit claimed actual termination");
                Equal(1, (await wire.WrittenMessages()).Count);
            }
        });
        AddAsync("manual GUI exchange needs release confirmation even after a valid actual-close result and ack", async () =>
        {
            var context = ManualClientContext(ManualProtectionOperation.DisableProtection);
            using (var wire = new ManualClientStream(ManualProtectionWireMessage.Hello(context),
                ManualProtectionWireMessage.ForResult(context, ManualClientSuccess(context.Operation))))
            {
                var client = new ManualProtectionClientSession(context); var result = await client.RunAsync(wire);
                Equal(ManualProtectionStatus.Unknown, result.Status); Check(client.IsUncertain && !result.CleanupComplete && !result.HasKnownMode, "missing ledger release exposed success");
                Equal(2, (await wire.WrittenMessages()).Count);
            }
        });
        AddAsync("manual GUI exchange rejects a foreign release instead of reusing a previous completed job", async () =>
        {
            var context = ManualClientContext(ManualProtectionOperation.ReadState);
            var foreign = new ManualProtectionContext(new string('d', 32), context.Nonce, context.Operation);
            using (var wire = new ManualClientStream(ManualProtectionWireMessage.Hello(context),
                ManualProtectionWireMessage.ForResult(context, ManualClientSuccess(context.Operation)), ManualProtectionWireMessage.Released(foreign)))
            {
                var client = new ManualProtectionClientSession(context); var result = await client.RunAsync(wire);
                Check(client.IsUncertain && !result.HasKnownMode && !result.CleanupComplete, "foreign release erased the uncertain operation");
            }
        });
        AddAsync("manual GUI exchange preserves a possibly delivered request when its write throws", async () =>
        {
            var context = ManualClientContext(ManualProtectionOperation.Enable80);
            using (var wire = new ManualClientStream(ManualProtectionWireMessage.Hello(context)))
            {
                wire.FailWriteNumber = 1;
                var client = new ManualProtectionClientSession(context); var result = await client.RunAsync(wire);
                Check(client.RequestMayHaveBeenSent && client.IsUncertain && !result.CleanupComplete && !result.HasKnownMode, "failed write was interpreted as no execution");
            }
        });
        AddAsync("manual GUI exchange retains uncertainty if acknowledgment write fails after actual result", async () =>
        {
            var context = ManualClientContext(ManualProtectionOperation.DisableProtection);
            using (var wire = new ManualClientStream(ManualProtectionWireMessage.Hello(context),
                ManualProtectionWireMessage.ForResult(context, ManualClientSuccess(context.Operation)), ManualProtectionWireMessage.Released(context)))
            {
                // Each frame uses a length write and a payload write.
                wire.FailWriteNumber = 3;
                var client = new ManualProtectionClientSession(context); var result = await client.RunAsync(wire);
                Check(client.IsUncertain && !result.HasKnownMode && !result.CleanupComplete, "failed acknowledgment published state");
            }
        });
        AddAsync("manual GUI exchange bounds notices and cannot be replayed even with a fresh transport", async () =>
        {
            var context = ManualClientContext(ManualProtectionOperation.ReadState);
            var messages = new List<ManualProtectionWireMessage> { ManualProtectionWireMessage.Hello(context) };
            messages.AddRange(Enumerable.Range(0, 33).Select(_ => ManualProtectionWireMessage.Progress(context, ManualProtectionPhase.Preparing)));
            var client = new ManualProtectionClientSession(context);
            using (var wire = new ManualClientStream(messages.ToArray()))
            {
                var result = await client.RunAsync(wire); Check(client.IsUncertain && !result.HasKnownMode, "unbounded notices accepted");
            }
            using (var wire = new ManualClientStream())
            {
                Equal(ManualProtectionStatus.Busy, (await client.RunAsync(wire)).Status);
                Equal(0, (await wire.WrittenMessages()).Count);
            }
        });
        AddAsync("manual GUI exchange ignores presentation exceptions and never turns a normal cancel into device state", async () =>
        {
            var context = ManualClientContext(ManualProtectionOperation.Enable80);
            using (var wire = new ManualClientStream(ManualProtectionWireMessage.Hello(context),
                ManualProtectionWireMessage.ForResult(context, ManualProtectionResult.Failure(context.Operation, ManualProtectionStatus.Cancelled, true)),
                ManualProtectionWireMessage.Released(context)))
            {
                var client = new ManualProtectionClientSession(context);
                var result = await client.RunAsync(wire, _ => { throw new InvalidOperationException("PRIVATE-PRESENTATION"); });
                Equal(ManualProtectionStatus.Cancelled, result.Status); Check(!client.IsUncertain && result.CleanupComplete && !result.HasKnownMode, "cancel inferred a mode");
                Check(!result.ToDisplayText().Contains("PRIVATE-PRESENTATION"), "private presentation exception leaked");
            }
        });
    }

    private static ManualProtectionContext ManualClientContext(ManualProtectionOperation operation)
        => new ManualProtectionContext(new string('a', 32), new string('b', 64), operation);
    private static ManualProtectionResult ManualClientSuccess(ManualProtectionOperation operation)
    {
        if (operation == ManualProtectionOperation.ReadState)
            return new ManualProtectionResult(operation, ManualProtectionStatus.StateRead, true, true, 3, 0, 3, 0, 0, 80, 75);
        if (operation == ManualProtectionOperation.Enable80)
            return new ManualProtectionResult(operation, ManualProtectionStatus.ChangedCandidate, true, true, 7, 1, 6, 0, 1, 80, 75);
        return new ManualProtectionResult(operation, ManualProtectionStatus.ChangedCandidate, true, true, 3, 1, 2, 1, 0);
    }
    private sealed class ManualClientStream : Stream
    {
        private readonly MemoryStream incoming = new MemoryStream(), outgoing = new MemoryStream();
        private int writeCount;
        private long helloEnd;
        public bool BlockAfterHello;
        public readonly TaskCompletionSource<bool> RequestWritten = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        public readonly TaskCompletionSource<bool> ReleaseRead = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        public int FailWriteNumber;
        public ManualClientStream(params ManualProtectionWireMessage[] messages)
        {
            foreach (var message in messages)
            {
                byte[] body = ManualProtectionWireProtocol.Encode(message);
                byte[] length = BitConverter.GetBytes(body.Length);
                if (!BitConverter.IsLittleEndian) Array.Reverse(length);
                incoming.Write(length, 0, length.Length); incoming.Write(body, 0, body.Length);
                if (helloEnd == 0) helloEnd = incoming.Length;
            }
            incoming.Position = 0;
        }
        public async Task<List<ManualProtectionWireMessage>> WrittenMessages()
        {
            var result = new List<ManualProtectionWireMessage>();
            using (var copy = new MemoryStream(outgoing.ToArray()))
                while (copy.Position < copy.Length) result.Add(await ManualProtectionWireProtocol.ReadAsync(copy, CancellationToken.None));
            return result;
        }
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => true;
        public override long Length => incoming.Length;
        public override long Position { get => incoming.Position; set => throw new NotSupportedException(); }
        public override int Read(byte[] buffer, int offset, int count) => incoming.Read(buffer, offset, Math.Min(count, 5));
        public override async Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken token)
        {
            if (BlockAfterHello && incoming.Position >= helloEnd) await ReleaseRead.Task;
            return Read(buffer, offset, count);
        }
        public override void Write(byte[] buffer, int offset, int count)
        {
            if (++writeCount == FailWriteNumber) throw new IOException("PRIVATE-PIPE");
            outgoing.Write(buffer, offset, count);
            if (writeCount == 2) RequestWritten.TrySetResult(true);
        }
        public override Task WriteAsync(byte[] buffer, int offset, int count, CancellationToken token)
        { Write(buffer, offset, count); return Task.CompletedTask; }
        public override void Flush() { }
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        protected override void Dispose(bool disposing) { if (disposing) { incoming.Dispose(); outgoing.Dispose(); } base.Dispose(disposing); }
    }
}
