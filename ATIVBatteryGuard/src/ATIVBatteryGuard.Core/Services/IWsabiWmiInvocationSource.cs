using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Explicitly supplied, prepared single-invocation boundary. No SDK/native
    // implementation, target selection, default source or app registration is
    // supplied here. Invoke returning or throwing is not method completion.
    public interface IWsabiWmiInvocationSource
    {
        void Invoke(WsabiWmiMethodRequest request, IWsabiWmiInvocationObserver observer);
    }

    // Reports facts for this invocation only. The source must establish that a
    // terminal status applies to the method (not merely client cancellation).
    // Capture settlement means all selected capture access has ended. Bytes
    // must already be detached and must not be mutated during the report.
    // These short Try-report methods do not execute source code under a lock.
    public interface IWsabiWmiInvocationObserver
    {
        bool IsStopRequested { get; }
        // Zero is the source-reported successful terminal status. A nonzero
        // status does not authorize reading or retaining output bytes.
        bool ReportTerminal(int status);
        // After terminal only. At status zero, clone at most 4096 bytes;
        // null/oversized data settles as capture failure. At nonzero status,
        // ignore the bytes entirely (null is suitable for unneeded output).
        bool SettleCapture(byte[] detachedBytes);
        // The selected capture access has ended without a usable result.
        // Failure does not end the invocation while other evidence is missing.
        bool FailCapture();
    }
}
