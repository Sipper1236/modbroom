"""Pages call the bisect engine with the app's live state dict.

The engine persists to disk via store.save_state, which mutates nothing on the
passed-in object beyond adding/replacing the 'bisect' key — so the caller's
state object stays authoritative for the UI.
"""
from .. import bisect as _bisect


def active_sessions(state):
    return _bisect.active_sessions(state)


def all_sessions(state):
    return list((state or {}).get('bisect', {}).values())


def start(state, files, mods_root):
    return _bisect.start(state, files, mods_root)


def verdict(state, sid, result):
    return _bisect.verdict(state, sid, result)


def restore_all(state, sid):
    return _bisect.restore_all(state, sid)


def finish(state, sid):
    return _bisect.finish(state, sid)


def forget(state, sid):
    return _bisect.forget(state, sid)
