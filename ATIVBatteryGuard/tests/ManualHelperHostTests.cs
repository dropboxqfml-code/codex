using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.ManualProtectionHelper;

internal static partial class Program
{
    private static void RegisterManualHelperHostTests()
    {
        Add("manual helper admission accepts only fixed enum and bounded local correlation tokens", () =>
        {
            foreach (ManualProtectionOperation operation in Enum.GetValues(typeof(ManualProtectionOperation)))
            {
                var context = ManualLeaseContext(); ManualProtectionContext parsed;
                Check(ManualHelperAdmission.TryParse(new[] { "--manual-v1", context.JobId, operation.ToString(), context.Nonce }, out parsed), "fixed operation rejected");
                Equal(operation, parsed.Operation); Equal(context.JobId, parsed.JobId); Equal(context.Nonce, parsed.Nonce);
            }
            ManualProtectionContext rejected;
            foreach (string[] args in new[] {
                null, new string[0], new[] { "--manual-v1" },
                new[] { "--worker", new string('a',32), "ReadState", new string('b',64) },
                new[] { "--manual-v1", new string('a',32), "0", new string('b',64) },
                new[] { "--manual-v1", new string('a',32), "Enable80", new string('b',64), "extra" },
                new[] { "--manual-v1", "../path", "Enable80", new string('b',64) },
                new[] { "--manual-v1", new string('A',32), "ReadState", new string('b',64) },
                new[] { "--manual-v1", new string('a',32), "readstate", new string('b',64) },
                new[] { "--manual-v1", new string('a',32), "DisableProtection", new string('b',63) } })
                Check(!ManualHelperAdmission.TryParse(args, out rejected) && rejected == null, "arbitrary helper input admitted");
        });

        Add("manual helper confirmation describes the chosen bounds and no automatic restore", () =>
        {
            string read = ManualHelperAdmission.Confirmation(ManualProtectionOperation.ReadState);
            string enable = ManualHelperAdmission.Confirmation(ManualProtectionOperation.Enable80);
            string disable = ManualHelperAdmission.Confirmation(ManualProtectionOperation.DisableProtection);
            Check(read.Contains("최대3회") && read.Contains("설정은 변경하지 않습니다"), "read-only operation impact missing");
            Check(enable.Contains("최대7회") && enable.Contains("상한80·하한75") && enable.Contains("복원하지 않습니다"), "enable impact missing");
            Check(disable.Contains("최대3회") && disable.Contains("충전이 재개될 수") && disable.Contains("100% 충전을 보장하지"), "disable impact missing");
            Check(new[] { read, enable, disable }.All(value => value.Contains("강제 종료하지") && value.Contains("profile")), "actual lifetime or target explanation missing");
        });

        AddAsync("manual helper notice never substitutes for actual preparation return", async () =>
        {
            var actual = new TaskCompletionSource<int>(TaskCreationOptions.RunContinuationsAsynchronously);
            int notices = 0;
            var run = ManualHelperLifetime.AwaitWithNoticeAsync(actual.Task, Task.CompletedTask, () => { notices++; throw new IOException("PRIVATE-NOTICE"); });
            await Task.Yield(); Equal(1, notices); Check(!run.IsCompleted, "notice ended the actual preparation");
            actual.SetResult(7); Equal(7, await run);
        });

        AddAsync("manual helper cleanup awaits its actual task and rejects failed unknown faulted cancelled and null", async () =>
        {
            var actual = new TaskCompletionSource<WsabiWmiProtectionCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
            var pending = ManualHelperLifetime.JoinActualCloseAsync(() => actual.Task);
            Check(!pending.IsCompleted, "pending cleanup became complete");
            actual.SetResult(WsabiWmiProtectionCleanupStatus.Complete); Check(await pending, "actual complete rejected");
            foreach (var status in new[] { WsabiWmiProtectionCleanupStatus.Failed, WsabiWmiProtectionCleanupStatus.Unknown })
                Check(!await ManualHelperLifetime.JoinActualCloseAsync(() => Task.FromResult(status)), "uncertain cleanup became complete");
            Check(!await ManualHelperLifetime.JoinActualCloseAsync(() => null), "null cleanup accepted");
            Check(!await ManualHelperLifetime.JoinActualCloseAsync(() => Task.FromException<WsabiWmiProtectionCleanupStatus>(new IOException("PRIVATE"))), "fault cleanup accepted");
            Check(!await ManualHelperLifetime.JoinActualCloseAsync(() => Task.FromCanceled<WsabiWmiProtectionCleanupStatus>(new CancellationToken(true))), "cancelled cleanup accepted");
        });

        Add("manual helper entered cancellation becomes unknown after known actual close without hiding counters", () =>
        {
            var untouched = ManualHelperResultFactory.FromCompleted(ManualProtectionOperation.Enable80, ManualProtectionStatus.Cancelled, 0, 0, 0, null, null, null, null);
            Equal(ManualProtectionStatus.Cancelled, untouched.Status); Check(untouched.CleanupComplete && !untouched.ProfileValidated, "no-entry cancellation changed meaning");
            foreach (var status in new[] { ManualProtectionStatus.Cancelled, ManualProtectionStatus.Busy, ManualProtectionStatus.PreflightFailed })
            {
                var entered = ManualHelperResultFactory.FromCompleted(ManualProtectionOperation.Enable80, status, 4, 1, 3, 0, 1, 80, 75);
                Equal(ManualProtectionStatus.Unknown, entered.Status); Equal(4, entered.SdkEntries); Equal(1, entered.SetterEntries); Equal(3, entered.ReadCandidates);
                Equal((int?)0, entered.PreModeCandidate); Check(entered.CleanupComplete && entered.ProfileValidated && !entered.HasKnownMode, "entered stop became untouched or a current snapshot");
            }
        });

        Add("manual helper completed result preserves all three success contracts and refuses invalid counters", () =>
        {
            var read = ManualHelperResultFactory.FromCompleted(ManualProtectionOperation.ReadState, ManualProtectionStatus.StateRead, 3, 0, 3, 1, 1, 80, 75);
            var enabled = ManualHelperResultFactory.FromCompleted(ManualProtectionOperation.Enable80, ManualProtectionStatus.ChangedCandidate, 7, 1, 6, 0, 1, 80, 75);
            var disabled = ManualHelperResultFactory.FromCompleted(ManualProtectionOperation.DisableProtection, ManualProtectionStatus.ChangedCandidate, 3, 1, 2, 1, 0, null, null);
            Check(read.IsSuccess && enabled.IsSuccess && disabled.IsSuccess, "complete fixed result rejected");
            BatteryThrows<ArgumentException>(() => ManualHelperResultFactory.FromCompleted(ManualProtectionOperation.Enable80, ManualProtectionStatus.ChangedCandidate, 7, 1, 6, 0, 1, 81, 75));
            BatteryThrows<ArgumentException>(() => ManualHelperResultFactory.FromCompleted(ManualProtectionOperation.ReadState, ManualProtectionStatus.Unknown, 4, 0, 0, null, null, null, null));
        });

        AddAsync("manual helper refuses premature acknowledgement and signals admission stop without completing actual work", async () =>
        {
            var context = ManualLeaseContext(); var stream = new ManualHelperDuplexStream();
            var channel = new ManualHelperPipe(stream, context);
            var actual = new TaskCompletionSource<WsabiWmiProtectionCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
            var joined = ManualHelperLifetime.JoinActualCloseAsync(() => actual.Task);
            channel.StartAcknowledgmentMonitor();
            stream.Receive(ManualProtectionWireMessage.Ack(context));
            Check(!await channel.WaitForAcknowledgmentAsync(), "premature ACK accepted");
            Check(channel.HasFailed && channel.DisconnectedToken.IsCancellationRequested, "lost GUI did not request admission stop");
            Check(!joined.IsCompleted, "transport failure fabricated actual cleanup");
            actual.SetResult(WsabiWmiProtectionCleanupStatus.Complete); Check(await joined, "actual cleanup could not finish after lost transport");
        });

        AddAsync("manual helper EOF and wrong-context acknowledgements stop future admission without a terminal result", async () =>
        {
            for (int variant = 0; variant < 3; variant++)
            {
                var context = ManualLeaseContext(); var stream = new ManualHelperDuplexStream(); var channel = new ManualHelperPipe(stream, context);
                channel.StartAcknowledgmentMonitor(); channel.BeginTerminalResult();
                if (variant == 0) stream.End();
                else if (variant == 1) stream.Receive(ManualProtectionWireMessage.Ack(ManualLeaseContext()));
                else stream.Receive(ManualProtectionWireMessage.Released(context));
                Check(!await channel.WaitForAcknowledgmentAsync() && channel.HasFailed && channel.DisconnectedToken.IsCancellationRequested, "EOF or foreign frame accepted");
            }
        });

        AddAsync("manual helper accepts one attributed acknowledgement only after actual terminal phase", async () =>
        {
            var context = ManualLeaseContext(); var stream = new ManualHelperDuplexStream(); var channel = new ManualHelperPipe(stream, context);
            channel.StartAcknowledgmentMonitor();
            channel.Notice(ManualProtectionPhase.Running);
            await channel.DrainNoticesAsync(); Check(!channel.HasFailed, "progress failed");
            var result = new ManualProtectionResult(ManualProtectionOperation.ReadState, ManualProtectionStatus.StateRead, true, true, 3, 0, 3, 1, 1, 80, 75);
            channel.BeginTerminalResult(); Check(await channel.SendAsync(ManualProtectionWireMessage.ForResult(context, result)), "closed result failed");
            channel.Notice(ManualProtectionPhase.Uncertain); await channel.DrainNoticesAsync(); // No late progress after Result.
            stream.Receive(ManualProtectionWireMessage.Ack(context));
            Check(await channel.WaitForAcknowledgmentAsync() && !channel.HasFailed && !channel.DisconnectedToken.IsCancellationRequested, "normal attributed ACK rejected");
            using (var output = new MemoryStream(stream.Written.ToArray()))
            {
                Equal(ManualProtectionWireKind.Progress, (await ManualProtectionWireProtocol.ReadAsync(output)).Kind);
                Equal(ManualProtectionWireKind.Result, (await ManualProtectionWireProtocol.ReadAsync(output)).Kind);
                Equal(output.Length, output.Position);
            }
        });
    }

