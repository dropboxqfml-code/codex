using System;
using System.IO;
using System.Linq;
using System.Text;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.Controls;

internal static partial class Program
{
    private static void RegisterSavedBatteryObservationTests()
    {
        Add("saved observation round trips exported rows and graph gaps using the existing TXT format", () =>
        {
            var session = new BatteryObservationSession(); session.Start();
            session.Record(TimeSpan.Zero, new BatterySnapshot(0, ExternalPowerStatus.Disconnected, BatteryChargeState.Discharging, ""));
            session.Record(TimeSpan.FromSeconds(10), BatterySnapshot.Unknown("PRIVATE-ERROR"));
            session.Record(TimeSpan.FromSeconds(20), new BatterySnapshot(80, ExternalPowerStatus.Connected, BatteryChargeState.NotCharging, ""));
            session.Record(TimeSpan.FromSeconds(60), new BatterySnapshot(100, ExternalPowerStatus.Connected, BatteryChargeState.Charging, ""));
            session.Stop();
            var loaded = SavedBatteryObservation.Parse(session.ExportText(), @"C:\PrivateAccount\battery-observation-old.txt");
            Check(loaded.Success, loaded.ErrorMessage); Equal("battery-observation-old.txt", loaded.FileName);
            Equal(BatteryObservationSessionStatus.Stopped, loaded.Graph.Status);
            Equal(4, loaded.Graph.SampleCount); Equal(3, loaded.Graph.Points.Count); Equal(1, loaded.Graph.GapCount);
            var badGap = SavedBatteryObservation.Parse(session.ExportText()
                .Replace("60,100,Connected,Charging,Observed,No,Yes", "60,100,Connected,Charging,Observed,No,No")
                .Replace("긴 갱신 간격: 1", "긴 갱신 간격: 0"), "bad-gap.txt");
            Check(!badGap.Success, "impossible missing gap flag accepted");
            Check(loaded.Graph.Points.All(p => p.StartsSegment), "lines crossed unavailable data or a time gap");
            Equal(0, loaded.Graph.Points[0].Percent); Equal(100, loaded.Graph.Points[2].Percent);
            string boundary = SavedObservationText().Replace("0,80,", "30,80,")
                .Replace("마지막 샘플 경과초: 0", "마지막 샘플 경과초: 30")
                .Replace("Observed,No,No", "Observed,No,Yes").Replace("긴 갱신 간격: 0", "긴 갱신 간격: 1");
            Check(SavedBatteryObservation.Parse(boundary, "fractional-gap.txt").Success, "rounded thirty-second gap was rejected");
            Check(loaded.Summary.Contains("00:01:00") && loaded.Summary.Contains("사용자 중지"), "summary lost saved status or elapsed time");
            Check(!loaded.Summary.Contains("PrivateAccount") && !loaded.Summary.Contains("PRIVATE-ERROR"), "source text leaked");
            var selection = new BatteryObservationChartSelection(); selection.UpdateGraph(loaded.Graph);
            selection.Select(selection.FindPointIndex(0, 100, 600, 100));
            Equal(0, selection.Point.Percent); selection.Move(1); Equal(80, selection.Point.Percent);
        });

        Add("saved observation accepts UTF8 with BOM and CRLF and leaves caller streams open", () =>
        {
            byte[] bytes = Encoding.UTF8.GetPreamble().Concat(Encoding.UTF8.GetBytes(
                SavedObservationText().Replace("\r\n", "\n").Replace("\n", "\r\n"))).ToArray();
            using (var stream = new MemoryStream(bytes))
            {
                var loaded = SavedBatteryObservation.Read(stream, "legacy.txt");
                Check(loaded.Success, loaded.ErrorMessage);
                Equal(1, loaded.Graph.SampleCount); Check(stream.CanRead, "reader closed the caller stream");
            }
        });

        Add("saved observation retains recording and terminal states without activating a session", () =>
        {
            foreach (var status in new[] { "기록 중", "사용자 중지", "시간 한도 도달", "시간 순서 오류로 중지" })
            {
                var loaded = SavedBatteryObservation.Parse(SavedObservationText().Replace("상태: 사용자 중지", "상태: " + status), "history.txt");
                Check(loaded.Success, loaded.ErrorMessage);
                Check(loaded.Summary.Contains(status), "saved status was changed");
                Equal(1, loaded.Graph.SampleCount);
            }
            var session = new BatteryObservationSession(); session.Start();
            for (int i = 0; i < BatteryObservationSession.MaxSamples; i++)
                session.Record(TimeSpan.FromSeconds(i * 10), new BatterySnapshot(80, ExternalPowerStatus.Connected, BatteryChargeState.NotCharging, ""));
            var full = SavedBatteryObservation.Parse(session.ExportText(), "full.txt");
            Check(full.Success, full.ErrorMessage);
            Equal(721, full.Graph.SampleCount); Equal(7200, full.Graph.ElapsedSeconds);
            Equal(BatteryObservationSessionStatus.SampleLimitReached, full.Graph.Status);
            Check(!SavedBatteryObservation.Parse(session.ExportText().Replace("상태: 샘플 한도 도달", "상태: 기록 중"), "wrong-status.txt").Success,
                "recording status accepted beyond session bounds");
            var oversized = SavedBatteryObservation.Parse(session.ExportText()
                + "7210,80,Connected,NotCharging,Observed,No,No\n", "too-many.txt");
            Check(!oversized.Success && oversized.ErrorMessage.Contains("721"), "row bound was bypassed");
        });

        Add("saved observation preserves all unavailable quality states without inventing drawable points", () =>
        {
            var session = new BatteryObservationSession(); session.Start();
            session.Record(TimeSpan.Zero, new BatterySnapshot(null, ExternalPowerStatus.Connected, BatteryChargeState.NoBattery, ""));
            session.Record(TimeSpan.FromSeconds(10), new BatterySnapshot(50, ExternalPowerStatus.Connected, BatteryChargeState.Charging, "private"));
            session.Record(TimeSpan.FromSeconds(20), new BatterySnapshot(50, ExternalPowerStatus.Disconnected, BatteryChargeState.Charging, ""));
            session.Record(TimeSpan.FromSeconds(30), new BatterySnapshot(null, ExternalPowerStatus.Unknown, BatteryChargeState.Unknown, ""));
            var loaded = SavedBatteryObservation.Parse(session.ExportText(), "unknown.txt");
            Check(loaded.Success, loaded.ErrorMessage); Equal(4, loaded.Graph.SampleCount); Equal(0, loaded.Graph.Points.Count);
        });

        Add("saved observation rejects header metadata and column corruption without publishing partial graphs", () =>
        {
            string text = SavedObservationText();
            foreach (string invalid in new[] {
                "", text.Replace(SavedBatteryObservation.Title, "other report"),
                text.Replace(SavedBatteryObservation.Columns, "elapsed_seconds,percent"),
                text.Replace("상태: 사용자 중지", "상태: unknown"),
                text.Replace("상태: 사용자 중지", "상태: 사용자 중지\n상태: 기록 중"),
                text.Replace("관측 샘플: 1", "관측 샘플: 2"),
                text.Replace("긴 갱신 간격: 0", "긴 갱신 간격: 1"),
                text.Replace("마지막 샘플 경과초: 0", "마지막 샘플 경과초: 1"),
                text.Replace("상태: 사용자 중지", "상태: 시작 전"),
                text.Replace("상태: 사용자 중지", "상태: 샘플 한도 도달"),
                text.Replace("마지막 샘플 경과초: 0", "")
            })
            {
                var loaded = SavedBatteryObservation.Parse(invalid, "bad.txt");
                Check(!loaded.Success && loaded.ErrorMessage.Length > 0, "invalid header accepted");
                Equal(0, loaded.Graph.SampleCount);
            }
        });

        Add("saved observation rejects invalid row values enums quality and private payloads", () =>
        {
            string text = SavedObservationText();
            string row = "0,80,Connected,NotCharging,Observed,No,No";
            foreach (string invalidRow in new[] {
                "0,101,Connected,NotCharging,Observed,No,No",
                "-1,80,Connected,NotCharging,Observed,No,No",
                "7201,80,Connected,NotCharging,Observed,No,No",
                "0,80,1,NotCharging,Observed,No,No",
                "0,80,Connected,999,Observed,No,No",
                "0,80,Connected,NotCharging,Unknown,No,No",
                "0,80,Connected,NotCharging,Observed,Yes,No",
                "0,80,Connected,NoBattery,Observed,No,No",
                "0,80,Connected,NotCharging,Observed,No,private",
                "0,80,Connected,NotCharging,Observed,No,No,extra",
                "PRIVATE-ACCOUNT-PATH"
            })
            {
                var loaded = SavedBatteryObservation.Parse(text.Replace(row, invalidRow), "bad.txt");
                Check(!loaded.Success && !loaded.ErrorMessage.Contains("PRIVATE"), "bad row accepted or echoed");
                Equal(0, loaded.Graph.Points.Count);
            }
        });

        Add("saved observation rejects unordered duplicate too-close and missing rows with row count bounds", () =>
        {
            string text = SavedObservationText();
            string row = "0,80,Connected,NotCharging,Observed,No,No";
            foreach (string extra in new[] { row, row.Replace("0,80", "1,80"), "\n" + row.Replace("0,80", "10,80") })
                Check(!SavedBatteryObservation.Parse(text + extra + "\n", "bad.txt").Success, "duplicate or missing row accepted");
            string tooMany = text + string.Concat(Enumerable.Repeat(row + "\n", BatteryObservationSession.MaxSamples));
            Check(!SavedBatteryObservation.Parse(tooMany, "bad.txt").Success, "oversized row list accepted");
            Check(!SavedBatteryObservation.Parse(text.Substring(0, text.IndexOf(row)), "empty.txt").Success, "no rows accepted");
        });

        Add("saved observation rejects oversized or malformed UTF8 input with bounded nonseekable reads", () =>
        {
            using (var stream = new SavedObservationEndlessStream())
            {
                var loaded = SavedBatteryObservation.Read(stream, "large.txt");
                Check(!loaded.Success && loaded.ErrorMessage.Contains("256"), "oversized stream accepted");
                Equal(SavedBatteryObservation.MaximumBytes + 1, stream.BytesRead);
            }
            using (var stream = new MemoryStream(new byte[] { 0xff, 0xfe, 0xff }))
                Check(!SavedBatteryObservation.Read(stream, "bad.txt").Success, "invalid encoding accepted");
            Check(!SavedBatteryObservation.Parse(new string('x', SavedBatteryObservation.MaximumBytes + 1), "large.txt").Success, "oversized text accepted");
        });
    }

    private static string SavedObservationText()
    {
        var session = new BatteryObservationSession(); session.Start();
        session.Record(TimeSpan.Zero, new BatterySnapshot(80, ExternalPowerStatus.Connected, BatteryChargeState.NotCharging, ""));
        session.Stop(); return session.ExportText();
    }

    private sealed class SavedObservationEndlessStream : Stream
    {
        public int BytesRead;
        public override int Read(byte[] buffer, int offset, int count) { Array.Clear(buffer, offset, count); BytesRead += count; return count; }
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }
}
