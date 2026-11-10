using System;
using System.Collections.Generic;
using System.Linq;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterBatteryObservationGraphTests()
    {
        Add("observation graph starts empty and preserves a recording state without inventing a sample", () =>
        {
            var empty = BatteryObservationGraph.Empty;
            Equal(0, empty.SampleCount); Equal(0, empty.ObservedPointCount); Equal(0, empty.ElapsedSeconds); Equal(0, empty.GapCount);
            Equal(BatteryObservationSessionStatus.NotStarted, empty.Status);
            var graph = BatteryObservationGraph.FromSamples(new BatteryObservationSample[0], BatteryObservationSessionStatus.Recording);
            Equal(0, graph.Points.Count); Equal(0, graph.SampleCount);
            Equal(BatteryObservationSessionStatus.Recording, graph.Status);
        });

        Add("observation graph retains one relative point including a genuine zero and the supplied Windows flags", () =>
        {
            var sample = GraphSample(45, 0, ExternalPowerStatus.Disconnected, BatteryChargeState.Discharging, gapBefore: true);
            var graph = BatteryObservationGraph.FromSamples(new[] { sample }, BatteryObservationSessionStatus.Stopped);
            Equal(1, graph.SampleCount); Equal(1, graph.ObservedPointCount); Equal(45, graph.ElapsedSeconds); Equal(1, graph.GapCount);
            Equal(BatteryObservationSessionStatus.Stopped, graph.Status);
            var point = graph.Points[0];
            Equal(45, point.ElapsedSeconds); Equal(0, point.Percent); Check(point.StartsSegment, "a single point needs a segment start");
            Equal(ExternalPowerStatus.Disconnected, point.ExternalPower); Equal(BatteryChargeState.Discharging, point.ChargeState);
        });

        Add("observation graph omits unknown erroneous no-battery and invalid values and never joins across them", () =>
        {
            var rows = new[] {
                GraphSample(0, 79), GraphSample(10, null), GraphSample(20, 80),
                GraphSample(30, 50, state: BatteryChargeState.NoBattery), GraphSample(40, 81),
                GraphSample(50, 82, error: "PRIVATE user path and serial"), GraphSample(60, 83),
                GraphSample(70, -1), GraphSample(80, 84), GraphSample(90, 101), GraphSample(100, 85),
                GraphSample(110, 86, ac: ExternalPowerStatus.Unknown), GraphSample(120, 100), GraphSample(130, null)
            };
            var graph = BatteryObservationGraph.FromSamples(rows, BatteryObservationSessionStatus.Recording);
            Equal(14, graph.SampleCount); Equal(7, graph.ObservedPointCount); Equal(130, graph.ElapsedSeconds);
            Check(graph.Points.Select(point => point.ElapsedSeconds).SequenceEqual(new[] { 0, 20, 40, 60, 80, 100, 120 }), "missing data became a point");
            Check(graph.Points.Select(point => point.Percent).SequenceEqual(new[] { 79, 80, 81, 83, 84, 85, 100 }), "unknown was replaced with zero or a carried value");
            Check(graph.Points.All(point => point.StartsSegment), "line bridged an unobserved or invalid sample");
        });

        Add("observation graph keeps unknown-only elapsed time and gap metadata without drawing a zero", () =>
        {
            var graph = BatteryObservationGraph.FromSamples(new[] {
                GraphSample(40, null, gapBefore: true), GraphSample(80, 80, error: "private", gapBefore: true),
                GraphSample(90, 80, state: BatteryChargeState.NoBattery)
            }, BatteryObservationSessionStatus.DurationLimitReached);
            Equal(3, graph.SampleCount); Equal(0, graph.ObservedPointCount); Equal(90, graph.ElapsedSeconds); Equal(2, graph.GapCount);
            Equal(BatteryObservationSessionStatus.DurationLimitReached, graph.Status);
        });

        Add("observation graph breaks explicit long backward and duplicate gaps while preserving the exact thirty second boundary", () =>
        {
            var graph = BatteryObservationGraph.FromSamples(new[] {
                GraphSample(0, 80), GraphSample(10, 81), GraphSample(40, 82), GraphSample(71, 83),
                GraphSample(81, 84, gapBefore: true), GraphSample(80, 85), GraphSample(90, 86), GraphSample(90, 87)
            }, BatteryObservationSessionStatus.InvalidTime);
            Check(graph.Points.Select(point => point.StartsSegment).SequenceEqual(new[] { true, false, false, true, true, true, false, true }),
                "line continuity ignored missing time or rewrote the thirty second boundary");
            Check(graph.Points.Select(point => point.ElapsedSeconds).SequenceEqual(new[] { 0, 10, 40, 71, 81, 80, 90, 90 }), "input times were sorted or interpolated");
            Equal(1, graph.GapCount); Equal(8, graph.SampleCount); Equal(BatteryObservationSessionStatus.InvalidTime, graph.Status);
        });

        Add("observation graph is detached from input replacement session restart and collection writes", () =>
        {
            var session = new BatteryObservationSession(); session.Start();
            session.Record(TimeSpan.Zero, new BatterySnapshot(79, ExternalPowerStatus.Connected, BatteryChargeState.NotCharging, ""));
            var rows = session.Samples.ToArray();
            var graph = BatteryObservationGraph.FromSamples(rows, session.Status);
            rows[0] = GraphSample(20, 10);
            session.Clear(); session.Start();
            session.Record(TimeSpan.Zero, new BatterySnapshot(99, ExternalPowerStatus.Connected, BatteryChargeState.NotCharging, ""));
            Equal(79, graph.Points[0].Percent); Equal(0, graph.ElapsedSeconds); Equal(1, graph.SampleCount);
            Equal(BatteryObservationSessionStatus.Recording, graph.Status);
            var writable = graph.Points as IList<BatteryObservationGraphPoint>;
            Check(writable != null && writable.IsReadOnly, "points expose a writable collection");
            bool rejected = false;
            try { writable[0] = null; } catch (NotSupportedException) { rejected = true; }
            Check(rejected, "a caller replaced a graph point");
            Equal(79, graph.Points[0].Percent);
            foreach (var property in typeof(BatteryObservationGraphPoint).GetProperties())
            {
                Check(!property.CanWrite, "a graph point became mutable");
                Check(property.PropertyType == typeof(int) || property.PropertyType == typeof(bool) || property.PropertyType.IsEnum,
                    "graph point exposes source objects private error text or execution dependencies");
            }
        });

        Add("observation graph accepts the full passive session bound without extending its duration or copying export text", () =>
        {
            var session = new BatteryObservationSession(); session.Start();
            for (int index = 0; index < BatteryObservationSession.MaxSamples; index++)
                session.Record(TimeSpan.FromSeconds(index * 10), new BatterySnapshot(80, ExternalPowerStatus.Connected, BatteryChargeState.NotCharging, ""));
            string before = session.ExportText();
            var graph = BatteryObservationGraph.FromSamples(session.Samples, session.Status);
            Equal(721, graph.SampleCount); Equal(721, graph.ObservedPointCount); Equal(7200, graph.ElapsedSeconds);
            Equal(BatteryObservationSessionStatus.SampleLimitReached, graph.Status);
            Equal(1, graph.Points.Count(point => point.StartsSegment)); Equal(before, session.ExportText());
        });

        Add("observation graph rejects rows outside the session bounds rather than trimming or clamping evidence", () =>
        {
            var oversized = Enumerable.Repeat(GraphSample(0, 80), BatteryObservationSession.MaxSamples + 1).ToArray();
            foreach (var rows in new[] { oversized, new[] { GraphSample(-1, 80) }, new[] { GraphSample(7201, 80) } })
            {
                bool rejected = false;
                try { BatteryObservationGraph.FromSamples(rows, BatteryObservationSessionStatus.Recording); }
                catch (ArgumentOutOfRangeException) { rejected = true; }
                Check(rejected, "graph accepted an input beyond the bounded session domain");
            }
        });

        Add("observation graph rejects missing input rows and invalid status instead of inventing an empty valid observation", () =>
        {
            bool rejected = false;
            try { BatteryObservationGraph.FromSamples(null, BatteryObservationSessionStatus.Stopped); }
            catch (ArgumentNullException) { rejected = true; }
            Check(rejected, "missing input became an apparently valid empty graph");
            rejected = false;
            try { BatteryObservationGraph.FromSamples(new BatteryObservationSample[] { null }, BatteryObservationSessionStatus.Recording); }
            catch (ArgumentException) { rejected = true; }
            Check(rejected, "a missing row became a sample");
            rejected = false;
            try { BatteryObservationGraph.FromSamples(new BatteryObservationSample[0], (BatteryObservationSessionStatus)999); }
            catch (ArgumentOutOfRangeException) { rejected = true; }
            Check(rejected, "graph retained an undefined status");
        });
    }

    private static BatteryObservationSample GraphSample(int seconds, int? percent,
        ExternalPowerStatus ac = ExternalPowerStatus.Connected, BatteryChargeState state = BatteryChargeState.NotCharging,
        string error = "", bool gapBefore = false)
        => new BatteryObservationSample(TimeSpan.FromSeconds(seconds), new BatterySnapshot(percent, ac, state, error), gapBefore);
}
