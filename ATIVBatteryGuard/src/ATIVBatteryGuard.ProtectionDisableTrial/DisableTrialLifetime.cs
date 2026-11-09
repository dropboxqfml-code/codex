using System;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.ProtectionDisableTrial
{
    internal static class DisableTrialLifetime
    {
        internal static async Task<T> AwaitWithNoticeAsync<T>(Task<T> operation, Task notice, Action publishNotice)
        {
            if (await Task.WhenAny(operation, notice).ConfigureAwait(false) != operation) PublishQuiet(publishNotice);
            return await operation.ConfigureAwait(false);
        }

        internal static async Task<DisableTrialCloseResult> RunAndJoinAsync(Func<Task> runAndClose,
            Func<Task<WsabiWmiProtectionCleanupStatus>> requestClose, Action publishFailure)
        {
            bool failed = false;
            try { await runAndClose().ConfigureAwait(false); }
            catch { failed = true; PublishQuiet(publishFailure); }
            try
            {
                var closed = await requestClose().ConfigureAwait(false);
                return new DisableTrialCloseResult(failed, closed == WsabiWmiProtectionCleanupStatus.Complete);
            }
            catch { return new DisableTrialCloseResult(failed, false); }
        }

        private static void PublishQuiet(Action action) { try { action(); } catch { } }
    }

    internal sealed class DisableTrialCloseResult
    {
        internal bool RunFailed { get; }
        internal bool CleanupComplete { get; }
        internal DisableTrialCloseResult(bool runFailed, bool cleanupComplete)
        { RunFailed = runFailed; CleanupComplete = cleanupComplete; }
    }
}
