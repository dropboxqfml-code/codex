"""Developer-only offline Samsung Update response classification.

Reads response bytes, never sends a request or follows catalog locators. Protocol
shape: qt-kaneko/su-downloader README at
94f425236760721adcf50ecb0d355eb22c952500. Successful discovery cannot establish
manufacturer authenticity, current-device compatibility, or a battery contract.
"""
import argparse
import hashlib
import json
import re
import sys
from urllib.parse import urlsplit
from xml.etree import ElementTree


MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 32
MAX_NODES = 8192
MAX_RECORDS = 2048
# BOM catalogs have a different shape and their own budget. SOAP/JSON budgets
# stay unchanged; a larger BOM is never accepted as a larger service response.
BOM_MAX_DEPTH = 16
BOM_MAX_NODES = 16384
BOM_MAX_ITEMS = 256
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
OP_NS = "http://orcaservice.samsungmobile.com/"
OPERATIONS = {
    "models": ("GetModelListBykeyword", "DerivedModel"),
    "os": ("GetSupportedOSList", "OS"),
    "model-code": ("GetModelCode", "ModelCode"),
}
KINDS = tuple(OPERATIONS) + ("catalog", "bom")


class _InvalidResponse(ValueError):
    pass


class _LimitExceeded(ValueError):
    pass


def _report(status, kind=None, http_status=None, size=0, digest=None):
    return dict(status=status, kind=kind, httpStatus=http_status,
                sourceByteCount=size, sourceSha256=digest, serviceCode=None,
                entryCount=None, bomDownloadLocatorCount=None,
                comparisonSettingsCandidateCount=None,
                manufacturerAuthenticityVerified=False,
                currentDeviceIdentityVerified=False,
                currentModelCompatibilityVerified=False,
                batteryCommandContractVerified=False,
                sourcePayloadIntegrityVerified=False,
                catalogHashCryptographicallyVerified=False,
                canInferFeatureAbsence=False, canReadHardware=False,
                canInvokeMethods=False, canWriteHardware=False,
                networkAccessPerformed=False, locatorFetched=False,
                vendorCodeExecuted=False)


def _single(parent, tag):
    matches = [child for child in parent if child.tag == tag]
    if len(matches) != 1:
        raise _InvalidResponse()
    return matches[0]


def _plain_text(element):
    if len(element) or element.attrib:
        raise _InvalidResponse()
    return (element.text or "").strip()


def _numeric_code(value):
    # Codes are data, not arbitrary server error strings. Keep their output bound.
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,9}", value):
        raise _InvalidResponse()
    return value


def _xml_root(text, *, max_depth=MAX_DEPTH, max_nodes=MAX_NODES):
    # No entity expansion, DTD fetching, alternate encoding or XML 1.1 controls.
    if "\x00" in text or re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        raise _InvalidResponse()
    declaration = re.match(r"\s*<\?xml\s+([^?]*)\?>", text)
    if declaration:
        encoding = re.search(r"encoding\s*=\s*(['\"])(.*?)\1", declaration[1], re.I)
        if encoding and encoding[2].lower() not in ("utf-8", "utf8"):
            raise _InvalidResponse()
    parser = ElementTree.XMLPullParser(events=("start", "end"))
    depth = nodes = 0
    root = None
    for offset in range(0, len(text), 4096):
        parser.feed(text[offset:offset + 4096])
        for event, element in parser.read_events():
            if event == "start":
                depth += 1
                nodes += 1
                if depth > max_depth or nodes > max_nodes:
                    raise _LimitExceeded()
                if root is None:
                    root = element
            else:
                depth -= 1
    parser.close()
    if root is None or depth:
        raise _InvalidResponse()
    return root


def _soap(text, kind):
    root = _xml_root(text)
    if root.tag != "{%s}Envelope" % SOAP_NS:
        raise _InvalidResponse()
    body = _single(root, "{%s}Body" % SOAP_NS)
    if len(body) != 1:
        raise _InvalidResponse()
    response = body[0]
    if response.tag == "{%s}Fault" % SOAP_NS:
        return "SoapFault", None, None
    method, entry_tag = OPERATIONS[kind]
    if response.tag != "{%s}%sResponse" % (OP_NS, method) or len(response) != 1:
        raise _InvalidResponse()
    result = _single(response, "{%s}%sResult" % (OP_NS, method))
    info = _single(result, "{%s}ResultInfo" % OP_NS)
    code = _numeric_code(_plain_text(_single(info, "{%s}ResultCode" % OP_NS)))
    if code != "0":
        return "ServiceRejected", code, None
    entries = [child for child in result if child.tag == "{%s}%s" % (OP_NS, entry_tag)]
    if len(entries) > MAX_RECORDS:
        raise _LimitExceeded()
    # Direct children only. Nested vendor metadata never adds successful records.
    for entry in entries:
        value = _plain_text(entry)
        if not value or len(value) > 128 or any(ord(char) < 32 for char in value):
            raise _InvalidResponse()
    if kind == "model-code" and len(entries) > 1:
        raise _InvalidResponse()
    return ("Completed" if entries else "CompletedEmpty"), code, len(entries)


def _json_depth(text):
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                raise _LimitExceeded()
        elif char in "]}":
            depth -= 1
            if depth < 0:
                raise _InvalidResponse()
    if depth or quoted:
        raise _InvalidResponse()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidResponse()
        result[key] = value
    return result


