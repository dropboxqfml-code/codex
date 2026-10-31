using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Hardware
{
	public sealed class MockChargeLimitController : IChargeLimitController
	{
		private readonly object sync = new object();

		private ChargeMode currentMode = ChargeMode.Normal100;

		public ChargeCapabilities GetCapabilities()
		{
			return new ChargeCapabilities(canRead: true, canWrite: true, "시뮬레이션 — 실제 충전 제어 없음. 상태는 메모리에서만 변경됩니다.");
		}

		public ChargeMode GetCurrentMode()
		{
			lock (sync)
			{
				return currentMode;
			}
		}

		public OperationResult SetMode(ChargeMode mode)
		{
			if (mode != ChargeMode.Normal100 && mode != ChargeMode.Protection80)
			{
				return new OperationResult(success: false, "지원하지 않는 시뮬레이션 모드입니다.");
			}
			lock (sync)
			{
				currentMode = mode;
			}
			return new OperationResult(success: true, "모의 상태가 변경되었습니다. 실제 충전 제어는 수행하지 않았습니다.");
		}
	}
}
