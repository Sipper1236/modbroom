"""Package the in-game companion mod and write the desktop->game partner file."""
import json
import os
import time
import zipfile
from pathlib import Path

PACKAGE = 'modbroom_bridge'
NAME = 'ModBroomBridge.ts4script'

def _companion_dir():
    import sys
    base = getattr(sys, '_MEIPASS', None)  # PyInstaller onefile
    if base:
        cand = Path(base) / 'modbroom' / 'companion_src' / PACKAGE
        if cand.is_dir():
            return cand
    return Path(__file__).resolve().parent / 'companion_src' / PACKAGE

SRC = _companion_dir()


def build_ts4script(dest_dir=None):
    """Zip the companion package into a .ts4script. The game loads .ts4script as a zip of .py."""
    init = SRC / '__init__.py'
    if not init.exists():
        raise FileNotFoundError('missing companion source: %s' % init)
    dest_dir = Path(dest_dir) if dest_dir else Path.home() / '.modbroom'
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / NAME
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(init, '%s/__init__.py' % PACKAGE)
    return str(dest)


def write_partner(state):
    """Write ~/.modbroom/partner.json for the in-game companion to read."""
    from . import store
    ls = state.get('last_scan') or {}
    f = state.get('last_findings') or {}
    usage = state.get('last_usage') or {}
    stats = f.get('stats') or {}
    payload = {
        'schema': 1,
        'written_at': time.time(),
        'generated_by': 'ModBroom desktop',
        'files': stats.get('total_files', len(ls.get('files', []))),
        'packages': stats.get('packages', 0),
        'scripts': stats.get('scripts', 0),
        'duplicates': stats.get('duplicates', 0),
        'conflicts': stats.get('conflicts', 0),
        'broken': stats.get('integrity', 0),
        'high_risks': stats.get('high_risks', 0),
        'unused': len(usage.get('unused') or []) if isinstance(usage, dict) else None,
    }
    payload['issues'] = (payload['duplicates'] + payload['conflicts']
                         + payload['broken'] + payload['high_risks'])
    store._ensure()
    tmp = store.APP_DIR / 'partner.json.tmp'
    with open(tmp, 'w') as fh:
        json.dump(payload, fh, indent=2)
    tmp.replace(store.APP_DIR / 'partner.json')
    return str(store.APP_DIR / 'partner.json')


def install(state, mods_path=None):
    """Build the ts4script AND drop partner.json. Returns (ts4script_path, partner_path, dest)."""
    mods_path = mods_path or (state.get('settings') or {}).get('mods_path') or ''
    built = build_ts4script()
    dest = None
    if mods_path and os.path.isdir(mods_path):
        target = Path(mods_path) / NAME
        with zipfile.ZipFile(built) as zin, zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                zout.writestr(name, zin.read(name))
        dest = str(target)
    partner = write_partner(state)
    return built, partner, dest
