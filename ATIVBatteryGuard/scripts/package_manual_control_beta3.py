"""Package compact high-DPI placement and local feedback without changing the manual SDK contract."""
import argparse
import json
from pathlib import Path
import zipfile

import pefile
from package_manual_control_beta import PROGRAM_NAMES, sha, source_closure, validate


ARCHIVE_NAME = 'ATIVBatteryGuard-MANUAL-CONTROL-BETA3.zip'
RELEASE_VERSION = '0.2.0-beta.3'


def gui_version(data):
    pe = pefile.PE(data=data)
    fixed = pe.VS_FIXEDFILEINFO[0]
    actual = (fixed.FileVersionMS >> 16, fixed.FileVersionMS & 65535,
              fixed.FileVersionLS >> 16, fixed.FileVersionLS & 65535)
    if actual != (0, 2, 0, 3):
        raise ValueError('The GUI PE file version must identify beta3.')
    strings = {}
    for group in pe.FileInfo:
        for item in group:
            for table in getattr(item, 'StringTable', []):
                strings.update(table.entries)
    product = strings.get(b'ProductVersion', b'').decode('utf-8')
    if product != RELEASE_VERSION:
        raise ValueError('The GUI informational version must match the screen/report release.')
    return {'fileVersion': '.'.join(str(x) for x in actual), 'productVersion': product}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    suite = json.loads(args.test_report.read_text())
    if not (suite['passed'] > 1093 and suite['registered'] == suite['passed'] and
            suite['failed'] == 0 and suite.get('skipped', 0) == 0):
        raise ValueError('The previous and new usability regression groups must pass.')
    app = root/'src/ATIVBatteryGuard.App'
    helper = root/'src/ATIVBatteryGuard.ManualProtectionHelper'
    build = app/'bin/Release/net48'
    files = {name: (build/name).read_bytes() for name in PROGRAM_NAMES}
    for name in ('ATIVBatteryGuard.Core.dll', 'ATIVBatteryGuard.WmiInterop.dll',
                 'ATIVBatteryGuard.ManualProtectionHelper.exe', 'ATIVBatteryGuard.ManualProtectionHelper.exe.config'):
        if files[name] != (helper/'bin/Release/net48'/name).read_bytes():
            raise ValueError('The app and helper must contain the same shared build bytes.')
    audits = validate(files)
    version = gui_version(files['ATIVBatteryGuard.exe'])
    sources = dict(source_closure(root, app/'ATIVBatteryGuard.App.csproj'))
    sources.update(source_closure(root, helper/'ATIVBatteryGuard.ManualProtectionHelper.csproj'))
    sources = sorted(sources.items())
    if any(name.startswith('tests/') or '/tests/' in name for name, _ in sources):
        raise ValueError('Tests cannot enter the product source closure.')
    fingerprint = sha(b''.join(name.encode()+b'\0'+data+b'\0' for name, data in sources))
    guide = (root/'MANUAL_CONTROL_BETA3_USER_STEPS.txt').read_bytes()
    info = {
        'schemaVersion': 1, 'dateKorea': '2026-11-10',
        'application': 'ATIV Battery Guard Manual Control Beta 3',
        'releaseVersion': RELEASE_VERSION, 'guiVersionResource': version,
        'target': 'Windows10x64/.NETFramework4.8/940X3G-930X3G/P05ACJ',
        'productSourceFingerprintSha256': fingerprint, 'sourceFileCount': len(sources),
        'sourceFiles': [{'file': name, 'sha256': sha(data)} for name, data in sources],
        'userGuideSourceSha256': sha(guide),
        'portableTestsPassed': suite['passed'], 'portableTestsFailed': 0, 'portableTestsSkipped': 0,
        'actualWpfXamlCompiled': True, 'actualNewBeta3WindowsRuntimeTested': False,
        'previousBetaGuiDisableRuntimeResult': 'pre1/post0,SDK3,set1,read2,Complete',
        'previous80SuppressionAndOffThen85ChargingEvidenceRetained': True,
        'digitallySigned': False, 'ordinaryGuiAsInvoker': True, 'helperAsInvoker': True,
        'userInitiatedRunAsHelperOnly': True, 'startupAutomaticElevation': False,
        'sameAccountLocalPipe': True, 'remoteNetworkLogonDeniedByPipeAcl': True,
        'clientImpersonationLevel': 'Identification',
        'currentUserSidReadInternallyForPipeAcl': True,
        'userNamesAndGroupsExplicitlyRead': False, 'sidJobNonceOrPersonalPathReported': False,
        'privateCorrelationIsDeviceAuthentication': False,
        'frequentFunctionOrder': ['Windows battery', 'Manual protection', 'Battery observation'],
        'secondaryFeaturesCollapsedNotRemoved': True,
        'normalStartupSizeDip': {'width': 750, 'height': 565},
        'nominalMinimumSizeDip': {'width': 480, 'height': 320},
        'fontsAndDpiManifestUnchanged': True,
        'alwaysCompactNormalStartup': True,
        'nativeMaximizeMinimizeAndCaptionPreserved': True,
        'currentMonitorPhysicalWorkAreaClamping': True,
        'startupCursorMonitorWithCurrentWindowFallback': True,
        'dpiDisplayTaskbarRestoreAndMonitorMoveRefit': True,
        'fittingDeferredUntilUserDragCompletes': True,
        'folderFeedbackPreservesSavedFilenamesAndDoesNotReplayHardware': True,
        'previousWindows10RestartRetention': 'User reported charging restriction retained after Windows10 Restart; no new cloud firmware action or raw trace.',
        'mockAndGlobalWarningsRemainVisible': True,
        'manualReceiptTimeSemantics': 'GUI result receipt only; not exact firmware-read time or a continuous current-state guarantee.',
        'reportVersionRequestAndResultTimes': True,
        'reportTimeIsReplacedBySaveTime': False,
        'metadataFailureChangesHardwareOutcome': False,
        'lastReadTimeClearedWithInvalidatedState': True,
        'localProtocolMaximumBytes': 4096, 'terminalRequiresActualCleanup': True,
        'clientRequiresResultAckAndReleased': True,
        'perUserDurableInProgressRecord': 'ManualProtectionV1/active.operation',
        'ownRecordReleasedOnlyAfterActualCloseAndValidAck': True,
        'uncertainOrLostOperationAutomaticallyCleared': False,
        'operationPurpose': 'ManualProtection-v1',
        'explicitOperationMaximumSdkEntries': {'ReadState': 3, 'Enable80': 7, 'DisableProtection': 3},
        'maximumSetterEntriesPerEnableOrDisable': 1,
        'alreadyDesiredModePerformsNoSetting': True,
        'propertyGettersStartupAndBatteryPollInvokeOem': False,
        'normalBatteryPollApi': 'GetSystemPowerStatus', 'normalBatteryPollSeconds': 10,
        'sameCommonMutexAndQuarantineRequired': True,
        'oldTrialReservationAccessResetOrReuse': False,
        'automaticRetryReverseRepairRestoreOrKill': False,
        'oemOriginalModulesFirmwarePdbOrTrialExecutablesIncluded': False,
        'driversServicesSecurityPolicyOrFlashChanges': False,
        'serviceAutostartBootApplyOrRuntimeInternet': False,
        'compiledReleaseAudit': audits,
        'programFiles': [{'file': name, 'bytes': len(files[name]), 'sha256': sha(files[name])} for name in PROGRAM_NAMES],
    }
    files['BUILD-INFO.json'] = (json.dumps(info, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    files['먼저 읽어주세요.txt'] = guide.decode('utf-8-sig').replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(data)+'  '+name+'\n' for name, data in sorted(files.items())).encode()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output/ARCHIVE_NAME
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != 9 or set(archive.namelist()) != set(files):
            raise ValueError('ZIP CRC or exact allowlist validation failed.')
        for name, data in files.items():
            if archive.read(name) != data:
                raise ValueError('ZIP source-byte comparison failed.')
    print(json.dumps({'file': target.name, 'bytes': target.stat().st_size,
                      'sha256': sha(target.read_bytes()), 'entries': len(files),
                      'sourceFileCount': len(sources), 'productSourceFingerprintSha256': fingerprint,
                      'releaseVersion': RELEASE_VERSION, 'guiVersionResource': version}))


if __name__ == '__main__':
    main()
