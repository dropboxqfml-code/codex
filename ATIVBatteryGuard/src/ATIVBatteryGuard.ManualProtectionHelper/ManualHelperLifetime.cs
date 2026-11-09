using System;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.ManualProtectionHelper
{
    internal static class ManualHelperLifetime
    {
        internal static async Task<T> AwaitWithNoticeAsync<T>(Task<T> operation, Task notice, Action publish)
        {
            if (operation == null || notice == null) throw new ArgumentNullException();
            if (await Task.WhenAny(operation, notice).ConfigureAwait(false) != operation) Quiet(publish);
            // A notice/transport timeout never substitutes for actual return.
            return await operation.ConfigureAwait(false);
        }

        internal static async Task<bool> JoinActualCloseAsync(Func<Task<WsabiWmiProtectionCleanupStatus>> requestClose)
        {
            try
            {
                var pending = requestClose();
                return pending != null && await pending.ConfigureAwait(false) == WsabiWmiProtectionCleanupStatus.Complete;
            }
            catch { return false; }
        }

        private static void Quiet(Action value) { try { value?.Invoke(); } catch { } }
    }
}
