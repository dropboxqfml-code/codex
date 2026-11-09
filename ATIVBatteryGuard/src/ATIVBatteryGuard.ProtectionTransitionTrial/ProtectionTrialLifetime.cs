using System;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.ProtectionTransitionTrial
{
    internal static class ProtectionTrialLifetime
    {
        internal static async Task<T> AwaitWithNoticeAsync<T>(Task<T> operation, Task notice, Action publishNotice)
        {
            if (await Task.WhenAny(operation, notice).ConfigureAwait(false) != operation) PublishQuiet(publishNotice);
            return await operation.ConfigureAwait(false);
        }

        internal static async Task<ProtectionTrialCloseResult> RunAndJoinAsync(Func<Task> runAndClose,
            Func<Task<WsabiWmiProtectionCleanupStatus>> requestClose, Action publishFailure)
        {
            bool failed = false;
            try { await runAndClose().ConfigureAwait(false); }
            catch { failed = true; PublishQuiet(publishFailure); }
            try
            {
                var closed = await requestClose().ConfigureAwait(false);
                return new ProtectionTrialCloseResult(failed, closed == WsabiWmiProtectionCleanupStatus.Complete);
            }
            catch { return new ProtectionTrialCloseResult(failed, false); }
        }

        private static void PublishQuiet(Action action) { try { action(); } catch { } }
    }

    internal sealed class ProtectionTrialCloseResult
    {
        internal bool RunFailed { get; }
        internal bool CleanupComplete { get; }
        internal ProtectionTrialCloseResult(bool runFailed, bool cleanupComplete)
        { RunFailed = runFailed; CleanupComplete = cleanupComplete; }
    }
}
