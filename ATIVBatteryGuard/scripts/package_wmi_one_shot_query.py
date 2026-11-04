"""Package the explicitly approved, fixed one-attempt experiment only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
import zipfile

from package_wmi_preflight_check import inspect_locator_scope, inspect_source_zip


EXPERIMENT_REVISION = "Query65-locator-v2"
PROJECT_NAME = "ATIVBatteryGuard.WmiOneShotQuery"
# Reviewed commit 55f09c6. The locator preparation fix must not alter the
# approved request, claim identity, dispatch, callback handling or host guards.
FROZEN_FILES = {
    "src/ATIVBatteryGuard.Core/Services/WsabiWmiOneShotPolicy.cs":
        "4b66af5f6f70e2f83ed6f0df761735005b900c969592772bede1c92ab06a1f1e",
    "src/ATIVBatteryGuard.Core/Services/WsabiWmiOneShotExperiment.cs":
        "66bdf53ca79c0e1c564ee03cb40f26e2ad031860064205abac9b987d4be0caf6",
    "src/ATIVBatteryGuard.Core/Storage/WsabiWmiOneShotFileReservation.cs":
        "135ef5d7f499ef5245d97eb2ea42111df01d3de2517376105bb35b06872a95a1",
    "src/ATIVBatteryGuard.WmiOneShotQuery/OneShotResultCapture.cs":
        "1fcacdb4f34e339fc2364711dfaae5e9b0acd15fefb70155d3ba0a2cab126984",
}
FROZEN_NATIVE_SHA256 = "d29fc245db94e6090c213094cfbebf87125d51c1057b256f6aa9e10ce09c1402"
FROZEN_HOST_SHA256 = "c97b5a10d4cc6a9bcec923734eeb004439399e700faef0a992a683e74c71e640"
FROZEN_DISPATCH_SHA256 = "436eb2d4c67cec51a63d6034ca1f937797cb9c10bcd5747e37245b33481961f9"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(source, new, previous):
    if source.count(new) != 1:
        raise ValueError("Only the reviewed locator preparation and revision changes may be packaged.")
    return source.replace(new, previous, 1)


def inspect_sources(root):
    if not (root / "WMI_ONE_SHOT_QUERY_APPROVAL.md").is_file():
        raise ValueError("The explicit approval record must accompany this experiment.")
    project = root / "src" / PROJECT_NAME
    manifest = ET.parse(project / "app.manifest")
    level = manifest.find(".//{urn:schemas-microsoft-com:asm.v3}requestedExecutionLevel")
    if level is None or level.attrib != {"level": "asInvoker", "uiAccess": "false"}:
        raise ValueError("Automatic elevation is outside the approved scope.")
    if "WmiOneShotQuery" in (root / "src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj").read_text():
        raise ValueError("The main application must not reference this separate experiment.")
    native = (project / "WindowsOneShotBackend.cs").read_text(encoding="utf-8")
    if len(re.findall(r"selectedTarget\.InvokeMethod\s*\(", native)) != 1:
        raise ValueError("The backend must have one fixed SDK invocation site.")
    if re.search(r"\.(Put|Delete|StartService|StopService)\s*\(", native):
        raise ValueError("Repository and service changes are outside this experiment.")
    inspect_locator_scope(native)
    start = "        public async Task<WsabiWmiMethodSnapshot> ExchangeAsync"
    end = "        private string ReadSingleString"
    if native.count(start) != 1 or native.count(end) != 1:
        raise ValueError("The reviewed dispatch and output extraction region is required.")
    dispatch = native[native.index(start):native.index(end)]
    if sha(dispatch.encode("utf-8")) != FROZEN_DISPATCH_SHA256:
        raise ValueError("The approved dispatch, callbacks and output extraction must remain unchanged.")
    previous_native = replace_once(native, "CreateEnumerationOptions(ensureLocatable: true)",
                                   "CreateEnumerationOptions()")
    previous_native = replace_once(previous_native,
        "CreateEnumerationOptions(bool ensureLocatable = false)", "CreateEnumerationOptions()")
    previous_native = replace_once(previous_native,
        "ReturnImmediately = true, DirectRead = true, EnsureLocatable = ensureLocatable",
        "ReturnImmediately = true, DirectRead = true")
    if sha(previous_native.encode("utf-8")) != FROZEN_NATIVE_SHA256:
        raise ValueError("Native changes beyond the reviewed method-query locator option are outside this revision.")
    host = (project / "Program.cs").read_text(encoding="utf-8")
    if "Environment.Exit(3)" not in host or "new Thread" not in host or "WorkerTimeoutMilliseconds = 10000" not in host:
        raise ValueError("Both parent and worker lifetime guards are required.")
    previous_host = replace_once(host,
        '        private const string ExperimentRevision = "Query65-locator-v2";\n', "")
    previous_host = replace_once(previous_host,
        '            Console.WriteLine("수정판: 승인된 단1회 조회 · 경로 정보 확보 보완 (" + ExperimentRevision + ")");\n', "")
    if sha(previous_host.encode("utf-8")) != FROZEN_HOST_SHA256:
        raise ValueError("Host changes beyond the fixed revision display are outside this revision.")
    for name, expected in FROZEN_FILES.items():
        if sha((root / name).read_bytes()) != expected:
            raise ValueError("The approved request, reservation, experiment and callback policies must remain unchanged.")


def inspect_build(executable):
    if b"set_EnsureLocatable\0" not in executable or EXPERIMENT_REVISION.encode("utf-16-le") not in executable:
        raise ValueError("The built EXE must be the Query65-locator-v2 revision, not a previous experiment or preflight checker.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-report", type=Path, required=True)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if (root / "WMI_ONE_SHOT_QUERY_RESULT.md").is_file():
        raise ValueError("The approved one-shot request has been completed. Further OEM executable distribution is closed.")
    tests = json.loads(args.test_report.read_text(encoding="utf-8"))
    for key in ("passed", "failed", "registered"):
        if type(tests.get(key)) is not int:
            raise ValueError("A complete integer-count test report is required.")
    if type(tests.get("skipped", 0)) is not int or tests["passed"] <= 0 or tests["failed"] or tests.get("skipped", 0) or tests["passed"] != tests["registered"]:
        raise ValueError("A complete passing test report is required.")
    inspect_sources(root)
    inspect_source_zip(root, args.source_zip)
    project = root / "src" / PROJECT_NAME

    build = project / "bin/Release/net48"
    names = ["ATIVBatteryGuard.WmiOneShotQuery.exe", "ATIVBatteryGuard.Core.dll"]
    config = "ATIVBatteryGuard.WmiOneShotQuery.exe.config"
    if (build / config).exists():
        names.append(config)
    files = {name: (build / name).read_bytes() for name in names}
    executable = files[names[0]]
    if executable[:2] != b"MZ":
        raise ValueError("A real built executable is required.")
    pe = struct.unpack_from("<I", executable, 0x3c)[0]
    if executable[pe:pe + 4] != b"PE\0\0" or struct.unpack_from("<H", executable, pe + 4)[0] != 0x8664:
        raise ValueError("The separate executable must be x64.")
    if b"asInvoker" not in executable or b"requireAdministrator" in executable or b"highestAvailable" in executable:
        raise ValueError("The built executable must remain asInvoker.")
    inspect_build(executable)

    info = {
        "application": "ATIV Battery Guard Approved WMI One-Shot Query",
        "target": "Windows10x64/.NETFramework4.8",
        "approvalDateKorea": "2026-11-03",
        "explicitOwnerApprovalRecorded": True,
        "experimentRevision": EXPERIMENT_REVISION,
        "ensuresMethodTargetLocatable": True,
        "locatorOptionChangesOnlyMethodTargetQuery": True,
        "samePersistentClaim": True,
        "readsPreflightResultFileAsAuthorization": False,
        "rechecksPreflightAtExecution": True,
        "protectedPoliciesAndDispatchMatchReviewedSource": True,
        "requestedExecutionLevel": "asInvoker",
        "requiresOwnerManualSameAccountAdministratorRun": True,
        "requestsUacOrElevation": False,
        "mainApplicationLaunchesTool": False,
        "expectedModel": "940X3G/930X3G",
        "expectedBios": "P05ACJ.128.140819.dg",
        "requiresCompleteFixedSchemaAndExactlyOneActiveInstance": True,
        "observedWindowsMethodIdRequired": 1,
        "fixedMethod": "ROOT\\WMI/WmiAcpiMethod.CallSabiFunction",
        "candidateCommand": "0x65",
        "requestBytes": "43 58 65 00 00 80 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
        "maximumSdkInvocationAttempts": 1,
        "automaticRetries": 0,
        "persistentClaimBeforeInvocation": True,
        "claimFileName": "WmiQuery65-v1.attempt",
        "claimResetOrDeletionImplemented": False,
        "claimProtectsAgainstDeliberateTamperingOrOtherAccounts": False,
        "asyncCompletionStatusMustBeZeroBeforeReadingOutput": True,
        "asyncCompletionIsNotImmediateExecMethodHresult": True,
        "parentWorkerTimeoutMs": 10000,
        "independentWorkerWatchdogMs": 10000,
        "preflightBudgetMs": 6000,
        "maximumDetachedBytes": 4096,
        "maximumOutputCharacters": 32768,
        "authentication": "PacketPrivacy",
        "enablePrivileges": False,
        "executesFixedOemCandidate": True,
        "candidateMeaningAndFirmwareSideEffectsVerified": False,
        "outputsProtectionModeOrRawPayload": False,
        "implementsServiceDriverAclOrFirmwareSettingWrites": False,
        "unexpectedFirmwareSideEffectsExcluded": False,
        "containsOriginalVendorBinariesOrRawUserReports": False,
        "actualChargeControlSupported": False,
        "portableTests": tests,
        "testsExecuteWindowsOrFirmware": False,
        "windowsRuntimeTested": False,
        "digitallySigned": False,
        "matchingSourceZipSha256": sha(args.source_zip.read_bytes()),
    }
    files["BUILD-INFO.json"] = json.dumps(info, ensure_ascii=False, indent=2).encode("utf-8")
    instructions = """ATIV Battery Guard — 승인된 1회 WMI 조회 후보 실험
