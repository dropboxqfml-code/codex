"""Synthetic response tests; no Samsung payloads, requests, or hardware calls."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import unittest
from unittest.mock import patch

import inspect_samsung_update_response as response


def soap(kind="models", code="0", records="", extra="", info_extra=""):
    method = response.OPERATIONS[kind][0]
    return (f'<s:Envelope xmlns:s="{response.SOAP_NS}"><s:Body>'
            f'<{method}Response xmlns="{response.OP_NS}"><{method}Result>'
            f'<ResultInfo><ResultCode>{code}</ResultCode>'
            f'<ResultDesc>synthetic-private-error</ResultDesc>{info_extra}</ResultInfo>'
            f'{records}{extra}</{method}Result></{method}Response>'
            '</s:Body></s:Envelope>').encode()


def catalog(items=None, **fields):
    data = dict(Result="SUCC", SN="synthetic-private-serial", FailInfo=None,
                HDM={"ITEM": [] if items is None else items})
    data.update(fields)
    return json.dumps(data).encode()


def item(**fields):
    data = dict(ID="synthetic-private-id", HASHCODE="1234ABCD",
                FURL="https://example.invalid/private-path/metadata.xml?token=private")
    data.update(fields)
    return data


class SamsungUpdateResponseTests(unittest.TestCase):
    def assert_closed(self, report):
        for key in ("manufacturerAuthenticityVerified", "currentDeviceIdentityVerified",
                    "currentModelCompatibilityVerified", "batteryCommandContractVerified",
                    "sourcePayloadIntegrityVerified", "catalogHashCryptographicallyVerified",
                    "canInferFeatureAbsence", "canReadHardware", "canInvokeMethods",
                    "canWriteHardware", "networkAccessPerformed", "locatorFetched",
                    "vendorCodeExecuted"):
            self.assertIs(report[key], False, key)
        rendered = json.dumps(report)
        for secret in ("synthetic-private", "example.invalid", "metadata.xml", "1234ABCD",
                       "private-path", "token=private", "NOT FOUND"):
            self.assertNotIn(secret, rendered)

    def inspect(self, data, kind="models", http_status=200):
        report = response.inspect_response(data, kind, http_status)
        self.assert_closed(report)
        return report

    def assert_failure(self, data, kind="models", status="InvalidResponse"):
        report = self.inspect(data, kind)
        self.assertEqual(status, report["status"])
        self.assertIsNone(report["entryCount"])
        return report

    def test_all_soap_operations_count_only_their_direct_records(self):
        for kind, (_method, tag) in response.OPERATIONS.items():
            with self.subTest(kind=kind):
                data = soap(kind, records=f'<{tag}>synthetic-private-record</{tag}>',
                            extra=f'<Unknown><{tag}>not-a-direct-record</{tag}></Unknown>')
                report = self.inspect(data, kind)
                self.assertEqual("Completed", report["status"])
                self.assertEqual(1, report["entryCount"])
                self.assertEqual("0", report["serviceCode"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), report["sourceSha256"])
        # Model discovery alone never establishes a catalog or battery contract.
        self.assert_failure(soap(), "catalog")

    def test_http_200_is_not_service_success_and_stale_entries_are_discarded(self):
        for kind, (_method, tag) in response.OPERATIONS.items():
            with self.subTest(kind=kind):
                report = self.assert_failure(soap(kind, "404", f'<{tag}>stale</{tag}>'),
                                             kind, "ServiceRejected")
                self.assertEqual("404", report["serviceCode"])
        data = catalog([item()], Result="FAIL", FailInfo={"FailCode": 404,
                                                       "Desc": "NOT FOUND"})
        report = self.assert_failure(data, "catalog", "ServiceRejected")
        self.assertEqual("404", report["serviceCode"])

    def test_successful_zero_records_are_completed_empty_not_absence(self):
        for kind in response.OPERATIONS:
            with self.subTest(kind=kind):
                report = self.inspect(soap(kind), kind)
                self.assertEqual("CompletedEmpty", report["status"])
                self.assertEqual(0, report["entryCount"])
        report = self.inspect(catalog(), "catalog")
        self.assertEqual("CompletedEmpty", report["status"])
        self.assertEqual(0, report["entryCount"])

    def test_soap_structure_namespaces_duplicates_and_ambiguous_success_are_rejected(self):
        data = soap(records="<DerivedModel>valid</DerivedModel>")
        invalid = [
            data.replace(b"GetModelListBykeyword", b"WrongMethod"),
            data.replace(response.OP_NS.encode(), b"https://example.invalid/"),
            soap(info_extra="<ResultCode>0</ResultCode>"),
            soap(extra="<ResultInfo><ResultCode>0</ResultCode></ResultInfo>"),
            data.replace(b"<ResultInfo>", b"<Wrapper><ResultInfo>")
                .replace(b"</ResultInfo>", b"</ResultInfo></Wrapper>"),
            data.replace(b"</s:Body>", b"</s:Body><s:Body/>"),
            data.replace(b"</GetModelListBykeywordResponse>",
                         b"<GetModelListBykeywordResult/></GetModelListBykeywordResponse>"),
            soap("model-code", records="<ModelCode>a</ModelCode><ModelCode>b</ModelCode>"),
        ]
        for index, malformed in enumerate(invalid):
            with self.subTest(index=index):
                self.assert_failure(malformed, "model-code" if index == 7 else "models")
        # A nested successful code cannot override the actual direct rejection.
        report = self.assert_failure(soap(code="404", info_extra=
            "<Unknown><ResultCode>0</ResultCode></Unknown>"), status="ServiceRejected")
        self.assertEqual("404", report["serviceCode"])

    def test_soap_fault_has_a_distinct_private_failure_state(self):
        data = (f'<s:Envelope xmlns:s="{response.SOAP_NS}"><s:Body><s:Fault>'
                '<faultcode>synthetic-private-fault</faultcode>'
                '<faultstring>synthetic-private-error</faultstring>'
                '</s:Fault></s:Body></s:Envelope>').encode()
        report = self.assert_failure(data, status="SoapFault")
        self.assertIsNone(report["serviceCode"])

    def test_catalog_single_or_list_locators_are_counted_without_hash_verification(self):
        for entries, count in ((item(), 1), ([item(), item()], 2)):
            with self.subTest(count=count):
                report = self.inspect(catalog(entries), "catalog")
                self.assertEqual("Completed", report["status"])
                self.assertEqual(count, report["entryCount"])
                self.assertEqual("SUCC", report["serviceCode"])
                self.assertFalse(report["catalogHashCryptographicallyVerified"])

    def test_null_primary_catalog_and_explicit_empty_are_distinct(self):
        report = self.inspect(catalog(HDM=None), "catalog")
        self.assertEqual("NoPrimaryCatalog", report["status"])
        self.assertIsNone(report["entryCount"])
        for primary in ({}, {"ITEM": None}, {"ITEM": ""}, [], ""):
            with self.subTest(primary=primary):
                self.assert_failure(catalog(HDM=primary), "catalog")
        self.assert_failure(b'{"Result":"SUCC"}', "catalog")

    def test_json_duplicate_keys_conflicts_unknown_results_and_non_json_constants_fail(self):
        invalid = [
            b'{"Result":"FAIL","Result":"SUCC","HDM":{"ITEM":[]}}',
            b'{"Result":"SUCC","HDM":{"ITEM":[],"ITEM":[]}}',
            b'{"Result":"FAIL","FailInfo":{"FailCode":404,"FailCode":0}}',
            catalog(Result="succ"), catalog(Result="UNKNOWN"),
            catalog(FailInfo={"FailCode": 404}),
            catalog(Result="FAIL", FailInfo=None),
            catalog(Result="FAIL", FailInfo={"FailCode": "synthetic-private-error"}),
            b'{"Result":"SUCC","HDM":{"ITEM":[]},"extra":NaN}',
            b'{"Result":"SUCC","HDM":{"ITEM":[]},"extra":Infinity}',
        ]
        for index, data in enumerate(invalid):
            with self.subTest(index=index):
                self.assert_failure(data, "catalog")

    def test_invalid_catalog_locators_or_late_records_fail_atomically(self):
        for locator in (None, "", "file:///synthetic-private/path", "ftp://example.invalid/a",
                        "https://user:password@example.invalid/a", "https://example.invalid/a\n",
                        "https://example.invalid:bad/a", "https://example.invalid/a#private"):
            with self.subTest(locator=locator):
                self.assert_failure(catalog([item(), item(FURL=locator)]), "catalog")
        self.assert_failure(catalog([item(), {"ID": "without-locator"}]), "catalog")
        self.assert_failure(soap(records="<DerivedModel>good</DerivedModel>"
                               "<DerivedModel><Nested>bad</Nested></DerivedModel>"))

    def test_malformed_truncated_encoding_and_xml_entities_never_emit_partial_counts(self):
        valid = soap(records="<DerivedModel>valid</DerivedModel>")
        invalid = [valid[:-8], b"", b"\xff", valid.decode().encode("utf-16"),
                   b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///synthetic-private">]>' + valid,
                   b'<!DOCTYPE x [<!ENTITY x "content">]>' + valid,
                   valid.replace(b"<DerivedModel>valid", b"<DerivedModel>&unknown;valid")]
        for index, data in enumerate(invalid):
            with self.subTest(index=index):
                self.assert_failure(data)
        for data in (catalog([item()])[:-2], b'{"Result":"SUCC",', b"[]", b"null"):
            with self.subTest(data=data[:20]):
                self.assert_failure(data, "catalog")

    def test_input_depth_node_and_record_limits_are_bounded_for_both_formats(self):
        self.assert_failure(b"x" * (response.MAX_INPUT_BYTES + 1), status="LimitExceeded")
        deep_xml = b"<x>" * 33 + b"</x>" * 33
        self.assert_failure(deep_xml, status="LimitExceeded")
        self.assert_failure(b"<x>" + b"<y/>" * 8192 + b"</x>", status="LimitExceeded")
        self.assert_failure(soap(records="<DerivedModel>x</DerivedModel>" * 2049),
                            status="LimitExceeded")
        for data in (b"[" * 33 + b"0" + b"]" * 33,
                     json.dumps([0] * 8192).encode(), catalog([item()] * 2049),
                     # Stay below MAX_NODES so this reaches the record limit.
                     catalog([{"FURL": "https://example.invalid/bom.xml"}] * 2049)):
            with self.subTest(size=len(data)):
                self.assert_failure(data, "catalog", "LimitExceeded")
        # Brackets and escaped quotes inside strings do not consume nesting.
        report = self.inspect(catalog(extra='[[[\\"' * 40), "catalog")
        self.assertEqual("CompletedEmpty", report["status"])

    def test_non_200_transport_precedes_parsing_and_input_contract_is_strict(self):
        for http_status in (100, 204, 301, 404, 500, 599):
            with self.subTest(http_status=http_status), patch.object(response, "_xml_root") as parser:
                report = self.inspect(b"<!DOCTYPE untrusted [bad]>", http_status=http_status)
                self.assertEqual("TransportRejected", report["status"])
                self.assertIsNone(report["sourceSha256"])
                parser.assert_not_called()
        for data, kind, status in ((b"", "unknown", 200), (b"", "models", True),
                                   (b"", "models", 99), (b"", "models", 600),
                                   ("not-bytes", "models", 200)):
            with self.subTest(kind=kind, status=status):
                self.assertEqual("InvalidInput", self.inspect(data, kind, status)["status"])

    def test_cli_requires_transport_and_sanitizes_argument_and_read_errors(self):
        for args in (["--kind", "models"], ["--kind", "synthetic-private-name",
                      "--http-status", "200"], ["--kind", "models", "--http-status", "600"],
                     ["--kind", "models", "--http-status", "200", "synthetic-private-path"]):
            with self.subTest(args=args):
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(response.sys, "stdin") as stdin, redirect_stdout(stdout), redirect_stderr(stderr):
                    self.assertEqual(2, response.main(args))
                    stdin.buffer.read.assert_not_called()
                self.assertEqual("", stderr.getvalue())
                report = json.loads(stdout.getvalue())
                self.assertEqual("InvalidArguments", report["status"])
                self.assert_closed(report)
        with patch.object(response.sys, "stdin") as stdin, redirect_stdout(io.StringIO()) as output:
            stdin.buffer.read.side_effect = OSError("synthetic-private-path")
            self.assertEqual(2, response.main(["--kind", "models", "--http-status", "200"]))
        self.assertEqual("InputReadFailed", json.loads(output.getvalue())["status"])
        self.assertNotIn("synthetic-private", output.getvalue())

    def test_cli_caps_stdin_before_hashing_and_reports_only_sanitized_json(self):
        args = ["--kind", "catalog", "--http-status", "200"]
        with patch.object(response.sys, "stdin") as stdin, patch.object(response.hashlib, "sha256") as digest:
            stdin.buffer.read.return_value = b"x" * (response.MAX_INPUT_BYTES + 1)
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(1, response.main(args))
            stdin.buffer.read.assert_called_once_with(response.MAX_INPUT_BYTES + 1)
            digest.assert_not_called()
            report = json.loads(output.getvalue())
            self.assertEqual("LimitExceeded", report["status"])
            self.assertIsNone(report["sourceSha256"])
            self.assert_closed(report)
        with patch.object(response.sys, "stdin") as stdin, redirect_stdout(io.StringIO()) as output:
            stdin.buffer.read.return_value = catalog(item())
            self.assertEqual(0, response.main(args))
        report = json.loads(output.getvalue())
        self.assertEqual("Completed", report["status"])
        self.assertEqual(1, report["entryCount"])
        self.assert_closed(report)


if __name__ == "__main__":
    unittest.main()
