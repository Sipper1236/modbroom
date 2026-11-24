"""Real Sims 4 loading rules.

The Sims 4 is picky about *where* and *how* mod files sit, and it fails
silently. This module flags exactly those situations so "the game ignores my mod"
stops being a mystery.

Rules implemented (documented community/EA behavior):
  1. .ts4script must be in Mods\\ or exactly one subfolder deep. Deeper => ignored.
  2. Loose .py files in Mods are never loaded; they must be zipped as .ts4script.
  3. Paths longer than 259 chars are not loaded on Windows.
  4. Dotfiles and names ending in a space or dot are skipped/renamed by Windows.
  5. Empty (zero-byte) .package / .ts4script are skipped.
  6. Non-mod files are ignored by the game entirely (reported as info, not error).
  7. Documents redirected to OneDrive breaks mod loading and save integrity.
"""
import os
from pathlib import PureWindowsPath

MAX_PATH = 259

def _depth_under_mods(mods_root, full_path):
    try:
        rel = os.path.relpath(full_path, mods_root)
    except ValueError:
        return None
    return len(PureWindowsPath(rel).parts)


def analyze(scan):
    """Return list of findings: {rule, level, file, detail}."""
    mods = scan.get('mods_path') or ''
    findings = []

    # OneDrive / redirected Documents detection
    lowered = mods.lower()
    if 'onedrive' in lowered:
        findings.append({
            'rule': 'onedrive_documents', 'level': 'high', 'file': mods,
            'detail': 'Your Mods folder lives inside OneDrive. The game can read stale synced copies and lose files. Move Documents (or at least The Sims 4 folder) out of OneDrive.',
        })

    for f in scan.get('files', []):
        path = f['path']
        name = f['name']
        rel = f.get('rel', name)
        ext = f.get('ext', '')

        # 3. path length
        if len(path) > MAX_PATH:
            findings.append({'rule': 'path_too_long', 'level': 'high', 'file': path,
                             'detail': 'Path is %d characters (max ~259 on Windows). The game will not load this file.' % len(path)})

        # 4. dotfiles / trailing space or dot
        parts = PureWindowsPath(name).parts if '\\' in name else rel.replace('\\', '/').split('/')
        if any(p.startswith('.') for p in parts):
            findings.append({'rule': 'dotfile', 'level': 'low', 'file': path,
                             'detail': 'Hidden/dotfile — the game skips it.'})
        if name != name.rstrip(' .'):
            findings.append({'rule': 'trailing_dot_space', 'level': 'medium', 'file': path,
                             'detail': 'Name ends with a space or dot; Windows strips it and the game may not match the file.'})

        # 5. zero-byte
        if f.get('size', 1) == 0:
            findings.append({'rule': 'empty_file', 'level': 'medium', 'file': path,
                             'detail': 'Zero bytes — the game silently skips empty files.'})

        # 1. script nesting depth
        if ext == '.ts4script':
            depth = _depth_under_mods(mods, path)
            if depth is not None and depth > 2:
                findings.append({'rule': 'script_too_deep', 'level': 'high', 'file': path,
                                 'detail': 'Script mod is %d folders deep (%s). The Sims 4 only loads .ts4script files from Mods\\ or one subfolder deep — this one is ignored. Move it up.' % (depth - 1, rel)})

        # 2. loose .py is not loadable (only if it slipped into the scan)
        if ext == '.py':
            findings.append({'rule': 'loose_python', 'level': 'medium', 'file': path,
                             'detail': 'Loose .py files are never loaded by the game. Zip it as .ts4script (or delete it).'})

    # Non-mod files the game ignores (informational)
    ignored = 0
    try:
        for root, dirs, files in os.walk(mods):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for n in files:
                e = os.path.splitext(n)[1].lower()
                if e not in ('.package', '.ts4script'):
                    ignored += 1
    except OSError:
        pass
    if ignored:
        findings.append({'rule': 'ignored_files', 'level': 'info', 'file': mods,
                         'detail': '%d file(s) with extensions the game does not load (.txt, .png, .rar, …). They are ignored — fine to keep, but they are not mods.' % ignored})

    return findings


PREFLIGHT_CHECKLIST = [
    'The Sims 4 → Game Options → Other → tick "Enable Custom Content and Mods"',
    'Tick "Script Mods Allowed" if you use any .ts4script — then fully restart the game',
    'After every Sims 4 patch, re-tick those boxes; the game disables mods on update',
    'First launch after installing mods: check for the "outdated mods" prompt and clear it',
    'Mods must be in Documents\\Electronic Arts\\The Sims 4\\Mods (not a shortcut)',
    'Zip/rar archives must be extracted — the game never reads .zip/.rar inside Mods',
    'After adding/removing script mods, fully quit the game to the desktop before relaunching',
]
