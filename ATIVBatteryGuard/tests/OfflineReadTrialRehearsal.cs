using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Management;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.WmiInterop;

internal static partial class Program
{
    // Compiled ONLY in PortableTests alongside the local SDK stand-ins. No
    // production entry, firmware template or runtime approval switch is added.
    private enum RehearsalScenario { PublicEntryBlocked = 1, PreCancelled, GateTimedOut, EarlyTerminalBeforeCallExit, MissingTerminalAfterThrow, ValidFrameUnattributed }
    private enum RehearsalCheckpoint { BeforeSdk, GateRejected, BoundedResultPendingClose, Settled }
    private enum RehearsalOutcome { Passed, Failed }
    private enum RehearsalDisposition { NotAttempted, Indeterminate, AttributionNotEstablished }

    private sealed class RehearsalSnapshot
    {
        public RehearsalCheckpoint Checkpoint { get; init; }
        public WsabiWmiSingleReadPreparationStatus PreparationStatus { get; init; }
        public WsabiWmiWindowsPreparationStatus? RegistrationStatus { get; init; }
        public WsabiWmiWindowsInputPreparationStatus? InputStatus { get; init; }
        public WsabiWmiWindowsCleanupStatus? PreparationInputCleanupStatus { get; init; }
        public bool InputOwnershipTransferred { get; init; }
        public WsabiWmiWindowsSdkBindingStatus? SdkStatus { get; init; }
        public WsabiWmiFrameExchangeStatus? FrameStatus { get; init; }
        public bool? IsValidFrame { get; init; }
        public WsabiWmiExchangeGateStatus? FakeGateStatus { get; init; }
        public int FakeGateCalls { get; init; }
        public int FakeInvokeCalls { get; init; }
        public bool FakeInvokeHookExited { get; init; }
        public int FakeTerminalEmissions { get; init; }
        public int FakeObjectEmissions { get; init; }
        public int ResultPublications { get; init; }
        public int SubscriptionsRemaining { get; init; }
        public int ParameterDisposeAttempts { get; init; }
        public int BufferDisposeAttempts { get; init; }
        public int BorrowedTargetDisposeAttempts { get; init; }
        public int OutputDisposeAttempts { get; init; }
        public bool? LeaseHeld { get; init; }
        public bool? RunCompleted { get; init; }
        public bool? CloseCompleted { get; init; }
        public WsabiWmiWindowsCleanupStatus? FinalCleanupStatus { get; init; }
        public bool SyntheticCleanupUsed { get; init; }
    }

    private sealed class RehearsalCase
    {
        internal RehearsalScenario Id;
        internal Func<List<RehearsalSnapshot>, Task> Run;
    }

    private sealed class RehearsalCaseResult
    {
        public RehearsalScenario Scenario { get; init; }
        public RehearsalOutcome Outcome { get; init; }
        public IReadOnlyList<RehearsalSnapshot> Observations { get; init; }
        public RehearsalDisposition Disposition { get; init; }
    }

    private sealed class RehearsalReport
    {
        public int SchemaVersion => 1;
        public string ReportKind => "offline-read-trial-rehearsal";
        public bool UsesSdkStandIns => true;
        public bool IsHardwareObservation => false;
        public int ActualOemCalls => 0;
        public int ActualSystemManagementCalls => 0;
        public string RealTrialReadiness => "NotEstablished";
        public string ProtectionReadAndControl => "Unsupported";
        public IReadOnlyList<RehearsalCaseResult> Scenarios { get; init; }
        public int Passed => Scenarios.Count(x => x.Outcome == RehearsalOutcome.Passed);
        public int Failed => Scenarios.Count - Passed;
    }

