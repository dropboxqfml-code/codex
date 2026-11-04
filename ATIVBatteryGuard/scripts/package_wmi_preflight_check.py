"""Package the separate, bounded, read-only preparation checker only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
import zipfile


PROJECT_NAME = "ATIVBatteryGuard.WmiPreflightCheck"
DIAGNOSTIC_REVISION = "Locator-v2"
SOURCE_SUFFIXES = {".cs", ".csproj", ".sln", ".xaml", ".md", ".config", ".manifest", ".ps1", ".py"}
EXCLUDED_PARTS = {"bin", "obj", "reports", "dist", ".git", ".vs", "__pycache__"}
FORBIDDEN_REFERENCES = {
    "InvokeMethod", "TryClaim", "WsabiWmiOneShotExperiment", "WindowsOneShotBackend",
    "WsabiWmiOneShotFileReservation",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked_slice(data, offset, size):
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError("Truncated executable metadata.")
    return data[offset:offset + size]


def unpack(data, offset, fmt):
    return struct.unpack(fmt, checked_slice(data, offset, struct.calcsize(fmt)))


def inspect_executable(executable):
    """Read exact CLI type/member names, never substring-match prefixes."""
    if checked_slice(executable, 0, 2) != b"MZ":
        raise ValueError("A real built executable is required.")
    pe, = unpack(executable, 0x3C, "<I")
    if checked_slice(executable, pe, 4) != b"PE\0\0":
        raise ValueError("A valid PE executable is required.")
    machine, section_count = unpack(executable, pe + 4, "<HH")
    optional_size, = unpack(executable, pe + 20, "<H")
    optional = pe + 24
    magic, = unpack(executable, optional, "<H")
    if machine != 0x8664 or magic != 0x20B:
        raise ValueError("The separate executable must be AMD64 PE32+.")
    if optional_size < 112 + 15 * 8:
        raise ValueError("The PE has no CLI data directory.")
    directory_count, = unpack(executable, optional + 108, "<I")
    if directory_count <= 14:
        raise ValueError("The PE has no CLI data directory.")
    sections = optional + optional_size

    def rva_offset(rva):
        for index in range(section_count):
            section = sections + index * 40
            virtual_size, address, raw_size, raw = unpack(executable, section + 8, "<IIII")
            if address <= rva < address + max(virtual_size, raw_size):
                relative = rva - address
                if relative >= raw_size:
                    raise ValueError("CLI metadata points outside file-backed PE data.")
                return raw + relative
        raise ValueError("CLI metadata has an invalid RVA.")

    cli_rva, cli_size = unpack(executable, optional + 112 + 14 * 8, "<II")
    if not cli_rva or cli_size < 16:
        raise ValueError("The executable must contain managed CLI metadata.")
    cli = rva_offset(cli_rva)
    metadata_rva, metadata_size = unpack(executable, cli + 8, "<II")
    metadata = checked_slice(executable, rva_offset(metadata_rva), metadata_size)
    if checked_slice(metadata, 0, 4) != b"BSJB":
        raise ValueError("Invalid CLI metadata signature.")
    version_size, = unpack(metadata, 12, "<I")
    cursor = (16 + version_size + 3) & ~3
    _, stream_count = unpack(metadata, cursor, "<HH")
    cursor += 4
    streams = {}
    for _ in range(stream_count):
        offset, size = unpack(metadata, cursor, "<II")
        name_start = cursor + 8
        name_end = metadata.find(b"\0", name_start, min(name_start + 32, len(metadata)))
        if name_end < 0:
            raise ValueError("Invalid CLI stream name.")
        name = metadata[name_start:name_end].decode("ascii")
        if name in streams:
            raise ValueError("Duplicate CLI metadata stream.")
        streams[name] = checked_slice(metadata, offset, size)
        cursor = (name_end + 1 + 3) & ~3
    strings = streams.get("#Strings")
    tables = streams.get("#~", streams.get("#-"))
    if strings is None or tables is None:
        raise ValueError("Required CLI metadata streams are missing.")
    heap_flags = checked_slice(tables, 6, 1)[0]
    valid, = unpack(tables, 8, "<Q")
    cursor = 24
    rows = [0] * 64
    for table in range(64):
        if valid & (1 << table):
            rows[table], = unpack(tables, cursor, "<I")
            cursor += 4
    string_width = 4 if heap_flags & 1 else 2
    guid_width = 4 if heap_flags & 2 else 2
    blob_width = 4 if heap_flags & 4 else 2

    def index_width(table):
        return 4 if rows[table] >= 65536 else 2

    def coded_width(targets, bits):
        return 4 if max(rows[table] for table in targets) >= (1 << (16 - bits)) else 2

    def heap_string(row, offset):
        index, = unpack(tables, row + offset, "<I" if string_width == 4 else "<H")
        if index >= len(strings):
            raise ValueError("Invalid CLI string index.")
        end = strings.find(b"\0", index)
        if end < 0:
            raise ValueError("Unterminated CLI metadata name.")
        return strings[index:end].decode("utf-8")

    resolution = coded_width([0, 26, 35, 1], 2)
    type_def_or_ref = coded_width([2, 1, 27], 2)
    member_parent = coded_width([2, 1, 26, 6, 27], 3)
    widths = [
        2 + string_width + 3 * guid_width,
        resolution + 2 * string_width,
        4 + 2 * string_width + type_def_or_ref + index_width(4) + index_width(6),
        index_width(4),
        2 + string_width + blob_width,
        index_width(6),
        8 + string_width + blob_width + index_width(8),
        index_width(8),
        4 + string_width,
        index_width(2) + type_def_or_ref,
        member_parent + string_width + blob_width,
    ]
    references = set()
    for table, width in enumerate(widths):
        checked_slice(tables, cursor, rows[table] * width)
        if table in {1, 2, 6, 10}:
            name_offset = {1: resolution, 2: 4, 6: 8, 10: member_parent}[table]
            for row in range(rows[table]):
                references.add(heap_string(cursor + row * width, name_offset))
        cursor += rows[table] * width
    if references & FORBIDDEN_REFERENCES:
        raise ValueError("The preflight EXE references an OEM invocation or reservation path.")
    if b"asInvoker" not in executable or b"requireAdministrator" in executable or b"highestAvailable" in executable:
        raise ValueError("The built executable must retain its asInvoker manifest.")


def code_only(source):
    # Remove comments and literal contents before checking actual operation
    # tokens. Safety explanations in console strings are not operations.
    literals_and_comments = r'@"(?:[^"]|"")*"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/'
    return re.sub(literals_and_comments, lambda match: "\n" * match.group().count("\n") + " ", source, flags=re.S)


def without_comments(source):
    # Preserve query literals so the option can be tied to the fixed SELECT,
    # while a commented-out example cannot satisfy the required call shape.
    literals_and_comments = r'@"(?:[^"]|"")*"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/'
    return re.sub(literals_and_comments,
                  lambda match: "\n" * match.group().count("\n") + " "
                  if match.group().startswith(("//", "/*")) else match.group(), source, flags=re.S)


def inspect_locator_scope(native):
    code = code_only(native)
    calls = re.findall(r'\bCreateEnumerationOptions\s*\(([^()]*)\)', code)
    expected_calls = [r'\s*ensureLocatable\s*:\s*true\s*', r'\s*',
                      r'\s*bool\s+ensureLocatable\s*=\s*false\s*']
    if len(calls) != 3 or any(sum(bool(re.fullmatch(pattern, call)) for call in calls) != 1
                              for pattern in expected_calls):
        raise ValueError("Only the fixed method-target query may request locatable information.")
    query_with_option = (r'\bnew\s+ObjectQuery\s*\(\s*"SELECT Active FROM WmiAcpiMethod"\s*\)\s*,\s*'
                         r'CreateEnumerationOptions\s*\(\s*ensureLocatable\s*:\s*true\s*\)')
    scalar_query = r'\bnew\s+ObjectQuery\s*\(\s*query\s*\)\s*,\s*CreateEnumerationOptions\s*\(\s*\)'
    source = without_comments(native)
    if not re.search(query_with_option, source) or not re.search(scalar_query, source):
        raise ValueError("The locator option must apply only to the reviewed method-target SELECT.")
    if len(re.findall(r'\bEnsureLocatable\b', code)) != 1 or not re.search(
            r'\bEnsureLocatable\s*=\s*ensureLocatable\b', code):
        raise ValueError("The locator option must use the reviewed false-by-default parameter.")


def inspect_locator_build(executable, core):
    if b"set_EnsureLocatable\0" not in executable:
        raise ValueError("The built preflight EXE must contain its locatable-option setter.")
    if DIAGNOSTIC_REVISION.encode("utf-16-le") not in core:
        raise ValueError("The built Core DLL must contain the Locator-v2 report marker.")


def inspect_sources(root, project):
    level = ET.parse(project / "app.manifest").find(
        ".//{urn:schemas-microsoft-com:asm.v3}requestedExecutionLevel")
    if level is None or level.attrib != {"level": "asInvoker", "uiAccess": "false"}:
        raise ValueError("The preflight checker must remain asInvoker.")
    native = (project / "ReadOnlyPreparationProbe.cs").read_text(encoding="utf-8")
    host = (project / "Program.cs").read_text(encoding="utf-8")
    dangerous = re.compile(
        r'\b(?:InvokeMethod|Invoke|TryClaim|WsabiWmiOneShotExperiment|WindowsOneShotBackend|'
        r'WsabiWmiOneShotFileReservation|DllImport|LoadLibrary|LoadLibraryEx|GetProcAddress|'
        r'DeviceIoControl|CreateFile|WriteFile|GetDelegateForFunctionPointer|FileStream|StreamWriter|'
        r'HttpClient|WebClient|WebRequest|TcpClient|Socket|ServiceController|RegistryKey)\b|'
        r'\.(?:Put|Delete|SetPropertyValue|SetValue|CreateSubKey|DeleteSubKey|DeleteValue|'
        r'StartService|StopService|WriteAllText|WriteAllBytes|AppendAllText|AppendAllLines|'
        r'WriteAllLines|CreateDirectory|Move|Replace|Copy|GetMethod)\s*\(|'
        r'\b(?:File|Directory|Registry)\s*\.|\bEnablePrivileges\s*=\s*true\b|'
        r'\.Value\s*=(?!=)|\]\s*=(?!=)')
    for source in (host, native):
        if dangerous.search(code_only(source)):
            raise ValueError("Preflight source contains a forbidden invocation, reservation, native, network or write operation.")
    host_code, native_code = code_only(host), code_only(native)
    required_host = [
        r'\bWorkerTimeoutMilliseconds\s*=\s*10000\s*;',
        r'\bnew\s+Thread\s*\(', r'\bThread\.Sleep\s*\(\s*WorkerTimeoutMilliseconds\s*\)',
        r'\bEnvironment\.Exit\s*\(\s*3\s*\)',
        r'\.WaitForExit\s*\(\s*WorkerTimeoutMilliseconds\s*\)',
        r'\bReadOnlyPreparationProbe\.Collect\s*\(\s*\)',
        r'\bwatchdog\.Start\s*\(\s*\)',
        r'\bUseShellExecute\s*=\s*false\b',
    ]
    if any(not re.search(pattern, host_code) for pattern in required_host):
        raise ValueError("The parent and independent worker must retain their 10-second limits.")
    if not re.search(r'\bPreflightBudget\s*=\s*TimeSpan\.FromSeconds\s*\(\s*6\s*\)', native_code):
        raise ValueError("The read-only preparation budget must remain six seconds.")
    if not re.search(r'\bEnablePrivileges\s*=\s*false\b', native_code) or not re.search(
            r'\bAuthentication\s*=\s*AuthenticationLevel\.PacketPrivacy\b', native_code):
        raise ValueError("The probe must retain its reviewed local WMI connection protections.")
    fixed_queries = {
        "SELECT Name FROM Win32_ComputerSystemProduct",
        "SELECT SMBIOSBIOSVersion FROM Win32_BIOS",
        "SELECT Active FROM WmiAcpiMethod",
    }
    actual_queries = set(re.findall(r'"(SELECT\s+[^"\r\n]+)"', native, re.I))
    if actual_queries != fixed_queries or re.search(r'\bSELECT\s+\*', native, re.I):
        raise ValueError("Only the reviewed fixed, read-only queries belong in the probe.")
    inspect_locator_scope(native)
    if PROJECT_NAME in (root / "src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj").read_text(encoding="utf-8"):
        raise ValueError("The main application must not reference this separate tool.")


def inspect_source_zip(root, source_zip):
    expected = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() not in SOURCE_SUFFIXES and path.name != ".gitignore":
            continue
        expected["ATIVBatteryGuard/" + relative.as_posix()] = path.read_bytes()
    required = {
        "ATIVBatteryGuard/src/" + PROJECT_NAME + "/" + name
        for name in [PROJECT_NAME + ".csproj", "Program.cs", "ReadOnlyPreparationProbe.cs", "app.manifest"]
    }
    if not required <= expected.keys():
        raise ValueError("The complete preflight checker source is required.")
    with zipfile.ZipFile(source_zip) as source:
        names = source.namelist()
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise ValueError("The source ZIP must contain the complete current source allowlist exactly once.")
        if source.testzip() is not None:
            raise ValueError("Source ZIP CRC failed.")
        for name, data in expected.items():
            if source.read(name) != data:
                raise ValueError("Source ZIP must match the current source bytes.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--test-report", type=Path, required=True)
    parser.add_argument("--source-zip", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tests = json.loads(args.test_report.read_text(encoding="utf-8"))
    for key in ("passed", "failed", "registered"):
        if type(tests.get(key)) is not int:
            raise ValueError("A complete integer-count test report is required.")
    if type(tests.get("skipped", 0)) is not int or tests["passed"] <= 0 or tests["failed"] != 0 or tests.get("skipped", 0) != 0 or tests["passed"] != tests["registered"]:
        raise ValueError("A complete passing test report without skipped tests is required.")
    project = root / "src" / PROJECT_NAME
    inspect_sources(root, project)
    inspect_source_zip(root, args.source_zip)
    build = project / "bin/Release/net48"
    names = [PROJECT_NAME + ".exe", PROJECT_NAME + ".exe.config", "ATIVBatteryGuard.Core.dll"]
    files = {name: (build / name).read_bytes() for name in names}
    inspect_executable(files[PROJECT_NAME + ".exe"])
    inspect_locator_build(files[PROJECT_NAME + ".exe"], files["ATIVBatteryGuard.Core.dll"])
    info = {
        "application": "ATIV Battery Guard WMI Preflight Locator",
        "target": "Windows10x64/.NETFramework4.8",
        "preflightOnly": True,
        "diagnosticRevision": DIAGNOSTIC_REVISION,
        "ensuresMethodTargetLocatable": True,
        "locatorOptionChangesOnlyMethodTargetQuery": True,
        "requestedExecutionLevel": "asInvoker",
        "requiresOwnerManualSameAccountAdministratorRun": True,
        "requestsUacOrElevation": False,
        "mainApplicationLaunchesTool": False,
        "consoleOutputOnly": True,
        "acceptsArbitraryQueriesCommandsOrPaths": False,
        "fixedReadOnlyQueries": ["SELECT Name FROM Win32_ComputerSystemProduct",
                                "SELECT SMBIOSBIOSVersion FROM Win32_BIOS",
                                "SELECT Active FROM WmiAcpiMethod"],
        "fixedMetadataClasses": ["WmiAcpiMethod", "DataBuffer"],
        "methodDefinitionOnly": "CallSabiFunction",
        "preparesInMemoryParametersOnly": True,
        "executesWmiMethods": False,
        "readsReservation": False,
        "writesReservation": False,
        "deletesOrResetsReservation": False,
        "touchesReservation": False,
        "canReadHardware": False,
        "canWriteHardware": False,
        "loadsSamsungDll": False,
        "changesServicesDriversAclOrFirmware": False,
        "actualChargeControlSupported": False,
        "preparationReadyProvesOemExecutionOrChargeControl": False,
        "parentWorkerTimeoutMs": 10000,
        "independentWorkerWatchdogMs": 10000,
        "preflightBudgetMs": 6000,
        "authentication": "PacketPrivacy",
        "enablePrivileges": False,
        "containsOriginalVendorBinariesOrRawUserReports": False,
        "containsPreviousOneShotExecutable": False,
        "exeForbiddenTypeAndMemberReferencesAbsent": True,
        "portableTests": tests,
        "testsExecuteWindowsOrFirmware": False,
        "currentWindowsRuntimeTested": False,
        "windowsRuntimeTested": False,
        "signed": False,
        "digitallySigned": False,
        "matchingSourceZipSha256": sha(args.source_zip.read_bytes()),
    }
    files["BUILD-INFO.json"] = json.dumps(info, ensure_ascii=False, indent=2).encode("utf-8")
    instructions = """ATIV Battery Guard — 사전검증 전용 · OEM 호출 없음
