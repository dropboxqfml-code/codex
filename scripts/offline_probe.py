"""Linux native-socket denial + local GUI functional probe; never uses user pictures."""

import ctypes
import errno
import json
import os
import sys
import traceback
from pathlib import Path


def deny_internet_sockets() -> None:
    if sys.platform != "linux":
        raise RuntimeError("This kernel-level offline probe requires Linux/libseccomp")
    lib = ctypes.CDLL("libseccomp.so.2", use_errno=True)

    class Comparison(ctypes.Structure):
        _fields_ = [
            ("arg", ctypes.c_uint),
            ("op", ctypes.c_int),
            ("datum_a", ctypes.c_uint64),
            ("datum_b", ctypes.c_uint64),
        ]

    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_rule_add_array.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.POINTER(Comparison),
    ]
    lib.seccomp_attr_set.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    context = lib.seccomp_init(0x7FFF0000)  # SCMP_ACT_ALLOW
    if not context:
        raise RuntimeError("seccomp_init failed")
    try:
        number = lib.seccomp_syscall_resolve_name(b"socket")
        if number < 0:
            raise RuntimeError("socket syscall unavailable")
        for family in (2, 10):
            comparison = Comparison(0, 4, family, 0)  # SCMP_CMP_EQ
            result = lib.seccomp_rule_add_array(
                context, 0x00050000 | errno.EPERM, number, 1, ctypes.byref(comparison)
            )
            if result != 0:
                raise RuntimeError(f"seccomp rule failed: {result}")
        if lib.seccomp_attr_set(context, 4, 1) != 0 or lib.seccomp_load(context) != 0:
            raise RuntimeError("Unable to install synchronized seccomp filter")
    finally:
        lib.seccomp_release(context)
    libc = ctypes.CDLL(None, use_errno=True)
    for family in (2, 10):
        descriptor = libc.socket(family, 1, 0)
        if descriptor != -1 or ctypes.get_errno() != errno.EPERM:
            raise RuntimeError("Native socket control did not fail with EPERM")


def main() -> int:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "reports/offline-probe.json").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"platform": sys.platform, "kernel_socket_denial": False, "status": "failed"}
    try:
        deny_internet_sockets()
        report["kernel_socket_denial"] = True
        from image_duplicate_finder.privacy import install_runtime_guard, runtime_blocks

        install_runtime_guard()
        # Isolate the disposable Linux trash from the developer's profile (which may be read-only).
        os.environ["XDG_DATA_HOME"] = str(output.parent / "offline-xdg-data")
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging"))
        from frozen_smoke import run

        functional = output.with_name("offline-functional.json")
        functional.unlink(missing_ok=True)
        functional.with_suffix(".png").unlink(missing_ok=True)
        exit_code = run(functional)
        report["functional"] = json.loads(functional.read_text(encoding="utf-8"))
        report["python_blocked_attempts"] = runtime_blocks()
        if exit_code != 0 or any(report["python_blocked_attempts"].values()):
            raise RuntimeError("Offline operation failed or attempted a forbidden Python operation")
        report["status"] = "passed"
    except Exception:
        report["error"] = traceback.format_exc()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
