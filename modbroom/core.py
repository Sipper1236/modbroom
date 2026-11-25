"""Shared controller + worker threads for ModBroom's UI.

Keeps every engine call off the UI thread. The window and the CLI both use this.
"""
import json
import threading
import time
import traceback

from . import scanner, store, crashlog, game_rules, demo
from .store import load_state, save_state
from .log import get_logger

log = get_logger('core')

APP_DIR = store.APP_DIR
PARTNER_PATH = APP_DIR / 'partner.json'


def read_partner():
    try:
        with open(PARTNER_PATH) as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return None


def clear_partner():
    try:
        PARTNER_PATH.unlink()
    except FileNotFoundError:
        pass


def edge_path():
    """First launch bootstrap script written for the in-game companion mod."""
    return APP_DIR / 'ModBroomBridge.ts4script'


def run_scan(state, on_progress=None, on_done=None, on_error=None):
    """Full pipeline: scan -> findings -> usage -> game rules -> crash logs.

    Callbacks fire from a worker thread; GUI callers must marshal to the UI thread.
    """
    def worker():
        try:
            s = state['settings']
            mods = s.get('mods_path') or ''
            t0 = time.time()
            log.info('pipeline start: mods=%s', mods)
            scan = scanner.scan_tree(mods, s.get('saves_path'), s.get('tray_path'),
                                     progress=on_progress)
            findings = scanner.analyze(scan, mods_path=scan.get('mods_path'))
            usage = None
            if s.get('include_saves', True):
                ev = scanner.scan_saves_and_tray(s.get('saves_path'), s.get('tray_path'))
                usage = scanner.usage_report(scan, ev)
            gr = game_rules.analyze(scan)
            logs = crashlog.find_crash_logs(s.get('logs_path'))
            parsed = [crashlog.parse_crash_log(p) for p in logs[:20]]
            suspects = crashlog.rank_suspects(parsed, scan['files'])
            state['last_scan'] = dict(scan)
            state['last_findings'] = findings
            state['last_usage'] = usage
            state['last_game_rules'] = gr
            state['last_crashlogs'] = {'logs': parsed, 'suspects': suspects, 'elapsed': time.time() - t0}
            try:
                from . import bridge
                bridge.write_partner(state)
            except Exception:
                pass
            save_state(state)
            log.info('pipeline complete in %.2fs: %d files, %d findings, %d game-rule notes',
                     time.time() - t0, len(scan['files']), len(findings.get('conflicts', [])), len(gr))
            if on_done:
                on_done(state)
        except Exception as exc:
            log.exception('scan pipeline failed')
            if on_error:
                on_error(exc)
    threading.Thread(target=worker, daemon=True).start()


def demo_library():
    """Point the app at a fresh synthetic library (for people without the game)."""
    root = demo.make_demo_library()
    st = load_state()
    st['settings'].update({
        'mods_path': str(root),
        'saves_path': str(root.parent / 'saves'),
        'tray_path': str(root.parent / 'tray'),
        'logs_path': str(root.parent / 'logs'),
    })
    save_state(st)
    return st
