using System;
using System.IO;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Security;
using System.Security.Cryptography;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Storage
{
    public sealed class SettingsStore
    {
        [DataContract]
        private sealed class SchemaHeader
        {
            [DataMember(Name = "schemaVersion")] public int SchemaVersion { get; set; }
        }
        private const int MaximumBytes = 65536;
        private readonly object sync = new object();
        private readonly string initializationError;
        private bool loaded, canSave;
        private string revision = "missing";
        public string DirectoryPath { get; private set; }
        public string FilePath { get; private set; }

        public SettingsStore(string directory)
        {
            try
            {
                DirectoryPath = LocalPathPolicy.NormalizeDirectory(directory);
                FilePath = Path.Combine(DirectoryPath, "settings.json");
            }
            catch (Exception ex) when (IsStorageError(ex))
            {
                DirectoryPath = FilePath = "";
                initializationError = "안전한 로컬 저장 위치를 확인할 수 없습니다.";
            }
        }

        public SettingsLoadResult Load()
        {
            lock (sync)
            {
                loaded = true; canSave = false;
                if (initializationError != null) return Defaults(initializationError, false);
                try
                {
                    LocalPathPolicy.EnsureNoReparsePoints(FilePath);
                    if (!Directory.Exists(DirectoryPath))
                    { revision = "missing"; canSave = true; return Defaults("", true); }
                    using (var lease = Lease())
                    {
                        if (!File.Exists(FilePath))
                        { revision = "missing"; canSave = true; return Defaults("", true); }
                        byte[] bytes = ReadBounded();
                        try
                        {
                            if (ReadSchema(bytes) > 1)
                                return Defaults("더 최신 버전의 설정 파일입니다. 원본을 보존하며 저장을 차단합니다.", false);
                            var settings = LocalJsonDocument.Read<AppSettings>(bytes, MaximumBytes);
                            if (settings == null || !settings.IsValid(out var reason)) return RecoverCorrupt();
                            revision = Hash(bytes); canSave = true;
                            return new SettingsLoadResult(settings, "", true);
                        }
                        catch (SerializationException) { return RecoverCorrupt(); }
                    }
                }
                catch (Exception ex) when (IsStorageError(ex))
                {
                    // A busy or read-only lock must not hide a valid existing preference snapshot.
                    // This fallback never rotates a corrupt file and never grants save permission.
                    try
                    {
                        LocalPathPolicy.EnsureNoReparsePoints(FilePath);
                        var settings = LocalJsonDocument.Read<AppSettings>(ReadBounded(), MaximumBytes);
                        if (settings != null && settings.IsValid(out var reason))
                            return new SettingsLoadResult(settings, "기존 설정을 읽기 전용으로 불러왔습니다. 다른 창의 저장 완료와 로컬 권한을 확인한 뒤 앱을 다시 여세요.", false);
                    }
                    catch (Exception fallback) when (IsStorageError(fallback) || fallback is SerializationException) { }
                    return Defaults("설정을 읽을 수 없습니다. 원본을 보존하며 저장을 차단합니다.", false);
                }
            }
        }

        public OperationResult Save(AppSettings settings)
        {
            lock (sync)
            {
                if (settings == null || !settings.IsValid(out var reason)) return Fail("저장할 설정 값이 올바르지 않습니다.");
                if (!loaded) Load();
                if (!canSave) return Fail("설정 파일 보호를 위해 저장이 차단되었습니다. 앱을 다시 열어 최신 설정을 확인하세요.");
                string temporary = null;
                try
                {
                    LocalPathPolicy.NormalizeDirectory(DirectoryPath);
                    Directory.CreateDirectory(DirectoryPath);
                    using (var lease = Lease())
                    {
                        LocalPathPolicy.EnsureNoReparsePoints(FilePath);
                        byte[] current = File.Exists(FilePath) ? ReadBounded() : null;
                        if (current != null && ReadSchema(current) > 1)
                        { canSave = false; return Fail("더 최신 버전의 설정 파일을 덮어쓰지 않습니다."); }
                        if ((current == null ? "missing" : Hash(current)) != revision)
                        { canSave = false; return Fail("다른 창이나 외부에서 설정이 변경됐습니다. 앱을 다시 열어 최신 설정을 확인하세요."); }
                        if (current != null)
                        {
                            var existing = LocalJsonDocument.Read<AppSettings>(current, MaximumBytes);
                            if (existing == null || !existing.IsValid(out reason))
                            { canSave = false; return Fail("설정 파일이 변경되었습니다. 앱을 다시 열어 파일 상태를 확인하세요."); }
                        }
                        byte[] bytes;
                        using (var buffer = new MemoryStream())
                        {
                            new DataContractJsonSerializer(typeof(AppSettings)).WriteObject(buffer, settings);
                            bytes = buffer.ToArray();
                        }
                        string candidate = Path.Combine(DirectoryPath, ".settings-" + Guid.NewGuid().ToString("N") + ".tmp");
                        using (var output = new FileStream(candidate, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough))
                        { temporary = candidate; output.Write(bytes, 0, bytes.Length); output.Flush(true); }
                        string backup = FilePath + ".bak";
                        LocalPathPolicy.EnsureNoReparsePoints(FilePath);
                        LocalPathPolicy.EnsureNoReparsePoints(backup);
                        if (File.Exists(FilePath)) File.Replace(temporary, FilePath, backup, true);
                        else File.Move(temporary, FilePath);
                        temporary = null; revision = Hash(bytes);
                        return new OperationResult(true, "사용자 희망 설정을 저장했습니다. 실제 하드웨어 적용을 의미하지 않습니다.");
                    }
                }
                catch (Exception ex) when (IsStorageError(ex) || ex is SerializationException)
                { return Fail("설정을 저장하지 못했습니다. 기존 설정을 보관합니다. 다른 창의 저장 완료와 로컬 공간·권한을 확인하고 다시 시도하세요."); }
                finally
                {
                    if (temporary != null)
                    { try { LocalPathPolicy.EnsureNoReparsePoints(temporary); File.Delete(temporary); } catch (Exception ex) when (IsStorageError(ex)) { } }
                }
            }
        }

        private FileStream Lease()
        {
            LocalPathPolicy.EnsureNoReparsePoints(FilePath + ".lock");
            return new FileStream(FilePath + ".lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        }
        // Called with the same cross-process lease as Load/Save, so a new valid file cannot be rotated away.
        private SettingsLoadResult RecoverCorrupt()
        {
            try
            {
                LocalPathPolicy.EnsureNoReparsePoints(FilePath);
                string copy = Path.Combine(DirectoryPath, "settings.corrupt-" + DateTime.UtcNow.ToString("yyyyMMddTHHmmss") + "-" + Guid.NewGuid().ToString("N") + ".json");
                File.Move(FilePath, copy);
                revision = "missing"; canSave = true;
                return Defaults("손상된 설정 원본을 별도 파일로 보존했습니다. 기본 사용자 설정으로 시작합니다.", true);
            }
            catch (Exception ex) when (IsStorageError(ex))
            { canSave = false; return Defaults("손상된 설정 원본을 보존할 수 없어 저장을 차단했습니다.", false); }
        }
        private byte[] ReadBounded()
        {
            using (var input = new FileStream(FilePath, FileMode.Open, FileAccess.Read, FileShare.Read))
            using (var bytes = new MemoryStream())
            {
                var buffer = new byte[4096]; int count;
                while ((count = input.Read(buffer, 0, buffer.Length)) != 0)
                {
                    if (bytes.Length + count > MaximumBytes) throw new IOException();
                    bytes.Write(buffer, 0, count);
                }
                return bytes.ToArray();
            }
        }
        private static string Hash(byte[] bytes)
        { using (var hash = SHA256.Create()) return Convert.ToBase64String(hash.ComputeHash(bytes)); }
        private static int ReadSchema(byte[] bytes) => LocalJsonDocument.Read<SchemaHeader>(bytes, MaximumBytes)?.SchemaVersion ?? 0;
        private static SettingsLoadResult Defaults(string warning, bool allowSave) => new SettingsLoadResult(new AppSettings(), warning, allowSave);
        private static OperationResult Fail(string text) => new OperationResult(false, text);
        private static bool IsStorageError(Exception ex) => ex is IOException || ex is UnauthorizedAccessException
            || ex is ArgumentException || ex is NotSupportedException || ex is SecurityException;
    }
}
