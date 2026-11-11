"""Command-driven emulator using the Rev. D 6517A manual ASCII/profile contract.

Responses are synthetic manual-derived fixtures, never measured device traces.
The electrical model does not validate physical materials or hardware safety.
"""

import math
import random
import threading
import time

from .base import CommunicationError


class SimulatorTransport:
    is_simulation = True

    def __init__(
        self,
        clock=None,
        seed=6517,
        faults=None,
        resistance_ohm=1e12,
        offset_A=2e-14,
        noise_A=1e-14,
        absorption_A=2e-12,
        tau_s=3.0,
        drift_A_per_s=0.0,
    ):
        self.clock = clock or time
        self.seed = seed
        self.rng = random.Random(seed)
        self.faults = dict(faults or {})
        self.resistance_ohm, self.offset_A, self.noise_A = resistance_ohm, offset_A, noise_A
        self.absorption_A, self.tau_s, self.drift_A_per_s = absorption_A, tau_s, drift_A_per_s
        self.commands = []
        self.opened = False
        self.owner = None
        self.output = False
        self.voltage = 0.0
        self.voltage_change_time = self.clock.monotonic()
        self.read_count = 0
        self.last_number = 0
        self.values = {
            ":INIT:CONT": "0",
            ":SYST:ZCH": "1",
            ":SYST:ZCOR": "0",
            ":SENS:RES:VSC": "MAN",
            ":SENS:RES:MSEL": "NORM",
            ":SOUR:VOLT:RANG": "100",
            ":SOUR:VOLT:LIM": "10",
            ":SOUR:VOLT:LIM:STAT": "1",
            ":SOUR:VOLT:MCON": "0",
            ":SOUR:CURR:RLIM:STAT": "0",
            ":SENS:FUNC": "CURR",
            ":SENS:CURR:RANG:AUTO": "1",
            ":SENS:CURR:RANG": "2e-9",
            ":SENS:CURR:NPLC": "10",
            ":SENS:CURR:NPLC:AUTO": "0",
            ":SENS:RES:NPLC": "10",
            ":SENS:RES:NPLC:AUTO": "0",
            ":SENS:RES:MAN:CRANG:AUTO": "1",
            ":SENS:RES:MAN:CRANG": "2e-9",
            ":FORM:DATA": "ASC",
            ":FORM:ELEM": "READ,STAT,UNIT,RNUM,VSO",
            ":ARM:SOUR": "IMM",
            ":ARM:COUN": "1",
            ":ARM:LAY2:SOUR": "IMM",
            ":ARM:LAY2:COUN": "1",
            ":ARM:LAY2:DEL": "0",
            ":TRIG:SOUR": "IMM",
            ":TRIG:COUN": "1",
            ":TRIG:DEL": "0",
            ":SENS:CURR:AVER:STAT": "0",
            ":SENS:CURR:MED:STAT": "0",
            ":SENS:RES:AVER:STAT": "0",
            ":SENS:RES:MED:STAT": "0",
            ":SENS:CURR:REF:STAT": "0",
            ":SENS:RES:REF:STAT": "0",
            ":SENS:RES:IREF": "0",
            ":CALC:STAT": "0",
            ":CALC2:STAT": "0",
            ":CALC3:LIM1:STAT": "0",
            ":CALC3:LIM2:STAT": "0",
            ":ROUT:SCAN:LSEL": "NONE",
            ":TRAC:FEED:CONT": "NEV",
            ":SYST:HLC": "1",
        }
        self.last_response = None
        self.errors = []
        self.line_frequency_hz = 60

    @property
    def truth(self):
        return {
            "seed": self.seed,
            "resistance_ohm": self.resistance_ohm,
            "offset_A": self.offset_A,
            "noise_A": self.noise_A,
            "absorption_A": self.absorption_A,
            "tau_s": self.tau_s,
            "drift_A_per_s": self.drift_A_per_s,
            "model": "V/R + A*exp(-t/tau) + offset + drift*t + seeded Gaussian noise",
            "not_material_validation": True,
        }

    def _owned(self):
        if not self.opened or self.owner != threading.get_ident():
            raise CommunicationError("Simulator disconnected or wrong I/O owner")

    def open(self):
        if self.opened:
            raise CommunicationError("Already open")
        self.opened, self.owner = True, threading.get_ident()

    def close(self):
        self.opened = False
        self.owner = None

    def cancel_or_abort_io_if_supported(self):
        self._owned()
        if self.faults.get("fail_cancel"):
            raise CommunicationError("Injected cancellation failure")

    def _canonical(self, command):
        return command.strip().upper()

    def write(self, command):
        self._owned()
        command = self._canonical(command)
        self.commands.append(command)
        if command == ":ABOR":
            if self.faults.get("fail_abort"):
                raise CommunicationError("Injected abort failure")
            return
        if command == ":TSEQ:ABOR":
            if self.faults.get("fail_sequence_abort"):
                raise CommunicationError("Injected test sequence abort failure")
            return
        if command == ":SYST:ZCOR:ACQ":
            if self.values[":SYST:ZCH"] != "1" or self.output:
                raise CommunicationError("Zero acquire requires Zero Check ON and output OFF")
            return
        try:
            key, value = command.split(" ", 1)
        except ValueError as exc:
            raise CommunicationError(f"Unsupported simulator command {command}") from exc
        if key == ":OUTP1":
            on = value in ("ON", "1")
            if not on and self.faults.get("fail_off"):
                raise CommunicationError("Injected output OFF failure")
            if on and self.faults.get("interlock", 1) != 1:
                raise CommunicationError("Interlock open")
            self.output = on
            return
        if key == ":SYST:ZCH" and self.faults.get("fail_zero_check"):
            raise CommunicationError("Injected Zero Check command failure")
        if key == ":SOUR:VOLT":
            requested = float(value)
            if not math.isfinite(requested):
                raise CommunicationError("Non-finite source voltage")
            ceiling = float(self.values[":SOUR:VOLT:LIM"])
            clamp = self.faults.get("limit_clamp_V", ceiling)
            self.voltage = math.copysign(min(abs(requested), ceiling, clamp), requested)
            self.voltage_change_time = self.clock.monotonic()
            return
        allowed = set(self.values)
        if key not in allowed:
            raise CommunicationError(f"Unsupported simulator command {command}")
        value = {"ON": "1", "OFF": "0", "MANUAL": "MAN", "NORMAL": "NORM", "ASCII": "ASC"}.get(
            value, value
        )
        self.values[key] = value.strip("'\"")

    def query(self, command):
        self._owned()
        command = self._canonical(command)
        self.commands.append(command)
        if command == "*IDN?":
            return self.faults.get("idn", "KEITHLEY INSTRUMENTS INC.,MODEL 6517A,SIM0001,SIM-1.0")
        if command == "*OPC?":
            return "1"
        if command == ":OUTP1?":
            if self.faults.get("output_query_failure"):
                raise CommunicationError("Injected output query failure")
            return "1" if self.output else "0"
        if command == ":SOUR:VOLT?":
            return str(self.voltage + self.faults.get("readback_mismatch_V", 0.0))
        if command == ":SOUR:CURR:LIM:STAT?":
            active = self.faults.get("source_current_limit", False)
            at = self.faults.get("current_limit_at_read")
            return str(int(active or (at is not None and self.read_count >= at)))
        if command == ":SYST:INT?":
            return str(self.faults.get("interlock", 1))
        if command == ":SYST:ERR?":
            return self.errors.pop(0) if self.errors else '0,"No error"'
        if command == ":READ?":
            return self._reading()
        if command.endswith("?") and command[:-1] in self.values:
            value = self.values[command[:-1]]
            if command == ":SYST:ZCH?" and self.faults.get("zero_check"):
                return "1"
            return value
        raise CommunicationError(f"Unsupported simulator query {command}")

    def read(self):
        self._owned()
        if self.last_response is None:
            raise CommunicationError("No pending complete response")
        response, self.last_response = self.last_response, None
        return response

    def _reading(self):
        self.read_count += 1
        n = self.read_count
        if self.faults.get("timeout_at_read") == n:
            raise TimeoutError("Injected read timeout; no retry")
        if self.faults.get("disconnect_at_read") == n:
            self.opened = False
            raise CommunicationError("Injected USB disconnection; physical output can remain ON")
        nplc_key = (
            ":SENS:RES:NPLC" if self.values[":SENS:FUNC"].startswith("RES") else ":SENS:CURR:NPLC"
        )
        self.clock.sleep(float(self.values[nplc_key]) / self.line_frequency_hz)
        delay = self.faults.get("delay_s", 0)
        if delay:
            self.clock.sleep(delay)
        if self.faults.get("malformed_at_read") == n:
            return "broken,ADC,not-a-number"
        if self.faults.get("split_response_at_read") == n:
            # The first partial response is deliberately invalid. Do not concatenate
            # it with the next query's reply or retry a possibly executed operation.
            self.last_response = "-11NADC,+00001rdg#,+0Vsrc"
            return "+1.0E"
        t = max(0.0, self.clock.monotonic() - self.voltage_change_time)
        volts = self.voltage if self.output else 0.0
        current = volts / self.resistance_ohm + self.offset_A + self.drift_A_per_s * t
        current += self.absorption_A * math.exp(-t / self.tau_s) if volts else 0.0
        current += self.rng.gauss(0, self.noise_A)
        if self.faults.get("sign_reverse_at_read") == n:
            current *= -1
        if self.faults.get("zero_current_at_read") == n:
            current = 0.0
        status = "N"
        if self.faults.get("reference"):
            status = "R"
        if self.values[":SYST:ZCH"] == "1" or self.faults.get("zero_check"):
            status = "Z"
        if self.faults.get("overflow_at_read") == n:
            status = "O"
        if self.faults.get("underflow_at_read") == n:
            status = "U"
        if self.faults.get("out_of_limit_at_read") == n:
            status = "L"
        native = self.values[":SENS:FUNC"].startswith("RES")
        value = (volts / current if current and volts else 9.9e37) if native else current
        if status in {"O", "L"}:
            value = 9.9e37
        if status == "U":
            value = 0.0
        if status == "Z":
            value = 9.91e37
        number = self.last_number if self.faults.get("stale_at_read") == n else n
        self.last_number = number
        if self.faults.get("range_change_at_read") == n:
            self.values[":SENS:CURR:RANG"] = "2e-8"
            self.values[":SENS:RES:MAN:CRANG"] = "2e-8"
        return (
            f"{value:+.8E}{status}{'OHM' if native else 'ADC'},{number:+06d}rdg#,{volts:+.8E}Vsrc"
        )
