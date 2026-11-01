using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;
using System.Xml;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Typed, bounded local IPC. Paths, original bytes and exception text are never fields.
    public static class SamsungFileInspectionProtocol
    {
        public const int MaximumBytes = 2097152;

        [DataContract]
        private sealed class Packet
        {
            [DataMember(IsRequired = true)] public int Version;
            [DataMember(IsRequired = true)] public int Status;
            [DataMember(IsRequired = true)] public bool Limited;
            [DataMember(IsRequired = true)] public int DriverLink;
            [DataMember(IsRequired = true)] public Entry[] Entries;
        }

        [DataContract]
        private sealed class Entry
        {
            [DataMember(IsRequired = true)] public string FileName;
            [DataMember(IsRequired = true)] public string LocationLabel;
            [DataMember(IsRequired = true)] public int Status;
            [DataMember(IsRequired = true)] public long Length;
            [DataMember(IsRequired = true)] public string FileVersion;
            [DataMember(IsRequired = true)] public string ProductVersion;
            [DataMember(IsRequired = true)] public string CompanyName;
            [DataMember(IsRequired = true)] public string Description;
            [DataMember(IsRequired = true)] public string Sha256;
            [DataMember(IsRequired = true)] public int Signature;
            [DataMember(IsRequired = true)] public bool PeValid;
            [DataMember(IsRequired = true)] public bool PeManaged;
            [DataMember(IsRequired = true)] public string PeArchitecture;
            [DataMember(IsRequired = true)] public bool PeLimited;
            [DataMember(IsRequired = true)] public string[] Imports;
            [DataMember(IsRequired = true)] public string[] Exports;
            [DataMember(IsRequired = true)] public ImportFunction[] Functions;
        }

        [DataContract]
        private sealed class ImportFunction
        {
            [DataMember(IsRequired = true)] public string ModuleName;
            [DataMember(IsRequired = true)] public string FunctionName;
            [DataMember(IsRequired = true)] public int? Ordinal;
        }

        private static DataContractJsonSerializer Serializer()
        {
            return new DataContractJsonSerializer(typeof(Packet), new DataContractJsonSerializerSettings { MaxItemsInObjectGraph = 32768 });
        }

        public static byte[] Encode(SamsungFileInspectionReport report)
        {
            if (report == null) throw new ArgumentNullException(nameof(report));
            var source = report.Entries;
            var entries = new Entry[source.Length];
            for (int i = 0; i < source.Length; i++)
            {
                var entry = source[i];
                entries[i] = new Entry
                {
                    FileName = entry.FileName, LocationLabel = entry.LocationLabel, Status = (int)entry.Status,
                    Length = entry.Length, FileVersion = entry.FileVersion, ProductVersion = entry.ProductVersion,
                    CompanyName = entry.CompanyName, Description = entry.Description, Sha256 = entry.Sha256,
                    Signature = (int)entry.Signature, PeValid = entry.Pe.IsValid, PeManaged = entry.Pe.IsManaged,
                    PeArchitecture = entry.Pe.Architecture, PeLimited = !string.IsNullOrEmpty(entry.Pe.Error),
                    Imports = entry.Pe.ImportedModules, Exports = entry.Pe.ExportedNames,
                    Functions = ToWire(entry.Pe.ImportedFunctions)
                };
            }
            using (var output = new MemoryStream())
            {
                Serializer().WriteObject(output, new Packet { Version = 3, Status = (int)report.Status, Limited = report.Limited, DriverLink = (int)report.DriverLink, Entries = entries });
                if (output.Length > MaximumBytes) throw new SerializationException("Result exceeds the size limit.");
                return output.ToArray();
            }
        }

        public static SamsungFileInspectionReport Decode(byte[] bytes)
        {
            if (bytes == null || bytes.Length == 0 || bytes.Length > MaximumBytes) return Invalid();
            try
            {
                if (!HasSingleObjectEnvelope(bytes)) return Invalid();
                Packet packet;
                using (var reader = JsonReaderWriterFactory.CreateJsonReader(bytes, new XmlDictionaryReaderQuotas
                {
                    MaxDepth = 16, MaxStringContentLength = 128, MaxArrayLength = 256,
                    MaxNameTableCharCount = 2048, MaxBytesPerRead = MaximumBytes
                }))
                {
                    packet = (Packet)Serializer().ReadObject(reader);
                    while (reader.Read()) if (reader.NodeType != XmlNodeType.Whitespace) return Invalid();
                }
                if (packet == null || packet.Version != 3 || !Enum.IsDefined(typeof(SabiDriverLinkStatus), packet.DriverLink) || !Enum.IsDefined(typeof(SamsungFileInspectionStatus), packet.Status) ||
                    packet.Entries == null || packet.Entries.Length > SamsungFileInspectionReport.MaximumEntries) return Invalid();
                var entries = new SamsungFileInspectionEntry[packet.Entries.Length];
                for (int i = 0; i < entries.Length; i++)
                {
                    Entry wire = packet.Entries[i];
                    if (!Valid(wire)) return Invalid();
                    entries[i] = new SamsungFileInspectionEntry(wire.FileName, wire.LocationLabel, (SamsungFileEntryStatus)wire.Status,
                        wire.Length, wire.FileVersion, wire.ProductVersion, wire.CompanyName, wire.Description, wire.Sha256,
                        new PeModuleInfo(wire.PeValid, wire.PeManaged, wire.PeArchitecture, wire.Imports, wire.Exports,
                            wire.PeLimited ? "표시 또는 분석 범위가 제한됐습니다." : string.Empty, FromWire(wire.Functions)), (OfflineSignatureStatus)wire.Signature);
                }
                return new SamsungFileInspectionReport((SamsungFileInspectionStatus)packet.Status, entries, packet.Limited, (SabiDriverLinkStatus)packet.DriverLink);
            }
            catch (Exception exception) when (exception is SerializationException || exception is XmlException ||
                exception is ArgumentException || exception is InvalidOperationException || exception is FormatException || exception is OverflowException)
            {
                return Invalid();
            }
        }

        private static bool Valid(Entry entry)
        {
            if (entry == null || SamsungFileInspectionEntry.CanonicalFileName(entry.FileName) == null ||
                !SamsungFileInspectionEntry.IsLocationLabel(entry.LocationLabel) ||
                !Enum.IsDefined(typeof(SamsungFileEntryStatus), entry.Status) ||
                !Enum.IsDefined(typeof(OfflineSignatureStatus), entry.Signature) ||
                !Metadata(entry.FileVersion) || !Metadata(entry.ProductVersion) || !Metadata(entry.CompanyName) || !Metadata(entry.Description) ||
                entry.Sha256 == null || !Names(entry.Imports, 64, true) || !Names(entry.Exports, 128, false) || !ValidFunctions(entry.Functions)) return false;
            if (entry.PeValid)
            {
                if (entry.PeArchitecture != "x86" && entry.PeArchitecture != "x64") return false;
            }
            else if (entry.PeArchitecture != "Unknown" || entry.PeManaged || entry.Imports.Length != 0 || entry.Exports.Length != 0 || entry.Functions.Length != 0) return false;
            if ((SamsungFileEntryStatus)entry.Status == SamsungFileEntryStatus.Inspected)
                return entry.Length > 0 && entry.Length <= SamsungFileInspectionReport.MaximumFileBytes &&
                    SamsungFileInspectionEntry.IsSha256(entry.Sha256) && entry.PeValid;
            // Failure data never carries an earlier successful observation.
            return entry.Length == 0 && entry.FileVersion.Length == 0 && entry.ProductVersion.Length == 0 && entry.CompanyName.Length == 0 &&
                entry.Description.Length == 0 && entry.Sha256.Length == 0 && entry.Signature == (int)OfflineSignatureStatus.NotChecked &&
                !entry.PeValid && !entry.PeLimited;
        }

        private static bool Metadata(string value)
        {
            return value != null && value == SamsungFileInspectionEntry.CleanMetadata(value);
        }

        private static ImportFunction[] ToWire(PeImportedFunction[] source)
        {
            var result = new ImportFunction[source.Length];
            for (int i = 0; i < source.Length; i++) result[i] = new ImportFunction {
                ModuleName = source[i].ModuleName, FunctionName = source[i].FunctionName, Ordinal = source[i].Ordinal };
            return result;
        }

        private static PeImportedFunction[] FromWire(ImportFunction[] source)
        {
            var result = new PeImportedFunction[source.Length];
            for (int i = 0; i < source.Length; i++) result[i] = new PeImportedFunction(source[i].ModuleName, source[i].FunctionName, source[i].Ordinal);
            return result;
        }

        private static bool ValidFunctions(ImportFunction[] functions)
        {
            if (functions == null || functions.Length > PeModuleInfo.MaximumImportedFunctions) return false;
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (var f in functions)
            {
                if (f == null || !PeModuleInfo.IsSafeName(f.ModuleName, true) || f.FunctionName == null) return false;
                if (f.Ordinal.HasValue)
                {
                    if (f.Ordinal.Value < 0 || f.Ordinal.Value > 65535 || f.FunctionName.Length != 0) return false;
                }
                else if (!PeModuleInfo.IsSafeName(f.FunctionName, false)) return false;
                if (!seen.Add(f.ModuleName.ToUpperInvariant() + "!" + (f.Ordinal.HasValue ? "#" + f.Ordinal.Value : f.FunctionName))) return false;
            }
            return true;
        }

        private static bool Names(string[] values, int maximum, bool module)
        {
            if (values == null || values.Length > maximum) return false;
            var unique = new HashSet<string>(module ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal);
            foreach (string value in values)
                if (!PeModuleInfo.IsSafeName(value, module) || !unique.Add(value)) return false;
            return true;
        }

        private static SamsungFileInspectionReport Invalid() => new SamsungFileInspectionReport(SamsungFileInspectionStatus.InvalidResponse);

        // The JSON reader alone can accept the first object and ignore trailing JSON.
        private static bool HasSingleObjectEnvelope(byte[] bytes)
        {
            string text = new UTF8Encoding(false, true).GetString(bytes);
            int start = 0;
            while (start < text.Length && JsonSpace(text[start])) start++;
            if (start == text.Length || text[start] != '{') return false;
            var stack = new char[16];
            int depth = 0;
            int stringLength = 0, unicodeDigits = 0;
            bool quoted = false, escaped = false;
            for (int i = start; i < text.Length; i++)
            {
                char value = text[i];
                if (quoted)
                {
                    if (unicodeDigits != 0)
                    {
                        if (!HexDigit(value)) return false;
                        unicodeDigits--;
                        continue;
                    }
                    if (escaped)
                    {
                        escaped = false;
                        if (value == 'u') unicodeDigits = 4;
                        else if ("\"\\/bfnrt".IndexOf(value) < 0) return false;
                        if (++stringLength > 128) return false;
                        continue;
                    }
                    if (value == '\\') escaped = true;
                    else if (value == '"') quoted = false;
                    else if (value < 0x20) return false;
                    else if (++stringLength > 128) return false;
                    continue;
                }
                if (value == '"') { quoted = true; stringLength = 0; continue; }
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
        private static bool HexDigit(char value) => (value >= '0' && value <= '9') || (value >= 'a' && value <= 'f') || (value >= 'A' && value <= 'F');
    }
}
