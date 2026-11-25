"""Package 0.2.x releases with friendly labels and a passive battery observation chart."""
import argparse
import json
from pathlib import Path
import zipfile

import pefile
from package_manual_control_beta import PROGRAM_NAMES, sha, source_closure, validate


RELEASE_VERSION = '0.2.0'


def gui_version(data, release_version=RELEASE_VERSION):
    pe = pefile.PE(data=data)
    fixed = pe.VS_FIXEDFILEINFO[0]
    actual = (fixed.FileVersionMS >> 16, fixed.FileVersionMS & 65535,
              fixed.FileVersionLS >> 16, fixed.FileVersionLS & 65535)
    if actual != tuple(int(part) for part in release_version.split('.')) + (0,):
        raise ValueError('The GUI PE file version must match the requested release.')
    strings = {}
    for group in pe.FileInfo:
        for item in group:
            for table in getattr(item, 'StringTable', []):
                strings.update(table.entries)
    product = strings.get(b'ProductVersion', b'').decode('utf-8')
    if product != release_version:
        raise ValueError('The GUI informational version must match the screen/report release.')
    return {'fileVersion': '.'.join(str(x) for x in actual), 'productVersion': product}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--release-version', choices=('0.2.0', '0.2.1', '0.2.2', '0.2.3', '0.2.4', '0.2.5', '0.2.6', '0.2.7', '0.2.8', '0.2.9'), default=RELEASE_VERSION)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    suite = json.loads(args.test_report.read_text())
    if not (suite['passed'] >= {'0.2.0': 1120, '0.2.1': 1143, '0.2.2': 1150, '0.2.3': 1163, '0.2.4': 1179, '0.2.5': 1186, '0.2.6': 1201, '0.2.7': 1219, '0.2.8': 1236, '0.2.9': 1243}[args.release_version] and suite['registered'] == suite['passed'] and
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
    version = gui_version(files['ATIVBatteryGuard.exe'], args.release_version)
    sources = dict(source_closure(root, app/'ATIVBatteryGuard.App.csproj'))
    sources.update(source_closure(root, helper/'ATIVBatteryGuard.ManualProtectionHelper.csproj'))
    sources = sorted(sources.items())
    if any(name.startswith('tests/') or '/tests/' in name for name, _ in sources):
        raise ValueError('Tests cannot enter the product source closure.')
    fingerprint = sha(b''.join(name.encode()+b'\0'+data+b'\0' for name, data in sources))
    guide_name = 'RELEASE_' + args.release_version.replace('.', '') + '_USER_STEPS.txt'
    guide = (root/guide_name).read_bytes()
    info = {
        'schemaVersion': 1, 'dateKorea': '2026-11-10' if args.release_version == '0.2.0' else '2026-11-25',
        'application': 'ATIV Battery Guard',
        'releaseVersion': args.release_version, 'guiVersionResource': version,
        'target': 'Windows10x64/.NETFramework4.8/940X3G/P05ACJ' if args.release_version == '0.2.9' else 'Windows10x64/.NETFramework4.8/940X3G-930X3G/P05ACJ',
        'productSourceFingerprintSha256': fingerprint, 'sourceFileCount': len(sources),
        'sourceFiles': [{'file': name, 'sha256': sha(data)} for name, data in sources],
        'userGuideSourceSha256': sha(guide),
        'portableTestsPassed': suite['passed'], 'portableTestsFailed': 0, 'portableTestsSkipped': 0,
        'actualWpfXamlCompiled': True, 'actualNewReleaseWindowsRuntimeTested': False,
        'previousBetaGuiDisableRuntimeResult': 'pre1/post0,SDK3,set1,read2,Complete',
        'previous80SuppressionAndOffThen85ChargingEvidenceRetained': True,
        'digitallySigned': False, 'ordinaryGuiAsInvoker': True, 'helperAsInvoker': True,
        'userInitiatedRunAsHelperOnly': True, 'startupAutomaticElevation': False,
        'sameAccountLocalPipe': True, 'remoteNetworkLogonDeniedByPipeAcl': True,
        'clientImpersonationLevel': 'Identification',
        'currentUserSidReadInternallyForPipeAcl': True,
        'userNamesAndGroupsExplicitlyRead': False, 'sidJobNonceOrPersonalPathReported': False,
        'privateCorrelationIsDeviceAuthentication': False,
        'frequentFunctionOrder': ['Battery and charging', 'Records and notes', 'Help and diagnostics'] if args.release_version == '0.2.9' else ['Windows battery', 'Manual protection', 'Battery observation'],
        'secondaryFeaturesCollapsedNotRemoved': args.release_version != '0.2.9',
        'beginnerThreeSectionNavigation': args.release_version == '0.2.9',
        'modelPresentation940X3GOnly': args.release_version == '0.2.9',
        'rawHardwareAdmissionProfilePreserved': True,
        'inactivePreferencesMockHistoricalReviewInquiryAndFileResearchExcludedFromUi': args.release_version == '0.2.9',
        'recordNoteComparisonAndDiagnosticDataPreserved': True,
        'prereleaseMarkerRemovedFromCurrentUserInterface': True,
        'friendlyProtectionLabels': True,
        'modeOneAloneImplies80Percent': False,
        'passiveBatteryChartOnObservationStart': True,
        'chartUsesExistingTenSecondSamplesOnly': True,
        'chartHasNewTimerClockProviderOrHardwareCalls': False,
        'chartUnknownNoBatteryReadErrorAndGapsBreakSegments': True,
        'chartAxis': 'Elapsed seconds horizontally and observed battery percentage from 0 to 100 vertically.',
        'chartHoverUsesOnlyActualObservedPoints': True,
        'chartKeyboardObservedPointNavigation': args.release_version in ('0.2.1', '0.2.2', '0.2.3', '0.2.4', '0.2.5', '0.2.6', '0.2.7', '0.2.8', '0.2.9'),
        'chartMouseClickFocusAndSelection': args.release_version in ('0.2.2', '0.2.3', '0.2.4', '0.2.5', '0.2.6', '0.2.7', '0.2.8', '0.2.9'),
        'chartMouseSelectionWindowsRuntimeTested': False,
        'savedObservationTxtOpenAndHistoricalGraph': args.release_version in ('0.2.3', '0.2.4', '0.2.5', '0.2.6', '0.2.7', '0.2.8', '0.2.9'),
        'savedObservationMaximumBytes': 262144,
        'savedObservationStrictUtf8AndPreviousExportFormat': True,
        'savedObservationFilePickerWindowsRuntimeTested': False,
        'unsavedObservationSaveDiscardCancelGuard': args.release_version in ('0.2.4', '0.2.5', '0.2.6', '0.2.7', '0.2.8', '0.2.9'),
        'recentObservationLocalIndexMaximumEntries': 10,
        'recentIndexFailureChangesTxtSaveOutcome': False,
        'recentIndexAndConfirmationWindowsRuntimeTested': False,
        'twoSavedObservationGraphsWithCommonElapsedAxis': args.release_version in ('0.2.5', '0.2.6', '0.2.7', '0.2.8', '0.2.9'),
        'comparisonPreservesIndependentTimestampsGapsAndSelection': args.release_version in ('0.2.5', '0.2.6', '0.2.7', '0.2.8', '0.2.9'),
        'comparisonWindowsRuntimeTested': False,
        'recordNotesInLocalAppData': args.release_version in ('0.2.6', '0.2.7', '0.2.8', '0.2.9'),
        'txtAndNoteBundleExportImport': args.release_version in ('0.2.7', '0.2.8', '0.2.9'),
        'bundleMaximumBytes': 2097152,
        'bundleVersion': 1,
        'bundleHashesProvideAuthenticity': False,
        'bundleImportUsesUniqueLocalDirectoryAndRebindsNote': args.release_version in ('0.2.7', '0.2.8', '0.2.9'),
        'bundleExportIncludesDisplayedDraftWithoutMarkingLocalNoteSaved': args.release_version in ('0.2.7', '0.2.8', '0.2.9'),
        'bundleNativeFileDialogsWindowsRuntimeTested': False,
        'previous026UserConfirmedNoteInput': args.release_version in ('0.2.7', '0.2.8', '0.2.9'),
        'previous027UserConfirmedBundleExportImport': args.release_version in ('0.2.8', '0.2.9'),
        'strictBoundedJsonForSettingsNotesRecentsAndBundle': args.release_version in ('0.2.8', '0.2.9'),
        'settingsCrossProcessLeaseAndRevisionCheck': args.release_version in ('0.2.8', '0.2.9'),
        'validSettingsReadOnlyFallback': args.release_version in ('0.2.8', '0.2.9'),
        'importRecoveryCopyPreparedBeforeTxtAndNote': args.release_version in ('0.2.8', '0.2.9'),
        'abandonedImportRecoveryGuidanceWithoutAutomaticDeletion': args.release_version in ('0.2.8', '0.2.9'),
        'recentSelectionPreservedDuringMemoRefresh': args.release_version in ('0.2.8', '0.2.9'),
        'matchingFileNamesHaveShortRecordIdentityLabels': args.release_version in ('0.2.8', '0.2.9'),
        'windowsImeDpiDefenderAndPowerLossTested': False,
        'recordNoteMaximumCharacters': 1000,
        'noteIdentityUsesFileLocationAndNormalizedTxtContent': True,
        'noteStoreIndependentOfRecentTenEntryLimit': True,
        'noteConcurrentRevisionCheckAndAtomicReplace': True,
        'noteWindowsRuntimeTested': False,
        'previous025UserConfirmedABComparison': args.release_version in ('0.2.6', '0.2.7', '0.2.8', '0.2.9'),
        'previous024UserConfirmedRecentSelectionGraphOpen': args.release_version in ('0.2.5', '0.2.6', '0.2.7', '0.2.8', '0.2.9'),
        'previous023UserConfirmedHistoricalGraphAndInputSelection': args.release_version in ('0.2.4', '0.2.5', '0.2.6', '0.2.7', '0.2.8', '0.2.9'),
        'previous022UserConfirmedMouseSelection': args.release_version in ('0.2.3', '0.2.4', '0.2.5', '0.2.6', '0.2.7', '0.2.8', '0.2.9'),
        'previous021UserConfirmedTabSampleInspection': args.release_version in ('0.2.2', '0.2.3', '0.2.4', '0.2.5', '0.2.6', '0.2.7', '0.2.8', '0.2.9'),
        'observationFinalStatusCanBeSavedOnceWithoutNewRows': args.release_version in ('0.2.2', '0.2.3', '0.2.4', '0.2.5', '0.2.6', '0.2.7', '0.2.8', '0.2.9'),
        'observationTerminalReasonVisible': args.release_version in ('0.2.2', '0.2.3', '0.2.4', '0.2.5', '0.2.6', '0.2.7', '0.2.8', '0.2.9'),
        'chartKeyboardWindowsRuntimeTested': False,
        'chartStopPreservesHistoryAndClearResets': True,
        'chartHiddenWhileMockActive': True,
        'existingObservationSessionCsvAndExportUnchanged': True,
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
    target = args.output/('ATIVBatteryGuard-' + args.release_version + '-WIN10-X64.zip')
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
                      'releaseVersion': args.release_version, 'guiVersionResource': version}))


if __name__ == '__main__':
    main()
