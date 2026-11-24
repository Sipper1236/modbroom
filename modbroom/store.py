"""Persistent state: settings, quarantine, 50/50 sessions, profiles, backups."""
import json, os, shutil, time, uuid
from pathlib import Path

APP_DIR = Path.home() / '.modbroom'
STATE_FILE = APP_DIR / 'state.json'
QUAR_DIR = APP_DIR / 'quarantine'
BACKUP_DIR = APP_DIR / 'backups'

DEFAULT_STATE = {
    'settings': {
        'mods_path': '',
        'saves_path': '',
        'tray_path': '',
        'logs_path': '',
        'game_path': '',
        'theme': 'neon',
        'include_saves': True,
        'watch': False,
    },
    'quarantine': [],   # {id, original, stored, name, reason, time}
    'profiles': [],     # {id, name, files:[rel paths disabled], created}
    'sessions_5050': [],
    'last_scan': None,
    'last_findings': None,
    'last_usage': None,
    'last_crashlogs': None,
}

def _ensure():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    QUAR_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

def load_state():
    _ensure()
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as fh:
                data = json.load(fh)
            merged = json.loads(json.dumps(DEFAULT_STATE))
            # keep every stored key, but guarantee defaults exist and settings merge
            merged.update(data)
            merged_settings = dict(DEFAULT_STATE['settings'])
            merged_settings.update(data.get('settings', {}))
            merged['settings'] = merged_settings
            return merged
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_STATE))

def save_state(state):
    _ensure()
    tmp = STATE_FILE.with_suffix('.tmp')
    with open(tmp, 'w') as fh:
        json.dump(state, fh, indent=2)
    tmp.replace(STATE_FILE)

def autodetect_paths():
    """Windows-first defaults, with Linux/macOS fallbacks for dev."""
    home = Path.home()
    candidates = {}
    # Windows
    docs = home / 'Documents'
    candidates['mods_path'] = str(docs / 'Electronic Arts' / 'The Sims 4' / 'Mods')
    candidates['saves_path'] = str(docs / 'Electronic Arts' / 'The Sims 4' / 'saves')
    candidates['tray_path'] = str(docs / 'Electronic Arts' / 'The Sims 4' / 'Tray')
    candidates['logs_path'] = str(docs / 'Electronic Arts' / 'The Sims 4' / 'logs')
    candidates['game_path'] = r'C:\Program Files (x86)\Steam\steamapps\common\The Sims 4'
    import sys
    if sys.platform.startswith('linux'):
        # Proton/Wine prefix location varies; default to the Proton common path
        proton = home / '.steam' / 'steam' / 'steamapps' / 'compatdata' / '1222670' / 'pfx' / 'drive_c' / 'users' / 'steamuser' / 'Documents' / 'Electronic Arts' / 'The Sims 4'
        ea = home / 'Documents' / 'Electronic Arts' / 'The Sims 4'
        base = proton if proton.exists() else ea
        candidates['mods_path'] = str(base / 'Mods')
        candidates['saves_path'] = str(base / 'saves')
        candidates['tray_path'] = str(base / 'Tray')
        candidates['logs_path'] = str(base / 'logs')
        candidates['game_path'] = str(home / '.steam' / 'steam' / 'steamapps' / 'common' / 'The Sims 4')
    # macOS
    elif not (home / 'Documents' / 'Electronic Arts').exists():
        candidates['game_path'] = '/Applications/The Sims 4.app'
    return candidates

def quarantine_files(state, paths, reason='manual'):
    _ensure()
    moved = []
    for p in paths:
        src = Path(p)
        if not src.exists():
            continue
        qid = uuid.uuid4().hex[:12]
        dest = QUAR_DIR / ('%s__%s' % (qid, src.name))
        shutil.move(str(src), str(dest))
        state['quarantine'].append({
            'id': qid,
            'original': str(src),
            'stored': str(dest),
            'name': src.name,
            'reason': reason,
            'time': time.time(),
            'size': dest.stat().st_size,
        })
        moved.append(src.name)
    save_state(state)
    return moved

def restore_quarantine(state, ids):
    restored, failed = [], []
    remaining = []
    for item in state['quarantine']:
        if item['id'] in ids:
            try:
                Path(item['original']).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(item['stored'], item['original'])
                restored.append(item['name'])
            except Exception:
                failed.append(item['name'])
                remaining.append(item)
        else:
            remaining.append(item)
    state['quarantine'] = remaining
    save_state(state)
    return restored, failed

