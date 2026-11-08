using System;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    internal enum WsabiWmiProtectionSetterReplyReviewStatus
    {
        ReceiptOnly, MissingExchange, ExchangeInvalidRequest, ExchangeCancelled,
        ExchangeBusy, ExchangeTimedOut, ExchangeTransportFailure, MethodEnvelopeRejected,
        FrameRejected, DispatchFailurePrefix, UnexpectedControlPrefix,
        UnexpectedClearedTail, UnexpectedInputEcho, PreservedSecondComponentMismatch,
        PreservedContentMismatch
    }

    // The selected setter leaves its input message intact. A matched response
    // cannot distinguish setter execution from upload-only echo or a matching
    // older response. In particular, it is NOT a setter-specific success ACK.
    internal sealed class WsabiWmiProtectionSetterReplyReviewResult
    {
        internal WsabiWmiProtectionTransitionStage Role => WsabiWmiProtectionTransitionStage.SemanticSet1;
        internal WsabiWmiProtectionSetterReplyReviewStatus Status { get; }
        internal bool IsReceiptOnly => Status == WsabiWmiProtectionSetterReplyReviewStatus.ReceiptOnly;
        internal bool IsSetterExecutionConfirmed => false;
        internal bool HasSemanticAcknowledgement => false;
        internal bool IsStoredChangeConfirmed => false;
        internal bool IsActualCloseConfirmed => false;
        internal bool IsChargeLimitConfirmed => false;
        internal bool CanSupplyTransitionObservation => false;
        internal bool IsHardwareObservation => false;
        internal bool IsExecutable => false;
        internal bool CanInvokeMethods => false;
        internal bool CanReadHardware => false;
        internal bool CanWriteHardware => false;

        internal WsabiWmiProtectionSetterReplyReviewResult(WsabiWmiProtectionSetterReplyReviewStatus status)
        { Status = status; }
    }

    // Pure review of supplied, detached replies only. The semantic input is 1;
    // it is never encoded as a command or request. No target, nonce, SDK caller,
    // reservation, dispatch, lifetime evidence or automatic transition mapping
    // is provided. The supplied comparison is not freshness authentication.
    internal sealed class WsabiWmiProtectionSetterReplyReview
    {
        private readonly int preservedSecondComponent;
        private readonly byte[] comparison;
        internal bool IsExecutable => false;
        internal bool CanInvokeMethods => false;
        internal bool CanReadHardware => false;
        internal bool CanWriteHardware => false;

        internal WsabiWmiProtectionSetterReplyReview(int semanticMode, int preservedSecondComponent,
            object comparisonContent)
        {
            if (semanticMode != 1) throw new ArgumentOutOfRangeException(nameof(semanticMode));
            if (preservedSecondComponent < 0 || preservedSecondComponent > byte.MaxValue)
                throw new ArgumentOutOfRangeException(nameof(preservedSecondComponent));
            if (comparisonContent == null || comparisonContent.GetType() != typeof(byte[]) ||
                ((byte[])comparisonContent).Length != 8)
                throw new ArgumentException("Exactly eight ordinary byte cells are required.", nameof(comparisonContent));
            comparison = (byte[])((byte[])comparisonContent).Clone();
            int any = 0;
            foreach (byte value in comparison) any |= value;
            if (any == 0) throw new ArgumentException("All-zero comparison content is unsupported.", nameof(comparisonContent));
            this.preservedSecondComponent = preservedSecondComponent;
        }

        internal WsabiWmiProtectionSetterReplyReviewResult Evaluate(WsabiWmiFrameExchangeResult exchange)
        {
            if (exchange == null) return Result(WsabiWmiProtectionSetterReplyReviewStatus.MissingExchange);
            switch (exchange.Status)
            {
                case WsabiWmiFrameExchangeStatus.InvalidRequest: return Result(WsabiWmiProtectionSetterReplyReviewStatus.ExchangeInvalidRequest);
                case WsabiWmiFrameExchangeStatus.Cancelled: return Result(WsabiWmiProtectionSetterReplyReviewStatus.ExchangeCancelled);
                case WsabiWmiFrameExchangeStatus.Busy: return Result(WsabiWmiProtectionSetterReplyReviewStatus.ExchangeBusy);
                case WsabiWmiFrameExchangeStatus.TimedOut: return Result(WsabiWmiProtectionSetterReplyReviewStatus.ExchangeTimedOut);
                case WsabiWmiFrameExchangeStatus.TransportFailure: return Result(WsabiWmiProtectionSetterReplyReviewStatus.ExchangeTransportFailure);
            }
            var reply = exchange.Reply;
            if (reply == null || reply.MethodReplyStatus != WsabiWmiMethodReplyStatus.FrameChecked)
                return Result(WsabiWmiProtectionSetterReplyReviewStatus.MethodEnvelopeRejected);
            if (!exchange.IsValidFrame) return Result(WsabiWmiProtectionSetterReplyReviewStatus.FrameRejected);
            if (reply.DispatchFailurePrefix == WsabiWmiDispatchFailurePrefix.MatchesAnalyzedP05AcjPrefix)
                return Result(WsabiWmiProtectionSetterReplyReviewStatus.DispatchFailurePrefix);

            var payload = reply.Payload;
            try
            {
                if (payload[0] != 0 || payload[1] != 0)
                    return Result(WsabiWmiProtectionSetterReplyReviewStatus.UnexpectedControlPrefix);
                for (int i = 12; i < 16; i++)
                    if (payload[i] != 0) return Result(WsabiWmiProtectionSetterReplyReviewStatus.UnexpectedClearedTail);
                // This is the unchanged input, NOT a returned stored mode.
                // Applying the reader's anti-echo rule here would reject the
                // normal shape without proving that the setter ran.
                if (payload[2] != 1) return Result(WsabiWmiProtectionSetterReplyReviewStatus.UnexpectedInputEcho);
                if (payload[3] != preservedSecondComponent)
                    return Result(WsabiWmiProtectionSetterReplyReviewStatus.PreservedSecondComponentMismatch);
                int difference = 0;
                for (int i = 0; i < comparison.Length; i++) difference |= payload[i + 4] ^ comparison[i];
                if (difference != 0) return Result(WsabiWmiProtectionSetterReplyReviewStatus.PreservedContentMismatch);
                return Result(WsabiWmiProtectionSetterReplyReviewStatus.ReceiptOnly);
            }
            finally { Array.Clear(payload, 0, payload.Length); }
        }

        private static WsabiWmiProtectionSetterReplyReviewResult Result(WsabiWmiProtectionSetterReplyReviewStatus status)
            => new WsabiWmiProtectionSetterReplyReviewResult(status);
    }
}
