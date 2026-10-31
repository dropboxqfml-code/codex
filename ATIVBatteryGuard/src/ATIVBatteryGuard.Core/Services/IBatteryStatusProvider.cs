using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
	public interface IBatteryStatusProvider
	{
		BatterySnapshot Read();
	}
}
