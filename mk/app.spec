# mk/app.spec

# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None
spec_dir = SPECPATH
# spec_dir is mk/, root is one level up
root_dir = os.path.abspath(os.path.join(spec_dir, '..'))
src_path = os.path.join(root_dir, 'src')

main_script = os.path.join(src_path, 'main.py')
icon_path = os.path.join(spec_dir, 'icon.ico')

a = Analysis(
    [main_script],
    pathex=[src_path],
    binaries=[],
    datas=[
        (os.path.join(src_path, 'conf'), 'conf'),
        (icon_path, 'mk')  # Put icon into mk/ folder inside the bundle so get_resource_path finds it
    ],
    hiddenimports=['gflzirc'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
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
    name='GFLH',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, 
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GFLH',
    contents_directory='_internal'
)