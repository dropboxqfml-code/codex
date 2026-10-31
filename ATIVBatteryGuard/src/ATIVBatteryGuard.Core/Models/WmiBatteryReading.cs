namespace ATIVBatteryGuard.Core.Models
{
	public sealed class WmiBatteryReading
	{
		public int? EstimatedChargeRemaining { get; private set; }

		public int? BatteryStatus { get; private set; }

		public WmiBatteryReading(int? estimatedChargeRemaining, int? batteryStatus)
		{
			EstimatedChargeRemaining = ((estimatedChargeRemaining.HasValue && estimatedChargeRemaining.Value >= 0 && estimatedChargeRemaining.Value <= 100) ? estimatedChargeRemaining : ((int?)null));
			BatteryStatus = ((batteryStatus.HasValue && batteryStatus.Value >= 0 && batteryStatus.Value <= 65535) ? batteryStatus : ((int?)null));
		}
	}
}
