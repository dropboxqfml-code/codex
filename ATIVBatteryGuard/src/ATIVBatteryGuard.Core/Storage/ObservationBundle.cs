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
        public const string RecoveryFileName = "import-recovery.ativrecord";
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
                    var document = LocalJsonDocument.Read<Document>(bytes.ToArray(), MaximumBytes, 32);
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

        private static bool IsValidFileName(string name)
        {
            return LocalPathPolicy.IsSafeFileName(name) && name.EndsWith(".txt", StringComparison.OrdinalIgnoreCase);
        }

        public static ObservationBundle ReadFile(string path)
        {
            ValidateLocalFile(path);
            using (var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read)) return Read(input);
        }

        private static void ValidateLocalFile(string path)
        {
            LocalPathPolicy.NormalizeFile(path);
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

        public static string RecoveryNotice(string applicationDirectory)
        {
            try
            {
                string root = Path.Combine(LocalPathPolicy.NormalizeDirectory(applicationDirectory), "imported-observations");
                LocalPathPolicy.EnsureNoReparsePoints(root);
                if (!Directory.Exists(root)) return "";
                foreach (string folder in Directory.EnumerateDirectories(root, ".import-*", SearchOption.TopDirectoryOnly).Take(64))
                {
                    string name = Path.GetFileName(folder); Guid id;
                    if (name.Length != 40 || !Guid.TryParseExact(name.Substring(8), "N", out id)) continue;
                    string recovery = Path.Combine(folder, RecoveryFileName);
                    LocalPathPolicy.EnsureNoReparsePoints(recovery);
                    string leasePath = folder + ".lock";
                    LocalPathPolicy.EnsureNoReparsePoints(leasePath);
                    if (File.Exists(leasePath))
                    {
                        try { using (var probe = new FileStream(leasePath, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { } }
                        catch (IOException) { continue; } // Another app is still importing this record.
                    }
                    if (File.Exists(recovery)) return "중단된 복원 자료가 있습니다. ‘저장 폴더 열기’ → imported-observations → .import- 폴더의 "
                        + RecoveryFileName + "을 ‘TXT·메모 묶음 불러오기’로 열어 다시 복원할 수 있습니다. 기존 자료는 자동 삭제하지 않습니다.";
                }
                return "";
            }
            catch { return "복원 중단 자료를 확인하지 못했습니다. 로컬 저장 폴더와 권한을 확인하세요."; }
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
            bool published = false, createdFile = false, createdDirectory = false, createdRecovery = false;
            string recovery = Path.Combine(staging, RecoveryFileName);
            string leasePath = staging + ".lock";
            FileStream importLease = null;
            try
            {
                LocalPathPolicy.EnsureNoReparsePoints(leasePath);
                importLease = new FileStream(leasePath, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None);
                if (Directory.Exists(staging)) throw new IOException();
                Directory.CreateDirectory(staging);
                createdDirectory = true;
                LocalPathPolicy.EnsureNoReparsePoints(staging);
                // A flushed, portable recovery copy precedes TXT/note changes. Do not auto-delete abandoned stages.
                using (var output = new FileStream(recovery, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                {
                    createdRecovery = true; byte[] bytes = ToBytes();
                    output.Write(bytes, 0, bytes.Length); output.Flush(true);
                }
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
                try
                {
                    string completedRecovery = Path.Combine(target, RecoveryFileName);
                    LocalPathPolicy.EnsureNoReparsePoints(completedRecovery);
                    File.Delete(completedRecovery);
                }
                catch { /* A completed import remains successful; only its optional recovery copy remains. */ }
                return record;
            }
            finally
            {
                try
                {
                    if (!published)
                    {
                        // Only remove this transaction's revision. Concurrently changed data is retained.
                        bool rolledBack = savedNote == null || !savedNote.Available || notes.RemoveImportedRevision(record.NoteKey, savedNote.Revision);
                        try
                        {
                            LocalPathPolicy.EnsureNoReparsePoints(staging);
                            if (rolledBack)
                            {
                                if (createdFile) File.Delete(Path.Combine(staging, Observation.FileName));
                                if (createdRecovery) File.Delete(recovery);
                                if (createdDirectory && Directory.Exists(staging)) Directory.Delete(staging);
                            }
                        }
                        catch { /* Original bundle is retained and can be imported again. */ }
                    }
                }
                finally
                {
                    if (importLease != null)
                    {
                        importLease.Dispose();
                        try { LocalPathPolicy.EnsureNoReparsePoints(leasePath); File.Delete(leasePath); } catch { }
                    }
                }
            }
        }
    }
}
