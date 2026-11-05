"""Developer-only, bounded statement-header index of the observed P05ACJ HII resource.

This never evaluates firmware, conditions, defaults, variables, or AML. A missing
reference in supported statement headers is not evidence that a feature is absent.
The fixed resource hash binds token labels to previously reviewed bytes, not to
manufacturer authenticity or the current laptop's firmware.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
import os
import stat
import struct

MAX_BYTES = 1024 * 1024
MAX_PACKAGES = 64
MAX_OPCODES = 32768
MAX_DEPTH = 64


@dataclass(frozen=True)
class ResourceReference:
    size: int
    sha256: str


REFERENCE = ResourceReference(333801,
    '53ec78bfce49bf65858d64aaadee9fbb31abf79088ee0c9b60c28783a6ddf527')
# Exact token labels reviewed in this resource's en-US string package only.
TOKENS = (('batteryLifeCycleExtension', 77, 78),
          ('usbChargeInSleepMode', 79, 80), ('smartBatteryCalibration', 93, 94))
# Common EFI_IFR_STATEMENT_HEADER at +2. These are header bounds, not a full
# semantic validator for all IFR versions/opcodes or vendor GUID payloads.
STATEMENTS = {0x02: ('Subtitle', 7), 0x03: ('Text', 8), 0x05: ('OneOf', 17),
              0x06: ('CheckBox', 14), 0x07: ('Numeric', 17), 0x08: ('Password', 17),
              0x0c: ('Action', 13), 0x0d: ('ResetButton', 8), 0x0f: ('Ref', 13),
              0x1c: ('String', 16), 0x23: ('OrderedList', 15)}


def report(status, size=0, digest=None):
    return dict(status=status, sourceByteCount=size, sourceSha256=digest,
                observedResourceMatched=False, statementIndexComplete=False,
                packageCount=0, formsPackageCount=0, opcodeCount=0,
                supportedStatementCount=0, vendorGuidOpcodeCount=0, references=None,
                fullIfrSemanticsValidated=False, conditionsOrDefaultsEvaluated=False,
                currentFirmwareIdentityVerified=False, manufacturerAuthenticityVerified=False,
                batteryCommandContractVerified=False, canInferFeatureAbsence=False,
                canInferMenuVisibility=False, canReadHardware=False, canInvokeMethods=False,
                canWriteHardware=False, firmwareOrAmlExecuted=False)


def index_headers(data):
    """Pure index of the AMI count-prefixed resource, atomic on any bound failure."""
    if len(data) < 4 or len(data) > MAX_BYTES:
        raise ValueError()
    expected_count, = struct.unpack_from('<I', data)
    if not 0 < expected_count <= MAX_PACKAGES:
        raise ValueError()
    refs = {label: dict(promptReferences=0, helpReferences=0, pairedReferences=0,
                       statementKinds=[]) for label, _, _ in TOKENS}
    p = 4
    packages = forms = opcodes = statements = vendor = 0
    while p < len(data):
        if p + 4 > len(data) or packages >= expected_count:
            raise ValueError()
        length = int.from_bytes(data[p:p + 3], 'little')
        kind = data[p + 3]
        if length < 4 or p + length > len(data):
            raise ValueError()
        packages += 1
        if kind == 2:  # EFI_HII_PACKAGE_FORMS
            forms += 1
            i, end, depth = p + 4, p + length, 0
            while i < end:
                if i + 2 > end or opcodes >= MAX_OPCODES:
                    raise ValueError()
                opcode, flags = data[i:i + 2]
                size, scoped = flags & 0x7f, bool(flags & 0x80)
                if size < 2 or i + size > end:
                    raise ValueError()
                opcodes += 1
                if opcode == 0x29:  # END must close a real, package-local scope
                    if size != 2 or scoped or depth == 0:
                        raise ValueError()
                    depth -= 1
                else:
                    if opcode == 0x5f:
                        vendor += 1
                    if opcode in STATEMENTS:
                        name, minimum = STATEMENTS[opcode]
                        if size < minimum:
                            raise ValueError()
                        if opcode in (0x05, 0x07) and size < 14 + 3 * (1 << (data[i + 13] & 3)):
                            raise ValueError()
                        statements += 1
                        prompt, help_token = struct.unpack_from('<HH', data, i + 2)
                        for label, prompt_token, expected_help in TOKENS:
                            target = refs[label]
                            pm, hm = prompt == prompt_token, help_token == expected_help
                            target['promptReferences'] += int(pm)
                            target['helpReferences'] += int(hm)
                            target['pairedReferences'] += int(pm and hm)
                            if (pm or hm) and name not in target['statementKinds']:
                                target['statementKinds'].append(name)
                    if scoped:
                        depth += 1
                        if depth > MAX_DEPTH:
                            raise ValueError()
                i += size
            if depth:
                raise ValueError()
        p += length
    if packages != expected_count or forms == 0:
        raise ValueError()
    return dict(packageCount=packages, formsPackageCount=forms, opcodeCount=opcodes,
                supportedStatementCount=statements, vendorGuidOpcodeCount=vendor,
                references=refs)


def inspect(data, reference=REFERENCE):
    """Custom references are for inert unit fixtures only; CLI has no override."""
    if len(data) > MAX_BYTES:
        return report('InputTooLarge', len(data))
    result = report('SourceSizeMismatch', len(data), hashlib.sha256(data).hexdigest())
    if len(data) != reference.size:
        return result
    if result['sourceSha256'] != reference.sha256:
        result['status'] = 'SourceHashMismatch'
        return result
    try:
        indexed = index_headers(data)
    except (ValueError, struct.error):
        result['status'] = 'InvalidResource'
        return result
    result.update(indexed, status='ObservedResourceIndexed', observedResourceMatched=True,
                  statementIndexComplete=True)
    return result


def inspect_path(path):
    try:
        metadata = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode):
            return report('InputUnavailable')
        if metadata.st_size > MAX_BYTES:
            return report('InputTooLarge', metadata.st_size)
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        flags |= getattr(os, 'O_NONBLOCK', 0)
        with os.fdopen(os.open(path, flags), 'rb') as source:
            metadata = os.fstat(source.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                return report('InputUnavailable')
            if metadata.st_size > MAX_BYTES:
                return report('InputTooLarge', metadata.st_size)
            data = source.read(MAX_BYTES + 1)
        return inspect(data)
    except (OSError, ValueError):
        return report('InputUnavailable')


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError()


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('--input', required=True, metavar='PATH')
    try:
        args = parser.parse_args(argv)
    except ValueError:
        result = report('InvalidArguments')
    else:
        result = inspect_path(args.input)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'ObservedResourceIndexed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
