using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // The GUI-side local exchange. This owns transport only, never an OEM
    // invocation. Completion requires both the actually-closed result AND the
    // helper's release acknowledgment; process exit cannot substitute either.
    public sealed class ManualProtectionClientSession
    {
        private readonly ManualProtectionContext context;
        private readonly TimeSpan handshakeTimeout, releaseTimeout;
        private int used;
        public bool RequestMayHaveBeenSent { get; private set; }
        public bool IsUncertain { get; private set; }

        public ManualProtectionClientSession(ManualProtectionContext context)
            : this(context, TimeSpan.FromSeconds(20), TimeSpan.FromSeconds(10)) { }

        internal ManualProtectionClientSession(ManualProtectionContext context, TimeSpan handshakeTimeout,
            TimeSpan releaseTimeout)
        {
            this.context = context ?? throw new ArgumentNullException(nameof(context));
            if (handshakeTimeout <= TimeSpan.Zero || handshakeTimeout > TimeSpan.FromSeconds(30) ||
                releaseTimeout <= TimeSpan.Zero || releaseTimeout > TimeSpan.FromSeconds(30))
                throw new ArgumentOutOfRangeException(nameof(handshakeTimeout));
            this.handshakeTimeout = handshakeTimeout; this.releaseTimeout = releaseTimeout;
        }

        public async Task<ManualProtectionResult> RunAsync(Stream stream, Action<ManualProtectionPhase> progress = null)
        {
            if (Interlocked.CompareExchange(ref used, 1, 0) != 0)
                return ManualProtectionResult.Failure(context.Operation, ManualProtectionStatus.Busy, true);
            try
            {
                if (stream == null) throw new ArgumentNullException(nameof(stream));
                var hello = await ReadBoundedAsync(stream, handshakeTimeout).ConfigureAwait(false);
                Require(hello, ManualProtectionWireKind.Hello);
                // Set before attempting a write: a failed write may still have
                // delivered a complete request to the helper.
                RequestMayHaveBeenSent = true;
                await WriteBoundedAsync(stream, ManualProtectionWireMessage.Request(context), handshakeTimeout).ConfigureAwait(false);
                Report(progress, ManualProtectionPhase.Preparing);
                ManualProtectionResult result = null;
                int notices = 0;
                while (result == null)
                {
                    // No whole-operation timeout here. An OEM call may still
                    // be running after the display deadline. EOF is Unknown.
                    var message = await ManualProtectionWireProtocol.ReadAsync(stream, CancellationToken.None).ConfigureAwait(false);
                    RequireContext(message);
                    if (message.Kind == ManualProtectionWireKind.Progress)
                    {
                        if (++notices > 32) throw new InvalidDataException("Too many local operation notices.");
                        Report(progress, message.Phase);
                        continue;
                    }
                    Require(message, ManualProtectionWireKind.Result);
                    result = message.Result;
                    if (result == null || !result.CleanupComplete) throw new InvalidDataException("Actual cleanup is unconfirmed.");
                }
                await WriteBoundedAsync(stream, ManualProtectionWireMessage.Ack(context), releaseTimeout).ConfigureAwait(false);
                var released = await ReadBoundedAsync(stream, releaseTimeout).ConfigureAwait(false);
                Require(released, ManualProtectionWireKind.Released);
                Report(progress, ManualProtectionPhase.Completed);
                return result;
            }
            catch
            {
                IsUncertain = RequestMayHaveBeenSent;
                Report(progress, IsUncertain ? ManualProtectionPhase.Uncertain : ManualProtectionPhase.Completed);
                return ManualProtectionResult.Failure(context.Operation,
                    IsUncertain ? ManualProtectionStatus.Unknown : ManualProtectionStatus.Rejected, !IsUncertain);
            }
        }

        private void Require(ManualProtectionWireMessage message, ManualProtectionWireKind kind)
        {
            RequireContext(message);
            if (message.Kind != kind) throw new InvalidDataException("The local operation sequence does not match.");
        }
        private void RequireContext(ManualProtectionWireMessage message)
        {
            if (message == null || !context.Matches(message.Context)) throw new InvalidDataException("The local operation result does not match.");
        }
        private static async Task<ManualProtectionWireMessage> ReadBoundedAsync(Stream stream, TimeSpan timeout)
        {
            var pending = ManualProtectionWireProtocol.ReadAsync(stream, CancellationToken.None);
            await WaitBoundedAsync(pending, timeout).ConfigureAwait(false);
            return await pending.ConfigureAwait(false);
        }
        private static async Task WriteBoundedAsync(Stream stream, ManualProtectionWireMessage message, TimeSpan timeout)
        {
            var pending = ManualProtectionWireProtocol.WriteAsync(stream, message, CancellationToken.None);
            await WaitBoundedAsync(pending, timeout).ConfigureAwait(false);
        }
        private static async Task WaitBoundedAsync(Task pending, TimeSpan timeout)
        {
            if (await Task.WhenAny(pending, Task.Delay(timeout)).ConfigureAwait(false) != pending)
            {
                // The caller closes only this transport. It must not kill a
                // helper or clear a durable operation when this times out.
                _ = pending.ContinueWith(task => { var ignored = task.Exception; },
                    CancellationToken.None, TaskContinuationOptions.OnlyOnFaulted, TaskScheduler.Default);
                throw new TimeoutException("The local exchange did not complete.");
            }
            await pending.ConfigureAwait(false);
        }
        private static void Report(Action<ManualProtectionPhase> progress, ManualProtectionPhase phase)
        { try { progress?.Invoke(phase); } catch { } }
    }
}
