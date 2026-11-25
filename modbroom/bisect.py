"""50/50 bisect: binary-search the mod that breaks your game.

The game cannot tell us which file is bad, so we split the suspects in half,
move one half out of the Mods folder, and ask the user what happened. Each
answer halves the pool. Everything is reversible: moved files are stored in
~/.modbroom/bisect/<session>/ mirroring their relative layout, and any
unfinished session can be rolled back wholesale.
"""
import os
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import store
from .log import get_logger

log = get_logger('bisect')

BISECT_DIR = store.APP_DIR / 'bisect'


class BisectError(Exception):
    pass


def _load(state):
    sessions = state.get('bisect') or {}
    if not isinstance(sessions, dict):
        sessions = {}
    return sessions


def _save(state, sessions):
    state['bisect'] = sessions
    store.save_state(state)


def _session_dir(sid):
    return BISECT_DIR / sid


def _stash_path(session, rel):
    return _session_dir(session['id']) / 'stash' / rel


def _apply(session, desired, progress=None):
    """Move files so reality matches `desired` ({relpath: 'in'|'out'}).

    Moves are independent, so they run in a small thread pool. On a large
    library this is the difference between a visible pause and a quick step.
    """
    mods = Path(session['mods_root'])
    jobs = [(rel, where, mods / rel, _stash_path(session, rel))
            for rel, where in desired.items()]
    if not jobs:
        return []

    def move_one(job):
        rel, where, target_in, target_out = job
        try:
            if where == 'out':
                if not target_in.exists():
                    return None
                if target_out.exists():
                    target_out.unlink()
                target_out.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target_in), str(target_out))
                return ('out', rel)
            if target_out.exists():
                target_in.parent.mkdir(parents=True, exist_ok=True)
                if target_in.exists():
                    conflict = target_in.with_name(target_in.name + '.modbroom-conflict')
                    shutil.move(str(target_in), str(conflict))
                shutil.move(str(target_out), str(target_in))
                return ('in', rel)
        except OSError as exc:
            raise BisectError('Could not move %s: %s' % (rel, exc))
        return None

    workers = min(8, max(2, (os.cpu_count() or 2) * 2))
    moved = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for done, result in enumerate(pool.map(move_one, jobs), 1):
            if result:
                moved.append(result)
            if progress and (done % 10 == 0 or done == len(jobs)):
                progress('Moved %d/%d file(s)' % (done, len(jobs)))
    return moved


def active_sessions(state):
    return [s for s in _load(state).values() if s.get('status') == 'active']


def risk_scores(state):
    """Score suspect paths from the last scan.

    Higher score = more likely to be the culprit. Used to make the *first*
    split informed instead of alphabetical: the highest-risk group is moved
    out, so a "problem gone" answer immediately narrows to a small pool.
    """
    scores = {}

    def bump(paths, amount):
        for p in paths or []:
            if p:
                scores[p] = scores.get(p, 0) + amount

    f = state.get('last_findings') or {}
    bump([i.get('file') for i in f.get('integrity', [])], 8)
    bump([i.get('file') for i in f.get('parse_errors', [])], 8)
    bump([i.get('file') for i in f.get('script_risks', []) if i.get('level') == 'high'], 4)
    bump([i.get('file') for i in f.get('script_risks', []) if i.get('level') == 'medium'], 2)
    for d in f.get('duplicates', []):
        bump((d.get('files') or [])[1:], 1)
    for d in f.get('resource_dupes', []):
        bump((d.get('files') or [])[1:], 1)
    for c in f.get('conflicts', []):
        bump(c.get('files', []), 1)
    crash = state.get('last_crashlogs') or {}
    bump([s.get('file') for s in crash.get('suspects', [])], 10)
    return scores


def _ordered_groups(pool, scores):
    """Group files by folder so a mod and its companion files stay together."""
    groups = {}
    for rel in pool:
        parent = str(Path(rel).parent).replace('\\', '/').lower() or '.'
        groups.setdefault(parent, []).append(rel)
    ranked = sorted(
        groups.items(),
        key=lambda kv: (-max(scores.get(r, 0) for r in kv[1]), kv[0]),
    )
    return [(key, sorted(rs, key=lambda r: (-scores.get(r, 0), r.lower())))
            for key, rs in ranked]


