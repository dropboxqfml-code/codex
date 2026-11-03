"""Package the explicitly approved, fixed one-attempt experiment only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-report", type=Path, required=True)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tests = json.loads(args.test_report.read_text(encoding="utf-8"))
    if tests["passed"] <= 0 or tests["failed"] or tests.get("skipped", 0) or tests["passed"] != tests["registered"]:
        raise ValueError("A complete passing test report is required.")
    if not (root / "WMI_ONE_SHOT_QUERY_APPROVAL.md").is_file():
        raise ValueError("The explicit approval record must accompany this experiment.")
    project = root / "src/ATIVBatteryGuard.WmiOneShotQuery"
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
    host = (project / "Program.cs").read_text(encoding="utf-8")
    if "Environment.Exit(3)" not in host or "new Thread" not in host or "WorkerTimeoutMilliseconds = 10000" not in host:
        raise ValueError("Both parent and worker lifetime guards are required.")

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
    with zipfile.ZipFile(args.source_zip) as source:
        if source.testzip() is not None:
            raise ValueError("Source ZIP CRC failed.")
        required = "ATIVBatteryGuard/src/ATIVBatteryGuard.WmiOneShotQuery/WindowsOneShotBackend.cs"
        if required not in source.namelist():
            raise ValueError("The exact matching experiment source is required.")
        for name in source.namelist():
            path = Path(name)
            if path.parts[0] != "ATIVBatteryGuard" or path.is_absolute() or ".." in path.parts:
                raise ValueError("Unexpected source path.")
            if path.suffix.lower() in {".exe", ".dll", ".txt", ".json", ".log", ".zip", ".aml"}:
                raise ValueError("No original binaries or raw reports belong in source.")
            if source.read(name) != (root.parent / path).read_bytes():
                raise ValueError("Source ZIP must match current files.")

    info = {
        "application": "ATIV Battery Guard Approved WMI One-Shot Query",
        "target": "Windows10x64/.NETFramework4.8",
        "approvalDateKorea": "2026-11-03",
        "explicitOwnerApprovalRecorded": True,
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

이 파일은 일반 배터리 표시 앱과 분리된 미서명 실험 도구입니다.
사용자가 승인한 조회 후보 0x65 한 번만 시도하며 실제 충전 제어는 미지원입니다.
현재 모델에서 후보 의미와 펌웨어 부작용은 아직 검증되지 않았습니다.

1. ZIP 전체를 메인 앱과 다른 새 로컬 폴더에 압축 해제합니다.
2. 같은 Windows 계정에서 ATIVBatteryGuard.WmiOneShotQuery.exe를 오른쪽 클릭하여 관리자 권한으로 한 번 실행합니다.
   다른 관리자 계정의 암호를 요구하면 중단합니다. 자동 UAC·권한 상승 코드는 없습니다.
3. 창의 출력만 복사해 전달하고 Enter로 닫습니다. 과거 TXT·삼성 DLL·파일 목록·권한 비교는 다시 필요하지 않습니다.
4. 호출 요청·시간 초과·결과 불명 이후에는 재실행하지 마세요. 로컬 1회 예약 표식을 삭제하지 마세요.
   이 프로그램에는 예약 초기화나 다른 명령 입력 기능이 없습니다.

일반 실행으로 Elevated가 확인되지 않으면 OEM 호출하지 않습니다.
모델/BIOS, 고정 메타데이터, 메서드 번호1, 전체 조회 완료·정확히 한 행·Active=True,
입력 준비, 영속 예약 중 하나라도 충족되지 않으면 호출하지 않습니다.
실제 호출 직전 고정 예약 표식만 로컬 앱 데이터에 저장합니다.
기존 표식이 있거나 예약을 안전하게 쓸 수 없으면 추가 호출하지 않습니다.
오류·재부팅·다른 폴더에 재압축 해제해도 같은 계정의 표식을 복구·삭제하지 않습니다.

실험은 후보 0x65와 고정 입력80+15개00만 사용합니다. 설정 명령0x66, 다른 명령 탐색,
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
    target = args.output / "ATIVBatteryGuard-WMI-ONE-SHOT-QUERY.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError("Executable ZIP CRC failed.")
    print(json.dumps({"file": str(target), "bytes": target.stat().st_size, "sha256": sha(target.read_bytes())}))


if __name__ == "__main__":
    main()
