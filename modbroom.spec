# PyInstaller spec — builds a single-file app:  pyinstaller modbroom.spec
# On Windows this produces dist/ModBroom.exe; on Linux it produces dist/ModBroom.
import sys

block_cipher = None
datas = [('modbroom/assets', 'modbroom/assets'), ('modbroom/companion_src', 'modbroom/companion_src')]
icon = 'modbroom/assets/broom.ico' if sys.platform.startswith('win') else None

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=['PySide6.QtSvg'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.QtWebEngineCore',
              'PySide6.QtWebEngineWidgets', 'PySide6.QtMultimedia', 'PySide6.QtQuick'],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
    name='ModBroom',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon,
)
