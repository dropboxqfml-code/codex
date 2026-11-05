using System;
using System.Text;

namespace ATIVBatteryGuard.Core.Models
{
    public enum AcpiMethodFlowStatus { NotInspected, ParsedObservedDefinitions, Partial, LimitExceeded }

    [Flags]
    public enum AcpiReturnSyntax
    {
        None = 0, IntegerLiteral = 1, BufferLiteral = 2, Argument2 = 4,
        KnownMethodCall = 8, UnresolvedName = 16, Other = 32
    }

    [Flags]
    public enum AcpiSyntaxFailureKind
    {
        None = 0, UnsupportedOpcode = 1, UnsupportedExtendedOpcode = 2, InvalidEncoding = 4,
        UnsupportedReference = 8, AmbiguousName = 16, MethodNameCollision = 32,
        DynamicBuffer = 64, DynamicNamespace = 128, UnresolvedStatement = 256
    }

    [Flags]
    public enum AcpiSyntaxOperation
    {
        None = 0, UnrecognizedPrimary = 1, UnrecognizedExtended = 2, Acquire = 4, Release = 8,
        Wait = 16, Signal = 32, Reset = 64, Sleep = 128, Stall = 256, CondRefOf = 512,
        FromBcd = 1024, ToBcd = 2048, Revision = 4096, Timer = 8192, Debug = 16384,
        CreateField = 32768, Fatal = 65536, LoadTable = 131072, Load = 262144, Unload = 524288,
        Match = 1048576, NameDefinition = 2097152, OtherNamespaceDefinition = 4194304
    }

    // Only fixed syntax kinds and bounded counts leave the temporary reader.
    // No method names, namespace paths, operands or table buffers are retained.
    public sealed class AcpiMethodFlowReport
    {
        public AcpiMethodFlowStatus Status { get; }
        public int? RootCallSites { get; }
        public int? RootArg2CallArguments { get; }
        public int? RootReturnStatements { get; }
        public AcpiReturnSyntax? RootReturnSyntax { get; }
        public int InspectedHelpers { get; }
        public int ParsedHelpers { get; }
        public int UnsupportedHelpers { get; }
        public int UnresolvedNameReferences { get; }
        public bool CycleObserved { get; }
        public bool? HelperLiteralFfReturn { get; }
        public AcpiSyntaxFailureKind RootSyntaxFailure { get; }
        public AcpiSyntaxFailureKind HelperSyntaxFailures { get; }
        public AcpiSyntaxOperation RootFailureOperations { get; }
        public AcpiSyntaxOperation HelperFailureOperations { get; }
        public AcpiSyntaxOperation? RootExtendedSyntax { get; }
        public AcpiSyntaxOperation? ParsedHelperExtendedSyntax { get; }
        public int? ParsedHelperReturnStatements { get; }
        public AcpiReturnSyntax? ParsedHelperReturnSyntax { get; }
        public bool? ParsedHelperLiteralFfReturn { get; }
        public bool CanInvokeMethods => false;
        public bool CanWriteHardware => false;

