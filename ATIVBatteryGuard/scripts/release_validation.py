"""Require Windows scan evidence for the exact signed build being packaged.

This prevents accidental unverified releases; JSON evidence is not a malware
certificate or proof against a forged report.
"""
from datetime import datetime, timezone, timedelta


def validate_release(report, files, fingerprint, now=None):
    now = now or datetime.now(timezone.utc)
    if report.get('schemaVersion') != 1 or report.get('sourceFingerprintSha256') != fingerprint:
        raise ValueError('Windows evidence does not match this source.')
    stamp = datetime.fromisoformat(report['completedUtc'].replace('Z', '+00:00'))
    if stamp.tzinfo is None or not timedelta(0) <= now - stamp <= timedelta(hours=24):
        raise ValueError('Windows evidence is stale or has an invalid timestamp.')
    if any(report.get(key) is not True for key in
           ('defenderEnabled', 'realTimeProtectionEnabled', 'scanCompleted', 'scanPassed')):
        raise ValueError('A completed Defender scan with protections enabled is required.')
    if type(report.get('detections')) is not int or report['detections'] != 0 or not report.get('defenderSignatureVersion'):
        raise ValueError('Defender detection or missing definitions evidence.')
    import hashlib
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    if report.get('fileHashes') != hashes:
        raise ValueError('Scanned files differ from the packaged build.')
    signatures = report.get('signatures', {})
    thumbprints = set()
    for name in ('ATIVBatteryGuard.exe', 'ATIVBatteryGuard.Core.dll'):
        entry = signatures.get(name, {})
        thumbprint = entry.get('thumbprint', '')
        if entry.get('status') != 'Valid' or len(thumbprint) != 40 or any(c not in '0123456789abcdefABCDEF' for c in thumbprint):
            raise ValueError('A valid Authenticode publisher signature is required: ' + name)
        thumbprints.add(thumbprint.upper())
    if len(thumbprints) != 1:
        raise ValueError('Executable and library must have the same signing certificate.')
