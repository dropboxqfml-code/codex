using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
	public interface IHardwareDiagnosticsProvider
	{
		HardwareProbeReport Collect();
	}
}
