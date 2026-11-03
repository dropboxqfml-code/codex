using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.WmiOneShotQuery
{
    // Owns callback objects until one completion closes the capture. It never
    // reads provider fields; only a successful, single-result completion may
    // call the supplied detached-output reader. No raw object or error is a
    // final report. Disposal occurs outside the gate, including reentrant or
    // failing Dispose implementations.
    internal sealed class OneShotResultCapture<T> : IDisposable where T : class, IDisposable
    {
        private readonly object gate = new object();
        private readonly HashSet<T> disposing = new HashSet<T>(ReferenceComparer.Instance);
        private T first;
        private T processing;
        private int count;
        private bool invalid;
        private bool closed;

        internal void Accept(T value)
        {
            T discardFirst = null;
            T discardValue = null;
            lock (gate)
            {
                if (closed)
                {
                    // A late callback can return the object currently being
                    // read. Its completion retains ownership until cleanup.
                    if (!ReferenceEquals(value, processing)) discardValue = value;
                }
                else
                {
                    count = Math.Min(2, count + 1);
                    if (count == 1 && !invalid) first = value;
                    else
                    {
                        invalid = true;
                        discardFirst = first;
                        first = null;
                        if (!ReferenceEquals(value, discardFirst)) discardValue = value;
                    }
                }
            }
            DisposeQuiet(discardFirst);
            DisposeQuiet(discardValue);
        }

        internal void Invalidate()
        {
            T discard = null;
            lock (gate)
            {
                if (!closed)
                {
                    invalid = true;
                    discard = first;
                    first = null;
                }
            }
            DisposeQuiet(discard);
        }

        internal bool TryComplete(int completionStatus, Func<T, object> readOutput,
            CancellationToken token, out WsabiWmiMethodSnapshot snapshot)
        {
            snapshot = null;
            T selected;
            int selectedCount;
            bool selectedInvalid;
            lock (gate)
            {
                if (closed) return false;
                closed = true;
                selected = processing = first;
                first = null;
                selectedCount = count;
                selectedInvalid = invalid;
            }
            try
            {
                token.ThrowIfCancellationRequested();
                WsabiWmiMethodSnapshot completed;
                if (completionStatus != 0)
                    completed = new WsabiWmiMethodSnapshot(completionStatus, null);
                else if (selectedInvalid || selectedCount > 1)
                    completed = new WsabiWmiMethodSnapshot(0, new object());
                else if (selectedCount == 0 || selected == null)
                    completed = new WsabiWmiMethodSnapshot(0, null);
                else
                {
                    if (readOutput == null) throw new ArgumentNullException(nameof(readOutput));
                    // The reader must return a detached, bounded field view.
                    // It is not stored by this collector.
                    completed = new WsabiWmiMethodSnapshot(0, readOutput(selected));
                }
                token.ThrowIfCancellationRequested();
                snapshot = completed;
                return true;
            }
            finally
            {
                DisposeQuiet(selected);
                lock (gate) { processing = null; }
            }
        }

        public void Dispose()
        {
            T discard;
            lock (gate)
            {
                closed = true;
                discard = first;
                first = null;
                // A completion already reading processing owns its cleanup.
            }
            DisposeQuiet(discard);
        }

        private void DisposeQuiet(T value)
        {
            if (value == null) return;
            // Reentrant callbacks may hand back the object being discarded.
            // Track only active disposal, without calling provider equality or
            // retaining historical objects after Dispose has returned.
            lock (gate) { if (!disposing.Add(value)) return; }
            try { value.Dispose(); } catch { }
            finally { lock (gate) { disposing.Remove(value); } }
        }

        private sealed class ReferenceComparer : IEqualityComparer<T>
        {
            internal static readonly ReferenceComparer Instance = new ReferenceComparer();
            public bool Equals(T left, T right) => ReferenceEquals(left, right);
            public int GetHashCode(T value) => RuntimeHelpers.GetHashCode(value);
        }
    }
}
