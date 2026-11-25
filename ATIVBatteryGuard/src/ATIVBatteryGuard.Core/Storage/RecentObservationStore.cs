using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Core.Storage
{
    [DataContract]
    public sealed class RecentObservationEntry
    {
        [DataMember(Order = 0, IsRequired = true)] public string Path { get; private set; }
        [DataMember(Order = 1, IsRequired = true)] public int SampleCount { get; private set; }
        [DataMember(Order = 2, IsRequired = true)] public int ElapsedSeconds { get; private set; }
        [DataMember(Order = 3, IsRequired = true)] public BatteryObservationSessionStatus Status { get; private set; }
        [DataMember(Order = 4, EmitDefaultValue = false)] public string NoteKey { get; private set; }
        public string NotePreview { get; private set; } = "";
        public bool HasNote => !string.IsNullOrEmpty(NotePreview);
        public string IdentityText => ObservationNoteStore.IdentityLabel(NoteKey);
        public string FileName => System.IO.Path.GetFileName(Path);
        public string Summary => "표본 " + SampleCount.ToString(CultureInfo.InvariantCulture) + "건 · "
            + TimeSpan.FromSeconds(ElapsedSeconds).ToString(@"hh\:mm\:ss", CultureInfo.InvariantCulture)
            + " · " + BatteryObservationSession.StatusText(Status);

        internal RecentObservationEntry(string path, SavedBatteryObservation observation)
        {
            Path = path;
            SampleCount = observation.Graph.SampleCount;
            ElapsedSeconds = observation.Graph.ElapsedSeconds;
            Status = observation.Graph.Status;
            NoteKey = observation.NoteKey;
        }

        public RecentObservationEntry WithNote(ObservationNote note)
        {
            var copy = (RecentObservationEntry)MemberwiseClone();
            copy.NotePreview = note.Available ? ObservationNote.Preview(note.Text) : "메모를 읽지 못했습니다.";
            return copy;
        }

        internal bool IsValid()
        {
            return !string.IsNullOrEmpty(Path) && Path.Length <= 1024 && System.IO.Path.IsPathRooted(Path)
                && !Path.StartsWith(@"\\", StringComparison.Ordinal) && !Path.StartsWith("//", StringComparison.Ordinal)
                && Path.IndexOf("://", StringComparison.Ordinal) < 0
                && Path.IndexOfAny(System.IO.Path.GetInvalidPathChars()) < 0
                && LocalPathPolicy.IsSafeFileName(System.IO.Path.GetFileName(Path))
                && System.IO.Path.GetFullPath(Path) == Path
                && SampleCount >= 1 && SampleCount <= BatteryObservationSession.MaxSamples
                && ElapsedSeconds >= 0 && ElapsedSeconds <= 7200
                && Enum.IsDefined(typeof(BatteryObservationSessionStatus), Status)
                && Status != BatteryObservationSessionStatus.NotStarted
                && (string.IsNullOrEmpty(NoteKey) || ObservationNoteStore.IsValidKey(NoteKey));
        }
    }

    public sealed class RecentObservationStore
    {
        public const int MaximumEntries = 10;
        private const int MaximumBytes = 65536;
        private readonly string directory;
        public string FilePath { get; }

        [DataContract]
        private sealed class Index
        {
            [DataMember(IsRequired = true)] public int Version = 1;
            [DataMember(IsRequired = true)] public List<RecentObservationEntry> Entries = new List<RecentObservationEntry>();
        }

        public RecentObservationStore(string directory)
        {
            this.directory = LocalPathPolicy.NormalizeDirectory(directory);
            FilePath = System.IO.Path.Combine(this.directory, "recent-observations.json");
        }

        public IReadOnlyList<RecentObservationEntry> Load()
        {
            LocalPathPolicy.EnsureNoReparsePoints(FilePath);
            if (!File.Exists(FilePath)) return Array.AsReadOnly(new RecentObservationEntry[0]);
            using (var input = new FileStream(FilePath, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete))
            using (var bytes = new MemoryStream())
            {
                var buffer = new byte[4096];
                int count;
                while ((count = input.Read(buffer, 0, buffer.Length)) != 0)
                {
                    if (bytes.Length + count > MaximumBytes) throw new InvalidDataException();
                    bytes.Write(buffer, 0, count);
                }
                bytes.Position = 0;
                var index = LocalJsonDocument.Read<Index>(bytes.ToArray(), MaximumBytes);
                if (index == null || index.Version != 1 || index.Entries == null || index.Entries.Count > MaximumEntries
                    || index.Entries.Any(entry => entry == null || !entry.IsValid()))
                    throw new InvalidDataException();
                return index.Entries.AsReadOnly();
            }
        }

        public IReadOnlyList<RecentObservationEntry> Record(string path, SavedBatteryObservation observation)
        {
            if (observation == null || !observation.Success) throw new ArgumentException(nameof(observation));
            if (string.IsNullOrEmpty(path) || !System.IO.Path.IsPathRooted(path)
                || path.StartsWith(@"\\", StringComparison.Ordinal) || path.StartsWith("//", StringComparison.Ordinal)
                || path.IndexOf("://", StringComparison.Ordinal) >= 0) throw new IOException();
            string fullPath = LocalPathPolicy.NormalizeFile(path);
            LocalPathPolicy.NormalizeDirectory(System.IO.Path.GetDirectoryName(fullPath));
            LocalPathPolicy.EnsureNoReparsePoints(fullPath);
            var entry = new RecentObservationEntry(fullPath, observation);
            if (!entry.IsValid()) throw new InvalidDataException();
            Directory.CreateDirectory(directory);
            string lockPath = FilePath + ".lock";
            LocalPathPolicy.EnsureNoReparsePoints(lockPath);
            // Serializes read/merge/replace across app instances. A busy index
            // only prevents this cache update, never the TXT save/open itself.
            using (var lease = new FileStream(lockPath, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None))
            {
                var entries = Load().Where(item => !string.Equals(item.Path, fullPath, StringComparison.OrdinalIgnoreCase)).ToList();
                entries.Insert(0, entry);
                entries = entries.Take(MaximumEntries).ToList();
                string temporary = System.IO.Path.Combine(directory, ".recent-" + Guid.NewGuid().ToString("N") + ".tmp");
                try
                {
                    using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                    {
                        new DataContractJsonSerializer(typeof(Index)).WriteObject(output, new Index { Entries = entries });
                        output.Flush(true);
                    }
                    LocalPathPolicy.EnsureNoReparsePoints(FilePath);
                    if (File.Exists(FilePath)) File.Replace(temporary, FilePath, null);
                    else File.Move(temporary, FilePath);
                    return entries.AsReadOnly();
                }
                finally
                {
                    if (File.Exists(temporary)) File.Delete(temporary);
                }
            }
        }
    }
}
