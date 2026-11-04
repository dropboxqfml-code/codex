using System;
using System.Runtime.InteropServices;
using System.Text;
using ATIVBatteryGuard.Core.Services;

namespace ATIVBatteryGuard.AcpiRoutingCheck
{
    // Windows copies firmware-table data. Neither API evaluates an ACPI method.
    // No SMBIOS/FIRM provider, raw-table file, device, vendor DLL or WMI call.
    internal static class WindowsAcpiRoutingProbe
    {
        private const uint AcpiProvider = 0x41435049;
        private const uint DsdtId = 0x54445344;
        private const uint SsdtId = 0x54445353;
        private const uint MaximumEnumerationBytes = 4096;

        internal delegate uint EnumerateTables(uint provider, byte[] buffer, uint size);
        internal delegate uint ReadFirmwareTable(uint provider, uint table, byte[] buffer, uint size);

        internal static string Collect() => Collect(EnumSystemFirmwareTables, GetSystemFirmwareTable, Marshal.GetLastWin32Error);

        // Pure callbacks let portable tests exercise native acquisition boundaries
        // without loading a Windows API or evaluating firmware. Production always
        // supplies the two fixed read APIs above; no external inputs select them.
        internal static string Collect(EnumerateTables enumerate, ReadFirmwareTable read, Func<int> getLastError)
        {
            var text = new StringBuilder();
            text.AppendLine("ATIV Battery Guard — ACPI 정적 WMI 연결 점검 (Acpi-routing-v5)");
            text.AppendLine("Windows 내장 ACPI 테이블 읽기만 사용합니다. 관리자 권한은 요구하지 않습니다.");
            try
            {
                uint needed = enumerate(AcpiProvider, null, 0);
                if (needed == 0) { text.AppendLine("목록 조회: " + ErrorCategory(getLastError())); return Finish(text); }
                if (needed > MaximumEnumerationBytes || needed % 4 != 0)
                { text.AppendLine("목록 조회: InvalidOrExcessiveResult"); return Finish(text); }
                var ids = new byte[needed];
                try
                {
                    uint count = enumerate(AcpiProvider, ids, needed);
                    if (count == 0) { text.AppendLine("목록 조회: " + ErrorCategory(getLastError())); return Finish(text); }
                    if (count != needed) { text.AppendLine("목록 조회: Incomplete"); return Finish(text); }
                    int dsdt = 0, ssdt = 0;
                    for (int at = 0; at < ids.Length; at += 4)
                    {
                        uint id = (uint)(ids[at] | ids[at + 1] << 8 | ids[at + 2] << 16 | ids[at + 3] << 24);
                        if (id == DsdtId) dsdt++;
                        if (id == SsdtId) ssdt++;
                    }
                    text.AppendLine("테이블 목록 조회: Complete");
                    text.AppendLine("DSDT 목록 항목 수: " + dsdt);
                    text.AppendLine("SSDT 목록 항목 수: " + ssdt);
                    // ACPICA also adds DSDT explicitly: Windows enumeration can
                    // omit it even though a fixed GetSystemFirmwareTable works.
                    ReadTable(text, "DSDT", DsdtId, dsdt, read, getLastError);
                    ReadTable(text, "첫 SSDT", SsdtId, ssdt, read, getLastError);
                }
                finally { Array.Clear(ids, 0, ids.Length); }
            }
            catch { text.AppendLine("수집 결과: Unavailable"); }
            return Finish(text);
        }

        private static void ReadTable(StringBuilder text, string label, uint id, int occurrences,
            ReadFirmwareTable read, Func<int> getLastError)
        {
            text.AppendLine("[" + label + "]");
            if (id == DsdtId)
                text.AppendLine("조회 방식: 목록 관측 여부와 별도로 고정 DSDT ID 직접 읽기");
            else if (occurrences == 0) { text.AppendLine("조회: 목록에서 미관측·본문 조회 미실시"); return; }
            uint needed = read(AcpiProvider, id, null, 0);
            if (needed == 0) { text.AppendLine("조회: " + ErrorCategory(getLastError())); return; }
            if (needed < 36 || needed > AcpiWmiRoutingInspector.MaximumTableBytes)
            { text.AppendLine("조회: InvalidOrExcessiveResult"); return; }
            var table = new byte[needed];
            try
            {
                uint count = read(AcpiProvider, id, table, needed);
                if (count == 0) { text.AppendLine("조회: " + ErrorCategory(getLastError())); return; }
                if (count != needed) { text.AppendLine("조회: Incomplete"); return; }
                text.AppendLine("본문 읽기: Complete (구문 해석 결과와 별도)");
                text.Append(AcpiWmiRoutingInspector.Inspect(table).ToDisplayText());
            }
            finally { Array.Clear(table, 0, table.Length); }
        }

        private static string Finish(StringBuilder text)
        {
            text.AppendLine("DSDT 목록 미관측과 직접 조회 결과는 별개입니다. 미관측을 테이블 부재로 해석하지 않습니다.");
            text.AppendLine("Windows API는 같은 서명의 테이블 중 첫 것만 반환합니다. 모든 SSDT를 확인한 결과가 아닙니다.");
            text.AppendLine("보조 메서드는 같은 테이블의 관측 정의만 제한적으로 읽으며 실행·변수 값·다른 테이블 연결은 추정하지 않습니다.");
            text.AppendLine("제한된 AML 구문만 정적으로 읽습니다. 해석 실패나 미관측은 기능 부재가 아닙니다.");
            text.AppendLine("원본 ACPI·OEM 정보·GUID 원문·메서드 이름·주소·장치 식별자·경로는 출력하거나 저장하지 않습니다.");
            text.AppendLine("OEM 호출·AML 실행·예약 접근·드라이버/서비스/보안 변경·펌웨어 쓰기 없음.");
            text.AppendLine("실제 충전 제어: 미지원. 기존 1회 실험 재실행·예약 표식 삭제를 하지 마세요.");
            return text.ToString();
        }

        private static string ErrorCategory(int error)
        {
            if (error == 5) return "AccessDenied";
            if (error == 1 || error == 50 || error == 120) return "NotSupported";
            if (error == 2 || error == 1168) return "NotFound";
            return "Unavailable";
        }

        [DllImport("kernel32.dll", ExactSpelling = true, SetLastError = true)]
        private static extern uint EnumSystemFirmwareTables(uint provider, [Out] byte[] buffer, uint size);
        [DllImport("kernel32.dll", ExactSpelling = true, SetLastError = true)]
        private static extern uint GetSystemFirmwareTable(uint provider, uint table, [Out] byte[] buffer, uint size);
    }
}