def delete_quarantine(state, ids):
    deleted, remaining = [], []
    for item in state['quarantine']:
        if item['id'] in ids:
            try:
                Path(item['stored']).unlink(missing_ok=True)
                deleted.append(item['name'])
            except OSError:
                remaining.append(item)
        else:
            remaining.append(item)
    state['quarantine'] = remaining
    save_state(state)
    return deleted

def create_backup(state, mods_path, label='manual'):
    _ensure()
    mods = Path(mods_path)
    if not mods.exists():
        return None
    stamp = time.strftime('%Y%m%d-%H%M%S')
    dest = BACKUP_DIR / ('backup-%s-%s.zip' % (label, stamp))
    import zipfile
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(mods):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for name in files:
                fp = Path(root) / name
                zf.write(fp, fp.relative_to(mods))
    return str(dest)

def list_backups():
    _ensure()
    out = []
    for p in sorted(BACKUP_DIR.glob('backup-*.zip'), reverse=True):
        out.append({'name': p.name, 'path': str(p), 'size': p.stat().st_size, 'mtime': p.stat().st_mtime})
    return out

def export_manifest(scan, findings, dest):
    manifest = {
        'app': 'ModBroom', 'version': 1, 'exported_at': time.time(),
        'mods_path': scan.get('mods_path'),
        'stats': findings.get('stats'),
        'files': [{
            'rel': f['rel'], 'size': f['size'], 'kind': f['kind'],
            'parse_ok': f['parse_ok'], 'entry_count': f.get('entry_count', 0),
            'sha256': f.get('sha256'),
        } for f in scan['files']],
        'conflicts': findings.get('conflicts', [])[:500],
        'duplicates': findings.get('duplicates', []),
        'load_order': findings.get('load_order', []),
        'not_loaded': findings.get('not_loaded', []),
        'resource_cfg': findings.get('resource_cfg'),
    }
    with open(dest, 'w') as fh:
        json.dump(manifest, fh, indent=2)
    return dest

def export_html(scan, findings, dest, title='ModBroom report'):
    """Standalone HTML report (no external assets) for sharing on forums."""
    import html, datetime
    esc = html.escape
    stats = findings.get('stats', {})
    rows = []
    rows.append('<h1>%s</h1>' % esc(title))
    rows.append('<p class="meta">Generated by ModBroom on %s &middot; Mods folder: <code>%s</code></p>'
                % (esc(datetime.datetime.now().strftime('%Y-%m-%d %H:%M')), esc(str(scan.get('mods_path', '')))))
    rows.append('<h2>Summary</h2><table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>')
    for k, v in [('Files', stats.get('total_files', 0)), ('Packages', stats.get('packages', 0)),
                 ('Script mods', stats.get('scripts', 0)), ('Resources parsed', stats.get('total_resources', 0)),
                 ('Duplicates', stats.get('duplicates', 0) + stats.get('resource_dupes', 0)),
                 ('Conflicts', stats.get('conflicts', 0)), ('Broken', stats.get('integrity', 0)),
                 ('Risky scripts', stats.get('script_risks', 0)), ('High-risk scripts', stats.get('high_risks', 0))]:
        rows.append('<tr><td>%s</td><td>%s</td></tr>' % (esc(str(k)), esc(str(v))))
    rows.append('</tbody></table>')

    order = findings.get('load_order') or []
    rows.append('<h2>Load order <span class="muted">(Resource.cfg: %s)</span></h2>'
                % esc(str(findings.get('resource_cfg') or 'built-in default')))
    if order:
        rows.append('<table><thead><tr><th>#</th><th>File</th><th>Priority</th><th>Resources</th></tr></thead><tbody>')
        for f in order:
            rows.append('<tr><td>%d</td><td><code>%s</code></td><td>%d</td><td>%d</td></tr>' % (
                f['load_index'] + 1, esc(f['rel']), f['priority'], f.get('resource_count', 0)))
        rows.append('</tbody></table>')
        if findings.get('not_loaded'):
            rows.append('<p class="warn">%d package(s) match no <code>PackedFile</code> pattern and will never load:</p><ul>'
                        % len(findings['not_loaded']))
            for p in findings['not_loaded']:
                rows.append('<li><code>%s</code></li>' % esc(str(p)))
            rows.append('</ul>')
    else:
        rows.append('<p>No packages matched any PackedFile pattern.</p>')

    conflicts = findings.get('conflicts') or []
    rows.append('<h2>Conflicts (%d)</h2>' % len(conflicts))
    if conflicts:
        rows.append('<table><thead><tr><th>Resource</th><th>Winner (loads last)</th><th>Loses to it</th></tr></thead><tbody>')
        for c in conflicts[:500]:
            winner = c.get('winner') or (c.get('load_order') or ['?'])[-1]
            losers = ', '.join(c.get('losers', [])) or '—'
            rows.append('<tr><td><code>%s</code></td><td>%s</td><td>%s</td></tr>' % (
                esc(str(c.get('tgi', ''))), esc(str(winner)), esc(losers)))
        rows.append('</tbody></table>')
    else:
        rows.append('<p>None.</p>')

    dupes = findings.get('duplicates') or []
    rows.append('<h2>Byte-identical duplicates (%d)</h2>' % len(dupes))
    if dupes:
        rows.append('<ul>')
        for d in dupes:
            rows.append('<li><code>%s</code><ul>%s</ul></li>' % (
                esc(str(d.get('size', ''))) + ' bytes',
                ''.join('<li><code>%s</code></li>' % esc(f) for f in d.get('files', []))))
        rows.append('</ul>')
    else:
        rows.append('<p>None.</p>')

    broken = (findings.get('integrity') or []) + [{'file': p['file'], 'error': p.get('error', '')}
                                                  for p in findings.get('parse_errors', [])]
    rows.append('<h2>Broken / unparseable (%d)</h2>' % len(broken))
    if broken:
        rows.append('<table><thead><tr><th>File</th><th>Problem</th></tr></thead><tbody>')
        for b in broken:
            rows.append('<tr><td><code>%s</code></td><td>%s</td></tr>' % (esc(str(b.get('file', ''))), esc(str(b.get('error', '')))))
        rows.append('</tbody></table>')
    else:
        rows.append('<p>None.</p>')

    risks = findings.get('script_risks') or []
    rows.append('<h2>Script risks (%d)</h2>' % len(risks))
    if risks:
        rows.append('<table><thead><tr><th>Level</th><th>File</th><th>What</th></tr></thead><tbody>')
        for r in sorted(risks, key=lambda r: {'high': 0, 'medium': 1, 'low': 2}.get(r.get('level'), 3)):
            rows.append('<tr class="lvl-%s"><td>%s</td><td><code>%s</code></td><td>%s</td></tr>' % (
                esc(str(r.get('level', ''))), esc(str(r.get('level', ''))), esc(str(r.get('file', ''))), esc(str(r.get('msg', '')))))
        rows.append('</tbody></table>')
    else:
        rows.append('<p>None.</p>')

    rows.append('<p class="foot">ModBroom — local-only report. Not affiliated with Electronic Arts or Maxis. '
                '"Risk" flags are heuristics, not proof of malice. Generated from a read-only scan.</p>')

    doc = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>%(title)s</title>
