using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    public enum BatteryObservationSessionStatus
    {
        NotStarted, Recording, Stopped, SampleLimitReached, DurationLimitReached, InvalidTime
    }

    public enum BatteryObservationRecordResult
    {
        Added, NotRecording, TooSoon, InvalidTime, DurationLimitReached
    }

    public enum BatteryObservationQuality { Observed, Unknown, NoBattery }

    // A copy of bounded, caller-supplied Windows status fields only. The source
    // snapshot and its free-form Error string are never retained.
    public sealed class BatteryObservationSample
    {
        public int ElapsedSeconds { get; }
        public int? Percent { get; }
        public ExternalPowerStatus ExternalPower { get; }
        public BatteryChargeState ChargeState { get; }
        public BatteryObservationQuality Quality { get; }
        public bool HasReadError { get; }
        public bool GapBefore { get; }
        public bool IsHardwareObservation => false;
        public bool IsChargeLimitConfirmed => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        internal BatteryObservationSample(TimeSpan elapsed, BatterySnapshot source, bool gapBefore)
        {
            ElapsedSeconds = (int)Math.Floor(elapsed.TotalSeconds);
            GapBefore = gapBefore;
            bool validPower = source != null && Enum.IsDefined(typeof(ExternalPowerStatus), source.ExternalPower);
            bool validState = source != null && Enum.IsDefined(typeof(BatteryChargeState), source.ChargeState);
            ExternalPower = validPower ? source.ExternalPower : ExternalPowerStatus.Unknown;
            ChargeState = validState ? source.ChargeState : BatteryChargeState.Unknown;
            HasReadError = source == null || !string.IsNullOrEmpty(source.Error);
            int? percent = source == null ? (int?)null : source.Percent;
            Percent = percent.HasValue && percent.Value >= 0 && percent.Value <= 100 ? percent : null;
            if (ChargeState == BatteryChargeState.NoBattery) Percent = null;

            bool contradictory = ChargeState == BatteryChargeState.Charging && ExternalPower == ExternalPowerStatus.Disconnected;
            bool unknown = HasReadError || !validPower || !validState || ExternalPower == ExternalPowerStatus.Unknown ||
                ChargeState == BatteryChargeState.Unknown || contradictory;
            Quality = unknown ? BatteryObservationQuality.Unknown
                : ChargeState == BatteryChargeState.NoBattery ? BatteryObservationQuality.NoBattery
                : !Percent.HasValue ? BatteryObservationQuality.Unknown : BatteryObservationQuality.Observed;
        }
    }

    // Explicitly started, bounded in-memory observation. There is no provider,
    // timer, clock, file, identity, OEM API, reservation or control adapter here.
    // The caller feeds snapshots already obtained by its normal Windows poll.
    public sealed class BatteryObservationSession
    {
        public const int MaxSamples = 721;
        public static readonly TimeSpan MinSampleInterval = TimeSpan.FromSeconds(10);
        public static readonly TimeSpan MaxDuration = TimeSpan.FromHours(2);
        public static readonly TimeSpan GapThreshold = TimeSpan.FromSeconds(30);
        private readonly object sync = new object();
        private readonly List<BatteryObservationSample> samples = new List<BatteryObservationSample>();
        private TimeSpan? lastSubmitted, lastAccepted;
        private int gapCount;
        private BatteryObservationSessionStatus status;

        public BatteryObservationSessionStatus Status { get { lock (sync) return status; } }
        public bool IsRecording { get { lock (sync) return status == BatteryObservationSessionStatus.Recording; } }
        public int SampleCount { get { lock (sync) return samples.Count; } }
        public int GapCount { get { lock (sync) return gapCount; } }
        public bool CanExport { get { lock (sync) return samples.Count != 0; } }
        public int? LastSampleElapsedSeconds { get { lock (sync) return samples.Count == 0 ? (int?)null : samples[samples.Count - 1].ElapsedSeconds; } }
        public IReadOnlyList<BatteryObservationSample> Samples { get { lock (sync) return Array.AsReadOnly(samples.ToArray()); } }
        public bool IsHardwareObservation => false;
        public bool IsChargeLimitConfirmed => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        public void Start()
        {
            lock (sync)
            {
                ResetCore();
                status = BatteryObservationSessionStatus.Recording;
            }
        }

        public BatteryObservationRecordResult Record(TimeSpan elapsed, BatterySnapshot snapshot)
        {
            lock (sync)
            {
                if (status != BatteryObservationSessionStatus.Recording) return BatteryObservationRecordResult.NotRecording;
                if (elapsed < TimeSpan.Zero || (lastSubmitted.HasValue && elapsed < lastSubmitted.Value))
                {
                    status = BatteryObservationSessionStatus.InvalidTime;
                    return BatteryObservationRecordResult.InvalidTime;
                }
                lastSubmitted = elapsed;
                if (elapsed > MaxDuration)
                {
                    status = BatteryObservationSessionStatus.DurationLimitReached;
                    return BatteryObservationRecordResult.DurationLimitReached;
                }
                if (lastAccepted.HasValue && elapsed - lastAccepted.Value < MinSampleInterval)
                {
                    if (elapsed == MaxDuration)
                    {
                        status = BatteryObservationSessionStatus.DurationLimitReached;
                        return BatteryObservationRecordResult.DurationLimitReached;
                    }
                    return BatteryObservationRecordResult.TooSoon;
                }

                bool gap = elapsed - (lastAccepted ?? TimeSpan.Zero) > GapThreshold;
                samples.Add(new BatteryObservationSample(elapsed, snapshot, gap));
                lastAccepted = elapsed;
                if (gap) gapCount++;
                if (samples.Count >= MaxSamples) status = BatteryObservationSessionStatus.SampleLimitReached;
                else if (elapsed == MaxDuration) status = BatteryObservationSessionStatus.DurationLimitReached;
                return BatteryObservationRecordResult.Added;
            }
        }

        public void Stop()
        {
            lock (sync)
                if (status == BatteryObservationSessionStatus.Recording) status = BatteryObservationSessionStatus.Stopped;
        }

        public void Clear() { lock (sync) ResetCore(); }

        public string ToDisplayText()
        {
            lock (sync) return SummaryCore();
        }

        public string ExportText()
        {
            lock (sync)
            {
                // No-data sessions cannot be exported as apparently observed
                // evidence. Saving is an explicit caller action outside Core.
                if (samples.Count == 0) return string.Empty;
                var text = new StringBuilder();
                text.AppendLine("ATIV Battery Guard — 읽기 전용 Windows 배터리 관측");
                text.Append(SummaryCore());
                text.AppendLine("경과초는 시작 이후의 상대 시간이며, 샘플 사이 상태를 보간하거나 연속 관측 시간으로 합산하지 않습니다.");
                text.AppendLine("elapsed_seconds,percent,ac,state,quality,read_error,gap_before");
                foreach (var sample in samples)
                {
                    text.Append(sample.ElapsedSeconds.ToString(CultureInfo.InvariantCulture)).Append(',');
                    text.Append(sample.Percent.HasValue ? sample.Percent.Value.ToString(CultureInfo.InvariantCulture) : "Unknown").Append(',');
                    text.Append(sample.ExternalPower).Append(',').Append(sample.ChargeState).Append(',').Append(sample.Quality).Append(',');
                    text.Append(sample.HasReadError ? "Yes" : "No").Append(',').AppendLine(sample.GapBefore ? "Yes" : "No");
                }
                return text.ToString();
            }
        }

        private void ResetCore()
        {
            samples.Clear(); lastSubmitted = null; lastAccepted = null; gapCount = 0;
            status = BatteryObservationSessionStatus.NotStarted;
        }

        private string SummaryCore()
        {
            var text = new StringBuilder();
            text.AppendLine("읽기 전용 배터리 관측 · 기존 Windows 상태");
            text.AppendLine("상태: " + StatusText(status));
            text.AppendLine("관측 샘플: " + samples.Count.ToString(CultureInfo.InvariantCulture) + " / 긴 갱신 간격: " + gapCount.ToString(CultureInfo.InvariantCulture));
            if (status == BatteryObservationSessionStatus.Recording && samples.Count == 0)
                text.AppendLine("다음 기존 배터리 갱신부터 기록합니다. 시작 버튼은 추가 조회를 요청하지 않습니다.");
            if (samples.Count != 0)
                text.AppendLine("마지막 샘플 경과초: " + samples[samples.Count - 1].ElapsedSeconds.ToString(CultureInfo.InvariantCulture));
            text.AppendLine("10초 이상 간격·최대2시간/721개로 보관하며, 30초를 넘는 간격은 결측 구간으로 표시합니다.");
            text.AppendLine("AC·잔량·Windows 충전 상태만 기록하며 전류·충전기 레지스터를 측정하지 않습니다.");
            text.AppendLine("80% 정체나 NotCharging 한 개 또는 여러 개만으로 충전 제한 성공을 판정하지 않습니다.");
            text.AppendLine("실제 충전 제한 확인: 미확인. 보호 설정을 조회·변경하거나 재시험하지 않습니다.");
            return text.ToString();
        }

        private static string StatusText(BatteryObservationSessionStatus value)
        {
            switch (value)
            {
                case BatteryObservationSessionStatus.Recording: return "기록 중";
                case BatteryObservationSessionStatus.Stopped: return "사용자 중지";
                case BatteryObservationSessionStatus.SampleLimitReached: return "샘플 한도 도달";
                case BatteryObservationSessionStatus.DurationLimitReached: return "시간 한도 도달";
                case BatteryObservationSessionStatus.InvalidTime: return "시간 순서 오류로 중지";
                default: return "시작 전";
            }
        }
    }
}
