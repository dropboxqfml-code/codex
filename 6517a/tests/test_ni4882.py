"""Mock-only tests for an optional C-library backend; no NI driver or device I/O."""

import threading
from types import SimpleNamespace

import pytest

from keithley6517a.transport import visa
from keithley6517a.transport.base import CommunicationError
from keithley6517a.transport.ni4882 import NIBackendError, normalize_backend, prepare_backend


class Library:
    def __init__(self, name="C:/Windows/System32/ni4882.dll", missing=()):
        self._name = name
        self.missing = set(missing)
        self.calls = []

    def __getitem__(self, name):
        if name in self.missing:
            raise AttributeError(name)

        def function(*args):
            self.calls.append((name, args))
            raise AssertionError("Preflight must never call a bus/device function")

        return function


def imported(gpib, *, pyvisa_missing=False, incompatible=False):
    imports = []

    def importer(name):
        imports.append(name)
        if name == "gpib_ctypes.gpib.gpib":
            return gpib
        if name == "pyvisa_py.gpib":
            if pyvisa_missing:
                raise ImportError("optional package unavailable")
            return SimpleNamespace(GPIB_CTYPES=not incompatible, GPIBSession=object)
        raise AssertionError(name)

    return importer, imports


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, "@ivi"),
        ("", "@ivi"),
        (" @PY ", "@py"),
        ("@IVI", "@ivi"),
        ("C:/Vendor/visa64.dll", "C:/Vendor/visa64.dll"),
    ],
)
def test_backend_selection_is_explicit_and_keeps_library_paths(value, expected):
    assert normalize_backend(value) == expected


def test_native_visa_does_not_import_optional_bindings_or_change_backend():
    def no_import(_):
        pytest.fail("Native VISA must not load the alternative GPIB library")

    info = prepare_backend("@ivi", importer=no_import)
    assert info["selected_backend"] == "@ivi"
    assert not info["experimental"]
    assert info["requires_ni_visa"] is True


@pytest.mark.parametrize("selection", [None, "", "  "])
def test_native_default_missing_visa_never_automatically_opens_py_backend(monkeypatch, selection):
    import pyvisa

    attempted = []

    def missing_native(backend):
        attempted.append(backend)
        raise OSError("Could not locate a VISA implementation")

    monkeypatch.setattr(pyvisa, "ResourceManager", missing_native)
    transport = visa.VisaTransport("GPIB0::27::INSTR", backend=selection)
    with pytest.raises(OSError, match="VISA"):
        transport.open()
    assert attempted == ["@ivi"]
    assert transport.session is None
    assert transport.effective_timeout_ms is None
    attempted.clear()
    with pytest.raises(OSError, match="VISA"):
        visa.VisaTransport.list_resources(selection)
    assert attempted == ["@ivi"]


def test_invalid_backend_type_is_not_silently_coerced():
    with pytest.raises(ValueError):
        normalize_backend(["@py"])


def test_real_library_preflight_never_opens_a_resource_or_calls_ni_api():
    library = Library()
    importer, imports = imported(SimpleNamespace(_lib=library))
    info = prepare_backend("@py", importer=importer, system="Windows", pointer_bytes=8)
    assert imports == ["gpib_ctypes.gpib.gpib", "pyvisa_py.gpib"]
    assert library.calls == []
    assert info["driver_library"] == library._name
    assert info["experimental"]
    assert info["requires_ni_visa"] is False
    assert info["hardware_verified"] is False


def test_gpib_32_filename_is_not_interpreted_as_python_architecture():
    library = Library(name="gpib-32.dll")
    importer, _ = imported(SimpleNamespace(_lib=library))
    info = prepare_backend("@py", importer=importer, system="Windows", pointer_bytes=8)
    assert info["driver_library"] == "gpib-32.dll"


def test_32bit_windows_process_fails_before_loading_any_binding():
    def no_import(_):
        pytest.fail("Architecture mismatch must fail before library import")

    with pytest.raises(NIBackendError) as error:
        prepare_backend("@py", importer=no_import, system="Windows", pointer_bytes=4)
    assert error.value.code == "NI_BACKEND_ARCHITECTURE_MISMATCH"