<style>
 body{font:15px/1.5 -apple-system,'Segoe UI',Roboto,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#222}
 h1{border-bottom:3px solid #b34700;padding-bottom:.3rem} h2{margin-top:1.8rem;border-bottom:1px solid #ddd;padding-bottom:.25rem}
 table{border-collapse:collapse;width:100%%;margin:.5rem 0;font-size:13px}
 th,td{border:1px solid #ddd;padding:.35rem .5rem;text-align:left;vertical-align:top}
 th{background:#f4f4f4} tr:nth-child(even) td{background:#fafafa}
 code{background:#f2f2f2;padding:.1em .3em;border-radius:3px}
 .meta,.muted,.foot{color:#666}.foot{margin-top:2rem;border-top:1px solid #ddd;padding-top:.5rem;font-size:12px}
 .warn{color:#a33;background:#fdf0ef;border:1px solid #f0c0bb;padding:.4rem .6rem;border-radius:4px}
 .lvl-high td{background:#fdecea}.lvl-medium td{background:#fff8e6}.lvl-low td{background:#f4f8ff}
</style></head><body>
%(body)s
</body></html>""" % {'title': esc(title), 'body': '\n'.join(rows)}
    with open(dest, 'w', encoding='utf-8') as fh:
        fh.write(doc)
    return dest

def export_csv(scan, dest):
    import csv
    with open(dest, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['rel_path', 'kind', 'size_bytes', 'resources', 'parse_ok', 'sha256', 'issues'])
        for f in scan['files']:
            issues = []
            if not f['parse_ok']: issues.append('parse_error')
            issues += ['integrity'] * len(f.get('integrity_errors', []))
            issues += ['script:%s' % s.get('level') for s in f.get('script_findings', [])]
            w.writerow([f['rel'], f['kind'], f['size'], f.get('entry_count', 0),
                        f['parse_ok'], f.get('sha256') or '', ';'.join(issues)])
    return dest
