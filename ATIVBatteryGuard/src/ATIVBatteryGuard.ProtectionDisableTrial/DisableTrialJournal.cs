using System;
using System.IO;
using System.Text;
using ATIVBatteryGuard.Core.Storage;

namespace ATIVBatteryGuard.ProtectionDisableTrial
{
    // Only fixed text, enums and bounded numeric candidates reach this writer.
    // No exception, SDK object, identifier, frame or comparison is formatted.
    internal sealed class DisableTrialJournal : IDisposable
    {
        private readonly object gate = new object();
        private readonly TextWriter writer;
        private readonly Action<string> display;
        internal bool WriteFailed { get; private set; }
        internal DisableTrialJournal(TextWriter writer, Action<string> display)
        { this.writer = writer; this.display = display; }

        internal static DisableTrialJournal TryCreate(string directory)
        {
            FileStream stream = null;
            try
            {
                string local = LocalPathPolicy.NormalizeDirectory(directory);
                LocalPathPolicy.EnsureNoReparsePoints(local);
                string name = "protection-1to0-result-" + DateTime.UtcNow.ToString("yyyyMMddTHHmmssfff",
                    System.Globalization.CultureInfo.InvariantCulture) + ".txt";
                string path = Path.Combine(local, name);
                LocalPathPolicy.EnsureNoReparsePoints(path);
                stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read);
                return new DisableTrialJournal(new StreamWriter(stream, new UTF8Encoding(false)), Console.WriteLine);
            }
            catch
            {
                try { if (stream != null) stream.Dispose(); } catch { }
                return null;
            }
        }

        internal void Write(string line)
        {
            lock (gate)
            {
                try { display(line); } catch { }
                if (WriteFailed) return;
                try { writer.WriteLine(line); writer.Flush(); }
                catch { WriteFailed = true; }
            }
        }
        public void Dispose()
        { lock (gate) { try { writer.Dispose(); } catch { WriteFailed = true; } } }
    }
}
