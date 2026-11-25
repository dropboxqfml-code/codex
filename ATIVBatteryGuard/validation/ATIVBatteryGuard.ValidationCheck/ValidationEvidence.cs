using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Security.Cryptography;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Storage;

namespace ATIVBatteryGuard.Validation
{
    [DataContract]
    public sealed class ExpectedFile
    {
        [DataMember(IsRequired = true)] public string Name;
        [DataMember(IsRequired = true)] public long Bytes;
        [DataMember(IsRequired = true)] public string Sha256;
    }
    [DataContract]
    public sealed class ValidationManifest
    {
        [DataMember(IsRequired = true)] public int SchemaVersion;
        [DataMember(IsRequired = true)] public string ReleaseVersion;
        [DataMember(IsRequired = true)] public string SourceFingerprintSha256;
        [DataMember(IsRequired = true)] public List<ExpectedFile> ProgramFiles;
    }
    [DataContract]
    public sealed class GuiEvidence
    {
        [DataMember(Name = "schemaVersion", IsRequired = true)] public int SchemaVersion;
        [DataMember(Name = "status", IsRequired = true)] public string Status;
        [DataMember(Name = "guiPassed", IsRequired = true)] public bool GuiPassed;
        [DataMember(Name = "hardwareWritesPerformed", IsRequired = true)] public bool HardwareWritesPerformed;
        [DataMember(Name = "bindingErrors", IsRequired = true)] public int BindingErrors;
        [DataMember(Name = "nativePowerStatus", IsRequired = true)] public string NativePowerStatus;
        [DataMember(Name = "nativeWmiStatus", IsRequired = true)] public string NativeWmiStatus;
        [DataMember(Name = "errors", IsRequired = true)] public string[] Errors;
    }
    public static class ValidationEvidence
    {
        public static readonly string[] ProgramNames = {
            "ATIVBatteryGuard.exe", "ATIVBatteryGuard.exe.config", "ATIVBatteryGuard.Core.dll",
            "ATIVBatteryGuard.WmiInterop.dll", "ATIVBatteryGuard.ManualProtectionHelper.exe", "ATIVBatteryGuard.ManualProtectionHelper.exe.config"
        };
        public static bool IsHash(string text) => text != null && text.Length == 64 && text.All(c =>
            c >= '0' && c <= '9' || c >= 'a' && c <= 'f');
        public static string Hash(Stream input)
        {
            using (var hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(input)).Replace("-", "").ToLowerInvariant();
        }
        public static ValidationManifest ReadManifest(byte[] bytes)
        {
            var manifest = LocalJsonDocument.Read<ValidationManifest>(bytes, 65536);
            if (manifest == null || manifest.SchemaVersion != 1 || manifest.ReleaseVersion != ApplicationRelease.Version
                || !IsHash(manifest.SourceFingerprintSha256) || manifest.ProgramFiles == null || manifest.ProgramFiles.Count != 6
                || manifest.ProgramFiles.Any(e => e == null || !ProgramNames.Contains(e.Name) || e.Bytes < 1 || e.Bytes > 32 * 1024 * 1024 || !IsHash(e.Sha256))
                || manifest.ProgramFiles.Select(e => e.Name).Distinct(StringComparer.Ordinal).Count() != 6)
                throw new InvalidDataException("검증 묶음의 버전과 구성 정보를 확인하세요.");
            return manifest;
        }
        public static void VerifyFiles(string root, ValidationManifest manifest)
        {
            // Validate again even for callers holding an in-memory manifest.
            if (manifest == null || manifest.SchemaVersion != 1 || manifest.ProgramFiles == null || manifest.ProgramFiles.Count != 6
                || manifest.ReleaseVersion != ApplicationRelease.Version || !IsHash(manifest.SourceFingerprintSha256)
                || manifest.ProgramFiles.Any(e => e == null || !ProgramNames.Contains(e.Name) || e.Bytes < 1 || e.Bytes > 32 * 1024 * 1024 || !IsHash(e.Sha256))
                || manifest.ProgramFiles.Select(e => e.Name).Distinct(StringComparer.Ordinal).Count() != 6) throw new InvalidDataException();
            root = LocalPathPolicy.NormalizeDirectory(root);
            foreach (var entry in manifest.ProgramFiles)
            {
                string path = LocalPathPolicy.NormalizeFile(Path.Combine(root, entry.Name));
                using (var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
                    if (input.Length != entry.Bytes || Hash(input) != entry.Sha256)
                        throw new InvalidDataException("프로그램 파일이 검증 대상과 다릅니다. 새 폴더에 다시 압축을 풀어 주세요.");
            }
        }
        public static GuiEvidence ReadGui(byte[] bytes)
        {
            var evidence = LocalJsonDocument.Read<GuiEvidence>(bytes, 65536);
            if (evidence == null || evidence.SchemaVersion != 1 || (evidence.Status != "passed" && evidence.Status != "failed")
                || !new[] { "not-run", "available", "unavailable" }.Contains(evidence.NativePowerStatus)
                || !new[] { "not-run", "complete", "partial-or-unavailable" }.Contains(evidence.NativeWmiStatus)
                || evidence.Errors == null || evidence.Errors.Length > 32
                || evidence.Errors.Any(e => e == null || e.Length > 120 || e.Any(c => !(c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '_'))))
                throw new InvalidDataException("자동 화면 검사 결과의 형식을 확인하세요.");
            return evidence;
        }
        public static bool GuiPassed(int exitCode, GuiEvidence evidence) => exitCode == 0 && evidence != null
            && evidence.SchemaVersion == 1 && evidence.Status == "passed" && evidence.GuiPassed
            && !evidence.HardwareWritesPerformed && evidence.BindingErrors == 0 && evidence.Errors != null && evidence.Errors.Length == 0;
    }
}
