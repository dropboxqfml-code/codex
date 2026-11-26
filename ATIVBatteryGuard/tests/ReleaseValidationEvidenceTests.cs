using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Validation;

internal static partial class Program
{
    private static void RegisterReleaseValidationEvidenceTests()
    {
        Add("release candidate verification accepts exact allowlisted files and detects a post-check change without overwriting data", () =>
        {
            using (var f = new Fixture())
            {
                var manifest = MakeValidationManifest(f.DirectoryPath);
                var parsed = ValidationEvidence.ReadManifest(JsonSerializer.SerializeToUtf8Bytes(manifest, new JsonSerializerOptions { IncludeFields = true }));
                ValidationEvidence.VerifyFiles(f.DirectoryPath, parsed);
                string path = Path.Combine(f.DirectoryPath, "ATIVBatteryGuard.Core.dll");
                File.WriteAllText(path, "changed after GUI check");
                RejectValidation(() => ValidationEvidence.VerifyFiles(f.DirectoryPath, parsed));
                Equal("changed after GUI check", File.ReadAllText(path));
            }
        });
        Add("release evidence rejects unexpected paths duplicate names versions malformed hashes and sizes before use", () =>
        {
            using (var f = new Fixture())
            {
                foreach (Action<ValidationManifest> change in new Action<ValidationManifest>[] {
                    m => m.SchemaVersion = 2, m => m.ReleaseVersion = ApplicationRelease.Version + "-mismatch", m => m.SourceFingerprintSha256 = "bad",
                    m => m.ProgramFiles[0].Name = "../outside.exe", m => m.ProgramFiles[0].Name = m.ProgramFiles[1].Name,
                    m => m.ProgramFiles[0].Bytes = -1, m => m.ProgramFiles[0].Bytes = 33554433,
                    m => m.ProgramFiles[0].Sha256 = "uppercase-or-invalid", m => m.ProgramFiles.RemoveAt(0) })
                {
                    var manifest = MakeValidationManifest(f.DirectoryPath); change(manifest);
                    byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(manifest, new JsonSerializerOptions { IncludeFields = true });
                    RejectValidation(() => ValidationEvidence.ReadManifest(bytes));
                    RejectValidation(() => ValidationEvidence.VerifyFiles(f.DirectoryPath, manifest));
                }
            }
        });
        Add("release file verification requires all six files and refuses linked or network sources", () =>
        {
            using (var f = new Fixture())
            {
                var manifest = MakeValidationManifest(f.DirectoryPath);
                string path = Path.Combine(f.DirectoryPath, ValidationEvidence.ProgramNames[0]); File.Delete(path);
                RejectValidation(() => ValidationEvidence.VerifyFiles(f.DirectoryPath, manifest));
                ExpectBundleIo(() => ValidationEvidence.VerifyFiles("//server/share", manifest));
                string outside = Path.Combine(f.DirectoryPath, "external"); Directory.CreateDirectory(outside);
                if (TryCreateQualityDirectoryLink(Path.Combine(f.DirectoryPath, "alias"), outside))
                    ExpectBundleIo(() => ValidationEvidence.VerifyFiles(Path.Combine(f.DirectoryPath, "alias"), manifest));
            }
        });
        Add("native GUI evidence requires successful exit no hardware writes no binding errors and no error codes", () =>
        {
            var data = Encoding.UTF8.GetBytes("{\"schemaVersion\":1,\"status\":\"passed\",\"guiPassed\":true,\"hardwareWritesPerformed\":false,\"bindingErrors\":0,\"nativePowerStatus\":\"available\",\"nativeWmiStatus\":\"partial-or-unavailable\",\"errors\":[]}");
            var good = ValidationEvidence.ReadGui(data); Check(ValidationEvidence.GuiPassed(0, good), "valid GUI evidence rejected");
            Check(!ValidationEvidence.GuiPassed(1, good), "failed process accepted");
            foreach (Action<GuiEvidence> change in new Action<GuiEvidence>[] {
                e => e.SchemaVersion = 2, e => e.Status = "failed", e => e.GuiPassed = false,
                e => e.HardwareWritesPerformed = true, e => e.BindingErrors = 1, e => e.Errors = new[] { "GUI_ERROR" } })
            {
                var evidence = ValidationEvidence.ReadGui(data); change(evidence);
                Check(!ValidationEvidence.GuiPassed(0, evidence), "failed GUI evidence accepted");
            }
            RejectValidation(() => ValidationEvidence.ReadGui(Encoding.UTF8.GetBytes("{\"status\":\"passed\",\"guiPassed\":true}")));
        });
        Add("manual validation fixtures restore real parser graphs and clearly mark all samples and notes as synthetic", () =>
        {
            foreach (string name in new[] { "Validation.SampleA.ativrecord", "Validation.SampleB.ativrecord" })
            using (var input = System.Reflection.Assembly.GetExecutingAssembly().GetManifestResourceStream(name))
            {
                var bundle = ATIVBatteryGuard.Core.Storage.ObservationBundle.Read(input);
                Equal(3, bundle.Observation.Graph.SampleCount); Equal(20, bundle.Observation.Graph.ElapsedSeconds);
                Check(bundle.Observation.FileName.Contains("실측아님") && bundle.NoteText.Contains("실제 측정 아님"), "synthetic data could be mistaken for measured evidence");
            }
        });
        Add("validation JSON rejects trailing payload unknown status and private error strings without modifying evidence", () =>
        {
            byte[] valid = Encoding.UTF8.GetBytes("{\"schemaVersion\":1,\"status\":\"passed\",\"guiPassed\":true,\"hardwareWritesPerformed\":false,\"bindingErrors\":0,\"nativePowerStatus\":\"available\",\"nativeWmiStatus\":\"complete\",\"errors\":[]}");
            RejectValidation(() => ValidationEvidence.ReadGui(valid.Concat(Encoding.UTF8.GetBytes("{}" )).ToArray()));
            RejectValidation(() => ValidationEvidence.ReadGui(Encoding.UTF8.GetBytes(Encoding.UTF8.GetString(valid).Replace("available", "PRIVATE-path"))));
            RejectValidation(() => ValidationEvidence.ReadGui(Encoding.UTF8.GetBytes(Encoding.UTF8.GetString(valid).Replace("[]", "[\"PRIVATE path\"]"))));
            RejectValidation(() => ValidationEvidence.ReadManifest(new byte[65537]));
        });
    }
    private static ValidationManifest MakeValidationManifest(string directory)
    {
        return new ValidationManifest {
            SchemaVersion = 1, ReleaseVersion = ApplicationRelease.Version, SourceFingerprintSha256 = new string('a', 64),
            ProgramFiles = ValidationEvidence.ProgramNames.Select(name => {
                string path = Path.Combine(directory, name); File.WriteAllText(path, "synthetic verification fixture " + name);
                using (var stream = File.OpenRead(path)) return new ExpectedFile { Name = name, Bytes = stream.Length, Sha256 = ValidationEvidence.Hash(stream) };
            }).ToList()
        };
    }
    private static void RejectValidation(Action action)
    {
        try { action(); }
        catch (InvalidDataException) { return; }
        catch (IOException) { return; }
        catch (System.Runtime.Serialization.SerializationException) { return; }
        throw new InvalidOperationException("invalid release evidence accepted");
    }
}
