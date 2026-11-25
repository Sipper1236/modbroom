import struct
import sys, os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from modbroom import dbpf
from modbroom.demo import _build_package


def test_roundtrip_package(tmp_path):
    payload = b'\x11' * 700
    pkg = tmp_path / 'test.package'
    pkg.write_bytes(_build_package([(0x034AEECB, 0x00000001, 0xDEADBEEF, payload)]))
    reader = dbpf.PackageReader(pkg)
    assert len(reader.entries) == 1
    e = reader.entries[0]
    assert e.type_id == 0x034AEECB
    assert e.group_id == 0x00000001
    assert e.instance_id == 0xDEADBEEF
    assert reader.resource_bytes(e) == payload


def test_tgi_set(tmp_path):
    pkg = tmp_path / 'multi.package'
    pkg.write_bytes(_build_package([
        (0x015A1849, 0, 0x1111111122222222, b'a' * 100),
        (0x069C5B1F, 0, 0x3333333344444444, b'b' * 100),
    ]))
    reader = dbpf.PackageReader(pkg)
    assert reader.tgi_set() == {(0x015A1849, 0, 0x1111111122222222), (0x069C5B1F, 0, 0x3333333344444444)}


def test_truncated_file_raises(tmp_path):
    good = _build_package([(0x015A1849, 0, 1, b'x' * 200)])
    bad = tmp_path / 'broken.package'
    bad.write_bytes(good[:100])
    with pytest.raises(dbpf.PackageError):
        dbpf.PackageReader(bad)


def test_not_a_package(tmp_path):
    p = tmp_path / 'notapkg.package'
    p.write_bytes(b'NOPE' + b'\x00' * 200)
    with pytest.raises(dbpf.PackageError):
        dbpf.PackageReader(p)


def test_integrity_flags_missing_resources(tmp_path):
    good = _build_package([(0x015A1849, 0, 1, b'y' * 500)])
    p = tmp_path / 'trunc_res.package'
    # keep header + index but cut the payload area
    p.write_bytes(good[: len(good) - 100])
    with pytest.raises(dbpf.PackageError):
        dbpf.PackageReader(p)


def test_refpack_entry_decompresses(tmp_path):
    import zlib
    payload = b'print("hello sims")\n' * 50
    # build a package whose entry is stored as zlib (demo builder uses zlib),
    # and additionally verify the RefPack path via a hand-built entry
    pkg = tmp_path / 'z.package'
    pkg.write_bytes(_build_package([(0x073FAA07, 0, 0x1234, payload)]))
    reader = dbpf.PackageReader(pkg)
    assert reader.resource_bytes(reader.entries[0]) == payload


def test_refpack_entry_roundtrip(tmp_path):
    """A package whose resource is stored as an unflagged RefPack stream must decode."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from refpack_helper import encode
    import struct
    from modbroom import dbpf

    payload = b'print("hello from a genuinly-typed script")\n' * 40
    refpacked = encode(payload)

    # hand-build a DBPF containing one RefPack resource (stored unflagged, magic 0x10 0xFB)
    import io, zlib as _z
    buf = io.BytesIO()
    buf.write(b'DBPF')
    buf.write(struct.pack('<2I', 2, 1))
    buf.write(struct.pack('<6I', 0, 0, 0, 0, 0, 0))
    buf.write(struct.pack('<I', 0))  # index count placeholder
    buf.write(struct.pack('<I', 0))  # short index offset placeholder
    buf.write(struct.pack('<I', 0))  # index size placeholder
    buf.write(b'\x00' * 12)
    buf.write(struct.pack('<I', 3))
    buf.write(struct.pack('<Q', 0))
    buf.write(b'\x00' * 24)
    offset = buf.tell()
    buf.write(refpacked)
    index_offset = buf.tell()
    idx = io.BytesIO()
    idx.write(struct.pack('<I', 0))  # no constant groups
    idx.write(struct.pack('<I', 0x015A1849))
    idx.write(struct.pack('<I', 0))          # group
    idx.write(struct.pack('<I', 0))          # instance hi
    idx.write(struct.pack('<I', 0x12345678)) # instance lo
    idx.write(struct.pack('<I', offset))
    idx.write(struct.pack('<I', (len(refpacked) & 0x7FFFFFFF) | 0x80000000))
    idx.write(struct.pack('<I', len(payload)))
    idx.write(struct.pack('<H', 0))          # COMP_UNCOMPRESSED (payload IS the stream)
    idx.write(struct.pack('<H', 1))
    index_bytes = idx.getvalue()
    buf.write(index_bytes)
    data = bytearray(buf.getvalue())
    struct.pack_into('<I', data, 36, 1)
    struct.pack_into('<I', data, 40, 0)
    struct.pack_into('<I', data, 44, len(index_bytes))
    struct.pack_into('<Q', data, 68, index_offset)

    pkg = tmp_path / 'refpack.package'
    pkg.write_bytes(bytes(data))
    reader = dbpf.PackageReader(pkg)
    assert reader.resource_bytes(reader.entries[0]) == payload
