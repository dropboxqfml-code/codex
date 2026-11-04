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
        public bool CanInvokeMethods => false;
        public bool CanWriteHardware => false;

        internal AcpiMethodFlowReport(AcpiMethodFlowStatus status = AcpiMethodFlowStatus.NotInspected,
            int? rootCallSites = null, int? rootArg2CallArguments = null, int? rootReturnStatements = null,
            AcpiReturnSyntax? rootReturnSyntax = null, int inspectedHelpers = 0, int parsedHelpers = 0,
            int unsupportedHelpers = 0, int unresolvedNameReferences = 0, bool cycleObserved = false,
            bool? helperLiteralFfReturn = null)
        {
            Status = status; RootCallSites = rootCallSites; RootArg2CallArguments = rootArg2CallArguments;
            RootReturnStatements = rootReturnStatements; RootReturnSyntax = rootReturnSyntax;
            InspectedHelpers = inspectedHelpers; ParsedHelpers = parsedHelpers; UnsupportedHelpers = unsupportedHelpers;
            UnresolvedNameReferences = unresolvedNameReferences; CycleObserved = cycleObserved;
            HelperLiteralFfReturn = helperLiteralFfReturn;
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
            text.AppendLine("객체 또는 호출 종류가 미확정인 이름 참조 수: " + UnresolvedNameReferences);
            text.AppendLine("관측한 연결의 순환 구문: " + (CycleObserved ? "관측" : "관측한 연결 범위에서 미관측"));
            text.AppendLine("보조 정의 본문의 상수FF/FF프레임 반환 구문: " +
                (HelperLiteralFfReturn.HasValue ? (HelperLiteralFfReturn.Value ? "관측" : "해석한 보조 정의 범위에서 미관측") : "해석 불가 또는 미실시"));
            text.AppendLine("같은 테이블에서 관측한 정의만 깊이2·보조 정의8개·호출 표현식32개 범위로 정적으로 검사합니다.");
            text.AppendLine("호출 표현식은 실행한 호출이 아닙니다. 분기·변수·별칭·보조 인수의 실제 값은 평가하지 않습니다.");
            text.AppendLine("구문 연결은 전체 대상의 유일성·현재 실행 경로·실제 FF 발생 위치나 배터리 의미를 증명하지 않습니다.");
            text.AppendLine("Field 내부 이름·미해석 정의·다른 테이블을 포함한 전체 이름 해소는 보장하지 않습니다.");
            return text.ToString();
        }

        private static string Count(int? value) => value.HasValue ? value.Value.ToString() : "미확정";
    }
}
