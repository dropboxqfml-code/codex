"""Package the main application's offline experiment-result review only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from package_wmi_preflight_check import code_only, inspect_executable, inspect_source_zip


APPLICATION_NAME = "ATIVBatteryGuard"
REVIEW_REVISION = "Offline-result-review-v1"
REVIEW_TYPES = ("WsabiWmiExperimentReview", "WsabiWmiExperimentReviewParser")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bounded_section(source, start, end):
    if source.count(start) != 1 or source.count(end) != 1 or source.index(start) >= source.index(end):
        raise ValueError("The reviewed offline result sections are required.")
    return source[source.index(start):source.index(end)]


def inspect_review_sources(root):
    project = root / "src/ATIVBatteryGuard.App"
    level = ET.parse(project / "app.manifest").find(
        ".//{urn:schemas-microsoft-com:asm.v3}requestedExecutionLevel")
    if level is None or level.attrib != {"level": "asInvoker", "uiAccess": "false"}:
        raise ValueError("The main application must retain its ordinary-user manifest.")
    if "WmiOneShotQuery" in (project / "ATIVBatteryGuard.App.csproj").read_text(encoding="utf-8"):
        raise ValueError("The main application must not reference the OEM experiment project.")
    model = (root / "src/ATIVBatteryGuard.Core/Models/WsabiWmiExperimentReview.cs").read_text(encoding="utf-8")
    parser = (root / "src/ATIVBatteryGuard.Core/Services/WsabiWmiExperimentReviewParser.cs").read_text(encoding="utf-8")
    viewmodel = (project / "ViewModels/MainViewModel.cs").read_text(encoding="utf-8")
    sections = [model, parser,
                bounded_section(viewmodel, "public string ExperimentReviewInput", "public bool SamsungFileInspectionBusy"),
                bounded_section(viewmodel, "public void ReviewExperimentResult()", "private void SelectMode(")]
    forbidden = re.compile(
        r'\b(?:InvokeMethod|TryClaim|WindowsOneShotBackend|WsabiWmiOneShotExperiment|'
        r'WsabiWmiOneShotFileReservation|ManagementObject|ManagementClass|ManagementScope|'
        r'DllImport|LoadLibrary|DeviceIoControl|FileStream|StreamWriter|HttpClient|WebClient|'
        r'WebRequest|Socket|Process|File|Directory|Registry|Clipboard|LocalLog|SettingsStore|'
        r'physical|settings|log|interaction|battery|hardwareDiagnostics|samsungFiles|store|'
        r'CurrentController|SelectMode|Apply)\b')
    for section in sections:
        if forbidden.search(code_only(section)):
            raise ValueError("Offline result review must not access hardware, reservation, storage or app controls.")
    for capability in ("CanReadHardware", "CanWriteHardware", "CanInvokeMethods"):
        if not re.search(r'\b' + capability + r'\s*=>\s*false\s*;', code_only(model)):
            raise ValueError("Historical text must never grant hardware capabilities.")
    if not re.search(r'\bphysical\s*=\s*new\s+UnsupportedChargeLimitController\s*\(\s*\)', code_only(viewmodel)):
        raise ValueError("The main application's physical controller must remain unsupported.")
    if not re.search(r'\bMaximumCharacters\s*=\s*8192\s*;', code_only(parser)):
        raise ValueError("The historical text input bound must remain in place.")
    review_action = bounded_section(viewmodel, "public void ReviewExperimentResult()", "private void ClearExperimentReview()")
    if not re.search(r'\bexperimentReviewInput\s*=\s*string\.Empty\s*;', code_only(review_action)):
        raise ValueError("The original pasted text must be cleared after review.")


def inspect_review_build(executable, core):
    if b"ReviewExperimentResult\0" not in executable:
        raise ValueError("The built application must include the offline review action.")
    if any(name.encode("ascii") + b"\0" not in core for name in REVIEW_TYPES):
        raise ValueError("The built Core DLL must contain the offline review model and parser.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-report", type=Path, required=True)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tests = json.loads(args.test_report.read_text(encoding="utf-8"))
    if any(type(tests.get(key)) is not int for key in ("passed", "failed", "registered")):
        raise ValueError("A complete integer-count test report is required.")
    if (type(tests.get("skipped", 0)) is not int or tests["passed"] <= 0 or tests["failed"] != 0
            or tests.get("skipped", 0) != 0 or tests["passed"] != tests["registered"]):
        raise ValueError("A complete passing test report without skipped tests is required.")
    inspect_review_sources(root)
    inspect_source_zip(root, args.source_zip)
    build = root / "src/ATIVBatteryGuard.App/bin/Release/net48"
    names = [APPLICATION_NAME + ".exe", APPLICATION_NAME + ".Core.dll", APPLICATION_NAME + ".exe.config"]
    files = {name: (build / name).read_bytes() for name in names}
    inspect_executable(files[APPLICATION_NAME + ".exe"])
    inspect_review_build(files[APPLICATION_NAME + ".exe"], files[APPLICATION_NAME + ".Core.dll"])
    info = {
        "application": "ATIV Battery Guard Offline Experiment Result Review",
        "target": "Windows10x64/.NETFramework4.8",
        "reviewRevision": REVIEW_REVISION,
        "requestedExecutionLevel": "asInvoker",
        "requiresAdministrator": False,
        "requestsUacOrElevation": False,
        "offlineExperimentReviewIncluded": True,
        "reviewAcceptsUserPastedHistoricalTextOnly": True,
        "reviewAuthenticatesTextOrMatchesCurrentDevice": False,
        "reviewInvokesOemMethods": False,
        "reviewPerformsAdditionalWmiQueries": False,
        "reviewTouchesOneShotReservation": False,
        "reviewSavesOriginalText": False,
        "reviewGrantsHardwareCapabilities": False,
        "mainApplicationBatteryAndReadOnlyDiagnosticsRemainAvailable": True,
        "mainApplicationInvokesOemMethods": False,
        "mainApplicationLaunchesExperiment": False,
        "previousOwnerReportedExample": {
            "source": "owner-reported historical one-shot output; not current-device state",
            "responseFrame": "ValidFrame",
            "candidateMarker": "FF",
            "protectionMeaning": "Unknown",
            "candidateSupport": "Unconfirmed",
        },
        "inferredProtection": "Unknown",
        "candidateSupport": "Unconfirmed",
        "actualChargeControlSupported": False,
        "containsOriginalVendorBinariesOrRawUserReports": False,
        "containsExperimentExecutable": False,
        "exeForbiddenTypeAndMemberReferencesAbsent": True,
        "portableTests": tests,
        "testsExecuteWindowsOrFirmware": False,
        "currentWindowsGuiRuntimeTested": False,
        "digitallySigned": False,
        "matchingSourceZipSha256": sha(args.source_zip.read_bytes()),
    }
    files["BUILD-INFO.json"] = json.dumps(info, ensure_ascii=False, indent=2).encode("utf-8")
    instructions = """ATIV Battery Guard — 과거 WMI 실험 결과 오프라인 검토

