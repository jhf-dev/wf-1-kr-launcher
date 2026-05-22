# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

datas = []
launcher_art = Path('assets') / 'launcher_art.gif'
if launcher_art.is_file():
    datas.append((str(launcher_art), 'assets'))


a = Analysis(
    ['tooling\\wfantasy_steam_kr_patch_gui.py'],
    pathex=['tooling'],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='WF1_KR_Steam_Patch_GUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
