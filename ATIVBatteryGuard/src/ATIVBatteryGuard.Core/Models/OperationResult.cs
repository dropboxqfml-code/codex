namespace ATIVBatteryGuard.Core.Models
{
	public sealed class OperationResult
	{
		public bool Success { get; private set; }

		public string Message { get; private set; }

		public OperationResult(bool success, string message)
		{
			Success = success;
			Message = message ?? string.Empty;
		}
	}
}
