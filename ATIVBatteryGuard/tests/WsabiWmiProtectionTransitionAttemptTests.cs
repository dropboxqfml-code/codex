using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiProtectionTransitionAttemptTests()
    {
        Add("protection attempt fixes all seven packet roles independently of the production encoder", () =>
        {
            var attempt = ProtectionAttemptCreate();
            // Literal expectations from saved selected reader/setter and
            // generic callback proofs, not a call to the production encoder.
            byte[][] expected =
            {
                new byte[] { 0x43,0x58,0x7a,0,0,0x82,0x80,0xf0,0x4f, 1,2,3,4,5,6,7,8, 0,0,0,0 },
                new byte[] { 0x43,0x58,0x7a,0,0,0x82,0x80,0xf0,0x50, 9,10,11,12,13,14,15,16, 0,0,0,0 },
                new byte[] { 0x43,0x58,0x7a,0,0,0x82,0x80,0xf0,0x51, 17,18,19,20,21,22,23,24, 0,0,0,0 },
                new byte[] { 0x43,0x58,0x7a,0,0,0x82,0xe3,1,0, 25,26,27,28,29,30,31,32, 0,0,0,0 },
                new byte[] { 0x43,0x58,0x7a,0,0,0x82,0x80,0xf0,0x4f, 33,34,35,36,37,38,39,40, 0,0,0,0 },
                new byte[] { 0x43,0x58,0x7a,0,0,0x82,0x80,0xf0,0x50, 41,42,43,44,45,46,47,48, 0,0,0,0 },
                new byte[] { 0x43,0x58,0x7a,0,0,0x82,0x80,0xf0,0x51, 49,50,51,52,53,54,55,56, 0,0,0,0 }
            };
            int index = 0;
            foreach (var role in WsabiWmiProtectionTransitionReview.StageOrder)
            {
                var request = attempt.GetRequest(role);
                Equal((uint)1, request.ObservedMethodId); Equal((ushort)0x7a, request.FirmwareCommand);
                Check(request.Frame.SequenceEqual(expected[index]), "fixed role packet differed from saved source correspondence");
                Check(attempt.ValidateRoleRequest(role, request), "fixed packet failed its own exact equality guard");
                Equal(expected[index][7], attempt.GetFirstComponent(role)); Equal(expected[index][8], attempt.GetSecondComponent(role));
                Check(attempt.GetComparison(role).SequenceEqual(expected[index].Skip(9).Take(8)), "fixed role comparison differs");
                Check(request.Frame[6] != 0x81, "adjacent arbitrary-address write command was selected");
                index++;
            }
            Equal(7, index); Equal("Protection0To1-v1", WsabiWmiProtectionTransitionAttempt.Purpose);
            Equal(7, WsabiWmiProtectionTransitionAttempt.MaximumMethodEntries);
            Equal(1, WsabiWmiProtectionTransitionAttempt.MaximumSettingEntries);
            Equal(6, WsabiWmiProtectionTransitionAttempt.MaximumReadCandidates);
            Equal(0, WsabiWmiProtectionTransitionAttempt.DeclaredRetries);
            Equal(0, WsabiWmiSingleReadPlan.DeclaredSettingWrites);
        });

        Add("protection attempt fills exactly fifty-six random bytes once and clears the temporary without retaining caller aliases", () =>
        {
            int fills = 0; byte[] temporary = null; WsabiWmiProtectionTransitionAttempt attempt; WsabiWmiProtectionAttemptIssue issue;
            Check(WsabiWmiProtectionTransitionAttempt.TryCreateWithRandom(SingleReadTarget(new object()), BinderCompleteMetadata(1), bytes =>
            {
                fills++; Equal(56, bytes.Length); temporary = bytes; ProtectionAttemptFill(bytes);
            }, out attempt, out issue), "valid single fill was rejected");
            Equal(WsabiWmiProtectionAttemptIssue.None, issue); Equal(1, fills);
            Check(temporary.All(value => value == 0), "random temporary was retained after creation");
            temporary[0] = 0xfe;
            Equal((byte)1, attempt.GetRequest(WsabiWmiProtectionTransitionStage.PreMode).Frame[9]);
            var comparison = attempt.GetComparison(WsabiWmiProtectionTransitionStage.PreMode); comparison[0] = 0;
            Equal((byte)1, attempt.GetComparison(WsabiWmiProtectionTransitionStage.PreMode)[0]);
        });

        Add("protection attempt any all-zero tuple aborts all requests without a resample", () =>
        {
            for (int tuple = 0; tuple < 7; tuple++)
            {
                int selected = tuple, fills = 0; byte[] temporary = null;
                WsabiWmiProtectionTransitionAttempt attempt; WsabiWmiProtectionAttemptIssue issue;
                Check(!WsabiWmiProtectionTransitionAttempt.TryCreateWithRandom(SingleReadTarget(new object()), BinderCompleteMetadata(1), bytes =>
                {
                    fills++; temporary = bytes; ProtectionAttemptFill(bytes); Array.Clear(bytes, selected * 8, 8);
                }, out attempt, out issue), "zero tuple produced a fixed request set");
                Equal(WsabiWmiProtectionAttemptIssue.ZeroComparisonContent, issue); Equal(1, fills);
                Check(attempt == null && temporary.All(value => value == 0), "zero abort retained an attempt or temporary");
            }
        });

        Add("protection attempt every repeated tuple pair aborts without resampling or merging stage identity", () =>
        {
            for (int first = 0; first < 7; first++)
            for (int second = first + 1; second < 7; second++)
            {
                int a = first, b = second, fills = 0; WsabiWmiProtectionTransitionAttempt attempt; WsabiWmiProtectionAttemptIssue issue;
                Check(!WsabiWmiProtectionTransitionAttempt.TryCreateWithRandom(SingleReadTarget(new object()), BinderCompleteMetadata(1), bytes =>
                { fills++; ProtectionAttemptFill(bytes); Array.Copy(bytes, a * 8, bytes, b * 8, 8); }, out attempt, out issue),
                    "duplicate comparison tuple produced an attempt");
                Equal(WsabiWmiProtectionAttemptIssue.DuplicateComparisonContent, issue); Equal(1, fills); Check(attempt == null, "duplicate abort retained requests");
            }
        });

        Add("protection attempt missing throwing or partly filled random source is sanitized and does not retry", () =>
        {
            WsabiWmiProtectionTransitionAttempt attempt; WsabiWmiProtectionAttemptIssue issue;
            Check(!WsabiWmiProtectionTransitionAttempt.TryCreateWithRandom(SingleReadTarget(new object()), BinderCompleteMetadata(1), null,
                out attempt, out issue), "missing random source created an attempt");
            Equal(WsabiWmiProtectionAttemptIssue.RandomSourceUnavailable, issue); Check(attempt == null, "missing random source retained attempt");
            int calls = 0; byte[] temporary = null;
            Check(!WsabiWmiProtectionTransitionAttempt.TryCreateWithRandom(SingleReadTarget(new object()), BinderCompleteMetadata(1), bytes =>
            {
                calls++; temporary = bytes; bytes[0] = 1;
                throw new InvalidOperationException("Private RNG failure must not be reported.");
            }, out attempt, out issue), "throwing random source created an attempt");
            Equal(WsabiWmiProtectionAttemptIssue.RandomSourceUnavailable, issue); Equal(1, calls);
            Check(attempt == null && temporary.All(value => value == 0), "failed fill retained comparison data");
            Check(!WsabiWmiProtectionTransitionAttempt.TryCreateWithRandom(SingleReadTarget(new object()), BinderCompleteMetadata(1), bytes => bytes[0] = 1,
                out attempt, out issue), "partly filled zero tuples were accepted");
            Equal(WsabiWmiProtectionAttemptIssue.ZeroComparisonContent, issue);
        });

        Add("protection attempt guards the complete fixed model BIOS platform namespace and target scope before randomness", () =>
        {
            var identity = new object();
            ProtectionAttemptRejected(null, WsabiWmiProtectionAttemptIssue.PlatformUnknownOrDifferent);
            ProtectionAttemptRejected(SingleReadTarget(identity, windows10X64: false), WsabiWmiProtectionAttemptIssue.PlatformUnknownOrDifferent);
            foreach (string model in new[] { null, "", "940X3G", "930X3G", "NP940X3G", "940X3G/930X3G-extra", new string('x', 129) })
                ProtectionAttemptRejected(SingleReadTarget(identity, model: model), WsabiWmiProtectionAttemptIssue.DeviceScopeMismatch);
            foreach (string bios in new[] { null, "", "P05ACJ", "P05ACJ.128.140819.dg-extra", "P05ACJ.129.140819.dg", new string('x', 129) })
                ProtectionAttemptRejected(SingleReadTarget(identity, bios: bios), WsabiWmiProtectionAttemptIssue.DeviceScopeMismatch);
            foreach (string scope in new[] { null, "", @"root\cimv2", @"\\remote\root\WMI", @" root\WMI", @"root\WMI " })
                ProtectionAttemptRejected(SingleReadTarget(identity, namespaceName: scope), WsabiWmiProtectionAttemptIssue.TargetScopeMismatch);
            ProtectionAttemptRejected(SingleReadTarget(identity, className: "OtherClass"), WsabiWmiProtectionAttemptIssue.TargetScopeMismatch);
            ProtectionAttemptRejected(SingleReadTarget(identity, methodName: "OtherMethod"), WsabiWmiProtectionAttemptIssue.TargetScopeMismatch);
            ProtectionAttemptRejected(SingleReadTarget(null), WsabiWmiProtectionAttemptIssue.TargetScopeMismatch);
            var normalized = SingleReadTarget(identity, model: " 940x3g/930x3g\t", bios: " p05acj.128.140819.DG ",
                namespaceName: @"ROOT\wmi", className: "wmiacpimethod", methodName: "callsabifunction");
            WsabiWmiProtectionTransitionAttempt attempt; WsabiWmiProtectionAttemptIssue issue;
            Check(WsabiWmiProtectionTransitionAttempt.TryCreateWithRandom(normalized, BinderCompleteMetadata(1), ProtectionAttemptFill,
                out attempt, out issue) && attempt.TargetMatches(identity), "bounded normalized exact profile was rejected");
        });

        Add("protection attempt requires unique complete active enumeration before randomness", () =>
        {
            foreach (int count in new[] { -1, 0, 2, int.MaxValue })
                ProtectionAttemptRejected(SingleReadTarget(new object(), instanceCount: count), WsabiWmiProtectionAttemptIssue.TargetNotUniqueAndActive);
            foreach (bool? active in new bool?[] { null, false })
                ProtectionAttemptRejected(SingleReadTarget(new object(), active: active), WsabiWmiProtectionAttemptIssue.TargetNotUniqueAndActive);
            ProtectionAttemptRejected(SingleReadTarget(new object(), complete: false), WsabiWmiProtectionAttemptIssue.TargetNotUniqueAndActive);
        });

        Add("protection attempt requires detailed method metadata id one without borrowing the single read write-zero permission", () =>
        {
            foreach (uint id in new uint[] { 0, 2, uint.MaxValue }) ProtectionAttemptMetadataRejected(BinderCompleteMetadata(id));
            ProtectionAttemptMetadataRejected(null);
            var unresolved = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, null, null);
            var matched = BinderMatchedParameter();
            ProtectionAttemptMetadataRejected(SingleReadMetadata(unresolved, matched));
            ProtectionAttemptMetadataRejected(SingleReadMetadata(matched, unresolved));
            ProtectionAttemptMetadataRejected(SingleReadMetadata(matched, matched, WsabiWmiMetadataStatus.Partial));
            ProtectionAttemptMetadataRejected(SingleReadMetadata(matched, matched, bufferStatus: WsabiWmiMetadataStatus.Partial));
            Equal(0, WsabiWmiSingleReadPlan.DeclaredSettingWrites);
        });

        Add("protection attempt exact guard rejects every altered frame cell metadata and role or other attempt content", () =>
        {
            var attempt = ProtectionAttemptCreate();
            foreach (var role in WsabiWmiProtectionTransitionReview.StageOrder)
            {
                var own = attempt.GetRequest(role);
                for (int index = 0; index < 21; index++)
                {
                    var changed = own.Frame; changed[index] ^= 1;
                    Check(!attempt.ValidateRoleRequest(role, new WsabiWmiMethodRequest(1, 0x7a, changed)), "altered frame cell reached a fixed stage");
                }
                Check(!attempt.ValidateRoleRequest(role, null), "null request matched");
                Check(!attempt.ValidateRoleRequest(role, new WsabiWmiMethodRequest(2, 0x7a, own.Frame)), "different method metadata matched");
                Check(!attempt.ValidateRoleRequest(role, new WsabiWmiMethodRequest(1, 0x79, own.Frame)), "different declared command matched");
                foreach (var otherRole in WsabiWmiProtectionTransitionReview.StageOrder)
                    if (otherRole != role) Check(!attempt.ValidateRoleRequest(role, attempt.GetRequest(otherRole)), "different stage packet matched");
                var other = ProtectionAttemptCreate(first: 70);
                Check(!attempt.ValidateRoleRequest(role, other.GetRequest(role)), "another attempt comparison matched");
            }
            foreach (var invalid in new[] { (WsabiWmiProtectionTransitionStage)(-1), (WsabiWmiProtectionTransitionStage)7, (WsabiWmiProtectionTransitionStage)999 })
            {
                Check(!attempt.ValidateRoleRequest(invalid, attempt.GetRequest(WsabiWmiProtectionTransitionStage.PreMode)), "invalid role matched");
                BatteryThrows<ArgumentOutOfRangeException>(() => attempt.GetRequest(invalid));
                BatteryThrows<ArgumentOutOfRangeException>(() => attempt.GetComparison(invalid));
            }
        });

        Add("protection attempt requests comparisons and argument maps are immutable snapshots with reference-only target identity", () =>
        {
            var identity = new SingleReadPoisonIdentity(); var attempt = ProtectionAttemptCreate(identity);
            Check(attempt.TargetMatches(identity) && !attempt.TargetMatches(new SingleReadPoisonIdentity()) && !attempt.TargetMatches(null),
                "target matching used text provider equality or hashing");
            foreach (var role in WsabiWmiProtectionTransitionReview.StageOrder)
            {
                var request = attempt.GetRequest(role); var original = request.Frame;
                var external = request.Frame; Array.Clear(external, 0, external.Length);
                var args = (IReadOnlyDictionary<string, object>)request.Arguments["inData"];
                var bytes = (byte[])args["Bytes"]; Array.Clear(bytes, 0, bytes.Length);
                var content = attempt.GetComparison(role); Array.Clear(content, 0, content.Length);
                Check(request.Frame.SequenceEqual(original) && attempt.ValidateRoleRequest(role, request), "caller mutation changed a fixed request");
                Check(!request.CanInvokeMethods && !request.CanReadHardware && !request.CanWriteHardware, "request bytes granted hardware access");
            }
        });

        Add("protection attempt public construction cannot select arbitrary command address payload mode or random comparison", () =>
        {
            var type = typeof(WsabiWmiProtectionTransitionAttempt);
            Check(type.IsSealed && type.GetConstructors().Length == 0, "fixed attempt has a public constructor");
            var factories = type.GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly);
            Equal(1, factories.Length); Equal("TryCreate", factories[0].Name);
            var parameters = factories[0].GetParameters(); Equal(4, parameters.Length);
            Equal(typeof(WsabiWmiSingleReadTarget), parameters[0].ParameterType);
            Equal(typeof(WsabiWmiContractMetadataReport), parameters[1].ParameterType);
            Check(parameters[2].IsOut && parameters[3].IsOut, "public creation accepts protocol control arguments");
            var attempt = ProtectionAttemptCreate();
            Check(!attempt.IsHardwareObservation && !attempt.CanInvokeMethods && !attempt.CanReadHardware && !attempt.CanWriteHardware,
                "constructing seven fixed packets enabled charge control");
        });
    }

    private static void ProtectionAttemptFill(byte[] bytes) { for (int i = 0; i < bytes.Length; i++) bytes[i] = (byte)(i + 1); }
    private static WsabiWmiProtectionTransitionAttempt ProtectionAttemptCreate(object identity = null, byte first = 1)
    {
        WsabiWmiProtectionTransitionAttempt attempt; WsabiWmiProtectionAttemptIssue issue;
        Check(WsabiWmiProtectionTransitionAttempt.TryCreateWithRandom(SingleReadTarget(identity ?? new object()), BinderCompleteMetadata(1), bytes =>
        { for (int i = 0; i < bytes.Length; i++) bytes[i] = (byte)(first + i); }, out attempt, out issue), "fixed attempt fixture creation failed");
        Equal(WsabiWmiProtectionAttemptIssue.None, issue); return attempt;
    }
    private static void ProtectionAttemptRejected(WsabiWmiSingleReadTarget target, WsabiWmiProtectionAttemptIssue expected)
    {
        int fills = 0; WsabiWmiProtectionTransitionAttempt attempt; WsabiWmiProtectionAttemptIssue issue;
        Check(!WsabiWmiProtectionTransitionAttempt.TryCreateWithRandom(target, BinderCompleteMetadata(1), bytes => fills++, out attempt, out issue),
            "invalid target produced an attempt");
        Equal(expected, issue); Equal(0, fills); Check(attempt == null, "invalid target retained requests");
    }
    private static void ProtectionAttemptMetadataRejected(WsabiWmiContractMetadataReport metadata)
    {
        int fills = 0; WsabiWmiProtectionTransitionAttempt attempt; WsabiWmiProtectionAttemptIssue issue;
        Check(!WsabiWmiProtectionTransitionAttempt.TryCreateWithRandom(SingleReadTarget(new object()), metadata, bytes => fills++, out attempt, out issue),
            "invalid metadata produced an attempt");
        Equal(WsabiWmiProtectionAttemptIssue.MetadataMismatch, issue); Equal(0, fills); Check(attempt == null, "invalid metadata retained requests");
    }
}
