# -*- mode: python ; coding: utf-8 -*-
# GFLH-SlowShockMap 的 PyInstaller 配置。
# 只负责把 Python 侧打进去；gflmaps/ 与 GFLData/ 由 build_map.py 构建后拷到 exe 旁边。

import os

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

spec_dir = SPECPATH
root_dir = os.path.abspath(os.path.join(spec_dir, '..'))
main_script = os.path.join(root_dir, 'map.py')

a = Analysis(
    [main_script],
    pathex=[root_dir],
    binaries=[],
    # pythonnet 的 runtime/*.deps.json 必须一起带上，否则 frozen 下 CLR 起不来
    datas=collect_data_files('pythonnet'),
    hiddenimports=[
        'gflzirc',
        'webview',
        'webview.platforms.edgechromium',
        'clr',
        'clr_loader',
        'pythonnet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GFLH-SlowShockMap',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='GFLH-SlowShockMap',
    contents_directory='_internal',
)
