using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterManualProtectionWireTests()
    {
        Add("manual wire round trips only the six closed message kinds and bounded context", () =>
        {
            var context = ManualModelContext(ManualProtectionOperation.Enable80);
            var messages = new[] { ManualProtectionWireMessage.Hello(context), ManualProtectionWireMessage.Request(context),
                ManualProtectionWireMessage.Progress(context, ManualProtectionPhase.Preparing),
                ManualProtectionWireMessage.ForResult(context, ManualModelEnable()),
                ManualProtectionWireMessage.Ack(context), ManualProtectionWireMessage.Released(context) };
            foreach (var message in messages)
            {
                byte[] encoded = ManualProtectionWireProtocol.Encode(message); var preserved = (byte[])encoded.Clone();
                var decoded = ManualProtectionWireProtocol.Decode(encoded);
                Check(context.Matches(decoded.Context), "wire context changed"); Equal(message.Kind, decoded.Kind); Equal(message.Phase, decoded.Phase);
                Check(encoded.SequenceEqual(preserved), "decoder changed caller buffer");
                if (message.Result != null) ManualWireResultEqual(message.Result, decoded.Result);
                else Check(decoded.Result == null, "non-result message gained a result");
            }
        });

        Add("manual wire transmits all valid fixed result shapes including closed unknown without inventing state", () =>
        {
            foreach (var result in new[] { ManualModelEnable(), ManualModelDisable(),
                new ManualProtectionResult(ManualProtectionOperation.ReadState, ManualProtectionStatus.StateRead, true, true, 3, 0, 3, 1, 1, 255, 0),
                new ManualProtectionResult(ManualProtectionOperation.Enable80, ManualProtectionStatus.AlreadyDesiredCandidate, true, true, 1, 0, 1, 1, 1),
                new ManualProtectionResult(ManualProtectionOperation.DisableProtection, ManualProtectionStatus.AlreadyDesiredCandidate, true, true, 1, 0, 1, 0, 0),
                ManualProtectionResult.Failure(ManualProtectionOperation.ReadState, ManualProtectionStatus.Cancelled),
                ManualProtectionResult.Failure(ManualProtectionOperation.Enable80, ManualProtectionStatus.Unknown, true, true, 4, 1, 3, 0) })
            {
                var message = ManualProtectionWireMessage.ForResult(ManualModelContext(result.Operation), result);
                ManualWireResultEqual(result, ManualProtectionWireProtocol.Decode(ManualProtectionWireProtocol.Encode(message)).Result);
            }
        });

        Add("manual wire cannot send unconfirmed cleanup as a terminal result or phase completion", () =>
        {
            var context = ManualModelContext(ManualProtectionOperation.Enable80);
            BatteryThrows<ArgumentException>(() => ManualProtectionWireMessage.ForResult(context,
                ManualProtectionResult.Failure(context.Operation, ManualProtectionStatus.Unknown)));
            BatteryThrows<ArgumentException>(() => ManualProtectionWireMessage.ForResult(context, ManualModelDisable()));
            foreach (var phase in new[] { ManualProtectionPhase.Idle, ManualProtectionPhase.Completed, (ManualProtectionPhase)99 })
                BatteryThrows<ArgumentOutOfRangeException>(() => ManualProtectionWireMessage.Progress(context, phase));
            byte[] body = ManualWireMutate(ManualProtectionWireMessage.ForResult(context,
                ManualProtectionResult.Failure(context.Operation, ManualProtectionStatus.Unknown, true)), 7, "0");
            BatteryThrows<InvalidDataException>(() => ManualProtectionWireProtocol.Decode(body));
        });

        Add("manual wire rejects extra missing reordered and duplicate body fields", () =>
        {
            byte[] good = ManualProtectionWireProtocol.Encode(ManualProtectionWireMessage.Hello(ManualModelContext(ManualProtectionOperation.ReadState)));
            string text = Encoding.ASCII.GetString(good); var lines = text.Split('\n');
            foreach (string bad in new[] { text + "\n", text.TrimEnd('\n'), "\n" + text,
                string.Join("\n", lines.Where((line, index) => index != 6)),
                string.Join("\n", lines.Take(8).Concat(new[] { lines[7] }).Concat(lines.Skip(8))) })
                BatteryThrows<InvalidDataException>(() => ManualProtectionWireProtocol.Decode(Encoding.ASCII.GetBytes(bad)));
            string swapped = lines[2]; lines[2] = lines[3]; lines[3] = swapped;
            BatteryThrows<InvalidDataException>(() => ManualProtectionWireProtocol.Decode(Encoding.ASCII.GetBytes(string.Join("\n", lines))));
        });

        Add("manual wire rejects non ASCII control characters and unsupported payload sizes", () =>
        {
            byte[] good = ManualProtectionWireProtocol.Encode(ManualProtectionWireMessage.Request(ManualModelContext(ManualProtectionOperation.ReadState)));
            foreach (byte bad in new byte[] { 0, 9, 13, 31, 127, 128, 255 })
            {
                var value = (byte[])good.Clone(); value[0] = bad;
                BatteryThrows<InvalidDataException>(() => ManualProtectionWireProtocol.Decode(value));
            }
            BatteryThrows<InvalidDataException>(() => ManualProtectionWireProtocol.Decode(null));
            BatteryThrows<InvalidDataException>(() => ManualProtectionWireProtocol.Decode(new byte[0]));
            BatteryThrows<InvalidDataException>(() => ManualProtectionWireProtocol.Decode(new byte[ManualProtectionWireProtocol.MaximumPayloadBytes + 1]));
        });

        Add("manual wire rejects unknown enums noncanonical numbers invalid flags and expanded private contexts", () =>
        {
            var message = ManualProtectionWireMessage.ForResult(ManualModelContext(ManualProtectionOperation.Enable80), ManualModelEnable());
            foreach (int field in new[] { 1, 4, 6, 9, 10, 11 })
            foreach (string value in new[] { "-1", "+1", "01", " 1", "1 ", "999999999999", "999" })
                BatteryThrows<InvalidDataException>(() => ManualProtectionWireProtocol.Decode(ManualWireMutate(message, field, value)));
            foreach (int field in new[] { 7, 8 })
            foreach (string value in new[] { "2", "Yes", "true", "01", "-" })
                BatteryThrows<InvalidDataException>(() => ManualProtectionWireProtocol.Decode(ManualWireMutate(message, field, value)));
            BatteryThrows<InvalidDataException>(() => ManualProtectionWireProtocol.Decode(ManualWireMutate(message, 2, new string('a', 33))));
            BatteryThrows<InvalidDataException>(() => ManualProtectionWireProtocol.Decode(ManualWireMutate(message, 3, new string('B', 64))));
        });

        Add("manual wire rejects success or candidate spoofing by changing any dependent result field", () =>
        {
            var message = ManualProtectionWireMessage.ForResult(ManualModelContext(ManualProtectionOperation.Enable80), ManualModelEnable());
            foreach (var change in new[] { Tuple.Create(7, "0"), Tuple.Create(8, "0"), Tuple.Create(9, "6"),
                Tuple.Create(10, "0"), Tuple.Create(11, "5"), Tuple.Create(12, "1"), Tuple.Create(13, "0"),
                Tuple.Create(14, "79"), Tuple.Create(15, "74"), Tuple.Create(6, "8") })
                BatteryThrows<InvalidDataException>(() => ManualProtectionWireProtocol.Decode(ManualWireMutate(message, change.Item1, change.Item2)));
            var failed = ManualProtectionWireMessage.ForResult(ManualModelContext(ManualProtectionOperation.Enable80),
                ManualProtectionResult.Failure(ManualProtectionOperation.Enable80, ManualProtectionStatus.Rejected, true, true, 1, 0, 1, 0));
            foreach (int field in new[] { 13, 14, 15 })
                BatteryThrows<InvalidDataException>(() => ManualProtectionWireProtocol.Decode(ManualWireMutate(failed, field, "0")));
        });

        Add("manual wire non result frames cannot smuggle progress status or candidate fields", () =>
        {
            var context = ManualModelContext(ManualProtectionOperation.ReadState);
            foreach (var message in new[] { ManualProtectionWireMessage.Hello(context), ManualProtectionWireMessage.Request(context),
                ManualProtectionWireMessage.Ack(context), ManualProtectionWireMessage.Released(context) })
            for (int field = 5; field < 16; field++)
                BatteryThrows<InvalidDataException>(() => ManualProtectionWireProtocol.Decode(ManualWireMutate(message, field, "0")));
            var progress = ManualProtectionWireMessage.Progress(context, ManualProtectionPhase.WaitingForActualCompletion);
            for (int field = 6; field < 16; field++)
                BatteryThrows<InvalidDataException>(() => ManualProtectionWireProtocol.Decode(ManualWireMutate(progress, field, "0")));
        });

        AddAsync("manual wire handles partial framing reads and leaves concatenated later frames intact", async () =>
        {
            var context = ManualModelContext(ManualProtectionOperation.Enable80);
            using (var output = new MemoryStream())
            {
                await ManualProtectionWireProtocol.WriteAsync(output, ManualProtectionWireMessage.Hello(context));
                await ManualProtectionWireProtocol.WriteAsync(output, ManualProtectionWireMessage.ForResult(context, ManualModelEnable()));
                foreach (int fragment in new[] { 1, 2, 3, 17 })
                using (var input = new ManualWireFragmentStream(output.ToArray(), fragment))
                {
                    Equal(ManualProtectionWireKind.Hello, (await ManualProtectionWireProtocol.ReadAsync(input)).Kind);
                    var result = await ManualProtectionWireProtocol.ReadAsync(input); ManualWireResultEqual(ManualModelEnable(), result.Result);
                    Equal(input.Length, input.Position);
                }
            }
        });

        AddAsync("manual wire rejects zero huge and truncated frame lengths before accepting any message", async () =>
        {
            foreach (var header in new[] { new byte[] { 0, 0, 0, 0 }, new byte[] { 1, 16, 0, 0 }, new byte[] { 255, 255, 255, 255 } })
            using (var stream = new ManualWireFragmentStream(header, 64))
            {
                await ManualWireThrowsAsync<InvalidDataException>(() => ManualProtectionWireProtocol.ReadAsync(stream));
                Equal(1, stream.ReadCalls);
            }
            foreach (int length in new[] { 0, 1, 2, 3 })
            using (var stream = new MemoryStream(new byte[length]))
                await ManualWireThrowsAsync<EndOfStreamException>(() => ManualProtectionWireProtocol.ReadAsync(stream));
            using (var stream = new MemoryStream(new byte[] { 10, 0, 0, 0, 1, 2 }))
                await ManualWireThrowsAsync<EndOfStreamException>(() => ManualProtectionWireProtocol.ReadAsync(stream));
        });

        AddAsync("manual wire framing cancellation cannot construct a result and does not call hardware callbacks", async () =>
        {
            using (var cancelled = new CancellationTokenSource())
            using (var stream = new MemoryStream())
            {
                cancelled.Cancel();
                await ManualWireThrowsAsync<OperationCanceledException>(() => ManualProtectionWireProtocol.ReadAsync(stream, cancelled.Token));
                await ManualWireThrowsAsync<OperationCanceledException>(() => ManualProtectionWireProtocol.WriteAsync(stream,
                    ManualProtectionWireMessage.Request(ManualModelContext(ManualProtectionOperation.ReadState)), cancelled.Token));
                Equal(0L, stream.Length);
            }
        });

        Add("manual wire correlation validates context separately from a structurally valid result", () =>
        {
            var expected = ManualModelContext(ManualProtectionOperation.Enable80);
            var other = new ManualProtectionContext(new string('c', 32), expected.Nonce, expected.Operation);
            var message = ManualProtectionWireProtocol.Decode(ManualProtectionWireProtocol.Encode(
                ManualProtectionWireMessage.ForResult(other, ManualModelEnable())));
            Check(!expected.Matches(message.Context), "structural decoding authenticated a foreign request");
            Check(message.Result.IsSuccess, "structural decoding unexpectedly changed the detached shape");
        });
    }

    private static byte[] ManualWireMutate(ManualProtectionWireMessage message, int field, string value)
    {
        var lines = Encoding.ASCII.GetString(ManualProtectionWireProtocol.Encode(message)).Split('\n');
        lines[field] = value; return Encoding.ASCII.GetBytes(string.Join("\n", lines));
    }
    private static void ManualWireResultEqual(ManualProtectionResult expected, ManualProtectionResult actual)
    {
        Check(actual != null, "wire result missing"); Equal(expected.Operation, actual.Operation); Equal(expected.Status, actual.Status);
        Equal(expected.CleanupComplete, actual.CleanupComplete); Equal(expected.ProfileValidated, actual.ProfileValidated);
        Equal(expected.SdkEntries, actual.SdkEntries); Equal(expected.SetterEntries, actual.SetterEntries); Equal(expected.ReadCandidates, actual.ReadCandidates);
        Equal(expected.PreModeCandidate, actual.PreModeCandidate); Equal(expected.ModeCandidate, actual.ModeCandidate);
        Equal(expected.UpperCandidate, actual.UpperCandidate); Equal(expected.LowerCandidate, actual.LowerCandidate);
    }
    private static async Task ManualWireThrowsAsync<T>(Func<Task> action) where T : Exception
    {
        try { await action(); } catch (T) { return; }
        throw new Exception("Expected bounded wire failure: " + typeof(T).Name);
    }
    private sealed class ManualWireFragmentStream : MemoryStream
    {
        private readonly int fragment;
        internal int ReadCalls;
        internal ManualWireFragmentStream(byte[] bytes, int fragment) : base(bytes) { this.fragment = fragment; }
        public override Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken)
        { ReadCalls++; return base.ReadAsync(buffer, offset, Math.Min(count, fragment), cancellationToken); }
    }
}
