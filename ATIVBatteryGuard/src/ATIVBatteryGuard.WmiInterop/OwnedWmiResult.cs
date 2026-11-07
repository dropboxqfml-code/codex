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
        private readonly WsabiWmiWindowsOwnedInputPair protectedInputs;
        internal OwnedWmiResult(ManagementBaseObject value, WsabiWmiWindowsOwnedInputPair protectedInputs = null)
        {
            this.value = value;
            this.protectedInputs = protectedInputs;
        }
        internal byte[] Read() => WsabiWmiWindowsOutputReader.Read(value, protectedInputs);

        public void Dispose()
        {
            ManagementBaseObject owned = Interlocked.Exchange(ref value, null);
            // This is a concrete call even if the SDK type inherits a
            // different IDisposable implementation from Component.
            if (owned != null && !(protectedInputs != null && protectedInputs.Contains(owned))) owned.Dispose();
        }
    }
}
