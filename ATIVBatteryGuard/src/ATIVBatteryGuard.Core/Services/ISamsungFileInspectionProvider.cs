using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    public interface ISamsungFileInspectionProvider
    {
        SamsungFileInspectionReport Collect();
    }
}
