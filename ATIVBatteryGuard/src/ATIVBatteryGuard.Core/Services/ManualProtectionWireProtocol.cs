using System;
using System.Globalization;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Private local-pipe framing. Callers own sequencing and serialize writers.
    // Cancellation here affects transport I/O only, never an OEM invocation.
    public static class ManualProtectionWireProtocol
    {
        public const int MaximumPayloadBytes = 4096;
        private const string Magic = "ATIV-MANUAL-PROTECTION-V1";

        // Encode/Decode operate on the body; Read/Write add the 4-byte length.
        public static byte[] Encode(ManualProtectionWireMessage message)
        {
            if (message == null) throw new ArgumentNullException(nameof(message));
            var lines = new string[16];
            for (int i = 0; i < lines.Length; i++) lines[i] = "-";
            lines[0] = Magic; lines[1] = Number((int)message.Kind);
            lines[2] = message.Context.JobId; lines[3] = message.Context.Nonce; lines[4] = Number((int)message.Context.Operation);
            if (message.Kind == ManualProtectionWireKind.Progress) lines[5] = Number((int)message.Phase);
            if (message.Kind == ManualProtectionWireKind.Result)
            {
                var value = message.Result;
                if (value == null || value.Operation != message.Context.Operation) throw Invalid();
                lines[6] = Number((int)value.Status); lines[7] = value.CleanupComplete ? "1" : "0";
                lines[8] = value.ProfileValidated ? "1" : "0";
                lines[9] = Number(value.SdkEntries); lines[10] = Number(value.SetterEntries); lines[11] = Number(value.ReadCandidates);
                lines[12] = Candidate(value.PreModeCandidate); lines[13] = Candidate(value.ModeCandidate);
                lines[14] = Candidate(value.UpperCandidate); lines[15] = Candidate(value.LowerCandidate);
            }
            byte[] body = Encoding.ASCII.GetBytes(string.Join("\n", lines) + "\n");
            if (body.Length < 1 || body.Length > MaximumPayloadBytes) throw Invalid();
            return body;
        }

        public static ManualProtectionWireMessage Decode(byte[] body)
        {
            if (body == null || body.Length < 1 || body.Length > MaximumPayloadBytes) throw Invalid();
            foreach (byte value in body) if (value != 10 && (value < 32 || value > 126)) throw Invalid();
            var lines = Encoding.ASCII.GetString(body).Split('\n');
            if (lines.Length != 17 || lines[16].Length != 0 || lines[0] != Magic) throw Invalid();
            int kindValue = Integer(lines[1]), operationValue = Integer(lines[4]);
            if (!Enum.IsDefined(typeof(ManualProtectionWireKind), kindValue) || !Enum.IsDefined(typeof(ManualProtectionOperation), operationValue)) throw Invalid();
            ManualProtectionContext context;
            try { context = new ManualProtectionContext(lines[2], lines[3], (ManualProtectionOperation)operationValue); }
            catch (ArgumentException) { throw Invalid(); }
            var kind = (ManualProtectionWireKind)kindValue;
            if (kind == ManualProtectionWireKind.Result)
            {
                if (lines[5] != "-") throw Invalid();
                ManualProtectionResult result;
                try
                {
                    result = new ManualProtectionResult(context.Operation, (ManualProtectionStatus)Integer(lines[6]),
                        Flag(lines[7]), Flag(lines[8]), Integer(lines[9]), Integer(lines[10]), Integer(lines[11]),
                        Optional(lines[12]), Optional(lines[13]), Optional(lines[14]), Optional(lines[15]));
                }
                catch (ArgumentException) { throw Invalid(); }
                if (!result.CleanupComplete) throw Invalid();
                return ManualProtectionWireMessage.ForResult(context, result);
            }
            for (int i = 6; i < 16; i++) if (lines[i] != "-") throw Invalid();
            if (kind == ManualProtectionWireKind.Progress)
            {
                try { return ManualProtectionWireMessage.Progress(context, (ManualProtectionPhase)Integer(lines[5])); }
                catch (ArgumentException) { throw Invalid(); }
            }
            if (lines[5] != "-") throw Invalid();
            switch (kind)
            {
                case ManualProtectionWireKind.Hello: return ManualProtectionWireMessage.Hello(context);
                case ManualProtectionWireKind.Request: return ManualProtectionWireMessage.Request(context);
                case ManualProtectionWireKind.Ack: return ManualProtectionWireMessage.Ack(context);
                case ManualProtectionWireKind.Released: return ManualProtectionWireMessage.Released(context);
                default: throw Invalid();
            }
        }

        public static async Task<ManualProtectionWireMessage> ReadAsync(Stream stream, CancellationToken token = default(CancellationToken))
        {
            if (stream == null) throw new ArgumentNullException(nameof(stream));
            var header = new byte[4];
            await ReadExactAsync(stream, header, token).ConfigureAwait(false);
            uint length = (uint)header[0] | (uint)header[1] << 8 | (uint)header[2] << 16 | (uint)header[3] << 24;
            if (length < 1 || length > MaximumPayloadBytes) throw Invalid();
            var body = new byte[(int)length];
            try
            {
                await ReadExactAsync(stream, body, token).ConfigureAwait(false);
                return Decode(body);
            }
            finally { Array.Clear(body, 0, body.Length); }
        }

        public static async Task WriteAsync(Stream stream, ManualProtectionWireMessage message, CancellationToken token = default(CancellationToken))
        {
            if (stream == null) throw new ArgumentNullException(nameof(stream));
            var body = Encode(message);
            try
            {
                var header = new[] { (byte)body.Length, (byte)(body.Length >> 8), (byte)(body.Length >> 16), (byte)(body.Length >> 24) };
                await stream.WriteAsync(header, 0, header.Length, token).ConfigureAwait(false);
                await stream.WriteAsync(body, 0, body.Length, token).ConfigureAwait(false);
                await stream.FlushAsync(token).ConfigureAwait(false);
            }
            finally { Array.Clear(body, 0, body.Length); }
        }

        private static async Task ReadExactAsync(Stream stream, byte[] buffer, CancellationToken token)
        {
            int position = 0;
            while (position < buffer.Length)
            {
                int count = await stream.ReadAsync(buffer, position, buffer.Length - position, token).ConfigureAwait(false);
                if (count <= 0) throw new EndOfStreamException("The local protection message ended early.");
                if (count > buffer.Length - position) throw Invalid();
                position += count;
            }
        }
        private static int Integer(string text)
        {
            int result;
            if (!int.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out result) || result < 0 || Number(result) != text) throw Invalid();
            return result;
        }
        private static bool Flag(string text)
        { if (text == "0") return false; if (text == "1") return true; throw Invalid(); }
        private static int? Optional(string text) => text == "-" ? (int?)null : Integer(text);
        private static string Candidate(int? value) => value.HasValue ? Number(value.Value) : "-";
        private static string Number(int value) => value.ToString(CultureInfo.InvariantCulture);
        private static InvalidDataException Invalid() => new InvalidDataException("The bounded local protection message is invalid.");
    }
}
