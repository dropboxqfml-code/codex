using System;
using System.IO;
using ATIVBatteryGuard.WmiAccessCheck;

internal static partial class Program
{
    private static void RegisterWmiAccessCheckCaptureTests()
    {
        Add("WMI helper captures exact bounded Unicode output without changing content", () =>
        {
            string text = "현재 토큰: Unknown\r\nWmiAcpiVersion: AccessDenied\r\n";
            Equal(text, BoundedTextCapture.Read(new StringReader(text)));
            Equal(null, BoundedTextCapture.Read(null));
            Equal(null, BoundedTextCapture.Read(new StringReader("")));
        });
        Add("WMI helper rejects oversized output at its exact character boundary", () =>
        {
            foreach (int length in new[] { BoundedTextCapture.MaximumCharacters - 1, BoundedTextCapture.MaximumCharacters })
            {
                string text = new string('한', length);
                Equal(text, BoundedTextCapture.Read(new StringReader(text)));
            }
            Equal(null, BoundedTextCapture.Read(new StringReader(new string('x', BoundedTextCapture.MaximumCharacters + 1))));
        });
        Add("WMI helper capture handles short reads and refuses unreadable channels", () =>
        {
            const string text = "Active=False\nversion=0x00000000";
            Equal(text, BoundedTextCapture.Read(new ShortTextReader(text)));
            BatteryThrows<IOException>(() => BoundedTextCapture.Read(new BrokenTextReader()));
        });
    }

    private sealed class ShortTextReader : StringReader
    {
        internal ShortTextReader(string text) : base(text) { }
        public override int Read(char[] buffer, int index, int count) => base.Read(buffer, index, Math.Min(count, 3));
    }

    private sealed class BrokenTextReader : TextReader
    {
        public override int Read(char[] buffer, int index, int count) => throw new IOException("private channel");
    }
}
