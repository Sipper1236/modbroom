"""Load order and conflict-winner prediction for The Sims 4.

The game reads Resource.cfg in the Mods folder to decide which .package files to
load and in what order. Each block is:

    Priority 500
    PackedFile *.package
    PackedFile */*.package

Lower priority numbers load first; higher priority loads later and wins when two
packages define the same resource. Files matching no PackedFile pattern are not
loaded at all. Within one priority block, files are processed in alphabetical
order of their full (case-insensitive) relative path, and later wins.

This module models that so ModBroom can tell the user *which* mod wins a
conflict, instead of just listing that one exists.
"""
import fnmatch
import os
from pathlib import Path

DEFAULT_PRIORITY = 500
DEFAULT_PATTERNS = ['*.package', '*/*.package', '*/*/*.package',
                    '*/*/*/*.package', '*/*/*/*/*.package', '*/*/*/*/*/*.package']


class ResourceCfg:
    """Parsed Resource.cfg: ordered list of (priority, [patterns])."""

    def __init__(self, blocks):
        self.blocks = blocks  # list of dicts: {'priority': int, 'patterns': [str]}

    @classmethod
    def parse(cls, text):
        blocks = []
        current = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith(('#', '//', ';')):
                continue
            parts = line.split(None, 1)
            key = parts[0].lower()
            rest = parts[1].strip() if len(parts) > 1 else ''
            if key == 'priority':
                if current is not None:
                    blocks.append(current)
                try:
                    prio = int(rest)
                except ValueError:
                    prio = DEFAULT_PRIORITY
                current = {'priority': prio, 'patterns': []}
            elif key == 'packedfile':
                if current is None:
                    current = {'priority': DEFAULT_PRIORITY, 'patterns': []}
                if rest:
                    # game matches against slash-separated relative paths, case-insensitively
                    current['patterns'].append(rest.replace('\\', '/').lower())
            # unknown directives are ignored, mirroring the game being lenient
        if current is not None:
            blocks.append(current)
        if not blocks:
            blocks = [{'priority': DEFAULT_PRIORITY, 'patterns': list(DEFAULT_PATTERNS)}]
        return cls(blocks)

    @classmethod
    def default(cls):
        return cls([{'priority': DEFAULT_PRIORITY, 'patterns': list(DEFAULT_PATTERNS)}])

    @classmethod
    def load(cls, mods_path):
        cfg = Path(mods_path) / 'Resource.cfg'
        if cfg.is_file():
            try:
                return cls.parse(cfg.read_text(encoding='utf-8', errors='replace')), str(cfg)
            except OSError:
                pass
        return cls.default(), None

    def blocks_of(self, rel_path):
        """All (block_index, priority) whose patterns match this relative path."""
        rel = rel_path.replace('\\', '/').lower()
        segs = rel.split('/')

        def match(pat):
            pseg = pat.split('/')
            if len(pseg) != len(segs):
                return False
            return all(fnmatch.fnmatchcase(s, p) for s, p in zip(segs, pseg))

        hits = []
        for i, block in enumerate(self.blocks):
            if any(match(pat) for pat in block['patterns']):
                hits.append((i, block['priority']))
        return hits


def order_files(files, cfg, mods_path):
    """Sort package file dicts into game load order.

    files: list of dicts with 'path' (absolute) and 'rel' (relative to mods root).
    Returns (ordered, unmatched) where ordered is a list of dicts annotated with
    load order metadata, and unmatched lists files no PackedFile pattern covers.
    """
    annotated = []
    for f in files:
        rel = (f.get('rel') or os.path.relpath(f['path'], mods_path)).replace('\\', '/')
        hits = cfg.blocks_of(rel)
        if not hits:
            continue
        # A file matched by several blocks is loaded at each matching position;
        # its effective position is the LAST one (highest priority, then latest
        # block in file order), because whatever loads last is what the game keeps.
        eff_block, eff_prio = max(hits, key=lambda h: (h[1], h[0]))
        annotated.append({**f, '_rel': rel, 'priority': eff_prio, 'block_index': eff_block})
    ordered = sorted(annotated, key=lambda f: (f['priority'], f['block_index'], f['_rel'].lower()))
    matched = {f['path'] for f in annotated}
    unmatched = [f for f in files if f['path'] not in matched]
    for i, f in enumerate(ordered):
        f['load_index'] = i
    return ordered, unmatched


def resolve_conflicts(conflicts, ordered):
    """Annotate each conflict with the winning file (last to load wins)."""
    pos = {f['path']: f.get('load_index', -1) for f in ordered}
    out = []
    for c in conflicts:
        files = c.get('files', [])
        ranked = sorted(files, key=lambda p: pos.get(p, -1))
        winner = ranked[-1] if ranked else None
        out.append({**c, 'winner': winner, 'load_order': ranked,
                    'winner_reason': 'last to load wins (highest Resource.cfg priority, then path order)'})
    return out
