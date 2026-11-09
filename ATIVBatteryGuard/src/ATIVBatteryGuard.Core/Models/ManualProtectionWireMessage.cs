using System;
using System.Globalization;
using System.Security.Cryptography;

namespace ATIVBatteryGuard.Core.Models
{
    public enum ManualProtectionWireKind { Hello, Request, Progress, Result, Ack, Released }

    // Ephemeral request attribution only, not device identity or a permission.
    // These values belong on the private pipe, never in user reports or logs.
    public sealed class ManualProtectionContext
    {
        public string JobId { get; }
        public string Nonce { get; }
        public ManualProtectionOperation Operation { get; }
        public ManualProtectionContext(string jobId, string nonce, ManualProtectionOperation operation)
        {
            if (!Hex(jobId, 32) || !Hex(nonce, 64)) throw new ArgumentException("The local request context is invalid.");
            ManualProtectionLimits.Validate(operation);
            JobId = jobId; Nonce = nonce; Operation = operation;
        }
        public bool Matches(ManualProtectionContext other)
        {
            if (other == null || Operation != other.Operation) return false;
            int difference = 0;
            for (int i = 0; i < JobId.Length; i++) difference |= JobId[i] ^ other.JobId[i];
            for (int i = 0; i < Nonce.Length; i++) difference |= Nonce[i] ^ other.Nonce[i];
            return difference == 0;
        }
        public static ManualProtectionContext Create(ManualProtectionOperation operation)
        {
            ManualProtectionLimits.Validate(operation);
            var bytes = new byte[32];
            try
            {
                using (var random = RandomNumberGenerator.Create())
                {
                    if (random == null) throw new InvalidOperationException("The local random source is unavailable.");
                    random.GetBytes(bytes);
                }
                int any = 0; foreach (byte value in bytes) any |= value;
                if (any == 0) throw new InvalidOperationException("The local random source supplied unsupported content.");
                var text = new System.Text.StringBuilder(64);
                foreach (byte value in bytes) text.Append(value.ToString("x2", CultureInfo.InvariantCulture));
                return new ManualProtectionContext(Guid.NewGuid().ToString("N"), text.ToString(), operation);
            }
            finally { Array.Clear(bytes, 0, bytes.Length); }
        }
        private static bool Hex(string value, int length)
        {
            if (value == null || value.Length != length) return false;
            foreach (char cell in value) if (!(cell >= '0' && cell <= '9' || cell >= 'a' && cell <= 'f')) return false;
            return true;
        }
    }

    public sealed class ManualProtectionWireMessage
    {
        public ManualProtectionContext Context { get; }
        public ManualProtectionWireKind Kind { get; }
        public ManualProtectionPhase Phase { get; }
        public ManualProtectionResult Result { get; }
        private ManualProtectionWireMessage(ManualProtectionContext context, ManualProtectionWireKind kind,
            ManualProtectionPhase phase = ManualProtectionPhase.Idle, ManualProtectionResult result = null)
        {
            Context = context ?? throw new ArgumentNullException(nameof(context)); Kind = kind; Phase = phase; Result = result;
        }
        public static ManualProtectionWireMessage Hello(ManualProtectionContext context) => new ManualProtectionWireMessage(context, ManualProtectionWireKind.Hello);
        public static ManualProtectionWireMessage Request(ManualProtectionContext context) => new ManualProtectionWireMessage(context, ManualProtectionWireKind.Request);
        public static ManualProtectionWireMessage Ack(ManualProtectionContext context) => new ManualProtectionWireMessage(context, ManualProtectionWireKind.Ack);
        public static ManualProtectionWireMessage Released(ManualProtectionContext context) => new ManualProtectionWireMessage(context, ManualProtectionWireKind.Released);
        public static ManualProtectionWireMessage Progress(ManualProtectionContext context, ManualProtectionPhase phase)
        {
            if (!Enum.IsDefined(typeof(ManualProtectionPhase), phase) || phase == ManualProtectionPhase.Idle || phase == ManualProtectionPhase.Completed)
                throw new ArgumentOutOfRangeException(nameof(phase));
            return new ManualProtectionWireMessage(context, ManualProtectionWireKind.Progress, phase);
        }
        public static ManualProtectionWireMessage ForResult(ManualProtectionContext context, ManualProtectionResult result)
        {
            if (result == null || context == null || context.Operation != result.Operation)
                throw new ArgumentException("The detached result does not match this local request.");
            if (!result.CleanupComplete)
                throw new ArgumentException("Only an actually closed outcome may be sent as a terminal result.");
            return new ManualProtectionWireMessage(context, ManualProtectionWireKind.Result, result: result);
        }
    }
}