def _split_candidates(groups, weights, total_count):
    """Candidate partitions of whole folder groups.

    Scores are capped so one noisy heuristic cannot dominate a test. Each
    candidate is scored by the expected number of files left after the answer
    (size_a * p_a + size_b * p_b), with a small penalty for lopsided counts.
    """
    n = len(groups)
    sizes = [len(rels) for _k, rels in groups]
    masses = [sum(weights[r] for r in rels) for _k, rels in groups]
    total_mass = sum(masses)
    order = sorted(range(n), key=lambda i: (-masses[i], groups[i][0]))
    candidates = []

    def consider(indices):
        a = set(indices)
        if not a or len(a) == n:
            return
        mass_a = sum(masses[i] for i in a)
        mass_b = total_mass - mass_a
        count_a = sum(sizes[i] for i in a)
        count_b = total_count - count_a
        cost = (count_a * mass_a + count_b * mass_b) / total_mass
        cost += 0.02 * abs(count_a - count_b)   # discourage silly 1-vs-N splits
        candidates.append((cost, a))

    # ~50/50 by file count
    a, b = [], []
    for i in order:
        (a if len(a) <= len(b) else b).append(i)
    consider(a)

    # ~50/50 by probability (largest masses first, greedily balanced)
    a, b, ma, mb = [], [], 0.0, 0.0
    for i in order:
        if ma <= mb:
            a.append(i); ma += masses[i]
        else:
            b.append(i); mb += masses[i]
    consider(a)

    # Isolate the k most suspicious groups: a strong hint can end the search
    # in one game launch instead of forcing a full binary search.
    for k in range(1, min(4, n)):
        consider(order[:k])
    return candidates


def plan(pool, scores=None, risk_first=None):
    """Split a suspect pool into (enabled, disabled) in as few tests as possible.

    With no scores this is a plain 50/50 split. With scores it compares a
    probability-balanced split, a count-balanced split and "isolate the k
    riskiest" splits, then keeps the one that minimises the expected number
    of files left. Folder groups stay intact when a mod has companion files.

    The higher-risk half is moved *out*, so a "problem gone" answer confirms
    the smallest possible pool immediately.
    """
    pool = list(pool)
    if len(pool) <= 1:
        return pool, []
    scores = scores or {}
    order = lambda rels: sorted(rels, key=lambda r: (-scores.get(r, 0), r.lower()))

    if not scores:
        ordered = order(pool)
        half = (len(ordered) + 1) // 2
        return ordered[:half], ordered[half:]

    weights = {r: 1.0 + min(10.0, float(max(0.0, scores.get(r, 0)))) for r in pool}
    groups = _ordered_groups(pool, scores)
    if len(groups) < 2:
        # Everything lives in one folder — treat each file as its own group.
        groups = [(r, [r]) for r in order(pool)]

    candidates = _split_candidates(groups, weights, len(pool))
    if not candidates:
        ordered = order(pool)
        half = (len(ordered) + 1) // 2
        return ordered[:half], ordered[half:]
    _cost, chosen = min(candidates, key=lambda c: c[0])
    a = [rel for gi in sorted(chosen) for rel in groups[gi][1]]
    b = [rel for gi in range(len(groups)) if gi not in chosen for rel in groups[gi][1]]
    mass_a = sum(weights[r] for r in a)
    mass_b = sum(weights[r] for r in b)
    disabled, enabled = (a, b) if mass_a >= mass_b else (b, a)
    return order(enabled), order(disabled)


