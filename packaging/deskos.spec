# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DeskOS.

Build from the repository root:

    python scripts/build.py

or directly:

    pyinstaller --noconfirm --clean packaging/deskos.spec

Produces a one-folder application in ``dist/DeskOS`` with the resources that
``deskos.core.paths.resource_root()`` expects (``assets/`` and ``plugins/`` next
to the executable/inside ``_internal``).
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - injected by PyInstaller

block_cipher = None

datas = [
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "plugins"), "plugins"),
]

hiddenimports = [
    "shiboken6",
    "keyring.backends.Windows",
    "keyring.backends.SecretService",
    "keyring.backends.libsecret",
    "keyring.backends.chainer",
]

a = Analysis(
    [str(ROOT / "packaging" / "deskos_launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "_pytest", "PySide6.QtWebEngineCore"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DeskOS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "images" / "deskos.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DeskOS",
)
