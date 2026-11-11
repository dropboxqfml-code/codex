"""Opt-in NI-488.2/GPIB C-library bridge for the PyVISA-py backend.

This loads Python bindings, not a USB driver. NI-488.2 must already support the
adapter. No driver DLL is distributed, no resource is opened during preflight,
and a failed operation never switches to a different backend automatically.

Bindings and loader contract: gpib-ctypes 0.3.0 (gpib/gpib.py); backend contract:
PyVISA-py 0.8.1 (gpib.py). Hardware/firmware execution remains unverified here.
"""

from __future__ import annotations

import importlib
import platform
import struct
import warnings

from .base import CommunicationError


class NIBackendError(CommunicationError):
    """A pre-I/O failure with a stable diagnostic code and an actionable message."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def normalize_backend(backend: str | None) -> str:
    if backend is None:
        return "@ivi"
    if not isinstance(backend, str):
        raise ValueError("VISA backend must be a library path, backend name, or null")
    value = backend.strip()
    # PyVISA can choose PyVISA-py automatically for an empty backend when no
    # native VISA exists. Bundling the optional bridge must not change native
    # selection into an implicit experimental connection.
    if not value:
        return "@ivi"
    return value.lower() if value.lower() in ("@py", "@ivi") else value


def _usable_library(library) -> bool:
    """gpib-ctypes imports successfully even without a driver: reject its MockGPIB.

    Inspect exports without calling them. In particular, preflight must not use
    ibdev, ibfind, ibsic, clear, or any other device/bus operation as a probe.
    """
    if not isinstance(getattr(library, "_name", None), str):
        return False
    try:
        return all(
            callable(library[name])
            for name in (
                "ibdev",
                "ibask",
                "ibconfig",
                "ibwrt",
                "ibrd",
                "ibonl",
                "ibtmo",
                "ibln",
                "ibcac",
                "ibgts",
                "ibpct",
            )
        )
    except (AttributeError, KeyError, TypeError):
        return False


def prepare_backend(backend: str | None, *, importer=None, system=None, pointer_bytes=None) -> dict:
    """Validate the explicitly chosen backend before any resource manager/session.

    ``@py`` is the optional experimental NI-488.2-only route on Windows x64.
    Normal native VISA selection is deliberately unaffected and imports no
    alternative driver. Linux can use an already installed linux-gpib C library;
    that does not establish validation of a Windows NI adapter.
    """
    selected = normalize_backend(backend)
    info = {
        "selected_backend": selected,
        "experimental": selected == "@py",
        "requires_ni_visa": selected != "@py",
        "driver_library": None,
        "hardware_verified": False,
    }
    if selected != "@py":
        return info
    importer = importer or importlib.import_module
    system = platform.system() if system is None else system
    pointer_bytes = struct.calcsize("P") if pointer_bytes is None else pointer_bytes
    if system == "Windows" and pointer_bytes != 8:
        raise NIBackendError(
            "NI_BACKEND_ARCHITECTURE_MISMATCH",
            "The NI-488.2-only trial backend requires 64-bit Python and a matching 64-bit "
            "NI-488.2 library. Use the Windows x64 trial package.",
        )
    try:
        # The upstream module emits a warning and supplies MockGPIB when a DLL is
        # missing. Convert that condition to a recorded failure, never an empty
        # resource list that looks like successful driver discovery.
        with warnings.catch_warnings(record=True):
            gpib = importer("gpib_ctypes.gpib.gpib")
    except ImportError as exc:
        raise NIBackendError(
            "NI_BACKEND_DEPENDENCY_MISSING",
            "NI-488.2-only mode requires the optional gpib-ctypes and PyVISA-py extension. "
            "Run Enable-NI-Only.cmd explicitly, restart, or choose native VISA @ivi. "
            "NI-488.2 itself is still required.",
        ) from exc
    except (OSError, AttributeError, TypeError) as exc:
        raise NIBackendError(
            "NI_BACKEND_INCOMPATIBLE",
            "The installed GPIB C library cannot initialize gpib-ctypes. Check the "
            "NI-488.2 version and 64-bit compatibility; do not copy arbitrary DLLs.",
        ) from exc
    library = getattr(gpib, "_lib", None)
    if not _usable_library(library) and system == "Windows":
        loader = getattr(gpib, "_load_lib", None)
        # These are loader candidates only, before all GPIB I/O. ni4882.dll is
        # accepted only when it supplies the exact API expected by gpib-ctypes.
        # A name containing "32" is not evidence that the DLL is 32-bit.
        if callable(loader):
            for candidate in ("ni4882.dll", "gpib-32.dll"):
                try:
                    with warnings.catch_warnings(record=True):
                        loaded = loader(candidate)
                    library = getattr(gpib, "_lib", None)
                    if loaded and _usable_library(library):
                        break
                except (OSError, AttributeError, TypeError):
                    continue
    if not _usable_library(library):
        raise NIBackendError(
            "NI_DRIVER_UNAVAILABLE",
            "NI-488.2 GPIB C library was not found or is incompatible. Install the "
            "NI-488.2 driver for this NI GPIB-USB model and Windows x64, then confirm "
            "the adapter in NI MAX and restart this application. NI-VISA is not "
            "required for this @py mode, but NI-488.2 is still required.",
        )
    try:
        # Import after driver validation. Otherwise upstream may register an
        # unavailable GPIB session when the ctypes module contains its mock.
        module = importer("pyvisa_py.gpib")
        if not getattr(module, "GPIB_CTYPES", False) or not hasattr(module, "GPIBSession"):
            raise TypeError("PyVISA-py did not initialize the gpib-ctypes session")
    except ImportError as exc:
        raise NIBackendError(
            "NI_BACKEND_DEPENDENCY_MISSING",
            "NI-488.2-only mode requires the optional PyVISA-py and gpib-ctypes extension. "
            "Run Enable-NI-Only.cmd explicitly and restart the application.",
        ) from exc
    except (OSError, AttributeError, TypeError) as exc:
        raise NIBackendError(
            "NI_BACKEND_INCOMPATIBLE",
            "PyVISA-py could not initialize the installed NI-488.2 GPIB C API. "
            "Check the matching 64-bit driver and restart; the application will "
            "not fall back to another backend automatically.",
        ) from exc
    info["driver_library"] = library._name
    info["driver_interface"] = "gpib-ctypes / NI-488.2-compatible GPIB C API"
    return info