        internal AcpiMethodFlowReport(AcpiMethodFlowStatus status = AcpiMethodFlowStatus.NotInspected,
            int? rootCallSites = null, int? rootArg2CallArguments = null, int? rootReturnStatements = null,
            AcpiReturnSyntax? rootReturnSyntax = null, int inspectedHelpers = 0, int parsedHelpers = 0,
            int unsupportedHelpers = 0, int unresolvedNameReferences = 0, bool cycleObserved = false,
            bool? helperLiteralFfReturn = null,
            AcpiSyntaxFailureKind rootSyntaxFailure = AcpiSyntaxFailureKind.None,
            AcpiSyntaxFailureKind helperSyntaxFailures = AcpiSyntaxFailureKind.None,
            AcpiSyntaxOperation rootFailureOperations = AcpiSyntaxOperation.None,
            AcpiSyntaxOperation helperFailureOperations = AcpiSyntaxOperation.None,
            AcpiSyntaxOperation? rootExtendedSyntax = null,
            AcpiSyntaxOperation? parsedHelperExtendedSyntax = null, int? parsedHelperReturnStatements = null,
            AcpiReturnSyntax? parsedHelperReturnSyntax = null, bool? parsedHelperLiteralFfReturn = null)
        {
            Status = status; RootCallSites = rootCallSites; RootArg2CallArguments = rootArg2CallArguments;
            RootReturnStatements = rootReturnStatements; RootReturnSyntax = rootReturnSyntax;
            InspectedHelpers = inspectedHelpers; ParsedHelpers = parsedHelpers; UnsupportedHelpers = unsupportedHelpers;
            UnresolvedNameReferences = unresolvedNameReferences; CycleObserved = cycleObserved;
            HelperLiteralFfReturn = helperLiteralFfReturn;
            RootSyntaxFailure = rootSyntaxFailure; HelperSyntaxFailures = helperSyntaxFailures;
            RootFailureOperations = rootFailureOperations; HelperFailureOperations = helperFailureOperations;
            RootExtendedSyntax = rootExtendedSyntax; ParsedHelperExtendedSyntax = parsedHelperExtendedSyntax;
            ParsedHelperReturnStatements = parsedHelperReturnStatements;
            ParsedHelperReturnSyntax = parsedHelperReturnSyntax; ParsedHelperLiteralFfReturn = parsedHelperLiteralFfReturn;
        }

        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("반환·보조 정의 구문 요약: " + Status);
            text.AppendLine("후보 본문에서 관측한 알려진 호출 표현식 수: " + Count(RootCallSites));
            text.AppendLine("후보 본문 호출 인수의 직접 Arg2 구문 수: " + Count(RootArg2CallArguments));
            text.AppendLine("후보 본문의 Return 구문 수: " + Count(RootReturnStatements));
            text.AppendLine("후보 본문의 Return 값 구문 종류: " + (RootReturnSyntax.HasValue ? RootReturnSyntax.Value.ToString() : "미확정"));
            text.AppendLine("검사한 보조 정의 수: " + InspectedHelpers);
            text.AppendLine("구문 해석된 보조 정의 수: " + ParsedHelpers);
            text.AppendLine("지원하지 않는 보조 정의 수: " + UnsupportedHelpers);
            text.AppendLine("후보 본문 구문 실패 종류: " + RootSyntaxFailure);
            text.AppendLine("후보 본문 실패 위치의 표준 연산 종류: " + RootFailureOperations);
            text.AppendLine("보조 본문 구문 실패 종류: " + HelperSyntaxFailures);
            text.AppendLine("보조 본문 실패 위치의 표준 연산 종류: " + HelperFailureOperations);
            text.AppendLine("구문 해석된 후보 본문의 확장 연산 종류: " + Syntax(RootExtendedSyntax));
            text.AppendLine("구문 해석을 완료한 보조 본문 " + ParsedHelpers + "개의 확장 연산 종류: " + Syntax(ParsedHelperExtendedSyntax));
            text.AppendLine("구문 해석을 완료한 보조 본문 " + ParsedHelpers + "개의 Return 구문 수: " + Count(ParsedHelperReturnStatements));
            text.AppendLine("구문 해석을 완료한 보조 본문 " + ParsedHelpers + "개의 Return 값 구문 종류: " +
                (ParsedHelperReturnSyntax.HasValue ? ParsedHelperReturnSyntax.Value.ToString() : "미확정"));
            text.AppendLine("구문 해석을 완료한 보조 본문 " + ParsedHelpers + "개의 상수FF/FF프레임 반환 구문: " +
                Observed(ParsedHelperLiteralFfReturn, "해석한 본문 범위에서 미관측"));
            text.AppendLine("연결 구문 검사에서 객체 참조·호출 구분을 미확정으로 센 이름 참조 횟수: " + UnresolvedNameReferences);
            text.AppendLine("선언 종류 분류와 별도로 유지하는 지표입니다. 이름 객체·참조 관계 분류 결과도 함께 확인하세요.");
            text.AppendLine("관측한 연결의 순환 구문: " + (CycleObserved ? "관측" : "관측한 연결 범위에서 미관측"));
            text.AppendLine("보조 정의 본문의 상수FF/FF프레임 반환 구문: " +
                (HelperLiteralFfReturn.HasValue ? (HelperLiteralFfReturn.Value ? "관측" : "해석한 보조 정의 범위에서 미관측") : "해석 불가 또는 미실시"));
            text.AppendLine("같은 테이블에서 관측한 정의만 깊이2·보조 정의8개·호출 표현식32개 범위로 정적으로 검사합니다.");
            text.AppendLine("호출 표현식은 실행한 호출이 아닙니다. 분기·변수·별칭·보조 인수의 실제 값은 평가하지 않습니다.");
            text.AppendLine("확장 연산 이름은 정적 구문 종류입니다. 대기·동기화·지연·중단·이름 생성 동작을 실행하지 않습니다.");
            text.AppendLine("해석된 보조 본문만의 구문 사실은 미해석·미방문 정의의 부재나 실제 FF 발생 위치를 뜻하지 않습니다.");
            text.AppendLine("구문 연결은 전체 대상의 유일성·현재 실행 경로·실제 FF 발생 위치나 배터리 의미를 증명하지 않습니다.");
            text.AppendLine("Field 내부 이름·미해석 정의·다른 테이블을 포함한 전체 이름 해소는 보장하지 않습니다.");
            return text.ToString();
        }

        private static string Count(int? value) => value.HasValue ? value.Value.ToString() : "미확정";
        private static string Syntax(AcpiSyntaxOperation? value) => value.HasValue ? value.Value.ToString() : "미확정";
        private static string Observed(bool? value, string absent) => value.HasValue ? (value.Value ? "관측" : absent) : "해석 불가 또는 미실시";
    }
}
