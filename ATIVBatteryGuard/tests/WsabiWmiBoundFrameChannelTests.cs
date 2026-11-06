using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiBoundFrameChannelTests()
    {
        Add("bound snapshot channel requires explicit binder and transport dependencies", () =>
        {
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiBoundFrameChannel(null, new BoundChannelTransport()));
            BatteryThrows<ArgumentNullException>(() => new WsabiWmiBoundFrameChannel(BoundChannelBinder(), null));
            var transport = new BoundChannelTransport();
            var channel = new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport);
            Check(!channel.CanInvokeMethods && !channel.CanReadHardware && !channel.CanWriteHardware,
                "channel construction enabled hardware");
            var snapshot = new WsabiWmiMethodSnapshot(0, new object());
            Check(!snapshot.CanInvokeMethods && !snapshot.CanReadHardware && !snapshot.CanWriteHardware,
                "transient snapshot became a hardware permission");
            Equal(0, transport.Calls);
        });
        Add("bound snapshot request wrapper rejects malformed frames and preserves an independent envelope", () =>
        {
            var binder = BoundChannelBinder();
            WsabiWmiMethodRequest wrapped;
            foreach (object frame in new object[] { null, new object(), "private request", new int[21], new byte[20],
                new byte[22], new byte[1, 21], Array.CreateInstance(typeof(byte), new[] { 21 }, new[] { 1 }) })
            {
                Check(!binder.TryWrapFrame(frame, out wrapped) && wrapped == null, "malformed frame produced an envelope");
            }
            byte[] valid = BoundChannelRequest();
            for (int index = 0; index < 2; index++)
            {
                byte[] invalid = (byte[])valid.Clone(); invalid[index] ^= 0xff;
                Check(!binder.TryWrapFrame(invalid, out wrapped) && wrapped == null, "invalid magic accepted");
            }
            for (int value = 1; value <= byte.MaxValue; value++)
            {
                byte[] invalid = (byte[])valid.Clone(); invalid[4] = (byte)value;
                Check(!binder.TryWrapFrame(invalid, out wrapped) && wrapped == null, "nonzero request reserved byte accepted");
            }
            Check(binder.TryWrapFrame(valid, out wrapped), "valid frame rejected");
            Equal((uint)1, wrapped.ObservedMethodId);
            Equal((ushort)0x34, wrapped.FirmwareCommand);
            byte expected = valid[5]; valid[5] ^= 0xff;
            Equal(expected, wrapped.Frame[5]);
            byte[] exposed = wrapped.Frame; exposed[5] ^= 0xff;
            Equal(expected, wrapped.Frame[5]);
            var nested = (IReadOnlyDictionary<string, object>)wrapped.Arguments["inData"];
            ((byte[])nested["Bytes"])[5] ^= 0xff;
            Equal(expected, wrapped.Frame[5]);
        });
        AddAsync("bound snapshot pipeline connects framing metadata envelope and decoder without changing dispatch numbers", async () =>
        {
            byte[] replyBytes = BoundChannelReply();
            var output = BoundChannelOutput(replyBytes);
            var transport = new BoundChannelTransport { Handler = (request, token) =>
                Task.FromResult(new WsabiWmiMethodSnapshot(0, output)) };
            var exchange = new WsabiWmiFrameExchange(new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport), TimeSpan.FromSeconds(2));
            byte[] payload = BoundChannelPayload();
            var pending = exchange.ExchangeAsync(0x34, payload);
            payload[0] ^= 0xff;
            var result = await pending;
            Equal(WsabiWmiFrameExchangeStatus.ReplyReceived, result.Status);
            Equal(WsabiWmiReplyStatus.ValidFrame, result.Reply.Status);
            Equal<WsabiWmiMethodReplyStatus?>(WsabiWmiMethodReplyStatus.FrameChecked, result.Reply.MethodReplyStatus);
            Check(result.IsValidFrame && !result.IsHardwareObservation && !result.CanInvokeMethods &&
                !result.CanReadHardware && !result.CanWriteHardware, "synthetic pipeline enabled hardware");
            Equal((uint)1, transport.LastRequest.ObservedMethodId);
            Equal((ushort)0x34, transport.LastRequest.FirmwareCommand);
            Equal((byte)3, transport.LastRequest.Frame[5]);
            Equal((byte)0x34, transport.LastRequest.Frame[2]);
            Equal((byte)0, transport.LastRequest.Frame[3]);
            byte expected = replyBytes[5];
            byte[] exposed = result.Payload; exposed[0] ^= 0xff;
            replyBytes[5] ^= 0xff;
            ((Dictionary<string, object>)output["outData"])["Bytes"] = "private replacement";
            Equal(expected, result.Payload[0]);
            Equal(expected, result.Reply.Payload[0]);
            await BoundChannelIdle(exchange);
            Equal(1, transport.Calls);
        });
        AddAsync("bound snapshot invalid and precancelled requests never enter a transport", async () =>
        {
            var transport = new BoundChannelTransport();
            var channel = new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport);
            foreach (byte[] request in new[] { null, new byte[0], new byte[20], new byte[21], new byte[22] })
                await BoundChannelThrowsAsync<ArgumentException>(() => channel.ExchangeAsync(request, CancellationToken.None));
            using (var caller = new CancellationTokenSource())
            {
                caller.Cancel();
                await BoundChannelThrowsAsync<OperationCanceledException>(() => channel.ExchangeAsync(BoundChannelRequest(), caller.Token));
                var exchange = new WsabiWmiFrameExchange(channel, TimeSpan.FromSeconds(1));
                var result = await exchange.ExchangeAsync(0x34, BoundChannelPayload(), caller.Token);
                BoundChannelAssertExchangeFailure(result, WsabiWmiFrameExchangeStatus.Cancelled);
            }
            Equal(0, transport.Calls);
        });
        AddAsync("unsupported firmware words cannot bypass encoding through raw frames or frame exchange", async () =>
        {
            WsabiWmiMethodBinder binder;
            Check(WsabiWmiMethodBinder.TryCreate(BinderCompleteMetadata(uint.MaxValue), out binder), "metadata fixture rejected");
            var transport = new BoundChannelTransport();
            var channel = new WsabiWmiBoundFrameChannel(binder, transport);
            var frameChannel = new FakeFrameChannel();
            var exchange = new WsabiWmiFrameExchange(frameChannel, TimeSpan.FromSeconds(1));
            byte[] payload = BoundChannelPayload();

            foreach (int command in new[] { 0x100, 0x165, 0xffff })
            {
                byte[] encoded;
                Check(!WsabiWmiRequestEncoder.TryEncode(command, payload, out encoded), "unsupported word encoded");
                Equal(0, encoded.Length);
                WsabiWmiMethodRequest request;
                Check(binder.TryPrepareRequest(0xff, payload, out request), "boundary fixture rejected");
                Equal(uint.MaxValue, request.ObservedMethodId);
                Check(!binder.TryPrepareRequest(command, payload, out request) && request == null,
                    "unsupported word prepared or retained a prior envelope");

                // A caller can supply a complete UInt16 frame without using the
                // encoder. Its upper command byte must still be rejected here.
                byte[] raw = BoundChannelRequest();
                raw[2] = (byte)(command & 0xff); raw[3] = (byte)(command >> 8);
                Check(!binder.TryWrapFrame(raw, out request) && request == null, "raw word bypassed preparation");
                await BoundChannelThrowsAsync<ArgumentException>(() => channel.ExchangeAsync(raw, CancellationToken.None));
                BoundChannelAssertExchangeFailure(await exchange.ExchangeAsync(command, payload),
                    WsabiWmiFrameExchangeStatus.InvalidRequest);
                Equal((byte)(command >> 8), raw[3]);
                Equal(0, transport.Calls); Equal(0, frameChannel.Calls);
                Check(transport.LastRequest == null && frameChannel.LastRequest == null && !exchange.IsBusy,
                    "rejected word entered a dependency or retained an exchange slot");
            }

            WsabiWmiMethodRequest boundary;
            Check(binder.TryPrepareRequest(0xff, payload, out boundary), "maximum supported fixture rejected");
            Check((await channel.ExchangeAsync(boundary.Frame, CancellationToken.None)).IsValidFrame,
                "rejection poisoned a later supported frame");
            Equal(uint.MaxValue, transport.LastRequest.ObservedMethodId);
            Equal((ushort)0xff, transport.LastRequest.FirmwareCommand);
            Equal((byte)0xff, transport.LastRequest.Frame[2]); Equal((byte)0, transport.LastRequest.Frame[3]);
            Check((await exchange.ExchangeAsync(0xff, payload)).IsValidFrame, "rejection poisoned a later frame exchange");
            Equal(1, transport.Calls); Equal(1, frameChannel.Calls);
        });
        AddAsync("bound snapshot channel preserves every nested envelope failure and structural frame result", async () =>
        {
            var transport = new BoundChannelTransport();
            var channel = new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport);
            var throwing = new BoundChannelLookupDictionary(key => { throw new InvalidOperationException("private provider text"); });
            var outputs = new object[] { null, new object(), new Dictionary<string, object>(),
                new Dictionary<string, object> { { "outData", "private nested" } },
                new Dictionary<string, object> { { "outData", new Dictionary<string, object>() } }, throwing };
            var statuses = new[] { WsabiWmiMethodReplyStatus.MissingOutput, WsabiWmiMethodReplyStatus.InvalidOutputType,
                WsabiWmiMethodReplyStatus.MissingOutData, WsabiWmiMethodReplyStatus.InvalidOutDataType,
                WsabiWmiMethodReplyStatus.MissingBytes, WsabiWmiMethodReplyStatus.PropertyReadFailure };
            for (int index = 0; index < outputs.Length; index++)
            {
                object output = outputs[index];
                transport.Handler = (request, token) => Task.FromResult(new WsabiWmiMethodSnapshot(0, output));
                var reply = await channel.ExchangeAsync(BoundChannelRequest(), CancellationToken.None);
                Equal(WsabiWmiReplyStatus.InvalidEnvelope, reply.Status);
                Equal<WsabiWmiMethodReplyStatus?>(statuses[index], reply.MethodReplyStatus);
                Check(!reply.IsValidFrame && !reply.IsHardwareObservation && !reply.CanReadHardware && !reply.CanWriteHardware,
                    "envelope failure enabled hardware");
                Equal(0, reply.Payload.Length);
            }
            object[] bytes = { null, "private bytes", new byte[1, 21], new byte[20], new byte[21], BoundChannelReply() };
            var frames = new[] { WsabiWmiReplyStatus.MissingResponse, WsabiWmiReplyStatus.InvalidType,
                WsabiWmiReplyStatus.InvalidShape, WsabiWmiReplyStatus.UnsupportedLength,
                WsabiWmiReplyStatus.InvalidAcknowledgement, WsabiWmiReplyStatus.ValidFrame };
            for (int index = 0; index < bytes.Length; index++)
            {
                object value = bytes[index];
                transport.Handler = (request, token) => Task.FromResult(new WsabiWmiMethodSnapshot(0, BoundChannelOutput(value)));
                var reply = await channel.ExchangeAsync(BoundChannelRequest(), CancellationToken.None);
                Equal(frames[index], reply.Status);
                Equal<WsabiWmiMethodReplyStatus?>(WsabiWmiMethodReplyStatus.FrameChecked, reply.MethodReplyStatus);
                Equal(frames[index] == WsabiWmiReplyStatus.ValidFrame ? 16 : 0, reply.Payload.Length);
            }
        });
        Add("bound snapshot reply conversion rejects provenance replacement and undefined envelope failures", () =>
        {
            BatteryThrows<ArgumentNullException>(() => WsabiWmiReplyResult.FromMethodReply(null));
            BatteryThrows<ArgumentException>(() => new WsabiWmiReplyResult(WsabiWmiReplyStatus.InvalidEnvelope));
            var byteReply = WsabiWmiReplyDecoder.Decode(0, BoundChannelReply());
            var checkedReply = WsabiWmiReplyResult.FromMethodReply(
                new WsabiWmiMethodReplyResult(WsabiWmiMethodReplyStatus.FrameChecked, byteReply));
            var apiFailure = WsabiWmiReplyResult.FromMethodReply(
                new WsabiWmiMethodReplyResult(WsabiWmiMethodReplyStatus.ApiNotSuccessful));
            var envelopeFailure = WsabiWmiReplyResult.FromMethodReply(
                new WsabiWmiMethodReplyResult(WsabiWmiMethodReplyStatus.MissingOutData));
            foreach (var alreadyWrapped in new[] { checkedReply, apiFailure, envelopeFailure })
            {
                BatteryThrows<ArgumentException>(() => WsabiWmiReplyResult.FromMethodReply(
                    new WsabiWmiMethodReplyResult(WsabiWmiMethodReplyStatus.FrameChecked, alreadyWrapped)));
            }
            Equal<WsabiWmiMethodReplyStatus?>(null, byteReply.MethodReplyStatus);
            Equal<WsabiWmiMethodReplyStatus?>(WsabiWmiMethodReplyStatus.FrameChecked, checkedReply.MethodReplyStatus);
            Equal<WsabiWmiMethodReplyStatus?>(WsabiWmiMethodReplyStatus.ApiNotSuccessful, apiFailure.MethodReplyStatus);
            Equal<WsabiWmiMethodReplyStatus?>(WsabiWmiMethodReplyStatus.MissingOutData, envelopeFailure.MethodReplyStatus);
            Check(!apiFailure.IsValidFrame && !envelopeFailure.IsValidFrame && !checkedReply.CanInvokeMethods,
                "conversion promoted failed or synthetic metadata to an OEM permission");
        });
        AddAsync("bound snapshot API errors avoid field reads and leave the byte-only compatibility contract unchanged", async () =>
        {
            var output = new BoundChannelLookupDictionary(key => { throw new InvalidOperationException("must not inspect private output"); });
            var transport = new BoundChannelTransport();
            var channel = new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport);
            foreach (int apiResult in new[] { 1, -1, int.MinValue, unchecked((int)0x80041003) })
            {
                transport.Handler = (request, token) => Task.FromResult(new WsabiWmiMethodSnapshot(apiResult, output));
                var reply = await channel.ExchangeAsync(BoundChannelRequest(), CancellationToken.None);
                Equal(WsabiWmiReplyStatus.ApiNotSuccessful, reply.Status);
                Equal<WsabiWmiMethodReplyStatus?>(WsabiWmiMethodReplyStatus.ApiNotSuccessful, reply.MethodReplyStatus);
                Equal(0, reply.Payload.Length);
            }
            Equal(0, output.Calls);
            foreach (object bytes in new object[] { null, "private bytes", new byte[20], new byte[21], BoundChannelReply() })
            {
                var reply = WsabiWmiReplyDecoder.Decode(0, bytes);
                Equal<WsabiWmiMethodReplyStatus?>(null, reply.MethodReplyStatus);
                byte[] payload;
                Equal(reply.IsValidFrame, WsabiWmiReplyValidator.TryExtractPayload(0, bytes, out payload));
                Equal(reply.Payload.Length, payload.Length);
            }
        });
        AddAsync("bound snapshot transport faults null tasks null snapshots and unsolicited cancellation remain transport failures", async () =>
        {
            var transport = new BoundChannelTransport();
            var exchange = new WsabiWmiFrameExchange(new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport), TimeSpan.FromSeconds(2));
            Func<WsabiWmiMethodRequest, CancellationToken, Task<WsabiWmiMethodSnapshot>>[] failures =
            {
                (request, token) => { throw new InvalidOperationException(@"C:\Users\PrivateName"); },
                (request, token) => Task.FromException<WsabiWmiMethodSnapshot>(new Exception("private provider detail")),
                (request, token) => null,
                (request, token) => Task.FromResult<WsabiWmiMethodSnapshot>(null),
                (request, token) => Task.FromCanceled<WsabiWmiMethodSnapshot>(new CancellationToken(true))
            };
            foreach (var failure in failures)
            {
                transport.Handler = failure;
                BoundChannelAssertExchangeFailure(await exchange.ExchangeAsync(0x34, BoundChannelPayload()), WsabiWmiFrameExchangeStatus.TransportFailure);
                await BoundChannelIdle(exchange);
            }
            transport.Handler = (request, token) => Task.FromResult(new WsabiWmiMethodSnapshot(0, BoundChannelOutput(BoundChannelReply())));
            Check((await exchange.ExchangeAsync(0x34, BoundChannelPayload())).IsValidFrame, "transport failure poisoned the next operation");
            await BoundChannelIdle(exchange);
        });
        AddAsync("bound snapshot cancellation tokens survive the boundary and win before decoded results are published", async () =>
        {
            using (var caller = new CancellationTokenSource())
            {
                var completion = BoundChannelCompletion();
                var transport = new BoundChannelTransport { Handler = (request, token) => completion.Task };
                var channel = new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport);
                Task<WsabiWmiReplyResult> operation = channel.ExchangeAsync(BoundChannelRequest(), caller.Token);
                Equal(caller.Token, transport.LastToken);
                caller.Cancel();
                completion.SetResult(new WsabiWmiMethodSnapshot(0, BoundChannelOutput(BoundChannelReply())));
                await BoundChannelThrowsAsync<OperationCanceledException>(() => operation);
            }
            using (var caller = new CancellationTokenSource())
            {
                var output = new BoundChannelLookupDictionary(key => {
                    Equal("outData", key); caller.Cancel();
                    return new KeyValuePair<bool, object>(true,
                        new Dictionary<string, object> { { "Bytes", BoundChannelReply() } });
                });
                var transport = new BoundChannelTransport { Handler = (request, token) =>
                    Task.FromResult(new WsabiWmiMethodSnapshot(0, output)) };
                var channel = new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport);
                await BoundChannelThrowsAsync<OperationCanceledException>(() => channel.ExchangeAsync(BoundChannelRequest(), caller.Token));
                Equal(1, output.Calls);
            }
        });
        AddAsync("bound snapshot caller cancellation keeps the exchange busy until uncooperative transport work actually ends", async () =>
        {
            using (var caller = new CancellationTokenSource())
            {
                var completion = BoundChannelCompletion();
                var transport = new BoundChannelTransport { Handler = (request, token) => completion.Task };
                var exchange = new WsabiWmiFrameExchange(new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport), TimeSpan.FromSeconds(2));
                Task<WsabiWmiFrameExchangeResult> pending = exchange.ExchangeAsync(0x34, BoundChannelPayload(), caller.Token);
                await BoundChannelAwait(transport.Entered.Task);
                caller.Cancel();
                BoundChannelAssertExchangeFailure(await pending, WsabiWmiFrameExchangeStatus.Cancelled);
                Check(exchange.IsBusy && transport.LastToken.IsCancellationRequested, "cancelled transport lost its active slot or token");
                BoundChannelAssertExchangeFailure(await exchange.ExchangeAsync(0x34, BoundChannelPayload()), WsabiWmiFrameExchangeStatus.Busy);
                Equal(1, transport.Calls);
                completion.SetResult(new WsabiWmiMethodSnapshot(0, BoundChannelOutput(BoundChannelReply())));
                await BoundChannelIdle(exchange);
                transport.Handler = (request, token) => Task.FromResult(new WsabiWmiMethodSnapshot(0, BoundChannelOutput(BoundChannelReply())));
                Check((await exchange.ExchangeAsync(0x34, BoundChannelPayload())).IsValidFrame, "late cancelled reply poisoned the next operation");
                await BoundChannelIdle(exchange);
            }
        });
        AddAsync("bound snapshot timeout observes late transport faults and prevents overlap before recovery", async () =>
        {
            var completion = BoundChannelCompletion();
            var transport = new BoundChannelTransport { Handler = (request, token) => completion.Task };
            var exchange = new WsabiWmiFrameExchange(new WsabiWmiBoundFrameChannel(BoundChannelBinder(), transport), TimeSpan.FromMilliseconds(100));
            var pending = exchange.ExchangeAsync(0x34, BoundChannelPayload());
            await BoundChannelAwait(transport.Entered.Task);
            BoundChannelAssertExchangeFailure(await pending, WsabiWmiFrameExchangeStatus.TimedOut);
            Check(exchange.IsBusy && transport.LastToken.IsCancellationRequested, "timeout released unfinished transport work");
            BoundChannelAssertExchangeFailure(await exchange.ExchangeAsync(0x34, BoundChannelPayload()), WsabiWmiFrameExchangeStatus.Busy);
            Equal(1, transport.Calls);
            completion.SetException(new InvalidOperationException("private late provider detail"));
            await BoundChannelIdle(exchange);
            transport.Handler = (request, token) => Task.FromResult(new WsabiWmiMethodSnapshot(0, BoundChannelOutput(BoundChannelReply())));
            Check((await exchange.ExchangeAsync(0x34, BoundChannelPayload())).IsValidFrame, "late fault prevented a fresh operation");
            await BoundChannelIdle(exchange);
        });
    }

    private static WsabiWmiMethodBinder BoundChannelBinder()
    {
        var parameter = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, null, "object:DataBuffer");
        var report = new WsabiWmiContractMetadataReport(WsabiWmiContractMethodMetadata.FromParameters(
            WsabiWmiMetadataStatus.Complete, WsabiWmiGuidMatch.MatchesPublicCandidate, 1, true, parameter, parameter),
            new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, true));
        WsabiWmiMethodBinder binder;
        Check(WsabiWmiMethodBinder.TryCreate(report, out binder), "test setup cannot create a complete detailed binding");
        return binder;
    }

    private static byte[] BoundChannelPayload()
    {
        byte[] payload = new byte[16];
        for (int index = 0; index < payload.Length; index++) payload[index] = (byte)(index * 7 + 3);
        return payload;
    }

    private static byte[] BoundChannelRequest()
    {
        byte[] request;
        Check(WsabiWmiRequestEncoder.TryEncode(0x34, BoundChannelPayload(), out request), "test request encoding failed");
        return request;
    }

    private static byte[] BoundChannelReply()
    {
        byte[] reply = new byte[21]; reply[4] = 0xaa;
        for (int index = 5; index < reply.Length; index++) reply[index] = (byte)(index * 11 + 5);
        return reply;
    }

    private static Dictionary<string, object> BoundChannelOutput(object bytes)
        => new Dictionary<string, object> { { "outData", new Dictionary<string, object> { { "Bytes", bytes } } } };

    private static TaskCompletionSource<WsabiWmiMethodSnapshot> BoundChannelCompletion()
        => new TaskCompletionSource<WsabiWmiMethodSnapshot>(TaskCreationOptions.RunContinuationsAsynchronously);

    private static async Task BoundChannelThrowsAsync<T>(Func<Task> operation) where T : Exception
    {
        bool threw = false;
        try { await operation(); } catch (T) { threw = true; }
        Check(threw, "expected bounded channel exception was not thrown");
    }

    private static void BoundChannelAssertExchangeFailure(WsabiWmiFrameExchangeResult result, WsabiWmiFrameExchangeStatus status)
    {
        Equal(status, result.Status); Equal(null, result.Reply); Equal(0, result.Payload.Length);
        Check(!result.IsValidFrame && !result.IsHardwareObservation && !result.CanInvokeMethods &&
            !result.CanReadHardware && !result.CanWriteHardware, "failed bound exchange retained a capability or payload");
    }

    private static async Task BoundChannelAwait(Task operation)
    {
        Check(ReferenceEquals(await Task.WhenAny(operation, Task.Delay(2000)), operation), "transport did not enter within the test bound");
        await operation;
    }

    private static async Task BoundChannelIdle(WsabiWmiFrameExchange exchange)
    {
        var elapsed = Stopwatch.StartNew();
        while (exchange.IsBusy)
        {
            if (elapsed.Elapsed > TimeSpan.FromSeconds(2)) throw new Exception("bound exchange did not release the completed transport");
            await Task.Yield();
        }
    }

    private sealed class BoundChannelTransport : IWsabiWmiMethodSnapshotTransport
    {
        private int calls;
        internal int Calls => Volatile.Read(ref calls);
        internal WsabiWmiMethodRequest LastRequest;
        internal CancellationToken LastToken;
        internal readonly TaskCompletionSource<bool> Entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        internal Func<WsabiWmiMethodRequest, CancellationToken, Task<WsabiWmiMethodSnapshot>> Handler =
            (request, token) => Task.FromResult(new WsabiWmiMethodSnapshot(0, BoundChannelOutput(BoundChannelReply())));

        public Task<WsabiWmiMethodSnapshot> ExchangeAsync(WsabiWmiMethodRequest request, CancellationToken cancellationToken)
        {
            Interlocked.Increment(ref calls);
            LastRequest = request; LastToken = cancellationToken;
            Entered.TrySetResult(true);
            return Handler(request, cancellationToken);
        }
    }

    private sealed class BoundChannelLookupDictionary : IReadOnlyDictionary<string, object>
    {
        private readonly Func<string, KeyValuePair<bool, object>> lookup;
        internal int Calls { get; private set; }
        internal BoundChannelLookupDictionary(Func<string, KeyValuePair<bool, object>> lookup) { this.lookup = lookup; }
        public bool TryGetValue(string key, out object value)
        {
            Calls++;
            var result = lookup(key); value = result.Value; return result.Key;
        }
        public object this[string key] => throw new InvalidOperationException("indexer must not be read");
        public int Count => throw new InvalidOperationException("count must not be read");
        public IEnumerable<string> Keys => throw new InvalidOperationException("keys must not be enumerated");
        public IEnumerable<object> Values => throw new InvalidOperationException("values must not be enumerated");
        public bool ContainsKey(string key) { throw new InvalidOperationException("only fixed TryGetValue is supported"); }
        public IEnumerator<KeyValuePair<string, object>> GetEnumerator() { throw new InvalidOperationException("members must not be enumerated"); }
        IEnumerator IEnumerable.GetEnumerator() { return GetEnumerator(); }
    }
}
