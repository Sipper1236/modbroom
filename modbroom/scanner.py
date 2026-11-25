"""Scan engine: walks a Mods folder, analyzes packages/scripts/saves/tray."""
import os, re, hashlib, time, zipfile
from pathlib import Path
from .dbpf import PackageReader, PackageError
from . import loadorder
from .log import get_logger

log = get_logger('scanner')

SCRIPT_EXTS = {'.ts4script'}
PACKAGE_EXTS = {'.package'}
SAVE_EXTS = {'.save', '.ver'}

def _looks_like_ip(match):
    """Reject version strings such as 7.18.178.178 that look like an IPv4."""
    parts = match.group(0).split('.')
    if len(parts) != 4:
        return False
    try:
        octets = [int(p) for p in parts]
    except ValueError:
        return False
    return all(0 <= o <= 255 for o in octets) and octets[0] >= 10


# Risky patterns in python script mods
# Each entry is (regex, label, level, optional validator).
RISKY_PATTERNS = [
    (r'\bos\.system\s*\(', 'os.system call', 'high'),
    (r'\bsubprocess\b', 'subprocess usage', 'medium'),
    (r'\b(socket|urllib|requests|http\.client)\b', 'network access', 'high'),
    (r'\bexec\s*\(|\beval\s*\(', 'exec/eval', 'high'),
    (r'\b__import__\s*\(', 'dynamic import', 'medium'),
    (r'base64\.b64decode', 'base64 decode (possible obfuscation)', 'medium'),
    (r'(discord(app)?\.com/api/webhooks|discord\.com/api/webhooks)', 'Discord webhook', 'high'),
    (r'\bctypes\b', 'ctypes (native code access)', 'high'),
    (r'\bwinreg\b|\bHKEY_', 'Windows registry access', 'high'),
    (r'\bos\.environ\b', 'environment variable access', 'low'),
    (r'\bchmod\b|\bchmod\(', 'permission change', 'low'),
    (r'\bpickle\.loads?\b', 'pickle deserialization', 'medium'),
    (r'\bshutil\.rmtree\b', 'recursive delete', 'high'),
    (r'\bopen\s*\([^)]*["\']w["\']', 'file write access', 'low'),
    (r'\b\d{1,3}(?:\.\d{1,3}){3}\b(?!\.\d)', 'IP-like address', 'low', _looks_like_ip),
]

def sha256_file(path, limit=None):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        while True:
            chunk = fh.read(1 << 16)
            if not chunk: break
            h.update(chunk)
    return h.hexdigest()

def scan_script_zip(path):
    """Inspect a .ts4script (zip of pyc/py)."""
    findings = []
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            py_files = [n for n in names if n.endswith(('.py', '.pyc'))]
            if not py_files:
                findings.append({'level': 'low', 'msg': 'No Python files inside script archive', 'detail': ', '.join(names[:5])})
            blob = b''
            for n in py_files[:40]:
                try:
                    data = zf.read(n)
                except Exception:
                    continue
                blob += data + b'\n'
            text = blob.decode('latin-1', errors='ignore')
            for pattern in RISKY_PATTERNS:
                pat, label, level = pattern[:3]
                m = re.search(pat, text, re.I)
                if not m:
                    continue
                validator = pattern[3] if len(pattern) > 3 else None
                if validator is not None and not validator(m):
                    continue
                findings.append({'level': level, 'msg': label, 'detail': m.group(0)[:120]})
    except zipfile.BadZipFile:
        findings.append({'level': 'high', 'msg': 'Corrupt script archive (not a valid zip)', 'detail': 'BadZipFile'})
    except Exception as e:
        findings.append({'level': 'medium', 'msg': 'Could not inspect script archive', 'detail': str(e)[:200]})
    return findings

