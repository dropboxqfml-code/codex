using ATIVBatteryGuard.Controls;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterBatteryObservationChartSelectionTests()
    {
        Add("chart mouse hit testing reaches real zero and full percent points including their visible edge", () =>
        {
            var selection = new BatteryObservationChartSelection();
            selection.UpdateGraph(BatteryObservationGraph.FromSamples(new[] {
                GraphSample(0, 0), GraphSample(10, null), GraphSample(60, 100)
            }, BatteryObservationSessionStatus.Stopped));
            Equal(60.0, selection.DomainSeconds);
            Equal(0, selection.FindPointIndex(0, 100, 600, 100));
            Equal(1, selection.FindPointIndex(600, 0, 600, 100));
            Equal(0, selection.FindPointIndex(-14, 100, 600, 100));
            Equal(-1, selection.FindPointIndex(-15, 100, 600, 100));
            Equal(1, selection.FindPointIndex(600, -10, 600, 100));
            Equal(-1, selection.FindPointIndex(300, 50, 600, 100));
            Equal(-1, selection.Index);
        });

        Add("chart mouse hits and keyboard movement share selection with nearest point and deterministic overlap", () =>
        {
            var selection = new BatteryObservationChartSelection();
            selection.UpdateGraph(BatteryObservationGraph.FromSamples(new[] {
                GraphSample(0, 50), GraphSample(1, 50), GraphSample(60, 100)
            }, BatteryObservationSessionStatus.Stopped));
            Equal(0, selection.FindPointIndex(0.1, 50, 60, 100));
            Equal(1, selection.FindPointIndex(0.5, 50, 60, 100));
            selection.Select(selection.FindPointIndex(1, 50, 60, 100));
            selection.Move(1); Equal(2, selection.Index);
            selection.Move(-1); Equal(1, selection.Index);
            Equal(-1, selection.FindPointIndex(30, 50, 60, 100));
            Equal(1, selection.Index);
        });

        Add("chart mouse hit testing uses current plot size and complete domain through unavailable intervals", () =>
        {
            var selection = new BatteryObservationChartSelection();
            selection.UpdateGraph(BatteryObservationGraph.FromSamples(new[] {
                GraphSample(30, 50), GraphSample(90, null)
            }, BatteryObservationSessionStatus.Stopped));
            Equal(90.0, selection.DomainSeconds);
            Equal(0, selection.FindPointIndex(100, 50, 300, 100));
            Equal(0, selection.FindPointIndex(200, 100, 600, 200));
            Equal(-1, selection.FindPointIndex(100, 50, 600, 200));
            foreach (double invalid in new[] { 0.0, -1.0, double.NaN, double.PositiveInfinity })
            {
                Equal(-1, selection.FindPointIndex(100, 50, invalid, 100));
                Equal(-1, selection.FindPointIndex(100, 50, 300, invalid));
            }
            Equal(-1, selection.FindPointIndex(double.NaN, 50, 300, 100));
            Equal(-1, selection.FindPointIndex(100, double.PositiveInfinity, 300, 100));
            selection.UpdateGraph(BatteryObservationGraph.Empty);
            Equal(-1, selection.FindPointIndex(0, 0, 300, 100));
        });

        Add("chart keyboard navigation handles empty graphs and selects only actual points across gaps", () =>
        {
            var selection = new BatteryObservationChartSelection();
            selection.Move(1); selection.Select(0); Equal(-1, selection.Index); Check(selection.Point == null, "invented a point");
            selection.UpdateGraph(BatteryObservationGraph.FromSamples(new[] {
                GraphSample(0, 0), GraphSample(10, null), GraphSample(40, 100)
            }, BatteryObservationSessionStatus.Stopped));
            selection.Move(-1); Equal(1, selection.Index); Equal(100, selection.Point.Percent);
            selection.Move(-1); Equal(0, selection.Index); Equal(0, selection.Point.Percent);
            selection.Move(-1); Equal(0, selection.Index);
            selection.Move(1); Equal(1, selection.Index); Equal(40, selection.Point.ElapsedSeconds);
            selection.Move(1); Equal(1, selection.Index);
            selection.Select(0); Equal(0, selection.Index);
            selection.Select(selection.Graph.Points.Count - 1); Equal(1, selection.Index);
        });

        Add("chart keyboard selection survives append stop and unknown-only updates without jumping to newest", () =>
        {
            var selection = new BatteryObservationChartSelection();
            selection.UpdateGraph(BatteryObservationGraph.FromSamples(new[] { GraphSample(0, 80), GraphSample(10, 81) },
                BatteryObservationSessionStatus.Recording));
            selection.Select(0);
            foreach (var status in new[] { BatteryObservationSessionStatus.Recording, BatteryObservationSessionStatus.Stopped })
            {
                selection.UpdateGraph(BatteryObservationGraph.FromSamples(new[] {
                    GraphSample(0, 80), GraphSample(10, 81), GraphSample(20, 82), GraphSample(30, null)
                }, status));
                Equal(0, selection.Index); Equal(80, selection.Point.Percent);
            }
        });

        Add("chart keyboard selection clears on clear restart changed points and missing graph", () =>
        {
            var selection = new BatteryObservationChartSelection();
            selection.UpdateGraph(BatteryObservationGraph.FromSamples(new[] { GraphSample(0, 80), GraphSample(10, 81) },
                BatteryObservationSessionStatus.Recording));
            selection.Select(1);
            selection.UpdateGraph(BatteryObservationGraph.Empty);
            Equal(-1, selection.Index); Check(selection.Point == null, "cleared selection leaked");
            selection.UpdateGraph(BatteryObservationGraph.FromSamples(new[] { GraphSample(0, 80) },
                BatteryObservationSessionStatus.Recording));
            Equal(-1, selection.Index);
            selection.Select(0);
            selection.UpdateGraph(BatteryObservationGraph.FromSamples(new[] { GraphSample(0, 80, ac: ExternalPowerStatus.Disconnected) },
                BatteryObservationSessionStatus.Recording));
            Equal(-1, selection.Index);
            selection.Select(0); selection.UpdateGraph(null);
            Equal(-1, selection.Index); Check(selection.Point == null, "missing graph retained old point");
        });
    }
}
