using System;
using System.Threading.Tasks;
using ATIVBatteryGuard.WmiInterop;

namespace ATIVBatteryGuard.FixedReadTrial
{
    // The notice is a display deadline, never a reason to return, dispose or
    // cancel an SDK operation. Tests control the notice task, not firmware time.
    internal static class FixedReadTrialLifetime
    {
        internal static async Task<T> AwaitWithNoticeAsync<T>(Task<T> operation, Task notice, Action publishNotice)
        {
            if (await Task.WhenAny(operation, notice).ConfigureAwait(false) != operation)
                PublishQuiet(publishNotice);
            return await operation.ConfigureAwait(false);
        }

        internal static async Task<FixedReadTrialCloseResult> RunAndJoinAsync(Func<Task> runAndClose,
            Func<Task<WsabiWmiWindowsCleanupStatus>> requestClose, Action publishFailure)
        {
            bool runFailed = false;
            try { await runAndClose().ConfigureAwait(false); }
            catch { runFailed = true; PublishQuiet(publishFailure); }

            // A run exception or failed report cannot skip this same close.
            try
            {
                var status = await requestClose().ConfigureAwait(false);
                return new FixedReadTrialCloseResult(runFailed, status == WsabiWmiWindowsCleanupStatus.Complete);
            }
            catch { return new FixedReadTrialCloseResult(runFailed, false); }
        }

        private static void PublishQuiet(Action publish)
        {
            try { publish(); } catch { }
        }
    }

    internal sealed class FixedReadTrialCloseResult
    {
        internal bool RunFailed { get; }
        internal bool CleanupComplete { get; }
        internal FixedReadTrialCloseResult(bool runFailed, bool cleanupComplete)
        { RunFailed = runFailed; CleanupComplete = cleanupComplete; }
    }
}
