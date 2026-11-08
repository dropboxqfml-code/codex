using System;

namespace ATIVBatteryGuard.FixedReadTrial
{
    internal enum FixedReadPreflightSubstep
    {
        None, BudgetCheck, QueryCreate, QueryGet, EnumeratorCreate, MoveNext, Current,
        ActivePropertyRead, ActiveTypeRead, ActiveArrayRead, ActiveValueRead,
        InstancePathRead, PathKindRead, PathClassRead, RelativePathObjectRead, RelativePathRead,
        RowDispose, EnumeratorDispose, CollectionDispose, SearcherDispose
    }

    internal enum FixedReadPreflightError
    {
        None, WmiAccessDenied, WindowsAccessDenied, WmiClassNotFound,
        WmiNamespaceNotFound, WmiNotFound, WmiTimedOut, WindowsTimedOut,
        ManagedAccessDenied, ManagedSecurityDenied, ManagedTimedOut, Other
    }

    internal static class FixedReadPreflightErrors
    {
        internal static FixedReadPreflightError Classify(Exception exception, int? nativeCode = null)
        {
            if (exception == null) return FixedReadPreflightError.Other;
            switch (unchecked((uint)(nativeCode ?? exception.HResult)))
            {
                case 0x80041003: return FixedReadPreflightError.WmiAccessDenied;
                case 0x80070005: return FixedReadPreflightError.WindowsAccessDenied;
                case 0x80041010: return FixedReadPreflightError.WmiClassNotFound;
                case 0x8004100E: return FixedReadPreflightError.WmiNamespaceNotFound;
                case 0x80041002: return FixedReadPreflightError.WmiNotFound;
                // Target net48 ManagementStatus.Timedout is a distinct
                // success-status constant, not WBEM_E_TIMED_OUT below.
                case 0x00040004: return FixedReadPreflightError.WmiTimedOut;
                case 0x80043001: return FixedReadPreflightError.WmiTimedOut;
                case 0x800705B4: return FixedReadPreflightError.WindowsTimedOut;
            }
            if (exception is UnauthorizedAccessException) return FixedReadPreflightError.ManagedAccessDenied;
            if (exception is System.Security.SecurityException) return FixedReadPreflightError.ManagedSecurityDenied;
            if (exception is TimeoutException) return FixedReadPreflightError.ManagedTimedOut;
            return FixedReadPreflightError.Other;
        }
    }

    // No SDK references, raw values or exception objects are retained. This
    // tracker records the first failure while allowing every cleanup to run.
    internal sealed class FixedReadPreflightTracker
    {
        private readonly Func<Exception, FixedReadPreflightError> classify;
        private FixedReadPreflightSubstep latestStep, failureStep;
        private FixedReadPreflightError error;
        private bool hasFailure, cleanupFailed;

        internal FixedReadPreflightSubstep Substep => hasFailure ? failureStep : latestStep;
        internal FixedReadPreflightError Error => error;
        internal bool HasFailure => hasFailure;
        internal bool CleanupFailed => cleanupFailed;

        internal FixedReadPreflightTracker(Func<Exception, FixedReadPreflightError> classify)
        {
            this.classify = classify ?? throw new ArgumentNullException(nameof(classify));
        }

        internal T Run<T>(FixedReadPreflightSubstep step, Func<T> operation)
        {
            if (operation == null) throw new ArgumentNullException(nameof(operation));
            latestStep = step;
            try { return operation(); }
            catch (Exception exception)
            {
                RecordFailure(step, exception);
                throw;
            }
        }

        internal void Run(FixedReadPreflightSubstep step, Action operation)
        {
            if (operation == null) throw new ArgumentNullException(nameof(operation));
            Run(step, () => { operation(); return true; });
        }

        // An Action preserves concrete SDK Dispose dispatch. Converting a WMI
        // wrapper to IDisposable can select Component's different cleanup map.
        internal void DisposeTracked(FixedReadPreflightSubstep step, Action dispose)
        {
            if (dispose == null) return;
            try { dispose(); }
            catch (Exception exception)
            {
                cleanupFailed = true;
                RecordFailure(step, exception);
            }
        }

        private void RecordFailure(FixedReadPreflightSubstep step, Exception exception)
        {
            if (hasFailure) return;
            hasFailure = true;
            failureStep = step;
            try { error = classify(exception); }
            catch { error = FixedReadPreflightError.Other; }
            if (error == FixedReadPreflightError.None || !Enum.IsDefined(typeof(FixedReadPreflightError), error))
                error = FixedReadPreflightError.Other;
        }
    }
}
