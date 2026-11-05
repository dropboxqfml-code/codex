using System;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum AcpiFieldChannelStatus { NotInspected, ObservedDeclarations, Partial, LimitExceeded }
    public enum AcpiFieldWidthAssessment
    {
        NotObserved, Matches21ByteFrame, DoesNotMatch21ByteFrame, MultipleCandidates, Mixed, Unknown
    }
    public enum AcpiRegionDefinitionRelation
    {
        NotObserved, SameObservedDefinition, DifferentObservedDefinitions, Mixed, Unknown
    }
    [Flags]
    public enum AcpiStoreSourceKinds { None = 0, Arg0 = 1, Arg1 = 2, Arg2 = 4, Literal = 8, Other = 16 }

    // Declaration categories and syntactic input roles only. Raw field widths,
    // names, region identities, offsets, addresses and operand values stay private.
    public sealed class AcpiFieldChannelReport
    {
        public AcpiFieldChannelStatus Status { get; }
        public int? RootFieldStoreSites { get; }
        public int? RootArg2FieldStoreSites { get; }
        public AcpiStoreSourceKinds? RootFieldStoreSourceKinds { get; }
        public AcpiAddressSpaceKinds? RootArg2FieldSpaces { get; }
        public AcpiAddressSpaceKinds? RootReturnFieldSpaces { get; }
        public AcpiFieldWidthAssessment RootArg2FieldWidth { get; }
        public AcpiFieldWidthAssessment RootReturnFieldWidth { get; }
        public int ParsedHelpers { get; }
        public AcpiAddressSpaceKinds? ParsedHelperFieldStoreSpaces { get; }
        public AcpiRegionDefinitionRelation Arg2FieldAndHelperStoreRegions { get; }
        public AcpiRegionDefinitionRelation ReturnFieldAndHelperStoreRegions { get; }
        public bool CanInvokeMethods => false;
        public bool CanWriteHardware => false;

        internal AcpiFieldChannelReport(AcpiFieldChannelStatus status = AcpiFieldChannelStatus.NotInspected,
            int? rootFieldStoreSites = null, int? rootArg2FieldStoreSites = null,
            AcpiStoreSourceKinds? rootFieldStoreSourceKinds = null,
            AcpiAddressSpaceKinds? rootArg2FieldSpaces = null, AcpiAddressSpaceKinds? rootReturnFieldSpaces = null,
            AcpiFieldWidthAssessment rootArg2FieldWidth = AcpiFieldWidthAssessment.Unknown,
            AcpiFieldWidthAssessment rootReturnFieldWidth = AcpiFieldWidthAssessment.Unknown,
            int parsedHelpers = 0, AcpiAddressSpaceKinds? parsedHelperFieldStoreSpaces = null,
            AcpiRegionDefinitionRelation arg2FieldAndHelperStoreRegions = AcpiRegionDefinitionRelation.Unknown,
            AcpiRegionDefinitionRelation returnFieldAndHelperStoreRegions = AcpiRegionDefinitionRelation.Unknown)
        {
            Status = status; RootFieldStoreSites = rootFieldStoreSites; RootArg2FieldStoreSites = rootArg2FieldStoreSites;
            RootFieldStoreSourceKinds = rootFieldStoreSourceKinds; RootArg2FieldSpaces = rootArg2FieldSpaces;
            RootReturnFieldSpaces = rootReturnFieldSpaces; RootArg2FieldWidth = rootArg2FieldWidth;
            RootReturnFieldWidth = rootReturnFieldWidth; ParsedHelpers = parsedHelpers;
            ParsedHelperFieldStoreSpaces = parsedHelperFieldStoreSpaces;
            Arg2FieldAndHelperStoreRegions = arg2FieldAndHelperStoreRegions;
            ReturnFieldAndHelperStoreRegions = returnFieldAndHelperStoreRegions;
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("Field 통로 선언·입력 역할 요약: " + Status);
            text.AppendLine("후보에서 관측한 Field Store 구문 수 / 직접 Arg2 원천 구문 수: " + Count(RootFieldStoreSites) + " / " + Count(RootArg2FieldStoreSites));
            text.AppendLine("후보 Field Store 구문의 직접 원천 종류: " + (RootFieldStoreSourceKinds.HasValue ? RootFieldStoreSourceKinds.Value.ToString() : "미확정"));
            text.AppendLine("후보의 직접 Arg2 Store 대상 Field 주소 공간 종류: " + Space(RootArg2FieldSpaces));
            text.AppendLine("후보의 직접 Return 대상 Field 주소 공간 종류: " + Space(RootReturnFieldSpaces));
            text.AppendLine("후보 Arg2 Store 대상 Field의 21바이트 프레임 선언 폭 분류: " + RootArg2FieldWidth);
            text.AppendLine("후보 Return 대상 Field의 21바이트 프레임 선언 폭 분류: " + RootReturnFieldWidth);
            text.AppendLine("Field 통로를 검사한 완전 구문 해석 보조 본문 수: " + ParsedHelpers);
            text.AppendLine("해석된 보조 본문의 Field Store 대상 주소 공간 종류: " + Space(ParsedHelperFieldStoreSpaces));
            text.AppendLine("후보 Arg2 Field와 보조 Store Field의 관측 Region 선언 관계: " + Arg2FieldAndHelperStoreRegions);
            text.AppendLine("후보 Return Field와 보조 Store Field의 관측 Region 선언 관계: " + ReturnFieldAndHelperStoreRegions);
            text.AppendLine("구문 수는 발생 횟수이며 폭 후보는 서로 다른 관측 Field 정의 수로 구분합니다. 일부 대상의 일치를 단일 일치로 바꾸지 않습니다.");
            text.AppendLine("폭 일치는 선언 폭 비교뿐입니다. 바이트 배치·변환·입력 보존·명령 의미·실행이나 실제 FF 발생 위치를 보장하지 않습니다.");
            text.AppendLine("Region 관계는 관측 선언의 동일성만 비교합니다. 물리 주소·영역 겹침·별칭·실제 I/O·SMI 여부를 비교하거나 추론하지 않습니다.");
            text.AppendLine("Arg0·Arg1·Arg2는 후보 본문의 직접 인수 구문입니다. 보조 인수·변수·별칭의 값이나 실행 순서를 평가하지 않습니다.");
            text.AppendLine("부분 관측은 해석한 본문과 관측 선언 범위입니다. 주소·오프셋·폭 원문·필드 값은 보고하지 않으며 실제 영역을 읽거나 쓰지 않습니다.");
            return text.ToString();
        }

        private static string Count(int? value) => value.HasValue ? value.Value.ToString() : "미확정";
        private static string Space(AcpiAddressSpaceKinds? value) => value.HasValue ? value.Value.ToString() : "미확정";
    }
}
