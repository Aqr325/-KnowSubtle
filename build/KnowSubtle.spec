# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['local_metagpt.stub', 'learning_agent_system.orchestrator', 'learning_agent_system.schema', 'sqlalchemy', 'sqlalchemy.dialects.sqlite.aiosqlite', 'aiosqlite', 'webview', 'bottle', 'PyQt6', 'PyQt6.sip', 'PyQt6.QtCore', 'PyQt6.QtWidgets', 'PyQt6.QtGui', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebEngineCore', 'PyQt6.QtWebChannel', 'PyQt6.QtNetwork', 'PyQt6.QtPrintSupport', 'httpx', 'yaml', 'rich']
hiddenimports += collect_submodules('learning_agent_system')
hiddenimports += collect_submodules('webview')


a = Analysis(
    ['D:\\workbuddy workspace\\2026-06-26-10-37-12\\learning-agent-system\\launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('D:\\workbuddy workspace\\2026-06-26-10-37-12\\learning-agent-system\\local_metagpt', 'local_metagpt')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['metagpt'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KnowSubtle',
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
    icon=['D:\\workbuddy workspace\\2026-06-26-10-37-12\\learning-agent-system\\Release-Package\\Install\\程序图标.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='KnowSubtle',
)
