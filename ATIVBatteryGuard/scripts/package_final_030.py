"""Prepare a signed 0.3.0 review ZIP only after exact-file Windows evidence passes."""
import argparse
import json
import zipfile
from pathlib import Path
from final_release_030 import FINAL_VERSION, read_json_bytes, sha, verify_source_identity, verify_final_evidence
from package_manual_control_beta import PROGRAM_NAMES, source_closure, validate
from package_release_020 import gui_version


def read_plain(path, limit):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Input path or size rejected.')
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError('Linked input parent rejected.')
    return path.read_bytes()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--build-directory', required=True, type=Path)
    p.add_argument('--test-report', required=True, type=Path)
    p.add_argument('--windows-report', required=True, type=Path)
    p.add_argument('--gui-report', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = args.output/'ATIVBatteryGuard-0.3.0-WIN10-X64-SIGNED-REVIEW.zip'
    if target.exists():
        raise ValueError('A previous review package must not be overwritten.')
    tests = read_json_bytes(read_plain(args.test_report, 65536))
    if not (type(tests.get('passed')) is int and tests['passed'] >= 1272
            and tests.get('registered') == tests['passed'] and tests.get('failed') == 0 and tests.get('skipped') == 0):
        raise ValueError('Successful complete regression evidence is required.')
    validated = root.parent/'downloads/ATIVBatteryGuard-0.3.0-rc.3-WIN10-X64.zip'
    baseline = read_json_bytes(read_plain(root/'reports/release-030-rc3-validation.json', 65536))
    if sha(read_plain(validated, 32*1024*1024)) != baseline['package']['sha256']:
        raise ValueError('Validated RC3 baseline archive differs.')
    close = read_json_bytes(read_plain(root/'reports/field-ime-close-rc3/assessment.json', 65536))
    if close.get('startupAndFocusedClosePassed') is not True or close.get('sourceFingerprintMatchesReleasedRc3') is not True:
        raise ValueError('Validated RC3 close evidence is missing.')
    with zipfile.ZipFile(validated) as z:
        candidate = read_json_bytes(z.read('BUILD-INFO.json'))
        if z.testzip() is not None:
            raise ValueError('Baseline archive CRC differs.')
    sources = dict(source_closure(root, root/'src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj'))
    sources.update(source_closure(root, root/'src/ATIVBatteryGuard.ManualProtectionHelper/ATIVBatteryGuard.ManualProtectionHelper.csproj'))
    fingerprint = verify_source_identity(sources, candidate)
    files = {name: read_plain(args.build_directory/name, 32*1024*1024) for name in PROGRAM_NAMES}
    windows_raw = read_plain(args.windows_report, 65536)
    gui_raw = read_plain(args.gui_report, 65536)
    windows = read_json_bytes(windows_raw)
    if windows.get('guiReportFile') != args.gui_report.name:
        raise ValueError('GUI report filename differs from Windows collection.')
    version = gui_version(files['ATIVBatteryGuard.exe'], FINAL_VERSION)
    gate = verify_final_evidence(files, fingerprint, FINAL_VERSION, windows, gui_raw)
    audit = validate(files, signed=True)
    info = dict(schemaVersion=1, releaseVersion=FINAL_VERSION, releaseStage='signed-review-prepared',
                finalReleaseApproved=False, publicationPerformed=False, **gate,
                guiVersionResource=version, sourceFingerprintSha256=fingerprint,
                sourceFiles=[dict(file=n, sha256=sha(d)) for n,d in sorted(sources.items())],
                validatedRc3ZipSha256=baseline['package']['sha256'], onlyVersionChangedSinceValidatedRc3=True,
                manualEvidenceInheritedFromRc3=True, newManualImeRunClaimed=False,
                windowsEvidenceSha256=sha(windows_raw), guiEvidenceSha256=sha(gui_raw),
                portableTests=tests, compiledReleaseAudit=audit,
                programFiles=[dict(file=n,bytes=len(files[n]),sha256=sha(files[n])) for n in PROGRAM_NAMES])
    files['BUILD-INFO.json'] = (json.dumps(info,ensure_ascii=False,indent=2)+'\n').encode()
    files['먼저 읽어주세요.txt'] = (root/'RELEASE_030_SIGNED_REVIEW_USER_STEPS.txt').read_text().replace('\n','\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(d)+'  '+n+'\n' for n,d in sorted(files.items())).encode()
    # Read-only failures above create no output. Stage only after every gate passes.
    args.output.mkdir(parents=True,exist_ok=True)
    staging = target.with_suffix('.zip.pending')
    owns_staging = False
    try:
        with zipfile.ZipFile(staging,'x',zipfile.ZIP_DEFLATED) as z:
            owns_staging = True
            for n,d in sorted(files.items()): z.writestr(n,d)
        with zipfile.ZipFile(staging) as z:
            if z.testzip() is not None or len(z.namelist()) != 9:
                raise ValueError('Prepared ZIP count or CRC differs.')
            for n,d in files.items():
                if z.read(n) != d: raise ValueError('Prepared ZIP bytes differ.')
        # Exclusive link prevents clobbering an artifact created concurrently.
        import os
        os.link(staging,target)
        staging.unlink()
    except BaseException:
        if owns_staging and staging.exists(): staging.unlink()
        raise
    print(json.dumps(dict(file=target.name,bytes=target.stat().st_size,sha256=sha(target.read_bytes()),**gate,
                          finalReleaseApproved=False,publicationPerformed=False)))


if __name__ == '__main__':
    main()