def start(state, files, mods_root, progress=None):
    mods_root = str(Path(mods_root))
    mods = Path(mods_root)
    if not mods.is_dir():
        raise BisectError('Mods folder not found: %s' % mods_root)
    rels = []
    for f in files:
        p = Path(f)
        try:
            rel = p.resolve().relative_to(mods.resolve())
        except ValueError:
            raise BisectError('Not inside the Mods folder: %s' % f)
        if not p.exists():
            raise BisectError('File no longer exists: %s' % f)
        rels.append(str(rel))
    rels = sorted(dict.fromkeys(rels))
    if len(rels) < 2:
        raise BisectError('Pick at least two files to bisect.')

    log.info('bisect start: %d files from %s', len(rels), mods_root)
    backup = store.create_backup(state, mods_root, 'pre-bisect', progress=progress)

    sid = uuid.uuid4().hex[:12]
    scores = risk_scores(state)
    enabled, disabled = plan(rels, scores)
    session = {
        'id': sid,
        'created': time.time(),
        'mods_root': mods_root,
        'members': rels,
        'pool': list(rels),
        'enabled': enabled,
        'disabled': disabled,
        'backup': backup,
        'history': [],
        'status': 'active',
        'culprit': None,
        'scores': scores,
        'strategy': 'risk-balanced' if scores else 'balanced',
        'rejected': [],
    }
    _session_dir(sid).mkdir(parents=True, exist_ok=True)
    desired = {rel: 'in' for rel in enabled}
    desired.update({rel: 'out' for rel in disabled})
    session['moved'] = _apply(session, desired, progress=progress)
    log.info('bisect first split (%s): %d enabled, %d disabled, %d moved',
             session['strategy'], len(enabled), len(disabled), len(session['moved']))
    sessions = _load(state)
    sessions[sid] = session
    _save(state, sessions)
    return session


def verdict(state, sid, result, progress=None):
    """result: 'broken' (problem still happens) or 'fixed' (problem gone)."""
    sessions = _load(state)
    s = sessions.get(sid)
    if not s:
        raise BisectError('No such 50/50 session.')
    if s.get('status') != 'active':
        raise BisectError('That session is already finished.')
    if result not in ('broken', 'fixed'):
        raise BisectError("result must be 'broken' or 'fixed'")

    enabled, disabled = list(s['enabled']), list(s['disabled'])
    if result == 'broken':
        culprit_half, cleared = enabled, disabled
    else:
        culprit_half, cleared = disabled, enabled

    log.info('bisect verdict %s: pool %d -> %d', result, len(s['pool']), len(culprit_half))
    s['history'].append({'step': len(s['history']) + 1, 'result': result,
                         'pool_before': list(s['pool']),
                         'enabled': list(enabled), 'disabled': list(disabled),
                         'pool_after': list(culprit_half)})

    if len(culprit_half) <= 1:
        s['pool'] = list(culprit_half)
        s['enabled'] = list(culprit_half)
        s['disabled'] = []
        s['culprit'] = culprit_half[0] if culprit_half else None
        s['candidate_confirmed'] = False
        s['status'] = 'done'
        desired = {rel: 'in' for rel in cleared}
        desired.update({rel: 'in' for rel in s['pool']})
        if s['culprit']:
            desired[s['culprit']] = 'out'
        s['moved'] = _apply(s, desired, progress=progress)
        sessions[sid] = s
        _save(state, sessions)
        return s

    new_pool = culprit_half
    new_enabled, new_disabled = plan(new_pool, s.get('scores'))
    desired = {}
    for rel in cleared:
        desired[rel] = 'in'
    for rel in new_enabled:
        desired[rel] = 'in'
    for rel in new_disabled:
        desired[rel] = 'out'
    s['pool'] = list(new_pool)
    s['enabled'] = list(new_enabled)
    s['disabled'] = list(new_disabled)
    s['moved'] = _apply(s, desired, progress=progress)
    sessions[sid] = s
    _save(state, sessions)
    return s


