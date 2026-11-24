using ATIVBatteryGuard.Controls;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterBatteryObservationChartSelectionTests()
    {
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
