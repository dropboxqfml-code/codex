using System;
using System.Security.Cryptography;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    public enum WsabiWmiFixedReadProfile { P05AcjStoredModeReadA }

    public enum WsabiWmiFixedReadCreationStatus
    {
        Created, RandomSourceUnavailable, ZeroComparisonContent
    }

    public enum WsabiWmiFixedReadStatus
    {
        StoredModeCandidate, MissingExchange, ExchangeInvalidRequest,
        ExchangeCancelled, ExchangeBusy, ExchangeTimedOut, ExchangeTransportFailure,
        MethodEnvelopeRejected, FrameRejected, DispatchFailurePrefix,
        UnexpectedControlPrefix, UnexpectedClearedTail, InputEcho,
        PreservedAddressMismatch, PreservedContentMismatch, CandidateOutsideDomain
    }

    // Only a sanitized stored-byte candidate. This never identifies a charge
    // threshold, charger state, actual applied protection mode, or write support.
    public sealed class WsabiWmiFixedReadResult
    {
        public WsabiWmiFixedReadProfile Profile => WsabiWmiFixedReadProfile.P05AcjStoredModeReadA;
        public WsabiWmiFixedReadStatus Status { get; }
        public int? StoredModeCandidate { get; }
        public bool IsStoredModeCandidate => Status == WsabiWmiFixedReadStatus.StoredModeCandidate;
        public bool IsChargeLimitConfirmed => false;
        public bool CanWriteHardware => false;

        internal WsabiWmiFixedReadResult(WsabiWmiFixedReadStatus status, int? candidate = null)
        {
            if (!Enum.IsDefined(typeof(WsabiWmiFixedReadStatus), status))
                throw new ArgumentOutOfRangeException(nameof(status));
            if ((status == WsabiWmiFixedReadStatus.StoredModeCandidate) != candidate.HasValue ||
                (candidate.HasValue && candidate.Value != 0 && candidate.Value != 1))
                throw new ArgumentException("A stored-mode candidate requires the bounded candidate domain.", nameof(candidate));
            Status = status;
            StoredModeCandidate = candidate;
        }
    }

    // Approved Read Trial A only: one fixed target and one selected read branch.
    // There is deliberately no public command/address/payload/randomness input.
    // The immutable request is consumed by the separate one-use SDK preparation
    // entry. Constructing or evaluating this value never invokes a method.
    public sealed class WsabiWmiFixedModeReadAttempt
    {
        private const int ComparisonBytes = 8;
        private readonly byte[] comparisonContent;
        private readonly WsabiWmiMethodRequest request;

        public WsabiWmiFixedReadProfile Profile => WsabiWmiFixedReadProfile.P05AcjStoredModeReadA;
        public WsabiWmiMethodRequest Request => request;

        private WsabiWmiFixedModeReadAttempt(byte[] comparison)
        {
            comparisonContent = (byte[])comparison.Clone();
            // Outer selectors are little-endian. The selected EC reader's
            // address components are high then low, not UInt16 little-endian.
            var frame = new byte[21];
            frame[0] = 0x43; frame[1] = 0x58;
            frame[2] = 0x7a; frame[3] = 0x00;
            frame[4] = 0x00;
            frame[5] = 0x82; frame[6] = 0x80;
            frame[7] = 0xf0; frame[8] = 0x4f;
            Array.Copy(comparisonContent, 0, frame, 9, ComparisonBytes);
            request = new WsabiWmiMethodRequest(1, 0x7a, frame);
            Array.Clear(frame, 0, frame.Length);
        }

        public static WsabiWmiFixedReadCreationStatus TryCreate(out WsabiWmiFixedModeReadAttempt attempt)
        {
            attempt = null;
            try
            {
                using (var random = RandomNumberGenerator.Create())
                {
                    if (random == null) return WsabiWmiFixedReadCreationStatus.RandomSourceUnavailable;
                    return TryCreateWithRandom(random.GetBytes, out attempt);
                }
            }
            catch
            {
                attempt = null;
                return WsabiWmiFixedReadCreationStatus.RandomSourceUnavailable;
            }
        }

        // Deterministic offline test seam, inaccessible to application callers.
        // Exactly one eight-byte fill; zero is an abort, never a resample.
        internal static WsabiWmiFixedReadCreationStatus TryCreateWithRandom(Action<byte[]> fillRandom,
            out WsabiWmiFixedModeReadAttempt attempt)
        {
            attempt = null;
            if (fillRandom == null) return WsabiWmiFixedReadCreationStatus.RandomSourceUnavailable;
            var comparison = new byte[ComparisonBytes];
            try
            {
                fillRandom(comparison);
                int any = 0;
                for (int i = 0; i < comparison.Length; i++) any |= comparison[i];
                if (any == 0) return WsabiWmiFixedReadCreationStatus.ZeroComparisonContent;
                attempt = new WsabiWmiFixedModeReadAttempt(comparison);
                return WsabiWmiFixedReadCreationStatus.Created;
            }
            catch
            {
                attempt = null;
                return WsabiWmiFixedReadCreationStatus.RandomSourceUnavailable;
            }
            finally
            {
                Array.Clear(comparison, 0, comparison.Length);
            }
        }

        public WsabiWmiFixedReadResult Evaluate(WsabiWmiFrameExchangeResult exchange)
        {
            if (exchange == null) return Result(WsabiWmiFixedReadStatus.MissingExchange);
            switch (exchange.Status)
            {
                case WsabiWmiFrameExchangeStatus.InvalidRequest: return Result(WsabiWmiFixedReadStatus.ExchangeInvalidRequest);
                case WsabiWmiFrameExchangeStatus.Cancelled: return Result(WsabiWmiFixedReadStatus.ExchangeCancelled);
                case WsabiWmiFrameExchangeStatus.Busy: return Result(WsabiWmiFixedReadStatus.ExchangeBusy);
                case WsabiWmiFrameExchangeStatus.TimedOut: return Result(WsabiWmiFixedReadStatus.ExchangeTimedOut);
                case WsabiWmiFrameExchangeStatus.TransportFailure: return Result(WsabiWmiFixedReadStatus.ExchangeTransportFailure);
            }
            var reply = exchange.Reply;
            if (reply == null || reply.MethodReplyStatus != WsabiWmiMethodReplyStatus.FrameChecked)
                return Result(WsabiWmiFixedReadStatus.MethodEnvelopeRejected);
            if (!exchange.IsValidFrame) return Result(WsabiWmiFixedReadStatus.FrameRejected);
            if (reply.DispatchFailurePrefix == WsabiWmiDispatchFailurePrefix.MatchesAnalyzedP05AcjPrefix)
                return Result(WsabiWmiFixedReadStatus.DispatchFailurePrefix);

            var payload = reply.Payload;
            try
            {
                if (payload[0] != 0 || payload[1] != 0)
                    return Result(WsabiWmiFixedReadStatus.UnexpectedControlPrefix);
                for (int i = 12; i < 16; i++)
                    if (payload[i] != 0) return Result(WsabiWmiFixedReadStatus.UnexpectedClearedTail);
                // The reader replaces only the high address component. Returning
                // that input component is an echo, not the selected stored byte.
                if (payload[2] == 0xf0) return Result(WsabiWmiFixedReadStatus.InputEcho);
                if (payload[3] != 0x4f) return Result(WsabiWmiFixedReadStatus.PreservedAddressMismatch);
                int difference = 0;
                for (int i = 0; i < ComparisonBytes; i++)
                    difference |= payload[i + 4] ^ comparisonContent[i];
                if (difference != 0) return Result(WsabiWmiFixedReadStatus.PreservedContentMismatch);
                if (payload[2] != 0 && payload[2] != 1)
                    return Result(WsabiWmiFixedReadStatus.CandidateOutsideDomain);

                // Comparison is conditional correlation under the approved
                // profile/ordering assumptions, not a transaction identifier
                // or a measurement of charge-limit enforcement.
                return new WsabiWmiFixedReadResult(WsabiWmiFixedReadStatus.StoredModeCandidate, payload[2]);
            }
            finally
            {
                Array.Clear(payload, 0, payload.Length);
            }
        }

        private static WsabiWmiFixedReadResult Result(WsabiWmiFixedReadStatus status)
            => new WsabiWmiFixedReadResult(status);
    }
}