def scan_tree(mods_path, saves_path=None, tray_path=None, progress=None):
    """Walk folders and collect raw file facts."""
    log.info('scan start: %s', mods_path)
    mods_path = Path(mods_path)
    result = {
        'mods_path': str(mods_path),
        'scanned_at': time.time(),
        'files': [],         # per-file dicts
        'errors': [],
        'total_bytes': 0,
    }
    if not mods_path.exists():
        log.warning('Mods folder not found: %s', mods_path)
        result['errors'].append('Mods folder not found: %s' % mods_path)
        return result

    all_files = []
    for root, dirs, files in os.walk(mods_path):
        # skip hidden / quarantine folders
        dirs[:] = [d for d in dirs if not d.startswith('.') and d.lower() not in ('modbroom_quarantine', '__pycache__')]
        for name in files:
            p = Path(root) / name
            ext = p.suffix.lower()
            if ext in PACKAGE_EXTS or ext in SCRIPT_EXTS or ext == '.py':
                all_files.append(p)

    total = len(all_files)
    for i, p in enumerate(all_files):
        if progress:
            progress(i, total, p.name)
        try:
            st = p.stat()
        except OSError as e:
            result['errors'].append('Stat failed for %s: %s' % (p, e))
            continue
        rec = {
            'path': str(p),
            'rel': str(p.relative_to(mods_path)),
            'name': p.name,
            'ext': p.suffix.lower(),
            'size': st.st_size,
            'mtime': st.st_mtime,
            'sha256': None,
            'kind': 'script' if p.suffix.lower() in SCRIPT_EXTS else 'package',
            'entries': [],
            'tgi_keys': [],
            'entry_count': 0,
            'parse_ok': True,
            'parse_error': None,
            'integrity_errors': [],
            'script_findings': [],
            'resource_types': {},
        }
        if p.suffix.lower() == '.py':
            rec['kind'] = 'python'
            rec['script_findings'] = [{'level': 'medium', 'msg': 'Loose .py file — the game never loads these', 'detail': 'Zip as .ts4script or delete'}]
            result['files'].append(rec)
            result['total_bytes'] += rec['size']
            continue
        log.debug('file %s: kind=%s size=%d', p.name, rec['kind'], rec['size'])
        try:
            if rec['kind'] == 'package':
                reader = PackageReader(p)
                rec['entry_count'] = len(reader.entries)
                rec['entries'] = [e.to_dict() for e in reader.entries]
                rec['tgi_keys'] = ['0x%08X:0x%08X:0x%016X' % e.tgi for e in reader.entries]
                rec['integrity_errors'] = reader.integrity_errors()
                type_counts = {}
                for e in reader.entries:
                    type_counts[e.type_id] = type_counts.get(e.type_id, 0) + 1
                rec['resource_types'] = {('0x%08X' % k): v for k, v in sorted(type_counts.items(), key=lambda kv: -kv[1])}
            else:
                rec['script_findings'] = scan_script_zip(p)
                rec['entry_count'] = len(rec['script_findings'])
        except PackageError as e:
            rec['parse_ok'] = False
            rec['parse_error'] = str(e)
            log.warning('cannot parse %s: %s', p.name, e)
        except Exception as e:
            rec['parse_ok'] = False
            rec['parse_error'] = 'Unexpected: %s' % e
            log.exception('unexpected error reading %s', p.name)
        for err in rec.get('integrity_errors') or []:
            log.warning('integrity: %s — %s', p.name, err)
        for finding in rec.get('script_findings') or []:
            log.debug('script risk: %s — [%s] %s', p.name, finding.get('level'), finding.get('msg'))
        result['files'].append(rec)
        result['total_bytes'] += rec['size']

    # hashes only for duplicate detection candidates (same size) to keep it fast
    by_size = {}
    for f in result['files']:
        by_size.setdefault(f['size'], []).append(f)
    for size, group in by_size.items():
        if len(group) > 1:
            for f in group:
                try:
                    f['sha256'] = sha256_file(f['path'])
                except OSError:
                    pass
    log.info('scan complete: %d files, %d bytes, %d errors',
             len(result['files']), result['total_bytes'], len(result['errors']))
    return result

