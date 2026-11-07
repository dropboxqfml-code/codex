using System;
using System.Management;
using System.Threading.Tasks;

namespace ATIVBatteryGuard.WmiInterop
{
    // Ownership starts at the common input registry's atomic pair claim. This
    // holder has no public Dispose/SDK-object accessor that could bypass join.
    internal sealed class WsabiWmiWindowsOwnedInputPair
    {
        private readonly object gate = new object();
        private readonly WeakReference<ManagementBaseObject> inputIdentity, bufferIdentity;
        private ManagementBaseObject parameters, buffer;
        private Task<WsabiWmiWindowsCleanupStatus> release;

        internal WsabiWmiWindowsOwnedInputPair(ManagementBaseObject parameters, ManagementBaseObject buffer)
        {
            this.parameters = parameters; this.buffer = buffer;
            inputIdentity = new WeakReference<ManagementBaseObject>(parameters);
            bufferIdentity = new WeakReference<ManagementBaseObject>(buffer);
        }

        // Retain weak identities after release so a queued exact managed alias
        // cannot be disposed a second time by output cleanup. Not COM identity.
        internal bool Contains(ManagementBaseObject value)
        {
            if (value == null) return false;
            ManagementBaseObject known;
            return (inputIdentity.TryGetTarget(out known) && ReferenceEquals(value, known)) ||
                (bufferIdentity.TryGetTarget(out known) && ReferenceEquals(value, known));
        }

        internal Task<WsabiWmiWindowsCleanupStatus> ReleaseAsync()
        {
            lock (gate)
            {
                if (release == null) release = Task.Run(() =>
                {
                    bool failed = false;
                    // Concrete SDK Dispose, not Component's IDisposable map.
                    // Even a mutating/throwing first Dispose cannot skip second.
                    try { parameters.Dispose(); } catch { failed = true; }
                    try { buffer.Dispose(); } catch { failed = true; }
                    parameters = null; buffer = null;
                    return failed ? WsabiWmiWindowsCleanupStatus.Failed : WsabiWmiWindowsCleanupStatus.Complete;
                });
                return release;
            }
        }
    }
}
