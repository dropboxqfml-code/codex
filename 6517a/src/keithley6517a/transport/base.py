"""The protocol has a single synchronous I/O owner, the measurement worker."""

from typing import Protocol


class Transport(Protocol):
    is_simulation: bool

    def open(self) -> None: ...
    def close(self) -> None: ...
    def write(self, command: str) -> None: ...
    def query(self, command: str) -> str: ...
    def read(self) -> str: ...
    def cancel_or_abort_io_if_supported(self) -> None: ...


class CommunicationError(RuntimeError):
    """A failed exchange must abort; output writes are never retried automatically."""


class UnsupportedOperation(RuntimeError):
    """Not available with the current verified hardware profile."""
