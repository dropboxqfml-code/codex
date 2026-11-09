"""Package the separately approved fixed Protection1To0-v1 trial.

Source and managed PE bytes are read as data only. This script never executes
the program, loads OEM code, queries WMI or accesses a notebook trial marker.
"""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import dnfile
import pefile

from package_protection_0to1 import sha, source_closure


PROGRAM_NAMES = ('ATIVBatteryGuard.ProtectionDisableTrial.exe',
                 'ATIVBatteryGuard.Core.dll', 'ATIVBatteryGuard.WmiInterop.dll',
                 'ATIVBatteryGuard.ProtectionDisableTrial.exe.config')
PURPOSE = 'Protection1To0-v1'
ARCHIVE_NAME = 'ATIVBatteryGuard-PROTECTION-1TO0.zip'


def validate_programs(files):
    exe, core = files[PROGRAM_NAMES[0]], files[PROGRAM_NAMES[1]]
    if PURPOSE.encode('utf-16-le') not in exe or 'protection-1to0-result-'.encode('utf-16-le') not in exe:
        raise ValueError('The distinct approved purpose and result prefix are required.')
    if (PURPOSE + '.attempt').encode('utf-16-le') not in core or b'WsabiWmiProtectionDisableAttempt\0' not in core:
        raise ValueError('The fixed disable attempt and distinct reservation are required.')
    release = {}
    for name in PROGRAM_NAMES[:3]:
        data = files[name]
        pe = pefile.PE(data=data)
        if pe.FILE_HEADER.Machine != 0x8664 or not pe.OPTIONAL_HEADER.DATA_DIRECTORY[14].Size:
            raise ValueError('All programs must be managed Windows x64 assemblies.')
        if pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size:
            raise ValueError('Unexpected signed bytes: update the disclosure before packaging.')
        if b'.NETFramework,Version=v4.8' not in data:
            raise ValueError('The .NET Framework 4.8 target is required.')
        metadata = dnfile.dnPE(data=data)
        methods = {str(row.Name) for row in metadata.net.mdtables.MethodDef.rows}
        types = {str(row.TypeName) for row in metadata.net.mdtables.TypeDef.rows}
        fields = {str(row.Name) for row in metadata.net.mdtables.Field.rows}
        references = {str(row.Name) for row in metadata.net.mdtables.AssemblyRef.rows}
        if (methods & {'ConfirmDetachedForTests', 'PrepareForTests'} or 'writeAndFlushForTests' in fields
                or any('FakeManagement' in value for value in types)):
            raise ValueError('Portable test-only helpers must be absent from notebook programs.')
        if name == PROGRAM_NAMES[1] and 'System.Management' in references:
            raise ValueError('Core must remain independent of System.Management.')
        release[name] = {'managedX64Net48': True, 'signed': False, 'testHelpersAbsent': True}
    exe_metadata = dnfile.dnPE(data=exe)
    refs = {str(row.TypeName) for row in exe_metadata.net.mdtables.TypeRef.rows}
    required = {'WsabiWmiProtectionDisableAttempt', 'WsabiWmiWindowsProtectionDisableTrial',
                'WsabiWmiProtection1To0FileReservation'}
    if not required <= refs:
        raise ValueError('The new host must reference only its fixed attempt, SDK entry and reservation.')
    if refs & {'WsabiWmiProtectionTransitionAttempt', 'WsabiWmiWindowsProtectionTrial',
               'WsabiWmiProtection0To1FileReservation', 'WsabiWmiFixedReadAccess1FileReservation',
               'WsabiWmiFixedModeReadAFileReservation'}:
        raise ValueError('Old trial attempts and reservation types must not be called by the new host.')
    pe = pefile.PE(data=exe)
    levels = []
    for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if kind.id == 24:
            for item in kind.directory.entries:
                for language in item.directory.entries:
                    data = language.data.struct
                    manifest = ET.fromstring(pe.get_data(data.OffsetToData, data.Size))
                    levels.extend(element for element in manifest.iter()
                                  if element.tag.rsplit('}', 1)[-1] == 'requestedExecutionLevel')
    if len(levels) != 1 or levels[0].get('level') != 'asInvoker' or levels[0].get('uiAccess') != 'false':
        raise ValueError('The executable must remain asInvoker/uiAccess=false.')
    runtime = ET.fromstring(files[PROGRAM_NAMES[3]]).find('./startup/supportedRuntime')
    if runtime is None or runtime.get('sku') != '.NETFramework,Version=v4.8':
        raise ValueError('The .NET Framework 4.8 runtime configuration is required.')
    return release


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    suite = json.loads(args.test_report.read_text(encoding='utf-8'))
    if not (suite['passed'] >= 973 and suite['failed'] == 0 and suite.get('skipped', 0) == 0
            and suite['registered'] == suite['passed']):
        raise ValueError('The complete disable trial and previous regression suite must pass.')
    project = root/'src/ATIVBatteryGuard.ProtectionDisableTrial/ATIVBatteryGuard.ProtectionDisableTrial.csproj'
    build = project.parent/'bin/Release/net48'
    files = {name: (build/name).read_bytes() for name in PROGRAM_NAMES}
    release = validate_programs(files)
    sources = source_closure(root, project)
    if any(name.startswith('tests/') or '/tests/' in name for name, _ in sources):
        raise ValueError('No test stand-in may be part of the notebook source closure.')
    fingerprint = sha(b''.join(name.encode() + b'\0' + data + b'\0' for name, data in sources))
    guide = (root/'PROTECTION_1TO0_USER_STEPS.txt').read_bytes()
    info = {
        'schemaVersion': 1, 'application': 'ATIV Battery Guard Fixed Protection Disable Trial',
        'purpose': PURPOSE, 'target': 'Windows10x64/.NETFramework4.8',
        'productSourceFingerprintSha256': fingerprint, 'sourceFileCount': len(sources),
        'sourceFiles': [{'file': name, 'sha256': sha(data)} for name, data in sources],
        'userGuideSourceSha256': sha(guide),
        'portableTestsPassed': suite['passed'], 'portableTestsFailed': 0, 'portableTestsSkipped': 0,
        'actualWindowsRuntimeSdkOrNotebookTested': False, 'digitallySigned': False,
        'manualOnAcObservationBeforeOffRequired': True,
        'onObservationAcknowledgmentIsUserProcedureNotDeviceAuthentication': True,
        'manualInteractiveStartRequired': True,
        'currentElevatedTokenRequiredBeforeStartReservationAndWmi': True,
        'manualSameAccountElevationIsUserProcedure': True, 'accountNamesGroupsOrSidsRead': False,
        'maximumAdditionalPreparationsAfterStart': 1,
        'maximumCallSabiFunctionSdkEntries': 3, 'maximumFixedReadEntries': 2,
        'maximumSemanticSet0Entries': 1, 'maximumAcceptedStoredModeCandidates': 2,
        'settingRequiresFreshAcceptedPreModeOne': True, 'preModeZeroPerformsNoSetting': True,
        'settingInputFixedZeroOnly': True, 'postModeZeroRequiresReceiptAndActualCloseFirst': True,
        'thresholdReads': 0, 'directThresholdWrites': 0, 'thresholdPreservationVerified': False,
        'onRestorationOrPreviousThresholdRestoreIncluded': False,
        'fullChargeOrRebootRestoreGuaranteed': False,
        'handshakes': 0, 'oemInitializations': 0, 'retries': 0, 'randomResamples': 0, 'fallbackB': 0,
        'randomFillBytesOnce': 24, 'zeroOrDuplicateComparisonContentAborts': True,
        'sameWindowsMutexAndCommonResourceQuarantineRequired': True,
        'ownerAcquireSecondsMaximum': 2, 'wholeProcedureDisplayDeadlineSeconds': 10,
        'displayTimeoutTerminatesFirmwareOrProcess': False,
        'actualCloseRequiresInvocationOutputAndInputJoin': True,
        'settingReceiptIsIndependentExecutionOrStoredStateProof': False,
        'storedModeMatchConfirmsElectricalChargingBehavior': False,
        'newPurposeDurableReservation': True, 'previousExperimentReservationAccessed': False,
        'consumedPreviousBudgetRestored': False,
        'normalPlatformApplicabilityAssumptionsRequired': True,
        'automaticallyElevates': False, 'runtimeNetworking': False,
        'driverServiceSecurityOrFlashChanges': False, 'oemOriginalModulesIncludedOrLoaded': False,
        'otherExperimentExecutablesOrMainGuiIncluded': False,
        'mainApplicationChargeControl': 'Unsupported',
        'genericSdkReadTrialEntry': 'ReadSpecificationUnavailable',
        'compiledReleaseAudit': release,
        'programFiles': [{'file': name, 'bytes': len(files[name]), 'sha256': sha(files[name])}
                         for name in PROGRAM_NAMES],
    }
    files['BUILD-INFO.json'] = (json.dumps(info, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    files['먼저 읽어주세요.txt'] = guide.decode('utf-8-sig').replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8-sig')
    files['SHA256SUMS.txt'] = ''.join(sha(data)+'  '+name+'\n' for name, data in sorted(files.items())).encode()
    if len(files) != 7:
        raise ValueError('Only four program files and three review files may be packaged.')
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output/ARCHIVE_NAME
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files):
            raise ValueError('ZIP CRC or entry validation failed.')
        for name, data in files.items():
            if archive.read(name) != data:
                raise ValueError('ZIP build-byte validation failed.')
    print(json.dumps({'file': target.name, 'bytes': target.stat().st_size,
                      'sha256': sha(target.read_bytes()), 'entries': len(files),
                      'productSourceFingerprintSha256': fingerprint, 'sourceFileCount': len(sources)}))


if __name__ == '__main__':
    main()
