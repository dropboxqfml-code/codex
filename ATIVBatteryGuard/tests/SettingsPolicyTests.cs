using System;
using System.Text.RegularExpressions;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static SamsungSettingsPathPolicy SettingsPaths()
    {
        return new SamsungSettingsPathPolicy(@"C:\Program Files", @"C:\Program Files (x86)", @"C:\ProgramData");
    }

    private static void RegisterSettingsPolicyTests()
    {
        Add("Settings registration matches only the intended product", () =>
        {
            Check(SamsungSettingsPathPolicy.IsMatchingRegistration("Samsung Settings", "Samsung Electronics CO., LTD."), "installed product missed");
            Check(SamsungSettingsPathPolicy.IsMatchingRegistration(" samsung settings ", "삼성전자"), "trim/case or Korean publisher missed");
        });
        Add("Settings registration excludes unrelated Samsung programs", () =>
        {
            foreach (string name in new[] { "Easy Settings", "Samsung Settings Updater", "SamsungSystemConfiguration", "Settings", "", null })
                Check(!SamsungSettingsPathPolicy.IsMatchingRegistration(name, "Samsung Electronics"), "unrelated registered name accepted");
        });
        Add("Settings registration requires publisher metadata", () =>
        {
            foreach (string publisher in new[] { "Other Company", "", null })
                Check(!SamsungSettingsPathPolicy.IsMatchingRegistration("Samsung Settings", publisher), "publisher gate bypassed");
        });
        Add("Settings directories accept only dedicated vendor app roots", () =>
        {
            foreach (string parent in new[] { @"C:\Program Files", @"C:\Program Files (x86)", @"C:\ProgramData" })
                foreach (string app in new[] { "Settings", "Samsung Settings" })
                {
                    string root = parent + @"\Samsung\" + app;
                    Check(SettingsPaths().ResolveInstallDirectory(root).Accepted, "approved dedicated root rejected");
                    Check(SettingsPaths().ResolveInstallDirectory(root + @"\").Accepted, "normal registry trailing separator rejected");
                    Check(SettingsPaths().ResolveInstallDirectory(root + @"\Battery\Plugins").Accepted, "approved descendant rejected");
                }
        });
        Add("Settings directory allowlist has strict segment boundaries", () =>
        {
            foreach (string path in new[] {
                @"C:\Program Files\Samsung\SettingsBackup", @"C:\Program Files\Samsung\Samsung SettingsOld",
                @"C:\Program Files\Other\Samsung\Settings", @"C:\Program Files\SamsungOther\Settings",
                @"C:\ProgramData\Samsung\SystemConfiguration", @"C:\Program Files\Samsung\SettingsOther\Settings" })
                RejectSettingsPath(SettingsPaths().ResolveInstallDirectory(path));
        });
        Add("Settings directory policy excludes shared and private roots", () =>
        {
            foreach (string path in new[] {
                @"C:\", @"C:\Program Files", @"C:\Program Files\Samsung", @"C:\ProgramData\Samsung",
                @"C:\Windows\Samsung\Settings", @"C:\Windows\System32", @"C:\Users\Private\Samsung\Settings",
                @"D:\Samsung\Settings", "Samsung\\Settings", "", null })
                RejectSettingsPath(SettingsPaths().ResolveInstallDirectory(path));
        });
        Add("Settings directory policy rejects network and device namespaces", () =>
        {
            foreach (string path in new[] {
                @"\\server\share\Samsung\Settings", @"\\?\C:\Program Files\Samsung\Settings",
                @"\??\C:\Program Files\Samsung\Settings", @"\\.\C:\Program Files\Samsung\Settings",
                @"\\?\GLOBALROOT\Device\HarddiskVolume1\Program Files\Samsung\Settings" })
                RejectSettingsPath(SettingsPaths().ResolveInstallDirectory(path));
        });
        Add("Settings policy rejects traversal before normalization", () =>
        {
            foreach (string path in new[] {
                @"C:\Program Files\Samsung\Settings\..\Private", @"C:\Program Files\Samsung\Other\..\Settings",
                @"C:\Program Files\Samsung\Settings\.\Battery", @"C:\Program Files\Samsung\Settings\Battery\.." })
                RejectSettingsPath(SettingsPaths().ResolveInstallDirectory(path));
        });
        Add("Settings policy rejects alternate data streams", () =>
        {
            RejectSettingsPath(SettingsPaths().ResolveInstallDirectory(@"C:\Program Files\Samsung\Settings:extra"));
            RejectSettingsPath(SettingsPaths().ResolveModulePath(@"C:\Program Files\Samsung\Settings\Battery.dll:extra"));
        });
        Add("Settings policy rejects DOS device components", () =>
        {
            foreach (string name in new[] { "CON", "PRN", "AUX", "NUL", "COM1", "LPT9" })
            {
                RejectSettingsPath(SettingsPaths().ResolveInstallDirectory(@"C:\Program Files\Samsung\Settings\" + name));
                RejectSettingsPath(SettingsPaths().ResolveModulePath(@"C:\Program Files\Samsung\Settings\" + name + ".exe"));
            }
            RejectSettingsPath(SettingsPaths().ResolveModulePath(@"C:\Program Files\Samsung\Settings\NUL .exe"));
            RejectSettingsPath(SettingsPaths().ResolveModulePath(@"C:\Program Files\Samsung\Settings\COM¹.dll"));
        });
        Add("Settings policy rejects trailing dot and space components", () =>
        {
            foreach (string path in new[] {
                @"C:\Program Files\Samsung\Settings.\Battery", @"C:\Program Files\Samsung\Settings \Battery",
                @"C:\Program Files\Samsung\Settings\Battery.\Child", "\"C:\\Program Files\\Samsung\\Settings\\Battery \"" })
                RejectSettingsPath(SettingsPaths().ResolveInstallDirectory(path));
        });
        Add("Settings policy rejects path control and direction characters", () =>
        {
            foreach (string tail in new[] { "Bat\ntery", "Bat\rtery", "Bat\0tery", "Bat\ttery", "Bat\u202etery", "Bat\u2066tery" })
                RejectSettingsPath(SettingsPaths().ResolveInstallDirectory(@"C:\Program Files\Samsung\Settings\" + tail));
        });
        Add("Settings known environment variables resolve within app scope", () =>
        {
            foreach (string variable in new[] { "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData", "programfiles" })
                Check(SettingsPaths().ResolveInstallDirectory("%" + variable + @"%\Samsung\Settings").Accepted, "known environment root rejected");
        });
        Add("Settings unknown or incomplete environment expressions fail closed", () =>
        {
            foreach (string path in new[] {
                @"%USERPROFILE%\Samsung\Settings", @"%SystemRoot%\Samsung\Settings", @"%Unknown%\Samsung\Settings",
                @"%ProgramFiles\Samsung\Settings", @"%ProgramFiles%%Unknown%\Samsung\Settings" })
                RejectSettingsPath(SettingsPaths().ResolveInstallDirectory(path));
        });
        Add("Settings directories support quoted registry values and case", () =>
        {
            var quoted = SettingsPaths().ResolveInstallDirectory("\"C:\\Program Files (x86)\\Samsung\\Settings\"");
            Check(quoted.Accepted && string.Equals(quoted.Path, @"C:\Program Files (x86)\Samsung\Settings", StringComparison.OrdinalIgnoreCase), "quoted registry directory mishandled");
            Check(SettingsPaths().ResolveInstallDirectory(@"c:\program files\SAMSUNG\settings").Accepted, "case-sensitive Windows path gate");
        });
        Add("Settings DisplayIcon accepts only an executable and optional integer index", () =>
        {
            string path = @"C:\Program Files (x86)\Samsung\Settings\sSettings.exe";
            foreach (string icon in new[] { path, path + ",0", path + ",-1", "\"" + path + "\"", "\"" + path + "\",0", "\"" + path + "\",-2" })
            {
                var result = SettingsPaths().ResolveDisplayIcon(icon);
                Check(result.Accepted && string.Equals(result.Path, path, StringComparison.OrdinalIgnoreCase), "valid display icon missed");
            }
        });
        Add("Settings DisplayIcon rejects commands and malformed quoting", () =>
        {
            string path = @"C:\Program Files\Samsung\Settings\Settings.exe";
            foreach (string icon in new[] { path + " --run", "\"" + path + "\" --run", "\"" + path, path + "\"", "cmd.exe /c " + path, "rundll32.exe " + path })
                RejectSettingsPath(SettingsPaths().ResolveDisplayIcon(icon));
        });
        Add("Settings DisplayIcon rejects controls outside the quoted path", () =>
        {
            string quoted = "\"C:\\Program Files\\Samsung\\Settings\\sSettings.exe\"";
            foreach (string icon in new[] {
                quoted + "\n,0", quoted + "\r,0", quoted + "\t,0", quoted + ",\t0", quoted + ",\n0",
                quoted + "\u202e,0", quoted + "\u2066,0", quoted + "\u2028,0", "\u202e" + quoted + ",0" })
                RejectSettingsPath(SettingsPaths().ResolveDisplayIcon(icon));
        });
        Add("Settings DisplayIcon rejects noninteger and trailing index data", () =>
        {
            string path = @"C:\Program Files\Samsung\Settings\Settings.exe";
            foreach (string index in new[] { ",abc", ",0,1", ",0 --run", ",", ",1.2", ",0.exe", ",2147483648" })
                RejectSettingsPath(SettingsPaths().ResolveDisplayIcon(path + index));
        });
        Add("Settings DisplayIcon does not authorize icon DLL or private paths", () =>
        {
            foreach (string icon in new[] {
                @"C:\Program Files\Samsung\Settings\Settings.ico,0", @"C:\Program Files\Samsung\Settings\Settings.dll,0",
                @"C:\Users\Private\Samsung\Settings\Settings.exe,0", @"C:\Windows\Installer\Product\Settings.exe,0" })
                RejectSettingsPath(SettingsPaths().ResolveDisplayIcon(icon));
        });
        Add("Settings module paths permit EXE DLL only within dedicated app scope", () =>
        {
            Check(SettingsPaths().ResolveModulePath(@"C:\Program Files\Samsung\Settings\Settings.exe").Accepted, "main EXE rejected");
            Check(SettingsPaths().ResolveModulePath(@"C:\Program Files\Samsung\Settings\Battery\Battery.DLL").Accepted, "nested DLL rejected");
            foreach (string extension in new[] { ".sys", ".json", ".config", ".log", ".txt", ".exe.bak", ".ps1" })
                RejectSettingsPath(SettingsPaths().ResolveModulePath(@"C:\Program Files\Samsung\Settings\data" + extension));
        });
        Add("Settings directory containment rejects prefix siblings", () =>
        {
            string root = @"C:\Program Files\Samsung\Settings";
            Check(SamsungSettingsPathPolicy.IsInsideDirectory(root + @"\Battery\Battery.dll", root), "descendant not recognized");
            Check(!SamsungSettingsPathPolicy.IsInsideDirectory(root + @"Backup\Battery.dll", root), "prefix sibling accepted");
            Check(!SamsungSettingsPathPolicy.IsInsideDirectory(@"C:\Users\Private\Settings\Battery.dll", root), "other root accepted");
        });
        Add("Settings rejected results do not expose personal paths or unsafe tokens", () =>
        {
            var result = SettingsPaths().ResolveInstallDirectory(@"C:\Users\PrivateName\Samsung\Settings");
            RejectSettingsPath(result);
            Check(!result.ReasonCode.Contains("PrivateName") && Regex.IsMatch(result.ReasonCode, @"\A[A-Z0-9_]+\z"), "raw input leaked through reason");
        });
        Add("Settings roots cannot be redefined to network or private locations", () =>
        {
            try
            {
                var policy = new SamsungSettingsPathPolicy(@"\\server\share", @"C:\Users\Private", @"C:\Users\PrivateData");
                RejectSettingsPath(policy.ResolveInstallDirectory(@"\\server\share\Samsung\Settings"));
                RejectSettingsPath(policy.ResolveInstallDirectory(@"C:\Users\Private\Samsung\Settings"));
                RejectSettingsPath(policy.ResolveInstallDirectory(@"C:\Users\PrivateData\Samsung\Settings"));
            }
            catch (ArgumentException) { /* Constructor rejection is also fail-closed. */ }
        });
        Add("Legacy service locations do not acquire a collection directory", () =>
        {
            var location = new SamsungServiceLocation(true,
                @"C:\ProgramData\Samsung\SystemConfiguration\SamsungSystemConfiguration.exe",
                "SamsungSystemConfiguration.exe", "WMI", "ProgramDataSamsung", "MODULE_LOCATED", true);
            Check(location.Found && location.CanEnumerateDirectory, "legacy location changed");
            Equal(string.Empty, location.CollectionDirectory);
        });
        Add("Settings collection boundary preserves root separately from nested anchor", () =>
        {
            string root = @"C:\Program Files\Samsung\Settings";
            string anchor = root + @"\Launcher\sSettings.exe";
            var location = new SamsungServiceLocation(true, anchor, "sSettings.exe",
                "RegistryDisplayIcon", "SettingsProgramFiles", "MODULE_LOCATED", true, root);
            Check(location.Found && location.CanEnumerateDirectory, "valid Settings location lost");
            Equal(anchor, location.Path); Equal(root, location.CollectionDirectory);
        });
        Add("Failed service locations discard all local collection paths", () =>
        {
            string root = @"C:\Program Files\Samsung\Settings";
            foreach (var location in new[] {
                new SamsungServiceLocation(false, root + @"\sSettings.exe", "sSettings.exe",
                    "RegistryDisplayIcon", "SettingsProgramFiles", "NOT_FOUND", true, root),
                new SamsungServiceLocation(true, root + @"\sSettings.exe", "../escape.exe",
                    "RegistryDisplayIcon", "SettingsProgramFiles", "MODULE_LOCATED", true, root) })
            {
                Check(!location.Found && !location.CanEnumerateDirectory, "failed location still usable");
                Equal(string.Empty, location.Path); Equal(string.Empty, location.CollectionDirectory);
            }
        });
    }

    private static void RejectSettingsPath(SamsungSettingsPathResult result)
    {
        Check(result != null && !result.Accepted, "unsafe Settings path accepted");
        Equal(string.Empty, result.Path);
    }
}
