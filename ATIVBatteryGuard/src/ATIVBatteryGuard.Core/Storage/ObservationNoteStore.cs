using System;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Security.Cryptography;
using System.Text;

namespace ATIVBatteryGuard.Core.Storage
{
    public sealed class ObservationNote
    {
        public static ObservationNote Empty { get; } = Ready("", "missing");
        public string Text { get; }
        public string Revision { get; }
        public string Notice { get; }
        public bool Available => Notice.Length == 0;

        private ObservationNote(string text, string revision, string notice)
        { Text = text; Revision = revision; Notice = notice; }

        internal static ObservationNote Ready(string text, string revision) { return new ObservationNote(text, revision, ""); }
        public static ObservationNote Unavailable(string notice) { return new ObservationNote("", "", notice); }

        public static string Normalize(string text) { return (text ?? "").Replace("\r\n", "\n").Replace('\r', '\n'); }

        public static string Preview(string text)
        {
            string singleLine = Normalize(text).Replace('\n', ' ').Replace('\t', ' ');
            if (singleLine.Length == 0) return "";
            int count = Math.Min(120, singleLine.Length);
            if (count < singleLine.Length && char.IsHighSurrogate(singleLine[count - 1])) count--;
            return "메모 · " + singleLine.Substring(0, count) + (count < singleLine.Length ? "…" : "");
        }
    }

    public sealed class ObservationNoteStore
    {
        public const int MaximumCharacters = 1000;
        private const int MaximumBytes = 16384;
        private readonly string directory;
        private static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);

        [DataContract]
        private sealed class Document
        {
            [DataMember(IsRequired = true)] public int Version = 1;
            [DataMember(IsRequired = true)] public string Text;
        }

        public ObservationNoteStore(string applicationDirectory)
        {
            directory = Path.Combine(LocalPathPolicy.NormalizeDirectory(applicationDirectory), "observation-notes");
        }

        internal static string Identity(string path, string text)
        {
            string fullPath = Path.GetFullPath(path);
            if (Environment.OSVersion.Platform == PlatformID.Win32NT) fullPath = fullPath.ToUpperInvariant();
            return Hash(Utf8.GetBytes(fullPath + "\0" + ObservationNote.Normalize(text).TrimStart('\uFEFF')));
        }

        private static string Hash(byte[] bytes)
        {
            using (var hash = SHA256.Create())
                return BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
        }

        public static bool IsValidKey(string key)
        {
            return key != null && key.Length == 64 && key.All(c => (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'));
        }

        public static bool IsValidText(string text)
        {
            if (text == null || text.Length > MaximumCharacters || text.Any(c => char.IsControl(c) && c != '\n' && c != '\t'))
                return false;
            try { Utf8.GetByteCount(text); return true; } catch (EncoderFallbackException) { return false; }
        }

        private string FilePath(string key) { return Path.Combine(directory, key + ".json"); }

        public ObservationNote Load(string key)
        {
            if (!IsValidKey(key)) return ObservationNote.Unavailable("기록을 다시 열어 메모를 사용할 수 있습니다.");
            try
            {
                string path = FilePath(key);
                LocalPathPolicy.EnsureNoReparsePoints(path);
                if (!File.Exists(path)) return ObservationNote.Empty;
                using (var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete))
                using (var bytes = new MemoryStream())
                {
                    var buffer = new byte[4096];
                    int count;
                    while ((count = input.Read(buffer, 0, buffer.Length)) != 0)
                    {
                        if (bytes.Length + count > MaximumBytes) return ObservationNote.Unavailable("메모 파일 크기를 확인하세요.");
                        bytes.Write(buffer, 0, count);
                    }
                    bytes.Position = 0;
                    var document = (Document)new DataContractJsonSerializer(typeof(Document)).ReadObject(bytes);
                    if (document == null || document.Version != 1 || !IsValidText(document.Text))
                        return ObservationNote.Unavailable("메모 파일의 형식을 확인하세요.");
                    return ObservationNote.Ready(ObservationNote.Normalize(document.Text), Hash(bytes.ToArray()));
                }
            }
            catch { return ObservationNote.Unavailable("메모를 읽지 못했습니다. 로컬 저장 위치와 읽기 권한을 확인하세요."); }
        }

        // Rollback only a note created for an unpublished import, guarded against concurrent edits.
        internal bool RemoveImportedRevision(string key, string revision)
        {
            try
            {
                string path = FilePath(key);
                LocalPathPolicy.EnsureNoReparsePoints(path + ".lock");
                using (var lease = new FileStream(path + ".lock", FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                {
                    var current = Load(key);
                    if (!current.Available || current.Revision != revision) return false;
                    LocalPathPolicy.EnsureNoReparsePoints(path);
                    File.Delete(path);
                    return true;
                }
            }
            catch { return false; }
        }

        public ObservationNote Save(string key, string text, string expectedRevision)
        {
            text = ObservationNote.Normalize(text);
            if (!IsValidKey(key) || !IsValidText(text))
                return ObservationNote.Unavailable("메모는 일반 텍스트로 최대 1000자까지 저장할 수 있습니다.");
            string temporary = null;
            try
            {
                LocalPathPolicy.NormalizeDirectory(directory);
                Directory.CreateDirectory(directory);
                string path = FilePath(key), lockPath = path + ".lock";
                LocalPathPolicy.EnsureNoReparsePoints(lockPath);
                using (var lease = new FileStream(lockPath, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None))
                {
                    var current = Load(key);
                    if (!current.Available) return current;
                    if (current.Revision != expectedRevision)
                        return ObservationNote.Unavailable("다른 창에서 메모가 변경됐습니다. 메모 다시 읽기로 최신 내용을 확인하세요.");
                    byte[] bytes;
                    using (var output = new MemoryStream())
                    {
                        new DataContractJsonSerializer(typeof(Document)).WriteObject(output, new Document { Text = text });
                        bytes = output.ToArray();
                    }
                    temporary = Path.Combine(directory, ".note-" + Guid.NewGuid().ToString("N") + ".tmp");
                    using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                    { output.Write(bytes, 0, bytes.Length); output.Flush(true); }
                    LocalPathPolicy.EnsureNoReparsePoints(path);
                    if (File.Exists(path)) File.Replace(temporary, path, null);
                    else File.Move(temporary, path);
                    temporary = null;
                    return ObservationNote.Ready(text, Hash(bytes));
                }
            }
            catch { return ObservationNote.Unavailable("메모를 저장하지 못했습니다. 입력한 내용을 보관 중입니다."); }
            finally
            {
                if (temporary != null) { try { File.Delete(temporary); } catch { } }
            }
        }
    }
}
