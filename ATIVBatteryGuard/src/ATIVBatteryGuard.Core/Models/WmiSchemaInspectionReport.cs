using System;
using System.Collections.Generic;
using System.Text;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.Core.Models
{
    public sealed class WmiSchemaInspectionReport
    {
        private readonly WmiClassSchema[] classes;
        public WmiClassSchema[] Classes => (WmiClassSchema[])classes.Clone();
        public bool HardwareWriteAllowed => false;
        public WmiSchemaInspectionReport(IEnumerable<WmiClassSchema> classes)
        {
            bool ignored;
            this.classes = WmiSchemaPolicy.CopyBounded(classes, WmiSchemaPolicy.AllowedClasses.Length, out ignored);
        }
        public string ToDisplayText()
        {
            var text = new StringBuilder();
            text.AppendLine("[정적 분석으로 확인한 삼성 WMI 클래스 정의]");
            text.AppendLine(@"조회 범위: 로컬 ROOT\WMI의 WmiAcpiVersion / WmiAcpiMethod / DataBuffer");
            text.AppendLine("속성 이름·형식·배열 여부와 메서드의 입력/출력 매개변수 정의만 읽었습니다.");
            text.AppendLine("OEM 인스턴스 값·기본값·한정자는 읽지 않았으며 OEM 메서드와 DLL은 호출하지 않았습니다.");
            text.AppendLine("클래스가 있어도 충전 제한 지원이 검증된 것은 아닙니다. 조회 실패나 부재도 하드웨어 기능 부재를 확정하지 않습니다.");
            if (classes.Length == 0) text.AppendLine("정의 조회를 수행하지 않았습니다.");
            foreach (WmiClassSchema schema in classes)
            {
                text.AppendLine(schema.ClassName + ": " + StatusText(schema.Status));
                if (schema.Status != WmiSchemaStatus.Found) continue;
                foreach (WmiSchemaField field in schema.Properties) AppendField(text, "  속성", field);
                foreach (WmiSchemaMethod method in schema.Methods)
                {
                    text.AppendLine("  메서드 정의: " + method.Name + " (호출하지 않음)");
                    foreach (WmiSchemaField field in method.Inputs) AppendField(text, "    입력", field);
                    foreach (WmiSchemaField field in method.Outputs) AppendField(text, "    출력", field);
                    if (method.Truncated) text.AppendLine("    매개변수 항목 한도로 일부 정의를 생략했습니다.");
                }
                if (schema.Truncated) text.AppendLine("  항목 한도로 일부 정의를 생략했습니다.");
            }
            text.AppendLine("실제 충전 제어: 미지원. 하드웨어 쓰기 허용: false.");
            return text.ToString();
        }
        private static void AppendField(StringBuilder text, string prefix, WmiSchemaField field)
        {
            text.AppendLine(prefix + ": " + field.Name + " : " + field.TypeName + (field.IsArray ? "[]" : string.Empty));
        }
        public static string StatusText(WmiSchemaStatus status)
        {
            switch (status)
            {
                case WmiSchemaStatus.Found: return "정의 발견 (충전 제어 지원 여부 미검증)";
                case WmiSchemaStatus.ClassNotFound: return "클래스 정의를 찾지 못했습니다.";
                case WmiSchemaStatus.NamespaceNotFound: return "로컬 WMI 네임스페이스를 찾지 못했습니다.";
                case WmiSchemaStatus.AccessDenied: return "일반 사용자 권한으로 정의를 읽을 수 없습니다. 권한 상승은 요청하지 않았습니다.";
                case WmiSchemaStatus.TimedOut: return "정의 조회 시간이 초과되었습니다.";
                case WmiSchemaStatus.UnsupportedPlatform: return "Windows에서만 정의를 조회할 수 있습니다.";
                default: return "클래스 정의 읽기에 실패했습니다. 상세 오류나 개인 경로는 기록하지 않습니다.";
            }
        }
    }
}