def test_missing_python_binding_has_different_error_from_missing_ni_driver():
    def absent(_):
        raise ImportError("gpib_ctypes missing")

    with pytest.raises(NIBackendError) as error:
        prepare_backend("@py", importer=absent, system="Windows", pointer_bytes=8)
    assert error.value.code == "NI_BACKEND_DEPENDENCY_MISSING"


def test_upstream_mock_driver_is_not_treated_as_a_working_backend():
    class MockGPIB:
        def __getattr__(self, name):
            return lambda *a: None

    loader_calls = []
    gpib = SimpleNamespace(_lib=MockGPIB(), _load_lib=lambda n: loader_calls.append(n) or False)
    importer, imports = imported(gpib)
    with pytest.raises(NIBackendError) as error:
        prepare_backend("@py", importer=importer, system="Windows", pointer_bytes=8)
    assert error.value.code == "NI_DRIVER_UNAVAILABLE"
    assert loader_calls == ["ni4882.dll", "gpib-32.dll"]
    assert imports == ["gpib_ctypes.gpib.gpib"]
    assert "NI-VISA is not required" in str(error.value)


def test_loader_candidate_selection_happens_only_before_io():
    library = Library()
    gpib = SimpleNamespace(_lib=None)
    loads = []

    def load(name):
        loads.append(name)
        gpib._lib = library
        return True

    gpib._load_lib = load
    importer, _ = imported(gpib)
    info = prepare_backend("@py", importer=importer, system="Windows", pointer_bytes=8)
    assert loads == ["ni4882.dll"]
    assert info["driver_library"] == library._name
    assert not library.calls


def test_incompatible_library_exports_cannot_pass_preflight():
    library = Library(missing={"ibdev"})
    importer, imports = imported(SimpleNamespace(_lib=library))
    with pytest.raises(NIBackendError) as error:
        prepare_backend("@py", importer=importer, system="Linux", pointer_bytes=8)
    assert error.value.code == "NI_DRIVER_UNAVAILABLE"
    assert imports == ["gpib_ctypes.gpib.gpib"]


@pytest.mark.parametrize(
    "missing,incompatible,code",
    [(True, False, "NI_BACKEND_DEPENDENCY_MISSING"), (False, True, "NI_BACKEND_INCOMPATIBLE")],
)
def test_optional_backend_initialization_failures_are_not_empty_discovery(
    missing, incompatible, code
):
    importer, _ = imported(
        SimpleNamespace(_lib=Library()), pyvisa_missing=missing, incompatible=incompatible
    )
    with pytest.raises(NIBackendError) as error:
        prepare_backend("@py", importer=importer, system="Windows", pointer_bytes=8)
    assert error.value.code == code


class Session:
    def __init__(self, effective=3000):
        self.effective = effective
        self.requested = None
        self.closed = self.unlocked = False
        self.commands = []

    @property
    def timeout(self):
        return self.effective

    @timeout.setter
    def timeout(self, value):
        self.requested = value

    def lock_excl(self, timeout):
        self.lock_timeout = timeout

    def unlock(self):
        self.unlocked = True

    def close(self):
        self.closed = True

    def query(self, command):
        self.commands.append(command)
        return "REPLY"


class Manager:
    def __init__(self, session):
        self.session = session
        self.closed = False

    def open_resource(self, resource):
        self.resource = resource
        return self.session

    def list_resources(self):
        return ("GPIB0::27::INSTR", "ASRL1::INSTR")

    def close(self):
        self.closed = True


def fake_manager(monkeypatch, session):
    import pyvisa

    manager = Manager(session)
    selected = []

    def create(backend):
        selected.append(backend)
        return manager

    monkeypatch.setattr(pyvisa, "ResourceManager", create)
    monkeypatch.setattr(visa, "prepare_backend", lambda b: dict(selected_backend=b))
    return manager, selected


