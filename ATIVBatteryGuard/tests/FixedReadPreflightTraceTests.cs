using System;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security;
using ATIVBatteryGuard.FixedReadTrial;

internal static partial class Program
{
    private static void RegisterFixedReadPreflightTraceTests()
    {
        Add("fixed read preflight preserves target net48 ManagementStatus Timedout classification", () =>
        {
            // Inert metadata of the target net48 reference enum is 0x00040004;
            // this is different from the separately allowlisted error code.
            Equal(FixedReadPreflightError.WmiTimedOut,
                FixedReadPreflightErrors.Classify(new InvalidOperationException("PRIVATE-SDK-TIMEOUT"), 0x00040004));
        });
        Add("fixed read preflight classifies only allowlisted native and managed error categories", () =>
        {
            var cases = new[]
            {
                Tuple.Create(0x80041003u, FixedReadPreflightError.WmiAccessDenied),
                Tuple.Create(0x80070005u, FixedReadPreflightError.WindowsAccessDenied),
                Tuple.Create(0x80041010u, FixedReadPreflightError.WmiClassNotFound),
                Tuple.Create(0x8004100Eu, FixedReadPreflightError.WmiNamespaceNotFound),
                Tuple.Create(0x80041002u, FixedReadPreflightError.WmiNotFound),
                Tuple.Create(0x80043001u, FixedReadPreflightError.WmiTimedOut),
                Tuple.Create(0x800705B4u, FixedReadPreflightError.WindowsTimedOut)
            };
            foreach (var item in cases)
            {
                Equal(item.Item2, FixedReadPreflightErrors.Classify(
                    new COMException("PRIVATE-NATIVE", unchecked((int)item.Item1))));
                Equal(item.Item2, FixedReadPreflightErrors.Classify(
                    new InvalidOperationException("PRIVATE-WMI"), unchecked((int)item.Item1)));
            }
            Equal(FixedReadPreflightError.WindowsAccessDenied,
                FixedReadPreflightErrors.Classify(new UnauthorizedAccessException("PRIVATE-ACCOUNT")));
            Equal(FixedReadPreflightError.ManagedAccessDenied,
                FixedReadPreflightErrors.Classify(new UnauthorizedAccessException("PRIVATE-ACCOUNT"), 1));
            Equal(FixedReadPreflightError.ManagedSecurityDenied,
                FixedReadPreflightErrors.Classify(new SecurityException("PRIVATE-SECURITY")));
            Equal(FixedReadPreflightError.ManagedTimedOut,
                FixedReadPreflightErrors.Classify(new TimeoutException("PRIVATE-TIMEOUT")));
            Equal(FixedReadPreflightError.Other,
                FixedReadPreflightErrors.Classify(new COMException("PRIVATE-UNKNOWN", unchecked((int)0x81234567))));
            Equal(FixedReadPreflightError.Other, FixedReadPreflightErrors.Classify(null));
        });

        Add("fixed read preflight captures the exact failing substep and rethrows the original exception", () =>
        {
            foreach (FixedReadPreflightSubstep step in Enum.GetValues(typeof(FixedReadPreflightSubstep)))
            {
                if (step == FixedReadPreflightSubstep.None || (int)step >= (int)FixedReadPreflightSubstep.RowDispose) continue;
                var trace = new FixedReadPreflightTracker(exception => FixedReadPreflightErrors.Classify(exception));
                var original = new COMException("PRIVATE-INSTANCE", unchecked((int)0x80041003));
                Exception observed = null;
                try { trace.Run(step, (Action)(() => { throw original; })); }
                catch (Exception exception) { observed = exception; }
                Check(ReferenceEquals(original, observed), "tracker replaced the original failure");
                Equal(step, trace.Substep);
                Equal(FixedReadPreflightError.WmiAccessDenied, trace.Error);
                Check(trace.HasFailure && !trace.CleanupFailed, "operation failure was confused with cleanup");
            }
        });

        Add("fixed read preflight preserves successful false values and does not attribute success to cleanup", () =>
        {
            var trace = new FixedReadPreflightTracker(exception => FixedReadPreflightErrors.Classify(exception));
            int reads = 0, cleanups = 0;
            Check(!trace.Run(FixedReadPreflightSubstep.MoveNext, () => { reads++; return false; }), "empty result changed");
            trace.DisposeTracked(FixedReadPreflightSubstep.EnumeratorDispose, () => cleanups++);
            trace.DisposeTracked(FixedReadPreflightSubstep.CollectionDispose, () => cleanups++);
            trace.DisposeTracked(FixedReadPreflightSubstep.SearcherDispose, () => cleanups++);
            Equal(1, reads); Equal(3, cleanups);
            Equal(FixedReadPreflightSubstep.MoveNext, trace.Substep);
            Equal(FixedReadPreflightError.None, trace.Error);
            Check(!trace.HasFailure && !trace.CleanupFailed, "successful empty result manufactured an error");
        });

        Add("fixed read preflight later cleanup failures cannot replace the primary operation failure", () =>
        {
            var trace = new FixedReadPreflightTracker(exception => FixedReadPreflightErrors.Classify(exception));
            var original = new TimeoutException("PRIVATE-FIRST");
            Exception observed = null;
            int cleanups = 0;
            try
            {
                try { trace.Run(FixedReadPreflightSubstep.QueryGet, (Action)(() => { throw original; })); }
                finally
                {
                    trace.DisposeTracked(FixedReadPreflightSubstep.EnumeratorDispose,
                        () => { cleanups++; throw new UnauthorizedAccessException("PRIVATE-CLEANUP-1"); });
                    trace.DisposeTracked(FixedReadPreflightSubstep.CollectionDispose,
                        () => { cleanups++; throw new InvalidOperationException("PRIVATE-CLEANUP-2"); });
                    trace.DisposeTracked(FixedReadPreflightSubstep.SearcherDispose, () => cleanups++);
                }
            }
            catch (Exception exception) { observed = exception; }
            Check(ReferenceEquals(original, observed), "cleanup masked the primary exception");
            Equal(3, cleanups);
            Equal(FixedReadPreflightSubstep.QueryGet, trace.Substep);
            Equal(FixedReadPreflightError.ManagedTimedOut, trace.Error);
            Check(trace.HasFailure && trace.CleanupFailed, "cleanup failure was omitted");
        });

        Add("fixed read preflight cleanup only failure remains first while later resources are all cleaned", () =>
        {
            var trace = new FixedReadPreflightTracker(exception => FixedReadPreflightErrors.Classify(exception));
            int cleanups = 0;
            trace.Run(FixedReadPreflightSubstep.RelativePathRead, () => true);
            trace.DisposeTracked(FixedReadPreflightSubstep.RowDispose,
                () => { cleanups++; throw new COMException("PRIVATE-ROW", unchecked((int)0x80070005)); });
            trace.DisposeTracked(FixedReadPreflightSubstep.EnumeratorDispose,
                () => { cleanups++; throw new TimeoutException("PRIVATE-LATER"); });
            trace.DisposeTracked(FixedReadPreflightSubstep.CollectionDispose, () => cleanups++);
            trace.DisposeTracked(FixedReadPreflightSubstep.SearcherDispose, () => cleanups++);
            Equal(4, cleanups);
            Equal(FixedReadPreflightSubstep.RowDispose, trace.Substep);
            Equal(FixedReadPreflightError.WindowsAccessDenied, trace.Error);
            Check(trace.HasFailure && trace.CleanupFailed, "cleanup only failure became a successful read");
        });

        Add("fixed read preflight a broken classifier cannot hide the actual operation or cleanup failure", () =>
        {
            foreach (Func<Exception, FixedReadPreflightError> classify in new Func<Exception, FixedReadPreflightError>[]
            {
                exception => { throw new InvalidOperationException("PRIVATE-CLASSIFIER"); },
                exception => FixedReadPreflightError.None,
                exception => (FixedReadPreflightError)999
            })
            {
                var trace = new FixedReadPreflightTracker(classify);
                var original = new InvalidOperationException("PRIVATE-PRIMARY");
                Exception observed = null;
                try { trace.Run(FixedReadPreflightSubstep.Current, (Action)(() => { throw original; })); }
                catch (Exception exception) { observed = exception; }
                Check(ReferenceEquals(original, observed), "classifier changed the original failure");
                Equal(FixedReadPreflightError.Other, trace.Error);
                trace.DisposeTracked(FixedReadPreflightSubstep.RowDispose,
                    () => { throw new TimeoutException("PRIVATE-CLEANUP"); });
                Equal(FixedReadPreflightSubstep.Current, trace.Substep);
                Check(trace.CleanupFailed, "classifier failure lost the cleanup fact");
            }
        });

        Add("fixed read preflight cleanup action preserves concrete disposal rather than interface mapping", () =>
        {
            var trace = new FixedReadPreflightTracker(exception => FixedReadPreflightErrors.Classify(exception));
            var resource = new FixedReadTraceConcreteCleanup();
            trace.DisposeTracked(FixedReadPreflightSubstep.RowDispose, () => resource.Dispose());
            Equal(1, resource.ConcreteCalls); Equal(0, resource.InterfaceCalls);
            Check(!trace.CleanupFailed, "concrete disposal was classified as failed");
        });

        Add("fixed read preflight tracker retains only fixed categories rather than raw error or SDK values", () =>
        {
            var trace = new FixedReadPreflightTracker(exception => FixedReadPreflightErrors.Classify(exception));
            try
            {
                trace.Run(FixedReadPreflightSubstep.ActiveValueRead, (Action)(() =>
                { throw new UnauthorizedAccessException(@"C:\Users\PrivateName\Instance-UUID"); }));
            }
            catch (UnauthorizedAccessException) { }
            foreach (var field in typeof(FixedReadPreflightTracker).GetFields(BindingFlags.Instance | BindingFlags.NonPublic))
            {
                Check(field.FieldType.IsEnum || field.FieldType == typeof(bool) ||
                    field.FieldType == typeof(Func<Exception, FixedReadPreflightError>), "tracker retains raw error or SDK data");
                Check(!(field.GetValue(trace) is Exception), "tracker retains an exception object");
            }
            string output = trace.Substep + " / " + trace.Error + " / " + trace.CleanupFailed;
            Check(!output.Contains("PrivateName") && !output.Contains("Instance-UUID") && !output.Contains(@"C:\Users"),
                "private data escaped fixed categories");
            Check(!typeof(FixedReadPreflightTracker).GetFields(BindingFlags.Instance | BindingFlags.NonPublic)
                .Any(field => field.FieldType.FullName.StartsWith("System.Management.", StringComparison.Ordinal)),
                "pure tracker retains an actual SDK object");
        });
    }

    private class FixedReadTraceInterfaceCleanup : IDisposable
    {
        internal int InterfaceCalls;
        public void Dispose() { InterfaceCalls++; }
    }

    private sealed class FixedReadTraceConcreteCleanup : FixedReadTraceInterfaceCleanup
    {
        internal int ConcreteCalls;
        public new void Dispose() { ConcreteCalls++; }
    }
}
