# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for ECOWHISPER Command Center."""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None

project_dir = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(project_dir, 'ui'), 'ui'),
    (os.path.join(project_dir, 'voices'), 'voices'),
    (os.path.join(project_dir, 'assets'), 'assets'),
]

for cert_file in ['cert.pem', 'key.pem']:
    p = os.path.join(project_dir, cert_file)
    if os.path.isfile(p):
        datas.append((p, '.'))

datas += collect_data_files('_sounddevice_data')
datas += collect_data_files('_soundfile_data')
datas += collect_data_files('faster_whisper')
datas += collect_data_files('ctranslate2')

try:
    datas += collect_data_files('piper')
except Exception:
    pass

try:
    datas += collect_data_files('piper_phonemize')
except Exception:
    pass

try:
    datas += collect_data_files('tokenizers')
except Exception:
    pass

binaries = []
binaries += collect_dynamic_libs('ctranslate2')
binaries += collect_dynamic_libs('onnxruntime')

hiddenimports = [
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'fastapi',
    'starlette',
    'starlette.routing',
    'starlette.middleware',
    'starlette.middleware.cors',
    'starlette.staticfiles',
    'websockets',
    'wsproto',
    'comtypes',
    'comtypes.client',
    'piper',
    'piper.voice',
    'edge_tts',
    'sounddevice',
    'soundfile',
    'faster_whisper',
    'ctranslate2',
    'onnxruntime',
    'tokenizers',
    'huggingface_hub',
    'requests',
    'numpy',
    'PIL',
    'PIL.Image',
    'engineio.async_drivers.asgi',
]

hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('fastapi')
hiddenimports += collect_submodules('starlette')

a = Analysis(
    ['main.py'],
    pathex=[project_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'tkinter', 'unittest', 'pytest', 'IPython', 'notebook'],
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
    name='ECOWHISPER',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_dir, 'assets', 'icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ECOWHISPER',
)
