using System;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Security.Cryptography;
using System.Text;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Core.Storage
{
    // One bounded JSON document. No archive entry or imported path is ever extracted.
    public sealed class ObservationBundle
    {
        public const int MaximumBytes = 2 * 1024 * 1024;
        public const string Extension = ".ativrecord";
        private const string Format = "ATIVBatteryGuard.ObservationBundle";
        private static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);
        public SavedBatteryObservation Observation { get; }
        public string NoteText { get; }

        [DataContract]
        private sealed class Document
        {
            [DataMember(IsRequired = true)] public string Format;
            [DataMember(IsRequired = true)] public int Version;
            [DataMember(IsRequired = true)] public string ObservationFileName;
            [DataMember(IsRequired = true)] public string ObservationText;
            [DataMember(IsRequired = true)] public string ObservationSha256;
            [DataMember(IsRequired = true)] public string NoteText;
            [DataMember(IsRequired = true)] public string NoteSha256;
        }

        private ObservationBundle(SavedBatteryObservation observation, string note)
        { Observation = observation; NoteText = note; }

        private static string Hash(string text)
        {
            using (var hash = SHA256.Create())
                return BitConverter.ToString(hash.ComputeHash(Utf8.GetBytes(text))).Replace("-", "").ToLowerInvariant();
        }

        public static ObservationBundle Create(SavedBatteryObservation record, string note)
        {
            note = ObservationNote.Normalize(note);
            if (record == null || !record.Success || !ObservationNoteStore.IsValidText(note))
                throw new InvalidDataException("유효한 관찰 TXT와 최대 1000자의 일반 텍스트 메모가 필요합니다.");
            // Retain the exact validated text snapshot, independent of subsequent source-file edits.
            return new ObservationBundle(SavedBatteryObservation.Parse(record.Text,
                IsValidFileName(record.FileName) ? record.FileName : "observation.txt"), note);
        }

        public byte[] ToBytes()
        {
            using (var output = new MemoryStream())
            {
                new DataContractJsonSerializer(typeof(Document)).WriteObject(output, new Document
                {
                    Format = Format, Version = 1, ObservationFileName = Observation.FileName, ObservationText = Observation.Text,
                    ObservationSha256 = Hash(Observation.Text), NoteText = NoteText, NoteSha256 = Hash(NoteText)
                });
                if (output.Length > MaximumBytes) throw new InvalidDataException("묶음 파일의 최대 크기는 2 MiB입니다.");
                return output.ToArray();
            }
        }

        public static ObservationBundle Read(Stream input)
        {
            if (input == null) throw new ArgumentNullException(nameof(input));
            try
            {
                using (var bytes = new MemoryStream())
                {
                    var buffer = new byte[4096]; int count;
                    while ((count = input.Read(buffer, 0, Math.Min(buffer.Length, MaximumBytes + 1 - (int)bytes.Length))) != 0)
                    {
                        bytes.Write(buffer, 0, count);
                        if (bytes.Length > MaximumBytes) throw new InvalidDataException();
                    }
                    // Reject invalid UTF-8 before the JSON reader can substitute replacement characters.
                    EnsureSingleObject(Utf8.GetString(bytes.ToArray()));
                    bytes.Position = 0;
                    Document document;
                    using (var reader = JsonReaderWriterFactory.CreateJsonReader(bytes, new System.Xml.XmlDictionaryReaderQuotas
                    { MaxDepth = 8, MaxStringContentLength = MaximumBytes, MaxArrayLength = MaximumBytes,
                        MaxBytesPerRead = 4096, MaxNameTableCharCount = 4096 }))
                    {
                        document = (Document)new DataContractJsonSerializer(typeof(Document),
                            new DataContractJsonSerializerSettings { MaxItemsInObjectGraph = 32 }).ReadObject(reader);
                        if (reader.Read()) throw new InvalidDataException();
                    }
                    if (document == null || document.Format != Format || document.Version != 1
                        || !IsValidFileName(document.ObservationFileName) || document.ObservationText == null || !ObservationNoteStore.IsValidText(document.NoteText)
                        || document.NoteText != ObservationNote.Normalize(document.NoteText)
                        || !ObservationNoteStore.IsValidKey(document.ObservationSha256)
                        || !ObservationNoteStore.IsValidKey(document.NoteSha256)
                        || document.ObservationSha256 != Hash(document.ObservationText)
                        || document.NoteSha256 != Hash(document.NoteText)) throw new InvalidDataException();
                    var record = SavedBatteryObservation.Parse(document.ObservationText, document.ObservationFileName);
                    if (!record.Success) throw new InvalidDataException();
                    return new ObservationBundle(record, document.NoteText);
                }
            }
            catch (Exception ex) when (ex is SerializationException || ex is System.Xml.XmlException
                || ex is ArgumentException || ex is InvalidDataException || ex is FormatException)
            { throw new InvalidDataException("묶음 파일의 형식·버전·크기·내용 검증에 실패했습니다. 원본 .ativrecord 파일을 확인하세요."); }
        }

        // The framework JSON reader can stop at the root and ignore trailing documents.
        // Check its envelope before deserialization, tracking quoted/escaped braces.
        private static void EnsureSingleObject(string json)
        {
            int start = 0;
            while (start < json.Length && IsJsonSpace(json[start])) start++;
            if (start == json.Length || json[start] != '{') throw new InvalidDataException();
            int depth = 0; bool quoted = false, escaped = false;
            for (int i = start; i < json.Length; i++)
            {
                char c = json[i];
                if (quoted)
                {
                    if (escaped) escaped = false;
                    else if (c == '\\') escaped = true;
                    else if (c == '\"') quoted = false;
                    continue;
                }
                if (c == '\"') quoted = true;
                else if (c == '{' || c == '[') { if (++depth > 8) throw new InvalidDataException(); }
                else if (c == '}' || c == ']')
                {
                    if (--depth == 0)
                    {
                        for (int j = i + 1; j < json.Length; j++) if (!IsJsonSpace(json[j])) throw new InvalidDataException();
                        return;
                    }
                }
            }
            throw new InvalidDataException();
        }

        private static bool IsJsonSpace(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }

        private static bool IsValidFileName(string name)
        {
            if (string.IsNullOrWhiteSpace(name) || name.Length > 255 || !name.EndsWith(".txt", StringComparison.OrdinalIgnoreCase)
                || name.Any(c => char.IsControl(c) || "<>:\"/\\|?*".IndexOf(c) >= 0)) return false;
            try { Utf8.GetByteCount(name); } catch (EncoderFallbackException) { return false; }
            string stem = name.Split('.')[0].TrimEnd(' ');
            return stem.Length != 0 && !new[] { "CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$" }
                .Concat(Enumerable.Range(1, 9).SelectMany(i => new[] { "COM" + i, "LPT" + i }))
                .Any(reserved => string.Equals(reserved, stem, StringComparison.OrdinalIgnoreCase));
        }

        public static ObservationBundle ReadFile(string path)
        {
            ValidateLocalFile(path);
            using (var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read)) return Read(input);
        }

        private static void ValidateLocalFile(string path)
        {
            if (string.IsNullOrWhiteSpace(path) || !Path.IsPathRooted(path)) throw new IOException();
            LocalPathPolicy.NormalizeDirectory(Path.GetDirectoryName(path));
            LocalPathPolicy.EnsureNoReparsePoints(path);
            if (Environment.OSVersion.Platform == PlatformID.Win32NT && Path.GetFileName(path).IndexOf(':') >= 0)
                throw new IOException();
        }

        public void Export(string path)
        {
            ValidateLocalFile(path);
            byte[] bytes = ToBytes();
            string temporary = Path.Combine(Path.GetDirectoryName(path), ".bundle-" + Guid.NewGuid().ToString("N") + ".tmp");
            bool created = false;
            try
            {
                using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                { created = true; output.Write(bytes, 0, bytes.Length); output.Flush(true); }
                ValidateLocalFile(path);
                // An existing file is never replaced, including one created after the save dialog.
                File.Move(temporary, path);
                created = false;
            }
            finally
            {
                if (created)
                {
                    LocalPathPolicy.EnsureNoReparsePoints(temporary);
                    File.Delete(temporary);
                }
            }
        }

        public SavedBatteryObservation Import(string applicationDirectory)
        {
            string root = Path.Combine(LocalPathPolicy.NormalizeDirectory(applicationDirectory), "imported-observations");
            LocalPathPolicy.NormalizeDirectory(root);
            Directory.CreateDirectory(root);
            string identity = Guid.NewGuid().ToString("N");
            string target = Path.Combine(root, identity);
            string staging = Path.Combine(root, ".import-" + identity);
            string path = Path.Combine(target, Observation.FileName);
            var record = SavedBatteryObservation.Parse(Observation.Text, Observation.FileName, path);
            var notes = new ObservationNoteStore(applicationDirectory);
            ObservationNote savedNote = null;
            bool published = false, createdFile = false, createdDirectory = false;
            try
            {
                if (Directory.Exists(staging)) throw new IOException();
                Directory.CreateDirectory(staging);
                createdDirectory = true;
                LocalPathPolicy.EnsureNoReparsePoints(staging);
                using (var output = new FileStream(Path.Combine(staging, Observation.FileName), FileMode.CreateNew, FileAccess.Write, FileShare.None))
                {
                    createdFile = true;
                    byte[] bytes = Utf8.GetBytes(Observation.Text);
                    output.Write(bytes, 0, bytes.Length); output.Flush(true);
                }
                savedNote = notes.Save(record.NoteKey, NoteText, ObservationNote.Empty.Revision);
                if (!savedNote.Available) throw new IOException("복원할 메모를 저장하지 못했습니다.");
                LocalPathPolicy.EnsureNoReparsePoints(target);
                LocalPathPolicy.EnsureNoReparsePoints(staging);
                Directory.Move(staging, target);
                published = true;
                return record;
            }
            finally
            {
                if (!published)
                {
                    // Only remove this transaction's revision. Concurrently changed data is retained.
                    if (savedNote != null && savedNote.Available) notes.RemoveImportedRevision(record.NoteKey, savedNote.Revision);
                    try
                    {
                        LocalPathPolicy.EnsureNoReparsePoints(staging);
                        if (createdFile) File.Delete(Path.Combine(staging, Observation.FileName));
                        if (createdDirectory && Directory.Exists(staging)) Directory.Delete(staging);
                    }
                    catch { /* Original bundle is retained and can be imported again. */ }
                }
            }
        }
    }
}
