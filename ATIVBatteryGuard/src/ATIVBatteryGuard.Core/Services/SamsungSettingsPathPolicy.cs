using System;
using System.Globalization;
using System.Text.RegularExpressions;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    // Pure lexical Windows path checks: no filesystem, registry, environment or OEM access.
    public sealed class SamsungSettingsPathPolicy
    {
        private readonly string programFiles;
        private readonly string programFilesX86;
        private readonly string programData;

        public SamsungSettingsPathPolicy(string programFiles, string programFilesX86, string programData)
        {
            this.programFiles = NormalizeRoot(programFiles);
            this.programFilesX86 = NormalizeRoot(programFilesX86);
            this.programData = NormalizeRoot(programData);
        }

        public static bool IsMatchingRegistration(string displayName, string publisher)
        {
            return !string.IsNullOrWhiteSpace(displayName) &&
                string.Equals(displayName.Trim(), "Samsung Settings", StringComparison.OrdinalIgnoreCase) &&
                !string.IsNullOrWhiteSpace(publisher) &&
                (publisher.IndexOf("Samsung", StringComparison.OrdinalIgnoreCase) >= 0 ||
                 publisher.IndexOf("삼성", StringComparison.Ordinal) >= 0);
        }

        public SamsungSettingsPathResult ResolveInstallDirectory(string raw)
        {
            string token = UnquoteDirectory(raw);
            if (token == null) return Reject("DIRECTORY_SYNTAX_REJECTED");
            return Resolve(token, false);
        }

        public SamsungSettingsPathResult ResolveDisplayIcon(string raw)
        {
            if (string.IsNullOrWhiteSpace(raw) || raw.Length > 1200) return Reject("ICON_PATH_NOT_PROVIDED");
            foreach (char c in raw)
            {
                if (char.IsControl(c) || c == '\u2028' || c == '\u2029' ||
                    (c >= '\u202a' && c <= '\u202e') || (c >= '\u2066' && c <= '\u2069')) return Reject("ICON_SYNTAX_REJECTED");
            }
            // Registry DisplayIcon is not a command line. Only a path and integer icon index are accepted.
            Match match = Regex.Match(raw,
                "\\A(?:\"(?<path>[^\"]+)\"|(?<path>[^\",]+?))(?:\\s*,\\s*(?<index>[+-]?[0-9]{1,10}))?\\z",
                RegexOptions.CultureInvariant);
            if (!match.Success) return Reject("ICON_SYNTAX_REJECTED");
            int ignoredIndex;
            if (match.Groups["index"].Success && !int.TryParse(match.Groups["index"].Value,
                NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out ignoredIndex)) return Reject("ICON_INDEX_REJECTED");
            string path = match.Groups["path"].Value;
            if (!path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) return Reject("ICON_NOT_EXECUTABLE");
            return Resolve(path, true);
        }

        public SamsungSettingsPathResult ResolveModulePath(string raw)
        {
            if (string.IsNullOrEmpty(raw) ||
                (!raw.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) && !raw.EndsWith(".dll", StringComparison.OrdinalIgnoreCase)))
                return Reject("MODULE_EXTENSION_REJECTED");
            return Resolve(raw, true);
        }

        public static bool IsInsideDirectory(string path, string directory)
        {
            string normalizedPath, normalizedDirectory;
            if (!Normalize(path, false, out normalizedPath) || !Normalize(directory, true, out normalizedDirectory)) return false;
            return normalizedPath.Length > normalizedDirectory.Length + 1 &&
                normalizedPath.StartsWith(normalizedDirectory + "\\", StringComparison.OrdinalIgnoreCase);
        }

        private SamsungSettingsPathResult Resolve(string raw, bool module)
        {
            if (string.IsNullOrEmpty(raw)) return Reject("PATH_NOT_PROVIDED");
            bool known = true;
            string expanded = Regex.Replace(raw, "%([^%]+)%", match =>
            {
                string value = null;
                string name = match.Groups[1].Value;
                if (Same(name, "ProgramFiles") || Same(name, "ProgramW6432")) value = programFiles;
                else if (Same(name, "ProgramFiles(x86)")) value = programFilesX86;
                else if (Same(name, "ProgramData")) value = programData;
                if (string.IsNullOrEmpty(value)) { known = false; return string.Empty; }
                return value;
            });
            if (!known || expanded.IndexOf('%') >= 0) return Reject("UNKNOWN_ENVIRONMENT_VARIABLE");
            string full;
            if (!Normalize(expanded, !module, out full)) return Reject("PATH_SYNTAX_REJECTED");
            string category = Classify(full, module);
            if (category == null) return Reject("OUTSIDE_SETTINGS_DIRECTORY");
            if (module)
            {
                string name = full.Substring(full.LastIndexOf('\\') + 1);
                if (name.Length > 160) return Reject("MODULE_NAME_REJECTED");
                if (!name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) && !name.EndsWith(".dll", StringComparison.OrdinalIgnoreCase))
                    return Reject("MODULE_EXTENSION_REJECTED");
            }
            return new SamsungSettingsPathResult(true, full, category, "SETTINGS_PATH_ACCEPTED");
        }

        private string Classify(string path, bool module)
        {
            if (UnderSettings(path, programFilesX86, module)) return "SettingsProgramFilesX86";
            if (UnderSettings(path, programFiles, module)) return "SettingsProgramFiles";
            if (UnderSettings(path, programData, module)) return "SettingsProgramData";
            return null;
        }

        private static bool UnderSettings(string path, string root, bool module)
        {
            if (string.IsNullOrEmpty(root)) return false;
            foreach (string folder in new[] { "Samsung\\Settings", "Samsung\\Samsung Settings" })
            {
                string allowed = root + "\\" + folder;
                if ((!module && Same(path, allowed)) ||
                    (path.Length > allowed.Length + 1 && path.StartsWith(allowed + "\\", StringComparison.OrdinalIgnoreCase))) return true;
            }
            return false;
        }

        private static string UnquoteDirectory(string raw)
        {
            if (string.IsNullOrEmpty(raw)) return raw;
            if (raw[0] == '"')
            {
                if (raw.Length < 2 || raw[raw.Length - 1] != '"') return null;
                return raw.Substring(1, raw.Length - 2);
            }
            return raw;
        }

        private static string NormalizeRoot(string raw)
        {
            string result;
            if (!Normalize(raw, true, out result)) return string.Empty;
            foreach (string part in result.Substring(3).Split('\\'))
            {
                if (Same(part, "Users") || Same(part, "Documents and Settings") ||
                    Same(part, "Windows") || Same(part, "System32") || Same(part, "SysWOW64")) return string.Empty;
            }
            return result;
        }

        private static bool Normalize(string raw, bool directory, out string full)
        {
            full = string.Empty;
            if (string.IsNullOrEmpty(raw) || raw.Length > 1024) return false;
            string path = raw.Replace('/', '\\');
            if (directory) path = path.TrimEnd('\\');
            if (path.Length < 4 || !IsAsciiLetter(path[0]) || path[1] != ':' || path[2] != '\\') return false;
            string[] parts = path.Substring(3).Split('\\');
            foreach (string part in parts)
            {
                if (part.Length == 0 || part == "." || part == ".." || part != part.Trim() || part.EndsWith(".", StringComparison.Ordinal)) return false;
                foreach (char c in part)
                {
                    if (!(char.IsLetterOrDigit(c) || c == ' ' || c == '.' || c == '_' || c == '-' || c == '(' || c == ')')) return false;
                }
                string stem = part.Split('.')[0].TrimEnd(' ');
                if (Same(stem, "CON") || Same(stem, "PRN") || Same(stem, "AUX") || Same(stem, "NUL") || Same(stem, "CLOCK$") ||
                    Regex.IsMatch(stem, "\\A(?:COM|LPT)[1-9¹²³]\\z", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)) return false;
            }
            full = char.ToUpperInvariant(path[0]) + path.Substring(1);
            return true;
        }

        private static bool IsAsciiLetter(char value) { return (value >= 'A' && value <= 'Z') || (value >= 'a' && value <= 'z'); }
        private static bool Same(string left, string right) { return string.Equals(left, right, StringComparison.OrdinalIgnoreCase); }
        private static SamsungSettingsPathResult Reject(string code) { return new SamsungSettingsPathResult(false, string.Empty, "Invalid", code); }
    }
}
