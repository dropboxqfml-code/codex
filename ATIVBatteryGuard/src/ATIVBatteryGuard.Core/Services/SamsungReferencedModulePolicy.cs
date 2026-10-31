using System;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
	public static class SamsungReferencedModulePolicy
	{
		public const string KnownParentFileName = "SamsungConfigurationMonitor.exe";

		public const string KnownParentSha256 = "8a0d87b214623f424b7f493034bca3271e35fc4376bbfa3f72a1491d33b72281";

		public const string TargetFileName = "wsabi.dll";

		private const int MaximumFileBytes = 16777216;

		public static bool IsConfirmedParent(string parentFileName, string parentSha256)
		{
			if (string.Equals(parentFileName, "SamsungConfigurationMonitor.exe", StringComparison.OrdinalIgnoreCase))
			{
				return string.Equals(parentSha256, "8a0d87b214623f424b7f493034bca3271e35fc4376bbfa3f72a1491d33b72281", StringComparison.OrdinalIgnoreCase);
			}
			return false;
		}

		public static ReferencedModuleDecision Evaluate(string parentFileName, string parentSha256, string targetFileName, byte[] bytes)
		{
			if (!string.Equals(parentFileName, "SamsungConfigurationMonitor.exe", StringComparison.OrdinalIgnoreCase))
			{
				return Reject("REFERENCE_PARENT_NOT_ALLOWED");
			}
			if (!IsConfirmedParent(parentFileName, parentSha256))
			{
				return Reject("REFERENCE_PARENT_HASH_MISMATCH");
			}
			if (!string.Equals(targetFileName, "wsabi.dll", StringComparison.OrdinalIgnoreCase))
			{
				return Reject("REFERENCE_TARGET_NOT_ALLOWED");
			}
			if (bytes == null || bytes.Length == 0)
			{
				return Reject("REFERENCE_FILE_MISSING");
			}
			if (bytes.Length > 16777216)
			{
				return Reject("REFERENCE_FILE_TOO_LARGE");
			}
			if (!TryBasicHeader(bytes, out var architecture))
			{
				return Reject("REFERENCE_BASIC_PE_REJECTED");
			}
			PeModuleInfo peModuleInfo = PeModuleReader.Read(bytes);
			return new ReferencedModuleDecision(allowed: true, peModuleInfo.IsValid ? "COPY_AS_DATA" : "COPY_AS_DATA_WITH_INCOMPLETE_METADATA", architecture, peModuleInfo, peModuleInfo.IsValid);
		}

		private static ReferencedModuleDecision Reject(string reason)
		{
			return new ReferencedModuleDecision(allowed: false, reason, "Unknown", null, detailedMetadataAvailable: false);
		}

		private static bool TryBasicHeader(byte[] data, out string architecture)
		{
			architecture = "Unknown";
			if (!Contains(data, 0L, 64L) || U16(data, 0L) != 23117)
			{
				return false;
			}
			long num = U32(data, 60L);
			if (num < 64 || num > 1048576 || !Contains(data, num, 24L) || U32(data, num) != 17744)
			{
				return false;
			}
			long num2 = num + 4;
			ushort num3 = U16(data, num2);
			bool flag = num3 == 34404;
			if (num3 != 332 && !flag)
			{
				return false;
			}
			if ((U16(data, num2 + 18) & 2) == 0)
			{
				return false;
			}
			int num4 = U16(data, num2 + 2);
			int num5 = U16(data, num2 + 16);
			long num6 = num2 + 20;
			if (num4 < 1 || num4 > 96 || num5 < (flag ? 112 : 96) || !Contains(data, num6, num5) || U16(data, num6) != (flag ? 523 : 267))
			{
				return false;
			}
			long num7 = num6 + num5;
			long num8 = num7 + (long)num4 * 40L;
			uint num9 = U32(data, num6 + 60);
			if (!Contains(data, num7, (long)num4 * 40L) || num9 < num8 || num9 > data.Length)
			{
				return false;
			}
			for (int i = 0; i < num4; i++)
			{
				long num10 = num7 + (long)i * 40L;
				uint num11 = U32(data, num10 + 8);
				uint num12 = U32(data, num10 + 12);
				uint num13 = U32(data, num10 + 16);
				uint num14 = U32(data, num10 + 20);
				if (num12 == 0 || num12 + Math.Max((ulong)num11, (ulong)num13) > 4294967296L)
				{
					return false;
				}
				if (num13 != 0 && (num14 < num9 || !Contains(data, num14, num13)))
				{
					return false;
				}
			}
			architecture = (flag ? "x64" : "x86");
			return true;
		}

		private static bool Contains(byte[] data, long offset, long size)
		{
			if (offset >= 0 && size >= 0 && size <= data.Length)
			{
				return offset <= data.Length - size;
			}
			return false;
		}

		private static ushort U16(byte[] data, long offset)
		{
			int num = (int)offset;
			return (ushort)(data[num] | (data[num + 1] << 8));
		}

		private static uint U32(byte[] data, long offset)
		{
			int num = (int)offset;
			return (uint)(data[num] | (data[num + 1] << 8) | (data[num + 2] << 16) | (data[num + 3] << 24));
		}
	}
}
