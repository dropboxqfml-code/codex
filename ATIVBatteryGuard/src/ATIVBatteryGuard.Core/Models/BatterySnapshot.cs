namespace ATIVBatteryGuard.Core.Models
{
	public sealed class BatterySnapshot
	{
		public int? Percent { get; private set; }

		public ExternalPowerStatus ExternalPower { get; private set; }

		public BatteryChargeState ChargeState { get; private set; }

		public string Error { get; private set; }

		public BatterySnapshot(int? percent, ExternalPowerStatus externalPower, BatteryChargeState chargeState, string error)
		{
			Percent = ((percent.HasValue && percent.Value >= 0 && percent.Value <= 100) ? percent : ((int?)null));
			ExternalPower = externalPower;
			ChargeState = chargeState;
			Error = error ?? string.Empty;
		}

		public static BatterySnapshot Unknown(string error)
		{
			return new BatterySnapshot(null, ExternalPowerStatus.Unknown, BatteryChargeState.Unknown, error);
		}
	}
}
