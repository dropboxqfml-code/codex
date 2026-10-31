using System;
using System.IO;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;
using System.Xml;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Local worker protocol: only bounded indices, status codes, and capability
    // bits. Never carries a device path, tag, serial number, or exception text.
    public static class BatteryCapabilitiesProtocol
    {
        public const int MaximumBytes = 16384;

        [DataContract]
        private sealed class Packet
        {
            [DataMember(IsRequired = true)] public int Version;
            [DataMember(IsRequired = true)] public int Status;
            [DataMember(IsRequired = true)] public bool Limited;
            [DataMember(IsRequired = true)] public Entry[] Entries;
        }
        [DataContract]
        private sealed class Entry
        {
            [DataMember(IsRequired = true)] public int Index;
            [DataMember(IsRequired = true)] public int Status;
            [DataMember(IsRequired = true)] public uint? Flags;
        }

        private static DataContractJsonSerializer Serializer()
        {
            return new DataContractJsonSerializer(typeof(Packet), new DataContractJsonSerializerSettings { MaxItemsInObjectGraph = 128 });
        }

        public static byte[] Encode(WindowsBatteryCapabilitiesReport report)
        {
            if (report == null) throw new ArgumentNullException(nameof(report));
            var entries = report.Entries;
            var wire = new Entry[entries.Length];
            for (int i = 0; i < entries.Length; i++)
                wire[i] = new Entry { Index = entries[i].Index, Status = (int)entries[i].Status, Flags = entries[i].Capabilities };
            using (var output = new MemoryStream())
            {
                Serializer().WriteObject(output, new Packet { Version = 1, Status = (int)report.Status, Limited = report.Limited, Entries = wire });
                if (output.Length > MaximumBytes) throw new SerializationException("Result exceeds the size limit.");
                return output.ToArray();
            }
        }

        public static WindowsBatteryCapabilitiesReport Decode(byte[] bytes)
        {
            if (bytes == null || bytes.Length == 0 || bytes.Length > MaximumBytes) return Invalid();
            try
            {
                if (!HasSingleObjectEnvelope(bytes)) return Invalid();
                Packet packet;
                using (var reader = JsonReaderWriterFactory.CreateJsonReader(bytes, new XmlDictionaryReaderQuotas
                {
                    MaxDepth = 16, MaxStringContentLength = 512,
                    MaxArrayLength = WindowsBatteryCapabilitiesReport.MaximumDevices,
                    MaxNameTableCharCount = 1024, MaxBytesPerRead = MaximumBytes
                }))
                {
                    packet = (Packet)Serializer().ReadObject(reader);
                    // ReadObject alone can accept an initial JSON object while
                    // ignoring trailing data. Require the entire input to end.
                    while (reader.Read()) if (reader.NodeType != XmlNodeType.Whitespace) return Invalid();
                }
                if (packet == null || packet.Version != 1 || !Enum.IsDefined(typeof(BatteryProbeStatus), packet.Status) ||
                    packet.Entries == null || packet.Entries.Length > WindowsBatteryCapabilitiesReport.MaximumDevices) return Invalid();
                var entries = new BatteryCapabilityEntry[packet.Entries.Length];
                for (int i = 0; i < entries.Length; i++)
                {
                    Entry wire = packet.Entries[i];
                    if (wire == null || !Enum.IsDefined(typeof(BatteryProbeStatus), wire.Status)) return Invalid();
                    entries[i] = new BatteryCapabilityEntry(wire.Index, (BatteryProbeStatus)wire.Status, wire.Flags);
                }
                return new WindowsBatteryCapabilitiesReport((BatteryProbeStatus)packet.Status, entries, packet.Limited);
            }
            catch (Exception exception) when (exception is SerializationException || exception is XmlException ||
                exception is ArgumentException || exception is InvalidOperationException || exception is FormatException)
            {
                return Invalid();
            }
        }

        private static WindowsBatteryCapabilitiesReport Invalid() => new WindowsBatteryCapabilitiesReport(BatteryProbeStatus.InvalidResponse);

        // DataContractJsonSerializer/JsonReader may ignore a second root object.
        // Check framing here; the framework serializer still validates grammar
        // and schema. Braces in strings and escaped quotes do not end the root.
        private static bool HasSingleObjectEnvelope(byte[] bytes)
        {
            string text = new UTF8Encoding(false, true).GetString(bytes);
            int start = 0;
            while (start < text.Length && JsonSpace(text[start])) start++;
            if (start == text.Length || text[start] != '{') return false;
            var stack = new char[16];
            int depth = 0;
            bool quoted = false, escaped = false;
            for (int i = start; i < text.Length; i++)
            {
                char value = text[i];
                if (quoted)
                {
                    if (escaped) { escaped = false; continue; }
                    if (value == '\\') escaped = true;
                    else if (value == '"') quoted = false;
                    else if (value < 0x20) return false;
                    continue;
                }
                if (value == '"') { quoted = true; continue; }
                if (value == '{' || value == '[')
                {
                    if (depth == stack.Length) return false;
                    stack[depth++] = value;
                }
                else if (value == '}' || value == ']')
                {
                    if (depth == 0 || stack[depth - 1] != (value == '}' ? '{' : '[')) return false;
                    if (--depth != 0) continue;
                    for (int tail = i + 1; tail < text.Length; tail++) if (!JsonSpace(text[tail])) return false;
                    return true;
                }
            }
            return false;
        }

        private static bool JsonSpace(char value) => value == ' ' || value == '\t' || value == '\r' || value == '\n';
    }
}
