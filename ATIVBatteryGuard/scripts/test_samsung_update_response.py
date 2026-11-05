"""Synthetic response tests; no Samsung payloads, requests, or hardware calls."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape

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


def bom_item(name="synthetic-private-item", version="", locator=None, extra=""):
    locator_xml = "" if locator is None else f"<FURL>{escape(locator)}</FURL>"
    return (f"<Item><DisplayName>{escape(name)}</DisplayName>"
            f"<Version>{escape(version)}</Version>{locator_xml}{extra}</Item>")


def bom(items="", extra="", head_extra=""):
    return ("<MaxList><Head><Model>synthetic-private-model</Model>"
            f"<OS>synthetic-private-os</OS>{head_extra}</Head>"
            f"{items}{extra}</MaxList>").encode()


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
                       "private-path", "token=private", "NOT FOUND",
                       "Easy Settings for Win7 2.0.0.89", "2.0.0.89"):
            self.assertNotIn(secret, rendered)

    def inspect(self, data, kind="models", http_status=200):
        report = response.inspect_response(data, kind, http_status)
        self.assert_closed(report)
        return report

    def assert_failure(self, data, kind="models", status="InvalidResponse"):
        report = self.inspect(data, kind)
        self.assertEqual(status, report["status"])
        self.assertIsNone(report["entryCount"])
        self.assertIsNone(report["bomDownloadLocatorCount"])
        self.assertIsNone(report["comparisonSettingsCandidateCount"])
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

    def test_bom_missing_or_empty_locators_and_versions_preserve_metadata_items(self):
        data = bom(bom_item() + bom_item(locator="") +
                   bom_item(version="synthetic-private-version",
                            locator="https://example.invalid/metadata.xml"),
                   head_extra="<Test>Yes</Test>")
        report = self.inspect(data, "bom")
        self.assertEqual("Completed", report["status"])
        self.assertEqual(3, report["entryCount"])
        self.assertEqual(1, report["bomDownloadLocatorCount"])
        self.assertEqual(0, report["comparisonSettingsCandidateCount"])
        self.assertIsNone(report["serviceCode"])

    def test_bom_comparison_candidates_require_both_exact_direct_fields(self):
        exact_name, exact_version = "Easy Settings for Win7 2.0.0.89", "2.0.0.89"
        candidate = bom_item(exact_name, exact_version,
                             "https://example.invalid/private-path/metadata.xml",
                             "<CheckType>FileVer</CheckType>"
                             "<VerifyAttribute>2.0.0.89</VerifyAttribute>"
                             "<InstallFileSize>synthetic-private-size</InstallFileSize>"
                             "<InstallPara1>synthetic-private-command</InstallPara1>")
        items = (candidate + bom_item(exact_name, "different-version") +
                 bom_item("different-name", exact_version) +
                 bom_item(exact_name.lower(), exact_version))
        report = self.inspect(bom(items, extra=f"<Unknown>{candidate}</Unknown>"), "bom")
        self.assertEqual(4, report["entryCount"])
        self.assertEqual(1, report["bomDownloadLocatorCount"])
        self.assertEqual(1, report["comparisonSettingsCandidateCount"])
        self.assertFalse(report["catalogHashCryptographicallyVerified"])

    def test_bom_explicit_zero_direct_items_is_empty_without_feature_absence(self):
        for extra in ("", f"<Unknown>{bom_item()}</Unknown>"):
            with self.subTest(nested_item=bool(extra)):
                report = self.inspect(bom(extra=extra), "bom")
                self.assertEqual("CompletedEmpty", report["status"])
                for key in ("entryCount", "bomDownloadLocatorCount", "comparisonSettingsCandidateCount"):
                    self.assertEqual(0, report[key])
                self.assertFalse(report["canInferFeatureAbsence"])

    def test_bom_wrong_structure_duplicate_and_complex_core_fields_are_rejected(self):
        valid = bom(bom_item())
        invalid = [
            valid.replace(b"MaxList", b"maxlist"),
            valid.replace(b"<MaxList>", b'<MaxList xmlns="https://example.invalid/">'),
            valid.replace(b"<Head>", b"<Unknown><Head>")
                .replace(b"</Head>", b"</Head></Unknown>"),
            valid.replace(b"</Head>", b"</Head><Head/>"),
            valid.replace(b"<Model>synthetic-private-model</Model>", b""),
            bom(head_extra="<OS>duplicate</OS>"),
            bom(head_extra="<Model>duplicate</Model>"),
            bom(bom_item(extra="<DisplayName>duplicate</DisplayName>")),
            bom(bom_item(extra="<Version>duplicate</Version>")),
            bom(bom_item(locator="", extra="<FURL/>")),
            valid.replace(b"<Version></Version>", b"<Version><Nested/></Version>"),
            valid.replace(b"<DisplayName>", b'<DisplayName id="synthetic-private-id">'),
            valid.replace(b"<Version></Version>", b""),
        ]
        for index, data in enumerate(invalid):
            with self.subTest(index=index):
                self.assert_failure(data, "bom")
        self.assert_failure(soap(), "bom")
        self.assert_failure(catalog(), "bom")
        self.assert_failure(valid, "models")

    def test_bom_late_invalid_or_truncated_item_discards_all_counts(self):
        first = bom_item("Easy Settings for Win7 2.0.0.89", "2.0.0.89",
                         "https://example.invalid/metadata.xml")
        invalid_items = [bom_item(locator="file:///synthetic-private-path"),
                         bom_item(extra="<Version>duplicate</Version>"),
                         "<Item><DisplayName>synthetic-private-tail</DisplayName></Item>"]
        self.assertEqual(1, self.inspect(bom(first), "bom")["comparisonSettingsCandidateCount"])
        for last in invalid_items:
            with self.subTest(last=last[:20]):
                self.assert_failure(bom(first + last), "bom")
        self.assert_failure(bom(first + bom_item())[:-3], "bom")

    def test_bom_hostile_xml_encodings_and_locators_never_emit_metadata(self):
        valid = bom(bom_item())
        invalid = [b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///synthetic-private">]>' + valid,
                   b'<!DOCTYPE x [<!ENTITY x "content">]>' + valid,
                   valid.decode().encode("utf-16"), b"\xff" + valid,
                   valid.replace(b"<Version></Version>", b"<Version>&unknown;</Version>")]
        for data in invalid:
            with self.subTest(size=len(data)):
                self.assert_failure(data, "bom")
        for locator in ("ftp://example.invalid/a", "https://user:password@example.invalid/a",
                        "https://example.invalid/a#private", "https://example.invalid:bad/a",
                        "https://example.invalid/a\nb"):
            with self.subTest(locator=locator):
                self.assert_failure(bom(bom_item(locator=locator)), "bom")

    def test_bom_accepts_8271_nodes_without_raising_existing_soap_budget(self):
        # MaxList + Head + Model + OS + Metadata + 8266 padding nodes = 8271.
        data = bom(extra="<Metadata>" + "<Padding/>" * 8266 + "</Metadata>")
        self.assertEqual(8271, sum(1 for _ in response.ElementTree.fromstring(data).iter()))
        self.assertEqual("CompletedEmpty", self.inspect(data, "bom")["status"])
        self.assert_failure(data, "models", "LimitExceeded")
        self.assertEqual(8192, response.MAX_NODES)
        self.assertEqual(32, response.MAX_DEPTH)

    def test_bom_has_separate_node_depth_and_item_boundary_limits(self):
        at_nodes = bom(extra="<Metadata>" + "<Padding/>" * (16384 - 5) + "</Metadata>")
        over_nodes = bom(extra="<Metadata>" + "<Padding/>" * (16385 - 5) + "</Metadata>")
        self.assertEqual("CompletedEmpty", self.inspect(at_nodes, "bom")["status"])
        self.assert_failure(over_nodes, "bom", "LimitExceeded")
        at_depth = bom(extra="<Layer>" * 15 + "</Layer>" * 15)
        over_depth = bom(extra="<Layer>" * 16 + "</Layer>" * 16)
        self.assertEqual("CompletedEmpty", self.inspect(at_depth, "bom")["status"])
        self.assert_failure(over_depth, "bom", "LimitExceeded")
        self.assertEqual(256, self.inspect(bom(bom_item() * 256), "bom")["entryCount"])
        self.assert_failure(bom(bom_item() * 257), "bom", "LimitExceeded")

    def test_bom_plain_text_limits_allow_empty_fields_but_reject_oversize(self):
        self.assertEqual("Completed", self.inspect(bom(bom_item("", "", "")), "bom")["status"])
        multiline = bom(bom_item("synthetic-private\nmultiline\tlabel"))
        self.assertEqual("Completed", self.inspect(multiline, "bom")["status"])
        self.assertEqual(1, self.inspect(bom(bom_item("x" * 512, "v" * 128)), "bom")["entryCount"])
        for record in (bom_item("x" * 513), bom_item(version="v" * 129),
                       bom_item(locator="https://example.invalid/" + "x" * 4096)):
            with self.subTest(size=len(record)):
                self.assert_failure(bom(record), "bom")
        self.assert_failure(bom().replace(b"synthetic-private-model", b"x" * 129), "bom")

    def test_bom_transport_is_checked_before_xml_and_other_kinds_have_no_bom_counts(self):
        with patch.object(response, "_xml_root") as parser:
            report = self.inspect(b"<!DOCTYPE untrusted [bad]>", "bom", 403)
            self.assertEqual("TransportRejected", report["status"])
            parser.assert_not_called()
            self.assertIsNone(report["sourceSha256"])
        for data, kind in ((soap(), "models"), (catalog(), "catalog")):
            with self.subTest(kind=kind):
                report = self.inspect(data, kind)
                self.assertIsNone(report["bomDownloadLocatorCount"])
                self.assertIsNone(report["comparisonSettingsCandidateCount"])

    def test_bom_cli_is_stdin_only_bounded_and_clears_previous_success_counts(self):
        args = ["--kind", "bom", "--http-status", "200"]
        valid = bom(bom_item("Easy Settings for Win7 2.0.0.89", "2.0.0.89",
                             "https://example.invalid/metadata.xml"))
        with patch.object(response.sys, "stdin") as stdin, patch("builtins.open") as opened, \
                patch("socket.socket") as network:
            stdin.buffer.read.return_value = valid
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(0, response.main(args))
            report = json.loads(output.getvalue())
            self.assertEqual(1, report["comparisonSettingsCandidateCount"])
            self.assert_closed(report)
            stdin.buffer.read.assert_called_once_with(response.MAX_INPUT_BYTES + 1)
            opened.assert_not_called()
            network.assert_not_called()
            stdin.buffer.read.return_value = valid[:-3]
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(1, response.main(args))
            report = json.loads(output.getvalue())
            for key in ("entryCount", "bomDownloadLocatorCount", "comparisonSettingsCandidateCount"):
                self.assertIsNone(report[key])
        with patch.object(response.sys, "stdin") as stdin, patch.object(response.hashlib, "sha256") as digest:
            stdin.buffer.read.return_value = b"x" * (response.MAX_INPUT_BYTES + 1)
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(1, response.main(args))
            stdin.buffer.read.assert_called_once_with(response.MAX_INPUT_BYTES + 1)
            digest.assert_not_called()
            self.assertEqual("LimitExceeded", json.loads(output.getvalue())["status"])


if __name__ == "__main__":
    unittest.main()
