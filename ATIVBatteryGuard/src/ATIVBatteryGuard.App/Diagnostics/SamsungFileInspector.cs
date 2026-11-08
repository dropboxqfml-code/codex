using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Win32.SafeHandles;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Core.Storage;

namespace ATIVBatteryGuard.Diagnostics
{
    // Finite, fixed-root metadata inspection. Invoked only by our separate worker.
    internal static class SamsungFileInspector
    {
        private static readonly string[] Targets = { "Sabi3.dll", "wsabi.dll", "BatteryToast.exe", "PowerAudit.exe" };
        private const int MaximumDirectories = 32;
        private const int MaximumItems = 512;
        private const long MaximumTotalBytes = 64L * 1024 * 1024;

        private sealed class Folder
        {
            internal string Path;
            internal int Depth;
        }

        private sealed class Scan
        {
            internal readonly List<SamsungFileInspectionEntry> Entries = new List<SamsungFileInspectionEntry>();
            internal int Directories;
            internal int Items;
            internal long Bytes;
            internal bool Limited;
            internal bool Partial;
            internal bool FoundRoot;
        }

        private sealed class DirectoryPins : IDisposable
        {
            private readonly List<SafeFileHandle> handles = new List<SafeFileHandle>();

            internal DirectoryPins(string directory)
            {
                try
                {
                    var ancestors = new Stack<string>();
                    for (string path = directory; !string.IsNullOrEmpty(path); path = Path.GetDirectoryName(path))
                        ancestors.Push(path);
                    foreach (string path in ancestors)
                    {
                        // OPEN_REPARSE_POINT inspects the directory itself. Sharing only reads
                        // prevents its replacement or conversion while path-based version APIs run.
                        var handle = CreateFileW(path, 0x80, 1, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero);
                        handles.Add(handle);
                        AttributeTag attributes;
                        if (handle.IsInvalid || !GetFileInformationByHandleEx(handle, 9, out attributes, 8) ||
                            (attributes.Attributes & FileAttributes.Directory) == 0 ||
                            (attributes.Attributes & FileAttributes.ReparsePoint) != 0 || !DirectoryPathMatches(handle, path))
                            throw new IOException();
                    }
                }
                catch { Dispose(); throw; }
            }

            public void Dispose()
            {
                for (int index = handles.Count - 1; index >= 0; index--) handles[index].Dispose();
                handles.Clear();
            }
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct AttributeTag
        {
            internal FileAttributes Attributes;
            internal uint ReparseTag;
        }

        internal static SamsungFileInspectionReport Collect()
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
                return new SamsungFileInspectionReport(SamsungFileInspectionStatus.UnsupportedPlatform,
                    driverLink: SabiDriverLinkStatus.UnsupportedPlatform,
                    kernelDrivers: new SamsungKernelDriverReport(SamsungDriverQueryStatus.UnsupportedPlatform),
                    wmiInstances: SamsungWmiInstanceReport.Failure(SamsungWmiQueryStatus.UnsupportedPlatform),
                    bootEnvironment: new WindowsBootEnvironmentReport(WindowsBootQueryStatus.UnsupportedPlatform));
            var bootEnvironment = WindowsBootEnvironmentProbe.Collect();
            var driverLink = (SabiDriverLinkStatus)SabiDriverLinkProbe.CollectCode();
            var kernelDrivers = SamsungKernelDriverProbe.Collect();
            var wmiInstances = SamsungWmiInstanceProbe.Collect();
            try
            {
                string programFiles = LocalPathPolicy.NormalizeDirectory(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86));
                string drive = Path.GetPathRoot(programFiles);
                if (string.IsNullOrEmpty(drive) || new DriveInfo(drive).DriveType != DriveType.Fixed)
                    return new SamsungFileInspectionReport(SamsungFileInspectionStatus.Unavailable,
                        driverLink: driverLink, kernelDrivers: kernelDrivers, wmiInstances: wmiInstances, bootEnvironment: bootEnvironment);
                var scan = new Scan();
                foreach (string name in new[] { "Setting", "Settings" })
                {
                    if (scan.Entries.Count >= SamsungFileInspectionReport.MaximumEntries) { scan.Limited = true; break; }
                    string root = Path.GetFullPath(Path.Combine(programFiles, "Samsung", name));
                    InspectRoot(root, name, scan);
                }
                var status = !scan.FoundRoot && scan.Entries.Count == 0
                    ? SamsungFileInspectionStatus.DirectoryNotFound
                    : scan.Partial || scan.Limited ? SamsungFileInspectionStatus.Partial : SamsungFileInspectionStatus.Complete;
                return new SamsungFileInspectionReport(status, scan.Entries, scan.Limited, driverLink, kernelDrivers, wmiInstances, bootEnvironment);
            }
            catch { return new SamsungFileInspectionReport(SamsungFileInspectionStatus.Unavailable,
                driverLink: driverLink, kernelDrivers: kernelDrivers, wmiInstances: wmiInstances, bootEnvironment: bootEnvironment); }
        }

