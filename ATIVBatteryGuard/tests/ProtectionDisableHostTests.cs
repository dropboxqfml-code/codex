using System;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using ATIVBatteryGuard.Core.Services;
using ATIVBatteryGuard.ProtectionDisableTrial;

internal static partial class Program
{
    private static void RegisterProtectionDisableHostTests()
    {
        AddAsync("disable host notice and notice failure never replace actual preparation completion", async () =>
        {
            foreach (bool reportFails in new[] { false, true })
            {
                var operation = CooperativeCompletion(); var notice = CooperativeCompletion(); var noticed = CooperativeCompletion();
                var run = DisableTrialLifetime.AwaitWithNoticeAsync(operation.Task, notice.Task, () =>
                {
                    noticed.TrySetResult(true);
                    if (reportFails) throw new IOException("Unreported disable notice failure.");
                });
                notice.TrySetResult(true); await CooperativeAwait(noticed.Task);
                Check(!run.IsCompleted, "disable display notice manufactured preparation completion");
                operation.TrySetResult(true); Check(await run, "actual disable preparation result changed");
            }
        });

        AddAsync("disable host always joins actual cleanup after run and report failure", async () =>
        {
            var run = CooperativeCompletion();
            var close = new TaskCompletionSource<WsabiWmiProtectionCleanupStatus>(TaskCreationOptions.RunContinuationsAsynchronously);
            var closeEntered = CooperativeCompletion(); int closeCalls = 0;
            var joined = DisableTrialLifetime.RunAndJoinAsync(() => run.Task,
                () => { closeCalls++; closeEntered.TrySetResult(true); return close.Task; },
                () => { throw new IOException("Unreported disable report failure."); });
            run.TrySetException(new InvalidOperationException("Unreported disable run failure."));
            await CooperativeAwait(closeEntered.Task);
            Check(!joined.IsCompleted && closeCalls == 1, "disable host bypassed or replayed related cleanup");
            close.TrySetResult(WsabiWmiProtectionCleanupStatus.Complete);
            var result = await joined;
            Check(result.RunFailed && result.CleanupComplete && closeCalls == 1, "disable host lost run failure or actual cleanup");
        });

        AddAsync("disable host failed unknown faulted cancelled and null cleanup are never complete", async () =>
        {
            foreach (var status in new[] { WsabiWmiProtectionCleanupStatus.Failed, WsabiWmiProtectionCleanupStatus.Unknown })
            {
                var result = await DisableTrialLifetime.RunAndJoinAsync(() => Task.CompletedTask,
                    () => Task.FromResult(status), () => { });
                Check(!result.CleanupComplete, "disable host promoted noncomplete cleanup");
            }
            foreach (Task<WsabiWmiProtectionCleanupStatus> close in new[] {
                Task.FromException<WsabiWmiProtectionCleanupStatus>(new IOException("Unreported disable cleanup failure.")),
                Task.FromCanceled<WsabiWmiProtectionCleanupStatus>(new System.Threading.CancellationToken(true)), null })
            {
                var result = await DisableTrialLifetime.RunAndJoinAsync(() => Task.CompletedTask, () => close, () => { });
                Check(!result.CleanupComplete, "disable host promoted failed or unavailable cleanup");
            }
        });

        Add("disable journal preserves display and never retries a failed writer", () =>
        {
            var writer = new DisableFailingWriter(); int displayed = 0;
            using (var journal = new DisableTrialJournal(writer, line => displayed++))
            {
                journal.Write("ReceiptOnly"); journal.Write("Pending");
                Check(journal.WriteFailed && writer.Attempts == 1 && displayed == 2, "disable journal retried or hid failed TXT");
            }
            var stored = new StringWriter();
            using (var journal = new DisableTrialJournal(stored, line => { throw new IOException("Unreported console failure."); }))
            {
                journal.Write("Complete"); Equal("Complete" + Environment.NewLine, stored.ToString());
                Check(!journal.WriteFailed, "console failure discarded disable TXT");
            }
        });

        Add("disable journal creates only its new result prefix and preserves prior TXT bytes", () => WithDirectory(directory =>
        {
            string prior = Path.Combine(directory, "protection-0to1-result-old.txt");
            File.WriteAllText(prior, "preserve historical ON record");
            using (var journal = DisableTrialJournal.TryCreate(directory))
            {
                Check(journal != null, "disable TXT creation failed"); journal.Write("ReceiptOnly");
                Check(!journal.WriteFailed, "disable TXT write failed");
            }
            var paths = Directory.GetFiles(directory, "protection-1to0-result-*.txt"); Equal(1, paths.Length);
            Equal("ReceiptOnly" + Environment.NewLine, File.ReadAllText(paths[0]));
            Equal("preserve historical ON record", File.ReadAllText(prior)); Equal(2, Directory.GetFiles(directory).Length);
        }));

        Add("disable prezero report preserves already disabled candidate without a new setting claim", () =>
        {
            var model = new WsabiWmiProtectionDisableReview();
            model.Observe(new WsabiWmiProtectionDisableObservation(WsabiWmiProtectionDisableStage.PreMode,
                WsabiWmiProtectionDisableEvidence.BoundReadCandidate, 0));
            Equal(1, DisableTrialReport.CandidateCount(model.Snapshot));
            Check(!model.Snapshot.SetterReceiptAccepted && !model.Snapshot.IsStoredReadbackMatchedCandidate,
                "prezero became a new disable transition");
            var writer = new StringWriter();
            using (var journal = new DisableTrialJournal(writer, line => { })) DisableTrialReport.WriteSnapshot(journal, model.Snapshot);
            string text = writer.ToString();
            Check(text.Contains("사전 모드 후보: 0") && text.Contains("이미 해제된 후보") && text.Contains("설정0 요청은 없습니다") &&
                text.Contains("모드1→0 저장 후보 일치: No") && text.Contains("사후 모드 후보: 미관측"),
                "prezero report claimed setting or dropped the candidate");
        });

        Add("disable mismatch report preserves post one and keeps receipt distinct from acknowledgement", () =>
        {
            var model = DisableHostReviewThroughReceipt();
            model.Observe(new WsabiWmiProtectionDisableObservation(WsabiWmiProtectionDisableStage.PostMode,
                WsabiWmiProtectionDisableEvidence.BoundReadCandidate, 1));
            Equal(2, DisableTrialReport.CandidateCount(model.Snapshot));
            Check(model.Snapshot.SetterReceiptAccepted && !model.Snapshot.SetterAcknowledged, "disable receipt became execution ACK");
            var writer = new StringWriter();
            using (var journal = new DisableTrialJournal(writer, line => { })) DisableTrialReport.WriteSnapshot(journal, model.Snapshot);
            Check(writer.ToString().Contains("사후 모드 후보: 1") && writer.ToString().Contains("모드1→0 저장 후보 일치: No"),
                "disable mismatch was replaced by expected zero");
        });

        Add("disable matched report disclaims charger effect threshold restore and full charging guarantee", () =>
        {
            var model = DisableHostReviewThroughReceipt();
            model.Observe(new WsabiWmiProtectionDisableObservation(WsabiWmiProtectionDisableStage.PostMode,
                WsabiWmiProtectionDisableEvidence.BoundReadCandidate, 0));
            var writer = new StringWriter();
            using (var journal = new DisableTrialJournal(writer, line => { })) DisableTrialReport.WriteSnapshot(journal, model.Snapshot);
            string text = writer.ToString();
            Check(text.Contains("모드1→0 저장 후보 일치: Yes") && text.Contains("독립 setter 성공 ACK로 판정하지 않습니다") &&
                text.Contains("임계값은 조회·변경하지 않았으며 이전값 복원·100% 충전을 확인한 것이 아닙니다") &&
                text.Contains("전기적 충전 재개의 증거가 아닙니다"), "matched disable report exceeded observed scope");
        });

        Add("disable user instructions require ON AC observation first and success gated AFTER observation", () =>
        {
            var steps = new List<string>(); DisableTrialReport.WriteUserSteps(steps.Add);
            Equal(5, steps.Count);
            Check(steps[0].Contains("충전기를 연결") && steps[1].Contains("저장을 한 번") &&
                steps[2].Contains("START를 한 번") && steps[3].Contains("사전1→사후0") && steps[3].Contains("Complete") &&
                steps[4].Contains("기존 진단·삼성 DLL·EXE는 다시 제출하지 않습니다"), "mandatory disable instructions missing or reordered");
            foreach (bool matched in new[] { false, true })
            {
                var text = new StringWriter();
                using (var journal = new DisableTrialJournal(text, line => { })) DisableTrialReport.WriteAfterCloseSteps(journal, matched);
                Check(matched ? text.ToString().Contains("같은 충전기 연결 상태에서 새 관찰 시작")
                    : text.ToString().Contains("이 TXT를 먼저 전달") && !text.ToString().Contains("새 관찰 시작"),
                    "failed transition prompted an AFTER trial as though it succeeded");
            }
        });
    }

    private static WsabiWmiProtectionDisableReview DisableHostReviewThroughReceipt()
    {
        var model = new WsabiWmiProtectionDisableReview();
        model.Observe(new WsabiWmiProtectionDisableObservation(WsabiWmiProtectionDisableStage.PreMode,
            WsabiWmiProtectionDisableEvidence.BoundReadCandidate, 1));
        model.Observe(new WsabiWmiProtectionDisableObservation(WsabiWmiProtectionDisableStage.SemanticSet0,
            WsabiWmiProtectionDisableEvidence.SetterReceiptAcceptedForReadback));
        return model;
    }

    private sealed class DisableFailingWriter : StringWriter
    {
        internal int Attempts;
        public override void WriteLine(string line) { Attempts++; throw new IOException("Unreported disable TXT failure."); }
    }
}
