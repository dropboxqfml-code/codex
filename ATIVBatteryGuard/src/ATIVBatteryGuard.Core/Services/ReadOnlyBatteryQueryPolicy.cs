using System;

namespace ATIVBatteryGuard.Core.Services
{
    public enum ReadOnlyBatteryQuery { Tag, Information }

    public static class ReadOnlyBatteryQueryPolicy
    {
        // Microsoft Windows SDK shared/poclass.h: FILE_DEVICE_BATTERY 0x29,
        // METHOD_BUFFERED 0, FILE_READ_ACCESS 1. No SET code is exposed here.
        public static uint Code(ReadOnlyBatteryQuery query)
        {
            switch (query)
            {
                case ReadOnlyBatteryQuery.Tag: return 0x00294040;
                case ReadOnlyBatteryQuery.Information: return 0x00294044;
                default: throw new ArgumentOutOfRangeException(nameof(query));
            }
        }

        public static byte[] InformationRequest(uint tag)
        {
            if (tag == 0) throw new ArgumentOutOfRangeException(nameof(tag));
            var bytes = new byte[12];
            for (int i = 0; i < 4; i++) bytes[i] = (byte)(tag >> (8 * i));
            // InformationLevel = BatteryInformation (0), AtRate = 0.
            return bytes;
        }

        public static bool TryCapabilities(byte[] response, uint returnedBytes, out uint capabilities)
        {
            capabilities = 0;
            if (response == null || response.Length != 36 || returnedBytes != 36) return false;
            capabilities = UInt32(response);
            return true;
        }

        public static uint UInt32(byte[] bytes)
        {
            if (bytes == null || bytes.Length < 4) throw new ArgumentException("Four bytes are required.");
            return (uint)bytes[0] | ((uint)bytes[1] << 8) | ((uint)bytes[2] << 16) | ((uint)bytes[3] << 24);
        }
    }
}
