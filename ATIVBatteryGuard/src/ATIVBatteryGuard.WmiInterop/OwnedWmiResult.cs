using System;
using System.Management;
using System.Threading;

namespace ATIVBatteryGuard.WmiInterop
{
    // Canonical per raw wrapper within one binding, not native COM identity.
    // The generic source owns this explicit IDisposable implementation.
    internal sealed class OwnedWmiResult : IDisposable
    {
        private ManagementBaseObject value;
        internal OwnedWmiResult(ManagementBaseObject value) { this.value = value; }
        internal byte[] Read() => WsabiWmiWindowsOutputReader.Read(value);

        public void Dispose()
        {
            ManagementBaseObject owned = Interlocked.Exchange(ref value, null);
            // This is a concrete call even if the SDK type inherits a
            // different IDisposable implementation from Component.
            if (owned != null) owned.Dispose();
        }
    }
}