점검판: 경로 정보 확보 보완판 (Locator-v2)

이번 도구는 이전 대상 확인 실패를 보완한 별도 미서명 개발판입니다.
메서드 대상 쿼리에만 경로 정보 확보 옵션을 적용하고 객체·경로 문제와 명시적 비활성을 구분합니다.
이전 실패의 실제 원인은 아직 미확정이며 이번 수정이 원인을 해결한다고 보장하지 않습니다.
OEM 메서드를 실행하지 않으며 1회 예약 표식을 읽거나 만들거나 변경하지 않습니다.
이전 ATIVBatteryGuard.WmiOneShotQuery.exe 실험 도구는 재실행하지 마세요.

1. ZIP 전체를 메인 앱과 이전 실험 도구에서 분리된 새 로컬 폴더에 압축 해제합니다.
2. 같은 Windows 계정에서 새 ATIVBatteryGuard.WmiPreflightCheck.exe만 오른쪽 클릭하여 수동 관리자 실행합니다.
   다른 관리자 계정의 암호를 요구하면 중단합니다. 자동 UAC·권한 상승 코드는 없습니다.
3. 창의 '사전검증 전용 · OEM 호출 없음'과 'Locator-v2'를 확인하고 새 출력 전체를 복사해 전달한 뒤 Enter로 닫습니다.
   과거 TXT·삼성 DLL·EXE·기존 진단은 다시 제출할 필요가 없습니다.
