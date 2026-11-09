using System;
using System.Security.Cryptography;
using ATIVBatteryGuard.Core.Models;

namespace ATIVBatteryGuard.Core.Services
{
    public enum WsabiWmiProtectionAttemptIssue
    {
        None, PlatformUnknownOrDifferent, DeviceScopeMismatch, TargetScopeMismatch,
        TargetNotUniqueAndActive, MetadataMismatch, RandomSourceUnavailable,
        ZeroComparisonContent, DuplicateComparisonContent
    }

    // The separately approved Protection0To1-v1 purpose only. This sealed
    // attempt owns seven immutable requests; there is no supplied selector,
    // address, input mode, ordering, timeout, retry or random-content argument
    // on the public factory. Construction does not invoke a method or claim
    // the tool's persistent reservation, and is not hardware support evidence.
    public sealed class WsabiWmiProtectionTransitionAttempt
    {
        public const string Purpose = "Protection0To1-v1";
        public const int MaximumMethodEntries = 7;
        public const int MaximumSettingEntries = 1;
        public const int MaximumReadCandidates = 6;
        public const int DeclaredRetries = 0;
        private const int ComparisonBytes = 8;
        private const int RandomBytes = MaximumMethodEntries * ComparisonBytes;
        private const ushort FirmwareCommand = 0x7a;
        private const uint WindowsMethodId = 1;
        private readonly object targetIdentity;
        private readonly WsabiWmiMethodRequest[] requests = new WsabiWmiMethodRequest[MaximumMethodEntries];
        private readonly byte[][] comparisons = new byte[MaximumMethodEntries][];
        private readonly byte[] firstComponents = new byte[MaximumMethodEntries];
        private readonly byte[] secondComponents = new byte[MaximumMethodEntries];

        public WsabiWmiMethodBinder Binder { get; }
        public bool IsHardwareObservation => false;
        public bool CanInvokeMethods => false;
        public bool CanReadHardware => false;
        public bool CanWriteHardware => false;

        private WsabiWmiProtectionTransitionAttempt(object targetIdentity, WsabiWmiMethodBinder binder, byte[] content)
        {
            this.targetIdentity = targetIdentity; Binder = binder;
            for (int i = 0; i < MaximumMethodEntries; i++)
            {
                comparisons[i] = new byte[ComparisonBytes];
                Array.Copy(content, i * ComparisonBytes, comparisons[i], 0, ComparisonBytes);
                bool setter = i == (int)WsabiWmiProtectionTransitionStage.SemanticSet1;
                // Existing conditional source mapping: the selected reader
                // uses high then low XDATA components. The semantic setter
                // instead consumes input1; its second message cell is unused
                // preserved content, NOT a target address or prior mode.
                firstComponents[i] = setter ? (byte)1 : (byte)0xf0;
                secondComponents[i] = setter ? (byte)0 : i == 1 || i == 5 ? (byte)0x50
                    : i == 2 || i == 6 ? (byte)0x51 : (byte)0x4f;
                var frame = new byte[21];
                try
                {
                    frame[0] = 0x43; frame[1] = 0x58; frame[2] = 0x7a;
                    frame[5] = 0x82; frame[6] = setter ? (byte)0xe3 : (byte)0x80;
                    frame[7] = firstComponents[i]; frame[8] = secondComponents[i];
                    Array.Copy(comparisons[i], 0, frame, 9, ComparisonBytes);
                    requests[i] = new WsabiWmiMethodRequest(WindowsMethodId, FirmwareCommand, frame);
                }
                finally { Array.Clear(frame, 0, frame.Length); }
            }
        }

        public bool TargetMatches(object identity) => identity != null && ReferenceEquals(targetIdentity, identity);

        public WsabiWmiMethodRequest GetRequest(WsabiWmiProtectionTransitionStage role)
            => requests[RoleIndex(role)];

