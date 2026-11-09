using System;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    public interface IManualProtectionOperationService
    {
        bool IsBlocked { get; }
        Task<ManualProtectionResult> RunAsync(ManualProtectionOperation operation, Action<ManualProtectionPhase> progress);
    }
}
