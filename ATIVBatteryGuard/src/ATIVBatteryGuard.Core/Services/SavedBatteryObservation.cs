using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Storage;

namespace ATIVBatteryGuard.Core.Services
{
    // A historical file snapshot. It never enters a live observation session.
    public sealed class SavedBatteryObservation
    {
        public const int MaximumBytes = 256 * 1024;
        public const string Title = "ATIV Battery Guard — 읽기 전용 Windows 배터리 관측";
        public const string Columns = "elapsed_seconds,percent,ac,state,quality,read_error,gap_before";
        private static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);

        public string FileName { get; }
        public string NoteKey { get; }
        public string Text { get; }
        public string SourcePath { get; }
        public string IdentityText => ObservationNoteStore.IdentityLabel(NoteKey);
        public BatteryObservationGraph Graph { get; }
        public string ErrorMessage { get; }
        public bool Success => ErrorMessage.Length == 0;
        public string Summary => "파일 저장 당시 상태 · " + BatteryObservationSession.StatusText(Graph.Status)
            + " · 표본 " + Graph.SampleCount.ToString(CultureInfo.InvariantCulture) + "건"
            + " · 잔량 표본 " + Graph.ObservedPointCount.ToString(CultureInfo.InvariantCulture) + "개"
            + " · 마지막 경과 " + TimeSpan.FromSeconds(Graph.ElapsedSeconds).ToString(@"hh\:mm\:ss", CultureInfo.InvariantCulture)
            + " · 기록 공백 " + Graph.GapCount.ToString(CultureInfo.InvariantCulture) + "건";

        private SavedBatteryObservation(string fileName, BatteryObservationGraph graph, string error, string noteKey = "", string text = "", string sourcePath = "")
        {
            string leaf = (fileName ?? "관찰 TXT").Replace('\\', '/');
            FileName = leaf.Substring(leaf.LastIndexOf('/') + 1);
            Graph = graph;
            NoteKey = noteKey;
            Text = text;
            SourcePath = sourcePath;
            ErrorMessage = error;
        }

        private static SavedBatteryObservation Fail(string message)
        {
            return new SavedBatteryObservation(null, BatteryObservationGraph.Empty, message);
        }

        public static SavedBatteryObservation Read(Stream input, string fileName) { return Read(input, fileName, null); }

        public static SavedBatteryObservation Read(Stream input, string fileName, string sourcePath)
        {
            if (input == null) throw new ArgumentNullException(nameof(input));
            using (var bytes = new MemoryStream())
            {
                var buffer = new byte[4096];
                int count;
                while ((count = input.Read(buffer, 0, Math.Min(buffer.Length, MaximumBytes + 1 - (int)bytes.Length))) != 0)
                {
                    bytes.Write(buffer, 0, count);
                    if (bytes.Length > MaximumBytes)
                        return Fail("관찰 TXT는 256 KiB 이하만 열 수 있습니다.");
                }
                try { return Parse(Utf8.GetString(bytes.ToArray()), fileName, sourcePath); }
                catch (DecoderFallbackException) { return Fail("UTF-8 관찰 TXT 파일인지 확인하세요."); }
            }
        }

        public static SavedBatteryObservation Parse(string text, string fileName) { return Parse(text, fileName, null); }

