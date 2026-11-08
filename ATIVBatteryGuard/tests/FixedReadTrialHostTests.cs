using System;
using System.IO;
using System.Threading.Tasks;
using ATIVBatteryGuard.FixedReadTrial;
using ATIVBatteryGuard.WmiInterop;

internal static partial class Program
{
    private static void RegisterFixedReadTrialHostTests()
    {
        AddAsync("fixed read host preparation notice does not end the pending operation", async () =>
        {
            var operation = CooperativeCompletion(); var notice = CooperativeCompletion(); var noticed = CooperativeCompletion(); int notices = 0;
            var waiting = FixedReadTrialLifetime.AwaitWithNoticeAsync(operation.Task, notice.Task,
                () => { notices++; noticed.TrySetResult(true); });
            notice.TrySetResult(true);
            await CooperativeAwait(noticed.Task);
            Equal(1, notices); Check(!waiting.IsCompleted, "display deadline released pending preparation");
            operation.TrySetResult(true);
            Check(await waiting, "preparation result replaced by display deadline");
        });
        AddAsync("fixed read host notice writer failure still joins preparation", async () =>
        {
            var operation = CooperativeCompletion();
            var waiting = FixedReadTrialLifetime.AwaitWithNoticeAsync(operation.Task, Task.CompletedTask,
                () => { throw new IOException("PRIVATE-PREPARE-REPORT"); });
            Check(!waiting.IsCompleted, "failed pending report released preparation");
            operation.TrySetResult(true); Check(await waiting, "report failure replaced actual preparation");
        });
        AddAsync("fixed read host awaits run and the same related close", async () =>
        {
            var run = CooperativeCompletion();
            var close = new TaskCompletionSource<WsabiWmiWindowsCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
            var closeEntered = CooperativeCompletion();
            int runCalls = 0, closeCalls = 0;
            var joined = FixedReadTrialLifetime.RunAndJoinAsync(() => { runCalls++; return run.Task; },
                () => { closeCalls++; closeEntered.TrySetResult(true); return close.Task; }, () => { });
            Check(!joined.IsCompleted, "pending run was ended by host"); Equal(1, runCalls); Equal(0, closeCalls);
            run.TrySetResult(true);
            await CooperativeAwait(closeEntered.Task);
            Check(!joined.IsCompleted, "host left before related close"); Equal(1, closeCalls);
            close.TrySetResult(WsabiWmiWindowsCleanupStatus.Complete);
            var result = await joined; Check(result.CleanupComplete && !result.RunFailed, "host changed completed status");
            Equal(1, runCalls); Equal(1, closeCalls);
        });
        AddAsync("fixed read host invocation and report failures cannot skip close", async () =>
        {
            var close = new TaskCompletionSource<WsabiWmiWindowsCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
            int calls = 0;
            var joined = FixedReadTrialLifetime.RunAndJoinAsync(
                () => Task.FromException(new InvalidOperationException("PRIVATE-RUN")),
                () => { calls++; return close.Task; }, () => { throw new IOException("PRIVATE-REPORT"); });
            Check(!joined.IsCompleted, "run/report exception skipped actual close"); Equal(1, calls);
            close.TrySetResult(WsabiWmiWindowsCleanupStatus.Complete);
            var result = await joined; Check(result.RunFailed && result.CleanupComplete, "failure or close classification lost");
        });
        AddAsync("fixed read host failed cleanup is never complete", async () =>
        {
            var result = await FixedReadTrialLifetime.RunAndJoinAsync(() => Task.CompletedTask,
                () => Task.FromResult(WsabiWmiWindowsCleanupStatus.Failed), () => { });
            Check(!result.CleanupComplete, "failed cleanup promoted to complete");
            result = await FixedReadTrialLifetime.RunAndJoinAsync(() => Task.CompletedTask,
                () => Task.FromException<WsabiWmiWindowsCleanupStatus>(new IOException("PRIVATE-CLOSE")), () => { });
            Check(!result.CleanupComplete, "faulted cleanup promoted to complete");
        });
        Add("fixed read journal report failure does not throw or retry the writer", () =>
        {
            var writer = new FixedReadFailingWriter(); int shown = 0;
            using (var log = new FixedReadTrialJournal(writer, text => shown++))
            {
                log.Write("FixedStatus"); log.Write("Complete");
                Check(log.WriteFailed, "TXT write failure concealed"); Equal(1, writer.Attempts); Equal(2, shown);
            }
        });
        Add("fixed read journal console failure does not discard the TXT result", () =>
        {
            var writer = new StringWriter();
            using (var log = new FixedReadTrialJournal(writer, text => { throw new IOException("PRIVATE-CONSOLE"); }))
            {
                log.Write("StoredModeCandidate: 1"); Check(!log.WriteFailed, "console failure discarded TXT");
                Equal("StoredModeCandidate: 1" + Environment.NewLine, writer.ToString());
            }
        });
        Add("fixed read journal creates only a new local TXT", () => WithDirectory(directory =>
        {
            using (var log = FixedReadTrialJournal.TryCreate(directory))
            {
                Check(log != null, "new TXT unavailable"); log.Write("FixedStatus"); Check(!log.WriteFailed, "new TXT failed");
            }
            var files = Directory.GetFiles(directory, "fixed-read-a-access1-result-*.txt"); Equal(1, files.Length);
            Equal("FixedStatus" + Environment.NewLine, File.ReadAllText(files[0]));
        }));
    }

    private sealed class FixedReadFailingWriter : StringWriter
    {
        internal int Attempts;
        public override void WriteLine(string value) { Attempts++; throw new IOException("PRIVATE-TXT"); }
    }
}