        // Narrow equality guard for the real SDK leaf, not a generic request
        // normalizer. No alternate command/address/input can be admitted.
        public bool ValidateRoleRequest(WsabiWmiProtectionTransitionStage role, WsabiWmiMethodRequest supplied)
        {
            int index = (int)role;
            if (index < 0 || index >= MaximumMethodEntries || supplied == null ||
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

        internal byte[] GetComparison(WsabiWmiProtectionTransitionStage role) => (byte[])comparisons[RoleIndex(role)].Clone();
        internal byte GetFirstComponent(WsabiWmiProtectionTransitionStage role) => firstComponents[RoleIndex(role)];
        internal byte GetSecondComponent(WsabiWmiProtectionTransitionStage role) => secondComponents[RoleIndex(role)];

        public static bool TryCreate(WsabiWmiSingleReadTarget target, WsabiWmiContractMetadataReport metadata,
            out WsabiWmiProtectionTransitionAttempt attempt, out WsabiWmiProtectionAttemptIssue issue)
        {
            attempt = null;
            WsabiWmiMethodBinder binder;
            if (!Validate(target, metadata, out binder, out issue)) return false;
            try
            {
                using (var random = RandomNumberGenerator.Create())
                {
                    if (random == null) { issue = WsabiWmiProtectionAttemptIssue.RandomSourceUnavailable; return false; }
                    return CreateValidated(target.Identity, binder, random.GetBytes, out attempt, out issue);
                }
            }
            catch { attempt = null; issue = WsabiWmiProtectionAttemptIssue.RandomSourceUnavailable; return false; }
        }

        // Test seam only: exactly one 56-byte fill. Invalid content is an abort,
        // never an entropy resample or a firmware retry.
        internal static bool TryCreateWithRandom(WsabiWmiSingleReadTarget target, WsabiWmiContractMetadataReport metadata,
            Action<byte[]> fillRandom, out WsabiWmiProtectionTransitionAttempt attempt, out WsabiWmiProtectionAttemptIssue issue)
        {
            attempt = null;
            WsabiWmiMethodBinder binder;
            return Validate(target, metadata, out binder, out issue) &&
                CreateValidated(target.Identity, binder, fillRandom, out attempt, out issue);
        }

        private static bool CreateValidated(object identity, WsabiWmiMethodBinder binder, Action<byte[]> fillRandom,
            out WsabiWmiProtectionTransitionAttempt attempt, out WsabiWmiProtectionAttemptIssue issue)
        {
            attempt = null; issue = WsabiWmiProtectionAttemptIssue.RandomSourceUnavailable;
            if (fillRandom == null) return false;
            var content = new byte[RandomBytes];
            try
            {
                fillRandom(content);
                for (int i = 0; i < MaximumMethodEntries; i++)
                {
                    int any = 0;
                    for (int k = 0; k < ComparisonBytes; k++) any |= content[i * ComparisonBytes + k];
                    if (any == 0) { issue = WsabiWmiProtectionAttemptIssue.ZeroComparisonContent; return false; }
                    for (int j = 0; j < i; j++)
                    {
                        int difference = 0;
                        for (int k = 0; k < ComparisonBytes; k++)
                            difference |= content[i * ComparisonBytes + k] ^ content[j * ComparisonBytes + k];
                        if (difference == 0) { issue = WsabiWmiProtectionAttemptIssue.DuplicateComparisonContent; return false; }
                    }
                }
                attempt = new WsabiWmiProtectionTransitionAttempt(identity, binder, content);
                issue = WsabiWmiProtectionAttemptIssue.None; return true;
            }
            catch { attempt = null; issue = WsabiWmiProtectionAttemptIssue.RandomSourceUnavailable; return false; }
            finally { Array.Clear(content, 0, content.Length); }
        }

        private static bool Validate(WsabiWmiSingleReadTarget value, WsabiWmiContractMetadataReport metadata,
            out WsabiWmiMethodBinder binder, out WsabiWmiProtectionAttemptIssue issue)
        {
            binder = null; issue = WsabiWmiProtectionAttemptIssue.PlatformUnknownOrDifferent;
            if (value == null || !value.IsWindows10X64) return false;
            issue = WsabiWmiProtectionAttemptIssue.DeviceScopeMismatch;
            if (!DeviceEquals(value.ModelName, "940X3G/930X3G") || !DeviceEquals(value.BiosVersion, "P05ACJ.128.140819.dg")) return false;
            issue = WsabiWmiProtectionAttemptIssue.TargetScopeMismatch;
            if (!ScopeEquals(value.NamespaceName, WsabiWmiContractMetadataPolicy.LocalNamespace) ||
                !ScopeEquals(value.ClassName, WsabiWmiContractMetadataPolicy.MethodClass) ||
                !ScopeEquals(value.MethodName, WsabiWmiContractMetadataPolicy.MethodName) || value.Identity == null) return false;
            issue = WsabiWmiProtectionAttemptIssue.TargetNotUniqueAndActive;
            if (!value.EnumerationComplete || value.InstanceCount != 1 || value.Active != true) return false;
            issue = WsabiWmiProtectionAttemptIssue.MetadataMismatch;
            if (!WsabiWmiMethodBinder.TryCreate(metadata, out binder) || binder.ObservedMethodId != WindowsMethodId) { binder = null; return false; }
            issue = WsabiWmiProtectionAttemptIssue.None; return true;
        }

        private static int RoleIndex(WsabiWmiProtectionTransitionStage role)
        {
            int index = (int)role;
            if (index < 0 || index >= MaximumMethodEntries) throw new ArgumentOutOfRangeException(nameof(role));
            return index;
        }
        private static bool DeviceEquals(string actual, string expected)
            => actual != null && string.Equals(actual.Trim(), expected, StringComparison.OrdinalIgnoreCase);
        private static bool ScopeEquals(string actual, string expected)
            => string.Equals(actual, expected, StringComparison.OrdinalIgnoreCase);
    }
}