    private static JsonSerializerOptions RehearsalJsonOptions()
    {
        var options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, WriteIndented = true };
        options.Converters.Add(new JsonStringEnumConverter());
        return options;
    }

    private static RehearsalCase[] RehearsalCases() => new[]
    {
        new RehearsalCase { Id = RehearsalScenario.PublicEntryBlocked, Run = RehearseBlockedAsync },
        new RehearsalCase { Id = RehearsalScenario.PreCancelled, Run = RehearseCancelledAsync },
        new RehearsalCase { Id = RehearsalScenario.GateTimedOut, Run = RehearseGateAsync },
        new RehearsalCase { Id = RehearsalScenario.EarlyTerminalBeforeCallExit, Run = rows => RehearsePendingAsync(rows, true) },
        new RehearsalCase { Id = RehearsalScenario.MissingTerminalAfterThrow, Run = rows => RehearsePendingAsync(rows, false) },
        new RehearsalCase { Id = RehearsalScenario.ValidFrameUnattributed, Run = RehearseValidAsync }
    };

    private static async Task<RehearsalCaseResult> ExecuteRehearsalAsync(RehearsalCase scenario)
    {
        var rows = new List<RehearsalSnapshot>();
        var outcome = RehearsalOutcome.Passed;
        try
        {
            Check(typeof(ManagementObject).Assembly == typeof(Program).Assembly, "SDK stand-in assembly required");
            await scenario.Run(rows);
            Check(rows.Count != 0, "scenario produced no measured checkpoints");
        }
        catch { outcome = RehearsalOutcome.Failed; } // Never serialize exception text, type, test key or objects.
        return new RehearsalCaseResult
        {
            Scenario = scenario.Id, Outcome = outcome, Observations = rows.AsReadOnly(),
            Disposition = outcome == RehearsalOutcome.Failed ? RehearsalDisposition.Indeterminate
                : scenario.Id == RehearsalScenario.ValidFrameUnattributed ? RehearsalDisposition.AttributionNotEstablished
                : scenario.Id <= RehearsalScenario.GateTimedOut ? RehearsalDisposition.NotAttempted : RehearsalDisposition.Indeterminate
        };
    }

    private static async Task<int> WriteOfflineRehearsalAsync(string path)
    {
        try
        {
            ValidateRehearsalPath(path);
            var results = new List<RehearsalCaseResult>();
            foreach (var scenario in RehearsalCases()) results.Add(await ExecuteRehearsalAsync(scenario));
            var report = new RehearsalReport { Scenarios = results.AsReadOnly() };
            SaveRehearsalReport(path, report);
            Console.WriteLine("OFFLINE_REHEARSAL " + report.Passed + " passed, " + report.Failed + " failed; actual OEM calls 0");
            return report.Failed == 0 ? 0 : 1;
        }
        catch { Console.Error.WriteLine("OFFLINE_REHEARSAL_REPORT_ERROR"); return 2; }
    }

    private static void ValidateRehearsalPath(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || path.StartsWith(@"\\", StringComparison.Ordinal) ||
            path.StartsWith("//", StringComparison.Ordinal) || path.Contains("://") ||
            !string.Equals(Path.GetExtension(path), ".json", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("A new local JSON report is required.");
    }

    private static void SaveRehearsalReport(string path, RehearsalReport report)
    {
        ValidateRehearsalPath(path);
        string full = Path.GetFullPath(path);
        Directory.CreateDirectory(Path.GetDirectoryName(full));
        // Preserve every existing file, including previous rehearsal evidence.
        using (var stream = new FileStream(full, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            JsonSerializer.Serialize(stream, report, RehearsalJsonOptions());
    }

    private sealed class RehearsalDriver
    {
        internal readonly SdkBindingFixture Fixture = new SdkBindingFixture();
        internal int Terminals, Objects, Publications, HookExited;
        internal WsabiWmiExchangeGateStatus? GateStatus;
        internal ManagementBaseObject Output;

        internal RehearsalDriver()
        {
            Fixture.Gate.Handler = (timeout, stop) =>
            {
                GateStatus = WsabiWmiExchangeGateStatus.Acquired;
                return new WsabiWmiExchangeGateAttempt(GateStatus.Value, new CooperativeTestLease());
            };
            // Even an unexpected invocation in a rejection scenario must drain.
            Fixture.Target.OnInvoke = (observer, method, input, options) =>
            {
                try { Terminal(ManagementStatus.AccessDenied); }
                finally { Interlocked.Exchange(ref HookExited, 1); }
            };
        }
        internal void Terminal(ManagementStatus status)
        { Interlocked.Increment(ref Terminals); Fixture.Observer.EmitCompleted(status); }
        internal void Object()
        { Interlocked.Increment(ref Objects); Fixture.Observer.EmitObjectReady(Output); }

        internal RehearsalSnapshot Snapshot(RehearsalCheckpoint checkpoint, WsabiWmiSingleReadPreparationResult prepared,
            WsabiWmiFrameExchangeResult shown = null, Task run = null, Task close = null,
            WsabiWmiWindowsCleanupStatus? cleanup = null, bool syntheticCleanup = false)
        {
            var f = Fixture;
            return new RehearsalSnapshot
            {
                Checkpoint = checkpoint, PreparationStatus = prepared.Status, RegistrationStatus = prepared.RegistrationStatus,
                InputStatus = prepared.InputStatus, InputOwnershipTransferred = prepared.InputOwnershipTransferred, SdkStatus = prepared.SdkStatus,
                PreparationInputCleanupStatus = prepared.InputCleanupStatus,
                FrameStatus = shown?.Status, IsValidFrame = shown == null ? (bool?)null : shown.IsValidFrame,
                FakeGateStatus = GateStatus, FakeGateCalls = f.Gate.Calls, FakeInvokeCalls = f.Target.InvokeCalls,
                FakeInvokeHookExited = Volatile.Read(ref HookExited) != 0, FakeTerminalEmissions = Volatile.Read(ref Terminals),
                FakeObjectEmissions = Volatile.Read(ref Objects), ResultPublications = Volatile.Read(ref Publications),
                SubscriptionsRemaining = f.Observer.ObjectReadySubscriberCount + f.Observer.CompletedSubscriberCount,
                ParameterDisposeAttempts = f.Pair.Parameters.ConcreteDisposeCalls, BufferDisposeAttempts = f.Pair.Buffer.ConcreteDisposeCalls,
                BorrowedTargetDisposeAttempts = f.Target.ConcreteDisposeCalls + f.Target.ComponentDisposeCalls,
                OutputDisposeAttempts = Output?.ConcreteDisposeCalls ?? 0, LeaseHeld = f.Gate.LastLease?.IsHeld,
                RunCompleted = run?.IsCompleted, CloseCompleted = close?.IsCompleted, FinalCleanupStatus = cleanup,
                SyntheticCleanupUsed = syntheticCleanup
            };
        }
    }

    private static async Task RehearseBlockedAsync(List<RehearsalSnapshot> rows)
    {
        var d = new RehearsalDriver(); var f = d.Fixture;
        var result = await TrialEntryCall(f.Plan, f.Binding, InputPreparationRequest(), f.Gate);
        rows.Add(d.Snapshot(RehearsalCheckpoint.BeforeSdk, result));
        TrialEntryAssertBlocked(result); f.AssertNoLowerWork();
    }

    private static async Task RehearseCancelledAsync(List<RehearsalSnapshot> rows)
    {
        using (var cancellation = new CancellationTokenSource())
        {
            var d = new RehearsalDriver(); var f = d.Fixture; cancellation.Cancel();
            var result = await TrialEntryCall(f.Plan, f.Binding, InputPreparationRequest(), f.Gate, cancellation.Token);
            rows.Add(d.Snapshot(RehearsalCheckpoint.BeforeSdk, result));
            Equal(WsabiWmiSingleReadPreparationStatus.PreparationNotReady, result.Status);
            Equal<WsabiWmiWindowsPreparationStatus?>(WsabiWmiWindowsPreparationStatus.Cancelled, result.RegistrationStatus);
            Check(result.Invocation == null && !result.InputOwnershipTransferred, "pre-cancel created an invocation");
            f.AssertNoLowerWork();
        }
    }

    private static Task RehearseGateAsync(List<RehearsalSnapshot> rows) => RehearseGateAsync(rows, false);

    private static async Task RehearseGateAsync(List<RehearsalSnapshot> rows, bool injectUnexpectedInvocation)
    {
        var d = new RehearsalDriver(); var f = d.Fixture;
        f.Gate.Handler = (timeout, stop) =>
        {
            d.GateStatus = injectUnexpectedInvocation ? WsabiWmiExchangeGateStatus.Acquired : WsabiWmiExchangeGateStatus.TimedOut;
            return new WsabiWmiExchangeGateAttempt(d.GateStatus.Value, injectUnexpectedInvocation ? new CooperativeTestLease() : null);
        };
        var prepared = await SdkLifeReady(SdkBindingPrepare(f));
        Task<WsabiWmiFrameExchangeResult> run = null;
        try
        {
            run = prepared.Invocation.RunAndCloseAsync(value => Interlocked.Increment(ref d.Publications));
            await CooperativeAwait(run); var shown = await run;
            var close = prepared.Invocation.RequestCloseAsync(); await CooperativeAwait(close);
            rows.Add(d.Snapshot(RehearsalCheckpoint.GateRejected, prepared, shown, run, close, await close));
            Equal(WsabiWmiFrameExchangeStatus.TransportFailure, shown.Status);
            Equal<WsabiWmiExchangeGateStatus?>(WsabiWmiExchangeGateStatus.TimedOut, d.GateStatus);
            Equal(0, f.Target.InvokeCalls); Equal(1, f.Gate.Calls); Equal(1, d.Publications);
            SdkLifeAssertPairDisposes(f.Pair, 1); SdkLifeAssertUnsubscribed(f.Observer);
        }
        finally
        {
            if (f.Target.InvokeCalls != 0 && Volatile.Read(ref d.Terminals) == 0) d.Terminal(ManagementStatus.AccessDenied);
            await CooperativeAwait(prepared.Invocation.RequestCloseAsync());
            if (run != null) await CooperativeAwait(run);
        }
    }

    private static async Task RehearsePendingAsync(List<RehearsalSnapshot> rows, bool earlyTerminal, bool injectCleanupFailure = false)
    {
        using (var release = new ManualResetEventSlim())
        {
            var d = new RehearsalDriver(); var f = d.Fixture;
            if (injectCleanupFailure) f.Pair.Parameters.OnDispose = () => { throw new InvalidOperationException("PRIVATE rehearsal cleanup detail"); };
            var entered = CooperativeCompletion(); var published = CooperativeCompletion();
            ManagementBaseObject embedded;
            d.Output = earlyTerminal ? WindowsOutputFixture(BoundChannelReply(), out embedded) : new ManagementBaseObject();
            if (!earlyTerminal) d.Output.OnGetProperties = () => { throw new InvalidOperationException("PRIVATE rehearsal output must not be read"); };
            f.Target.OnInvoke = (observer, method, input, options) =>
            {
                entered.TrySetResult(true);
                try
                {
                    d.Object();
                    if (!earlyTerminal) throw new InvalidOperationException("PRIVATE rehearsal dispatch detail");
                    d.Terminal(ManagementStatus.NoError); SdkLifeWait(release);
                }
                finally { Interlocked.Exchange(ref d.HookExited, 1); }
            };
            var prepared = await SdkLifeReady(SdkLifePrepare(f.Plan, f.Facts, f.Target, f.Observer, f.Pair, f.Gate,
                TimeSpan.FromMilliseconds(500)));
            WsabiWmiFrameExchangeResult shown = null;
            Task<WsabiWmiFrameExchangeResult> run = null;
            Task<WsabiWmiWindowsCleanupStatus> close = null;
            try
            {
                run = prepared.Invocation.RunAndCloseAsync(value =>
                { shown = value; Interlocked.Increment(ref d.Publications); published.TrySetResult(true); });
                await CooperativeAwait(entered.Task); await CooperativeAwait(published.Task);
                close = prepared.Invocation.RequestCloseAsync();
                rows.Add(d.Snapshot(RehearsalCheckpoint.BoundedResultPendingClose, prepared, shown, run, close));
                Equal(WsabiWmiFrameExchangeStatus.TimedOut, shown.Status);
                Check(!run.IsCompleted && !close.IsCompleted && f.Gate.LastLease.IsHeld, "bounded result released pending ownership");
                Equal(1, f.Target.InvokeCalls); Equal(1, d.Publications); SdkLifeAssertPairDisposes(f.Pair, 0);
                Equal(earlyTerminal ? 1 : 0, d.Terminals);
                if (!earlyTerminal) Equal(2, f.Observer.ObjectReadySubscriberCount + f.Observer.CompletedSubscriberCount);
            }
            finally
            {
                release.Set();
                if (run != null && f.Target.InvokeCalls == 0 && !run.IsCompleted) await CooperativeAwait(Task.WhenAny(entered.Task, run));
                // Explicit test-only settlement, never a real SDK/end signal.
                if (f.Target.InvokeCalls != 0 && Volatile.Read(ref d.Terminals) == 0) d.Terminal(ManagementStatus.AccessDenied);
                close = prepared.Invocation.RequestCloseAsync();
                WsabiWmiWindowsCleanupStatus? cleanup = null;
                try
                {
                    await CooperativeAwait(close); cleanup = await close;
                    if (run != null) await CooperativeAwait(run);
                }
                finally
                {
                    rows.Add(d.Snapshot(close.IsCompleted && (run == null || run.IsCompleted)
                        ? RehearsalCheckpoint.Settled : RehearsalCheckpoint.BoundedResultPendingClose,
                        prepared, shown, run, close, cleanup, true));
                }
            }
            Equal(1, d.Publications); Equal(WsabiWmiFrameExchangeStatus.TimedOut, (await run).Status);
            Equal(WsabiWmiWindowsCleanupStatus.Complete, await close); SdkLifeAssertPairDisposes(f.Pair, 1);
            SdkLifeAssertBorrowedTarget(f.Target); SdkLifeAssertUnsubscribed(f.Observer);
            Equal(1, f.Gate.LastLease.DisposeCalls); Check(!f.Gate.LastLease.IsHeld, "settled owner still held");
        }
    }

    private static async Task RehearseValidAsync(List<RehearsalSnapshot> rows)
    {
        var d = new RehearsalDriver(); var f = d.Fixture; ManagementBaseObject embedded;
        d.Output = WindowsOutputFixture(BoundChannelReply(), out embedded);
        f.Target.OnInvoke = (observer, method, input, options) =>
        {
            try { d.Object(); }
            finally { try { d.Terminal(ManagementStatus.NoError); } finally { Interlocked.Exchange(ref d.HookExited, 1); } }
        };
        var prepared = await SdkLifeReady(SdkBindingPrepare(f));
        Task<WsabiWmiFrameExchangeResult> run = null;
        try
        {
            run = prepared.Invocation.RunAndCloseAsync(value => Interlocked.Increment(ref d.Publications));
            await CooperativeAwait(run); var result = await run;
            var close = prepared.Invocation.RequestCloseAsync(); await CooperativeAwait(close);
            rows.Add(d.Snapshot(RehearsalCheckpoint.Settled, prepared, result, run, close, await close));
            Check(result.IsValidFrame && !result.IsHardwareObservation && !result.CanReadHardware && !result.CanWriteHardware && !result.CanInvokeMethods,
                "synthetic frame became a hardware observation");
            Equal(1, f.Target.InvokeCalls); Equal(1, d.Publications); Equal(1, d.Terminals);
            SdkLifeAssertPairDisposes(f.Pair, 1); SdkLifeAssertBorrowedTarget(f.Target); SdkLifeAssertUnsubscribed(f.Observer);
        }
        finally
        {
            if (run != null && !run.IsCompleted && f.Target.InvokeCalls != 0) d.Terminal(ManagementStatus.AccessDenied);
            await CooperativeAwait(prepared.Invocation.RequestCloseAsync());
            if (run != null) await CooperativeAwait(run);
        }
    }

    private static void RegisterOfflineRehearsalTests()
    {
        foreach (var scenario in RehearsalCases())
            AddAsync("offline rehearsal " + scenario.Id, async () =>
                Equal(RehearsalOutcome.Passed, (await ExecuteRehearsalAsync(scenario)).Outcome));

        AddAsync("offline rehearsal failure report excludes exception input and retains measured checkpoints", async () =>
        {
            var result = await ExecuteRehearsalAsync(new RehearsalCase
            {
                Id = RehearsalScenario.PublicEntryBlocked,
                Run = rows => { rows.Add(new RehearsalSnapshot { Checkpoint = RehearsalCheckpoint.BeforeSdk }); throw new Exception(@"C:\Users\PRIVATE-REHEARSAL\secret.txt"); }
            });
            Equal(RehearsalOutcome.Failed, result.Outcome); Equal(1, result.Observations.Count);
            string json = JsonSerializer.Serialize(new RehearsalReport { Scenarios = new[] { result } }, RehearsalJsonOptions());
            Check(!json.Contains("PRIVATE-REHEARSAL") && !json.Contains("secret.txt") && !json.Contains("Exception"), "private failure escaped report");
            Check(json.Contains("NotEstablished") && json.Contains("Unsupported"), "offline report became trial authority");
        });
        Add("offline rehearsal report rejects non JSON and remote paths before file access", () =>
        {
            foreach (var path in new[] { "", "trial.attempt", @"\\server\share\trial.json", "//server/share/trial.json", "https://example.org/trial.json" })
                BatteryThrows<ArgumentException>(() => ValidateRehearsalPath(path));
        });
        Add("offline rehearsal report never overwrites existing evidence", () => WithDirectory(directory =>
        {
            string path = Path.Combine(directory, "rehearsal.json"); File.WriteAllText(path, "keep");
            BatteryThrows<IOException>(() => SaveRehearsalReport(path, new RehearsalReport { Scenarios = new RehearsalCaseResult[0] }));
            Equal("keep", File.ReadAllText(path));
        }));
        AddAsync("offline rehearsal unexpected gate dispatch is failed indeterminate and fully drained", async () =>
        {
            var result = await ExecuteRehearsalAsync(new RehearsalCase
            { Id = RehearsalScenario.GateTimedOut, Run = rows => RehearseGateAsync(rows, true) });
            Equal(RehearsalOutcome.Failed, result.Outcome); Equal(RehearsalDisposition.Indeterminate, result.Disposition);
            var last = result.Observations.Last();
            Equal(1, last.FakeInvokeCalls); Equal(1, last.FakeTerminalEmissions);
            Equal<bool?>(true, last.RunCompleted); Equal<bool?>(true, last.CloseCompleted);
            Equal<WsabiWmiWindowsCleanupStatus?>(WsabiWmiWindowsCleanupStatus.Complete, last.FinalCleanupStatus);
            Equal(1, last.ParameterDisposeAttempts); Equal(1, last.BufferDisposeAttempts);
        });
        AddAsync("offline rehearsal failed cleanup remains in failure JSON after run fault", async () =>
        {
            var result = await ExecuteRehearsalAsync(new RehearsalCase
            { Id = RehearsalScenario.MissingTerminalAfterThrow, Run = rows => RehearsePendingAsync(rows, false, true) });
            Equal(RehearsalOutcome.Failed, result.Outcome); Equal(RehearsalDisposition.Indeterminate, result.Disposition);
            Equal(2, result.Observations.Count); var last = result.Observations.Last();
            Equal<WsabiWmiWindowsCleanupStatus?>(WsabiWmiWindowsCleanupStatus.Failed, last.FinalCleanupStatus);
            Equal<bool?>(true, last.RunCompleted); Equal<bool?>(true, last.CloseCompleted);
            Check(last.SyntheticCleanupUsed, "fake cleanup was attributed to a real provider");
            Equal(1, last.ParameterDisposeAttempts); Equal(1, last.BufferDisposeAttempts);
            string json = JsonSerializer.Serialize(result, RehearsalJsonOptions());
            Check(json.Contains("Failed") && !json.Contains("PRIVATE"), "cleanup outcome lost or private error exposed");
        });
    }
}
