namespace ATIVBatteryGuard.Core.Hardware
{
	public sealed class ChargeCapabilities
	{
		public bool CanRead { get; private set; }

		public bool CanWrite { get; private set; }

		public string Reason { get; private set; }

		public ChargeCapabilities(bool canRead, bool canWrite, string reason)
		{
			CanRead = canRead;
			CanWrite = canWrite;
			Reason = reason ?? string.Empty;
		}
	}
}
