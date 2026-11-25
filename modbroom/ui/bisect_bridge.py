"""Pages call the bisect engine with the app's live state dict.

The engine persists to disk via store.save_state, which mutates nothing on the
passed-in object beyond adding/replacing the 'bisect' key — so the caller's
state object stays authoritative for the UI.

`progress` is an optional callable taking a short status string. Pages hand it
a signal emitter so backups and file moves run off the UI thread with feedback.
"""
from .. import bisect as _bisect


def active_sessions(state):
    return _bisect.active_sessions(state)


def all_sessions(state):
    return list((state or {}).get('bisect', {}).values())


def start(state, files, mods_root, progress=None):
    return _bisect.start(state, files, mods_root, progress=progress)


def verdict(state, sid, result, progress=None):
    return _bisect.verdict(state, sid, result, progress=progress)


def undo_verdict(state, sid, progress=None):
    return _bisect.undo_verdict(state, sid, progress=progress)


def reject_candidate(state, sid, progress=None):
    return _bisect.reject_candidate(state, sid, progress=progress)


def restore_all(state, sid, progress=None):
    return _bisect.restore_all(state, sid, progress=progress)


def finish(state, sid, progress=None):
    return _bisect.finish(state, sid, progress=progress)


def forget(state, sid):
    return _bisect.forget(state, sid)
