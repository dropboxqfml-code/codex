using System.IO;
using System.Text;

namespace ATIVBatteryGuard.WmiAccessCheck
{
    // The parent accepts at most one small result; paths and commands are not inputs.
    internal static class BoundedTextCapture
    {
        internal const int MaximumCharacters = 32768;

        internal static string Read(TextReader input)
        {
            if (input == null) return null;
            var text = new StringBuilder();
            var buffer = new char[512];
            int count;
            while ((count = input.Read(buffer, 0, buffer.Length)) != 0)
            {
                if (count < 0 || text.Length > MaximumCharacters - count) return null;
                text.Append(buffer, 0, count);
            }
            return text.Length == 0 ? null : text.ToString();
        }
    }
}
