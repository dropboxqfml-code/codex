using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Hardware
{
	public sealed class UnsupportedChargeLimitController : IChargeLimitController
	{
		public ChargeCapabilities GetCapabilities()
		{
			return new ChargeCapabilities(canRead: false, canWrite: false, "검증된 삼성 충전 제어 인터페이스가 없습니다. 실제 충전 제한은 지원하지 않습니다.");
		}

		public ChargeMode GetCurrentMode()
		{
			return ChargeMode.Unsupported;
		}

		public OperationResult SetMode(ChargeMode mode)
		{
			return new OperationResult(success: false, "하드웨어 쓰기가 차단되었습니다. 사용자 희망 설정만 저장할 수 있습니다.");
		}
	}
}