수정판: 승인된 단1회 조회 · 경로 정보 확보 보완 (Query65-locator-v2)

이 파일은 일반 배터리 표시 앱과 분리된 미서명 실험 도구입니다.
앞선 무호출 점검 도구와 달리, 조건이 모두 맞으면 OEM 조회 후보를 실제로 요청할 수 있습니다.
기존 명시적 승인 범위의 고정 후보 0x65 최대1회만 시도하며 실제 충전 제어는 미지원입니다.
현재 모델에서 후보 의미와 펌웨어 부작용은 아직 검증되지 않았습니다.

1. ZIP 전체를 메인 앱·이전 실험·무호출 점검 도구와 다른 새 로컬 폴더에 압축 해제합니다.
2. 같은 Windows 계정에서 새 폴더의 ATIVBatteryGuard.WmiOneShotQuery.exe만 관리자 권한으로 한 번 실행합니다.
   다른 관리자 계정의 암호를 요구하면 중단합니다. 자동 UAC·권한 상승 코드는 없습니다.
3. Query65-locator-v2 표시와 새 출력만 복사해 전달하고 Enter로 닫습니다.
   과거 TXT·삼성 DLL·파일 목록·권한 비교는 다시 필요하지 않습니다.
4. 호출 요청·오류·시간 초과·결과 불명 이후에는 재실행하지 마세요. 로컬 1회 예약 표식을 삭제하지 마세요.
   이 프로그램에는 예약 초기화나 다른 명령 입력 기능이 없습니다.

