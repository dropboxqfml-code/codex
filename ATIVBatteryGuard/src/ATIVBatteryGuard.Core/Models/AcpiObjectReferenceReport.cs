using System;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum AcpiReferenceAnalysisStatus { NotInspected, ClassifiedObservedSyntax, Partial, LimitExceeded }
    [Flags]
    public enum AcpiNamedObjectKinds
    {
        None = 0, Buffer = 1, Integer = 2, String = 4, Package = 8, Mutex = 16,
        Event = 32, OperationRegion = 64, Field = 128, Other = 256, MethodReference = 512
    }
    [Flags]
    public enum AcpiAddressSpaceKinds
    {
        None = 0, SystemMemory = 1, SystemIo = 2, PciConfiguration = 4,
        EmbeddedControl = 8, SmBus = 16, Other = 32, Unknown = 64
    }

    // Declaration syntax and reference occurrences only. No name, address,
    // buffer, value, reference collection or runtime object leaves the reader.
    public sealed class AcpiObjectReferenceReport
    {
        public AcpiReferenceAnalysisStatus Status { get; }
        public int? RootNamedReferences { get; }
        public int? RootClassifiedReferences { get; }
        public AcpiNamedObjectKinds? RootReferencedKinds { get; }
        public AcpiNamedObjectKinds? RootReturnKinds { get; }
        public AcpiNamedObjectKinds? RootArg2StoreKinds { get; }
        public int ParsedHelpers { get; }
        public int? ParsedHelperNamedReferences { get; }
        public int? ParsedHelperClassifiedReferences { get; }
        public AcpiNamedObjectKinds? ParsedHelperReferencedKinds { get; }
        public AcpiNamedObjectKinds? ParsedHelperStoreTargetKinds { get; }
        public AcpiAddressSpaceKinds? ParsedHelperFieldStoreSpaces { get; }
        public bool? RootStoresArg2ToReturnedObject { get; }
        public bool? RootReturnedObjectReferencedByParsedHelper { get; }
        public bool? RootArg2StoreObjectReferencedByParsedHelper { get; }
        public bool CanInvokeMethods => false;
        public bool CanWriteHardware => false;

        internal AcpiObjectReferenceReport(AcpiReferenceAnalysisStatus status = AcpiReferenceAnalysisStatus.NotInspected,
            int? rootNamedReferences = null, int? rootClassifiedReferences = null,
            AcpiNamedObjectKinds? rootReferencedKinds = null, AcpiNamedObjectKinds? rootReturnKinds = null,
            AcpiNamedObjectKinds? rootArg2StoreKinds = null, int parsedHelpers = 0,
            int? parsedHelperNamedReferences = null, int? parsedHelperClassifiedReferences = null,
            AcpiNamedObjectKinds? parsedHelperReferencedKinds = null, AcpiNamedObjectKinds? parsedHelperStoreTargetKinds = null,
            AcpiAddressSpaceKinds? parsedHelperFieldStoreSpaces = null, bool? rootStoresArg2ToReturnedObject = null,
            bool? rootReturnedObjectReferencedByParsedHelper = null, bool? rootArg2StoreObjectReferencedByParsedHelper = null)
        {
            Status = status; RootNamedReferences = rootNamedReferences; RootClassifiedReferences = rootClassifiedReferences;
            RootReferencedKinds = rootReferencedKinds; RootReturnKinds = rootReturnKinds; RootArg2StoreKinds = rootArg2StoreKinds;
            ParsedHelpers = parsedHelpers; ParsedHelperNamedReferences = parsedHelperNamedReferences;
            ParsedHelperClassifiedReferences = parsedHelperClassifiedReferences; ParsedHelperReferencedKinds = parsedHelperReferencedKinds;
            ParsedHelperStoreTargetKinds = parsedHelperStoreTargetKinds; ParsedHelperFieldStoreSpaces = parsedHelperFieldStoreSpaces;
            RootStoresArg2ToReturnedObject = rootStoresArg2ToReturnedObject;
            RootReturnedObjectReferencedByParsedHelper = rootReturnedObjectReferencedByParsedHelper;
            RootArg2StoreObjectReferencedByParsedHelper = rootArg2StoreObjectReferencedByParsedHelper;
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("관측한 이름 객체·참조 관계 분류: " + Status);
            text.AppendLine("후보 본문의 이름 참조 횟수 / 분류된 참조 횟수: " + Count(RootNamedReferences) + " / " + Count(RootClassifiedReferences));
            text.AppendLine("후보 본문에서 분류한 이름 객체 종류: " + Kind(RootReferencedKinds));
            text.AppendLine("후보의 직접 Return 이름 참조에서 분류한 종류: " + Kind(RootReturnKinds));
            text.AppendLine("후보의 직접 Store(Arg2, 이름) 대상에서 분류한 종류: " + Kind(RootArg2StoreKinds));
            text.AppendLine("객체 참조를 검사한 완전 구문 해석 보조 본문 수: " + ParsedHelpers);
            text.AppendLine("해석된 보조 본문의 이름 참조 횟수 / 분류된 참조 횟수: " + Count(ParsedHelperNamedReferences) + " / " + Count(ParsedHelperClassifiedReferences));
            text.AppendLine("해석된 보조 본문에서 분류한 이름 객체 종류: " + Kind(ParsedHelperReferencedKinds));
            text.AppendLine("해석된 보조 본문의 Store 대상에서 분류한 종류: " + Kind(ParsedHelperStoreTargetKinds));
            text.AppendLine("해석된 보조 본문의 Field Store 대상 주소 공간 종류: " +
                (ParsedHelperFieldStoreSpaces.HasValue ? ParsedHelperFieldStoreSpaces.Value.ToString() : "미확정"));
            text.AppendLine("후보의 Arg2 Store 대상과 직접 Return이 같은 관측 정의를 참조하는 구문: " + Relation(RootStoresArg2ToReturnedObject));
            text.AppendLine("후보의 직접 Return 관측 정의를 해석된 보조 본문도 참조하는 구문: " + Relation(RootReturnedObjectReferencedByParsedHelper));
            text.AppendLine("후보의 Arg2 Store 관측 정의를 해석된 보조 본문도 참조하는 구문: " + Relation(RootArg2StoreObjectReferencedByParsedHelper));
            text.AppendLine("참조 횟수는 발생 횟수이며 고유 객체 수가 아닙니다. 본문당 이름 관계 기록은64개로 제한합니다.");
            text.AppendLine("분류와 관계는 관측한 선언·참조 구문에만 해당합니다. 같은 실행 중 객체·값 전달·실행 순서·수정 효과를 뜻하지 않습니다.");
            text.AppendLine("부분 관측의 관계는 해석된 본문 범위입니다. 미분류·동적 가림·미해석 보조 정의를 기능 부재나 실제 FF 발생 위치로 바꾸지 않습니다.");
            text.AppendLine("주소 공간은 선언 종류만 분류합니다. 영역·필드의 값이나 주소를 읽거나 쓰지 않습니다.");
            return text.ToString();
        }

        private static string Count(int? value) => value.HasValue ? value.Value.ToString() : "미확정";
        private static string Kind(AcpiNamedObjectKinds? value) => value.HasValue ? value.Value.ToString() : "미확정";
        private static string Relation(bool? value) => value.HasValue ? (value.Value ? "관측" : "완전히 분류한 관측 범위에서 미관측") : "미확정";
    }
}
