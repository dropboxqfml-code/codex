using System;
using System.Collections.Generic;
using System.Linq;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    // Detached scope and existing synthetic framing only. No real request
    // candidate, target discovery, reservation or hardware call is exercised.
    private static void RegisterWsabiWmiSingleReadPlanTests()
    {
        Add("single read plan declares A bounds while preserving Unsupported hardware authority", () =>
        {
            var plan = SingleReadPlanCreate(SingleReadTarget(new object()));
            Equal(1, WsabiWmiSingleReadPlan.MaximumDispatchHandoffs);
            Equal(0, WsabiWmiSingleReadPlan.DeclaredHandshakeCalls);
            Equal(0, WsabiWmiSingleReadPlan.DeclaredRetries);
            Equal(0, WsabiWmiSingleReadPlan.DeclaredSettingWrites);
            Equal((uint)1, plan.Binder.ObservedMethodId);
            Check(plan.MatchesCandidateScope && !plan.IsHardwareObservation && !plan.CanInvokeMethods &&
                !plan.CanReadHardware && !plan.CanWriteHardware, "scope match became a hardware observation or execution authority");
            Check(!plan.Binder.CanInvokeMethods && !plan.Binder.CanReadHardware && !plan.Binder.CanWriteHardware,
                "scope plan changed the offline binder's authority");
        });

        Add("single read plan rejects B invalid variants and unknown or different supplied platform", () =>
        {
            foreach (var variant in new[] { WsabiWmiReadTrialVariant.HandshakeThenRead, (WsabiWmiReadTrialVariant)(-1), (WsabiWmiReadTrialVariant)999 })
                SingleReadPlanRejected(SingleReadTarget(new object()), WsabiWmiSingleReadPlanIssue.VariantNotAvailable, variant);
            SingleReadPlanRejected(null, WsabiWmiSingleReadPlanIssue.PlatformUnknownOrDifferent);
            SingleReadPlanRejected(SingleReadTarget(new object(), windows10X64: false), WsabiWmiSingleReadPlanIssue.PlatformUnknownOrDifferent);
        });

        Add("single read plan matches one full WMI model and BIOS using bounded trimmed ordinal text", () =>
        {
            var identity = new object();
            var normalized = SingleReadTarget(identity, model: " \t940x3g/930x3g\r\n", bios: "  p05acj.128.140819.DG\t");
            var plan = SingleReadPlanCreate(normalized);
            Check(plan.MatchesTarget(SingleReadTarget(identity)), "equivalent trimmed full device scope was rejected");
            foreach (string model in new[] { null, "", "940X3G", "930X3G", "NP940X3G", "940X3G/930X3G-extra", "940X3G/930X3G\0" })
                SingleReadPlanRejected(SingleReadTarget(identity, model: model), WsabiWmiSingleReadPlanIssue.DeviceScopeMismatch);
            foreach (string bios in new[] { null, "", "P05ACJ", "P05ACJ.128", "P05ACJ.128.140819.dg-extra", "P05ACJ.128.140819.dg\0", "P05ACJ.129.140819.dg" })
                SingleReadPlanRejected(SingleReadTarget(identity, bios: bios), WsabiWmiSingleReadPlanIssue.DeviceScopeMismatch);

            const string exactModel = "940X3G/930X3G", exactBios = "P05ACJ.128.140819.dg";
            string maximumModel = new string(' ', 128 - exactModel.Length) + exactModel;
            string maximumBios = exactBios + new string(' ', 128 - exactBios.Length);
            SingleReadPlanCreate(SingleReadTarget(identity, model: maximumModel, bios: maximumBios));
            var tooLong = SingleReadTarget(identity, model: maximumModel + " ", bios: maximumBios + " ");
            Check(tooLong.ModelName == null && tooLong.BiosVersion == null, "overlong device values were retained or truncated");
            SingleReadPlanRejected(tooLong, WsabiWmiSingleReadPlanIssue.DeviceScopeMismatch);
            SingleReadPlanRejected(SingleReadTarget(identity, bios: maximumBios + " "), WsabiWmiSingleReadPlanIssue.DeviceScopeMismatch);
        });

        Add("single read plan restricts the local namespace class method and requires an opaque target identity", () =>
        {
            var identity = new object();
            SingleReadPlanCreate(SingleReadTarget(identity, namespaceName: @"ROOT\wmi", className: "wmiacpimethod", methodName: "cALLsABIfunction"));
            foreach (string value in new[] { null, "", @"\\remote\root\WMI", @"root\cimv2", @" root\WMI", @"root\WMI ", @"root\WMI;SELECT *", new string('x', 129) })
                SingleReadPlanRejected(SingleReadTarget(identity, namespaceName: value), WsabiWmiSingleReadPlanIssue.TargetScopeMismatch);
            foreach (string value in new[] { null, "", "WmiAcpiVersion", "WmiAcpiMethodExtra", " WmiAcpiMethod", new string('x', 129) })
                SingleReadPlanRejected(SingleReadTarget(identity, className: value), WsabiWmiSingleReadPlanIssue.TargetScopeMismatch);
            foreach (string value in new[] { null, "", "OtherMethod", "CallSabiFunctionExtra", " CallSabiFunction", new string('x', 129) })
                SingleReadPlanRejected(SingleReadTarget(identity, methodName: value), WsabiWmiSingleReadPlanIssue.TargetScopeMismatch);
            SingleReadPlanRejected(SingleReadTarget(null), WsabiWmiSingleReadPlanIssue.TargetScopeMismatch);
        });

        Add("single read plan requires complete enumeration of exactly one actively reported instance", () =>
        {
            var identity = new object();
            foreach (int count in new[] { -1, 0, 2, 8, int.MaxValue })
                SingleReadPlanRejected(SingleReadTarget(identity, instanceCount: count), WsabiWmiSingleReadPlanIssue.TargetNotUniqueAndActive);
            foreach (bool? active in new bool?[] { null, false })
                SingleReadPlanRejected(SingleReadTarget(identity, active: active), WsabiWmiSingleReadPlanIssue.TargetNotUniqueAndActive);
            foreach (int count in new[] { 0, 1, 2 })
                SingleReadPlanRejected(SingleReadTarget(identity, complete: false, instanceCount: count), WsabiWmiSingleReadPlanIssue.TargetNotUniqueAndActive);
            SingleReadPlanCreate(SingleReadTarget(identity, complete: true, instanceCount: 1, active: true));
        });

        Add("single read plan reuses detailed binder alternatives and requires Windows method id one", () =>
        {
            var target = SingleReadTarget(new object());
            var matched = BinderMatchedParameter();
            Equal(WsabiWmiQualifierMatch.Missing, matched.EmbeddedInstanceMatch);
            Equal(WsabiWmiQualifierMatch.MatchesDataBuffer, matched.CimTypeMatch);
            SingleReadPlanCreate(target, SingleReadMetadata(matched, matched));
            var embeddedOnly = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, "DataBuffer", null);
            SingleReadPlanCreate(target, SingleReadMetadata(embeddedOnly, matched));
            SingleReadPlanCreate(target, SingleReadMetadata(matched, embeddedOnly));
            var unresolved = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, null, null);
            var conflict = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, "OtherClass", "object:DataBuffer");
            foreach (var parameter in new[] { unresolved, conflict })
            {
                SingleReadMetadataRejected(target, SingleReadMetadata(parameter, matched));
                SingleReadMetadataRejected(target, SingleReadMetadata(matched, parameter));
            }
            foreach (uint id in new uint[] { 0, 2, uint.MaxValue })
                SingleReadMetadataRejected(target, BinderCompleteMetadata(id));
            foreach (var metadata in new[]
            {
                (WsabiWmiContractMetadataReport)null,
                BinderMetadata(WsabiWmiGuidMatch.Other, 1, true, true),
                BinderMetadata(WsabiWmiGuidMatch.MatchesPublicCandidate, 1, false, true),
                BinderMetadata(WsabiWmiGuidMatch.MatchesPublicCandidate, 1, true, false),
                SingleReadMetadata(matched, matched, WsabiWmiMetadataStatus.Partial),
                SingleReadMetadata(matched, matched, bufferStatus: WsabiWmiMetadataStatus.Partial),
                new WsabiWmiContractMetadataReport(new WsabiWmiContractMethodMetadata(
                    WsabiWmiMetadataStatus.Complete, WsabiWmiGuidMatch.MatchesPublicCandidate, 1, true, true, true),
                    new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, true))
            }) SingleReadMetadataRejected(target, metadata);
        });

        Add("single read plan compares opaque target identities by reference without provider equality hashing or text", () =>
        {
            var identity = new SingleReadPoisonIdentity();
            var target = SingleReadTarget(identity);
            var plan = SingleReadPlanCreate(target);
            Check(plan.MatchesTarget(target) && plan.MatchesTarget(SingleReadTarget(identity)), "same opaque identity did not match");
            Check(!plan.MatchesTarget(SingleReadTarget(new SingleReadPoisonIdentity())), "different opaque identity matched");
            Check(!plan.MatchesTarget(null) && !plan.MatchesTarget(SingleReadTarget(identity, complete: false)) &&
                !plan.MatchesTarget(SingleReadTarget(identity, bios: "P05ACJ")) &&
                !plan.MatchesTarget(SingleReadTarget(identity, methodName: "OtherMethod")),
                "opaque identity bypassed fresh scope validation");
        });

        Add("single read plan freezes only a detached copy of the existing synthetic request", () =>
        {
            var plan = SingleReadPlanCreate(SingleReadTarget(new object()));
            byte[] original = BoundChannelRequest();
            WsabiWmiMethodRequest request;
            Check(BinderCreate().TryWrapFrame(original, out request), "existing synthetic frame was rejected");
            WsabiWmiMethodRequest first, second;
            Check(plan.TryFreezeRequest(request, out first), "valid request could not be frozen");
            Check(plan.TryFreezeRequest(request, out second), "second detached request could not be frozen");
            Check(!ReferenceEquals(first, request) && !ReferenceEquals(first, second), "freezing reused a request envelope");
            Equal((uint)1, first.ObservedMethodId); Equal((ushort)0x34, first.FirmwareCommand);
            Check(first.Frame.SequenceEqual(original) && second.Frame.SequenceEqual(original), "freezing changed the synthetic frame");
            original[5] ^= 0xff;
            byte[] externalFrame = request.Frame; externalFrame[6] ^= 0xff;
            var arguments = (IReadOnlyDictionary<string, object>)first.Arguments["inData"];
            ((byte[])arguments["Bytes"])[7] ^= 0xff;
            byte[] firstView = first.Frame; firstView[8] ^= 0xff;
            Check(first.Frame.SequenceEqual(BoundChannelRequest()) && second.Frame.SequenceEqual(BoundChannelRequest()) &&
                request.Frame.SequenceEqual(BoundChannelRequest()), "caller array or argument mutation changed a frozen request");
            Check(!first.CanInvokeMethods && !first.CanReadHardware && !first.CanWriteHardware,
                "frozen bytes became a hardware command authorization");
        });

        Add("single read plan rejects null metadata id header reserved byte and command inconsistencies while clearing output", () =>
        {
            var plan = SingleReadPlanCreate(SingleReadTarget(new object()));
            var mismatchedId = new WsabiWmiMethodRequest(2, 0x34, BoundChannelRequest());
            var malformed = new[] { BoundChannelRequest(), BoundChannelRequest(), BoundChannelRequest(), BoundChannelRequest() };
            malformed[0][0] ^= 0xff; malformed[1][1] ^= 0xff; malformed[2][4] = 1;
            malformed[3][2] ^= 1; // The frame no longer agrees with its supplied 0x34 envelope.
            var requests = new WsabiWmiMethodRequest[]
            {
                null, mismatchedId,
                new WsabiWmiMethodRequest(1, 0x34, malformed[0]), new WsabiWmiMethodRequest(1, 0x34, malformed[1]),
                new WsabiWmiMethodRequest(1, 0x34, malformed[2]), new WsabiWmiMethodRequest(1, 0x34, malformed[3])
            };
            foreach (var request in requests)
            {
                WsabiWmiMethodRequest frozen = mismatchedId;
                Check(!plan.TryFreezeRequest(request, out frozen) && frozen == null, "invalid request retained an output envelope");
            }
        });
    }

    private static WsabiWmiSingleReadTarget SingleReadTarget(object identity, string model = "940X3G/930X3G",
        string bios = "P05ACJ.128.140819.dg", bool windows10X64 = true, string namespaceName = @"root\WMI",
        string className = "WmiAcpiMethod", string methodName = "CallSabiFunction", bool complete = true,
        int instanceCount = 1, bool? active = true)
        => new WsabiWmiSingleReadTarget(model, bios, windows10X64, namespaceName, className, methodName,
            complete, instanceCount, active, identity);

    private static WsabiWmiSingleReadPlan SingleReadPlanCreate(WsabiWmiSingleReadTarget target,
        WsabiWmiContractMetadataReport metadata = null)
    {
        WsabiWmiSingleReadPlan plan; WsabiWmiSingleReadPlanIssue issue;
        Check(WsabiWmiSingleReadPlan.TryCreate(WsabiWmiReadTrialVariant.SingleReadWithoutHandshake,
            target, metadata ?? BinderCompleteMetadata(), out plan, out issue), "detached test plan could not be created");
        Equal(WsabiWmiSingleReadPlanIssue.None, issue); Check(plan != null, "successful plan was null");
        return plan;
    }

    private static void SingleReadPlanRejected(WsabiWmiSingleReadTarget target, WsabiWmiSingleReadPlanIssue expected,
        WsabiWmiReadTrialVariant variant = WsabiWmiReadTrialVariant.SingleReadWithoutHandshake)
    {
        var plan = SingleReadPlanCreate(SingleReadTarget(new object()));
        WsabiWmiSingleReadPlanIssue issue;
        Check(!WsabiWmiSingleReadPlan.TryCreate(variant, target, BinderCompleteMetadata(), out plan, out issue) && plan == null,
            "invalid detached scope retained a plan");
        Equal(expected, issue);
    }

    private static WsabiWmiContractMetadataReport SingleReadMetadata(WsabiWmiParameterMetadata input,
        WsabiWmiParameterMetadata output, WsabiWmiMetadataStatus status = WsabiWmiMetadataStatus.Complete,
        WsabiWmiMetadataStatus bufferStatus = WsabiWmiMetadataStatus.Complete)
        => new WsabiWmiContractMetadataReport(WsabiWmiContractMethodMetadata.FromParameters(status,
            WsabiWmiGuidMatch.MatchesPublicCandidate, 1, true, input, output),
            new WsabiWmiContractBufferMetadata(bufferStatus, true));

    private static void SingleReadMetadataRejected(WsabiWmiSingleReadTarget target, WsabiWmiContractMetadataReport metadata)
    {
        var plan = SingleReadPlanCreate(target);
        WsabiWmiSingleReadPlanIssue issue;
        Check(!WsabiWmiSingleReadPlan.TryCreate(WsabiWmiReadTrialVariant.SingleReadWithoutHandshake,
            target, metadata, out plan, out issue) && plan == null, "invalid metadata retained a plan");
        Equal(WsabiWmiSingleReadPlanIssue.MetadataMismatch, issue);
    }

    private sealed class SingleReadPoisonIdentity
    {
        public override bool Equals(object value) => throw new InvalidOperationException("Opaque identity equality must remain unused.");
        public override int GetHashCode() => throw new InvalidOperationException("Opaque identity hashing must remain unused.");
        public override string ToString() => throw new InvalidOperationException("Opaque identity text must remain unused.");
    }
}
