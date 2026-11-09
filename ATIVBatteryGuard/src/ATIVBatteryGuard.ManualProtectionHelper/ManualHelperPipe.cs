using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.ManualProtectionHelper
{
    // Serializes a few bounded messages. Transport failure requests no more
    // admissions; it never cancels an SDK call or fabricates actual cleanup.
    internal sealed class ManualHelperPipe
    {
        private readonly Stream stream;
        private readonly ManualProtectionContext context;
        private readonly SemaphoreSlim writer = new SemaphoreSlim(1, 1);
        private readonly CancellationTokenSource disconnected = new CancellationTokenSource();
        private readonly object noticeGate = new object();
        private Task notices = Task.CompletedTask;
        private int failed;
        private int terminalReady;
        private Task<ManualProtectionWireMessage> acknowledgment;
        internal bool HasFailed => Volatile.Read(ref failed) != 0;
        internal CancellationToken DisconnectedToken => disconnected.Token;
        internal ManualHelperPipe(Stream stream, ManualProtectionContext context)
        { this.stream = stream; this.context = context; }

        internal void Notice(ManualProtectionPhase phase)
        {
            // The SDK/owner publication callback only schedules transport work.
            // Its local message cannot block actual completion or cleanup.
            lock (noticeGate)
            {
                if (Volatile.Read(ref terminalReady) != 0) return;
                notices = Task.WhenAll(notices, SendAsync(ManualProtectionWireMessage.Progress(context, phase)));
            }
        }

        internal Task DrainNoticesAsync() { lock (noticeGate) return notices; }

        internal void StartAcknowledgmentMonitor()
        {
            if (acknowledgment != null) throw new InvalidOperationException("A single response reader is required.");
            acknowledgment = ReadAcknowledgmentAsync();
        }

        internal void BeginTerminalResult() => Interlocked.Exchange(ref terminalReady, 1);

        internal async Task<bool> WaitForAcknowledgmentAsync()
        {
            if (acknowledgment == null) return false;
            if (await Task.WhenAny(acknowledgment, Task.Delay(TimeSpan.FromSeconds(10))).ConfigureAwait(false) != acknowledgment)
            { Fail(); return false; }
            return await acknowledgment.ConfigureAwait(false) != null && !HasFailed;
        }

        private async Task<ManualProtectionWireMessage> ReadAcknowledgmentAsync()
        {
            try
            {
                // While actual work is active this pending read detects loss
                // of the GUI. The only later GUI frame allowed is the ACK for
                // a terminal result whose actual cleanup is already complete.
                var message = await ManualProtectionWireProtocol.ReadAsync(stream, CancellationToken.None).ConfigureAwait(false);
                if (message == null || message.Kind != ManualProtectionWireKind.Ack ||
                    !context.Matches(message.Context) || Volatile.Read(ref terminalReady) == 0)
                { Fail(); return null; }
                return message;
            }
            catch { Fail(); return null; }
        }

        internal async Task<bool> SendAsync(ManualProtectionWireMessage message)
        {
            if (HasFailed) return false;
            await writer.WaitAsync().ConfigureAwait(false);
            try
            {
                if (HasFailed) return false;
                using (var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5)))
                {
                    var pending = ManualProtectionWireProtocol.WriteAsync(stream, message, timeout.Token);
                    if (await Task.WhenAny(pending, Task.Delay(TimeSpan.FromSeconds(5))).ConfigureAwait(false) != pending)
                    { Fail(); return false; }
                    await pending.ConfigureAwait(false);
                }
                return true;
            }
            catch { Fail(); return false; }
            finally { writer.Release(); }
        }

        internal async Task<ManualProtectionWireMessage> ReadExpectedAsync(ManualProtectionWireKind kind, TimeSpan timeout)
        {
            if (HasFailed) return null;
            try
            {
                using (var cancellation = new CancellationTokenSource(timeout))
                {
                    var pending = ManualProtectionWireProtocol.ReadAsync(stream, cancellation.Token);
                    if (await Task.WhenAny(pending, Task.Delay(timeout)).ConfigureAwait(false) != pending)
                    { Fail(); return null; }
                    var message = await pending.ConfigureAwait(false);
                    if (message == null || message.Kind != kind || !context.Matches(message.Context))
                    { Fail(); return null; }
                    return message;
                }
            }
            catch { Fail(); return null; }
        }

        private void Fail()
        {
            Interlocked.Exchange(ref failed, 1);
            try { disconnected.Cancel(); } catch { }
            try { stream.Dispose(); } catch { }
        }
    }
}
