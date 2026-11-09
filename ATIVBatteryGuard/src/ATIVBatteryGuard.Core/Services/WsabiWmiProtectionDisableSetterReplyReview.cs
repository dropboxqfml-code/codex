using System;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    internal enum WsabiWmiProtectionDisableSetterReplyReviewStatus
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
    internal sealed class WsabiWmiProtectionDisableSetterReplyReviewResult
    {
        internal WsabiWmiProtectionDisableStage Role => WsabiWmiProtectionDisableStage.SemanticSet0;
        internal WsabiWmiProtectionDisableSetterReplyReviewStatus Status { get; }
        internal bool IsReceiptOnly => Status == WsabiWmiProtectionDisableSetterReplyReviewStatus.ReceiptOnly;
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

        internal WsabiWmiProtectionDisableSetterReplyReviewResult(WsabiWmiProtectionDisableSetterReplyReviewStatus status)
        { Status = status; }
    }

    // Pure review of supplied, detached replies only. The semantic input is 0;
    // it is never encoded as a command or request. No target, nonce, SDK caller,
    // reservation, dispatch, lifetime evidence or automatic transition mapping
    // is provided. The supplied comparison is not freshness authentication.
    internal sealed class WsabiWmiProtectionDisableSetterReplyReview
    {
        private readonly int preservedSecondComponent;
        private readonly byte[] comparison;
        internal bool IsExecutable => false;
        internal bool CanInvokeMethods => false;
        internal bool CanReadHardware => false;
        internal bool CanWriteHardware => false;

        internal WsabiWmiProtectionDisableSetterReplyReview(int semanticMode, int preservedSecondComponent,
            object comparisonContent)
        {
            if (semanticMode != 0) throw new ArgumentOutOfRangeException(nameof(semanticMode));
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

        internal WsabiWmiProtectionDisableSetterReplyReviewResult Evaluate(WsabiWmiFrameExchangeResult exchange)
        {
            if (exchange == null) return Result(WsabiWmiProtectionDisableSetterReplyReviewStatus.MissingExchange);
            switch (exchange.Status)
            {
                case WsabiWmiFrameExchangeStatus.InvalidRequest: return Result(WsabiWmiProtectionDisableSetterReplyReviewStatus.ExchangeInvalidRequest);
                case WsabiWmiFrameExchangeStatus.Cancelled: return Result(WsabiWmiProtectionDisableSetterReplyReviewStatus.ExchangeCancelled);
                case WsabiWmiFrameExchangeStatus.Busy: return Result(WsabiWmiProtectionDisableSetterReplyReviewStatus.ExchangeBusy);
                case WsabiWmiFrameExchangeStatus.TimedOut: return Result(WsabiWmiProtectionDisableSetterReplyReviewStatus.ExchangeTimedOut);
                case WsabiWmiFrameExchangeStatus.TransportFailure: return Result(WsabiWmiProtectionDisableSetterReplyReviewStatus.ExchangeTransportFailure);
            }
            var reply = exchange.Reply;
            if (reply == null || reply.MethodReplyStatus != WsabiWmiMethodReplyStatus.FrameChecked)
                return Result(WsabiWmiProtectionDisableSetterReplyReviewStatus.MethodEnvelopeRejected);
            if (!exchange.IsValidFrame) return Result(WsabiWmiProtectionDisableSetterReplyReviewStatus.FrameRejected);
            if (reply.DispatchFailurePrefix == WsabiWmiDispatchFailurePrefix.MatchesAnalyzedP05AcjPrefix)
                return Result(WsabiWmiProtectionDisableSetterReplyReviewStatus.DispatchFailurePrefix);

            var payload = reply.Payload;
            try
            {
                if (payload[0] != 0 || payload[1] != 0)
                    return Result(WsabiWmiProtectionDisableSetterReplyReviewStatus.UnexpectedControlPrefix);
                for (int i = 12; i < 16; i++)
                    if (payload[i] != 0) return Result(WsabiWmiProtectionDisableSetterReplyReviewStatus.UnexpectedClearedTail);
                // This is the unchanged input, NOT a returned stored mode.
                // Applying the reader's anti-echo rule here would reject the
                // normal shape without proving that the setter ran.
                if (payload[2] != 0) return Result(WsabiWmiProtectionDisableSetterReplyReviewStatus.UnexpectedInputEcho);
                if (payload[3] != preservedSecondComponent)
                    return Result(WsabiWmiProtectionDisableSetterReplyReviewStatus.PreservedSecondComponentMismatch);
                int difference = 0;
                for (int i = 0; i < comparison.Length; i++) difference |= payload[i + 4] ^ comparison[i];
                if (difference != 0) return Result(WsabiWmiProtectionDisableSetterReplyReviewStatus.PreservedContentMismatch);
                return Result(WsabiWmiProtectionDisableSetterReplyReviewStatus.ReceiptOnly);
            }
            finally { Array.Clear(payload, 0, payload.Length); }
        }

        private static WsabiWmiProtectionDisableSetterReplyReviewResult Result(WsabiWmiProtectionDisableSetterReplyReviewStatus status)
            => new WsabiWmiProtectionDisableSetterReplyReviewResult(status);
    }
}
