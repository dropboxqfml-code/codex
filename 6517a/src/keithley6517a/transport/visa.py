"""VISA USB-GPIB adapter backend, not USBTMC and not Prologix serial."""

import math
import threading

from .base import CommunicationError


class VisaTransport:
    is_simulation = False

    def __init__(
        self,
        resource: str,
        backend: str = "",
        timeout_ms: int = 2000,
        read_termination: str | None = "\n",
        write_termination: str | None = "\n",
        send_end: bool = True,
    ):
        if not resource.upper().startswith("GPIB"):
            raise ValueError("Select an explicit VISA GPIB resource; serial/USBTMC is unsupported")
        if not math.isfinite(timeout_ms) or timeout_ms <= 0:
            raise ValueError("VISA timeout must be finite and positive")
        self.resource, self.backend, self.timeout_ms = resource, backend, int(timeout_ms)
        self.read_termination, self.write_termination = read_termination, write_termination
        self.send_end = send_end
        self.session = self.manager = None
        self.owner = None
        self.lock_acquired = False

    @staticmethod
    def list_resources(backend: str = "") -> tuple[str, ...]:
        import pyvisa

        manager = pyvisa.ResourceManager(backend or "")
        try:
            return tuple(r for r in manager.list_resources() if r.upper().startswith("GPIB"))
        finally:
            manager.close()

    def _owned(self):
        if self.owner != threading.get_ident() or self.session is None:
            raise CommunicationError("VISA session must be accessed by its single owning worker")
        return self.session

    def open(self):
        if self.session is not None:
            raise CommunicationError("Close the existing VISA session before reconnecting")
        import pyvisa

        self.manager = pyvisa.ResourceManager(self.backend or "")
        try:
            self.session = self.manager.open_resource(self.resource)
            self.owner = threading.get_ident()
            self.session.timeout = self.timeout_ms
            self.session.read_termination = self.read_termination
            self.session.write_termination = self.write_termination
            self.session.send_end = self.send_end
            try:
                self.session.lock_excl(timeout=self.timeout_ms)
                self.lock_acquired = True
            except pyvisa.errors.VisaIOError as exc:
                # Only explicit unsupported locking is acceptable; busy/timeout is fatal.
                if exc.error_code != pyvisa.constants.StatusCode.error_nonsupported_operation:
                    raise
        except Exception:
            self.close()
            raise

    def write(self, command):
        self._owned().write(command)

    def query(self, command):
        # PyVISA query completes its read before returning. No blind retries or clears.
        return self._owned().query(command)

    def read(self):
        return self._owned().read()

    def cancel_or_abort_io_if_supported(self):
        # This synchronous owner cannot cancel another thread's VISA request safely.
        # Bounded timeout is the maximum I/O latency. Device clear is NOT output OFF.
        self._owned()

    def close(self):
        if self.session is not None and self.owner != threading.get_ident():
            raise CommunicationError("Only the VISA owner can close its session")
        errors = []
        try:
            if self.session is not None:
                if self.lock_acquired:
                    try:
                        self.session.unlock()
                    except Exception as exc:
                        errors.append(exc)
                try:
                    self.session.close()
                except Exception as exc:
                    errors.append(exc)
        finally:
            self.session = None
            self.lock_acquired = False
            self.owner = None
            if self.manager is not None:
                try:
                    self.manager.close()
                except Exception as exc:
                    errors.append(exc)
                finally:
                    self.manager = None
        if errors:
            raise CommunicationError(
                "VISA cleanup failed: " + "; ".join(map(str, errors))
            ) from errors[0]
