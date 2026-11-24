import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from modbroom import loadorder

CFG = """Priority 900
PackedFile Overrides/*.package
Priority 500
PackedFile *.package
PackedFile */*.package
"""


def test_parse_blocks():
    cfg = loadorder.ResourceCfg.parse(CFG)
    assert cfg.blocks[0]['priority'] == 900
    assert cfg.blocks[1]['priority'] == 500


def test_higher_priority_loads_later(tmp_path):
    root = tmp_path
    (root / 'Overrides').mkdir()
    (root / 'base.package').write_bytes(b'x')
    (root / 'Overrides' / 'top.package').write_bytes(b'x')
    (root / 'Resource.cfg').write_text(CFG)
    cfg, path = loadorder.ResourceCfg.load(str(root))
    files = [
        {'path': str(root / 'base.package'), 'rel': 'base.package'},
        {'path': str(root / 'Overrides' / 'top.package'), 'rel': 'Overrides/top.package'},
    ]
    ordered, unmatched = loadorder.order_files(files, cfg, str(root))
    assert [f['rel'] for f in ordered] == ['base.package', 'Overrides/top.package']
    assert unmatched == []


def test_unmatched_files_reported(tmp_path):
    root = tmp_path
    cfg = loadorder.ResourceCfg.parse('Priority 500\nPackedFile *.package\n')
    files = [{'path': str(root / 'deep/a/b/c/d/e.package'), 'rel': 'deep/a/b/c/d/e.package'}]
    ordered, unmatched = loadorder.order_files(files, cfg, str(root))
    assert ordered == []
    assert len(unmatched) == 1


def test_conflict_winner_is_last_to_load(tmp_path):
    root = tmp_path
    (root / 'Overrides').mkdir()
    (root / 'Resource.cfg').write_text(CFG)
    files = [
        {'path': str(root / 'a.package'), 'rel': 'a.package'},
        {'path': str(root / 'Overrides' / 'z.package'), 'rel': 'Overrides/z.package'},
    ]
    cfg, _ = loadorder.ResourceCfg.load(str(root))
    ordered, _ = loadorder.order_files(files, cfg, str(root))
    conflicts = [{'tgi': '0x1:0x0:0x2', 'files': [f['path'] for f in files], 'file_count': 2}]
    resolved = loadorder.resolve_conflicts(conflicts, ordered)
    assert resolved[0]['winner'].endswith('z.package')


def test_default_cfg_when_missing(tmp_path):
    cfg, path = loadorder.ResourceCfg.load(str(tmp_path))
    assert path is None
    assert cfg.blocks[0]['priority'] == 500


def test_case_insensitive_matching(tmp_path):
    cfg = loadorder.ResourceCfg.parse('Priority 500\nPackedFile *.PACKAGE\n')
    files = [{'path': str(tmp_path / 'A.Package'), 'rel': 'A.Package'}]
    ordered, unmatched = loadorder.order_files(files, cfg, str(tmp_path))
    assert len(ordered) == 1
