# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

block_cipher = None

# Create directories in the source folder if they don't exist
os.makedirs('status', exist_ok=True)
os.makedirs('commands', exist_ok=True)

# Create empty placeholder files
Path('status/.keep').touch(exist_ok=True)  
Path('commands/.keep').touch(exist_ok=True)

# Create a temp dir for output
temp_dir = 'build_temp'
os.makedirs(temp_dir, exist_ok=True)

# Main application analysis
a = Analysis(
    ['vast_auto_shutoff_gui.py'],  # Your main script
    pathex=[],
    binaries=[],
    datas=[
        ('monitor_process.py', '.'),
        ('monitor_launcher.bat', '.'),
        ('config.ini', '.') if os.path.exists('config.ini') else (),
    ],
    hiddenimports=[
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'requests',
        'psutil',
        'configparser',
        'glob',
        'json',
        'datetime',
        'time',
        'logging',
        'argparse',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Monitor process analysis
b = Analysis(
    ['monitor_process.py'],  # Monitor process script
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'requests',
        'psutil',
        'json',
        'datetime',
        'time',
        'logging',
        'argparse',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Add directories as data files
a.datas += [('status/.keep', 'status/.keep', 'DATA')]
a.datas += [('commands/.keep', 'commands/.keep', 'DATA')]

# Create PYZ archives
pyz_a = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
pyz_b = PYZ(b.pure, b.zipped_data, cipher=block_cipher)

# Build the main application - NO CONSOLE WINDOW
exe_a = EXE(
    pyz_a,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='VastAutoShutoff',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to False to hide console window
    icon='icon.ico' if os.path.exists('icon.ico') else None,
)

# Build the monitor process - WITH CONSOLE WINDOW
exe_b = EXE(
    pyz_b,
    b.scripts,
    b.binaries,
    b.zipfiles,
    b.datas,
    [],
    name='monitor_process',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Set to True to show console window for monitoring
)

# Create a collection of both executables
COLLECT(
    exe_a,
    exe_b,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VastAutoShutoff',
) 