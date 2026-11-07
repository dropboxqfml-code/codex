using System;
using System.Management;

namespace ATIVBatteryGuard.WmiInterop
{
    // Reads a supplied result only. No query, Get, connection, method call or
    // default endpoint exists here. The outer object is borrowed from the
    // source; a distinct embedded wrapper returned by Value is locally owned.
    public static class WsabiWmiWindowsOutputReader
    {
        private const int MaximumCaptureBytes = 4096;

        public static byte[] Read(ManagementBaseObject result)
            => Read(result, null);

        internal static byte[] Read(ManagementBaseObject result, WsabiWmiWindowsOwnedInputPair protectedInputs)
        {
            ManagementBaseObject embedded = null;
            bool ownsEmbedded = false;
            try
            {
                if (result == null || (protectedInputs != null && protectedInputs.Contains(result))) throw Failure();
                PropertyData output = result.Properties["outData"];
                if (output == null || output.Type != CimType.Object || output.IsArray) throw Failure();
                embedded = output.Value as ManagementBaseObject;
                // The borrowed root and protected inputs keep their own
                // ownership. Reject before any embedded metadata or Dispose.
                if (embedded == null || ReferenceEquals(embedded, result) ||
                    (protectedInputs != null && protectedInputs.Contains(embedded))) throw Failure();
                ownsEmbedded = true;
                if (!string.Equals(embedded.ClassPath.ClassName, "DataBuffer", StringComparison.OrdinalIgnoreCase))
                    throw Failure();
                PropertyData property = embedded.Properties["Bytes"];
                if (property == null || property.Type != CimType.UInt8 || !property.IsArray) throw Failure();
                // CLR casts can treat some primitive arrays as compatible.
                // Require exact runtime byte[] as well as the CIM declaration.
                object value = property.Value;
                if (value == null || value.GetType() != typeof(byte[])) throw Failure();
                byte[] bytes = (byte[])value;
                if (bytes.Length > MaximumCaptureBytes) throw Failure();
                return (byte[])bytes.Clone();
            }
            catch { throw Failure(); }
            finally
            {
                if (ownsEmbedded)
                {
                    // ManagementBaseObject hides Component.Dispose. Resolve
                    // its concrete method, not the inherited IDisposable map.
                    try { embedded.Dispose(); }
                    catch { throw Failure(); }
                }
            }
        }

        private static InvalidOperationException Failure()
            => new InvalidOperationException("The supplied WMI output did not have a supported detached form.");
    }
}
