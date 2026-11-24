"""Parse Sims 4 crash / exception logs and rank suspect mods."""
import re, os
from pathlib import Path

# Exception type lines like "(1234) ... Last Exception: ..." or "c0000005"
EXCEPTION_RE = re.compile(r'(?:exception|EXCEPTION|crash|CRASH|error|ERROR)[^\n]{0,300}')
STACK_MOD_RE = re.compile(r'([A-Za-z0-9_\-]+)\.(?:py|pyc)')
TS4_RE = re.compile(r'(?:ts4script|\.package)', re.I)

def find_crash_logs(logs_dir):
    logs = []
    if not logs_dir or not Path(logs_dir).exists():
        return logs
    for root, dirs, files in os.walk(logs_dir):
        for name in files:
            lower = name.lower()
            if any(k in lower for k in ('crash', 'exception', 'lastexception', 'last_exception', 'error')):
                if lower.endswith(('.txt', '.log', '.html', '.dmp', '.mdmp')):
                    logs.append(Path(root) / name)
    return sorted(logs, key=lambda p: p.stat().st_mtime, reverse=True)

def parse_crash_log(path):
    try:
        text = Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return {'path': str(path), 'error': 'unreadable', 'suspects': []}
    exceptions = EXCEPTION_RE.findall(text)[:5]
    py_refs = STACK_MOD_RE.findall(text)
    suspect_names = []
    seen = set()
    for name in py_refs:
        n = name.strip()
        if n.lower() not in seen and len(n) > 2:
            seen.add(n.lower())
            suspect_names.append(n)
    return {
        'path': str(path),
        'size': Path(path).stat().st_size,
        'mtime': Path(path).stat().st_mtime,
        'exceptions': [e.strip() for e in exceptions],
        'suspects': suspect_names[:30],
        'exception_count': len(exceptions),
    }

def rank_suspects(parsed_logs, scanned_files):
    """Cross-reference crash-log module names with scanned script files."""
    names = []
    for log in parsed_logs:
        names.extend(log.get('suspects', []))
    counts = {}
    for n in names:
        counts[n.lower()] = counts.get(n.lower(), 0) + 1
    suspects = []
    for f in scanned_files:
        if f.get('kind') != 'script':
            continue
        stem = Path(f['path']).stem.lower()
        hit = counts.get(stem, 0)
        if hit:
            suspects.append({'file': f['path'], 'hits': hit, 'match': stem})
    suspects.sort(key=lambda s: -s['hits'])
    return suspects
