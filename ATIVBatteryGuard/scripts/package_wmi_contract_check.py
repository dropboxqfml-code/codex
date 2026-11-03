"""Package the asInvoker class-definition contract checker, never OEM code."""
import argparse
import hashlib
import json
from pathlib import Path
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
    project = root / "src/ATIVBatteryGuard.WmiContractCheck"
    level = ET.parse(project / "app.manifest").find(
        ".//{urn:schemas-microsoft-com:asm.v3}requestedExecutionLevel")
    if level is None or level.attrib != {"level": "asInvoker", "uiAccess": "false"}:
        raise ValueError("The contract checker must remain asInvoker.")
    build = project / "bin/Release/net48"
    names = ["ATIVBatteryGuard.WmiContractCheck.exe", "ATIVBatteryGuard.Core.dll"]
    config = "ATIVBatteryGuard.WmiContractCheck.exe.config"
    if (build / config).exists():
        names.append(config)
    files = {name: (build / name).read_bytes() for name in names}
    executable = files["ATIVBatteryGuard.WmiContractCheck.exe"]
    if b"asInvoker" not in executable or b"requireAdministrator" in executable or b"highestAvailable" in executable:
        raise ValueError("The built executable must retain its asInvoker manifest.")
    with zipfile.ZipFile(args.source_zip) as source:
        if source.testzip() is not None or not any(name.endswith(
            "/ATIVBatteryGuard.WmiContractCheck/Program.cs") for name in source.namelist()):
            raise ValueError("Matching contract-checker source is required.")
        if any(Path(name).suffix.lower() in {".exe", ".dll", ".txt"} for name in source.namelist()):
            raise ValueError("Source cannot contain original binaries or TXT reports.")
    info = {
        "application": "ATIV Battery Guard WMI Contract Check",
        "target": "Windows10x64/.NETFramework4.8",
        "requestedExecutionLevel": "asInvoker",
        "requestsUacOrElevation": False,
        "mainApplicationLaunchesTool": False,
        "consoleOutputOnly": True,
        "acceptsArbitraryQueriesCommandsOrPaths": False,
        "authentication": "PacketPrivacy",
        "enablePrivileges": False,
        "namespace": r"ROOT\WMI",
        "fixedClasses": ["WmiAcpiMethod", "DataBuffer"],
        "fixedMethodDefinition": "CallSabiFunction",
        "qualifierAllowlist": ["Guid", "WmiMethodId", "EmbeddedInstance"],
        "fieldDefinitionAllowlist": ["inData", "outData", "Bytes"],
        "printsActualGuid": False,
        "readsInstancesOrInstanceProperties": False,
        "readsElevationSidsNamesOrSecurityDescriptors": False,
        "executesWmiMethods": False,
        "workerTimeoutMs": 10000,
        "maximumOutputCharacters": 32768,
        "changesServicesAclDriversOrFirmware": False,
        "containsOriginalVendorBinariesOrRawUserReports": False,
        "actualChargeControlSupported": False,
        "windowsRuntimeTested": False,
        "digitallySigned": False,
        "portableTests": tests,
        "matchingSourceZipSha256": sha(args.source_zip.read_bytes()),
    }
    files["BUILD-INFO.json"] = json.dumps(info, ensure_ascii=False, indent=2).encode("utf-8")
    instructions = """ATIV Battery Guard — WMI 정적 전송 규약 확인 도구

1. ZIP 전체를 메인 앱과 다른 로컬 폴더에 압축 해제합니다.
2. ATIVBatteryGuard.WmiContractCheck.exe를 일반적으로 더블클릭합니다. 관리자 실행은 요청하지 않습니다.
3. 클래스 GUID의 공개 후보 일치 여부, WmiMethodId, 입출력 정의와 DataBuffer.Bytes 정의가 표시됩니다.
4. 출력 내용을 복사한 뒤 Enter로 닫습니다. 기존 배터리 진단·삼성 파일 목록·DLL은 다시 필요하지 않습니다.

이 도구는 로컬 ROOT\\WMI의 WmiAcpiMethod와 DataBuffer 클래스 정의만 읽습니다.
Guid·WmiMethodId·EmbeddedInstance qualifier와 고정 필드의 형식만 조회합니다.
실제 GUID 값·인스턴스 이름·사용자 이름·SID·경로·예외 원문은 표시하지 않습니다.
인스턴스나 Active/version 값, 토큰 상승 여부, ACL은 읽지 않습니다.
CallSabiFunction은 정의만 읽으며 실행하지 않습니다. DataBuffer 내용도 읽지 않습니다.
관리자 권한 상승·삼성 DLL·OEM 명령·드라이버/서비스/ACL·펌웨어 변경은 없습니다.
일치 결과가 나오더라도 인스턴스 연계·배터리 명령의 의미나 안전성·충전 제어 지원은 미검증입니다.
클래스별 결과와 누락·권한 거부·시간 초과를 구분합니다. 실패 시 보안 설정을 바꾸거나 권한을 올려 재시도하지 않습니다.
인수 없는 일반 실행 경로에서 자체 작업자를 10초로 제한하고 출력은 콘솔에만 표시합니다.
내부 작업자 인수는 부모 전용이며 임의 파일 경로·쿼리·서버·명령을 받지 않습니다.
새 도구의 Windows 실기 실행은 아직 미검증인 미서명 개발판입니다.
삼성 원본 바이너리·사용자 원문 보고서는 포함하지 않습니다. 실제 충전 제어는 계속 미지원입니다.
"""
    files["먼저 읽어주세요.txt"] = instructions.replace("\n", "\r\n").encode("utf-8-sig")
    files["SHA256SUMS.txt"] = "".join(sha(data) + "  " + name + "\n" for name, data in sorted(files.items())).encode()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "ATIVBatteryGuard-WMI-CONTRACT-CHECK.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP CRC check failed.")
    print(json.dumps({"file": str(target), "bytes": target.stat().st_size, "sha256": sha(target.read_bytes())}))


if __name__ == "__main__":
    main()