4. 기존 1회 예약 표식을 삭제하거나 초기화하지 마세요. 이 도구에는 예약 접근 기능이 없습니다.

고정 모델/BIOS 값, 로컬 WMI의 고정 클래스·메서드 정의, 단일 활성 대상만 읽습니다.
입력 매개변수와 DataBuffer는 메모리에서만 준비하며 값을 기록하거나 메서드를 호출하지 않습니다.
준비 완료는 이전 OEM 호출이 실행됐다는 증거가 아니며 충전 제한 성공이나 실제 보호 상태를 뜻하지 않습니다.
실제 충전 제어는 계속 미지원입니다. 어떤 결과에서도 제어를 활성화하지 않습니다.

부모와 작업자는 각각 10초 제한을 사용하고 사전 검사에는 6초 예산을 적용합니다.
클래스·필드 미관측, 권한 거부, 시간 초과, 형식 불일치와 기타 오류를 고정 분류로 구분합니다.
사용자 이름·SID·인스턴스 이름·전체 경로·원문 오류·원문 오류 코드는 출력하거나 저장하지 않습니다.
삼성 DLL 초기화, OEM 명령, 드라이버 설치, 서비스 시작·중지, ACL·보안 정책·펌웨어 변경은 없습니다.
프로그램의 인터넷 통신은 없습니다. 보안 제품이 차단하면 보호를 해제하거나 우회하지 마세요.
새 도구의 현재 Windows 실기 실행은 아직 미검증입니다. 삼성 원본 DLL·이전 실험 EXE·원문 보고서는 포함하지 않습니다.
"""
    files["먼저 읽어주세요.txt"] = instructions.replace("\n", "\r\n").encode("utf-8-sig")
    files["SHA256SUMS.txt"] = "".join(sha(data) + "  " + name + "\n" for name, data in sorted(files.items())).encode("utf-8")
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "ATIVBatteryGuard-WMI-PREFLIGHT-LOCATOR.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files):
            raise ValueError("Executable ZIP integrity or allowlist check failed.")
    print(json.dumps({"file": str(target), "bytes": target.stat().st_size, "sha256": sha(target.read_bytes())}))


if __name__ == "__main__":
    main()