이 파일은 일반 배터리 표시 앱에 기존 실험 결과 검토를 추가한 개발판입니다.
ATIVBatteryGuard.exe를 일반 권한으로 실행합니다. 관리자 권한은 필요하지 않습니다.
새 노트북 실험이나 OEM 호출을 할 필요가 없으며 실험 실행 파일도 포함하지 않습니다.

1. ZIP 전체를 새 로컬 폴더에 압축 해제하고 ATIVBatteryGuard.exe를 실행합니다.
2. 원하는 경우 앱의 '과거 WMI 실험 결과 검토'에 이미 받은 콘솔 출력을 붙여넣고 검토합니다.
   결과를 새로 만들기 위해 1회 실험 프로그램을 다시 실행하지 마세요.
3. 검토는 붙여넣은 텍스트를 고정 상태로 해석합니다. 원문 입력은 검토 후 비우며 저장하지 않습니다.
   과거 TXT·삼성 DLL·EXE·기존 진단을 다시 제출할 필요가 없습니다.

과거 텍스트의 진위나 현재 장치와의 일치는 검증하지 않습니다.
ValidFrame은 전송 응답 형식 검증이며 FF와 0/1은 보호 OFF/ON 또는 기능 미지원 판정이 아닙니다.
배터리 보호 상태와 후보 명령 지원 여부는 아직 미확정이고 실제 충전 제어는 미지원입니다.
검토 결과로 실제 제어를 활성화하거나 사용자 선택값·현재 배터리 상태를 바꾸지 않습니다.

새 검토 기능은 추가 장치/WMI 조회·OEM 호출·1회 예약 파일 접근을 하지 않습니다.
기존 앱의 Windows 배터리 상태 표시와 선택적 읽기 전용 진단 기능은 유지합니다.
기존 WmiQuery65-v1.attempt를 삭제·초기화하거나 실험을 재실행하지 마세요.
삼성 DLL 실행·드라이버/서비스/ACL·보안 설정 변경·펌웨어 쓰기·프로그램의 인터넷 통신은 없습니다.
보호 기능이 차단하면 해제하거나 우회하지 마세요. 삼성 원본 DLL은 포함하지 않습니다.
이번 GUI의 Windows 실기 실행은 아직 미검증입니다.
"""
    files["먼저 읽어주세요.txt"] = instructions.replace("\n", "\r\n").encode("utf-8-sig")
    files["SHA256SUMS.txt"] = "".join(sha(data) + "  " + name + "\n" for name, data in sorted(files.items())).encode("utf-8")
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "ATIVBatteryGuard-WMI-RESULT-REVIEW.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files):
            raise ValueError("Executable ZIP integrity or allowlist check failed.")
    print(json.dumps({"file": str(target), "bytes": target.stat().st_size, "sha256": sha(target.read_bytes())}))


if __name__ == "__main__":
    main()