def undo_verdict(state, sid, progress=None):
    """Take back the last answer and restore the previous split.

    Useful when a test run was inconclusive or the wrong button was clicked.
    """
    sessions = _load(state)
    s = sessions.get(sid)
    if not s:
        raise BisectError('No such 50/50 session.')
    history = s.get('history') or []
    if not history:
        raise BisectError('There is no answer to undo yet.')
    log.info('bisect undo requested')
    step = history.pop()
    pool_before = step.get('pool_before') or (list(step.get('enabled') or []) + list(step.get('disabled') or []))
    s['pool'] = list(pool_before)
    s['enabled'] = list(step.get('enabled') or [])
    s['disabled'] = list(step.get('disabled') or [])
    s['status'] = 'active'
    s['culprit'] = None
    s['candidate_confirmed'] = False
    desired = {rel: 'in' for rel in s.get('members', [])}
    desired.update({rel: 'out' for rel in s['disabled']})
    s['moved'] = _apply(s, desired, progress=progress)
    sessions[sid] = s
    _save(state, sessions)
    return s


def reject_candidate(state, sid, progress=None):
    """The single remaining file is not the culprit — keep searching without it."""
    sessions = _load(state)
    s = sessions.get(sid)
    if not s:
        raise BisectError('No such 50/50 session.')
    culprit = s.get('culprit')
    if not culprit:
        raise BisectError('There is no candidate to reject.')
    remaining = [rel for rel in s.get('members', []) if rel != culprit]
    if len(remaining) < 2:
        raise BisectError('No files left to test — restore everything instead.')
    log.info('bisect candidate rejected: %s', culprit)
    s.setdefault('rejected', []).append(culprit)
    enabled, disabled = plan(remaining, s.get('scores'))
    s['pool'] = remaining
    s['enabled'] = enabled
    s['disabled'] = disabled
    s['culprit'] = None
    s['candidate_confirmed'] = False
    s['status'] = 'active'
    desired = {rel: 'in' for rel in s.get('members', [])}
    desired.update({rel: 'out' for rel in disabled})
    s['moved'] = _apply(s, desired, progress=progress)
    sessions[sid] = s
    _save(state, sessions)
    return s


def restore_all(state, sid, progress=None):
    """Put every file from this session back where it belongs."""
    sessions = _load(state)
    s = sessions.get(sid)
    if not s:
        raise BisectError('No such 50/50 session.')
    desired = {rel: 'in' for rel in s.get('members', [])}
    s['moved'] = _apply(s, desired, progress=progress)
    s['status'] = 'aborted'
    s['disabled'] = []
    s['enabled'] = list(s.get('members', []))
    sessions[sid] = s
    _save(state, sessions)
    return s


def finish(state, sid, progress=None):
    """Restore everything except the culprit, and move the culprit into quarantine."""
    sessions = _load(state)
    s = sessions.get(sid)
    if not s:
        raise BisectError('No such 50/50 session.')
    culprit = s.get('culprit')
    desired = {rel: 'in' for rel in s.get('members', []) if rel != culprit}
    s['moved'] = _apply(s, desired, progress=progress)
    # Move the culprit (still in the stash, or put back by the user) into the
    # visible quarantine so it can be restored from Tools -> Quarantine.
    if culprit:
        stash = _stash_path(s, culprit)
        target = Path(s['mods_root']) / culprit
        src = stash if stash.exists() else (target if target.exists() else None)
        if src is not None:
            store._ensure()
            qid = uuid.uuid4().hex[:12]
            dest = store.QUAR_DIR / ('%s__%s' % (qid, src.name))
            shutil.move(str(src), str(dest))
            state.setdefault('quarantine', []).append({
                'id': qid,
                'original': str(target),
                'stored': str(dest),
                'name': src.name,
                'reason': '50/50 culprit',
                'note': 'Identified by 50/50 as the file causing the problem',
                'time': time.time(),
                'size': dest.stat().st_size,
            })
    s['status'] = 'done'
    s['candidate_confirmed'] = True
    sessions[sid] = s
    _save(state, sessions)
    return s


def forget(state, sid):
    sessions = _load(state)
    sessions.pop(sid, None)
    _save(state, sessions)
    # Remove empty dirs only; never delete stashed files silently.
    d = _session_dir(sid)
    try:
        for dirpath, dirnames, filenames in os.walk(d, topdown=False):
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
    except OSError:
        pass
