import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from modbroom import log, demo


@pytest.fixture(autouse=True)
def clean_logging():
    log.reset()
    yield
    log.reset()


def test_debug_messages_are_written_to_the_log_file(tmp_path):
    path = tmp_path / 'logs' / 'modbroom.log'
    log.setup(verbose=False, log_file=path, force=True)
    log.get_logger('test').debug('detail %s', 42)
    for handler in log.get_logger().handlers:
        handler.flush()
    text = path.read_text(encoding='utf-8')
    assert 'detail 42' in text
    assert 'DEBUG' in text


def test_verbose_enables_debug_on_the_console(tmp_path, capsys):
    path = tmp_path / 'modbroom.log'
    log.setup(verbose=True, log_file=path, force=True)
    log.get_logger('test').debug('verbose marker')
    assert 'verbose marker' in capsys.readouterr().err


def test_quiet_mode_hides_debug_on_the_console(tmp_path, capsys):
    path = tmp_path / 'modbroom.log'
    log.setup(verbose=False, log_file=path, force=True)
    log.get_logger('test').debug('hidden marker')
    assert 'hidden marker' not in capsys.readouterr().err
    assert 'hidden marker' in path.read_text(encoding='utf-8')


def test_stale_results_are_dropped_when_schema_changes(tmp_path, monkeypatch):
    """An old cached scan must not keep showing errors a new parser fixed."""
    from modbroom import store
    monkeypatch.setattr(store, 'APP_DIR', tmp_path / 'app')
    monkeypatch.setattr(store, 'STATE_FILE', tmp_path / 'app' / 'state.json')
    monkeypatch.setattr(store, 'QUAR_DIR', tmp_path / 'app' / 'quarantine')
    monkeypatch.setattr(store, 'BACKUP_DIR', tmp_path / 'app' / 'backups')
    state = store.load_state()
    state['last_scan'] = {'files': []}
    state['last_findings'] = {'parse_errors': [{'file': 'x', 'error': 'No index offset present'}]}
    store.save_state(state)

    monkeypatch.setattr(store, 'CACHE_SCHEMA', 'new-schema')
    state = store.load_state()
    assert state['last_scan'] is None
    assert state['last_findings'] is None
    assert state['cache_schema'] == 'new-schema'


def test_cli_verbose_reports_scan_details(tmp_path, capsys):
    from modbroom import cli
    mods = tmp_path / 'Mods'
    demo.make_demo_library(mods)
    logpath = tmp_path / 'cli.log'
    cli.main(['--verbose', '--log-file', str(logpath), str(mods)])
    err = capsys.readouterr().err
    assert 'scan start' in err
    assert 'findings:' in err
    assert 'CLI scan requested' in err
    assert 'CLI scan requested' in logpath.read_text(encoding='utf-8')