        private static void InspectRoot(string root, string label, Scan scan)
        {
            try
            {
                LocalPathPolicy.EnsureNoReparsePoints(root);
                if ((File.GetAttributes(root) & FileAttributes.Directory) == 0)
                {
                    AddFailures(scan, label, SamsungFileEntryStatus.PathRejected); return;
                }
            }
            catch (FileNotFoundException) { return; }
            catch (DirectoryNotFoundException) { return; }
            catch (UnauthorizedAccessException) { AddFailures(scan, label, SamsungFileEntryStatus.AccessDenied); return; }
            catch (IOException) { AddFailures(scan, label, SamsungFileEntryStatus.PathRejected); return; }
            catch { AddFailures(scan, label, SamsungFileEntryStatus.Unavailable); return; }
            scan.FoundRoot = true;
            bool complete = true;
            var found = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var queue = new Queue<Folder>();
            queue.Enqueue(new Folder { Path = root, Depth = 0 });
            while (queue.Count != 0)
            {
                if (scan.Directories >= MaximumDirectories || scan.Items >= MaximumItems ||
                    scan.Entries.Count >= SamsungFileInspectionReport.MaximumEntries)
                {
                    scan.Limited = true; complete = false; break;
                }
                Folder folder = queue.Dequeue();
                scan.Directories++;
                try
                {
                    LocalPathPolicy.EnsureNoReparsePoints(folder.Path);
                    foreach (string path in Directory.EnumerateFileSystemEntries(folder.Path))
                    {
                        if (++scan.Items > MaximumItems || scan.Entries.Count >= SamsungFileInspectionReport.MaximumEntries)
                        { scan.Limited = true; complete = false; break; }
                        string name = Path.GetFileName(path);
                        string target = CanonicalName(name);
                        FileAttributes attributes;
                        try { attributes = File.GetAttributes(path); }
                        catch
                        {
                            complete = false;
                            if (target != null)
                            {
                                found.Add(target);
                                scan.Entries.Add(new SamsungFileInspectionEntry(target, Location(label, folder.Depth), SamsungFileEntryStatus.Unavailable));
                            }
                            continue;
                        }
                        if ((attributes & FileAttributes.ReparsePoint) != 0)
                        {
                            if (target != null)
                            {
                                found.Add(target);
                                scan.Entries.Add(new SamsungFileInspectionEntry(target, Location(label, folder.Depth), SamsungFileEntryStatus.PathRejected));
                            }
                            complete = false;
                            continue;
                        }
                        if ((attributes & FileAttributes.Directory) != 0)
                        {
                            if (folder.Depth < 2 && queue.Count + scan.Directories < MaximumDirectories)
                                queue.Enqueue(new Folder { Path = path, Depth = folder.Depth + 1 });
                            else { scan.Limited = true; complete = false; }
                            continue;
                        }
                        if (target == null) continue;
                        found.Add(target);
                        var entry = InspectFile(path, root, target, Location(label, folder.Depth), scan);
                        scan.Entries.Add(entry);
                        if (entry.Status != SamsungFileEntryStatus.Inspected) scan.Partial = true;
                    }
                }
                catch { complete = false; scan.Partial = true; }
            }
            if (!complete) scan.Partial = true;
            foreach (string name in Targets)
            {
                if (found.Contains(name)) continue;
                if (scan.Entries.Count >= SamsungFileInspectionReport.MaximumEntries) { scan.Limited = true; break; }
                scan.Entries.Add(new SamsungFileInspectionEntry(name, label,
                    complete ? SamsungFileEntryStatus.NotFound : SamsungFileEntryStatus.Unavailable));
            }
        }

