using System;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum AcpiRoutingStatus { Complete, Partial, InvalidTable, LimitExceeded }
    public enum AcpiMethodSyntaxStatus { NotObserved, Ambiguous, WrongArgumentCount, UnsupportedSyntax, Parsed }

    // Static syntax evidence only. No table bytes, names, addresses or OEM IDs
    // cross this boundary. Nothing here permits evaluation or a hardware call.
    public sealed class AcpiWmiRoutingReport
    {
        public AcpiRoutingStatus Status { get; }
        public int MatchingDescriptors { get; }
        public int MatchingMethods { get; }
        public int? MethodArgumentCount { get; }
        public AcpiMethodSyntaxStatus MethodSyntax { get; }
        public bool? DirectMethodIdOneComparison { get; }
        public bool? DirectInputLength21Comparison { get; }
        public bool? LiteralFfReturn { get; }
        public AcpiMethodFlowReport Flow { get; }
        public AcpiObjectReferenceReport ObjectReferences { get; }
        public AcpiFieldChannelReport FieldChannel { get; }
        public AcpiStoreRoleReport StoreRoles { get; }
        public bool CanInvokeMethods => false;
        public bool CanWriteHardware => false;

        internal AcpiWmiRoutingReport(AcpiRoutingStatus status, int descriptors = 0, int methods = 0,
            int? arguments = null, bool? idOne = null, bool? input21 = null, bool? ff = null,
            AcpiMethodSyntaxStatus syntax = AcpiMethodSyntaxStatus.NotObserved, AcpiMethodFlowReport flow = null,
            AcpiObjectReferenceReport objectReferences = null, AcpiFieldChannelReport fieldChannel = null,
            AcpiStoreRoleReport storeRoles = null)
        {
            Status = status; MatchingDescriptors = descriptors; MatchingMethods = methods;
            MethodArgumentCount = arguments; DirectMethodIdOneComparison = idOne;
            DirectInputLength21Comparison = input21; LiteralFfReturn = ff;
            MethodSyntax = syntax;
            Flow = flow ?? new AcpiMethodFlowReport();
            ObjectReferences = objectReferences ?? new AcpiObjectReferenceReport();
            FieldChannel = fieldChannel ?? new AcpiFieldChannelReport();
            StoreRoles = storeRoles ?? new AcpiStoreRoleReport();
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("테이블 정의 구문 탐색: " + Status);
            text.AppendLine("관측한 알려진 SABI WMI 설명자 수: " + MatchingDescriptors);
            text.AppendLine("관측한 대응 메서드 정의 수: " + MatchingMethods);
            text.AppendLine("관측한 단일 후보 메서드 인수 수: " + (MethodArgumentCount.HasValue ? MethodArgumentCount.Value.ToString() : "미확정"));
            text.AppendLine("후보 메서드 본문 구문 해석: " + MethodSyntax);
            text.AppendLine("메서드 본문의 Arg1과 상수1 동등 비교 구문: " + Observed(DirectMethodIdOneComparison));
            text.AppendLine("메서드 본문의 SizeOf(Arg2)와 상수21 동등 비교 구문: " + Observed(DirectInputLength21Comparison));
            text.AppendLine("메서드 본문의 상수FF/FF프레임 반환 구문: " + Observed(LiteralFfReturn));
            text.AppendLine("구문 관측은 해당 분기의 실행·배터리 명령 지원·FF 의미를 증명하지 않습니다.");
            text.AppendLine("일부 해석·미확정·미관측은 정의나 기능 부재 판정이 아닙니다.");
            text.AppendLine("Complete도 한 테이블의 지원 구문 범위이며 전체 펌웨어 해석이나 대상 유일성 보장이 아닙니다.");
            text.Append(Flow.ToDisplayText());
            text.Append(ObjectReferences.ToDisplayText());
            text.Append(FieldChannel.ToDisplayText());
            text.Append(StoreRoles.ToDisplayText());
            return text.ToString();
        }

        private static string Observed(bool? value) => value.HasValue
            ? (value.Value ? "관측" : "지원한 구문 범위에서 미관측") : "해석 불가 또는 미실시";
    }
}
