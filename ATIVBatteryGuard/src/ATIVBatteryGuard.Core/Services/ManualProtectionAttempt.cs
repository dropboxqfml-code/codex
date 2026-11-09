using System;
using System.Security.Cryptography;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    public enum ManualProtectionAttemptIssue
    {
        None, InvalidOperation, PlatformUnknownOrDifferent, DeviceScopeMismatch, TargetScopeMismatch,
        TargetNotUniqueAndActive, MetadataMismatch, RandomSourceUnavailable,
        ZeroComparisonContent, DuplicateComparisonContent
    }

    // Fixed manual-operation purpose. Each constructed attempt is single-use;
    // only the three declared operation schedules are represented here.
    public enum ManualProtectionRole { PreMode, PreUpper, PreLower, SemanticSet, PostMode, PostUpper, PostLower }
    public sealed class ManualProtectionAttempt
    {
        public const string Purpose = "ManualProtection-v1";
        public const int DeclaredRetries = 0;
        public ManualProtectionOperation Operation { get; }
        public System.Collections.Generic.IReadOnlyList<ManualProtectionRole> StageOrder { get; }
        public int MaximumMethodEntries => StageOrder.Count;
        public int MaximumSettingEntries => Operation == ManualProtectionOperation.ReadState ? 0 : 1;
        public int MaximumReadCandidates => Operation == ManualProtectionOperation.ReadState ? 3
            : Operation == ManualProtectionOperation.Enable80 ? 6 : 2;
        private const int ComparisonBytes = 8;
        private const ushort FirmwareCommand = 0x7a;
        private const uint WindowsMethodId = 1;
        private readonly object targetIdentity;
        private readonly WsabiWmiMethodRequest[] requests = new WsabiWmiMethodRequest[7];
        private readonly byte[][] comparisons = new byte[7][];
        private readonly byte[] firstComponents = new byte[7];
        private readonly byte[] secondComponents = new byte[7];

        public WsabiWmiMethodBinder Binder { get; }
        public bool IsHardwareObservation => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        private ManualProtectionAttempt(ManualProtectionOperation operation, object targetIdentity, WsabiWmiMethodBinder binder, byte[] content)
        {
            this.targetIdentity = targetIdentity; Binder = binder; Operation = operation;
            StageOrder = Schedule(operation);
            for (int i = 0; i < MaximumMethodEntries; i++)
            {
                int role = (int)StageOrder[i];
                comparisons[role] = new byte[ComparisonBytes];
                Array.Copy(content, i * ComparisonBytes, comparisons[role], 0, ComparisonBytes);
                bool setter = IsSettingRole(StageOrder[i]);
                // Fixed source correspondence; the setter's second cell is
                // preserved content, never an arbitrary address argument.
                firstComponents[role] = setter ? (byte)(operation == ManualProtectionOperation.Enable80 ? 1 : 0) : (byte)0xf0;
                secondComponents[role] = setter ? (byte)0
                    : StageOrder[i] == ManualProtectionRole.PreUpper || StageOrder[i] == ManualProtectionRole.PostUpper ? (byte)0x50
                    : StageOrder[i] == ManualProtectionRole.PreLower || StageOrder[i] == ManualProtectionRole.PostLower ? (byte)0x51 : (byte)0x4f;
                var frame = new byte[21];
                try
                {
                    frame[0] = 0x43; frame[1] = 0x58; frame[2] = 0x7a;
                    frame[5] = 0x82; frame[6] = setter ? (byte)0xe3 : (byte)0x80;
                    frame[7] = firstComponents[role]; frame[8] = secondComponents[role];
                    Array.Copy(comparisons[role], 0, frame, 9, ComparisonBytes);
                    requests[role] = new WsabiWmiMethodRequest(WindowsMethodId, FirmwareCommand, frame);
                }
                finally { Array.Clear(frame, 0, frame.Length); }
            }
        }

        public bool TargetMatches(object identity) => identity != null && ReferenceEquals(targetIdentity, identity);

        public WsabiWmiMethodRequest GetRequest(ManualProtectionRole role)
            => requests[RoleIndex(role)];

        // Narrow equality guard for the real SDK leaf, not a generic request
        // normalizer. No alternate command/address/input can be admitted.
        public bool ValidateRoleRequest(ManualProtectionRole role, WsabiWmiMethodRequest supplied)
        {
            int index = (int)role;
            if (index < 0 || index >= requests.Length || requests[index] == null || supplied == null ||
                supplied.ObservedMethodId != WindowsMethodId || supplied.FirmwareCommand != FirmwareCommand) return false;
            var actual = supplied.Frame; var expected = requests[index].Frame;
            try
            {
                if (actual.Length != expected.Length) return false;
                int difference = 0;
                for (int i = 0; i < expected.Length; i++) difference |= actual[i] ^ expected[i];
                return difference == 0;
            }
            finally { Array.Clear(actual, 0, actual.Length); Array.Clear(expected, 0, expected.Length); }
        }

        internal byte[] GetComparison(ManualProtectionRole role) => (byte[])comparisons[RoleIndex(role)].Clone();
        internal byte GetFirstComponent(ManualProtectionRole role) => firstComponents[RoleIndex(role)];
        internal byte GetSecondComponent(ManualProtectionRole role) => secondComponents[RoleIndex(role)];

        public static bool TryCreate(ManualProtectionOperation operation, WsabiWmiSingleReadTarget target, WsabiWmiContractMetadataReport metadata,
            out ManualProtectionAttempt attempt, out ManualProtectionAttemptIssue issue)
        {
            attempt = null;
            WsabiWmiMethodBinder binder;
            if (!ValidateOperation(operation, out issue) || !Validate(target, metadata, out binder, out issue)) return false;
            try
            {
                using (var random = RandomNumberGenerator.Create())
                {
                    if (random == null) { issue = ManualProtectionAttemptIssue.RandomSourceUnavailable; return false; }
                    return CreateValidated(operation, target.Identity, binder, random.GetBytes, out attempt, out issue);
                }
            }
            catch { attempt = null; issue = ManualProtectionAttemptIssue.RandomSourceUnavailable; return false; }
        }

        // Test seam only: exactly one 24- or 56-byte fill. Invalid content is an abort,
        // never an entropy resample or a firmware retry.
        internal static bool TryCreateWithRandom(ManualProtectionOperation operation, WsabiWmiSingleReadTarget target, WsabiWmiContractMetadataReport metadata,
            Action<byte[]> fillRandom, out ManualProtectionAttempt attempt, out ManualProtectionAttemptIssue issue)
        {
            attempt = null;
            WsabiWmiMethodBinder binder;
            return ValidateOperation(operation, out issue) && Validate(target, metadata, out binder, out issue) &&
                CreateValidated(operation, target.Identity, binder, fillRandom, out attempt, out issue);
        }

        private static bool CreateValidated(ManualProtectionOperation operation, object identity, WsabiWmiMethodBinder binder, Action<byte[]> fillRandom,
            out ManualProtectionAttempt attempt, out ManualProtectionAttemptIssue issue)
        {
            attempt = null; issue = ManualProtectionAttemptIssue.RandomSourceUnavailable;
            if (fillRandom == null) return false;
            int count = Schedule(operation).Count;
            var content = new byte[count * ComparisonBytes];
            try
            {
                fillRandom(content);
                for (int i = 0; i < count; i++)
                {
                    int any = 0;
                    for (int k = 0; k < ComparisonBytes; k++) any |= content[i * ComparisonBytes + k];
                    if (any == 0) { issue = ManualProtectionAttemptIssue.ZeroComparisonContent; return false; }
                    for (int j = 0; j < i; j++)
                    {
                        int difference = 0;
                        for (int k = 0; k < ComparisonBytes; k++)
                            difference |= content[i * ComparisonBytes + k] ^ content[j * ComparisonBytes + k];
                        if (difference == 0) { issue = ManualProtectionAttemptIssue.DuplicateComparisonContent; return false; }
                    }
                }
                attempt = new ManualProtectionAttempt(operation, identity, binder, content);
                issue = ManualProtectionAttemptIssue.None; return true;
            }
            catch { attempt = null; issue = ManualProtectionAttemptIssue.RandomSourceUnavailable; return false; }
            finally { Array.Clear(content, 0, content.Length); }
        }

        private static bool Validate(WsabiWmiSingleReadTarget value, WsabiWmiContractMetadataReport metadata,
            out WsabiWmiMethodBinder binder, out ManualProtectionAttemptIssue issue)
        {
            binder = null; issue = ManualProtectionAttemptIssue.PlatformUnknownOrDifferent;
            if (value == null || !value.IsWindows10X64) return false;
            issue = ManualProtectionAttemptIssue.DeviceScopeMismatch;
            if (!DeviceEquals(value.ModelName, "940X3G/930X3G") || !DeviceEquals(value.BiosVersion, "P05ACJ.128.140819.dg")) return false;
            issue = ManualProtectionAttemptIssue.TargetScopeMismatch;
            if (!ScopeEquals(value.NamespaceName, WsabiWmiContractMetadataPolicy.LocalNamespace) ||
                !ScopeEquals(value.ClassName, WsabiWmiContractMetadataPolicy.MethodClass) ||
                !ScopeEquals(value.MethodName, WsabiWmiContractMetadataPolicy.MethodName) || value.Identity == null) return false;
            issue = ManualProtectionAttemptIssue.TargetNotUniqueAndActive;
            if (!value.EnumerationComplete || value.InstanceCount != 1 || value.Active != true) return false;
            issue = ManualProtectionAttemptIssue.MetadataMismatch;
            if (!WsabiWmiMethodBinder.TryCreate(metadata, out binder) || binder.ObservedMethodId != WindowsMethodId) { binder = null; return false; }
            issue = ManualProtectionAttemptIssue.None; return true;
        }

        public bool IsSettingRole(ManualProtectionRole role)
            => role == ManualProtectionRole.SemanticSet && Operation != ManualProtectionOperation.ReadState;
        public ManualProtectionRole GetRole(int index)
        {
            if (index < 0 || index >= StageOrder.Count) throw new ArgumentOutOfRangeException(nameof(index));
            return StageOrder[index];
        }
        public int GetIndex(ManualProtectionRole role)
        {
            for (int i = 0; i < StageOrder.Count; i++) if (StageOrder[i] == role) return i;
            throw new ArgumentOutOfRangeException(nameof(role));
        }
        private int RoleIndex(ManualProtectionRole role) { GetIndex(role); return (int)role; }
        private static bool ValidateOperation(ManualProtectionOperation operation, out ManualProtectionAttemptIssue issue)
        {
            issue = ManualProtectionAttemptIssue.InvalidOperation;
            return Enum.IsDefined(typeof(ManualProtectionOperation), operation);
        }
        internal static System.Collections.Generic.IReadOnlyList<ManualProtectionRole> Schedule(ManualProtectionOperation operation)
        {
            if (!Enum.IsDefined(typeof(ManualProtectionOperation), operation)) throw new ArgumentOutOfRangeException(nameof(operation));
            return Array.AsReadOnly(operation == ManualProtectionOperation.Enable80 ? new[] {
                ManualProtectionRole.PreMode, ManualProtectionRole.PreUpper, ManualProtectionRole.PreLower,
                ManualProtectionRole.SemanticSet, ManualProtectionRole.PostMode, ManualProtectionRole.PostUpper, ManualProtectionRole.PostLower }
                : operation == ManualProtectionOperation.DisableProtection ? new[] {
                    ManualProtectionRole.PreMode, ManualProtectionRole.SemanticSet, ManualProtectionRole.PostMode }
                : new[] { ManualProtectionRole.PreMode, ManualProtectionRole.PreUpper, ManualProtectionRole.PreLower });
        }
        private static bool DeviceEquals(string actual, string expected)
            => actual != null && actual.Length <= 128 && string.Equals(actual.Trim(), expected, StringComparison.OrdinalIgnoreCase);
        private static bool ScopeEquals(string actual, string expected)
            => string.Equals(actual, expected, StringComparison.OrdinalIgnoreCase);
    }
}
