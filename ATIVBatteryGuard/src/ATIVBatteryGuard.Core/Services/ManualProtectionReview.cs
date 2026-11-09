using System;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    internal enum ManualProtectionEvidence { Unknown, Historical, Rejected, ReadCandidate, SetterReceipt }
    internal sealed class ManualProtectionObservation
    {
        internal ManualProtectionRole Role { get; }
        internal ManualProtectionEvidence Evidence { get; }
        internal int? ByteValue { get; }
        internal ManualProtectionObservation(ManualProtectionRole role, ManualProtectionEvidence evidence, int? value = null)
        { Role = role; Evidence = evidence; ByteValue = value; }
    }
    internal sealed class ManualProtectionSnapshot
    {
        internal ManualProtectionStatus Status { get; }
        internal bool IsTerminal { get; }
        internal int ReadCandidates { get; }
        internal bool SetterReceiptAccepted { get; }
        internal int? PreModeCandidate { get; }
        internal int? ModeCandidate { get; }
        internal int? UpperCandidate { get; }
        internal int? LowerCandidate { get; }
        internal ManualProtectionSnapshot(ManualProtectionStatus status, bool terminal, int reads, bool receipt,
            int? pre, int? mode, int? upper, int? lower)
        { Status = status; IsTerminal = terminal; ReadCandidates = reads; SetterReceiptAccepted = receipt;
          PreModeCandidate = pre; ModeCandidate = mode; UpperCandidate = upper; LowerCandidate = lower; }
    }
    internal sealed class ManualProtectionDecision
    {
        internal bool IsAccepted { get; }
        internal bool IsTerminal => Snapshot.IsTerminal;
        internal ManualProtectionSnapshot Snapshot { get; }
        internal ManualProtectionDecision(bool accepted, ManualProtectionSnapshot snapshot)
        { IsAccepted = accepted; Snapshot = snapshot; }
    }

    // Numeric evidence review only. This model contains no request generation,
    // source, reservation, clock or SDK entry and cannot grant execution rights.
    internal sealed class ManualProtectionReview
    {
        private readonly ManualProtectionOperation operation;
        private readonly System.Collections.Generic.IReadOnlyList<ManualProtectionRole> order;
        private int accepted, reads;
        private bool terminal, receipt;
        private ManualProtectionStatus status = ManualProtectionStatus.Unknown;
        private int? preMode, preUpper, preLower, postMode, postUpper, postLower;
        internal ManualProtectionReview(ManualProtectionOperation operation)
        { this.operation = operation; order = ManualProtectionAttempt.Schedule(operation); }
        internal ManualProtectionSnapshot Snapshot
        {
            get
            {
                int? mode = null, upper = null, lower = null;
                if (terminal && status == ManualProtectionStatus.StateRead)
                { mode = preMode; upper = preUpper; lower = preLower; }
                else if (terminal && status == ManualProtectionStatus.ChangedCandidate)
                { mode = postMode; upper = postUpper; lower = postLower; }
                else if (terminal && status == ManualProtectionStatus.AlreadyDesiredCandidate) mode = preMode;
                return new ManualProtectionSnapshot(status, terminal, reads, receipt, preMode, mode, upper, lower);
            }
        }
        internal ManualProtectionDecision Observe(ManualProtectionObservation observation)
        {
            if (terminal) return new ManualProtectionDecision(false, Snapshot);
            if (observation == null || accepted >= order.Count || observation.Role != order[accepted]) return Reject();
            bool setter = observation.Role == ManualProtectionRole.SemanticSet;
            if (setter)
            {
                if (operation == ManualProtectionOperation.ReadState || observation.Evidence != ManualProtectionEvidence.SetterReceipt ||
                    observation.ByteValue.HasValue) return Reject();
                receipt = true;
            }
            else
            {
                if (observation.Evidence != ManualProtectionEvidence.ReadCandidate || !observation.ByteValue.HasValue ||
                    observation.ByteValue.Value < 0 || observation.ByteValue.Value > 255) return Reject();
                int value = observation.ByteValue.Value;
                if ((observation.Role == ManualProtectionRole.PreMode || observation.Role == ManualProtectionRole.PostMode) && value > 1)
                    return Reject();
                reads++;
                switch (observation.Role)
                {
                    case ManualProtectionRole.PreMode:
                        preMode = value;
                        if ((operation == ManualProtectionOperation.Enable80 && value == 1) ||
                            (operation == ManualProtectionOperation.DisableProtection && value == 0))
                        { accepted++; terminal = true; status = ManualProtectionStatus.AlreadyDesiredCandidate; return Accept(); }
                        break;
                    case ManualProtectionRole.PreUpper: preUpper = value; break;
                    case ManualProtectionRole.PreLower: preLower = value; break;
                    case ManualProtectionRole.PostMode:
                        postMode = value;
                        if (value != (operation == ManualProtectionOperation.Enable80 ? 1 : 0)) return Reject();
                        break;
                    case ManualProtectionRole.PostUpper:
                        postUpper = value; if (value != 80) return Reject(); break;
                    case ManualProtectionRole.PostLower:
                        postLower = value; if (value != 75) return Reject(); break;
                    default: return Reject();
                }
            }
            accepted++;
            if (accepted == order.Count)
            {
                terminal = true;
                status = operation == ManualProtectionOperation.ReadState ? ManualProtectionStatus.StateRead : ManualProtectionStatus.ChangedCandidate;
            }
            return Accept();
        }
        private ManualProtectionDecision Accept() => new ManualProtectionDecision(true, Snapshot);
        private ManualProtectionDecision Reject()
        { terminal = true; status = ManualProtectionStatus.Rejected; return new ManualProtectionDecision(false, Snapshot); }
    }
}
