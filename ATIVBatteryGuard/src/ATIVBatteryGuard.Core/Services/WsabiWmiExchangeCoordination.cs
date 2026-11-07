using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;

namespace ATIVBatteryGuard.Core.Services
{
    // Preserve a supplied transport's direct throw/null-task boundary through
    // an async wrapper. This is not evidence that untracked work has stopped.
    // Fixed text only: never retain the supplied exception or provider details.
    internal sealed class WsabiWmiUntrackedDispatchException : System.InvalidOperationException
    {
        internal WsabiWmiUntrackedDispatchException()
            : base("The supplied transport did not return a tracked operation.") { }
    }

    internal sealed class WsabiWmiExchangeResource
    {
        private static readonly ConditionalWeakTable<object, WsabiWmiExchangeResource> Resources =
            new ConditionalWeakTable<object, WsabiWmiExchangeResource>();
        private int active;
        private int quarantined;
        internal bool IsQuarantined => Volatile.Read(ref quarantined) != 0;
        internal bool IsBusy => Volatile.Read(ref active) != 0 || IsQuarantined;

        internal static object Identity(IWsabiWmiFrameChannel channel)
            => (channel as WsabiWmiCooperativeFrameChannel)?.ExchangeIdentity ??
               (channel as WsabiWmiBoundFrameChannel)?.ExchangeIdentity ?? channel;

        internal static WsabiWmiExchangeResource For(object identity)
            => Resources.GetValue(identity, _ => new WsabiWmiExchangeResource());

        internal bool TryEnter()
        {
            if (IsQuarantined || Interlocked.CompareExchange(ref active, 1, 0) != 0) return false;
            return !IsQuarantined;
        }

        // Quarantine has no reset/retry API. Even a concurrent Release cannot
        // clear it: both IsBusy and TryEnter consult the separate sticky flag.
        internal void Quarantine() => Interlocked.Exchange(ref quarantined, 1);
        internal void Release() => Interlocked.Exchange(ref active, 0);
    }

    internal sealed class WsabiWmiExchangeStopSignal : System.IDisposable
    {
        private const int Stopped = 2;
        private int state;
        private readonly ManualResetEvent signal = new ManualResetEvent(false);
        private readonly TaskCompletionSource<bool> notification =
            new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        internal WaitHandle WaitHandle => signal;
        internal Task Notification => notification.Task;
        internal bool IsRequested => (Volatile.Read(ref state) & Stopped) != 0;

        // This is a notification only; it never runs supplied channel callbacks.
        internal void Request()
        {
            int previous;
            do { previous = Volatile.Read(ref state); }
            while (Interlocked.CompareExchange(ref state, previous | Stopped, previous) != previous);
            signal.Set();
            notification.TrySetResult(true);
        }

        // Linearizes dispatch admission against stop. A stop after this claim
        // cancels an admitted operation, rather than retroactively undoing it.
        internal bool TryBeginDispatch() => Interlocked.CompareExchange(ref state, 1, 0) == 0;
        public void Dispose() => signal.Dispose();
    }
}
