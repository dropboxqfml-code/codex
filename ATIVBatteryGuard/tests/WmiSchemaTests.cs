using System;
using System.Collections.Generic;
using System.Linq;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterSchemaTests()
    {
        Add("schema query targets only exact statically confirmed class names", () =>
        {
            var source = new FakeSchemaSource(); var report = WmiSchemaInspector.Inspect(source);
            Equal("WmiAcpiVersion,WmiAcpiMethod,DataBuffer", string.Join(",", source.Calls));
            Equal(3, report.Classes.Length);
            Check(!WmiSchemaPolicy.IsAllowedClass("Win32_Battery") && !WmiSchemaPolicy.IsAllowedClass("WmiAcpiMethod;DROP") && !WmiSchemaPolicy.IsAllowedClass("wmiacpimethod"), "allowlist broadened");
        });
        Add("schema allowlist returned array cannot alter future targets", () =>
        {
            string[] names = WmiSchemaPolicy.AllowedClasses; names[0] = "Untrusted";
            Equal("WmiAcpiVersion", WmiSchemaPolicy.AllowedClasses[0]);
        });
        Add("schema discovery never grants hardware access", () =>
        {
            var source = new FakeSchemaSource(); var report = WmiSchemaInspector.Inspect(source);
            Check(!WmiSchemaPolicy.HardwareWriteAllowed && !report.HardwareWriteAllowed && report.Classes.All(c => !c.HardwareWriteAllowed), "schema discovery grants write");
            string text = report.ToDisplayText();
            Check(text.Contains("실제 충전 제어: 미지원") && text.Contains("충전 제한 지원이 검증된 것은 아닙니다") && text.Contains("호출하지 않았습니다"), "discovery misrepresented as support");
        });
        foreach (WmiSchemaStatus status in Enum.GetValues(typeof(WmiSchemaStatus)))
        {
            WmiSchemaStatus captured = status;
            Add("schema status stays explicit: " + status, () =>
            {
                var source = new FakeSchemaSource { Reader = name => new WmiClassSchema(name, captured) };
                var report = WmiSchemaInspector.Inspect(source);
                Check(report.Classes.All(c => c.Status == captured), "status discarded");
                Check(report.ToDisplayText().Contains(WmiSchemaInspectionReport.StatusText(captured)), "status omitted");
            });
        }
        Add("schema failures are isolated and personal exception text is removed", () =>
        {
            var source = new FakeSchemaSource { Reader = name => name == "WmiAcpiVersion" ? throw new Exception(@"C:\Users\PrivateName\device") : new WmiClassSchema(name, WmiSchemaStatus.Found) };
            var report = WmiSchemaInspector.Inspect(source);
            Equal(3, source.Calls.Count); Equal(WmiSchemaStatus.ReadError, report.Classes[0].Status); Equal(WmiSchemaStatus.Found, report.Classes[1].Status);
            Check(!report.ToDisplayText().Contains("PrivateName"), "exception leaked");
        });
        Add("schema null and mismatched source responses fail closed", () =>
        {
            var source = new FakeSchemaSource { Reader = name => name == "WmiAcpiVersion" ? null : new WmiClassSchema("Untrusted", WmiSchemaStatus.Found) };
            Check(WmiSchemaInspector.Inspect(source).Classes.All(c => c.Status == WmiSchemaStatus.ReadError), "untrusted response accepted");
        });
        Add("schema fields disclose identifiers and CIM types only", () =>
        {
            foreach (string name in new[] { @"C:\Users\PrivateName\device", "private\nInjected", "name\u202eexe", "7invalid", new string('A', 97) })
                Equal("InvalidIdentifier", new WmiSchemaField(name, "UInt8").Name);
            Equal("UnknownType", new WmiSchemaField("Bytes", @"C:\PrivateName").TypeName);
            var field = new WmiSchemaField("Bytes", "UInt8", true); Equal("Bytes", field.Name); Check(field.IsArray, "array shape lost");
        });
        Add("schema field and parameter output cannot leak raw input text", () =>
        {
            var schema = new WmiClassSchema("WmiAcpiMethod", WmiSchemaStatus.Found,
                new[] { new WmiSchemaField(@"C:\Users\PrivateName", "secret-type") },
                new[] { new WmiSchemaMethod("CallSabiFunction", new[] { new WmiSchemaField("inData", "Object") }, new[] { new WmiSchemaField("outData", "Object") }) });
            string text = new WmiSchemaInspectionReport(new[] { schema }).ToDisplayText();
            Check(!text.Contains("PrivateName") && !text.Contains("secret-type"), "untrusted schema text leaked");
            Check(text.Contains("CallSabiFunction (호출하지 않음)") && text.Contains("inData") && text.Contains("outData"), "method shape omitted");
        });
        Add("schema property and method collections are bounded", () =>
        {
            var schema = new WmiClassSchema("WmiAcpiMethod", WmiSchemaStatus.Found,
                Enumerable.Range(0, 100).Select(i => new WmiSchemaField("Property" + i, "UInt8")),
                Enumerable.Range(0, 100).Select(i => new WmiSchemaMethod("Method" + i)));
            Equal(WmiSchemaPolicy.MaxProperties, schema.Properties.Length); Equal(WmiSchemaPolicy.MaxMethods, schema.Methods.Length); Check(schema.Truncated, "truncation hidden");
        });
        Add("schema parameter collections are bounded and explicit", () =>
        {
            var fields = Enumerable.Range(0, 100).Select(i => new WmiSchemaField("Arg" + i, "UInt8"));
            var method = new WmiSchemaMethod("CallSabiFunction", fields, fields);
            Equal(WmiSchemaPolicy.MaxParameters, method.Inputs.Length); Equal(WmiSchemaPolicy.MaxParameters, method.Outputs.Length); Check(method.Truncated, "truncation hidden");
        });
        Add("schema errors cannot display stale successful fields", () =>
        {
            var schema = new WmiClassSchema("WmiAcpiMethod", WmiSchemaStatus.AccessDenied, new[] { new WmiSchemaField("Stale", "String") }, new[] { new WmiSchemaMethod("StaleMethod") });
            Equal(0, schema.Properties.Length); Equal(0, schema.Methods.Length);
        });
        Add("schema public arrays cannot mutate stored report", () =>
        {
            var field = new WmiSchemaField("Bytes", "UInt8");
            var method = new WmiSchemaMethod("CallSabiFunction", new[] { field });
            var schema = new WmiClassSchema("WmiAcpiMethod", WmiSchemaStatus.Found, new[] { field }, new[] { method });
            var report = new WmiSchemaInspectionReport(new[] { schema });
            schema.Properties[0] = null; schema.Methods[0] = null; method.Inputs[0] = null; report.Classes[0] = null;
            Check(schema.Properties[0] != null && schema.Methods[0] != null && method.Inputs[0] != null && report.Classes[0] != null, "mutable arrays exposed");
        });
        Add("schema unknown enum fails closed", () => Equal(WmiSchemaStatus.ReadError, new WmiClassSchema("WmiAcpiMethod", (WmiSchemaStatus)999).Status));
        Add("schema report is included in detailed hardware diagnostic", () =>
        {
            var schema = WmiSchemaInspector.Inspect(new FakeSchemaSource());
            var report = new HardwareProbeReport(oemWmiSchema: schema);
            Check(report.ToDisplayText().Contains("WmiAcpiMethod") && !report.HardwareWriteAllowed, "detailed report misses schema");
        });
    }

    private sealed class FakeSchemaSource : IWmiSchemaSource
    {
        public readonly List<string> Calls = new List<string>();
        public Func<string, WmiClassSchema> Reader = name => new WmiClassSchema(name, WmiSchemaStatus.Found);
        public WmiClassSchema ReadClass(string className) { Calls.Add(className); return Reader(className); }
    }
}
