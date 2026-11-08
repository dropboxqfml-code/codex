using System;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.WmiInterop
{
    public static partial class WsabiWmiWindowsSingleReadPreparation
    {
        private static readonly ConditionalWeakTable<WsabiWmiFixedModeReadAttempt, Attempt> FixedReadAttempts =
            new ConditionalWeakTable<WsabiWmiFixedModeReadAttempt, Attempt>();

        // The separate A-only entry accepts the sealed fixed-read attempt, not
        // caller-supplied commands, addresses, frames, timeouts or a dispatch.
        // Its local one-use claim supplements the tool's persistent reservation;
        // it is not a global approval flag or permission for setting writes.
        public static Task<WsabiWmiSingleReadPreparationResult> PrepareFixedReadAAsync(
            WsabiWmiSingleReadPlan plan, WsabiWmiWindowsSdkBinding binding,
            WsabiWmiFixedModeReadAttempt fixedRead, IWsabiWmiExchangeGate exchangeGate,
            CancellationToken cancellationToken = default(CancellationToken))
        {
            if (binding == null) throw new ArgumentNullException(nameof(binding));
            // Validate local arguments before consuming this attempt. This
            // creates no SDK objects, queries, subscriptions or hardware work.
            ValidateArguments(binding.CreateTrialBinding(), exchangeGate,
                TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(10));
            if (fixedRead == null) return Rejected(WsabiWmiSingleReadPreparationStatus.RequestMismatch);
            Attempt attempt = FixedReadAttempts.GetValue(fixedRead, _ => new Attempt());
            if (Interlocked.CompareExchange(ref attempt.Claimed, 1, 0) != 0)
                return Rejected(WsabiWmiSingleReadPreparationStatus.AttemptAlreadyUsed);

            // The existing path freezes the entire request, binds the actual
            // target/observer/input bundle, and retains owned inputs through
            // the method/capture/close join, including cancellation Unknown.
            return PrepareSdkBindingAsync(plan, binding, fixedRead.Request,
                exchangeGate, TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(10), cancellationToken);
        }
    }
}
