using System;
using System.Collections.Generic;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    public sealed class BatteryObservationGraphPoint
    {
        public int ElapsedSeconds { get; }
        public int Percent { get; }
        public bool StartsSegment { get; }
        public ExternalPowerStatus ExternalPower { get; }
        public BatteryChargeState ChargeState { get; }

        internal BatteryObservationGraphPoint(BatteryObservationSample sample, bool startsSegment)
        {
            ElapsedSeconds = sample.ElapsedSeconds;
            Percent = sample.Percent.Value;
            StartsSegment = startsSegment;
            ExternalPower = sample.ExternalPower;
            ChargeState = sample.ChargeState;
        }
    }

    // A detached presentation snapshot of the existing passive session. No
    // reads, clocks, interpolation, export changes or protection inference.
    public sealed class BatteryObservationGraph
    {
        private static readonly IReadOnlyList<BatteryObservationGraphPoint> noPoints =
            Array.AsReadOnly(new BatteryObservationGraphPoint[0]);

        public static BatteryObservationGraph Empty { get; } = new BatteryObservationGraph(
            noPoints, 0, 0, 0, BatteryObservationSessionStatus.NotStarted);

        public IReadOnlyList<BatteryObservationGraphPoint> Points { get; }
        public int SampleCount { get; }
        public int ObservedPointCount => Points.Count;
        public int ElapsedSeconds { get; }
        public int GapCount { get; }
        public BatteryObservationSessionStatus Status { get; }

        private BatteryObservationGraph(IReadOnlyList<BatteryObservationGraphPoint> points,
            int sampleCount, int elapsedSeconds, int gapCount, BatteryObservationSessionStatus status)
        {
            Points = points;
            SampleCount = sampleCount;
            ElapsedSeconds = elapsedSeconds;
            GapCount = gapCount;
            Status = status;
        }

        public static BatteryObservationGraph FromSamples(IReadOnlyList<BatteryObservationSample> samples,
            BatteryObservationSessionStatus status)
        {
            if (samples == null) throw new ArgumentNullException(nameof(samples));
            if (!Enum.IsDefined(typeof(BatteryObservationSessionStatus), status))
                throw new ArgumentOutOfRangeException(nameof(status));
            int sampleCount = samples.Count;
            if (sampleCount == 0)
                return status == BatteryObservationSessionStatus.NotStarted ? Empty
                    : new BatteryObservationGraph(noPoints, 0, 0, 0, status);
            // Session snapshots already obey these limits. Reject other input
            // rather than trimming rows or changing their relative timestamps.
            if (sampleCount > BatteryObservationSession.MaxSamples)
                throw new ArgumentOutOfRangeException(nameof(samples), "A graph cannot exceed the session sample limit.");

            int elapsedSeconds = 0, gapCount = 0;
            int? previousElapsed = null;
            bool startsSegment = true;
            var points = new List<BatteryObservationGraphPoint>(sampleCount);
            for (int index = 0; index < sampleCount; index++)
            {
                var sample = samples[index];
                if (sample == null) throw new ArgumentException("A sample is required.", nameof(samples));
                int elapsed = sample.ElapsedSeconds;
                if (elapsed < 0 || elapsed > BatteryObservationSession.MaxDuration.TotalSeconds)
                    throw new ArgumentOutOfRangeException(nameof(samples), "Sample time must be within the session duration.");
                elapsedSeconds = elapsed;
                if (sample.GapBefore) gapCount++;
                if (sample.GapBefore || (previousElapsed.HasValue &&
                    (elapsed <= previousElapsed.Value || elapsed - previousElapsed.Value > BatteryObservationSession.GapThreshold.TotalSeconds)))
                    startsSegment = true;
                previousElapsed = elapsed;

                if (sample.Quality != BatteryObservationQuality.Observed || sample.HasReadError ||
                    !sample.Percent.HasValue || sample.Percent.Value < 0 || sample.Percent.Value > 100)
                {
                    startsSegment = true;
                    continue;
                }

                points.Add(new BatteryObservationGraphPoint(sample, startsSegment));
                startsSegment = false;
            }

            return new BatteryObservationGraph(points.AsReadOnly(), sampleCount, elapsedSeconds, gapCount, status);
        }
    }
}
