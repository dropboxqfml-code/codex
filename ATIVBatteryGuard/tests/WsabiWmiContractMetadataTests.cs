using System;
using ATIVBatteryGuard.Core.Models;
using ATIVBatteryGuard.Core.Services;

internal static partial class Program
{
    private static void RegisterWsabiWmiContractMetadataTests()
    {
        Add("WMI contract metadata compares GUIDs without retaining actual values", () =>
        {
            Equal(WsabiWmiGuidMatch.Missing, WsabiWmiContractMetadataPolicy.CompareGuid(null));
            foreach (string value in new[] {
                WsabiWmiContractMetadataPolicy.PublicCandidateGuid,
                WsabiWmiContractMetadataPolicy.PublicCandidateGuid.ToLowerInvariant(),
                "{" + WsabiWmiContractMetadataPolicy.PublicCandidateGuid + "}",
                WsabiWmiContractMetadataPolicy.PublicCandidateGuid.Replace("-", "") })
                Equal(WsabiWmiGuidMatch.MatchesPublicCandidate, WsabiWmiContractMetadataPolicy.CompareGuid(value));
            Equal(WsabiWmiGuidMatch.Other, WsabiWmiContractMetadataPolicy.CompareGuid("00000000-0000-0000-0000-000000000000"));
            foreach (object value in new object[] { "", new object(), new string('a', 39), 1, new[] { WsabiWmiContractMetadataPolicy.PublicCandidateGuid }, @"C:\Users\PrivateName" })
                Equal(WsabiWmiGuidMatch.Invalid, WsabiWmiContractMetadataPolicy.CompareGuid(value));
            Check(!WsabiWmiContractMetadataPolicy.CanInvokeMethods, "metadata policy permits invocation");
        });
        Add("WMI contract method number and embedded class normalization are strict", () =>
        {
            Equal<uint?>(0u, WsabiWmiContractMetadataPolicy.NormalizeMethodId(0));
            Equal<uint?>(7u, WsabiWmiContractMetadataPolicy.NormalizeMethodId(7));
            Equal<uint?>(uint.MaxValue, WsabiWmiContractMetadataPolicy.NormalizeMethodId(uint.MaxValue));
            Equal<uint?>((uint)int.MaxValue, WsabiWmiContractMetadataPolicy.NormalizeMethodId(int.MaxValue));
            foreach (object value in new object[] { null, DBNull.Value, -1, 0L, 1UL, (ushort)1, "1", true, 1.0, new object() })
                Equal<uint?>(null, WsabiWmiContractMetadataPolicy.NormalizeMethodId(value));
            Equal<bool?>(true, WsabiWmiContractMetadataPolicy.NormalizeEmbeddedClass("DataBuffer"));
            Equal<bool?>(false, WsabiWmiContractMetadataPolicy.NormalizeEmbeddedClass("Other"));
            Equal<bool?>(true, WsabiWmiContractMetadataPolicy.NormalizeEmbeddedClass("databuffer"));
            Equal<bool?>(true, WsabiWmiContractMetadataPolicy.NormalizeEmbeddedClass("dAtAbUfFeR"));
            Equal<bool?>(false, WsabiWmiContractMetadataPolicy.NormalizeEmbeddedClass("DataBuffer "));
            Equal<bool?>(false, WsabiWmiContractMetadataPolicy.NormalizeEmbeddedClass(@"root\WMI:DataBuffer"));
            foreach (object value in new object[] { null, DBNull.Value, 1, new string('x', 97), new[] { "DataBuffer" } })
                Equal<bool?>(null, WsabiWmiContractMetadataPolicy.NormalizeEmbeddedClass(value));
        });
        Add("WMI metadata failure states remove all earlier method and buffer facts", () =>
        {
            foreach (WsabiWmiMetadataStatus status in Enum.GetValues(typeof(WsabiWmiMetadataStatus)))
            {
                var method = new WsabiWmiContractMethodMetadata(status, WsabiWmiGuidMatch.MatchesPublicCandidate, 7, true, true, true);
                var buffer = new WsabiWmiContractBufferMetadata(status, true);
                bool observed = status == WsabiWmiMetadataStatus.Complete || status == WsabiWmiMetadataStatus.Partial;
                Equal(observed ? WsabiWmiGuidMatch.MatchesPublicCandidate : WsabiWmiGuidMatch.Missing, method.GuidMatch);
                Equal<uint?>(observed ? 7u : (uint?)null, method.MethodId);
                Equal<bool?>(observed ? true : (bool?)null, method.MethodFound);
                Equal<bool?>(observed ? true : (bool?)null, method.InputIsDataBuffer);
                Equal<bool?>(observed ? true : (bool?)null, method.OutputIsDataBuffer);
                Equal<bool?>(observed ? true : (bool?)null, buffer.BytesIsUInt8Array);
            }
            Equal(WsabiWmiMetadataStatus.Unavailable, new WsabiWmiContractMethodMetadata((WsabiWmiMetadataStatus)999, methodId: 7).Status);
            Equal(WsabiWmiMetadataStatus.Unavailable, new WsabiWmiContractBufferMetadata((WsabiWmiMetadataStatus)999, true).Status);
            Equal(WsabiWmiMetadataStatus.Unavailable, WsabiWmiContractMetadataReport.Failure(WsabiWmiMetadataStatus.Complete).MethodMetadata.Status);
        });
        Add("WMI metadata distinguishes incomplete fields from observed nonmatching definitions", () =>
        {
            var incomplete = new WsabiWmiContractMethodMetadata(WsabiWmiMetadataStatus.Complete);
            Equal(WsabiWmiMetadataStatus.Partial, incomplete.Status);
            Equal(WsabiWmiMetadataStatus.Partial, new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete).Status);
            var mismatch = new WsabiWmiContractMethodMetadata(WsabiWmiMetadataStatus.Complete,
                WsabiWmiGuidMatch.Other, 0, false, false, true);
            Equal(WsabiWmiMetadataStatus.Complete, mismatch.Status);
            Equal<uint?>(0, mismatch.MethodId);
            Equal<bool?>(false, mismatch.InputIsDataBuffer);
            Equal(WsabiWmiMetadataStatus.Complete, new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, false).Status);
            var missingMethod = new WsabiWmiContractMethodMetadata(WsabiWmiMetadataStatus.Complete,
                WsabiWmiGuidMatch.MatchesPublicCandidate, 9, true, true, false);
            Equal(WsabiWmiMetadataStatus.Partial, missingMethod.Status);
            Equal<uint?>(null, missingMethod.MethodId);
            Equal<bool?>(null, missingMethod.InputIsDataBuffer);
            var invalidGuid = new WsabiWmiContractMethodMetadata(WsabiWmiMetadataStatus.Complete,
                (WsabiWmiGuidMatch)999, 0, true, true, true);
            Equal(WsabiWmiGuidMatch.Invalid, invalidGuid.GuidMatch);
            Equal(WsabiWmiMetadataStatus.Partial, invalidGuid.Status);
        });
        Add("WMI metadata class outcomes remain independent and never enable control", () =>
        {
            foreach (WsabiWmiMetadataStatus methodStatus in Enum.GetValues(typeof(WsabiWmiMetadataStatus)))
            foreach (WsabiWmiMetadataStatus bufferStatus in Enum.GetValues(typeof(WsabiWmiMetadataStatus)))
            {
                var report = new WsabiWmiContractMetadataReport(
                    new WsabiWmiContractMethodMetadata(methodStatus, WsabiWmiGuidMatch.MatchesPublicCandidate, 1, true, true, true),
                    new WsabiWmiContractBufferMetadata(bufferStatus, true));
                Equal(methodStatus, report.MethodMetadata.Status);
                Equal(bufferStatus, report.BufferMetadata.Status);
                string text = report.ToDisplayText();
                Check(text.Contains(WsabiWmiContractMetadataReport.StatusText(methodStatus)) &&
                    text.Contains(WsabiWmiContractMetadataReport.StatusText(bufferStatus)), "independent metadata status omitted");
                Check(!report.CanInvokeMethods && !report.CanReadHardware && !report.CanWriteHardware, "class metadata enabled transport");
                Check(text.Contains("실제 충전 제어: 미지원") && text.Contains("메서드 실행 권한"), "readiness misrepresented");
            }
        });
        Add("WMI metadata reports no actual GUID names paths or provider text", () =>
        {
            string actual = "00000000-0000-0000-0000-000000000000";
            var report = new WsabiWmiContractMetadataReport(new WsabiWmiContractMethodMetadata(
                WsabiWmiMetadataStatus.Complete, WsabiWmiContractMetadataPolicy.CompareGuid(actual),
                uint.MaxValue, true, false, true), new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, false));
            string text = report.ToDisplayText();
            Check(!text.Contains(actual) && !text.Contains(WsabiWmiContractMetadataPolicy.PublicCandidateGuid) &&
                !text.Contains(@"C:\Users") && !text.Contains("PrivateName"), "raw metadata retained");
            Check(text.Contains("4294967295 (0xFFFFFFFF)") && text.Contains("True") && text.Contains("False"), "bounded values lost");
            Equal(WsabiWmiMetadataStatus.NotChecked, new WsabiWmiContractMetadataReport().MethodMetadata.Status);
            Equal(WsabiWmiMetadataStatus.NotChecked, new WsabiWmiContractMetadataReport().BufferMetadata.Status);
            foreach (var property in typeof(WsabiWmiContractMethodMetadata).GetProperties())
                Check(!property.CanWrite, "method metadata publicly mutable");
            foreach (var property in typeof(WsabiWmiContractBufferMetadata).GetProperties())
                Check(!property.CanWrite, "buffer metadata publicly mutable");
        });
        Add("observed GUID method one and byte array preserve unresolved input output bindings", () =>
        {
            // Normalized facts from the owner's output; no raw report or GUID.
            var report = new WsabiWmiContractMetadataReport(new WsabiWmiContractMethodMetadata(
                WsabiWmiMetadataStatus.Partial, WsabiWmiGuidMatch.MatchesPublicCandidate, 1,
                null, null, true), new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, true));
            Equal<uint?>(1, report.MethodMetadata.MethodId);
            Equal<bool?>(null, report.MethodMetadata.InputIsDataBuffer);
            Equal<bool?>(null, report.MethodMetadata.OutputIsDataBuffer);
            Equal(WsabiWmiParameterShape.NotChecked, report.MethodMetadata.InputParameter.Shape);
            Equal(WsabiWmiContractBindingStatus.GuidMethodMatchedParametersUnresolved, report.BindingStatus);
            Check(!report.CanInvokeMethods && !report.CanReadHardware && !report.CanWriteHardware,
                "observed metadata enabled OEM calls");
        });
        Add("metadata binding accepts CIMTYPE evidence without choosing an OS dispatch mapping", () =>
        {
            var input = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, null, "object:DataBuffer");
            var output = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, "DataBuffer", "object");
            foreach (uint id in new uint[] { 0, 1, 65, uint.MaxValue })
            {
                var report = new WsabiWmiContractMetadataReport(WsabiWmiContractMethodMetadata.FromParameters(
                    WsabiWmiMetadataStatus.Complete, WsabiWmiGuidMatch.MatchesPublicCandidate, id, true,
                    input, output), new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, true));
                Equal<uint?>(id, report.MethodMetadata.MethodId);
                Equal(WsabiWmiMetadataStatus.Complete, report.MethodMetadata.Status);
                Equal(WsabiWmiContractBindingStatus.MetadataShapeMatched, report.BindingStatus);
                Equal(WsabiWmiQualifierMatch.Missing, report.MethodMetadata.InputParameter.EmbeddedInstanceMatch);
                Equal(WsabiWmiQualifierMatch.UnspecifiedObject, report.MethodMetadata.OutputParameter.CimTypeMatch);
                Check(!report.CanInvokeMethods && !report.CanReadHardware && !report.CanWriteHardware,
                    "shape match or dispatch number enabled hardware");
            }
        });
        Add("metadata conflicts partial outcomes and missing dispatch cannot establish full shape binding", () =>
        {
            var match = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, null, "object:DataBuffer");
            var conflict = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, "OtherBuffer", "object:DataBuffer");
            var method = WsabiWmiContractMethodMetadata.FromParameters(WsabiWmiMetadataStatus.Complete,
                WsabiWmiGuidMatch.MatchesPublicCandidate, 1, true, match, conflict);
            var report = new WsabiWmiContractMetadataReport(method,
                new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, true));
            Equal(WsabiWmiMetadataStatus.Partial, method.Status);
            Equal<bool?>(null, method.OutputIsDataBuffer);
            Equal(WsabiWmiContractBindingStatus.GuidMethodMatchedParametersUnresolved, report.BindingStatus);
            Check(report.ToDisplayText().Contains("두 qualifier 충돌") && !report.ToDisplayText().Contains("OtherBuffer"),
                "conflict lost or raw class exposed");
            foreach (var status in new[] { WsabiWmiMetadataStatus.Partial, WsabiWmiMetadataStatus.AccessDenied,
                WsabiWmiMetadataStatus.TimedOut, WsabiWmiMetadataStatus.ClassNotFound })
            {
                var partialBuffer = new WsabiWmiContractMetadataReport(WsabiWmiContractMethodMetadata.FromParameters(
                    WsabiWmiMetadataStatus.Complete, WsabiWmiGuidMatch.MatchesPublicCandidate, 1, true,
                    match, match), new WsabiWmiContractBufferMetadata(status, true));
                Equal(WsabiWmiContractBindingStatus.GuidMethodMatchedParametersUnresolved, partialBuffer.BindingStatus);
            }
            var noId = new WsabiWmiContractMetadataReport(WsabiWmiContractMethodMetadata.FromParameters(
                WsabiWmiMetadataStatus.Complete, WsabiWmiGuidMatch.MatchesPublicCandidate, null, true, match, match),
                new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, true));
            Equal(WsabiWmiContractBindingStatus.Unknown, noId.BindingStatus);
        });
        Add("failed or absent method metadata clears detailed qualifier facts without hiding independent buffer", () =>
        {
            var match = WsabiWmiContractMetadataPolicy.InspectParameter(true, true, "DataBuffer", "object:DataBuffer");
            foreach (WsabiWmiMetadataStatus status in Enum.GetValues(typeof(WsabiWmiMetadataStatus)))
            {
                if (status == WsabiWmiMetadataStatus.Complete || status == WsabiWmiMetadataStatus.Partial) continue;
                var method = WsabiWmiContractMethodMetadata.FromParameters(status,
                    WsabiWmiGuidMatch.MatchesPublicCandidate, 1, true, match, match);
                Equal(WsabiWmiParameterShape.NotChecked, method.InputParameter.Shape);
                Equal(WsabiWmiParameterShape.NotChecked, method.OutputParameter.Shape);
                Equal<uint?>(null, method.MethodId);
                Equal<bool?>(null, method.InputIsDataBuffer);
                var report = new WsabiWmiContractMetadataReport(method,
                    new WsabiWmiContractBufferMetadata(WsabiWmiMetadataStatus.Complete, true));
                Equal(WsabiWmiContractBindingStatus.Unknown, report.BindingStatus);
                Equal<bool?>(true, report.BufferMetadata.BytesIsUInt8Array);
            }
            var missingMethod = WsabiWmiContractMethodMetadata.FromParameters(WsabiWmiMetadataStatus.Complete,
                WsabiWmiGuidMatch.MatchesPublicCandidate, 1, false, match, match);
            Equal(WsabiWmiParameterShape.NotChecked, missingMethod.InputParameter.Shape);
            var missing = new WsabiWmiContractMetadataReport(missingMethod);
            Equal(WsabiWmiContractBindingStatus.ObservedDefinitionMismatch, missing.BindingStatus);
            Check(!missing.CanInvokeMethods && !missing.CanWriteHardware, "mismatch enabled control");
        });
    }
}