    private sealed class ManualHelperDuplexStream : Stream
    {
        private readonly TaskCompletionSource<byte[]> inbound = new TaskCompletionSource<byte[]>(TaskCreationOptions.RunContinuationsAsynchronously);
        private int position; private bool disposed;
        internal readonly System.Collections.Generic.List<byte> Written = new System.Collections.Generic.List<byte>();
        internal void Receive(ManualProtectionWireMessage message)
        {
            byte[] body = ManualProtectionWireProtocol.Encode(message); var frame = new byte[body.Length + 4];
            frame[0] = (byte)body.Length; frame[1] = (byte)(body.Length >> 8); frame[2] = (byte)(body.Length >> 16); frame[3] = (byte)(body.Length >> 24);
            Array.Copy(body, 0, frame, 4, body.Length); inbound.TrySetResult(frame);
        }
        internal void End() => inbound.TrySetResult(new byte[0]);
        public override async Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken)
        {
            byte[] content = await inbound.Task.WaitAsync(cancellationToken);
            if (disposed) throw new IOException("PRIVATE-STREAM");
            int take = Math.Min(count, content.Length - position);
            Array.Copy(content, position, buffer, offset, take); position += take; return take;
        }
        public override Task WriteAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken)
        {
            if (disposed) throw new IOException("PRIVATE-STREAM");
            lock (Written) for (int i = 0; i < count; i++) Written.Add(buffer[offset + i]);
            return Task.CompletedTask;
        }
        public override Task FlushAsync(CancellationToken cancellationToken) => Task.CompletedTask;
        protected override void Dispose(bool disposing) { disposed = true; inbound.TrySetException(new IOException("PRIVATE-DISPOSE")); base.Dispose(disposing); }
        public override bool CanRead => true; public override bool CanSeek => false; public override bool CanWrite => true;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
    }
}
