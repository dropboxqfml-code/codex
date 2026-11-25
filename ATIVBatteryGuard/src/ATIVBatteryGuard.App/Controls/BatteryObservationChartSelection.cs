using System;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Controls
{
    // Selection refers only to points already present in the immutable graph.
    internal sealed class BatteryObservationChartSelection
    {
        public BatteryObservationGraph Graph { get; private set; } = BatteryObservationGraph.Empty;
        public int Index { get; private set; } = -1;
        public BatteryObservationGraphPoint Point => Index < 0 ? null : Graph.Points[Index];

        private double minimumDomainSeconds = 60;
        public double MinimumDomainSeconds
        {
            get { return minimumDomainSeconds; }
            set
            {
                if (!IsValidMinimumDomain(value)) throw new ArgumentOutOfRangeException(nameof(MinimumDomainSeconds));
                minimumDomainSeconds = value;
            }
        }

        public static bool IsValidMinimumDomain(double value)
        {
            return !double.IsNaN(value) && !double.IsInfinity(value) && value >= 60
                && value <= BatteryObservationSession.MaxDuration.TotalSeconds;
        }

        public double DomainSeconds
        {
            get
            {
                double seconds = Math.Max(minimumDomainSeconds, Graph.ElapsedSeconds);
                foreach (BatteryObservationGraphPoint point in Graph.Points)
                    seconds = Math.Max(seconds, point.ElapsedSeconds);
                return seconds;
            }
        }

        // Coordinates and dimensions are in device-independent plot units.
        // A miss leaves selection to the caller, including clicks on a line
        // between actual observations.
        public int FindPointIndex(double x, double y, double width, double height)
        {
            if (width <= 0 || height <= 0 || double.IsInfinity(width) || double.IsInfinity(height) ||
                double.IsNaN(width) || double.IsNaN(height) || double.IsNaN(x) || double.IsNaN(y))
                return -1;
            int nearest = -1;
            double nearestDistance = 14 * 14;
            double domain = DomainSeconds;
            for (int index = 0; index < Graph.Points.Count; index++)
            {
                BatteryObservationGraphPoint point = Graph.Points[index];
                double dx = point.ElapsedSeconds * width / domain - x;
                double dy = height - point.Percent * height / 100 - y;
                double distance = dx * dx + dy * dy;
                if (distance <= nearestDistance)
                {
                    nearest = index;
                    nearestDistance = distance;
                }
            }
            return nearest;
        }

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
