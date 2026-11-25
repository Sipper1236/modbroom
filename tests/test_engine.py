import os, sys, json, shutil, re, zipfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from modbroom import scanner, store, bisect, crashlog, demo


def test_version_string_is_not_flagged_as_ip():
    pattern = r'\b\d{1,3}(?:\.\d{1,3}){3}\b(?!\.\d)'
    version = re.search(pattern, 'version = "7.18.178.178"')
    assert version is not None
    assert not scanner._looks_like_ip(version)
    real = re.search(pattern, 'host = "185.199.108.153"')
    assert scanner._looks_like_ip(real)


def test_script_version_string_does_not_create_risk_finding(tmp_path):
    script = tmp_path / 'legit.ts4script'
    with zipfile.ZipFile(script, 'w') as zf:
        zf.writestr('mod.py', 'VERSION = "7.18.178.178"\n')
    msgs = [f['msg'] for f in scanner.scan_script_zip(script)]
    assert 'IP-like address' not in msgs


@pytest.fixture()
def mods(tmp_path, monkeypatch):
    root = tmp_path / 'demo' / 'Mods'
    demo.make_demo_library(root)
    monkeypatch.setattr(store, 'APP_DIR', tmp_path / 'app')
    monkeypatch.setattr(store, 'QUAR_DIR', tmp_path / 'app' / 'quarantine')
    monkeypatch.setattr(store, 'BACKUP_DIR', tmp_path / 'app' / 'backups')
    monkeypatch.setattr(store, 'STATE_FILE', tmp_path / 'app' / 'state.json')
    monkeypatch.setattr(bisect, 'BISECT_DIR', tmp_path / 'app' / 'bisect')
    store.DEFAULT_STATE['quarantine'] = []
    return root


def test_scan_finds_expected_defects(mods):
    scan = scanner.scan_tree(str(mods))
    findings = scanner.analyze(scan, mods_path=str(mods))
    stats = findings['stats']
    assert stats['packages'] >= 3
    assert stats['scripts'] == 2
    assert stats['duplicates'] >= 1       # cool_hair_v2 (1).package
    assert stats['conflicts'] >= 1        # override_mesh vs cool_hair_v2
    assert stats['integrity'] >= 1       # broken_download.package
    assert stats['high_risks'] >= 1      # free_money_cheat.ts4script


def test_conflict_winner_prefers_later_load(tmp_path):
    root = tmp_path / 'Mods'
    root.mkdir()
    from modbroom.demo import _build_package
    (root / 'a_first.package').write_bytes(_build_package([(0x015A1849, 0, 0xABCD, b'A' * 64)]))
    (root / 'z_second.package').write_bytes(_build_package([(0x015A1849, 0, 0xABCD, b'B' * 64)]))
    scan = scanner.scan_tree(str(root))
    findings = scanner.analyze(scan, mods_path=str(root))
    conflict = next(c for c in findings['conflicts'] if '0x000000000000ABCD' in c['tgi'])
    assert conflict['winner'].endswith('z_second.package')
    assert conflict['losers'] == [os.path.join(str(root), 'a_first.package')]


def test_quarantine_and_restore_roundtrip(mods, tmp_path):
    state = store.load_state()
    state['settings']['mods_path'] = str(mods)
    victim = mods / 'helpful_lib.ts4script'
    original = victim.read_bytes()
    store.quarantine_files(state, [str(victim)], 'test')
    assert not victim.exists()
    assert len(state['quarantine']) == 1
    qid = state['quarantine'][0]['id']
    store.restore_quarantine(state, [qid])
    assert victim.exists() and victim.read_bytes() == original


def test_risk_first_split_moves_high_risk_files_out():
    pool = ['f%02d.package' % i for i in range(10)]
    scores = {pool[0]: 12, pool[1]: 9}
    enabled, disabled = bisect.plan(pool, scores, risk_first=True)
    assert pool[0] in disabled and pool[1] in disabled
    assert len(disabled) <= len(pool) // 2
    assert enabled and set(enabled).isdisjoint(disabled)


def test_plain_split_is_balanced():
    pool = ['f%02d.package' % i for i in range(12)]
    enabled, disabled = bisect.plan(pool)
    assert len(enabled) == 6 and len(disabled) == 6
    assert set(enabled).isdisjoint(disabled)


def test_risk_balanced_split_isolates_strong_hint():
    pool = ['f%02d.package' % i for i in range(12)]
    scores = {pool[0]: 10, pool[1]: 8}
    enabled, disabled = bisect.plan(pool, scores)
    # A strong hint should be moved out, leaving a small pool if it is right.
    assert set(scores).issubset(set(disabled))
    assert len(disabled) <= len(enabled)
    assert set(enabled).isdisjoint(disabled)


