using System;
using System.IO;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.ProtectionTransitionTrial;

internal static partial class Program
{
    private static void RegisterProtectionTransitionHostTests()
    {
        AddAsync("protection host preparation notice and failed notice do not replace actual completion", async () =>
        {
            foreach (bool failedReport in new[] { false, true })
            {
                var operation = CooperativeCompletion(); var notice = CooperativeCompletion(); var noticed = CooperativeCompletion();
                var run = ProtectionTrialLifetime.AwaitWithNoticeAsync(operation.Task, notice.Task, () =>
                {
                    noticed.TrySetResult(true);
                    if (failedReport) throw new IOException("Unreported notice failure.");
                });
                notice.TrySetResult(true); await CooperativeAwait(noticed.Task);
                Check(!run.IsCompleted, "display notice manufactured preparation completion");
                operation.TrySetResult(true); Check(await run, "actual preparation result changed");
            }
        });

        AddAsync("protection host always joins related close after run or reporting failure", async () =>
        {
            var run = CooperativeCompletion();
            var close = new TaskCompletionSource<WsabiWmiProtectionCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
            var closeEntered = CooperativeCompletion(); int closeCalls = 0;
            var joined = ProtectionTrialLifetime.RunAndJoinAsync(() => run.Task,
                () => { closeCalls++; closeEntered.TrySetResult(true); return close.Task; },
                () => { throw new IOException("Unreported report failure."); });
            run.TrySetException(new InvalidOperationException("Unreported run failure."));
            await CooperativeAwait(closeEntered.Task);
            Check(!joined.IsCompleted && closeCalls == 1, "run/report error bypassed actual close");
            close.TrySetResult(WsabiWmiProtectionCleanupStatus.Complete);
            var result = await joined;
            Check(result.RunFailed && result.CleanupComplete && closeCalls == 1, "host lost run failure or replayed cleanup");
        });

        AddAsync("protection host failed unknown cancelled and faulted cleanup cannot become complete", async () =>
        {
            foreach (var status in new[] { WsabiWmiProtectionCleanupStatus.Failed, WsabiWmiProtectionCleanupStatus.Unknown })
            {
                var result = await ProtectionTrialLifetime.RunAndJoinAsync(() => Task.CompletedTask,
                    () => Task.FromResult(status), () => { });
                Check(!result.CleanupComplete, "noncomplete cleanup was promoted");
            }
            foreach (Task<WsabiWmiProtectionCleanupStatus> close in new[] {
                Task.FromException<WsabiWmiProtectionCleanupStatus>(new IOException("Unreported close failure.")),
                Task.FromCanceled<WsabiWmiProtectionCleanupStatus>(new System.Threading.CancellationToken(true)) })
            {
                var result = await ProtectionTrialLifetime.RunAndJoinAsync(() => Task.CompletedTask, () => close, () => { });
                Check(!result.CleanupComplete, "fault or cancelled cleanup was promoted");
            }
        });

        Add("protection journal retains console output but does not retry a failed TXT writer", () =>
        {
            var writer = new ProtectionFailingWriter(); int displayed = 0;
            using (var journal = new ProtectionTrialJournal(writer, line => displayed++))
            {
                journal.Write("ReceiptOnly"); journal.Write("Pending");
                Check(journal.WriteFailed && writer.Attempts == 1 && displayed == 2, "TXT failure was hidden, retried, or suppressed display");
            }
            var stored = new StringWriter();
            using (var journal = new ProtectionTrialJournal(stored, line => { throw new IOException("Unreported console failure."); }))
            {
                journal.Write("Complete"); Check(!journal.WriteFailed, "console failure discarded local TXT");
                Equal("Complete" + Environment.NewLine, stored.ToString());
            }
        });

        Add("protection journal creates only its new purpose TXT without existing experiment names", () => WithDirectory(directory =>
        {
            using (var journal = ProtectionTrialJournal.TryCreate(directory))
            {
                Check(journal != null, "new purpose TXT creation failed"); journal.Write("ReceiptOnly");
                Check(!journal.WriteFailed, "new purpose TXT write failed");
            }
            var paths = Directory.GetFiles(directory); Equal(1, paths.Length);
            Check(Path.GetFileName(paths[0]).StartsWith("protection-0to1-result-", StringComparison.Ordinal), "wrong purpose TXT name");
            Equal("ReceiptOnly" + Environment.NewLine, File.ReadAllText(paths[0]));
        }));

        Add("protection report counts received byte candidates separately from accepted transition stages", () =>
        {
            var preOne = new WsabiWmiProtectionTransitionReview();
            preOne.Observe(new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.PreMode,
                WsabiWmiProtectionTransitionEvidence.BoundReadCandidate, 1));
            Equal(1, ProtectionTrialReport.CandidateCount(preOne.Snapshot)); Equal(0, preOne.Snapshot.BoundReadCandidateCount);
            var model = ProtectionHostReviewThroughReceipt();
            model.Observe(new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.PostMode,
                WsabiWmiProtectionTransitionEvidence.BoundReadCandidate, 1));
            model.Observe(new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.PostUpper,
                WsabiWmiProtectionTransitionEvidence.BoundReadCandidate, 79));
            Equal(5, ProtectionTrialReport.CandidateCount(model.Snapshot)); Equal(4, model.Snapshot.BoundReadCandidateCount);
            Check(model.Snapshot.SetterReceiptAccepted && !model.Snapshot.SetterAcknowledged,
                "receipt was changed into setter execution proof");
            var writer = new StringWriter();
            using (var journal = new ProtectionTrialJournal(writer, line => { })) ProtectionTrialReport.WriteSnapshot(journal, model.Snapshot);
            string text = writer.ToString();
            Check(text.Contains("수용 저장 byte 후보 수: 5") && text.Contains("전이 모델 수용 읽기 단계 수: 4") &&
                text.Contains("사후 모드/상한/하한 후보: 1 / 79 / 미관측") && text.Contains("저장 후보 일치: No"),
                "candidate report lost mismatch evidence or promoted it to success");
        });

        Add("protection matched numeric report still disclaims whole procedure and charging proof", () =>
        {
            var model = ProtectionHostReviewThroughReceipt();
            foreach (var observation in new[] {
                new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.PostMode, WsabiWmiProtectionTransitionEvidence.BoundReadCandidate, 1),
                new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.PostUpper, WsabiWmiProtectionTransitionEvidence.BoundReadCandidate, 80),
                new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.PostLower, WsabiWmiProtectionTransitionEvidence.BoundReadCandidate, 75) })
                model.Observe(observation);
            Equal(6, ProtectionTrialReport.CandidateCount(model.Snapshot));
            var writer = new StringWriter();
            using (var journal = new ProtectionTrialJournal(writer, line => { })) ProtectionTrialReport.WriteSnapshot(journal, model.Snapshot);
            string text = writer.ToString();
            Check(text.Contains("저장 후보 일치: Yes") && text.Contains("전체 절차의 성공·충전기 적용·전기적 충전 제한의 증거가 아닙니다") &&
                text.Contains("독립 setter 성공 ACK로 판정하지 않습니다"), "matched candidates became live charging success");
            var binding = new WsabiWmiProtectionStageBinding(WsabiWmiProtectionTransitionStage.PreUpper,
                new object(), new object(), new object(), new object(), new object(), new object());
            var stage = new WsabiWmiProtectionBoundStage(binding, 173, 91, new byte[] { 1, 2, 3, 4, 5, 6, 7, 8 },
                stop => Task.FromResult<WsabiWmiProtectionBoundReply>(null), Task.CompletedTask,
                Task.FromResult(WsabiWmiBoundStageCleanupStatus.Complete), Task.FromResult(WsabiWmiBoundStageCleanupStatus.Complete));
            var diagnosticWriter = new StringWriter();
            using (var journal = new ProtectionTrialJournal(diagnosticWriter, line => { }))
                ProtectionTrialReport.WriteDiagnostics(journal, new[] { new WsabiWmiProtectionStageDiagnostic(stage) });
            Equal("PreUpper / binding=NotReviewed / read=NotReviewed / setter=NotReviewed" + Environment.NewLine,
                diagnosticWriter.ToString());
        });
    }

    private static WsabiWmiProtectionTransitionReview ProtectionHostReviewThroughReceipt()
    {
        var model = new WsabiWmiProtectionTransitionReview();
        model.Observe(new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.PreMode, WsabiWmiProtectionTransitionEvidence.BoundReadCandidate, 0));
        model.Observe(new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.PreUpper, WsabiWmiProtectionTransitionEvidence.BoundReadCandidate, 44));
        model.Observe(new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.PreLower, WsabiWmiProtectionTransitionEvidence.BoundReadCandidate, 33));
        model.Observe(new WsabiWmiProtectionTransitionObservation(WsabiWmiProtectionTransitionStage.SemanticSet1,
            WsabiWmiProtectionTransitionEvidence.SetterReceiptAcceptedForReadback));
        return model;
    }

    private sealed class ProtectionFailingWriter : StringWriter
    {
        internal int Attempts;
        public override void WriteLine(string line) { Attempts++; throw new IOException("Unreported TXT failure."); }
    }
}
