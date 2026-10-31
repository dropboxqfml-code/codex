using System;
using System.Collections.Generic;
using System.IO;
using System.Security;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;
using Microsoft.Win32;

namespace ATIVBatteryGuard.Diagnostics
{
    // Only call after the user has confirmed OEM analysis-file collection.
    public static class SamsungSettingsLocator
    {
        private const string UninstallKey = @"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall";

        public static SamsungServiceLocation Locate(IList<string> notes)
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) return Failure("UNSUPPORTED_PLATFORM");
            var policy = new SamsungSettingsPathPolicy(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData));
            SamsungServiceLocation best = Failure("SETTINGS_REGISTRATION_NOT_FOUND");
            int matched = 0;
            foreach (RegistryView view in new[] { RegistryView.Registry64, RegistryView.Registry32 })
            {
                try
                {
                    using (RegistryKey machine = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, view))
                    using (RegistryKey entries = machine.OpenSubKey(UninstallKey, writable: false))
                    {
                        if (entries == null) { Note(notes, "SETTINGS_UNINSTALL_KEY_MISSING"); continue; }
                        int visited = 0;
                        foreach (string keyName in entries.GetSubKeyNames())
                        {
                            if (++visited > 1024) { Note(notes, "SETTINGS_REGISTRY_LIMIT"); break; }
                            try
                            {
                                using (RegistryKey entry = entries.OpenSubKey(keyName, writable: false))
                                {
                                    if (entry == null || !SamsungSettingsPathPolicy.IsMatchingRegistration(
                                        Read(entry, "DisplayName"), Read(entry, "Publisher"))) continue;
                                    if (++matched > 4) { Note(notes, "SETTINGS_MATCH_LIMIT"); return best; }
                                    Note(notes, view == RegistryView.Registry64 ? "SETTINGS_REGISTERED_64" : "SETTINGS_REGISTERED_32");
                                    // Never read or run UninstallString/QuietUninstallString/InstallSource.
                                    SamsungServiceLocation located = ResolveRegistration(
                                        Read(entry, "InstallLocation"), Read(entry, "DisplayIcon"), policy, notes);
                                    if (located.Found) return located;
                                    best = located;
                                }
                            }
                            catch (Exception exception) when (ReadFailure(exception))
                            {
                                Note(notes, "SETTINGS_REGISTRY_ENTRY_READ_FAILED");
                                best = Failure("SETTINGS_REGISTRY_READ_FAILED");
                            }
                        }
                    }
                }
                catch (Exception exception) when (ReadFailure(exception))
                {
                    Note(notes, "SETTINGS_REGISTRY_VIEW_READ_FAILED");
                    best = Failure("SETTINGS_REGISTRY_READ_FAILED");
                }
            }
            return best;
        }

        private static SamsungServiceLocation ResolveRegistration(string installLocation, string displayIcon,
            SamsungSettingsPathPolicy policy, IList<string> notes)
        {
            if (!string.IsNullOrEmpty(installLocation))
            {
                SamsungSettingsPathResult directory = policy.ResolveInstallDirectory(installLocation);
                if (!directory.Accepted)
                {
                    Note(notes, "SETTINGS_INSTALL_DIRECTORY_REJECTED");
                    return Failure(directory.ReasonCode);
                }
                if (!SafeSourceDirectory(directory.Path)) return Failure("SETTINGS_DIRECTORY_UNSAFE");
                if (!Directory.Exists(directory.Path)) return Failure("SETTINGS_DIRECTORY_NOT_FOUND");
                SamsungSettingsPathResult icon = policy.ResolveDisplayIcon(displayIcon);
                if (icon.Accepted && SamsungSettingsPathPolicy.IsInsideDirectory(icon.Path, directory.Path))
                {
                    SamsungServiceLocation direct = TryFile(icon.Path, icon.Category, "RegistryDisplayIcon", directory.Path);
                    if (direct.Found) return direct;
                    Note(notes, "SETTINGS_ICON_FILE_UNAVAILABLE");
                }
                else if (!string.IsNullOrEmpty(displayIcon)) Note(notes, "SETTINGS_ICON_NOT_IN_INSTALL_DIRECTORY");
                return FindAnchor(directory.Path, directory.Category, policy, notes);
            }
            SamsungSettingsPathResult file = policy.ResolveDisplayIcon(displayIcon);
            if (!file.Accepted)
            {
                Note(notes, "SETTINGS_LOCATION_NOT_CONFIRMED");
                return Failure(file.ReasonCode);
            }
            // No directory scan or known-folder fallback is used for an unavailable DisplayIcon.
            return TryFile(file.Path, file.Category, "RegistryDisplayIcon", Path.GetDirectoryName(file.Path));
        }

        private static SamsungServiceLocation FindAnchor(string directory, string category,
            SamsungSettingsPathPolicy policy, IList<string> notes)
        {
            var candidates = new List<string>();
            int visited = 0;
            // Re-check before enumeration; Directory.Exists alone is not a reparse check.
            if (!SafeSourceDirectory(directory)) return Failure("SETTINGS_DIRECTORY_UNSAFE");
            foreach (string file in Directory.EnumerateFiles(directory, "*", SearchOption.TopDirectoryOnly))
            {
                if (++visited > 128) { Note(notes, "SETTINGS_ANCHOR_SCAN_LIMIT"); break; }
                if (!file.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) continue;
                SamsungSettingsPathResult candidate = policy.ResolveModulePath(file);
                if (!candidate.Accepted || !SamsungSettingsPathPolicy.IsInsideDirectory(candidate.Path, directory)) continue;
                string name = Path.GetFileName(candidate.Path);
                if (IsInstallerName(name)) continue;
                candidates.Add(candidate.Path);
            }
            candidates.Sort((left, right) =>
            {
                int order = Priority(Path.GetFileName(left)).CompareTo(Priority(Path.GetFileName(right)));
                return order != 0 ? order : StringComparer.OrdinalIgnoreCase.Compare(Path.GetFileName(left), Path.GetFileName(right));
            });
            foreach (string file in candidates)
            {
                SamsungServiceLocation location = TryFile(file, category, "RegistryInstallLocation", directory);
                if (location.Found) { Note(notes, "SETTINGS_ANCHOR_FOUND"); return location; }
            }
            return Failure("SETTINGS_EXECUTABLE_NOT_FOUND");
        }

        private static SamsungServiceLocation TryFile(string file, string category, string source, string collectionDirectory = null)
        {
            try
            {
                if (IsInstallerName(Path.GetFileName(file))) return Failure("SETTINGS_INSTALLER_ANCHOR_REJECTED");
                if (!SafeSourceDirectory(Path.GetDirectoryName(file))) return Failure("SETTINGS_FILE_UNSAFE");
                LocalPathPolicy.EnsureNoReparsePoints(file);
                if (!File.Exists(file)) return Failure("SETTINGS_EXECUTABLE_NOT_FOUND");
                return new SamsungServiceLocation(true, file, Path.GetFileName(file), source, category,
                    "SETTINGS_EXECUTABLE_LOCATED", canEnumerateDirectory: true, collectionDirectory: collectionDirectory);
            }
            catch (Exception exception) when (ReadFailure(exception)) { return Failure("SETTINGS_FILE_READ_FAILED"); }
        }

        private static bool SafeSourceDirectory(string directory)
        {
            try
            {
                LocalPathPolicy.NormalizeDirectory(directory);
                LocalPathPolicy.EnsureNoReparsePoints(directory);
                return true;
            }
            catch (Exception exception) when (ReadFailure(exception)) { return false; }
        }

        private static int Priority(string name)
        {
            if (string.Equals(name, "sSettings.exe", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(name, "SamsungSettings.exe", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(name, "Settings.exe", StringComparison.OrdinalIgnoreCase)) return 0;
            return name.IndexOf("settings", StringComparison.OrdinalIgnoreCase) >= 0 ? 1 : 2;
        }

        private static bool IsInstallerName(string name)
        {
            return name.IndexOf("uninstall", StringComparison.OrdinalIgnoreCase) >= 0 ||
                name.IndexOf("setup", StringComparison.OrdinalIgnoreCase) >= 0 ||
                name.IndexOf("install", StringComparison.OrdinalIgnoreCase) >= 0;
        }

        private static string Read(RegistryKey key, string name)
        {
            object value = key.GetValue(name, null, RegistryValueOptions.DoNotExpandEnvironmentNames);
            return value as string;
        }

        private static void Note(IList<string> notes, string code)
        {
            if (notes != null && notes.Count < 16 && !notes.Contains(code)) notes.Add(code);
        }

        private static SamsungServiceLocation Failure(string code)
        {
            return new SamsungServiceLocation(false, string.Empty, string.Empty, "SettingsRegistry", "Invalid", code);
        }

        private static bool ReadFailure(Exception exception)
        {
            return exception is IOException || exception is UnauthorizedAccessException || exception is SecurityException ||
                exception is InvalidOperationException || exception is ArgumentException || exception is NotSupportedException;
        }
    }
}
