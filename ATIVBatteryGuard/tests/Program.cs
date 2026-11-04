using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Hardware;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using ATIVBatteryGuard.Services;
using ATIVBatteryGuard.ViewModels;

internal static partial class Program
{
    private static readonly List<KeyValuePair<string, Func<Task>>> Tests = new List<KeyValuePair<string, Func<Task>>>();

    private static async Task<int> Main(string[] args)
    {
        if (args.Length != 0 && (args.Length != 2 || args[0] != "--report"))
        {
            Console.Error.WriteLine("Usage: PortableTests [--report path.json]");
            return 2;
        }
        RegisterTests();
        int passed = 0;
        int failed = 0;
        int skipped = 0;
        foreach (var test in Tests)
        {
            try { await test.Value().WaitAsync(TimeSpan.FromSeconds(20)); passed++; Console.WriteLine("PASS " + test.Key); }
            catch (SkippedTestException ex) { skipped++; Console.WriteLine("SKIP " + test.Key + ": " + ex.Message); }
            catch (Exception ex) { failed++; Console.Error.WriteLine("FAIL " + test.Key + ": " + ex.Message); }
        }
        Console.WriteLine("RESULT " + passed + " passed, " + failed + " failed, " + skipped + " skipped (" + Tests.Count + " registered)");
        if (args.Length == 2)
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[1])));
                File.WriteAllText(args[1], System.Text.Json.JsonSerializer.Serialize(new { passed, failed, skipped, registered = Tests.Count, suite = "reconstructed-portable-safety-regressions" }));
            }
            catch (Exception ex) { Console.Error.WriteLine("Cannot save test report: " + ex.GetType().Name); return 2; }
        }
        return passed > 0 && failed == 0 ? 0 : 1;
    }

    private static void RegisterTests()
    {
        Add("unsupported exposes no hardware capability", () =>
        {
            var c = new UnsupportedChargeLimitController();
            Check(!c.GetCapabilities().CanWrite && !c.GetCapabilities().CanRead, "capability escalation");
            Equal(ChargeMode.Unsupported, c.GetCurrentMode());
        });
        foreach (ChargeMode mode in Enum.GetValues(typeof(ChargeMode)))
        {
            ChargeMode captured = mode;
            Add("unsupported rejects " + mode, () => Check(!new UnsupportedChargeLimitController().SetMode(captured).Success, "write accepted"));
        }
        Add("unsupported rejects invalid enum", () => Check(!new UnsupportedChargeLimitController().SetMode((ChargeMode)555).Success, "invalid write accepted"));
        Add("mock transitions remain local and separate", () =>
        {
            var a = new MockChargeLimitController(); var b = new MockChargeLimitController();
            Check(a.SetMode(ChargeMode.Protection80).Success, "mock cannot change");
            Equal(ChargeMode.Protection80, a.GetCurrentMode()); Equal(ChargeMode.Normal100, b.GetCurrentMode());
            Check(a.GetCapabilities().Reason.Contains("시뮬레이션"), "simulation labeling missing");
            Check(a.SetMode(ChargeMode.Normal100).Success, "mock cannot revert");
        });
        Add("mock rejects unknown without losing last state", () =>
        {
            var c = new MockChargeLimitController(); c.SetMode(ChargeMode.Protection80);
            Check(!c.SetMode(ChargeMode.Unknown).Success && !c.SetMode(ChargeMode.Unsupported).Success && !c.SetMode((ChargeMode)555).Success, "invalid mock state accepted");
            Equal(ChargeMode.Protection80, c.GetCurrentMode());
        });
        Add("actual laptop zero percent remains valid", () =>
        {
            var s = new NativePowerReading(true, 1, 6, 0).ToSnapshot();
            Equal<int?>(0, s.Percent); Equal(ExternalPowerStatus.Connected, s.ExternalPower); Equal(BatteryChargeState.NotCharging, s.ChargeState);
        });
        Add("unknown percentage does not become zero", () => Equal<int?>(null, PowerStatusDecoder.Decode(1, 1, 255).Percent));
        Add("unknown flag does not infer charging", () => Equal(BatteryChargeState.Unknown, PowerStatusDecoder.Decode(1, 255, 80).ChargeState));
        Add("no battery clears otherwise plausible percentage", () =>
        {
            var s = PowerStatusDecoder.Decode(1, 128, 80); Equal<int?>(null, s.Percent); Equal(BatteryChargeState.NoBattery, s.ChargeState);
        });
        Add("charging on disconnected AC is unknown", () => Equal(BatteryChargeState.Unknown, PowerStatusDecoder.Decode(0, 8, 45).ChargeState));
        Add("charging and discharging decode separately", () =>
        {
            Equal(BatteryChargeState.Charging, PowerStatusDecoder.Decode(1, 8, 45).ChargeState);
            Equal(BatteryChargeState.Discharging, PowerStatusDecoder.Decode(0, 1, 45).ChargeState);
        });
        Add("reserved flag bits are unknown", () => Equal(BatteryChargeState.Unknown, PowerStatusDecoder.Decode(1, 16, 80).ChargeState));
        Add("native API failure discards raw measurements", () =>
        {
            var s = new NativePowerReading(false, 1, 8, 80, 5).ToSnapshot(); Equal<int?>(null, s.Percent); Equal(BatteryChargeState.Unknown, s.ChargeState);
        });
        Add("missing native fields stay unknown", () => Equal<int?>(null, new NativePowerReading(true, 1, null, 80).ToSnapshot().Percent));
        Add("snapshot rejects out of range percentages", () =>
        {
            Equal<int?>(null, new BatterySnapshot(-1, ExternalPowerStatus.Connected, BatteryChargeState.Charging, null).Percent);
            Equal<int?>(null, new WmiBatteryReading(101, 2).EstimatedChargeRemaining);
        });
        Add("cross check preserves zero without diagnosis", () =>
        {
            string text = BatteryCrossCheck.Format(new NativePowerReading(true, 1, 6, 0), new[] { new WmiBatteryReading(0, 2) });
            Check(text.Contains("0%") && text.Contains("실제 충전 제어: 미지원"), "invalid zero diagnostic");
        });
        Add("multiple batteries do not replace native aggregate", () =>
        {
            string text = BatteryCrossCheck.Format(new NativePowerReading(true, 1, 1, 80), new[] { new WmiBatteryReading(0, 2), new WmiBatteryReading(100, 2) });
            Check(text.Contains("여러 배터리") && text.Contains("대체하지 않습니다"), "unsafe aggregation");
        });
        Add("settings defaults save and reload across stores", () => WithDirectory(dir =>
        {
            var store = new SettingsStore(dir); var initial = store.Load(); Check(initial.CanSave, "default cannot save");
            Equal(ChargeMode.Normal100, initial.Settings.DesiredMode);
            var expected = new AppSettings { DesiredMode = ChargeMode.Protection80, RestoreOnBoot = true, MockModeEnabled = true, LastUiState = "Maximized" };
            Check(store.Save(expected).Success, "save failed");
            var loaded = new SettingsStore(dir).Load(); Equal(ChargeMode.Protection80, loaded.Settings.DesiredMode);
            Check(loaded.Settings.RestoreOnBoot && loaded.Settings.MockModeEnabled, "flags not persisted"); Equal("Maximized", loaded.Settings.LastUiState);
        }));
        Add("settings repeated save leaves valid atomic result", () => WithDirectory(dir =>
        {
            var store = new SettingsStore(dir); store.Load(); Check(store.Save(new AppSettings()).Success, "initial save");
            Check(store.Save(new AppSettings { DesiredMode = ChargeMode.Protection80 }).Success, "replace save");
            Equal(ChargeMode.Protection80, new SettingsStore(dir).Load().Settings.DesiredMode);
            Equal(0, Directory.GetFiles(dir, "*.tmp").Length);
        }));
        Add("settings invalid enum cannot replace file", () => WithDirectory(dir =>
        {
            var store = new SettingsStore(dir); store.Load(); store.Save(new AppSettings()); string before = File.ReadAllText(store.FilePath);
            Check(!store.Save(new AppSettings { DesiredMode = ChargeMode.Unknown }).Success, "invalid setting saved"); Equal(before, File.ReadAllText(store.FilePath));
        }));
        Add("settings future schema is preserved and save blocked", () => WithDirectory(dir =>
        {
            const string data = "{\"schemaVersion\":2,\"desiredMode\":\"Protection80\",\"restoreOnBoot\":false,\"mockModeEnabled\":false,\"lastUiState\":\"Normal\"}";
            string path = Path.Combine(dir, "settings.json"); File.WriteAllText(path, data);
            var store = new SettingsStore(dir); Check(!store.Load().CanSave, "future file unlocked"); Check(!store.Save(new AppSettings()).Success, "future file overwritten"); Equal(data, File.ReadAllText(path));
        }));
        Add("settings malformed JSON preserved as corrupt copy", () => WithDirectory(dir =>
        {
            const string data = "{not-json"; File.WriteAllText(Path.Combine(dir, "settings.json"), data);
            var store = new SettingsStore(dir); var loaded = store.Load();
            Check(loaded.CanSave && loaded.Warning.Length > 0, "corruption not reported");
            var copies = Directory.GetFiles(dir, "settings.corrupt-*.json"); Equal(1, copies.Length); Equal(data, File.ReadAllText(copies[0]));
            Check(store.Save(loaded.Settings).Success, "recovered defaults cannot save");
        }));
        Add("settings oversized input preserved and save blocked", () => WithDirectory(dir =>
        {
            string data = new string('x', 65537); string path = Path.Combine(dir, "settings.json"); File.WriteAllText(path, data);
            var store = new SettingsStore(dir); Check(!store.Load().CanSave, "oversize allowed save"); Equal(data, File.ReadAllText(path));
        }));
        Add("settings externally upgraded file cannot be overwritten", () => WithDirectory(dir =>
        {
            var store = new SettingsStore(dir); store.Load(); store.Save(new AppSettings());
            const string newer = "{\"schemaVersion\":99}"; File.WriteAllText(store.FilePath, newer);
            Check(!store.Save(new AppSettings()).Success, "external upgrade overwritten"); Equal(newer, File.ReadAllText(store.FilePath));
        }));
        Add("numeric enum JSON cannot masquerade as desired mode", () => WithDirectory(dir =>
        {
            File.WriteAllText(Path.Combine(dir, "settings.json"), "{\"schemaVersion\":1,\"desiredMode\":\"2\",\"restoreOnBoot\":false,\"mockModeEnabled\":false,\"lastUiState\":\"Normal\"}");
            var loaded = new SettingsStore(dir).Load();
            Check(loaded.Warning.Length > 0 && Directory.GetFiles(dir, "settings.corrupt-*.json").Length == 1, "numeric enum JSON accepted");
        }));
        Add("settings symlink cannot redirect writes", () => WithDirectory(dir =>
        {
            string target = Path.Combine(dir, "original.json"); File.WriteAllText(target, "keep");
            try { File.CreateSymbolicLink(Path.Combine(dir, "settings.json"), target); }
            catch (UnauthorizedAccessException) { throw new SkippedTestException("this account cannot create a symbolic link"); }
            catch (PlatformNotSupportedException) { throw new SkippedTestException("this platform cannot create a symbolic link"); }
            var store = new SettingsStore(dir); Check(!store.Load().CanSave && !store.Save(new AppSettings()).Success, "symlink write allowed"); Equal("keep", File.ReadAllText(target));
        }));
        Add("log unknown text never captures personal input", () => WithDirectory(dir =>
        {
            var log = new LocalLog(dir); log.Write(@"C:\Users\PrivateName\file.txt"); string text = File.ReadAllText(log.LogPath);
            Check(text.Contains("UNRECOGNIZED_EVENT") && !text.Contains("PrivateName"), "unstructured private log input persisted");
        }));
        Add("network settings paths rejected", () =>
        {
            foreach (string dir in new[] { @"\\server\share\private", "//server/share/private", "https://example.org/settings" })
            {
                var store = new SettingsStore(dir); Check(!store.Load().CanSave && !store.Save(new AppSettings()).Success, "remote path accepted");
            }
        });
        Add("known device is research candidate but never permits write", () =>
        {
            var a = DeviceSupportAssessment.Evaluate(KnownDevice()); Check(a.IsResearchCandidate && !a.HardwareWriteAllowed, "device match enables write");
            Check(!DeviceSupportAssessment.Evaluate(null).HardwareWriteAllowed, "missing device enables write");
        });
        Add("spoofed model prefix is not research match", () =>
        {
            var d = new DeviceDiagnosticsResult("SAMSUNG", "940X3GFAKE", "BIOS", "Windows 10", "10.0", "64-bit"); Check(!DeviceSupportAssessment.Evaluate(d).IsResearchCandidate, "substring matching");
        });
        Add("report does not expose full paths or enable hardware", () =>
        {
            var r = new HardwareProbeReport(oemPrograms: new[] { @"C:\Users\PrivateName\app.exe" });
            Check(!r.HardwareWriteAllowed, "report writes allowed"); Check(!r.ToDisplayText().Contains("PrivateName"), "path leaked");
        });
        Add("bundle results reject traversal filenames", () =>
        {
            foreach (string name in new[] { "../secret.zip", @"C:\secret.zip", "name.zip.", "..", " name.zip" })
                Check(!new SamsungBundleResult(true, "ok", name).Success, "unsafe name accepted");
        });
        Add("report-only bundle remains visibly distinct", () =>
        {
            var r = new SamsungBundleResult(true, "report only", "safe.zip", false); Check(r.Success && !r.ContainsModules, "report-only misrepresented");
        });
        Add("service resolver accepts quoted ProgramDataSamsung location", () =>
        {
            var loc = Resolve(@"""C:\ProgramData\Samsung\Config\SamsungSystemConfiguration.exe"" --service");
            Check(loc.Found && loc.CanEnumerateDirectory, "known dedicated path rejected"); Equal("ProgramDataSamsung", loc.Category);
        });
        Add("service resolver cannot enumerate shared System32", () =>
        {
            var loc = Resolve(@"C:\Windows\System32\SamsungSystemConfiguration.exe"); Check(loc.Found && !loc.CanEnumerateDirectory, "shared directory enumerated");
        });
        foreach (string unsafePath in new[] { @"\\server\share\app.exe", @"C:\Users\Private\app.exe", @"C:\ProgramData\Samsung\..\Private\app.exe", @"C:\ProgramData\Samsung\app.exe:extra", @"C:\ProgramData\Samsung\NUL.exe", @"%USERPROFILE%\Samsung\app.exe" })
        {
            string captured = unsafePath; Add("service resolver rejects " + unsafePath, () => Check(!Resolve(captured).Found, "untrusted path accepted"));
        }
        Add("service resolver checks path safety before existence", () =>
        {
            bool touched = false;
            var loc = Resolve(@"C:\ProgramData\Samsung\Config\app.exe", p => { touched = true; return true; }, p => false);
            Check(!loc.Found && !touched, "file touched before safety gate");
        });
        Add("module policy rejects unconfirmed parent", () =>
        {
            var r = SamsungReferencedModulePolicy.Evaluate("SamsungConfigurationMonitor.exe", new string('0', 64), "wsabi.dll", new byte[200]);
            Check(!r.Allowed && !r.ExecutionAllowed && !r.HardwareWriteAllowed, "unconfirmed module allowed");
        });
        Add("module policy rejects malformed PE even for pinned parent", () =>
        {
            var r = SamsungReferencedModulePolicy.Evaluate(SamsungReferencedModulePolicy.KnownParentFileName, SamsungReferencedModulePolicy.KnownParentSha256, "wsabi.dll", new byte[200]);
            Check(!r.Allowed && !r.ExecutionAllowed && !r.HardwareWriteAllowed, "malformed module allowed");
        });
        Add("valid referenced PE is data only with no execution or write rights", () =>
        {
            var r = SamsungReferencedModulePolicy.Evaluate(SamsungReferencedModulePolicy.KnownParentFileName, SamsungReferencedModulePolicy.KnownParentSha256, "wsabi.dll", MinimalPe());
            Check(r.Allowed && r.IsDataOnly && !r.ExecutionAllowed && !r.HardwareWriteAllowed, "data copy escalates authority");
        });
        Add("PE parser rejects short and invalid files", () =>
        {
            Check(!PeModuleReader.Read(null).IsValid && !PeModuleReader.Read(new byte[63]).IsValid && !PeModuleReader.Read(new byte[256]).IsValid, "invalid PE accepted");
        });
        Add("persisted preference and mock never become actual firmware state", () => WithFixture(f =>
        {
            f.Store.Save(new AppSettings { DesiredMode = ChargeMode.Protection80, MockModeEnabled = true });
            using (var vm = f.ViewModel())
            {
                Check(vm.IsProtectionSelected && !vm.IsMockMode && !vm.CanApply, "startup state unsafe"); Check(vm.ActualModeText.Contains("미지원"), "desired substituted for actual"); Equal("0%", vm.BatteryPercentText);
                vm.IsMockMode = true; vm.ApplyCommand.Execute(null);
                Check(vm.MockActualModeText.Contains("80%") && vm.ActualModeText.Contains("미지원"), "mock substituted for actual");
            }
        }));
        Add("disposed view model disables actions and future changes", () => WithFixture(f =>
        {
            var vm = f.ViewModel(); vm.Dispose(); vm.IsProtectionSelected = true; vm.IsMockMode = true;
            Check(!vm.CanApply && !vm.IsMockMode && !vm.SaveCommand.CanExecute(null) && !vm.ShowDiagnosticsCommand.CanExecute(null), "disposed VM active");
        }));
        AddAsync("cancelled OEM bundle never calls collector", async () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel(confirm: () => false))
            {
                await vm.CreateSamsungBundleAsync(); Equal(0, f.Bundle.Calls); Check(vm.SamsungBundleStatus.Contains("취소"), "cancel state missing");
            }
        });
        AddAsync("bundle confirmation failure never calls collector", async () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel(confirm: () => throw new Exception("private")))
            {
                await vm.CreateSamsungBundleAsync(); Equal(0, f.Bundle.Calls); Check(!vm.SamsungBundleStatus.Contains("private"), "exception leaked");
            }
        });
        AddAsync("report-only ZIP does not claim OEM copies", async () =>
        {
            using (var f = new Fixture())
            {
                f.Bundle.Result = new SamsungBundleResult(true, "report only", "analysis.zip", false);
                using (var vm = f.ViewModel(confirm: () => true))
                {
                    await vm.CreateSamsungBundleAsync(); Equal(1, f.Bundle.Calls); Check(vm.SamsungBundleStatus.Contains("복사하지 않고"), "report-only status false");
                }
            }
        });
        AddAsync("diagnostic refresh blocks stale exports and overlap", async () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel())
            {
                await vm.RefreshDiagnosticsAsync(); Check(vm.CanExportDiagnostics, "completed diagnostic not exportable");
                using (var gate = new Gate())
                {
                    f.Interaction.Reader = () => { gate.Enter(); return KnownDevice(); };
                    Task pending = vm.RefreshDiagnosticsAsync(); await gate.WaitEntered();
                    Check(!vm.CanExportDiagnostics && !vm.CopyDiagnosticsCommand.CanExecute(null) && !vm.SaveDiagnosticsCommand.CanExecute(null), "stale export allowed");
                    await vm.RefreshDiagnosticsAsync(); gate.Release(); await pending;
                    Check(vm.CanExportDiagnostics, "new diagnostic not exportable");
                }
            }
        });
        AddAsync("disposed diagnostic completion cannot publish data", async () =>
        {
            using (var f = new Fixture()) using (var gate = new Gate())
            {
                f.Interaction.Reader = () => { gate.Enter(); return KnownDevice(); };
                var vm = f.ViewModel(); Task pending = vm.RefreshDiagnosticsAsync(); await gate.WaitEntered(); vm.Dispose();
                int events = 0; vm.PropertyChanged += (s, e) => events++; gate.Release(); await pending;
                Check(!vm.CanExportDiagnostics && !vm.DiagnosticsSucceeded, "disposed result published"); Equal(0, events);
            }
        });
        AddAsync("disposed hardware report never saves late result", async () =>
        {
            using (var f = new Fixture()) using (var gate = new Gate())
            {
                f.Hardware.Reader = () => { gate.Enter(); return new HardwareProbeReport(); };
                var vm = f.ViewModel(); Task pending = vm.CreateHardwareReportAsync(); await gate.WaitEntered(); vm.Dispose(); gate.Release(); await pending; Equal(0, f.Interaction.Saves);
            }
        });
        AddAsync("disposed bundle completion cannot publish filename", async () =>
        {
            using (var f = new Fixture()) using (var gate = new Gate())
            {
                f.Bundle.Reader = () => { gate.Enter(); return new SamsungBundleResult(true, "ok", "analysis.zip"); };
                var vm = f.ViewModel(confirm: () => true); Task pending = vm.CreateSamsungBundleAsync(); await gate.WaitEntered(); vm.Dispose(); gate.Release(); await pending; Equal(string.Empty, vm.SamsungBundleFileName);
            }
        });
        Add("Support inquiry includes device facts without inventing charge support", () =>
        {
            string text = SupportInquiryFormatter.Format(KnownDevice());
            Check(text.Contains("940X3G/930X3G") && text.Contains("P05ACJ.128.140819.dg") && text.Contains("10.0.19045"), "device context missing");
            Check(text.Contains("미지원") && text.Contains("공식 지원") && text.Contains("사용권"), "support uncertainty omitted");
        });
        Add("Support inquiry preserves unknown device fields", () =>
        {
            string text = SupportInquiryFormatter.Format(null);
            Check(text.Contains("알 수 없음") && !text.Contains("940X3G"), "unknown device replaced by fixed laptop");
        });
        Add("Support inquiry excludes raw errors and private paths", () =>
        {
            var device = new DeviceDiagnosticsResult(model: @"C:\Users\PrivateName\device", errors: new[] { "private-error-secret" });
            string text = SupportInquiryFormatter.Format(device);
            Check(!text.Contains("PrivateName") && !text.Contains("private-error-secret"), "private diagnostic text copied into inquiry");
        });
        AddAsync("Production review configuration cannot collect OEM files", async () =>
        {
            using (var f = new Fixture()) using (var vm = new MainViewModel(new FakeBattery(), f.Store, new LocalLog(f.DirectoryPath), f.Interaction, f.Hardware))
            {
                Check(!vm.CreateSamsungBundleCommand.CanExecute(null) && vm.SamsungBundleStatus.Contains("보류"), "OEM collection not visibly held");
                await vm.CreateSamsungBundleAsync(); Equal(string.Empty, vm.SamsungBundleFileName);
                Check(vm.ActualModeText.Contains("미지원"), "review enabled hardware writes");
            }
        });
        AddAsync("Support inquiry copy requires fresh diagnostics and stops on dispose", async () =>
        {
            using (var f = new Fixture())
            {
                var vm = f.ViewModel();
                Check(!vm.CopySupportInquiryCommand.CanExecute(null), "copy allowed before diagnostics");
                vm.CopySupportInquiryCommand.Execute(null); Equal(0, f.Interaction.Copies);
                await vm.RefreshDiagnosticsAsync();
                vm.CopySupportInquiryCommand.Execute(null); Equal(1, f.Interaction.Copies);
                Equal(vm.SupportInquiryText, f.Interaction.LastCopiedText);
                Check(f.Interaction.LastCopiedText.Contains("940X3G/930X3G"), "wrong inquiry copied");
                vm.Dispose(); vm.CopySupportInquiryCommand.Execute(null); Equal(1, f.Interaction.Copies);
            }
        });
        AddAsync("Support inquiry blocks stale clipboard content while refreshing", async () =>
        {
            using (var f = new Fixture()) using (var vm = f.ViewModel()) using (var gate = new Gate())
            {
                await vm.RefreshDiagnosticsAsync();
                f.Interaction.Reader = () => { gate.Enter(); return KnownDevice(); };
                Task pending = vm.RefreshDiagnosticsAsync(); await gate.WaitEntered();
                Check(!vm.CopySupportInquiryCommand.CanExecute(null) && !vm.SupportInquiryText.Contains("940X3G"), "stale inquiry available");
                vm.CopySupportInquiryCommand.Execute(null); Equal(0, f.Interaction.Copies);
                gate.Release(); await pending;
            }
        });
        RegisterSchemaTests();
        RegisterSettingsPolicyTests();
        RegisterBatteryCapabilitiesTests();
        RegisterSamsungFileInspectionTests();
        RegisterSamsungKernelDriverTests();
        RegisterWmiInstanceTests();
        RegisterWmiAccessTraceTests();
        RegisterWmiAccessCheckCaptureTests();
        RegisterSamsungTransportAssessmentTests();
        RegisterSamsungFileInspectionViewModelTests();
        RegisterPeImportedFunctionTests();
        RegisterSabi3ReplyDecoderTests();
        RegisterWsabiWmiReplyValidatorTests();
        RegisterWsabiWmiReplyDecoderTests();
        RegisterWsabiWmiContractMetadataTests();
        RegisterWsabiWmiParameterMetadataTests();
        RegisterWsabiWmiMethodBinderTests();
        RegisterWsabiWmiBoundFrameChannelTests();
        RegisterWsabiWmiOneShotExperimentTests();
        RegisterWsabiWmiOneShotReservationTests();
        RegisterWsabiWmiOneShotCaptureTests();
        RegisterWsabiWmiOneShotPreflightTraceTests();
        RegisterWsabiWmiPreflightInspectionTests();
        RegisterWsabiWmiExperimentReviewTests();
        RegisterAcpiWmiRoutingTests();
        RegisterAcpiFirmwareTableReadTests();
        RegisterAcpiMethodFlowTests();
        RegisterWsabiWmiExperimentReviewViewModelTests();
        RegisterWsabiWmiRequestEncoderTests();
        RegisterWsabiWmiFrameExchangeTests();
    }

    private static void Add(string name, Action action) { Tests.Add(new KeyValuePair<string, Func<Task>>(name, () => { action(); return Task.CompletedTask; })); }
    private static void AddAsync(string name, Func<Task> action) { Tests.Add(new KeyValuePair<string, Func<Task>>(name, action)); }
    private static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
    private static void Equal<T>(T expected, T actual) { if (!EqualityComparer<T>.Default.Equals(expected, actual)) throw new Exception("expected " + expected + ", got " + actual); }
    private static void WithDirectory(Action<string> action)
    {
        string dir = Path.Combine(Path.GetTempPath(), "ATIV-recovery-tests-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(dir);
        try { action(dir); } finally { Directory.Delete(dir, true); }
    }
    private static void WithFixture(Action<Fixture> action) { using (var f = new Fixture()) action(f); }
    private static DeviceDiagnosticsResult KnownDevice() { return new DeviceDiagnosticsResult("SAMSUNG ELECTRONICS CO., LTD.", "940X3G/930X3G", "P05ACJ.128.140819.dg", "Windows 10", "10.0.19045", "64-bit"); }
    private static SamsungServiceLocation Resolve(string image, Func<string, bool> exists = null, Func<string, bool> safe = null)
    {
        return SamsungServicePathResolver.Resolve(image, null, null, @"C:\Windows", @"C:\Program Files", @"C:\Program Files (x86)", @"C:\ProgramData", exists ?? (p => true), safe ?? (p => true));
    }
    private static byte[] MinimalPe()
    {
        byte[] bytes = new byte[1024];
        void U16(int offset, ushort value) { bytes[offset] = (byte)value; bytes[offset + 1] = (byte)(value >> 8); }
        void U32(int offset, uint value) { for (int i = 0; i < 4; i++) bytes[offset + i] = (byte)(value >> (8 * i)); }
        U16(0, 0x5a4d); U32(60, 0x80); U32(0x80, 0x4550);
        U16(0x84, 0x14c); U16(0x86, 1); U16(0x94, 0xe0); U16(0x96, 0x2102);
        U16(0x98, 0x10b); U32(0x98 + 60, 0x200); U32(0x98 + 92, 16);
        int section = 0x98 + 0xe0; U32(section + 8, 0x200); U32(section + 12, 0x1000); U32(section + 16, 0x200); U32(section + 20, 0x200);
        return bytes;
    }
    private sealed class Fixture : IDisposable
    {
        public readonly string DirectoryPath = Path.Combine(Path.GetTempPath(), "ATIV-vm-tests-" + Guid.NewGuid().ToString("N"));
        public readonly SettingsStore Store;
        public readonly FakeInteraction Interaction = new FakeInteraction();
        public readonly FakeHardware Hardware = new FakeHardware();
        public readonly FakeBundle Bundle = new FakeBundle();
        public readonly FakeFileInspection Files = new FakeFileInspection();
        public Fixture() { Directory.CreateDirectory(DirectoryPath); Store = new SettingsStore(DirectoryPath); Store.Load(); }
        public MainViewModel ViewModel(Func<bool> confirm = null) { return new MainViewModel(new FakeBattery(), Store, new LocalLog(DirectoryPath), Interaction, Hardware, Bundle, confirm, Files); }
        public void Dispose() { Directory.Delete(DirectoryPath, true); }
    }
    private sealed class FakeBattery : IBatteryStatusProvider { public BatterySnapshot Read() { return new NativePowerReading(true, 1, 6, 0).ToSnapshot(); } }
    private sealed class FakeInteraction : IUserInteraction
    {
        public Func<DeviceDiagnosticsResult> Reader = KnownDevice;
        public int Saves;
        public int Copies;
        public string LastCopiedText;
        public Func<string, string> Saver;
        public int FileInspectionSaves;
        public Func<string, string> FileInspectionSaver;
        public string LastFileInspection;
        public DeviceDiagnosticsResult ReadDiagnostics() { return Reader(); }
        public void OpenSettingsFolder() { }
        public void ShowLog() { }
        public void CopyDiagnostics(string text) { Copies++; LastCopiedText = text; }
        public string SaveDiagnostics(string text) { Saves++; return Saver == null ? "saved" : Saver(text); }
        public string SaveSamsungFileInspection(string text) { FileInspectionSaves++; LastFileInspection = text; return FileInspectionSaver == null ? "saved" : FileInspectionSaver(text); }
    }
    private sealed class FakeHardware : IHardwareDiagnosticsProvider
    {
        public Func<HardwareProbeReport> Reader = () => new HardwareProbeReport();
        public HardwareProbeReport Collect() { return Reader(); }
    }
    private sealed class FakeFileInspection : ISamsungFileInspectionProvider
    {
        public int Calls;
        public Func<SamsungFileInspectionReport> Reader = () => new SamsungFileInspectionReport(SamsungFileInspectionStatus.Unavailable);
        public SamsungFileInspectionReport Collect() { Interlocked.Increment(ref Calls); return Reader(); }
    }
    private sealed class FakeBundle : ISamsungAnalysisBundleService
    {
        public int Calls;
        public SamsungBundleResult Result = new SamsungBundleResult(true, "ok", "analysis.zip");
        public Func<SamsungBundleResult> Reader;
        public SamsungBundleResult Create() { Interlocked.Increment(ref Calls); return Reader != null ? Reader() : Result; }
    }
    private sealed class Gate : IDisposable
    {
        private readonly TaskCompletionSource<bool> entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly ManualResetEventSlim release = new ManualResetEventSlim();
        public void Enter() { entered.TrySetResult(true); if (!release.Wait(TimeSpan.FromSeconds(10))) throw new TimeoutException("test gate release timed out"); }
        public Task WaitEntered() { return entered.Task.WaitAsync(TimeSpan.FromSeconds(5)); }
        public void Release() { release.Set(); }
        public void Dispose() { release.Set(); release.Dispose(); }
    }
    private sealed class SkippedTestException : Exception
    {
        public SkippedTestException(string message) : base(message) { }
    }
}
