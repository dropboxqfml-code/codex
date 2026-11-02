"""Package only the independent asInvoker fixed-query permission-check tool."""
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
    project = root / "src/ATIVBatteryGuard.WmiAccessCheck"
    manifest = ET.parse(project / "app.manifest")
    level = manifest.find(".//{urn:schemas-microsoft-com:asm.v3}requestedExecutionLevel")
    if level is None or level.attrib != {"level": "asInvoker", "uiAccess": "false"}:
        raise ValueError("This preview must remain asInvoker without UIAccess.")
    build = project / "bin/Release/net48"
    names = ["ATIVBatteryGuard.WmiAccessCheck.exe", "ATIVBatteryGuard.Core.dll"]
    config = "ATIVBatteryGuard.WmiAccessCheck.exe.config"
    if (build / config).exists():
        names.append(config)
    files = {name: (build / name).read_bytes() for name in names}
    executable = files["ATIVBatteryGuard.WmiAccessCheck.exe"]
    if b'asInvoker' not in executable or b'requireAdministrator' in executable or b'highestAvailable' in executable:
        raise ValueError("The built executable must retain the asInvoker manifest.")
    with zipfile.ZipFile(args.source_zip) as source:
        if source.testzip() is not None or not any(name.endswith("/WmiAccessCheck/Program.cs") or
            name.endswith("/ATIVBatteryGuard.WmiAccessCheck/Program.cs") for name in source.namelist()):
            raise ValueError("Matching helper source archive is required.")
        if any(Path(name).suffix.lower() in {".exe", ".dll", ".txt"} for name in source.namelist()):
            raise ValueError("Source archive cannot contain original binaries or TXT reports.")
    info = {
        "application": "ATIV Battery Guard WMI Access Check",
        "target": "Windows10x64/.NETFramework4.8",
        "requestedExecutionLevel": "asInvoker",
        "requestsUacOrElevation": False,
        "mainApplicationLaunchesTool": False,
        "consoleOutputOnly": True,
        "acceptsArbitraryQueriesCommandsOrPaths": False,
        "authentication": "PacketPrivacy",
        "enablePrivileges": False,
        "queryNamespace": r"ROOT\WMI",
        "queries": ["SELECT Active,version FROM WmiAcpiVersion", "SELECT Active FROM WmiAcpiMethod"],
        "maximumInstancesPerClass": 8,
        "workerTimeoutMs": 10000,
        "maximumOutputCharacters": 32768,
        "printsUserNamesSidsInstanceKeysOrPaths": False,
        "invokesOemMethodsOrChangesServicesAclFirmware": False,
        "containsOriginalVendorBinariesOrUserReports": False,
        "actualChargeControlSupported": False,
        "windowsRuntimeTested": False,
        "administratorComparisonApprovedAtPackaging": False,
        "digitallySigned": False,
        "portableTests": tests,
        "matchingSourceZipSha256": sha(args.source_zip.read_bytes()),
    }
    files["BUILD-INFO.json"] = json.dumps(info, ensure_ascii=False, indent=2).encode("utf-8")
    instructions = """ATIV Battery Guard — 고정 WMI 읽기 권한 비교 도구

이 도구는 별도의 검토용 asInvoker 프로그램입니다. 메인 앱에서 실행하지 않으며 UAC를 요청하거나 스스로 권한을 올리지 않습니다.
현재 프로세스 토큰 상승 상태와 같은 두 WMI 속성 조회의 진행/실패 단계만 출력합니다.
일반 권한의 실행 자체는 가능합니다. 관리자 비교 실행에 대한 승인은 아직 받지 않았으므로 그 실행은 보류합니다.
원하는 결과를 얻기 위해 서비스·드라이버·ACL·보안 설정을 바꾸지 않습니다.

조회: ROOT\\WMI의 WmiAcpiVersion.Active/version 및 WmiAcpiMethod.Active.
최대 각 8개, PacketPrivacy, EnablePrivileges=false, 자체 조회 프로세스 10초 제한입니다.
현재 토큰의 Elevated/NotElevated/Unknown을 보여주며 관리자 그룹 소속을 권한 상승 여부로 대신하지 않습니다.
거부 단계와 고정 오류 분류는 원인을 확정하지 않습니다. 관리자 토큰이어도 조회 성공을 보장하지 않습니다.
사용자 이름·SID·인스턴스 이름·장치 식별자·경로·원문 오류는 기록하지 않습니다.
임의 파일 경로·쿼리·명령 인수는 받지 않습니다. 자체 내부 작업자 모드는 직접 실행용이 아닙니다.
화면 출력만 사용하며 결과 파일·서비스·드라이버를 만들거나 삼성 DLL/OEM 메서드·펌웨어 쓰기를 실행하지 않습니다.
실제 충전 제어는 계속 미지원입니다. 삼성 원본 바이너리와 사용자 TXT는 포함하지 않습니다.
Windows 실기 실행은 아직 미검증인 미서명 개발 도구입니다.
ZIP을 로컬 폴더에 모두 풀어 사용하며 EXE와 Core DLL은 함께 유지합니다.
"""
    files["먼저 읽어주세요.txt"] = instructions.replace("\n", "\r\n").encode("utf-8-sig")
    files["SHA256SUMS.txt"] = "".join(sha(data) + "  " + name + "\n" for name, data in sorted(files.items())).encode()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "ATIVBatteryGuard-WMI-PERMISSION-REVIEW.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP CRC check failed.")
    print(json.dumps({"file": str(target), "bytes": target.stat().st_size, "sha256": sha(target.read_bytes())}))


if __name__ == "__main__":
    main()