def test_mod_companion_files_stay_in_the_same_half():
    pool = ['a/main.package', 'a/extra.package', 'b/main.package', 'b/extra.package']
    scores = {'a/main.package': 9}
    enabled, disabled = bisect.plan(pool, scores)
    for folder in ('a', 'b'):
        members = [r for r in pool if r.startswith(folder + '/')]
        assert set(members).issubset(set(enabled)) or set(members).issubset(set(disabled))


def test_bisect_reports_progress_during_start(mods, tmp_path):
    state = store.load_state()
    files = [str(p) for p in sorted(mods.iterdir()) if p.is_file()]
    messages = []
    s = bisect.start(state, files, str(mods), progress=messages.append)
    assert s['status'] == 'active'
    assert any('Backed up' in m for m in messages)
    assert any('Moved' in m for m in messages)


def test_backup_does_not_recompress_package_files(mods, tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'BACKUP_DIR', tmp_path / 'backups')
    messages = []
    path = store.create_backup({}, str(mods), 'test', progress=messages.append)
    with zipfile.ZipFile(path) as zf:
        info = zf.getinfo('cool_hair_v2.package')
        assert info.compress_type == zipfile.ZIP_STORED
    assert any('Backed up' in m for m in messages)


def test_bisect_undo_restores_previous_split(mods):
    state = store.load_state()
    files = [str(p) for p in sorted(mods.iterdir()) if p.is_file()]
    s = bisect.start(state, files, str(mods))
    before = (list(s['pool']), list(s['enabled']), list(s['disabled']))
    s = bisect.verdict(state, s['id'], 'broken')
    assert list(s['pool']) != before[0]
    s = bisect.undo_verdict(state, s['id'])
    assert s['status'] == 'active'
    assert (list(s['pool']), list(s['enabled']), list(s['disabled'])) == before


def test_bisect_reject_candidate_continues_search(mods):
    state = store.load_state()
    files = [str(p) for p in sorted(mods.iterdir()) if p.is_file()]
    s = bisect.start(state, files, str(mods))
    culprit = files[0]
    guard = 0
    while s['status'] == 'active' and guard < 12:
        result = 'broken' if culprit in s['enabled'] else 'fixed'
        s = bisect.verdict(state, s['id'], result)
        guard += 1
    assert s['status'] == 'done'
    assert s['culprit'] is not None
    s = bisect.reject_candidate(state, s['id'])
    assert s['status'] == 'active'
    assert culprit not in s['pool']
    assert (mods / Path(culprit).name).exists()


def test_bisect_finds_culprit(mods, tmp_path):
    state = store.load_state()
    state['settings']['mods_path'] = str(mods)
    files = [str(p) for p in sorted(mods.iterdir()) if p.is_file()]
    s = bisect.start(state, files, str(mods))
    guard = 0
    while s['status'] == 'active' and guard < 12:
        broken = (mods / 'free_money_cheat.ts4script').exists()
        s = bisect.verdict(state, s['id'], 'broken' if broken else 'fixed')
        guard += 1
    assert s['culprit'].endswith('free_money_cheat.ts4script')
    s = bisect.finish(state, s['id'])
    assert s['status'] == 'done'
    # culprit ends up out of Mods and visible in quarantine
    assert not (mods / 'free_money_cheat.ts4script').exists()
    assert any(q['name'] == 'free_money_cheat.ts4script' for q in state['quarantine'])
    # everything else is back
    assert (mods / 'helpful_lib.ts4script').exists()


def test_crash_log_ranking(mods, tmp_path):
    logs = mods.parent / 'logs'
    parsed = [crashlog.parse_crash_log(p) for p in crashlog.find_crash_logs(str(logs))]
    scan = scanner.scan_tree(str(mods))
    ranked = crashlog.rank_suspects(parsed, scan['files'])
    assert ranked, 'expected at least one ranked suspect'
    assert ranked[0]['match'] == 'free_money_cheat'


def test_export_html_contains_report(tmp_path):
    scan = {'mods_path': '/x', 'files': [], 'total_bytes': 0}
    findings = {'stats': {'total_files': 0, 'packages': 0, 'scripts': 0, 'total_resources': 0,
                          'duplicates': 0, 'resource_dupes': 0, 'conflicts': 0, 'integrity': 0,
                          'script_risks': 0, 'high_risks': 0},
                'conflicts': [], 'duplicates': [], 'integrity': [], 'parse_errors': [],
                'script_risks': [], 'load_order': [], 'not_loaded': [], 'resource_cfg': None}
    out = tmp_path / 'r.html'
    store.export_html(scan, findings, str(out))
    html = out.read_text()
    assert '<html' in html and 'Load order' in html and 'ModBroom' in html
