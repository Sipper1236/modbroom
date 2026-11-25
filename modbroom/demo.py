"""Generate a synthetic Sims 4 Mods folder for demo/testing purposes."""
import io, os, random, struct, sys, zlib, zipfile
from pathlib import Path
from .dbpf import COMP_ZLIB, COMP_UNCOMPRESSED

def _build_package(resources):
    """resources: list of (type, group, instance, payload_bytes)"""
    out = io.BytesIO()
    out.write(b'DBPF')
    out.write(struct.pack('<2I', 2, 1))          # major, minor
    out.write(struct.pack('<6I', 0, 0, 0, 0, 0, 0))  # versions + times + unknown
    out.write(struct.pack('<I', 0))               # index_count placeholder
    out.write(struct.pack('<I', 0))               # index offset short placeholder
    out.write(struct.pack('<I', 0))               # index size placeholder
    out.write(b'\x00' * 12)                       # unknown
    out.write(struct.pack('<I', 3))               # magic const
    out.write(struct.pack('<Q', 0))               # long index offset placeholder
    out.write(b'\x00' * 24)                       # padding

    entries = []
    for rtype, group, inst, payload in resources:
        comp = zlib.compress(payload)
        use_z = len(comp) < len(payload)
        blob = comp if use_z else payload
        offset = out.tell()
        out.write(blob)
        entries.append((rtype, group, inst & 0xFFFFFFFF, (inst >> 32) & 0xFFFFFFFF,
                        offset, len(blob), len(payload), COMP_ZLIB if use_z else COMP_UNCOMPRESSED))

    index_offset = out.tell()
    idx = io.BytesIO()
    idx.write(struct.pack('<I', 0x1 | 0x2 | 0x4))  # constant type+group+instance-hi
    # write constant headers: use first entry's values as "constants" only if uniform; simpler: no constants
    idx.seek(0)
    idx.truncate(0)
    idx.write(struct.pack('<I', 0))  # flags = none, everything inline
    for rtype, group, inst_lo, inst_hi, offset, csize, usize, comp in entries:
        idx.write(struct.pack('<I', rtype))
        idx.write(struct.pack('<I', group))
        idx.write(struct.pack('<I', inst_hi))
        idx.write(struct.pack('<I', inst_lo))
        idx.write(struct.pack('<I', offset))
        idx.write(struct.pack('<I', (csize & 0x7FFFFFFF) | 0x80000000))  # extended
        idx.write(struct.pack('<I', usize))
        idx.write(struct.pack('<H', comp))
        idx.write(struct.pack('<H', 1))  # committed
    index_bytes = idx.getvalue()
    index_size = len(index_bytes)
    out.write(index_bytes)

    data = bytearray(out.getvalue())
    struct.pack_into('<I', data, 36, len(entries))
    struct.pack_into('<I', data, 40, 0)                    # short offset unused
    struct.pack_into('<I', data, 44, index_size)
    struct.pack_into('<Q', data, 68, index_offset)         # long offset
    return bytes(data)

def _ts4script(py_name, body):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(py_name, body)
    return buf.getvalue()

def make_demo_library(root=None):
    random.seed(1337)
    root = Path(root) if root else Path.home() / '.modbroom' / 'demo' / 'Mods'
    saves = root.parent / 'saves'; tray = root.parent / 'tray'; logs = root.parent / 'logs'
    for d in (root, saves, tray, logs):
        d.mkdir(parents=True, exist_ok=True)

    def pkg(name, resources):
        (root / name).write_bytes(_build_package(resources))

    # A healthy CAS part package
    pkg('cool_hair_v2.package', [(0x034AEECB, 0x00000000, 0x0000000100000001, b'\x01' * 512),
                                 (0x015A1849, 0x00000000, 0x0000000200000001, b'\x02' * 2048),
                                 (0x00B2D882, 0x00000000, 0x0000000300000001, zlib.compress(b'\x09' * 4096))])
    # Duplicate of the same package under another name
    (root / 'cool_hair_v2 (1).package').write_bytes((root / 'cool_hair_v2.package').read_bytes())
    # A conflicting package sharing one TGI
    pkg('override_mesh.package', [(0x015A1849, 0x00000000, 0x0000000200000001, b'\x07' * 1024),
                                  (0x069C5B1F, 0x00000000, 0x0000000400000002, b'\x03' * 256)])
    # A truncated/corrupt package
    (root / 'broken_download.package').write_bytes((root / 'cool_hair_v2.package').read_bytes()[:200])
    # A clean script mod
    (root / 'helpful_lib.ts4script').write_bytes(_ts4script('helpful_lib/__init__.py',
        'import sims4\n# totally fine mod\ndef hello():\n    return 42\n'))
    # A spicy script mod
    (root / 'free_money_cheat.ts4script').write_bytes(_ts4script('free_money/__init__.py',
        'import os, subprocess, socket\nimport base64\nexec(base64.b64decode("cHJpbnQoJ3N1cnByaXNlJyk="))\nos.system("echo hi")\nURL="http://192.168.1.66/collect"\n'))
    # Save file referencing one TGI
    (saves / 'slot_00000001.save').write_bytes(b'\x00\x01TGI:0x015A1849:0x00000000:0x0000000200000001\x00' + os.urandom(2048))
    # Tray file referencing the same TGI
    (tray / 'lot_123.trayitem').write_bytes(b'TGI:0x015A1849:0x00000000:0x0000000200000001' + os.urandom(1024))
    # A fake crash log naming the spicy mod
    (logs / 'LastException_2026-11-20.txt').write_text(
        'SAVED_CRASH\nException: 0xc0000005\nfree_money_cheat.py line 3\nsubprocess.CalledProcessError\n')
    return root


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else None
    root = make_demo_library(target)
    print('Demo Mods folder written to %s' % root)
