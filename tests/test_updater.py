import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from modbroom import updater


def test_version_parsing():
    assert updater._parse_version('v1.2.3') == (1, 2, 3)
    assert updater._parse_version('1.2') == (1, 2)
    assert updater._parse_version('2.0.0-beta') == (2, 0, 0)
    assert updater._parse_version('garbage') == (0,)


def test_is_newer():
    assert updater.is_newer('1.2.0', '1.1.9')
    assert updater.is_newer('1.10.0', '1.9.0')
    assert updater.is_newer('2.0', '1.9.9')
    assert not updater.is_newer('1.0.0', '1.0.0')
    assert not updater.is_newer('1.0.0', '1.0.1')
    assert not updater.is_newer('1.0', '1.0.0')       # 1.0 == 1.0.0
    assert updater.is_newer('1.0.1', '1.0')


def test_platform_asset_name():
    # the release publishes a Windows exe; other platforms use the plain binary
    assert updater.platform_asset_name() in ('ModBroom.exe', 'ModBroom')


def test_current_executable_none_when_source():
    assert updater.current_executable() is None


def test_check_for_update_uses_release_feed(monkeypatch):
    payload = {
        'tag_name': 'v9.9.9',
        'html_url': 'https://github.com/Sipper1236/modbroom/releases/tag/v9.9.9',
        'body': 'notes here',
        'assets': [{'name': 'ModBroom.exe',
                    'browser_download_url': 'https://example.invalid/ModBroom.exe'}],
    }
    monkeypatch.setattr(updater, '_get_json', lambda url: payload)
    rel, msg = updater.check_for_update(current='1.0.0')
    assert rel is not None
    assert rel['version'] == '9.9.9'
    assert '9.9.9' in msg
    assert rel['assets']['ModBroom.exe'].endswith('ModBroom.exe')


def test_check_for_update_up_to_date(monkeypatch):
    payload = {'tag_name': 'v1.0.0', 'html_url': 'x', 'body': '', 'assets': []}
    monkeypatch.setattr(updater, '_get_json', lambda url: payload)
    rel, msg = updater.check_for_update(current='1.0.0')
    assert rel is None
    assert 'up to date' in msg.lower()


def test_install_update_refuses_when_running_from_source(tmp_path):
    fake = tmp_path / 'ModBroom.exe'
    fake.write_bytes(b'MZ')
    with pytest.raises(updater.UpdateError):
        updater.install_update(fake)


def test_install_update_replaces_binary(tmp_path, monkeypatch):
    """Simulate a frozen app: point current_executable() at a fake binary."""
    exe = tmp_path / 'ModBroom.exe'
    exe.write_bytes(b'OLD')
    new = tmp_path / 'downloaded.exe'
    new.write_bytes(b'NEW')
    monkeypatch.setattr(updater, 'current_executable', lambda: exe)
    monkeypatch.setattr(updater, '_schedule_cleanup', lambda p: None)
    monkeypatch.setattr(sys, 'platform', 'linux')
    updater.install_update(new)
    assert exe.read_bytes() == b'NEW'


def test_install_update_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, 'current_executable', lambda: tmp_path / 'ModBroom.exe')
    with pytest.raises(updater.UpdateError):
        updater.install_update(tmp_path / 'nope.exe')


def test_pending_cleanup_removes_old_binary(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setattr(updater, 'app_dir', lambda: home)
    marker = home / 'cleanup.txt'
    old = tmp_path / 'ModBroom.exe.old'
    old.write_bytes(b'OLD')
    marker.write_text(str(old))
    updater.run_pending_cleanup()
    assert not old.exists()
    assert not marker.exists()


def test_pending_cleanup_is_a_noop_without_marker(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setattr(updater, 'app_dir', lambda: home)
    updater.run_pending_cleanup()   # must not raise


def test_download_asset_writes_file(tmp_path, monkeypatch):
    class FakeResp:
        headers = {'Content-Length': '5'}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            if getattr(self, '_done', False):
                return b''
            self._done = True
            return b'HELLO'

    monkeypatch.setattr(updater.urllib.request, 'urlopen', lambda req, timeout=None: FakeResp())
    out = updater.download_asset('https://example.invalid/ModBroom.exe', dest_dir=tmp_path)
    assert Path(out).read_bytes() == b'HELLO'
    assert not Path(str(out) + '.part').exists()
