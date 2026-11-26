"""Strict final-file evidence and source-identity checks. No signing or policy changes."""
import hashlib
import json
from datetime import datetime, timezone, timedelta
from release_validation import validate_final_release

FINAL_VERSION = '0.3.0'
VERSION_SOURCE = 'src/ATIVBatteryGuard.Core/Models/ApplicationRelease.cs'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json_bytes(raw):
    if len(raw) > 65536:
        raise ValueError('Evidence exceeds its size limit.')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate evidence member.')
            result[key] = value
        return result
    def invalid_constant(_):
        raise ValueError('Nonfinite evidence number.')
    result = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=invalid_constant)
    if not isinstance(result, dict):
        raise ValueError('Evidence must contain one JSON object.')
    return result


def verify_source_identity(current, validated_candidate):
    expected = {entry['file']: entry['sha256'] for entry in validated_candidate['sourceFiles']}
    if set(current) != set(expected) or len(expected) != 207:
        raise ValueError('Final source closure differs from the validated RC3.')
    final_line = b'public const string Version = "0.3.0";'
    candidate_line = b'public const string Version = "0.3.0-rc.3";'
    for name, raw in current.items():
        compared = raw
        if name == VERSION_SOURCE:
            if raw.count(final_line) != 1:
                raise ValueError('The final source version must be exactly 0.3.0.')
            compared = raw.replace(final_line, candidate_line, 1)
        if sha(compared) != expected[name]:
            raise ValueError('Changes beyond the final version require new validation: ' + name)
    return sha(b''.join(name.encode()+b'\0'+data+b'\0' for name, data in sorted(current.items())))


def verify_final_evidence(files, fingerprint, version, report, gui_raw, now=None):
    now = now or datetime.now(timezone.utc)
    if type(report.get('schemaVersion')) is not int or report['schemaVersion'] != 1:
        raise ValueError('A typed Windows evidence schema is required.')
    if version != FINAL_VERSION or report.get('releaseVersion') != FINAL_VERSION:
        raise ValueError('RC versions cannot pass the final-file gate.')
    validate_final_release(report, files, fingerprint, now)
    hashes = {name: sha(raw) for name, raw in files.items()}
    if report.get('guiExecuted') is not True or type(report.get('guiExitCode')) is not int or report['guiExitCode'] != 0:
        raise ValueError('An executed final-file GUI self-test with exit code zero is required.')
    if report.get('guiFileHashes') != hashes or report.get('guiReportSha256') != sha(gui_raw):
        raise ValueError('GUI evidence is not linked to the exact signed files.')
    stamp = datetime.fromisoformat(report['guiCompletedUtc'].replace('Z', '+00:00'))
    completed = datetime.fromisoformat(report['completedUtc'].replace('Z', '+00:00'))
    if stamp.tzinfo is None or not timedelta(0) <= now-stamp <= timedelta(hours=24) or stamp > completed:
        raise ValueError('Final GUI evidence timestamp is invalid or stale.')
    gui = read_json_bytes(gui_raw)
    if (type(gui.get('schemaVersion')) is not int or gui['schemaVersion'] != 1
            or gui.get('status') != 'passed' or gui.get('guiPassed') is not True
            or gui.get('hardwareWritesPerformed') is not False
            or type(gui.get('bindingErrors')) is not int or gui['bindingErrors'] != 0
            or gui.get('errors') != []):
        raise ValueError('Final GUI evidence did not pass the required conditions.')
    return {'signedFinalFileGatePassed': True, 'finalGuiPassed': True,
            'sameSignedFileHashesForScanGuiAndPackage': True,
            'publisherAndTimestampEvidenceRequired': True}
