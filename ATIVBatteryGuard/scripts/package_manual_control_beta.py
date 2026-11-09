"""Package the manual-control GUI and its fixed elevated helper as data only."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import dnfile
import pefile
from package_protection_0to1 import sha, source_closure


PROGRAM_NAMES = ('ATIVBatteryGuard.exe', 'ATIVBatteryGuard.exe.config',
                 'ATIVBatteryGuard.Core.dll', 'ATIVBatteryGuard.WmiInterop.dll',
                 'ATIVBatteryGuard.ManualProtectionHelper.exe',
                 'ATIVBatteryGuard.ManualProtectionHelper.exe.config')
ARCHIVE_NAME = 'ATIVBatteryGuard-MANUAL-CONTROL-BETA.zip'


def execution_level(data):
    pe = pefile.PE(data=data)
    levels = []
    for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if kind.id == 24:
            for item in kind.directory.entries:
                for language in item.directory.entries:
                    resource = language.data.struct
                    manifest = ET.fromstring(pe.get_data(resource.OffsetToData, resource.Size))
                    levels.extend(element for element in manifest.iter()
                                  if element.tag.rsplit('}', 1)[-1] == 'requestedExecutionLevel')
    if len(levels) != 1 or levels[0].get('level') != 'asInvoker' or levels[0].get('uiAccess') != 'false':
        raise ValueError('Both executable manifests must remain asInvoker/uiAccess=false.')


def validate(files):
    audits = {}
    for name in PROGRAM_NAMES:
        data = files[name]
        if name.endswith('.config'):
            runtime = ET.fromstring(data).find('./startup/supportedRuntime')
            if runtime is None or runtime.get('sku') != '.NETFramework,Version=v4.8':
                raise ValueError('Both executable configurations must target .NET Framework 4.8.')
            continue
        pe = pefile.PE(data=data)
        if pe.FILE_HEADER.Machine != 0x8664 or not pe.OPTIONAL_HEADER.DATA_DIRECTORY[14].Size:
            raise ValueError('All assemblies must be managed Windows x64 builds.')
        if pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size or b'.NETFramework,Version=v4.8' not in data:
            raise ValueError('Only the disclosed unsigned net48 build is supported.')
        metadata = dnfile.dnPE(data=data)
        methods = {str(row.Name) for row in metadata.net.mdtables.MethodDef.rows}
        fields = {str(row.Name) for row in metadata.net.mdtables.Field.rows}
        types = {str(row.TypeName) for row in metadata.net.mdtables.TypeDef.rows}
        references = {str(row.Name) for row in metadata.net.mdtables.AssemblyRef.rows}
        type_refs = {str(row.TypeName) for row in metadata.net.mdtables.TypeRef.rows}
        if (methods & {'PrepareForTests', 'ConfirmDetachedForTests', 'TryClaimAtDirectory'} or
                fields & {'writeAndFlushForTests', 'StageLifetimeForTests'} or
                any('FakeManagement' in value for value in types)):
            raise ValueError('Portable-only seams and SDK stand-ins must be absent from release assemblies.')
        if name == 'ATIVBatteryGuard.Core.dll' and 'System.Management' in references:
            raise ValueError('Core must remain independent of System.Management.')
        if name == 'ATIVBatteryGuard.exe':
            if 'ATIVBatteryGuard.WmiInterop' in references:
                raise ValueError('The normal GUI must not load the privileged SDK bridge.')
            if not {'MainViewModel', 'WindowsManualProtectionOperationService'} <= types:
                raise ValueError('The manual GUI and private helper launcher are missing.')
            if not {'RunManualProtectionAsync', 'InvalidateManualState'} <= methods:
                raise ValueError('The async and cache invalidation entry points are missing.')
        if name == 'ATIVBatteryGuard.ManualProtectionHelper.exe':
            if not {'ManualProtectionAttempt', 'ManualProtectionOperationLease', 'WsabiWmiWindowsManualProtection'} <= type_refs:
                raise ValueError('The helper must use the application-specific fixed operation path.')
            if type_refs & {'WsabiWmiProtection0To1FileReservation', 'WsabiWmiProtection1To0FileReservation',
                            'WsabiWmiProtectionTransitionAttempt', 'WsabiWmiProtectionDisableAttempt'}:
                raise ValueError('Consumed trial attempts and markers cannot be reused by the helper.')
            if {'Kill', 'TerminateProcess'} & {str(row.Name) for row in metadata.net.mdtables.MemberRef.rows}:
                raise ValueError('The helper must not terminate an in-flight hardware process.')
        if name.endswith('.exe'):
            execution_level(data)
        audits[name] = {'managedX64Net48': True, 'signed': False, 'portableOnlyHelpersAbsent': True}
    return audits


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    suite = json.loads(args.test_report.read_text())
    if not (suite['passed'] >= 1081 and suite['registered'] == suite['passed'] and
            suite['failed'] == 0 and suite.get('skipped', 0) == 0):
        raise ValueError('The full manual-control and previous regression suite must pass.')
    app = root/'src/ATIVBatteryGuard.App'
    helper = root/'src/ATIVBatteryGuard.ManualProtectionHelper'
    build = app/'bin/Release/net48'
    helper_build = helper/'bin/Release/net48'
    files = {name: (build/name).read_bytes() for name in PROGRAM_NAMES}
    for name in ('ATIVBatteryGuard.Core.dll', 'ATIVBatteryGuard.WmiInterop.dll',
                 'ATIVBatteryGuard.ManualProtectionHelper.exe', 'ATIVBatteryGuard.ManualProtectionHelper.exe.config'):
        if files[name] != (helper_build/name).read_bytes():
            raise ValueError('The normal app folder must contain the same helper and shared build bytes.')
    audits = validate(files)
    sources = dict(source_closure(root, app/'ATIVBatteryGuard.App.csproj'))
    sources.update(source_closure(root, helper/'ATIVBatteryGuard.ManualProtectionHelper.csproj'))
    sources = sorted(sources.items())
    if any(name.startswith('tests/') or '/tests/' in name for name, _ in sources):
        raise ValueError('Test sources must not be part of the product closure.')
    fingerprint = sha(b''.join(name.encode()+b'\0'+data+b'\0' for name, data in sources))
    guide = (root/'MANUAL_CONTROL_BETA_USER_STEPS.txt').read_bytes()
    info = {
        'schemaVersion': 1, 'dateKorea': '2026-11-10',
        'application': 'ATIV Battery Guard Manual Control Beta',
        'target': 'Windows10x64/.NETFramework4.8/940X3G-930X3G/P05ACJ',
        'productSourceFingerprintSha256': fingerprint, 'sourceFileCount': len(sources),
        'sourceFiles': [{'file': name, 'sha256': sha(data)} for name, data in sources],
        'userGuideSourceSha256': sha(guide),
        'portableTestsPassed': suite['passed'], 'portableTestsFailed': 0, 'portableTestsSkipped': 0,
        'actualWpfXamlCompiled': True, 'actualNewWindowsGuiHelperRuntimeTested': False,
        'digitallySigned': False, 'ordinaryGuiAsInvoker': True, 'helperAsInvoker': True,
        'userInitiatedRunAsHelperOnly': True, 'startupAutomaticElevation': False,
        'sameAccountLocalPipe': True, 'remoteNetworkLogonDeniedByPipeAcl': True,
        'clientImpersonationLevel': 'Identification',
        'currentUserSidReadInternallyForPipeAcl': True,
        'userNamesAndGroupsExplicitlyRead': False, 'sidJobNonceOrPersonalPathReported': False,
        'privateCorrelationIsDeviceAuthentication': False,
        'localProtocolMaximumBytes': 4096, 'terminalRequiresActualCleanup': True,
        'clientRequiresResultAckAndReleased': True,
        'perUserDurableInProgressRecord': 'ManualProtectionV1/active.operation',
        'ownRecordReleasedOnlyAfterActualCloseAndValidAck': True,
        'uncertainOrLostOperationAutomaticallyCleared': False,
        'operationPurpose': 'ManualProtection-v1',
        'explicitOperationMaximumSdkEntries': {'ReadState': 3, 'Enable80': 7, 'DisableProtection': 3},
        'maximumSetterEntriesPerEnableOrDisable': 1,
        'alreadyDesiredModePerformsNoSetting': True,
        'modeOneAloneImplies80And75': False,
        'newSettingAlwaysUsesFreshPreRead': True,
        'propertyGettersStartupAndBatteryPollInvokeOem': False,
        'normalBatteryPollApi': 'GetSystemPowerStatus', 'normalBatteryPollSeconds': 10,
        'duplicateClickMockAndBusyCloseBlocked': True,
        'resumeAndLateResultCannotRestoreCurrentState': True,
        'sameContentObservationAndControlReportDuplicateSaveSuppressed': True,
        'saveFeedbackFilenameAndFolderButtons': True,
        'controlResultPrefix': 'manual-control-',
        'oldTrialReservationAccessResetOrReuse': False,
        'sameCommonMutexAndQuarantineRequired': True,
        'automaticRetryReverseRepairRestoreOrKill': False,
        'ownerAcquireSecondsMaximum': 2, 'displayDeadlineSeconds': 10,
        'displayTimeoutMeansFirmwareTermination': False,
        'oemOriginalModulesFirmwarePdbOrTrialExecutablesIncluded': False,
        'driversServicesSecurityPolicyOrFlashChanges': False,
        'serviceAutostartBootApplyOrRuntimeInternet': False,
        'chargeEffectOrFull100PercentGuaranteedByReadback': False,
        'compiledReleaseAudit': audits,
        'programFiles': [{'file': name, 'bytes': len(files[name]), 'sha256': sha(files[name])} for name in PROGRAM_NAMES],
    }
    files['BUILD-INFO.json'] = (json.dumps(info, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    files['먼저 읽어주세요.txt'] = guide.decode('utf-8-sig').replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(data)+'  '+name+'\n' for name, data in sorted(files.items())).encode()
    if len(files) != 9:
        raise ValueError('The package must contain six program files and three review files only.')
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output/ARCHIVE_NAME
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()): archive.writestr(name, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files):
            raise ValueError('ZIP CRC or allowlist validation failed.')
        for name, data in files.items():
            if archive.read(name) != data: raise ValueError('ZIP build-byte validation failed.')
    print(json.dumps({'file': target.name, 'bytes': target.stat().st_size,
                      'sha256': sha(target.read_bytes()), 'entries': len(files),
                      'productSourceFingerprintSha256': fingerprint, 'sourceFileCount': len(sources)}))


if __name__ == '__main__': main()