일반 실행으로 Elevated가 확인되지 않으면 OEM 호출하지 않습니다.
이전 Ready TXT를 입력값이나 승인 표식으로 사용하지 않고 실행 시 모든 준비 조건을 다시 검사합니다.
모델/BIOS, 고정 메타데이터, 메서드 번호1, 전체 조회 완료·정확히 한 행·Active=True,
입력 준비, 영속 예약 중 하나라도 충족되지 않으면 호출하지 않습니다.
실제 호출 직전 고정 예약 표식만 로컬 앱 데이터에 저장합니다.
기존과 같은 ATIVBatteryGuard\\Experiments의 WmiQuery65-v1.attempt를 사용합니다.
기존 표식이 있거나 예약을 안전하게 쓸 수 없으면 추가 호출하지 않습니다.
오류·재부팅·다른 폴더에 재압축 해제해도 같은 계정의 표식을 복구·삭제하지 않습니다.
표식의 이름·위치 변경이나 우회로 추가 호출을 허용하지 않습니다.

실험은 후보 0x65와 고정 입력0x80+15개0x00만 사용합니다. 0x80을 충전 상한80%로 해석하지 않습니다.
설정 명령0x66, 다른 명령 탐색,
삼성 DLL, SABI 장치/포트 I/O, 드라이버·서비스·ACL·보안 설정 변경은 구현하지 않습니다.
프로그램의 인터넷 통신은 없습니다. 보안 제품이 차단하면 보호를 해제하거나 우회하지 마세요.
부모와 작업자는 각각10초 제한을 사용합니다. 종료가 이미 시작된 펌웨어 동작의 취소·복구를 보장하지는 않습니다.

후보 표식0/1/FF/Other는 실제 보호OFF/ON/미지원 판정이 아닙니다.
어떤 결과에서도 메인 앱 제어를 활성화하거나 충전 상한80%/100% 성공으로 표시하지 않습니다.
실제 응답 전체, 사용자 이름·SID·시리얼·인스턴스 이름·경로·원문 오류는 출력·저장하지 않습니다.
새 도구의 Windows 실기 실행은 아직 미검증입니다. 삼성 원본 바이너리는 포함하지 않습니다.
"""
    files["먼저 읽어주세요.txt"] = instructions.replace("\n", "\r\n").encode("utf-8-sig")
    files["SHA256SUMS.txt"] = "".join(sha(data) + "  " + name + "\n" for name, data in sorted(files.items())).encode()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "ATIVBatteryGuard-WMI-ONE-SHOT-LOCATOR.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files):
            raise ValueError("Executable ZIP integrity or allowlist check failed.")
    print(json.dumps({"file": str(target), "bytes": target.stat().st_size, "sha256": sha(target.read_bytes())}))


if __name__ == "__main__":
    main()
