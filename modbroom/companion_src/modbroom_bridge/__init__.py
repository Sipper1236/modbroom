"""
ModBroom Bridge — in-game companion for the ModBroom desktop app.

Install: copy the packaged ModBroomBridge.ts4script into Documents\\Electronic Arts
\\The Sims 4\\Mods (the root of the Mods folder, not a subfolder), then restart the game
and make sure "Script Mods Allowed" is ticked in Game Options > Other.

What it does (and what it does NOT do):
  - Registers four cheat commands. That is all.
  - It never writes, moves or deletes anything. It only reads the Mods folder and
    the optional ~/.modbroom/partner.json file written by the ModBroom desktop app.
  - It does not phone home. There is no networking in this file.

Commands (type into the cheat console, Ctrl+Shift+C):
  mb_help     show this help
  mb_status   summary of the last ModBroom scan (link state, issues)
  mb_stats    live count of .package / .ts4script files in Mods
  mb_find X   find files whose name contains X; warns about script mods the
              game silently IGNORES because they sit too deep
"""

import os
import json
import time

import sims4.commands


def _home():
    try:
        return os.path.expanduser('~')
    except Exception:
        return os.getcwd()


def _partner_path():
    return os.path.join(_home(), '.modbroom', 'partner.json')


def _mods_root():
    home = _home()
    candidates = [
        os.path.join(home, 'Documents', 'Electronic Arts', 'The Sims 4', 'Mods'),
    ]
    onedrive = os.environ.get('OneDrive') if 'os' in globals() else None
    if onedrive:
        candidates.insert(0, os.path.join(onedrive, 'Documents', 'Electronic Arts', 'The Sims 4', 'Mods'))
    candidates.append(os.path.join(home, 'OneDrive', 'Documents', 'Electronic Arts', 'The Sims 4', 'Mods'))
    for path in candidates:
        if path and os.path.isdir(path):
            return path
    return candidates[0]


def _walk_mods():
    root = _mods_root()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for name in filenames:
            yield os.path.join(dirpath, name), name, root


def _age_str(ts):
    try:
        secs = int(time.time() - float(ts))
    except Exception:
        return 'unknown age'
    if secs < 90:
        return '%ds ago' % secs
    if secs < 5400:
        return '%d minutes ago' % (secs // 60)
    if secs < 172800:
        return '%d hours ago' % (secs // 3600)
    return '%d days ago' % (secs // 86400)


@sims4.commands.Command('mb_help', command_type=sims4.commands.CommandType.Live)
def _mb_help(_connection=None):
    out = sims4.commands.CheatOutput(_connection)
    out('ModBroom Bridge commands:')
    out('  mb_status  - last desktop scan summary (link state, issue counts)')
    out('  mb_stats   - live count of packages/scripts in your Mods folder')
    out('  mb_find X  - find files containing X (warns about ignored nested scripts)')
    out('  mb_help    - this list')


@sims4.commands.Command('mb_status', command_type=sims4.commands.CommandType.Live)
def _mb_status(_connection=None):
    out = sims4.commands.CheatOutput(_connection)
    data = None
    try:
        with open(_partner_path(), 'r') as handle:
            data = json.load(handle)
    except FileNotFoundError:
        out('ModBroom: no scan data yet. Open ModBroom on your desktop and run a scan.')
        return
    except Exception as exc:
        out('ModBroom: partner.json unreadable (%s). Re-run a scan in ModBroom.' % exc)
        return
    if not isinstance(data, dict):
        out('ModBroom: partner.json has unexpected format. Re-run a scan in ModBroom.')
        return
    out('ModBroom scan from %s:' % _age_str(data.get('written_at', 0)))
    out('  %(files)s files (%(packages)s packages, %(scripts)s scripts)' % data)
    out('  duplicates: %(duplicates)s | conflicts: %(conflicts)s | broken: %(broken)s | risky scripts: %(high_risks)s' % data)
    unused = data.get('unused')
    if unused is not None:
        out('  unused files (heuristic): %s' % unused)
    issues = int(data.get('issues', 0) or 0)
    if issues:
        out('  => %d issue(s) need attention. Open ModBroom for details.' % issues)
    else:
        out('  => all clear.')


@sims4.commands.Command('mb_stats', command_type=sims4.commands.CommandType.Live)
def _mb_stats(_connection=None):
    out = sims4.commands.CheatOutput(_connection)
    root = _mods_root()
    if not os.path.isdir(root):
        out('ModBroom: Mods folder not found at %s' % root)
        return
    packages = scripts = other = 0
    deep_scripts = 0
    total_bytes = 0
    for full, name, root_path in _walk_mods():
        ext = os.path.splitext(name)[1].lower()
        try:
            total_bytes += os.path.getsize(full)
        except OSError:
            pass
        if ext == '.package':
            packages += 1
        elif ext == '.ts4script':
            scripts += 1
            rel = os.path.relpath(full, root_path)
            depth = len(rel.replace('\\', '/').split('/')) - 1
            if depth > 1:
                deep_scripts += 1
        else:
            other += 1
    out('Mods folder: %s' % root)
    out('  %d .package, %d .ts4script, %d other file(s), %.1f MB total' % (
        packages, scripts, other, total_bytes / (1024.0 * 1024.0)))
    if deep_scripts:
        out('  WARNING: %d script mod(s) sit more than one folder deep and are IGNORED by the game.' % deep_scripts)
        out('  Move them into Mods\\ or one subfolder deep, or they will never load.')


@sims4.commands.Command('mb_find', command_type=sims4.commands.CommandType.Live)
def _mb_find(query=None, _connection=None):
    out = sims4.commands.CheatOutput(_connection)
    if not query:
        out('Usage: mb_find <part of a filename>')
        return
    needle = str(query).lower()
    root = _mods_root()
    hits = 0
    for full, name, root_path in _walk_mods():
        if needle in name.lower():
            hits += 1
            if hits <= 15:
                rel = os.path.relpath(full, root_path)
                note = ''
                if name.lower().endswith('.ts4script'):
                    depth = len(rel.replace('\\', '/').split('/')) - 1
                    if depth > 1:
                        note = '  [IGNORED BY GAME: too deep]'
                out('  %s%s' % (rel, note))
    if hits == 0:
        out('No files matching "%s" under %s' % (query, root))
    elif hits > 15:
        out('...and %d more. Narrow the search.' % (hits - 15))