        private static SamsungFileInspectionEntry InspectFile(string path, string root, string name, string label, Scan scan)
        {
            try
            {
                string full = Path.GetFullPath(path);
                if (!Inside(root, full)) return Failure(name, label, SamsungFileEntryStatus.PathRejected);
                LocalPathPolicy.EnsureNoReparsePoints(full);
                using (var directories = new DirectoryPins(Path.GetDirectoryName(full)))
                using (var input = new FileStream(full, FileMode.Open, FileAccess.Read, FileShare.Read))
                {
                    if (!PinnedPathMatches(input.SafeFileHandle, full, root))
                        return Failure(name, label, SamsungFileEntryStatus.PathRejected);
                    long length = input.Length;
                    if (length < 1) return Failure(name, label, SamsungFileEntryStatus.InvalidPe);
                    if (length > SamsungFileInspectionReport.MaximumFileBytes || length > MaximumTotalBytes - scan.Bytes)
                    { scan.Limited = true; return Failure(name, label, SamsungFileEntryStatus.TooLarge); }
                    scan.Bytes += length;
                    var bytes = new byte[(int)length];
                    int position = 0;
                    while (position < bytes.Length)
                    {
                        int read = input.Read(bytes, position, bytes.Length - position);
                        if (read == 0) return Failure(name, label, SamsungFileEntryStatus.Unavailable);
                        position += read;
                    }
                    if (input.ReadByte() != -1) return Failure(name, label, SamsungFileEntryStatus.Unavailable);
                    PeModuleInfo pe = PeModuleReader.Read(bytes);
                    if (!pe.IsValid) return Failure(name, label, SamsungFileEntryStatus.InvalidPe);
                    string hash;
                    using (var algorithm = SHA256.Create())
                        hash = BitConverter.ToString(algorithm.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
                    // Sharing denies writes and deletes while all path-based metadata reads occur.
                    LocalPathPolicy.EnsureNoReparsePoints(full);
                    var version = FileVersionInfo.GetVersionInfo(full);
                    var signature = OfflineAuthenticodeVerifier.Verify(full, input.SafeFileHandle);
                    LocalPathPolicy.EnsureNoReparsePoints(full);
                    if (!PinnedPathMatches(input.SafeFileHandle, full, root))
                        return Failure(name, label, SamsungFileEntryStatus.PathRejected);
                    return new SamsungFileInspectionEntry(name, label, SamsungFileEntryStatus.Inspected, length,
                        version.FileVersion, version.ProductVersion, version.CompanyName, version.FileDescription,
                        hash, pe, signature);
                }
            }
            catch (UnauthorizedAccessException) { return Failure(name, label, SamsungFileEntryStatus.AccessDenied); }
            catch (FileNotFoundException) { return Failure(name, label, SamsungFileEntryStatus.Unavailable); }
            catch (DirectoryNotFoundException) { return Failure(name, label, SamsungFileEntryStatus.Unavailable); }
            catch { return Failure(name, label, SamsungFileEntryStatus.Unavailable); }
        }

        private static bool PinnedPathMatches(SafeFileHandle handle, string expected, string root)
        {
            string final = FinalPath(handle);
            return final != null && string.Equals(final, expected, StringComparison.OrdinalIgnoreCase) && Inside(root, final);
        }

        private static bool DirectoryPathMatches(SafeFileHandle handle, string expected)
        {
            string final = FinalPath(handle);
            return final != null && string.Equals(final.TrimEnd('\\'), expected.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase);
        }

        private static string FinalPath(SafeFileHandle handle)
        {
            var text = new StringBuilder(32768);
            uint count = GetFinalPathNameByHandleW(handle, text, (uint)text.Capacity, 0);
            if (count == 0 || count >= text.Capacity) return null;
            string final = text.ToString();
            if (!final.StartsWith(@"\\?\", StringComparison.Ordinal) || final.StartsWith(@"\\?\UNC\", StringComparison.OrdinalIgnoreCase)) return null;
            return final.Substring(4);
        }

        private static bool Inside(string root, string full) => full.StartsWith(root.TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase);
        private static string Location(string root, int depth) => depth == 0 ? root : root + " 하위 폴더";
        private static SamsungFileInspectionEntry Failure(string name, string label, SamsungFileEntryStatus status) => new SamsungFileInspectionEntry(name, label, status);
        private static string CanonicalName(string name)
        {
            foreach (string target in Targets) if (string.Equals(name, target, StringComparison.OrdinalIgnoreCase)) return target;
            return null;
        }
        private static void AddFailures(Scan scan, string label, SamsungFileEntryStatus status)
        {
            scan.Partial = true;
            foreach (string name in Targets)
            {
                if (scan.Entries.Count >= SamsungFileInspectionReport.MaximumEntries) { scan.Limited = true; break; }
                scan.Entries.Add(Failure(name, label, status));
            }
        }

        [DllImport("kernel32.dll", ExactSpelling = true, CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern uint GetFinalPathNameByHandleW(SafeFileHandle file, StringBuilder path, uint length, uint flags);

        [DllImport("kernel32.dll", ExactSpelling = true, CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern SafeFileHandle CreateFileW(string path, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);

        [DllImport("kernel32.dll", ExactSpelling = true, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool GetFileInformationByHandleEx(SafeFileHandle file, int informationClass, out AttributeTag information, uint size);
    }
}