        public static SavedBatteryObservation Parse(string text, string fileName, string sourcePath)
        {
            if (text == null) return Fail("관찰 TXT 내용이 없습니다.");
            try
            {
                if (text.Length > MaximumBytes || Utf8.GetByteCount(text) > MaximumBytes)
                    return Fail("관찰 TXT는 256 KiB 이하만 열 수 있습니다.");
            }
            catch (EncoderFallbackException) { return Fail("UTF-8 관찰 TXT 파일인지 확인하세요."); }

            using (var reader = new StringReader(text.TrimStart('\uFEFF')))
            {
                if (reader.ReadLine() != Title)
                    return Fail("ATIV Battery Guard 관찰 TXT 형식을 확인하세요.");
                BatteryObservationSessionStatus? status = null;
                int? reportedCount = null, reportedGaps = null, reportedElapsed = null;
                string line;
                int headerLines = 0;
                while ((line = reader.ReadLine()) != null && line != Columns)
                {
                    if (++headerLines > 32) return Fail("관찰 TXT 머리글이 너무 깁니다.");
                    if (line.StartsWith("상태: ", StringComparison.Ordinal))
                    {
                        BatteryObservationSessionStatus parsed;
                        if (status.HasValue || !TryStatus(line.Substring(4), out parsed))
                            return Fail("관찰 종료 상태가 올바르지 않습니다.");
                        status = parsed;
                    }
                    else if (line.StartsWith("관측 샘플: ", StringComparison.Ordinal))
                    {
                        string[] counts = line.Substring(7).Split(new[] { " / 긴 갱신 간격: " }, StringSplitOptions.None);
                        int samples, gaps;
                        if (reportedCount.HasValue || counts.Length != 2 ||
                            !TryNumber(counts[0], out samples) || !TryNumber(counts[1], out gaps))
                            return Fail("관찰 TXT의 표본 수와 공백 수가 올바르지 않습니다.");
                        reportedCount = samples;
                        reportedGaps = gaps;
                    }
                    else if (line.StartsWith("마지막 샘플 경과초: ", StringComparison.Ordinal))
                    {
                        int elapsed;
                        if (reportedElapsed.HasValue || !TryNumber(line.Substring("마지막 샘플 경과초: ".Length), out elapsed))
                            return Fail("마지막 표본의 경과 시간이 올바르지 않습니다.");
                        reportedElapsed = elapsed;
                    }
                }
                if (line != Columns || !status.HasValue || !reportedCount.HasValue || !reportedElapsed.HasValue)
                    return Fail("관찰 TXT의 상태·표본 요약 또는 CSV 열이 빠져 있습니다.");

                var rows = new List<BatteryObservationSample>();
                int previousElapsed = -10, gapsSeen = 0;
                bool blankLine = false;
                while ((line = reader.ReadLine()) != null)
                {
                    if (line.Length == 0) { blankLine = true; continue; }
                    if (blankLine) return Fail("표본 사이에 빈 행이 있습니다. 원본 관찰 TXT를 확인하세요.");
                    if (rows.Count >= BatteryObservationSession.MaxSamples)
                        return Fail("관찰 표본은 최대 721개까지 열 수 있습니다.");
                    string[] fields = line.Split(',');
                    if (fields.Length != 7) return Fail("표본 행의 CSV 열 수가 올바르지 않습니다.");
                    int elapsed, percentValue;
                    if (!TryNumber(fields[0], out elapsed) || elapsed > BatteryObservationSession.MaxDuration.TotalSeconds ||
                        elapsed - previousElapsed < BatteryObservationSession.MinSampleInterval.TotalSeconds)
                        return Fail("표본 경과 시간은 0~7200초 범위에서 10초 이상 간격으로 증가해야 합니다.");
                    int? percent = null;
                    if (fields[1] != "Unknown")
                    {
                        if (!TryNumber(fields[1], out percentValue) || percentValue > 100)
                            return Fail("배터리 잔량은 0~100 또는 Unknown이어야 합니다.");
                        percent = percentValue;
                    }
                    ExternalPowerStatus power;
                    BatteryChargeState charge;
                    BatteryObservationQuality quality;
                    if (!TryEnum(fields[2], out power) || !TryEnum(fields[3], out charge) || !TryEnum(fields[4], out quality) ||
                        (fields[5] != "Yes" && fields[5] != "No") || (fields[6] != "Yes" && fields[6] != "No"))
                        return Fail("표본의 전원·충전·품질·오류·공백 값이 올바르지 않습니다.");
                    if (fields[6] == "No" && elapsed - Math.Max(0, previousElapsed) > BatteryObservationSession.GapThreshold.TotalSeconds)
                        return Fail("표본의 경과 시간과 공백 표시가 서로 맞지 않습니다.");
                    var sample = new BatteryObservationSample(TimeSpan.FromSeconds(elapsed),
                        new BatterySnapshot(percent, power, charge, fields[5] == "Yes" ? "saved read error" : ""),
                        fields[6] == "Yes");
                    if (sample.Quality != quality || sample.Percent != percent)
                        return Fail("표본의 잔량·품질·충전 상태가 서로 맞지 않습니다.");
                    rows.Add(sample);
                    if (sample.GapBefore) gapsSeen++;
                    previousElapsed = elapsed;
                }
                if (rows.Count == 0 || rows.Count != reportedCount || gapsSeen != reportedGaps || previousElapsed != reportedElapsed)
                    return Fail("관찰 TXT의 요약과 실제 표본이 일치하지 않습니다.");
                if (status == BatteryObservationSessionStatus.NotStarted ||
                    (status == BatteryObservationSessionStatus.SampleLimitReached && rows.Count != BatteryObservationSession.MaxSamples) ||
                    (rows.Count == BatteryObservationSession.MaxSamples && status != BatteryObservationSessionStatus.SampleLimitReached) ||
                    (previousElapsed == 7200 && rows.Count < BatteryObservationSession.MaxSamples &&
                        status != BatteryObservationSessionStatus.DurationLimitReached))
                    return Fail("관찰 종료 상태와 표본 수가 서로 맞지 않습니다.");
                return new SavedBatteryObservation(fileName,
                    BatteryObservationGraph.FromSamples(rows.AsReadOnly(), status.Value), "",
                    sourcePath == null ? "" : ObservationNoteStore.Identity(sourcePath, text), text, sourcePath ?? "");
            }
        }

        private static bool TryNumber(string text, out int value)
        {
            return int.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out value);
        }

        private static bool TryEnum<T>(string text, out T value) where T : struct
        {
            return Enum.TryParse(text, out value) && Enum.IsDefined(typeof(T), value) && value.ToString() == text;
        }

        private static bool TryStatus(string text, out BatteryObservationSessionStatus status)
        {
            foreach (BatteryObservationSessionStatus value in Enum.GetValues(typeof(BatteryObservationSessionStatus)))
            {
                if (BatteryObservationSession.StatusText(value) == text) { status = value; return true; }
            }
            status = BatteryObservationSessionStatus.NotStarted;
            return false;
        }
    }
}
