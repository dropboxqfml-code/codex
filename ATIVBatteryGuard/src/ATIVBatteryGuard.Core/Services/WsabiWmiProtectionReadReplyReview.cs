using System;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    internal enum WsabiWmiProtectionReadReplyReviewStatus
    {
        CorrelatedStoredByteCandidate, MissingExchange, ExchangeInvalidRequest,
        ExchangeCancelled, ExchangeBusy, ExchangeTimedOut, ExchangeTransportFailure,
        MethodEnvelopeRejected, FrameRejected, DispatchFailurePrefix,
        UnexpectedControlPrefix, UnexpectedClearedTail, PreservedSecondComponentMismatch,
        PreservedContentMismatch, AmbiguousInputEcho, CandidateOutsideDomain
    }

    // Sanitized detached-data review only. Role is the supplied expectation's
    // label, not authenticated evidence of which target produced the response.
    internal sealed class WsabiWmiProtectionReadReplyReviewResult
    {
        internal WsabiWmiProtectionTransitionStage Role { get; }
        internal WsabiWmiProtectionReadReplyReviewStatus Status { get; }
        internal int? Candidate { get; }
        internal bool IsCorrelatedStoredByteCandidate => Status == WsabiWmiProtectionReadReplyReviewStatus.CorrelatedStoredByteCandidate;
        internal bool IsExecutable => false;
        internal bool IsHardwareObservation => false;
        internal bool IsCurrentRead => false;
        internal bool IsFreshnessProven => false;
        internal bool CanSupplyTransitionObservation => false;
        internal bool IsChargeLimitConfirmed => false;
        internal bool CanInvokeMethods => false;
        internal bool CanReadHardware => false;
        internal bool CanWriteHardware => false;

        internal WsabiWmiProtectionReadReplyReviewResult(WsabiWmiProtectionTransitionStage role,
            WsabiWmiProtectionReadReplyReviewStatus status, int? candidate = null)
        {
            if (!WsabiWmiProtectionReadReplyReview.IsReadRole(role)) throw new ArgumentOutOfRangeException(nameof(role));
            if (!Enum.IsDefined(typeof(WsabiWmiProtectionReadReplyReviewStatus), status)) throw new ArgumentOutOfRangeException(nameof(status));
            if ((status == WsabiWmiProtectionReadReplyReviewStatus.CorrelatedStoredByteCandidate) != candidate.HasValue ||
                (candidate.HasValue && (candidate.Value < 0 || candidate.Value > 255 ||
                    (WsabiWmiProtectionReadReplyReview.IsModeRole(role) && candidate.Value != 0 && candidate.Value != 1))))
                throw new ArgumentException("A correlated candidate requires its bounded role domain.", nameof(candidate));
            Role = role; Status = status; Candidate = candidate;
        }
    }

    // Pure internal response expectation. There is no target resolver, address
    // constant, request encoder, RNG, SDK adapter or transition-observation
    // conversion. Construction and evaluation can only inspect supplied data.
    internal sealed class WsabiWmiProtectionReadReplyReview
    {
        private readonly byte inputFirstComponent, preservedSecondComponent;
        private readonly byte[] comparisonContent;
        internal WsabiWmiProtectionTransitionStage Role { get; }
        internal bool IsExecutable => false;
        internal bool IsHardwareObservation => false;
        internal bool IsCurrentRead => false;
        internal bool IsFreshnessProven => false;
        internal bool IsChargeLimitConfirmed => false;
        internal bool CanInvokeMethods => false;
        internal bool CanReadHardware => false;
        internal bool CanWriteHardware => false;

        internal WsabiWmiProtectionReadReplyReview(WsabiWmiProtectionTransitionStage role,
            int inputFirstComponent, int preservedSecondComponent, object comparisonContent)
        {
            if (!IsReadRole(role)) throw new ArgumentOutOfRangeException(nameof(role));
            if (inputFirstComponent < 0 || inputFirstComponent > 255) throw new ArgumentOutOfRangeException(nameof(inputFirstComponent));
            if (preservedSecondComponent < 0 || preservedSecondComponent > 255) throw new ArgumentOutOfRangeException(nameof(preservedSecondComponent));
            if (comparisonContent == null) throw new ArgumentNullException(nameof(comparisonContent));
            if (comparisonContent.GetType() != typeof(byte[]) || ((byte[])comparisonContent).Length != 8)
                throw new ArgumentException("Exactly eight ordinary byte comparison cells are required.", nameof(comparisonContent));
            var owned = (byte[])((byte[])comparisonContent).Clone();
            int any = 0;
            for (int i = 0; i < owned.Length; i++) any |= owned[i];
            if (any == 0) throw new ArgumentException("Comparison content must not be entirely zero.", nameof(comparisonContent));
            Role = role;
            this.inputFirstComponent = (byte)inputFirstComponent;
            this.preservedSecondComponent = (byte)preservedSecondComponent;
            this.comparisonContent = owned;
        }

        internal WsabiWmiProtectionReadReplyReviewResult Evaluate(WsabiWmiFrameExchangeResult exchange)
        {
            if (exchange == null) return Result(WsabiWmiProtectionReadReplyReviewStatus.MissingExchange);
            switch (exchange.Status)
            {
                case WsabiWmiFrameExchangeStatus.InvalidRequest: return Result(WsabiWmiProtectionReadReplyReviewStatus.ExchangeInvalidRequest);
                case WsabiWmiFrameExchangeStatus.Cancelled: return Result(WsabiWmiProtectionReadReplyReviewStatus.ExchangeCancelled);
                case WsabiWmiFrameExchangeStatus.Busy: return Result(WsabiWmiProtectionReadReplyReviewStatus.ExchangeBusy);
                case WsabiWmiFrameExchangeStatus.TimedOut: return Result(WsabiWmiProtectionReadReplyReviewStatus.ExchangeTimedOut);
                case WsabiWmiFrameExchangeStatus.TransportFailure: return Result(WsabiWmiProtectionReadReplyReviewStatus.ExchangeTransportFailure);
            }
            var reply = exchange.Reply;
            if (reply == null || reply.MethodReplyStatus != WsabiWmiMethodReplyStatus.FrameChecked)
                return Result(WsabiWmiProtectionReadReplyReviewStatus.MethodEnvelopeRejected);
            if (!exchange.IsValidFrame) return Result(WsabiWmiProtectionReadReplyReviewStatus.FrameRejected);
            if (reply.DispatchFailurePrefix == WsabiWmiDispatchFailurePrefix.MatchesAnalyzedP05AcjPrefix)
                return Result(WsabiWmiProtectionReadReplyReviewStatus.DispatchFailurePrefix);

            var payload = reply.Payload;
            try
            {
                if (payload[0] != 0 || payload[1] != 0)
                    return Result(WsabiWmiProtectionReadReplyReviewStatus.UnexpectedControlPrefix);
                for (int i = 12; i < 16; i++)
                    if (payload[i] != 0) return Result(WsabiWmiProtectionReadReplyReviewStatus.UnexpectedClearedTail);
                if (payload[3] != preservedSecondComponent)
                    return Result(WsabiWmiProtectionReadReplyReviewStatus.PreservedSecondComponentMismatch);
                int difference = 0;
                for (int i = 0; i < comparisonContent.Length; i++) difference |= payload[i + 4] ^ comparisonContent[i];
                if (difference != 0) return Result(WsabiWmiProtectionReadReplyReviewStatus.PreservedContentMismatch);
                // For threshold bytes the legitimate domain overlaps the
                // unchanged input component. This response cannot distinguish
                // a real equal-valued read from input echo, so retain no value.
                if (payload[2] == inputFirstComponent)
                    return Result(WsabiWmiProtectionReadReplyReviewStatus.AmbiguousInputEcho);
                if (IsModeRole(Role) && payload[2] != 0 && payload[2] != 1)
                    return Result(WsabiWmiProtectionReadReplyReviewStatus.CandidateOutsideDomain);
                // Correlation is conditional on the caller's context and the
                // separately applicable source, input and capture contracts.
                // It does not prove freshness, target identity or execution.
                return new WsabiWmiProtectionReadReplyReviewResult(Role,
                    WsabiWmiProtectionReadReplyReviewStatus.CorrelatedStoredByteCandidate, payload[2]);
            }
            finally { Array.Clear(payload, 0, payload.Length); }
        }

        private WsabiWmiProtectionReadReplyReviewResult Result(WsabiWmiProtectionReadReplyReviewStatus status)
            => new WsabiWmiProtectionReadReplyReviewResult(Role, status);

        internal static bool IsModeRole(WsabiWmiProtectionTransitionStage role)
            => role == WsabiWmiProtectionTransitionStage.PreMode || role == WsabiWmiProtectionTransitionStage.PostMode;

        internal static bool IsReadRole(WsabiWmiProtectionTransitionStage role)
            => IsModeRole(role) || role == WsabiWmiProtectionTransitionStage.PreUpper ||
                role == WsabiWmiProtectionTransitionStage.PreLower || role == WsabiWmiProtectionTransitionStage.PostUpper ||
                role == WsabiWmiProtectionTransitionStage.PostLower;
    }
}
