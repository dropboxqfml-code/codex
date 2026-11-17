"""The delivered compatibility proof must reject ACQ regressions and lost failure records."""

import importlib.util
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("zero_smoke", PROJECT / "packaging/smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def test_native_zero_correction_proof_checks_compatible_arm_and_preserved_device_errors(tmp_path):
    assert smoke.zero_correction_compatibility_smoke(tmp_path) == {
        "zero_correction_compatibility_verified": True
    }


def test_native_zero_proof_rejects_a_regression_that_sends_acquire(tmp_path, monkeypatch):
    from keithley6517a.driver.instrument import Instrument
    from keithley6517a.driver.parser import ProtocolError

    original = Instrument.configure

    def old_acquire(self, config):
        self._write(":SYST:ZCOR:ACQ")
        return original(self, config)

    monkeypatch.setattr(Instrument, "configure", old_acquire)
    with pytest.raises(ProtocolError, match="Execution error"):
        smoke.zero_correction_compatibility_smoke(tmp_path)


def test_native_zero_proof_rejects_missing_arm_failure_record(tmp_path, monkeypatch):
    from keithley6517a.driver.parser import ProtocolError
    from keithley6517a.measurement.runner import MeasurementRunner

    original = MeasurementRunner.arm

    def lose_record(self):
        try:
            return original(self)
        except ProtocolError:
            self.last_arm_failure_report["report_saved"] = False
            raise

    monkeypatch.setattr(MeasurementRunner, "arm", lose_record)
    with pytest.raises(RuntimeError, match="did not persist"):
        smoke.zero_correction_compatibility_smoke(tmp_path)
