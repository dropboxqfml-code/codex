# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
import json

from PyInstaller.utils.hooks import copy_metadata

if sys.platform != "win32":
    raise SystemExit("Build this spec on Windows x64, not on Linux/macOS.")

root = Path(SPECPATH).parent
datas = [(str(root / "packaging" / "READ_ME_FIRST.txt"), ".")]
# Include distribution metadata and upstream license files when supplied by the wheel.
for distribution in (
    "PySide6_Essentials", "shiboken6",
    "Pillow", "ImageHash", "numpy", "scipy", "PyWavelets", "Send2Trash", "pywin32",
):
    datas += copy_metadata(distribution)

analysis = Analysis(
    [str(root / "packaging" / "windows_launcher.py")],
    pathex=[str(root / "src"), str(root / "packaging")],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PIL.BmpImagePlugin", "PIL.GifImagePlugin", "PIL.JpegImagePlugin",
        "PIL.PngImagePlugin", "PIL.TiffImagePlugin", "PIL.WebPImagePlugin",
        "scipy.fftpack", "pywt", "sqlite3", "send2trash.win.modern",
        "pythoncom", "pywintypes", "win32com.shell.shell", "win32com.shell.shellcon",
        "win32com.client.dynamic",
    ],
    hookspath=[str(root / "packaging" / "hooks")],
    runtime_hooks=[],
    excludes=[
        "PyQt5", "PyQt6", "PySide2", "tkinter", "matplotlib", "pytest", "IPython",
        "requests", "httpx", "httpcore", "urllib3", "aiohttp", "websockets",
        "urllib.request", "http.client", "ftplib", "smtplib", "webbrowser",
        "pip", "pip_audit", "scipy.datasets",
        "PIL.EpsImagePlugin", "PIL.PdfImagePlugin", "PIL.WmfImagePlugin", "PIL.ImageShow",
        "PIL.ImageGrab",
        "PySide6.QtNetwork", "PySide6.QtNetworkAuth", "PySide6.QtWebSockets",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtRemoteObjects",
    ],
    noarchive=False,
)
inventory = {
    "python_modules": sorted(row[0] for row in analysis.pure),
    "native_files": sorted(row[0] for row in analysis.binaries),
}
(root / "reports").mkdir(exist_ok=True)
(root / "reports" / "bundle-inventory.json").write_text(
    json.dumps(inventory, indent=2), encoding="utf-8"
)
for name in inventory["native_files"]:
    lower = name.lower().replace("\\", "/")
    if any(token in lower for token in (
        "qt6network", "qt6webengine", "qtwebengineprocess", "/tls/", "/networkinformation/",
    )):
        raise SystemExit("Unexpected network-capable Qt binary in bundle: " + name)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Image Duplicate Finder",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    uac_admin=False,
    version=str(root / "packaging" / "windows-version.txt"),
)
collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="Image Duplicate Finder",
)
