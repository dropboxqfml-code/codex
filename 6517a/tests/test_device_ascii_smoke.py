"""Delivered device-format proof preserves values and catches a suffix regression."""

import importlib.util
import re
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("device_ascii_smoke", PROJECT / "packaging/smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def test_native_device_format_proof_checks_capture_saved_values_and_duplicate_rejection(tmp_path):
    assert smoke.device_ascii_compatibility_smoke(tmp_path) == {
        "device_ascii_compatibility_verified": True
    }


def test_native_device_format_proof_rejects_parser_with_only_manual_suffix(tmp_path, monkeypatch):
    from keithley6517a.driver import parser

    monkeypatch.setattr(parser, "RNUM", re.compile(r"([+-]?\d+)rdg#", re.IGNORECASE))
    with pytest.raises(parser.ProtocolError, match="Malformed ASCII response"):
        smoke.device_ascii_compatibility_smoke(tmp_path)
