using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;

namespace ATIVBatteryGuard.ExtendedValidation
{
    [DataContract]
    public sealed class StartupEvidence
    {
        [DataMember] public int SchemaVersion = 1;
        [DataMember] public string ToolRevision = "extended-v4";
        [DataMember] public string ReleaseVersion = "0.3.0-rc.3";
        [DataMember] public string StartedUtc = DateTime.UtcNow.ToString("O");
        [DataMember] public string UpdatedUtc;
        [DataMember] public string CompletedUtc;
        [DataMember] public string Stage = "bootstrap";
        [DataMember] public string Outcome = "startup-in-progress-not-passed";
        [DataMember] public string Mode = "unselected";
        [DataMember] public string ErrorCode;
        [DataMember] public string ExceptionCategory;
        [DataMember] public int? ExceptionHResult;
        [DataMember] public bool StartupSucceeded;
        [DataMember] public int? ValidationExitCode;
        [DataMember] public bool FinalReleaseApproved = false;
        [DataMember] public bool HardwareWritesPerformed = false;
    }

    // BCL-only bootstrap: no WPF, product or Core types are required to save a
    // dependency/resource initialization failure. Never persist exception messages,
    // stack traces, paths, arguments or device/account identifiers.
    public sealed class StartupJournal
    {
        private readonly StartupEvidence evidence = new StartupEvidence();
        public string ReportPath { get; }
        public string Stage => evidence.Stage;
        public string ErrorCode => evidence.ErrorCode;
        public bool HasFailure => evidence.ErrorCode != null;
        private static readonly string[] Stages = { "bootstrap", "arguments", "platform", "location", "manifest-read",
            "files-before", "product-version", "application-create", "resources-load", "dispatcher-start", "runner-start" };
        public StartupJournal(string applicationDirectory)
        {
            string root = Path.GetFullPath(applicationDirectory);
            PlainPath(root);
            string directory = Path.Combine(root, "extended-results"); PlainPath(directory);
            Directory.CreateDirectory(directory);
            ReportPath = Path.Combine(directory, "startup-" + Guid.NewGuid().ToString("N") + ".json");
            WriteNew(ReportPath);
        }
        public void Advance(string stage)
        {
            if (!Stages.Contains(stage)) throw new ArgumentException();
            if (HasFailure) return;
            evidence.Stage = stage; Save();
        }
        public void SelectMode(bool soak)
        { evidence.Mode = soak ? "soak-20-minutes" : "quick-30-cycles"; Save(); }
        public void SelectImeCloseMode() { evidence.Mode = "guided-ime-close"; Save(); }
        public void SelectImeMode() { evidence.Mode = "guided-ime"; Save(); }
        public void Fail(Exception error)
        {
            if (HasFailure) return;
            while ((error is TargetInvocationException || error is TypeInitializationException) && error.InnerException != null)
                error = error.InnerException;
            evidence.ErrorCode = "STARTUP_" + evidence.Stage.Replace('-', '_').ToUpperInvariant() + "_FAILED";
            evidence.ExceptionCategory = Category(error);
            evidence.ExceptionHResult = error?.HResult;
            evidence.Outcome = "startup-failed-not-passed";
            evidence.CompletedUtc = DateTime.UtcNow.ToString("O"); Save();
        }
        public void Complete(int validationExitCode)
        {
            if (HasFailure) return;
            evidence.StartupSucceeded = true;
            evidence.ValidationExitCode = validationExitCode;
            evidence.Outcome = "startup-completed-see-validation-report";
            evidence.CompletedUtc = DateTime.UtcNow.ToString("O"); Save();
        }
        private static string Category(Exception error)
        {
            if (error is BadImageFormatException) return "assembly-format-or-architecture";
            if (error is FileNotFoundException) return "file-or-dependency-missing";
            if (error is FileLoadException) return "assembly-load-failed";
            if (error is UnauthorizedAccessException) return "access-denied";
            if (error is SerializationException) return "json-format";
            if (error is IOException) return "file-io";
            if (error is NotSupportedException) return "unsupported-platform-or-operation";
            if (error is ArgumentException) return "invalid-argument";
            if (error?.GetType().FullName == "System.Windows.Markup.XamlParseException") return "wpf-resource-parse";
            return "other-initialization-error";
        }
        private void Save()
        {
            string staging = ReportPath + ".tmp";
            try { WriteNew(staging); PlainPath(ReportPath); File.Replace(staging, ReportPath, null); }
            finally { if (File.Exists(staging)) { PlainPath(staging); File.Delete(staging); } }
        }
        private void WriteNew(string path)
        {
            PlainPath(path); evidence.UpdatedUtc = DateTime.UtcNow.ToString("O");
            using (var file = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { new DataContractJsonSerializer(typeof(StartupEvidence)).WriteObject(file, evidence); file.Flush(true); }
        }
        private static void PlainPath(string path)
        {
            // Startup logging must remain usable even if Core.dll cannot load.
            for (string current = Path.GetFullPath(path); !string.IsNullOrEmpty(current); current = Path.GetDirectoryName(current))
                if ((File.Exists(current) || Directory.Exists(current)) && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                    throw new IOException();
        }
    }
}
