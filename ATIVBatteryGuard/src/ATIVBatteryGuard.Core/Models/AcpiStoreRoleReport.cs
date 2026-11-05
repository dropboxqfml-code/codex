using System;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum AcpiStoreRoleStatus { NotInspected, ObservedSyntax, Partial, LimitExceeded }
    [Flags]
    public enum AcpiLiteralSyntaxKinds { None = 0, Integer = 1, String = 2, Buffer = 4, Package = 8 }
    public enum AcpiDefinitionRelation { NotObserved, SameObservedDefinition, DifferentObservedDefinitions, Mixed, Unknown }
    public enum AcpiRootLayoutStatus { NotInspected, SingleDirectList, NotObserved, MultipleCandidates, Unknown, LimitExceeded }
    public enum AcpiStatementOrder { NotObserved, BeforeInSameList, AfterInSameList, MultipleCandidates, Unknown }

    // Static declaration and source-layout categories only. No operand values,
    // names, declaration identities, byte offsets or firmware data are retained.
    public sealed class AcpiStoreRoleReport
    {
        public AcpiStoreRoleStatus Status { get; }
        public int? RootLiteralStoreSites { get; }
        public AcpiLiteralSyntaxKinds? RootLiteralSyntax { get; }
        public AcpiAddressSpaceKinds? RootLiteralFieldSpaces { get; }
        public AcpiFieldWidthAssessment RootLiteralFieldWidth { get; }
        public int ParsedHelpers { get; }
        public AcpiDefinitionRelation LiteralAndArg2Fields { get; }
        public AcpiDefinitionRelation LiteralAndReturnFields { get; }
        public AcpiDefinitionRelation LiteralAndHelperStoreFields { get; }
        public AcpiRegionDefinitionRelation LiteralAndArg2Regions { get; }
        public AcpiRegionDefinitionRelation LiteralAndReturnRegions { get; }
        public AcpiRegionDefinitionRelation LiteralAndHelperStoreRegions { get; }
        public AcpiRootLayoutStatus LayoutStatus { get; }
        public AcpiStatementOrder Arg2StoreAndLiteralStoreOrder { get; }
        public AcpiStatementOrder Arg2StoreAndHelperCallOrder { get; }
        public AcpiStatementOrder LiteralStoreAndHelperCallOrder { get; }
        public AcpiStatementOrder HelperCallAndReturnOrder { get; }
        public bool CanInvokeMethods => false;
        public bool CanWriteHardware => false;

        internal AcpiStoreRoleReport(AcpiStoreRoleStatus status = AcpiStoreRoleStatus.NotInspected,
            int? rootLiteralStoreSites = null, AcpiLiteralSyntaxKinds? rootLiteralSyntax = null,
            AcpiAddressSpaceKinds? rootLiteralFieldSpaces = null,
            AcpiFieldWidthAssessment rootLiteralFieldWidth = AcpiFieldWidthAssessment.Unknown,
            int parsedHelpers = 0,
            AcpiDefinitionRelation literalAndArg2Fields = AcpiDefinitionRelation.Unknown,
            AcpiDefinitionRelation literalAndReturnFields = AcpiDefinitionRelation.Unknown,
            AcpiDefinitionRelation literalAndHelperStoreFields = AcpiDefinitionRelation.Unknown,
            AcpiRegionDefinitionRelation literalAndArg2Regions = AcpiRegionDefinitionRelation.Unknown,
            AcpiRegionDefinitionRelation literalAndReturnRegions = AcpiRegionDefinitionRelation.Unknown,
            AcpiRegionDefinitionRelation literalAndHelperStoreRegions = AcpiRegionDefinitionRelation.Unknown,
            AcpiRootLayoutStatus layoutStatus = AcpiRootLayoutStatus.NotInspected,
            AcpiStatementOrder arg2StoreAndLiteralStoreOrder = AcpiStatementOrder.Unknown,
            AcpiStatementOrder arg2StoreAndHelperCallOrder = AcpiStatementOrder.Unknown,
            AcpiStatementOrder literalStoreAndHelperCallOrder = AcpiStatementOrder.Unknown,
            AcpiStatementOrder helperCallAndReturnOrder = AcpiStatementOrder.Unknown)
        {
            Status = status; RootLiteralStoreSites = rootLiteralStoreSites; RootLiteralSyntax = rootLiteralSyntax;
            RootLiteralFieldSpaces = rootLiteralFieldSpaces; RootLiteralFieldWidth = rootLiteralFieldWidth;
            ParsedHelpers = parsedHelpers; LiteralAndArg2Fields = literalAndArg2Fields;
            LiteralAndReturnFields = literalAndReturnFields; LiteralAndHelperStoreFields = literalAndHelperStoreFields;
            LiteralAndArg2Regions = literalAndArg2Regions; LiteralAndReturnRegions = literalAndReturnRegions;
            LiteralAndHelperStoreRegions = literalAndHelperStoreRegions; LayoutStatus = layoutStatus;
            Arg2StoreAndLiteralStoreOrder = arg2StoreAndLiteralStoreOrder;
            Arg2StoreAndHelperCallOrder = arg2StoreAndHelperCallOrder;
            LiteralStoreAndHelperCallOrder = literalStoreAndHelperCallOrder;
            HelperCallAndReturnOrder = helperCallAndReturnOrder;
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("Literal Store 역할·직접 구문 배치 요약: " + Status);
            text.AppendLine("후보의 직접 literal 원천 Store 구문 수 / literal 구문 종류: " +
                (RootLiteralStoreSites.HasValue ? RootLiteralStoreSites.Value.ToString() : "미확정") + " / " +
                (RootLiteralSyntax.HasValue ? RootLiteralSyntax.Value.ToString() : "미확정"));
            text.AppendLine("후보 literal Store 대상 Field 주소 공간 종류: " +
                (RootLiteralFieldSpaces.HasValue ? RootLiteralFieldSpaces.Value.ToString() : "미확정"));
            text.AppendLine("후보 literal Store 대상 Field의 21바이트 프레임 선언 폭 분류: " + RootLiteralFieldWidth);
            text.AppendLine("literal 대상과 Arg2 저장 대상의 관측 Field / Region 선언 관계: " + LiteralAndArg2Fields + " / " + LiteralAndArg2Regions);
            text.AppendLine("literal 대상과 직접 반환 대상의 관측 Field / Region 선언 관계: " + LiteralAndReturnFields + " / " + LiteralAndReturnRegions);
            text.AppendLine("literal 역할과 비교한 완전 구문 해석 보조 본문 수: " + ParsedHelpers);
            text.AppendLine("literal 대상과 보조 Store 대상의 관측 Field / Region 선언 관계: " + LiteralAndHelperStoreFields + " / " + LiteralAndHelperStoreRegions);
            text.AppendLine("후보의 단일 직접 구문 목록 배치: " + LayoutStatus);
            text.AppendLine("Arg2 Store와 literal Store의 구문상 앞뒤: " + Arg2StoreAndLiteralStoreOrder);
            text.AppendLine("Arg2 Store와 보조 호출의 구문상 앞뒤: " + Arg2StoreAndHelperCallOrder);
            text.AppendLine("literal Store와 보조 호출의 구문상 앞뒤: " + LiteralStoreAndHelperCallOrder);
            text.AppendLine("보조 호출과 Return의 구문상 앞뒤: " + HelperCallAndReturnOrder);
            text.AppendLine("literal 구문 수는 비Field·미분류·비이름 대상도 포함합니다. 정수·문자열·Buffer·Package의 원문 값은 보고하지 않습니다.");
            text.AppendLine("Field·Region 관계는 관측 선언만 비교합니다. 같은 값·물리 주소·영역 겹침·초기화·트리거·SMI·FF 원인을 뜻하지 않습니다.");
            text.AppendLine("앞뒤는 각 역할이 하나씩 있는 같은 직접 구문 목록의 배치입니다. 실행 순서·분기·값 전파나 보조 인수 값을 평가하지 않습니다.");
            text.AppendLine("분기·반복·중첩·복수 후보·미해석·한계 초과는 단일 배치로 만들지 않습니다. 실제 영역 접근·OEM/AML 실행·하드웨어 쓰기는 없습니다.");
            return text.ToString();
        }
    }
}
