using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Controls
{
    // Selection refers only to points already present in the immutable graph.
    internal sealed class BatteryObservationChartSelection
    {
        public BatteryObservationGraph Graph { get; private set; } = BatteryObservationGraph.Empty;
        public int Index { get; private set; } = -1;
        public BatteryObservationGraphPoint Point => Index < 0 ? null : Graph.Points[Index];

        public void UpdateGraph(BatteryObservationGraph graph)
        {
            BatteryObservationGraphPoint previous = Point;
            Graph = graph ?? BatteryObservationGraph.Empty;
            if (previous == null || Index >= Graph.Points.Count)
            {
                Index = -1;
                return;
            }

            BatteryObservationGraphPoint current = Graph.Points[Index];
            if (previous.ElapsedSeconds != current.ElapsedSeconds || previous.Percent != current.Percent ||
                previous.ExternalPower != current.ExternalPower || previous.ChargeState != current.ChargeState ||
                previous.StartsSegment != current.StartsSegment)
                Index = -1;
        }

        public void Select(int index)
        {
            Index = Graph.Points.Count == 0 ? -1 : System.Math.Max(0, System.Math.Min(index, Graph.Points.Count - 1));
        }

        public void Move(int direction)
        {
            Select(Index < 0 ? Graph.Points.Count - 1 : Index + direction);
        }
    }
}