def analyze(scan, mods_path=None):
    """Turn raw scan facts into findings: duplicates, conflicts, integrity, scripts, usage."""
    files = scan['files']
    # Work out load order / conflict winners. Resource.cfg lives in the Mods root.
    mods_path = mods_path or scan.get('mods_path')
    cfg, cfg_path = loadorder.ResourceCfg.load(mods_path) if mods_path else (loadorder.ResourceCfg.default(), None)
    pkg_files = [f for f in files if f.get('kind') == 'package']
    ordered, unmatched = loadorder.order_files(pkg_files, cfg, mods_path or '')
    load_index = {f['path']: f['load_index'] for f in ordered}

    findings = {
        'duplicates': [],        # byte-identical files
        'resource_dupes': [],    # same TGI set
        'conflicts': [],         # shared individual TGIs (override suspects)
        'integrity': [],         # truncated/corrupt
        'parse_errors': [],      # unreadable packages
        'script_risks': [],
        'stats': {},
    }

    # --- identical files (size+sha256) ---
    by_hash = {}
    for f in files:
        if f.get('sha256'):
            by_hash.setdefault(f['sha256'], []).append(f)
    for h, group in by_hash.items():
        if len(group) > 1:
            findings['duplicates'].append({
                'sha256': h,
                'size': group[0]['size'],
                'files': [g['path'] for g in group],
            })

    # --- resource-set duplicates & conflicts ---
    tgi_to_files = {}
    set_to_files = {}
    for f in files:
        keys = f.get('tgi_keys') or []
        if not keys:
            continue
        set_to_files.setdefault(tuple(sorted(keys)), []).append(f)
        for k in keys:
            tgi_to_files.setdefault(k, []).append(f)

    for keyset, group in set_to_files.items():
        if len(group) > 1 and len(keyset) > 0:
            findings['resource_dupes'].append({
                'resource_count': len(keyset),
                'files': [g['path'] for g in group],
            })

    for tgi, group in tgi_to_files.items():
        if len(group) > 1:
            paths = [g['path'] for g in group]
            # last to load wins the override
            ranked = sorted(paths, key=lambda p: load_index.get(p, -1))
            winner = ranked[-1]
            findings['conflicts'].append({
                'tgi': tgi,
                'files': paths,
                'file_count': len(paths),
                'load_order': ranked,
                'winner': winner,
                'losers': ranked[:-1],
            })
    # collapse conflicts by file-pair to keep the report readable
    findings['conflicts'].sort(key=lambda c: -c['file_count'])

    # --- integrity / parse errors ---
    for f in files:
        if not f['parse_ok']:
            findings['parse_errors'].append({'file': f['path'], 'error': f['parse_error']})
        for err in f.get('integrity_errors') or []:
            findings['integrity'].append({'file': f['path'], 'error': err})
        for s in f.get('script_findings') or []:
            findings['script_risks'].append({'file': f['path'], **s})

    log.info('findings: duplicates=%d resource_dupes=%d conflicts=%d integrity=%d parse=%d script_risks=%d',
             len(findings['duplicates']), len(findings['resource_dupes']), len(findings['conflicts']),
             len(findings['integrity']), len(findings['parse_errors']), len(findings['script_risks']))
    for err in findings['parse_errors']:
        log.warning('parse error: %s — %s', err['file'], err['error'])
    # --- stats ---
    total_entries = sum(f.get('entry_count', 0) for f in files)
    pkgs = sum(1 for f in files if f['kind'] == 'package')
    scripts = sum(1 for f in files if f['kind'] == 'script')
    findings['stats'] = {
        'total_files': len(files),
        'packages': pkgs,
        'scripts': scripts,
        'total_bytes': scan.get('total_bytes', 0),
        'total_resources': total_entries,
        'duplicates': len(findings['duplicates']),
        'resource_dupes': len(findings['resource_dupes']),
        'conflicts': len(findings['conflicts']),
        'integrity': len(findings['integrity']) + len(findings['parse_errors']),
        'script_risks': len(findings['script_risks']),
        'high_risks': sum(1 for s in findings['script_risks'] if s.get('level') == 'high'),
    }
    findings['load_order'] = [
        {'path': f['path'], 'rel': f['rel'], 'load_index': f['load_index'],
         'priority': f['priority'], 'resource_count': f.get('entry_count', 0)}
        for f in ordered
    ]
    findings['not_loaded'] = [f['path'] for f in unmatched]
    findings['resource_cfg'] = cfg_path
    return findings

_TGI_RE = re.compile(r'0x([0-9A-Fa-f]{8})[:_-]?0x?([0-9A-Fa-f]{8})[:_-]?0x?([0-9A-Fa-f]{16})')

def _extract_tgi_strings(blob):
    """Pull TGI-like triplets out of binary save/tray data (best-effort)."""
    out = []
    # textual TGI references
    for m in _TGI_RE.finditer(blob):
        try:
            t, g, i = int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16)
            out.append('0x%08X:0x%08X:0x%016X' % (t, g, i))
        except ValueError:
            pass
    return out

def scan_saves_and_tray(saves_path, tray_path):
    """Extract resource references from save and tray files (best-effort)."""
    evidence = {'save_refs': set(), 'tray_refs': set(), 'save_files': 0, 'tray_files': 0, 'notes': []}
    for path, key, count_key in ((saves_path, 'save_refs', 'save_files'), (tray_path, 'tray_refs', 'tray_files')):
        if not path or not Path(path).exists():
            evidence['notes'].append('Not found: %s' % path)
            continue
        for root, dirs, files in os.walk(path):
            for name in files:
                ext = Path(name).suffix.lower()
                if ext not in SAVE_EXTS and ext != '.trayitem' and ext not in PACKAGE_EXTS:
                    continue
                p = Path(root) / name
                try:
                    with open(p, 'rb') as fh:
                        blob = fh.read(64 << 20)  # cap at 64MB per file
                    text = blob.decode('latin-1', errors='ignore')
                    evidence[key].update(_extract_tgi_strings(text))
                    evidence[count_key] += 1
                except OSError:
                    continue
    evidence['save_refs'] = sorted(evidence['save_refs'])
    evidence['tray_refs'] = sorted(evidence['tray_refs'])
    return evidence

def usage_report(scan, evidence):
    """Mark files as referenced / unreferenced based on save+tray evidence."""
    ref_set = set(evidence.get('save_refs', [])) | set(evidence.get('tray_refs', []))
    used, unused, unknown = [], [], []
    for f in scan['files']:
        keys = set(f.get('tgi_keys') or [])
        if not keys:
            unknown.append(f['path'])
        elif keys & ref_set:
            used.append(f['path'])
        else:
            unused.append(f['path'])
    return {'used': used, 'unused': unused, 'unknown': unknown,
            'save_files': evidence.get('save_files', 0), 'tray_files': evidence.get('tray_files', 0),
            'notes': evidence.get('notes', [])}
