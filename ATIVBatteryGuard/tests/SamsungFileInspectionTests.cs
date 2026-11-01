using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json.Nodes;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterSamsungFileInspectionTests()
    {
        Add("SABI name presence is typed metadata and never device or firmware access", () =>
        {
            foreach(SabiDriverLinkStatus status in Enum.GetValues(typeof(SabiDriverLinkStatus)))
            {
                var report=new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete,new[]{InspectionEntry()},driverLink:status);
                var decoded=SamsungFileInspectionProtocol.Decode(SamsungFileInspectionProtocol.Encode(report));
                Equal(status,decoded.DriverLink);
                Check(!decoded.HardwareWriteAllowed && !Sabi3PreparationAssessment.Evaluate(decoded).CanReadHardware,"name presence enabled hardware access");
                Check(decoded.ToDisplayText().Contains(SamsungFileInspectionReport.DriverLinkText(status)),"name state omitted");
            }
            Equal(SabiDriverLinkStatus.Unavailable,new SamsungFileInspectionReport(driverLink:(SabiDriverLinkStatus)999).DriverLink);
        });
        Add("SABI name result rejects unknown missing and old IPC states", () =>
        {
            AssertInvalidInspectionPacket(MutateInspectionPacket(root=>root.Remove("DriverLink")));
            AssertInvalidInspectionPacket(MutateInspectionPacket(root=>root["DriverLink"]=999));
            AssertInvalidInspectionPacket(MutateInspectionPacket(root=>root["Version"]=2));
        });
        Add("observed x64 Sabi3 metadata prepares architecture without promoting hardware access", () =>
        {
            var pe64 = new PeModuleInfo(true, false, "x64", new[] { "MSVCR90.dll" }, InspectionPe().ExportedNames);
            var a = InspectionEntry(hash: "09a9714f0e11734872d60f2966edf8590ca721f0c05b2ca852a0bf20d6c006ae", pe: pe64);
            var b = InspectionEntry(hash: "d8ac306fa192d1d41591d0c846f1b0dfdfd4c2465752a671797ace2e6d824d3a", pe: InspectionPe());
            var report = new SamsungFileInspectionReport(SamsungFileInspectionStatus.Partial, new[] { a, b, a }, limited: true);
            var result = Sabi3PreparationAssessment.Evaluate(report);
            Equal(1, result.NativeX64Candidates); Equal(1, result.NativeX86Candidates);
            Equal(1, result.X64CandidatesWithExpectedNames);
            Check(result.SearchIncomplete && !result.CanReadHardware && !result.CanWriteHardware, "candidate enables device access");
            Check(report.ToDisplayText().Contains("초기화 부작용") && report.ToDisplayText().Contains("실제 충전 제어: 미지원"), "metadata confused with readback");
        });
        Add("analyzed x64 Sabi3 exports cannot override a missing observed device path", () =>
        {
            var file = InspectionEntry(hash: Sabi3X64Abi.AnalyzedSha256,
                pe: new PeModuleInfo(true, false, "x64", exportedNames: InspectionPe().ExportedNames));
            var report = new SamsungFileInspectionReport(SamsungFileInspectionStatus.Partial, new[] { file },
                limited: true, driverLink: SabiDriverLinkStatus.NotFound);
            var decoded = SamsungFileInspectionProtocol.Decode(SamsungFileInspectionProtocol.Encode(report));
            var result = Sabi3PreparationAssessment.Evaluate(decoded);
            Equal(1, result.NativeX64Candidates); Equal(1, result.X64CandidatesWithExpectedNames);
            string text = result.ToDisplayText();
            Check(text.Contains("필요한 SABI 경로를 확인하지 못했습니다") &&
                text.Contains("초기화 가능으로 판정하지 않습니다"), "exports obscured the missing observed path");
            Check(text.Contains("드라이버 미설치나 펌웨어 기능 부재를 확정하지 않습니다"), "name absence became a hardware impossibility claim");
            Check(!result.CanReadHardware && !result.CanWriteHardware && !decoded.HardwareWriteAllowed, "missing path enabled hardware access");
        });
        Add("analyzed x64 Sabi3 distinguishes observed names failures and unperformed lookup", () =>
        {
            var file = InspectionEntry(hash: Sabi3X64Abi.AnalyzedSha256,
                pe: new PeModuleInfo(true, false, "x64", exportedNames: InspectionPe().ExportedNames));
            var expected = new Dictionary<SabiDriverLinkStatus, string>
            {
                { SabiDriverLinkStatus.Present, "장치 접근·초기화·배터리 기능 지원은 미검증" },
                { SabiDriverLinkStatus.AccessDenied, "이름 조회 권한이 없어" },
                { SabiDriverLinkStatus.Unavailable, "이름 조회 결과를 확인하지 못해" },
                { SabiDriverLinkStatus.UnsupportedPlatform, "이 플랫폼에서는 Windows SABI 이름 조회를 지원하지 않아" },
                { SabiDriverLinkStatus.NotChecked, "SABI 이름 조회를 수행하지 않아" }
            };
            foreach (var state in expected)
            {
                var result = Sabi3PreparationAssessment.Evaluate(new SamsungFileInspectionReport(
                    SamsungFileInspectionStatus.Complete, new[] { file }, driverLink: state.Key));
                string text = result.ToDisplayText();
                Check(text.Contains(state.Value), "lookup state was lost: " + state.Key);
                Check(!text.Contains("현재 이름 조회에서는 필요한 SABI 경로를 확인하지 못했습니다"), "lookup failure was converted to absence");
                Check(!result.CanReadHardware && !result.CanWriteHardware, "lookup state enabled hardware access");
            }
        });
        Add("device path contract is not attributed to other hashes architectures or managed files", () =>
        {
            foreach (var file in new[]
            {
                InspectionEntry(hash: new string('b', 64), pe: new PeModuleInfo(true, false, "x64", exportedNames: InspectionPe().ExportedNames)),
                InspectionEntry(hash: Sabi3X64Abi.AnalyzedSha256, pe: InspectionPe()),
                InspectionEntry(hash: Sabi3X64Abi.AnalyzedSha256, pe: new PeModuleInfo(true, true, "x64", exportedNames: InspectionPe().ExportedNames))
            })
            {
                var result = Sabi3PreparationAssessment.Evaluate(new SamsungFileInspectionReport(
                    SamsungFileInspectionStatus.Complete, new[] { file }, driverLink: SabiDriverLinkStatus.NotFound));
                Check(!result.ToDisplayText().Contains("정적 분석된 x64 DLL의 초기화에는"), "unreviewed file inherited the analyzed device contract");
                Check(!result.CanReadHardware && !result.CanWriteHardware, "unreviewed file enabled hardware access");
            }
        });
        Add("managed and conflicting Sabi3 metadata cannot silently choose a native implementation", () =>
        {
            var managed = InspectionEntry(pe: new PeModuleInfo(true, true, "x64", exportedNames: InspectionPe().ExportedNames));
            Equal(0, Sabi3PreparationAssessment.Evaluate(new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, new[] { managed })).NativeX64Candidates);
            var a = InspectionEntry(hash: new string('a',64), pe: new PeModuleInfo(true, false,"x64", exportedNames: InspectionPe().ExportedNames));
            var b = InspectionEntry(hash: new string('b',64), pe: new PeModuleInfo(true, false,"x64", exportedNames: new[] { "CallBIOSInterface" }));
            var result = Sabi3PreparationAssessment.Evaluate(new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, new[] { a, b }));
            Equal(2, result.NativeX64Candidates); Equal(1, result.X64CandidatesWithExpectedNames);
            Check(result.ToDisplayText().Contains("첫 번째 파일") && !result.CanReadHardware, "ambiguous files selected automatically");
        });
        Add("function imports survive immutable inspection snapshot and typed IPC", () =>
        {
            var functions = new[] { new PeImportedFunction("KERNEL32.dll", "DeviceIoControl"), new PeImportedFunction("MSVCR90.dll", null, 17) };
            var pe = new PeModuleInfo(true, false, "x64", importedFunctions: functions);
            var entry = InspectionEntry(pe: pe); functions[0] = null; pe.ImportedFunctions[0] = null;
            var result = SamsungFileInspectionProtocol.Decode(SamsungFileInspectionProtocol.Encode(new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, new[] { entry })));
            Equal(2, result.Entries[0].Pe.ImportedFunctions.Length);
            Equal("DeviceIoControl", result.Entries[0].Pe.ImportedFunctions[0].FunctionName);
            Equal<int?>(17, result.Entries[0].Pe.ImportedFunctions[1].Ordinal);
            Check(result.ToDisplayText().Contains("실행됐다는 증거가 아닙니다") && !result.HardwareWriteAllowed, "static import promoted to behavior");
        });
        Add("function IPC rejects paths invalid ordinals duplicates and oversized lists", () =>
        {
            foreach (var f in new[] {
                new JsonObject { ["ModuleName"]="C:\\private.dll",["FunctionName"]="ReadFile",["Ordinal"]=null },
                new JsonObject { ["ModuleName"]="KERNEL32.dll",["FunctionName"]="ReadFile",["Ordinal"]=1 },
                new JsonObject { ["ModuleName"]="KERNEL32.dll",["FunctionName"]="",["Ordinal"]=65536 },
                new JsonObject { ["ModuleName"]="KERNEL32.dll",["FunctionName"]="ReadFile" } })
                AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["Entries"][0]["Functions"] = new JsonArray(f.DeepClone())));
            var valid = new JsonObject { ["ModuleName"]="KERNEL32.dll",["FunctionName"]="ReadFile",["Ordinal"]=null };
            foreach (int count in new[] { 2, 257 })
                AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["Entries"][0]["Functions"] = new JsonArray(Enumerable.Range(0,count).Select(i => valid.DeepClone()).ToArray())));
        });
        Add("maximum function metadata fits bounded version two protocol", () =>
        {
            var functions = Enumerable.Range(0,256).Select(i => new PeImportedFunction(new string('m',124)+".dll", "F"+i.ToString("D3")+new string('x',124))).ToArray();
            var pe = new PeModuleInfo(true, false, "x64", Enumerable.Range(0,64).Select(i=>"m"+i+".dll"),
                Enumerable.Range(0,128).Select(i=>"f"+i+new string('x',120)), importedFunctions:functions);
            var entry = InspectionEntry(pe:pe, description:new string('한',120));
            var report = new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, Enumerable.Repeat(entry,16));
            byte[] bytes = SamsungFileInspectionProtocol.Encode(report);
            Check(bytes.Length > 524288 && bytes.Length <= SamsungFileInspectionProtocol.MaximumBytes, "function quota not exercised");
            var result = SamsungFileInspectionProtocol.Decode(bytes);
            Equal(16,result.Entries.Length); Equal(256,result.Entries[15].Pe.ImportedFunctions.Length);
        });
        Add("file inspection parses actual PE import and export tables before reporting metadata", () =>
        {
            byte[] bytes = InspectionPeBytes();
            var parsed = PeModuleReader.Read(bytes);
            Check(parsed.IsValid && !parsed.IsManaged, "valid synthetic PE rejected");
            Equal("x86", parsed.Architecture); Equal("Sabi3.dll", parsed.ImportedModules.Single());
            Equal("CallBIOSInterface", parsed.ExportedNames.Single());
            string hash;
            using (var algorithm = System.Security.Cryptography.SHA256.Create())
                hash = Convert.ToHexString(algorithm.ComputeHash(bytes)).ToLowerInvariant();
            var report = new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete,
                new[] { InspectionEntry(length: bytes.Length, hash: hash, pe: parsed) });
            var decoded = SamsungFileInspectionProtocol.Decode(SamsungFileInspectionProtocol.Encode(report));
            Equal("Sabi3.dll", decoded.Entries[0].Pe.ImportedModules.Single());
            Equal("CallBIOSInterface", decoded.Entries[0].Pe.ExportedNames.Single());
            Check(decoded.ToDisplayText().Contains("CallBIOSInterface") && !decoded.HardwareWriteAllowed,
                "real PE facts omitted or interpreted as hardware support");
        });
        Add("file inspection rejects malformed PE names and RVAs without retaining partial imports", () =>
        {
            var malformed = new List<byte[]>();
            var badImportRva = InspectionPeBytes(); InspectionPut32(badImportRva, 0x20c, uint.MaxValue); malformed.Add(badImportRva);
            var badExportRva = InspectionPeBytes(); InspectionPut32(badExportRva, 0x444, uint.MaxValue); malformed.Add(badExportRva);
            var unterminated = InspectionPeBytes(); Array.Fill(unterminated, (byte)'A', 0x340, 129); malformed.Add(unterminated);
            malformed.Add(InspectionPeBytes().Take(1024).ToArray());
            foreach (byte[] bytes in malformed)
            {
                var parsed = PeModuleReader.Read(bytes);
                Check(!parsed.IsValid && parsed.ImportedModules.Length == 0 && parsed.ExportedNames.Length == 0,
                    "malformed PE retained earlier successful import/export data");
                Equal("Unknown", parsed.Architecture);
                var failed = new SamsungFileInspectionEntry("BatteryToast.exe", "Setting", SamsungFileEntryStatus.InvalidPe,
                    bytes.Length, "old version", sha256: new string('a', 64), pe: parsed);
                Equal(0L, failed.Length); Equal(string.Empty, failed.FileVersion);
                Check(!failed.Pe.IsValid && !failed.HardwareWriteAllowed, "invalid PE promoted to usable metadata");
            }
        });
        Add("file inspection accepts only four fixed target basenames and location labels", () =>
        {
            foreach (string name in new[] { "Sabi3.dll", "wsabi.dll", "BatteryToast.exe", "PowerAudit.exe" })
                Equal(name, new SamsungFileInspectionEntry(name.ToUpperInvariant(), "Setting", SamsungFileEntryStatus.NotFound).FileName);
            foreach (string name in new[] { null, "", "Other.dll", @"C:\Sabi3.dll", "../wsabi.dll", "Sabi3.dll:stream", "Sabi3.dll " })
                BatteryThrows<ArgumentException>(() => new SamsungFileInspectionEntry(name, "Setting", SamsungFileEntryStatus.NotFound));
            foreach (string label in new[] { "Setting", "Settings", "Setting 하위 폴더", "Settings 하위 폴더" })
                Equal(label, new SamsungFileInspectionEntry("Sabi3.dll", label, SamsungFileEntryStatus.NotFound).LocationLabel);
            foreach (string label in new[] { null, "", "setting", @"C:\Program Files\Samsung\Setting", "Setting/PrivateName" })
                BatteryThrows<ArgumentException>(() => new SamsungFileInspectionEntry("Sabi3.dll", label, SamsungFileEntryStatus.NotFound));
        });
        Add("file inspection metadata redacts paths control characters and oversize text", () =>
        {
            foreach (string unsafeText in new[] { @"C:\Users\PrivateName\module", "https://example.test", "line\nprivate", "tab\tprivate", "rtl\u202eprivate", new string('x', 121) })
            {
                var entry = InspectionEntry(fileVersion: unsafeText, company: unsafeText, description: unsafeText);
                Equal(string.Empty, entry.FileVersion); Equal(string.Empty, entry.CompanyName); Equal(string.Empty, entry.Description);
                Check(!new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, new[] { entry }).ToDisplayText().Contains(unsafeText), "private metadata retained");
            }
            Equal("Samsung Electronics Co., Ltd.", InspectionEntry(company: "Samsung Electronics Co., Ltd.").CompanyName);
            Equal("삼성 설정 (x86)", InspectionEntry(description: "삼성 설정 (x86)").Description);
        });
        Add("file inspection failures clear earlier versions PE hashes and signatures", () =>
        {
            foreach (SamsungFileEntryStatus status in Enum.GetValues(typeof(SamsungFileEntryStatus)))
            {
                if (status == SamsungFileEntryStatus.Inspected) continue;
                var entry = new SamsungFileInspectionEntry("Sabi3.dll", "Setting", status, 4096,
                    "2.2", "2.2", "Samsung", "old observation", new string('a', 64), InspectionPe(), OfflineSignatureStatus.ValidOffline);
                Equal(0L, entry.Length); Equal(string.Empty, entry.FileVersion); Equal(string.Empty, entry.ProductVersion);
                Equal(string.Empty, entry.CompanyName); Equal(string.Empty, entry.Description); Equal(string.Empty, entry.Sha256);
                Check(!entry.Pe.IsValid && entry.Pe.ImportedModules.Length == 0 && entry.Pe.ExportedNames.Length == 0, "stale PE result retained");
                Equal(OfflineSignatureStatus.NotChecked, entry.Signature); Check(!entry.HardwareWriteAllowed, "failure grants hardware access");
            }
            var invalid = new SamsungFileInspectionEntry("Sabi3.dll", "Setting", (SamsungFileEntryStatus)999);
            Equal(SamsungFileEntryStatus.Unavailable, invalid.Status);
        });
        Add("file inspection success requires bounded size valid PE architecture and SHA256", () =>
        {
            foreach (long length in new[] { -1L, 0L, (long)SamsungFileInspectionReport.MaximumFileBytes + 1, long.MaxValue })
                Equal(SamsungFileEntryStatus.Unavailable, InspectionEntry(length: length).Status);
            foreach (string hash in new[] { null, "", new string('a', 63), new string('g', 64), new string('a', 65) })
                Equal(SamsungFileEntryStatus.Unavailable, InspectionEntry(hash: hash).Status);
            var invalidPe = new SamsungFileInspectionEntry("Sabi3.dll", "Setting", SamsungFileEntryStatus.Inspected, 4096,
                sha256: new string('a', 64), pe: new PeModuleInfo(true, false, "arm64"));
            Equal(SamsungFileEntryStatus.Unavailable, invalidPe.Status);
            Equal(SamsungFileEntryStatus.Inspected, InspectionEntry(length: SamsungFileInspectionReport.MaximumFileBytes).Status);
            Equal(new string('a', 64), InspectionEntry(hash: new string('A', 64)).Sha256);
        });
        Add("file inspection snapshots returned arrays and removes arbitrary PE errors", () =>
        {
            var imports = new[] { "Sabi3.dll" }; var exports = new[] { "CallBIOSInterface" };
            var pe = new PeModuleInfo(true, true, "x86", imports, exports, @"C:\Users\PrivateName\parser-error");
            var entry = InspectionEntry(pe: pe);
            imports[0] = "Changed.dll"; exports[0] = "Changed";
            entry.Pe.ImportedModules[0] = "Changed.dll"; entry.Pe.ExportedNames[0] = "Changed";
            Equal("Sabi3.dll", entry.Pe.ImportedModules[0]); Equal("CallBIOSInterface", entry.Pe.ExportedNames[0]);
            var input = new[] { entry }; var report = new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, input);
            input[0] = null; report.Entries[0] = null;
            Equal(entry, report.Entries[0]);
            string text = report.ToDisplayText();
            Check(!text.Contains("PrivateName") && text.Contains("PE 구조: x86") && text.Contains("실제 실행 비트 수"), "private PE error or managed architecture claim");
        });
        Add("file inspection reports bound enumeration and discard stale entries on failure", () =>
        {
            var entry = InspectionEntry();
            foreach (SamsungFileInspectionStatus status in Enum.GetValues(typeof(SamsungFileInspectionStatus)))
            {
                if (status == SamsungFileInspectionStatus.Complete || status == SamsungFileInspectionStatus.Partial) continue;
                Equal(0, new SamsungFileInspectionReport(status, new[] { entry }).Entries.Length);
            }
            Equal(SamsungFileInspectionStatus.InvalidResponse, new SamsungFileInspectionReport((SamsungFileInspectionStatus)999, new[] { entry }).Status);
            Equal(SamsungFileInspectionStatus.InvalidResponse, new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, new SamsungFileInspectionEntry[] { null }).Status);
            Equal(SamsungFileInspectionStatus.DirectoryNotFound, new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete).Status);
            int visited = 0;
            var limited = new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, BoundedInspectionEntries(() => visited++));
            Equal(16, limited.Entries.Length); Equal(17, visited); Check(limited.Limited, "entry limit hidden");
        });
        Add("file inspection role and signature text never imply verified battery control", () =>
        {
            foreach (OfflineSignatureStatus signature in Enum.GetValues(typeof(OfflineSignatureStatus)))
            {
                var entry = InspectionEntry(signature: signature);
                var report = new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, new[] { entry });
                string text = report.ToDisplayText();
                Check(!report.HardwareWriteAllowed && !entry.HardwareWriteAllowed && text.Contains("실제 충전 제어: 미지원"), "signature grants control");
                Check(text.Contains("온라인 인증서 폐기 여부는 확인하지 않습니다") && text.Contains("실제 기능은 미확인"), "offline or filename caveats missing");
                Check(text.Contains("CallBIOSInterface") && text.Contains("일치 여부만으로 호출하지 않습니다"), "export discovery authorizes invocation");
            }
        });
        Add("file inspection IPC round trips statuses entries and complete metadata", () =>
        {
            foreach (SamsungFileInspectionStatus status in Enum.GetValues(typeof(SamsungFileInspectionStatus)))
            {
                var report = new SamsungFileInspectionReport(status, new[] { InspectionEntry() }, true);
                var copy = SamsungFileInspectionProtocol.Decode(SamsungFileInspectionProtocol.Encode(report));
                Equal(report.Status, copy.Status); Equal(report.Limited, copy.Limited); Equal(report.Entries.Length, copy.Entries.Length);
                Check(!copy.HardwareWriteAllowed, "decoded report grants hardware access");
            }
            var actual = SamsungFileInspectionProtocol.Decode(SamsungFileInspectionProtocol.Encode(InspectionReport())).Entries[0];
            Equal("Sabi3.dll", actual.FileName); Equal("Setting", actual.LocationLabel); Equal(4096L, actual.Length);
            Equal("2.2.0", actual.FileVersion); Equal("2.2.0", actual.ProductVersion); Equal("Samsung", actual.CompanyName);
            Equal("Samsung BIOS Interface", actual.Description); Equal(new string('a', 64), actual.Sha256);
            Equal(OfflineSignatureStatus.ValidOffline, actual.Signature); Equal("x86", actual.Pe.Architecture);
            Check(actual.Pe.ExportedNames.Contains("CallBIOSInterface") && actual.Pe.ImportedModules.Contains("kernel32.dll"), "PE data lost in IPC");
            foreach (SamsungFileEntryStatus status in Enum.GetValues(typeof(SamsungFileEntryStatus)))
            {
                var e = status == SamsungFileEntryStatus.Inspected ? InspectionEntry() : new SamsungFileInspectionEntry("wsabi.dll", "Settings", status);
                var r = new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, new[] { e });
                Equal(status, SamsungFileInspectionProtocol.Decode(SamsungFileInspectionProtocol.Encode(r)).Entries[0].Status);
            }
        });
        Add("file inspection maximum valid metadata fits bounded IPC without discovery truncation", () =>
        {
            var imports = Enumerable.Range(0, 64).Select(i => "m" + i.ToString("D3") + new string('x', 120) + ".dll").ToArray();
            var exports = Enumerable.Range(0, 128).Select(i => "f" + i.ToString("D3") + new string('x', 124)).ToArray();
            var pe = new PeModuleInfo(true, false, "x64", imports, exports);
            string metadata = new string('한', 120);
            var entry = new SamsungFileInspectionEntry("Sabi3.dll", "Setting 하위 폴더", SamsungFileEntryStatus.Inspected,
                SamsungFileInspectionReport.MaximumFileBytes, metadata, metadata, metadata, metadata, new string('f', 64), pe, OfflineSignatureStatus.ValidOffline);
            var report = new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, Enumerable.Repeat(entry, 16));
            byte[] bytes = SamsungFileInspectionProtocol.Encode(report);
            Check(bytes.Length > 262144 && bytes.Length <= SamsungFileInspectionProtocol.MaximumBytes, "maximum payload test not exercising protocol bound");
            var result = SamsungFileInspectionProtocol.Decode(bytes);
            Equal(SamsungFileInspectionStatus.Complete, result.Status); Equal(16, result.Entries.Length);
            Equal(64, result.Entries[15].Pe.ImportedModules.Length); Equal(128, result.Entries[15].Pe.ExportedNames.Length);
            Equal(metadata, result.Entries[15].Description);
        });
        Add("file inspection IPC rejects missing fields unsupported targets and invalid typed facts", () =>
        {
            AssertInvalidInspectionPacket(MutateInspectionPacket(root => root.Remove("Version")));
            foreach (string field in new[] { "FileName", "Length", "FileVersion", "Sha256", "Signature", "PeValid", "Imports", "Exports", "Functions" })
                AssertInvalidInspectionPacket(MutateInspectionPacket(root => ((JsonObject)root["Entries"][0]).Remove(field)));
            AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["Version"] = 1));
            AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["Status"] = 999));
            foreach (var mutation in new Action<JsonObject>[] {
                entry => entry["FileName"] = "Other.dll", entry => entry["LocationLabel"] = @"C:\Users\PrivateName",
                entry => entry["Status"] = 999, entry => entry["Signature"] = 999, entry => entry["Length"] = long.MaxValue,
                entry => entry["Sha256"] = new string('g',64), entry => entry["Description"] = @"C:\Users\PrivateName\value",
                entry => entry["CompanyName"] = "a\nb", entry => entry["FileVersion"] = new string('a',121),
                entry => entry["PeArchitecture"] = "arm64", entry => entry["Imports"] = new JsonArray(@"C:\private.dll"),
                entry => entry["Exports"] = new JsonArray("unsafe/name"), entry => entry["Description"] = null })
                AssertInvalidInspectionPacket(MutateInspectionPacket(root => mutation((JsonObject)root["Entries"][0])));
            AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["Entries"][0]["Status"] = (int)SamsungFileEntryStatus.AccessDenied));
        });
        Add("file inspection IPC rejects malformed framing quotas and invalid UTF8", () =>
        {
            foreach (byte[] bytes in new[] { null, new byte[0], new byte[SamsungFileInspectionProtocol.MaximumBytes + 1], new byte[] { 0xff, 0xfe }, Encoding.UTF8.GetBytes("[]") })
                AssertInvalidInspectionPacket(bytes, "null, byte bound, UTF8, or root array; length=" + (bytes == null ? -1 : bytes.Length));
            byte[] valid = SamsungFileInspectionProtocol.Encode(InspectionReport());
            string json = Encoding.UTF8.GetString(valid);
            foreach (string suffix in new[] { "{}", " true", "garbage", "\0", json })
                AssertInvalidInspectionPacket(Encoding.UTF8.GetBytes(json + suffix), "trailing data length=" + suffix.Length);
            Equal(SamsungFileInspectionStatus.Complete, SamsungFileInspectionProtocol.Decode(Encoding.UTF8.GetBytes("\r\n " + json + " \t")).Status);
            AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["Entries"] = new JsonArray(Enumerable.Range(0,17).Select(i => root["Entries"][0].DeepClone()).ToArray())), "17 entries");
            AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["Entries"][0]["Imports"] = new JsonArray(Enumerable.Range(0,65).Select(i => (JsonNode)JsonValue.Create("a"+i+".dll")).ToArray())), "65 imports");
            AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["Unknown"] = new string('x', 129)), "unknown string with129characters");
            Equal(SamsungFileInspectionStatus.Complete, SamsungFileInspectionProtocol.Decode(
                MutateInspectionPacket(root => root["Unknown"] = new string('한', 128))).Status);
            AssertInvalidInspectionPacket(MutateInspectionPacket(root => root["Unknown"] = new string('한', 129)), "escaped Unicode string with129characters");
            Equal(SamsungFileInspectionStatus.Complete, SamsungFileInspectionProtocol.Decode(
                MutateInspectionPacket(root => root["Entries"][0]["Description"] = new string('한', 120))).Status);
            AssertInvalidInspectionPacket(MutateInspectionPacket(root =>
            {
                JsonNode node = JsonValue.Create(0);
                for (int i=0; i<17; i++) node = new JsonObject { ["nested"] = node };
                root["Unknown"] = node;
            }), "unknown object depth17");
        });
        Add("file inspection IPC strips unknown private fields without retaining raw uploads", () =>
        {
            byte[] bytes = MutateInspectionPacket(root =>
            {
                root["OriginalPath"] = @"C:\Users\PrivateName\Setting";
                root["Exception"] = "private-exception";
                root["Entries"][0]["SerialNumber"] = "private-serial";
                root["Escaped"] = "quote: \" slash: \\ braces: }{][";
            });
            var result = SamsungFileInspectionProtocol.Decode(bytes);
            Equal(SamsungFileInspectionStatus.Complete, result.Status);
            string output = result.ToDisplayText() + Encoding.UTF8.GetString(SamsungFileInspectionProtocol.Encode(result));
            Check(!output.Contains("PrivateName") && !output.Contains("private-exception") && !output.Contains("private-serial"), "unknown private fields survived IPC");
            Check(!result.HardwareWriteAllowed, "unknown payload grants hardware access");
        });
    }

    private static PeModuleInfo InspectionPe()
    {
        return new PeModuleInfo(true, false, "x86", new[] { "kernel32.dll" }, new[] { "InitBIOSInterface", "UninitBIOSInterface", "CheckSamsung", "CallBIOSInterface", "CallBIOSInterfaceEx" });
    }

    private static byte[] InspectionPeBytes()
    {
        var bytes = new byte[4096];
        Array.Copy(MinimalPe(), bytes, 1024);
        int section = 0x98 + 0xe0;
        InspectionPut32(bytes, section + 8, 0xe00); InspectionPut32(bytes, section + 16, 0xe00);
        // File offset 0x200 maps to RVA0x1000. One import descriptor followed by a null descriptor.
        InspectionPut32(bytes, 0x98 + 96 + 8, 0x1000); InspectionPut32(bytes, 0x98 + 96 + 12, 40);
        InspectionPut32(bytes, 0x200, 0x1100); InspectionPut32(bytes, 0x20c, 0x1140); InspectionPut32(bytes, 0x210, 0x1100);
        Array.Copy(Encoding.ASCII.GetBytes("Sabi3.dll\0"), 0, bytes, 0x340, 10);
        // A single named export and its address/name/ordinal tables.
        InspectionPut32(bytes, 0x98 + 96, 0x1200); InspectionPut32(bytes, 0x98 + 100, 0x100);
        InspectionPut32(bytes, 0x400 + 20, 1); InspectionPut32(bytes, 0x400 + 24, 1);
        InspectionPut32(bytes, 0x400 + 28, 0x1240); InspectionPut32(bytes, 0x400 + 32, 0x1244); InspectionPut32(bytes, 0x400 + 36, 0x1248);
        InspectionPut32(bytes, 0x440, 0x1400); InspectionPut32(bytes, 0x444, 0x1260);
        byte[] function = Encoding.ASCII.GetBytes("CallBIOSInterface\0");
        Array.Copy(function, 0, bytes, 0x460, function.Length);
        return bytes;
    }

    private static void InspectionPut32(byte[] bytes, int offset, uint value)
    {
        for (int i=0; i<4; i++) bytes[offset+i] = (byte)(value >> (i*8));
    }

    private static SamsungFileInspectionEntry InspectionEntry(long length = 4096, string fileVersion = "2.2.0", string company = "Samsung",
        string description = "Samsung BIOS Interface", string hash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        PeModuleInfo pe = null, OfflineSignatureStatus signature = OfflineSignatureStatus.ValidOffline)
    {
        return new SamsungFileInspectionEntry("Sabi3.dll", "Setting", SamsungFileEntryStatus.Inspected, length, fileVersion, "2.2.0", company, description,
            hash, pe ?? InspectionPe(), signature);
    }

    private static SamsungFileInspectionReport InspectionReport()
    {
        return new SamsungFileInspectionReport(SamsungFileInspectionStatus.Complete, new[] { InspectionEntry() });
    }

    private static byte[] MutateInspectionPacket(Action<JsonObject> mutation)
    {
        var root = (JsonObject)JsonNode.Parse(SamsungFileInspectionProtocol.Encode(InspectionReport()));
        mutation(root);
        return Encoding.UTF8.GetBytes(root.ToJsonString());
    }

    private static void AssertInvalidInspectionPacket(byte[] bytes, string context = "packet")
    {
        var report = SamsungFileInspectionProtocol.Decode(bytes);
        Check(report.Status == SamsungFileInspectionStatus.InvalidResponse,
            "inspection " + context + " returned " + report.Status + " instead of InvalidResponse");
        Equal(0, report.Entries.Length);
        Check(!report.HardwareWriteAllowed, "invalid inspection packet authorizes write");
    }

    private static IEnumerable<SamsungFileInspectionEntry> BoundedInspectionEntries(Action visit)
    {
        for (int i=0; i<17; i++) { visit(); yield return InspectionEntry(); }
        throw new Exception("inspection entry enumeration exceeded bounded lookahead");
    }
}