def test_selected_py_backend_records_real_rounded_timeout_and_never_falls_back(monkeypatch):
    session = Session()
    manager, backends = fake_manager(monkeypatch, session)
    transport = visa.VisaTransport("GPIB0::27::INSTR", backend="@py", timeout_ms=2000)
    transport.open()
    assert backends == ["@py"]
    assert session.requested == 2000
    assert transport.effective_timeout_ms == 3000
    assert transport.runtime_info["requested_timeout_ms"] == 2000
    assert transport.runtime_info["effective_timeout_ms"] == 3000
    assert session.commands == []
    assert transport.query("*IDN?") == "REPLY"
    assert session.commands == ["*IDN?"]
    transport.close()
    assert session.unlocked and session.closed and manager.closed


@pytest.mark.parametrize("actual", [None, 0, float("inf"), 0xFFFFFFFF])
def test_infinite_or_invalid_driver_timeout_aborts_before_scpi(monkeypatch, actual):
    session = Session(actual)
    manager, backends = fake_manager(monkeypatch, session)
    transport = visa.VisaTransport("GPIB0::27::INSTR", backend="@py")
    with pytest.raises(CommunicationError, match="finite timeout"):
        transport.open()
    assert session.closed and manager.closed
    assert session.commands == []
    assert backends == ["@py"]


def test_failed_preflight_never_constructs_a_resource_manager(monkeypatch):
    import pyvisa

    def fail(_):
        raise NIBackendError("NI_DRIVER_UNAVAILABLE", "NI-488.2 driver is required")

    monkeypatch.setattr(visa, "prepare_backend", fail)
    monkeypatch.setattr(pyvisa, "ResourceManager", lambda *a: pytest.fail("Cannot open fallback"))
    transport = visa.VisaTransport("GPIB0::27::INSTR", backend="@py")
    with pytest.raises(NIBackendError):
        transport.open()
    with pytest.raises(NIBackendError):
        visa.VisaTransport.list_resources("@py")


def test_discovery_uses_only_the_explicit_backend_and_always_closes_manager(monkeypatch):
    manager, selected = fake_manager(monkeypatch, Session())
    assert visa.VisaTransport.list_resources(" @PY ") == ("GPIB0::27::INSTR",)
    assert selected == ["@py"]
    assert manager.closed


def test_ni_only_session_keeps_single_worker_ownership(monkeypatch):
    session = Session()
    manager, _ = fake_manager(monkeypatch, session)
    transport = visa.VisaTransport("GPIB0::27::INSTR", backend="@py")
    transport.open()
    errors = []

    def wrong_thread():
        try:
            transport.query("*IDN?")
        except CommunicationError as exc:
            errors.append(exc)

    worker = threading.Thread(target=wrong_thread)
    worker.start()
    worker.join()
    assert len(errors) == 1
    assert session.commands == []
    transport.close()
    assert manager.closed


def test_backend_without_resource_lock_reports_capability_instead_of_claiming_lock(monkeypatch):
    import pyvisa

    session = Session()
    manager, selected = fake_manager(monkeypatch, session)

    def unsupported(timeout):
        raise pyvisa.errors.VisaIOError(pyvisa.constants.StatusCode.error_nonsupported_operation)

    session.lock_excl = unsupported
    transport = visa.VisaTransport("GPIB0::27::INSTR", backend="@py")
    transport.open()
    assert transport.runtime_info["exclusive_lock_supported"] is False
    assert transport.runtime_info["exclusive_lock_acquired"] is False
    assert selected == ["@py"]
    transport.close()
    assert session.closed and manager.closed and not session.unlocked


def test_busy_resource_lock_does_not_become_unlocked_connection_or_backend_fallback(monkeypatch):
    import pyvisa

    session = Session()
    manager, selected = fake_manager(monkeypatch, session)

    def busy(timeout):
        raise pyvisa.errors.VisaIOError(pyvisa.constants.StatusCode.error_resource_locked)

    session.lock_excl = busy
    transport = visa.VisaTransport("GPIB0::27::INSTR", backend="@py")
    with pytest.raises(pyvisa.errors.VisaIOError):
        transport.open()
    assert selected == ["@py"]
    assert session.closed and manager.closed
    assert session.commands == []
