using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Xml.Linq;
using ATIVBatteryGuard.ExtendedValidation;

internal static partial class Program
{
    private static StartupEvidence ReadStartup(string path)
    {
        using (var stream = File.OpenRead(path)) return (StartupEvidence)new DataContractJsonSerializer(typeof(StartupEvidence)).ReadObject(stream);
    }
    private static void RegisterExtendedStartupTests()
    {
        Add("extended host dictionary preserves every frozen product application resource", () =>
        {
            XNamespace wpf = "http://schemas.microsoft.com/winfx/2006/xaml/presentation";
            using (var original = typeof(Program).Assembly.GetManifestResourceStream("Beginner.App.xaml"))
            using (var isolated = typeof(Program).Assembly.GetManifestResourceStream("Extended.ProductResources.xaml"))
            {
                var source = XDocument.Load(original).Root.Element(wpf + "Application.Resources");
                var target = XDocument.Load(isolated).Root;
                Check(target.Name == wpf + "ResourceDictionary", "host still loads application root");
                var sourceItems = source.Elements().ToArray(); var targetItems = target.Elements().ToArray();
                Equal(sourceItems.Length, targetItems.Length); Check(sourceItems.Length > 0, "resources empty");
                for (int i = 0; i < sourceItems.Length; i++) Check(XNode.DeepEquals(sourceItems[i], targetItems[i]), "host dictionary changed product resources");
            }
        });
        Add("extended startup journal exists before product initialization and supports Korean desktop-style paths", () =>
        {
            using (var f = new Fixture())
            {
                string root = Path.Combine(f.DirectoryPath, "바탕 화면", "추가 검사 v2"); Directory.CreateDirectory(root);
                var journal = new StartupJournal(root); var report = ReadStartup(journal.ReportPath);
                Equal("bootstrap", report.Stage); Equal("startup-in-progress-not-passed", report.Outcome);
                Check(!report.StartupSucceeded && !report.FinalReleaseApproved && !report.HardwareWritesPerformed, "startup treated as pass");
                journal.Advance("resources-load"); journal.Fail(new Exception("PRIVATE ACCOUNT and C:\\private\\memo"));
                report = ReadStartup(journal.ReportPath);
                Equal("STARTUP_RESOURCES_LOAD_FAILED", report.ErrorCode); Equal("startup-failed-not-passed", report.Outcome);
                string text = File.ReadAllText(journal.ReportPath);
                Check(!text.Contains("PRIVATE") && !text.Contains("private") && !text.Contains(f.DirectoryPath), "private startup details persisted");
                Check(!Directory.GetFiles(Path.GetDirectoryName(journal.ReportPath), "*.tmp").Any(), "journal leaked staging file");
            }
        });
        Add("extended startup classifies wrapped dependency failures without recording exception paths", () =>
        {
            using (var f = new Fixture())
            {
                Exception[] errors = { new FileNotFoundException("PRIVATE", "PRIVATE.dll"), new FileLoadException("PRIVATE"),
                    new BadImageFormatException("PRIVATE"), new UnauthorizedAccessException("PRIVATE"), new SerializationException("PRIVATE") };
                string[] categories = { "file-or-dependency-missing", "assembly-load-failed", "assembly-format-or-architecture", "access-denied", "json-format" };
                for (int i = 0; i < errors.Length; i++)
                {
                    var journal = new StartupJournal(f.DirectoryPath); journal.Advance("manifest-read");
                    journal.Fail(new TargetInvocationException(new TypeInitializationException("PRIVATE", errors[i])));
                    var report = ReadStartup(journal.ReportPath); Equal(categories[i], report.ExceptionCategory);
                    Equal(errors[i].HResult, report.ExceptionHResult.Value);
                    Check(!File.ReadAllText(journal.ReportPath).Contains("PRIVATE"), "wrapped exception details leaked");
                }
            }
        });
        Add("extended startup completion cannot overwrite a failure or approve unsuccessful validation", () =>
        {
            using (var f = new Fixture())
            {
                var failed = new StartupJournal(f.DirectoryPath); failed.Advance("files-before"); failed.Fail(new InvalidDataException());
                byte[] bytes = File.ReadAllBytes(failed.ReportPath); failed.Complete(0); failed.Advance("dispatcher-start");
                Check(bytes.SequenceEqual(File.ReadAllBytes(failed.ReportPath)), "startup failure overwritten");
                var completed = new StartupJournal(f.DirectoryPath); completed.SelectMode(false); completed.Advance("runner-start"); completed.Complete(1);
                var report = ReadStartup(completed.ReportPath);
                Check(report.StartupSucceeded && report.ValidationExitCode == 1 && !report.FinalReleaseApproved, "validation failure called release pass");
                Equal("startup-completed-see-validation-report", report.Outcome);
                Check(bytes.SequenceEqual(File.ReadAllBytes(failed.ReportPath)), "new run changed old report");
            }
        });
        Add("extended startup accepts only fixed diagnostic stages and never writes arbitrary arguments", () =>
        {
            using (var f = new Fixture())
            {
                var journal = new StartupJournal(f.DirectoryPath); bool rejected = false;
                try { journal.Advance("PRIVATE --command argument"); } catch (ArgumentException) { rejected = true; }
                Check(rejected, "arbitrary stage accepted");
                Equal("bootstrap", ReadStartup(journal.ReportPath).Stage);
                Check(!File.ReadAllText(journal.ReportPath).Contains("PRIVATE"), "untrusted argument logged");
            }
        });
    }
}
