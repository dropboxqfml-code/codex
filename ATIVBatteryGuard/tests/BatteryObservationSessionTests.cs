using System;
using System.Linq;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterBatteryObservationSessionTests()
    {
        Add("passive observation starts with no samples and waits for a supplied existing Windows snapshot", () =>
        {
            var session = new BatteryObservationSession();
            Equal(BatteryObservationSessionStatus.NotStarted, session.Status);
            Check(!session.IsRecording && !session.CanExport, "an unstarted observation became evidence");
            Equal(string.Empty, session.ExportText());
            Equal(BatteryObservationRecordResult.NotRecording, session.Record(TimeSpan.Zero, ObservationSnapshot()));
            session.Start();
            Check(session.IsRecording && !session.CanExport && session.SampleCount == 0, "start invented a battery read");
            Check(session.ToDisplayText().Contains("다음 기존 배터리 갱신"), "waiting state is unclear");
            ObservationAssertNoAuthority(session);
        });

        Add("passive observation copies normalized values with relative timestamps and keeps Windows flags separate from protection success", () =>
        {
            var session = new BatteryObservationSession(); session.Start();
            var snapshot = ObservationSnapshot(80, ExternalPowerStatus.Connected, BatteryChargeState.NotCharging);
            Equal(BatteryObservationRecordResult.Added, session.Record(TimeSpan.FromMilliseconds(12500), snapshot));
            var row = session.Samples[0];
            Equal(12, row.ElapsedSeconds); Equal<int?>(80, row.Percent);
            Equal(ExternalPowerStatus.Connected, row.ExternalPower); Equal(BatteryChargeState.NotCharging, row.ChargeState);
            Equal(BatteryObservationQuality.Observed, row.Quality); Check(!row.HasReadError && !row.GapBefore, "valid Windows sample acquired a failure");
            Check(session.ExportText().Contains("12,80,Connected,NotCharging,Observed,No,No"), "bounded row export was changed or inferred");
            Check(!row.IsHardwareObservation && !row.IsChargeLimitConfirmed && !row.CanReadHardware && !row.CanWriteHardware && !row.CanInvokeMethods,
                "a Windows flag was promoted to hardware or protection authority");
            ObservationAssertNoAuthority(session);
        });

        Add("passive observation throttles rapid and duplicate refreshes without adding samples or requesting another read", () =>
        {
            var session = new BatteryObservationSession(); session.Start();
            Equal(BatteryObservationRecordResult.Added, session.Record(TimeSpan.Zero, ObservationSnapshot()));
            foreach (double seconds in new[] { 0.0, 0.5, 1, 5, 9.999 })
                Equal(BatteryObservationRecordResult.TooSoon, session.Record(TimeSpan.FromSeconds(seconds), ObservationSnapshot(99)));
            Equal(1, session.SampleCount); Equal<int?>(80, session.Samples[0].Percent);
            Equal(BatteryObservationRecordResult.Added, session.Record(TimeSpan.FromSeconds(10), ObservationSnapshot(81)));
            Equal(2, session.SampleCount); Equal<int?>(81, session.Samples[1].Percent);
        });

        Add("passive observation preserves long gaps including an initially delayed sample and never fills missing intervals", () =>
        {
            var session = new BatteryObservationSession(); session.Start();
            foreach (int seconds in new[] { 0, 10, 40, 71, 300 })
                Equal(BatteryObservationRecordResult.Added, session.Record(TimeSpan.FromSeconds(seconds), ObservationSnapshot()));
            Equal(5, session.SampleCount); Equal(2, session.GapCount);
            Check(!session.Samples[2].GapBefore && session.Samples[3].GapBefore && session.Samples[4].GapBefore,
                "gap boundary was changed or an unobserved interval was filled");
            Check(session.ExportText().Contains("보간하거나 연속 관측 시간으로 합산하지 않습니다"), "elapsed wall time was treated as continuous observation");
            var delayed = new BatteryObservationSession(); delayed.Start();
            delayed.Record(TimeSpan.FromSeconds(45), ObservationSnapshot());
            Equal(1, delayed.SampleCount); Equal(1, delayed.GapCount); Check(delayed.Samples[0].GapBefore, "initial missing interval disappeared");
        });

        Add("passive observation rejects negative or backward submitted time and cannot resume by supplying a late good timestamp", () =>
        {
            var negative = new BatteryObservationSession(); negative.Start();
            Equal(BatteryObservationRecordResult.InvalidTime, negative.Record(TimeSpan.FromTicks(-1), ObservationSnapshot()));
            Equal(BatteryObservationSessionStatus.InvalidTime, negative.Status); Equal(0, negative.SampleCount);
            Equal(BatteryObservationRecordResult.NotRecording, negative.Record(TimeSpan.Zero, ObservationSnapshot()));
            var backwards = new BatteryObservationSession(); backwards.Start();
            backwards.Record(TimeSpan.FromSeconds(10), ObservationSnapshot());
            Equal(BatteryObservationRecordResult.TooSoon, backwards.Record(TimeSpan.FromSeconds(19), ObservationSnapshot()));
            Equal(BatteryObservationRecordResult.InvalidTime, backwards.Record(TimeSpan.FromSeconds(18), ObservationSnapshot()));
            Equal(1, backwards.SampleCount); Equal(BatteryObservationSessionStatus.InvalidTime, backwards.Status);
            backwards.Stop(); Equal(BatteryObservationSessionStatus.InvalidTime, backwards.Status);
            Equal(BatteryObservationRecordResult.NotRecording, backwards.Record(TimeSpan.FromSeconds(20), ObservationSnapshot()));
        });

        Add("passive observation stops beyond two hours without creating a sample or overflowing a relative timestamp", () =>
        {
            foreach (var late in new[] { TimeSpan.FromHours(2) + TimeSpan.FromTicks(1), TimeSpan.MaxValue })
            {
                var session = new BatteryObservationSession(); session.Start();
                session.Record(TimeSpan.Zero, ObservationSnapshot());
                Equal(BatteryObservationRecordResult.DurationLimitReached, session.Record(late, ObservationSnapshot()));
                Equal(1, session.SampleCount); Check(!session.IsRecording, "an expired session remained open");
                Equal(BatteryObservationSessionStatus.DurationLimitReached, session.Status);
            }
            var exact = new BatteryObservationSession(); exact.Start();
            Equal(BatteryObservationRecordResult.Added, exact.Record(BatteryObservationSession.MaxDuration, ObservationSnapshot()));
            Equal(1, exact.SampleCount); Equal(7200, exact.Samples[0].ElapsedSeconds);
            Equal(BatteryObservationSessionStatus.DurationLimitReached, exact.Status); Equal(1, exact.GapCount);
            var throttledAtLimit = new BatteryObservationSession(); throttledAtLimit.Start();
            throttledAtLimit.Record(TimeSpan.FromSeconds(7195), ObservationSnapshot());
            Equal(BatteryObservationRecordResult.DurationLimitReached,
                throttledAtLimit.Record(BatteryObservationSession.MaxDuration, ObservationSnapshot()));
            Equal(1, throttledAtLimit.SampleCount); Check(!throttledAtLimit.IsRecording, "sample throttling kept the session open at two hours");
            Equal(BatteryObservationSessionStatus.DurationLimitReached, throttledAtLimit.Status);
        });

        Add("passive observation holds at most 721 supplied samples and reaches the bound without enabling charge control", () =>
        {
            var session = new BatteryObservationSession(); session.Start();
            for (int index = 0; index < BatteryObservationSession.MaxSamples; index++)
                Equal(BatteryObservationRecordResult.Added, session.Record(TimeSpan.FromSeconds(index * 10), ObservationSnapshot()));
            Equal(721, session.SampleCount); Equal(0, session.GapCount);
            Equal(BatteryObservationSessionStatus.SampleLimitReached, session.Status);
            Equal(BatteryObservationRecordResult.NotRecording, session.Record(TimeSpan.FromSeconds(7210), ObservationSnapshot()));
            Check(session.ExportText().Length < 100000, "bounded rows produced an unbounded export");
            Check(session.ToDisplayText().Contains("80% 정체나 NotCharging 한 개 또는 여러 개만으로"), "repeated unchanged samples were promoted to success");
            ObservationAssertNoAuthority(session);
        });

        Add("passive observation keeps missing erroneous invalid-enum and no-battery data distinct without retaining private errors", () =>
        {
            var session = new BatteryObservationSession(); session.Start();
            string privateError = "PRIVATE-ERROR C:\\Users\\PrivateName\\report.txt S-1-5-21-private";
            BatterySnapshot[] source = {
                null, BatterySnapshot.Unknown(privateError),
                ObservationSnapshot(null),
                ObservationSnapshot(80, (ExternalPowerStatus)999, (BatteryChargeState)999),
                ObservationSnapshot(80, ExternalPowerStatus.Connected, BatteryChargeState.NotCharging, privateError),
                ObservationSnapshot(50, ExternalPowerStatus.Connected, BatteryChargeState.NoBattery),
                ObservationSnapshot(20, ExternalPowerStatus.Disconnected, BatteryChargeState.Charging),
            };
            for (int index = 0; index < source.Length; index++) session.Record(TimeSpan.FromSeconds(index * 10), source[index]);
            Equal(7, session.SampleCount);
            foreach (int index in new[] { 0, 1, 2, 3, 4, 6 }) Equal(BatteryObservationQuality.Unknown, session.Samples[index].Quality);
            Equal(BatteryObservationQuality.NoBattery, session.Samples[5].Quality); Equal<int?>(null, session.Samples[5].Percent);
            Equal(ExternalPowerStatus.Unknown, session.Samples[3].ExternalPower); Equal(BatteryChargeState.Unknown, session.Samples[3].ChargeState);
            Check(session.Samples[0].HasReadError && session.Samples[1].HasReadError && session.Samples[4].HasReadError,
                "read failure was silently converted to a known zero or off");
            string report = session.ExportText() + session.ToDisplayText();
            foreach (string token in new[] { "PRIVATE-ERROR", "PrivateName", "S-1-5-21-private", "C:\\Users" })
                Check(!report.Contains(token), "private error text escaped the snapshot copy");
        });

        Add("passive observation stop clear and restart preserve detached earlier snapshots without reusing old evidence", () =>
        {
            var session = new BatteryObservationSession(); session.Start();
            session.Record(TimeSpan.Zero, ObservationSnapshot(79));
            var oldRows = session.Samples; var old = oldRows[0];
            session.Stop(); Equal(BatteryObservationSessionStatus.Stopped, session.Status);
            Equal(BatteryObservationRecordResult.NotRecording, session.Record(TimeSpan.FromSeconds(10), ObservationSnapshot()));
            Equal(1, session.SampleCount);
            session.Start(); Equal(0, session.SampleCount); Equal(0, session.GapCount); Check(session.IsRecording && !session.CanExport, "restart retained a prior candidate");
            session.Record(TimeSpan.Zero, ObservationSnapshot(81));
            Equal<int?>(79, old.Percent); Equal(1, oldRows.Count); Equal<int?>(81, session.Samples[0].Percent);
            session.Clear(); Equal(BatteryObservationSessionStatus.NotStarted, session.Status);
            Equal(0, session.SampleCount); Equal(string.Empty, session.ExportText()); Check(!session.IsRecording && !session.CanExport, "clear retained evidence");
        });

        Add("passive observation API exposes only bounded normalized data and cannot query control or prove hardware state", () =>
        {
            var type = typeof(BatteryObservationSession);
            Check(type.GetConstructors().All(constructor => constructor.GetParameters().Length == 0), "session accepts a provider or execution dependency");
            foreach (var property in typeof(BatteryObservationSample).GetProperties())
            {
                Check(!property.CanWrite, "sample became mutable");
                Check(property.PropertyType.IsEnum || property.PropertyType == typeof(bool) || property.PropertyType == typeof(int) || property.PropertyType == typeof(int?),
                    "sample exposes raw error text, identity, wall time or a provider");
            }
            var session = new BatteryObservationSession(); ObservationAssertNoAuthority(session);
            session.Start(); session.Record(TimeSpan.Zero, ObservationSnapshot()); session.Stop(); ObservationAssertNoAuthority(session);
            Check(!session.ExportText().Contains("PRIVATE"), "unsupplied identity data appeared in report");
            session.Start(); session.Record(TimeSpan.Zero, ObservationSnapshot(0));
            Equal<int?>(0, session.Samples[0].Percent); Equal(BatteryObservationQuality.Observed, session.Samples[0].Quality);
        });
    }

    private static BatterySnapshot ObservationSnapshot(int? percent = 80, ExternalPowerStatus ac = ExternalPowerStatus.Connected,
        BatteryChargeState state = BatteryChargeState.NotCharging, string error = "")
        => new BatterySnapshot(percent, ac, state, error);

    private static void ObservationAssertNoAuthority(BatteryObservationSession session)
    {
        Check(!session.IsHardwareObservation && !session.IsChargeLimitConfirmed && !session.CanInvokeMethods && !session.CanReadHardware && !session.CanWriteHardware,
            "passive supplied Windows snapshots became physical control or proof");
    }
}
