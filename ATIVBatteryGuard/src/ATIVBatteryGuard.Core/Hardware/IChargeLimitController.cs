using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Hardware
{
	public interface IChargeLimitController
	{
		ChargeCapabilities GetCapabilities();

		ChargeMode GetCurrentMode();

		OperationResult SetMode(ChargeMode mode);
	}
}
