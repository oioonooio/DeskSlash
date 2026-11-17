# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build for Desktop Slash (single-file windowed EXE).

    python -m PyInstaller --noconfirm --clean DesktopSlash.spec

The self-test inside the EXE verifies assets, fonts, audio, pywin32,
desktop icon reading, the overlay render path and pause input handover:

    dist\\DesktopSlash.exe --self-test
"""

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = [
    "pythoncom",
    "pywintypes",
    "win32com",
    "win32com.client",
    "win32timezone",
]
hiddenimports += collect_submodules("win32com.client")

datas = [
    ("assets", "assets"),
    ("localization/translations", "localization/translations"),
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "numpy", "matplotlib"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DesktopSlash",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
    version="version_info.txt",
)
