"""Package the bounded static ACPI reader, with no firmware execution tool."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
from package_wmi_preflight_check import code_only, inspect_executable, inspect_source_zip


PROJECT = 'ATIVBatteryGuard.AcpiRoutingCheck'
READ_ONLY_FOOTPRINT = {
    'WindowsAcpiRoutingProbe.cs': 'd7c9653efccc04ad6c798e3ad10eb4075a1937aa211c3dcbaf301342622aa081',
    'Program.cs': '0efb632ebc566a2583fd8918a3f5e810cd57643935e05577bf056c75337154df',
}


def inspect_reader_sources(root):
    project = root / 'src' / PROJECT
    native = (project / 'WindowsAcpiRoutingProbe.cs').read_text(encoding='utf-8')
    host = (project / 'Program.cs').read_text(encoding='utf-8')
    parser = (root / 'src/ATIVBatteryGuard.Core/Services/AcpiWmiRoutingInspector.cs').read_text(encoding='utf-8')
    models = [(root / ('src/ATIVBatteryGuard.Core/Models/' + name)).read_text(encoding='utf-8')
              for name in ['AcpiWmiRoutingReport.cs', 'AcpiMethodFlowReport.cs', 'AcpiObjectReferenceReport.cs']]
    forbidden = re.compile(r'\b(?:InvokeMethod|TryClaim|WindowsOneShotBackend|ManagementObject|ManagementClass|'
        r'ManagementScope|WsabiWmiOneShotExperiment|WsabiWmiOneShotFileReservation|LoadLibrary|'
        r'DeviceIoControl|WriteFile|FileStream|StreamWriter|HttpClient|WebClient|Socket|Registry|ServiceController)\b|'
        r'\.(?:Put|Delete|WriteAllText|WriteAllBytes|CreateDirectory|SetValue)\s*\(')
    for source in [native, host, parser] + models:
        if forbidden.search(code_only(source)):
            raise ValueError('Only static table reading and syntax inspection may be packaged.')
    # Mutex is also a data-only enum member. Runtime construction, static calls,
    # threading namespaces and all the other active APIs remain forbidden.
    if any(re.search(r'\b(?:DllImport|Thread|Task|WaitHandle|EventWaitHandle|Monitor|Semaphore)\b|'
                     r'\bSystem\s*\.\s*Threading\b|\bnew\s+Mutex\b|\bMutex\s*\.', code_only(source))
           for source in [parser] + models):
        raise ValueError('The pure syntax parser and reports must not introduce native calls or perform waits or synchronization.')
    imports = re.findall(r'\[DllImport\("([^"]+)"[^\]]*\)\]\s*private static extern uint (\w+)\(', native)
    if set(imports) != {('kernel32.dll', 'EnumSystemFirmwareTables'), ('kernel32.dll', 'GetSystemFirmwareTable')} or len(imports) != 2:
        raise ValueError('Only the two reviewed Windows firmware-table read APIs are permitted.')
    for name, value in [('AcpiProvider', '0x41435049'), ('DsdtId', '0x54445344'), ('SsdtId', '0x54445353')]:
        if not re.search(r'const uint ' + name + r'\s*=\s*' + value + r'\s*;', native):
            raise ValueError('Only the ACPI provider and fixed DSDT/SSDT IDs are permitted.')
    if 'System.Management' in (project / (PROJECT + '.csproj')).read_text():
        raise ValueError('This tool must not link a live WMI provider.')
    for pattern in [r'WorkerTimeoutMilliseconds\s*=\s*10000', r'new Thread\s*\(',
                    r'Environment.Exit\(3\)', r'WaitForExit\(WorkerTimeoutMilliseconds\)', r'UseShellExecute\s*=\s*false']:
        if not re.search(pattern, host):
            raise ValueError('Both independent worker and parent time limits are required.')
    if PROJECT in (root / 'src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj').read_text():
        raise ValueError('The main app must not automatically launch this separate reader.')
    for name, expected in READ_ONLY_FOOTPRINT.items():
        if hashlib.sha256((project / name).read_bytes()).hexdigest() != expected:
            raise ValueError('The reviewed read-only provider, fixed table scope and worker footprint must remain unchanged.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-report', required=True, type=Path)
    parser.add_argument('--source-zip', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tests = json.loads(args.test_report.read_text())
    if (any(type(tests.get(k)) is not int for k in ['passed','failed','registered']) or tests['passed'] <= 0
            or tests['failed'] != 0 or tests.get('skipped',0) != 0 or tests['passed'] != tests['registered']):
        raise ValueError('A complete passing test report is required.')
    inspect_reader_sources(root)
    inspect_source_zip(root, args.source_zip)
    build = root / 'src' / PROJECT / 'bin/Release/net48'
    files = {name:(build/name).read_bytes() for name in [PROJECT+'.exe', PROJECT+'.exe.config', 'ATIVBatteryGuard.Core.dll']}
    inspect_executable(files[PROJECT+'.exe'])
    if ('Acpi-routing-v5'.encode('utf-16le') not in files[PROJECT+'.exe'] or
            any(('Acpi-routing-v'+str(v)).encode('utf-16le') in files[PROJECT+'.exe'] for v in [1,2,3,4])):
        raise ValueError('The v5 executable is required; a previous routing tool must not be distributed as the object-reference revision.')
    if (b'GetSystemFirmwareTable\0' not in files[PROJECT+'.exe'] or b'AcpiWmiRoutingInspector\0' not in files['ATIVBatteryGuard.Core.dll']
            or b'AcpiMethodFlowReport\0' not in files['ATIVBatteryGuard.Core.dll'] or b'AcpiSyntaxOperation\0' not in files['ATIVBatteryGuard.Core.dll']
            or b'AcpiObjectReferenceReport\0' not in files['ATIVBatteryGuard.Core.dll']):
        raise ValueError('The current static reader and parser binaries are required.')
    info = {'application':PROJECT, 'revision':'Acpi-routing-v5', 'target':'Windows10x64/.NETFramework4.8',
        'requestsElevation':False, 'usesOnlyWindowsAcpiTableReadApis':True,
        'evaluatesAml':False, 'invokesOemMethods':False, 'touchesExperimentReservation':False,
        'savesOrExportsRawFirmware':False, 'exportsDeviceIdentifiersOrPaths':False,
        'tables':['DSDT','first SSDT only'], 'completeSsdtCoverage':False, 'crossTableResolution':False,
        'dsdtReadIndependentOfEnumeration':True, 'readsAcpiRegistryCache':False,
        'methodFlowSyntaxSummary':True, 'readsObservedSameTableHelperDefinitions':True,
        'extendedAmlSyntaxConsumedStatically':True, 'syntaxFailuresUseFixedEnumsOnly':True,
        'executesParsedWaitsSynchronizationFatalOrConversions':False, 'dynamicNamespaceOperationsSupported':False,
        'parsedHelperObservationsAreExplicitlyScoped':True,
        'namedObjectDeclarationKinds':True, 'storeReturnDefinitionReferencesOnly':True,
        'maximumObjectRelationNamesPerBody':64, 'readsOperationRegionContents':False,
        'exportsObjectNamesAddressesOffsetsOrLengths':False, 'evaluatesAliasesValuesOrDataFlow':False,
        'fieldListSupport':['NamedField','ReservedField','AccessField','ExtendedAccessField'],
        'completeFieldListLanguageSupported':False, 'legacyMethodFlowSemanticsPreserved':True,
        'maximumHelperDepth':2, 'maximumHelperDefinitions':8, 'maximumHelperCallSites':32,
        'maximumNamespaceObjects':8192,
        'evaluatesVariablesBranchesOrArgumentMapping':False, 'helperSyntaxProvesExecutedRoute':False,
        'dsdtDirectReadPublicReference':'acpica/acpica@e85aa3bebaae81ed1e6d163511ac7e1eafe732cf/source/os_specific/service_layers/oswintbl.c',
        'completeAmlLanguageSupported':False, 'syntaxObservationsProveBatterySupport':False,
        'actualChargeControlSupported':False, 'maximumTableBytes':4194304,
        'parentTimeoutMs':10000, 'independentWorkerTimeoutMs':10000,
        'portableTests':tests, 'testsExecuteWindowsOrFirmware':False, 'windowsRuntimeTested':False,
        'previousDsdtDirectReadObserved':True, 'currentMethodFlowWindowsObserved':False,
        'previousExtendedHelperSyntaxObserved':True, 'currentObjectReferenceWindowsObserved':False,
        'digitallySigned':False, 'containsOriginalVendorBinariesOrUserReports':False,
        'sourceZipSha256':hashlib.sha256(args.source_zip.read_bytes()).hexdigest()}
    files['BUILD-INFO.json'] = json.dumps(info,ensure_ascii=False,indent=2).encode('utf-8')
    readme = '''ATIV Battery Guard — ACPI 객체·참조 관계 요약 (Acpi-routing-v5)

v4 실기에서 보조 본문1개·Acquire/Release 구문 해석과 미지원0개를 확인했습니다.
v5는 같은 테이블의 Buffer/Mutex/Field 등 관측 정의의 종류와 Store/Return의 참조 관계를 요약합니다.
같은 정의 참조 구문은 실제 값 전달·실행 순서·동일한 데이터 반환이나 하드웨어 효과를 증명하지 않습니다.
OperationRegion은 선언된 주소 공간 종류만 읽고 실제 영역을 읽거나 쓰지 않습니다.
이름·주소·오프셋·길이·식별자는 출력하거나 저장하지 않습니다. 별칭·동적 생성·중복은 보수적으로 처리합니다.
본문의 참조 관계는 고유 이름64개까지만 추적하며 초과·미분류를 관계 없음으로 바꾸지 않습니다.
기존 연결 구문 결과와 새 객체 선언 분류는 별개이며 Partial을 없애거나 제어를 활성화하는 기능이 아닙니다.
수집은 v2와 같은 고정 DSDT 직접 읽기/첫 SSDT이며, 기존 DLL/TXT를 다시 수집하지 않습니다.
보조 정의는 깊이2·최대8개·호출 표현식32개까지만 읽고 미해석·순환·한계 초과를 구분합니다.
Arg2의 직접 전달과 Return 형태는 구문 사실이며 변수 값·별칭·실행 경로를 계산하지 않습니다.
해석 완료한 보조 본문 수와 그 범위의 반환 구문만 별도로 표시합니다. 실패한 본문 중간 표식은 폐기합니다.
그 범위에서 상수FF 구문이 미관측이어도 나머지 연결의 부재·실제 응답의 위치나 의미를 입증하지 않습니다.
Load/LoadTable/Unload 등 동적 namespace 작업은 해석 불가로 닫고 실행하지 않습니다.
다른 SSDT를 얻으려고 같은 ID를 반복 조회하거나 레지스트리를 읽지 않습니다.
AML 실행, OEM 호출, 삼성 DLL 로드, 예약 접근, 드라이버·서비스·보안 변경은 없습니다.
원본 ACPI/주소/GUID 원문/장치 식별자/메서드 이름/경로는 출력하거나 파일에 저장하지 않습니다.

1. ZIP 전체를 새 로컬 폴더에 압축 해제합니다.
2. ATIVBatteryGuard.AcpiRoutingCheck.exe를 일반 권한으로 실행합니다. 관리자 실행은 요구하지 않습니다.
3. Acpi-routing-v5 표시와 출력된 새 요약만 복사해 전달하고 Enter로 닫습니다.
원본 테이블·삼성 DLL·기존 진단·이전 실행 결과는 다시 제출하지 않습니다.

Windows API는 같은 서명의 테이블 중 첫 것만 반환하므로 전체 SSDT를 읽지 못합니다.
한 테이블 내 관측된 정의의 제한된 구문만 읽습니다. 보조 메서드를 실행하거나 동작을 추정하지 않습니다.
미관측/Partial/해석 불가는 기능 부재나 미지원 판정이 아닙니다.
ID1/길이21/FF 반환 구문은 존재 여부이며 실제 분기의 실행이나 배터리 명령 의미를 입증하지 않습니다.
충전 제어는 계속 미지원입니다. 기존 1회 실험 재실행이나 예약 표식 삭제를 하지 마세요.
새 도구의 Windows 실기는 아직 미검증입니다. 삼성 원본 바이너리는 포함하지 않습니다.
프로그램의 인터넷 통신은 없습니다. 보호 기능을 해제하거나 우회하지 않습니다.
'''
    files['먼저 읽어주세요.txt'] = readme.replace('\n','\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name,data in sorted(files.items())).encode()
    args.output.mkdir(parents=True,exist_ok=True)
    target = args.output/'ATIVBatteryGuard-ACPI-OBJECT-REFERENCES.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()): archive.writestr(name,data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None: raise ValueError('ZIP CRC failed.')
    print(json.dumps({'file':str(target),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))


if __name__ == '__main__': main()