def _json_value(text):
    _json_depth(text)
    def invalid_constant(_value):
        raise _InvalidResponse()
    value = json.loads(text, object_pairs_hook=_unique_object,
                       parse_constant=invalid_constant)
    nodes = 0
    pending = [value]
    while pending:
        current = pending.pop()
        nodes += 1
        if nodes > MAX_NODES:
            raise _LimitExceeded()
        if isinstance(current, dict):
            # Include keys in the budget as well as values.
            nodes += len(current)
            if nodes > MAX_NODES:
                raise _LimitExceeded()
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return value


def _locator(value):
    if (not isinstance(value, str) or not value or len(value) > 4096 or
            any(ord(char) <= 32 or ord(char) == 127 for char in value)):
        raise _InvalidResponse()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise _InvalidResponse() from None
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or
            parsed.username is not None or parsed.password is not None or
            parsed.fragment or not parsed.path or port == 0):
        raise _InvalidResponse()


def _catalog(text):
    value = _json_value(text)
    if not isinstance(value, dict):
        raise _InvalidResponse()
    result = value.get("Result")
    if result == "FAIL":
        info = value.get("FailInfo")
        if not isinstance(info, dict) or "FailCode" not in info:
            raise _InvalidResponse()
        return "ServiceRejected", _numeric_code(info["FailCode"]), None
    if result != "SUCC" or value.get("FailInfo") not in (None, {}):
        raise _InvalidResponse()
    if "HDM" not in value:
        raise _InvalidResponse()
    primary = value["HDM"]
    if primary is None:
        return "NoPrimaryCatalog", "SUCC", None
    if not isinstance(primary, dict) or "ITEM" not in primary:
        raise _InvalidResponse()
    entries = primary["ITEM"]
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list):
        raise _InvalidResponse()
    if len(entries) > MAX_RECORDS:
        raise _LimitExceeded()
    for entry in entries:
        if not isinstance(entry, dict) or "FURL" not in entry:
            raise _InvalidResponse()
        _locator(entry["FURL"])
    return ("Completed" if entries else "CompletedEmpty"), "SUCC", len(entries)


def _bom_text(parent, tag, max_length, *, required=True):
    matches = [child for child in parent if child.tag == tag]
    if len(matches) > 1 or (required and not matches):
        raise _InvalidResponse()
    value = _plain_text(matches[0]) if matches else ""
    # Catalog display labels may contain XML whitespace, including line breaks.
    # Nonempty locators receive the stricter URL validation separately.
    if len(value) > max_length or any(ord(char) < 32 and char not in "\t\n\r" for char in value):
        raise _InvalidResponse()
    return value


def _bom(text):
    root = _xml_root(text, max_depth=BOM_MAX_DEPTH, max_nodes=BOM_MAX_NODES)
    if root.tag != "MaxList":
        raise _InvalidResponse()
    head = _single(root, "Head")
    # Structure only: these strings are neither returned nor matched to a device.
    _bom_text(head, "Model", 128)
    _bom_text(head, "OS", 128)
    entries = [child for child in root if child.tag == "Item"]
    if len(entries) > BOM_MAX_ITEMS:
        raise _LimitExceeded()
    locators = candidates = 0
    for entry in entries:
        name = _bom_text(entry, "DisplayName", 512)
        version = _bom_text(entry, "Version", 128)
        # Some observed metadata items have no FURL element at all. Neither
        # missing nor empty locators erase the item or establish file absence.
        locator = _bom_text(entry, "FURL", 4096, required=False)
        if locator:
            _locator(locator)
            locators += 1
        # A metadata comparison candidate is not a downloaded/verified module,
        # an install recommendation, or a current-model battery contract.
        if name == "Easy Settings for Win7 2.0.0.89" and version == "2.0.0.89":
            candidates += 1
    return ("Completed" if entries else "CompletedEmpty"), len(entries), locators, candidates


def inspect_response(data, kind, http_status):
    """Classify bounded, untrusted bytes. This function performs no I/O."""
    if (kind not in KINDS or not isinstance(http_status, int) or
            isinstance(http_status, bool) or not 100 <= http_status <= 599 or
            not isinstance(data, bytes)):
        return _report("InvalidInput")
    report = _report("InvalidResponse", kind, http_status, len(data))
    if len(data) > MAX_INPUT_BYTES:
        report["status"] = "LimitExceeded"
        return report
    if http_status != 200:
        report["status"] = "TransportRejected"
        return report
    report["sourceSha256"] = hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8-sig")
        if kind == "bom":
            status, count, locators, candidates = _bom(text)
            # Publish all counts together only after every direct item validates.
            report.update(status=status, entryCount=count,
                          bomDownloadLocatorCount=locators,
                          comparisonSettingsCandidateCount=candidates)
        else:
            status, code, count = _catalog(text) if kind == "catalog" else _soap(text, kind)
            report.update(status=status, serviceCode=code, entryCount=count)
    except _LimitExceeded:
        report["status"] = "LimitExceeded"
    except (ValueError, ElementTree.ParseError, RecursionError, OverflowError):
        pass
    return report


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, _message):
        raise _InvalidResponse()


def main(argv=None):
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument("--kind", required=True, choices=KINDS)
    parser.add_argument("--http-status", required=True, type=int,
                        choices=range(100, 600), metavar="100..599")
    try:
        args = parser.parse_args(argv)
    except _InvalidResponse:
        print(json.dumps(_report("InvalidArguments"), sort_keys=True))
        return 2
    try:
        data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    except (OSError, ValueError):
        print(json.dumps(_report("InputReadFailed", args.kind, args.http_status), sort_keys=True))
        return 2
    result = inspect_response(data, args.kind, args.http_status)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in ("Completed", "CompletedEmpty", "NoPrimaryCatalog") else 1


if __name__ == "__main__":
    sys.exit(main())
