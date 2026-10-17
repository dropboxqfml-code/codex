# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

from PyInstaller.utils.hooks import copy_metadata

if sys.platform != "win32":
    raise SystemExit("Build this spec on Windows x64, not on Linux/macOS.")

root = Path(SPECPATH).parent
datas = [(str(root / "packaging" / "READ_ME_FIRST.txt"), ".")]
# Include distribution metadata and upstream license files when supplied by the wheel.
for distribution in (
    "PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6",
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
    hookspath=[],
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "tkinter", "matplotlib", "pytest", "IPython"],
    noarchive=False,
)
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
