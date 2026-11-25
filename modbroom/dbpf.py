"""DBPF (.package) reader for The Sims 4.

Parses the DBPF 2.x format: header, resource index, and compressed resources.
Dependency-free (stdlib only) so the app can ship as a single-file Windows exe.
"""

import struct
import zlib
from pathlib import Path

from .refpack import decompress as _refpack_decompress, COMP_REFPACK, RefPackError
from .log import get_logger

log = get_logger('dbpf')

COMP_UNCOMPRESSED = 0x0000
COMP_ZLIB = 0x5A42          # 'ZB' little-endian
COMP_DELETED = 0xFFE0
COMP_STREAMABLE = 0xFFFE
COMP_INTERNAL = 0xFFFF

# Resource type ids -> human labels (subset of common Sims 4 types)
RESOURCE_TYPES = {
    0x015A1849: "Geometry (mesh)",
    0x01661233: "Model (object)",
    0x02D5DF13: "Bone Pose",
    0x0333406C: "Font Config",
    0x034AEECB: "CAS Part",
    0x062E94D3: "Combined Binary Tuning",
    0x06360F72: "Tuning",
    0x069C5B1F: "Material Definition",
    0x06DF1A66: "MTX Catalog",
    0x00B2D882: "DST Image (texture)",
    0x073FAA07: "Tuning (XML)",
    0x075A4A0B: "Collection (object)",
    0x015A1849: "Geometry (mesh)",
    0x545AC67A: "Sim Data",
    0x03A1E944: "Path",
    0x05B282D4: "Body Part Thumbnail",
    0x025ED6F4: "Sim Info",
    0x034C9F23: "Lot",
}


def type_label(type_id: int) -> str:
    return RESOURCE_TYPES.get(type_id, "Type 0x%08X" % type_id)


class PackageError(Exception):
    pass


class ResourceEntry:
    __slots__ = ("type_id", "group_id", "instance_hi", "instance_lo",
                 "offset", "compressed_size", "uncompressed_size", "compression")

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    @property
    def instance_id(self) -> int:
        return (self.instance_hi << 32) | self.instance_lo

    @property
    def tgi(self):
        return (self.type_id, self.group_id, self.instance_id)

    def to_dict(self):
        return {
            "type_id": self.type_id,
            "type_hex": "0x%08X" % self.type_id,
            "type_label": type_label(self.type_id),
            "group_hex": "0x%08X" % self.group_id,
            "instance_id": self.instance_id,
            "instance_hex": "0x%016X" % self.instance_id,
            "offset": self.offset,
            "compressed_size": self.compressed_size,
            "uncompressed_size": self.uncompressed_size,
            "compression": self.compression,
        }


def _header_candidates(header):
    """Possible (count, offset, size) triples for a DBPF header.

    Maxis TS4 packages use the DBPF 2.1 layout, but older tools (and some
    Sims 3-era packages that still load in TS4) use the 1.x layout. Trying both
    and validating against the file size avoids rejecting a good package just
    because its author wrote a different header variant.
    """
    u32 = lambda off: struct.unpack_from("<I", header, off)[0]
    u64 = lambda off: struct.unpack_from("<Q", header, off)[0]

    short = u32(0x28)
    long_ = u64(0x40)
    two = {
        'layout': 'DBPF 2.x', 'count': u32(0x24),
        'offset': long_ or short, 'size': u32(0x2C),
        'short': short, 'long': long_,
    }
    off1 = u32(0x20)
    one = {
        'layout': 'DBPF 1.x', 'count': u32(0x1C),
        'offset': off1, 'size': u32(0x24),
        'short': off1, 'long': 0,
    }
    return [two, one]


def _candidate_ok(c, file_size):
    """A candidate that points inside the file with a believable entry count."""
    off = c['offset']
    if not off or off + 4 > file_size:
        return False
    if c['count'] > 500000:
        return False
    if c['size'] and off + c['size'] > file_size:
        return False
    return True


class PackageReader:
    """Read a .package file's index and (on demand) decompressed resources."""

    def __init__(self, path):
        self.path = str(path)
        self.entries = []
        self.major = 0
        self.minor = 0
        self._size = 0
        self.integrity_notes = []
        self._index_count = 0
        self._read_header_and_index()

    def _read_header_and_index(self):
        with open(self.path, "rb") as fh:
            header = fh.read(96)
            if len(header) < 96:
                raise PackageError("File too small to be a DBPF package")
            if header[:4] != b"DBPF":
                raise PackageError("Not a DBPF package (missing 'DBPF' magic)")
            self.major, self.minor = struct.unpack_from("<2I", header, 4)
            fh.seek(0, 2)
            self._size = fh.tell()

            candidates = _header_candidates(header)
            for c in candidates:
                log.debug('header candidate %s in %s: count=%d offset=%d size=%d (short=%d long=%d)',
                          c['layout'], Path(self.path).name, c['count'], c['offset'],
                          c['size'], c['short'], c['long'])
            valid = [c for c in candidates if _candidate_ok(c, self._size)]
            chosen = valid[0] if valid else next((c for c in candidates if c['offset']), candidates[0])
            self.layout = chosen['layout']
            index_count = chosen['count']
            index_offset = chosen['offset']
            index_size = chosen['size']
            self._index_count = index_count

            if index_offset == 0:
                detail = ', '.join('%s short=%d long=%d count=%d size=%d'
                                   % (c['layout'], c['short'], c['long'], c['count'], c['size'])
                                   for c in candidates)
                info = describe_header(self.path)
                log.warning('no index offset in %s — %s; header words=%s',
                            self.path, detail, info.get('raw_words'))
                raise PackageError('No index offset present (%s; DBPF %d.%d)'
                                   % (detail, self.major, self.minor))

            log.debug('using %s layout for %s: index@%d count=%d size=%d',
                      self.layout, Path(self.path).name, index_offset, index_count, index_size)
            fh.seek(index_offset)
            expected = index_size if index_size else (self._size - index_offset)
            index_bytes = fh.read(expected)
            if index_size and len(index_bytes) < index_size:
                raise PackageError(
                    "Index extends past end of file (expected %d bytes, got %d) — file is truncated" % (index_size, len(index_bytes)))
            if index_offset >= self._size:
                raise PackageError("Index offset beyond end of file — truncated package")
            self._parse_index(index_bytes, index_count)
            if len(self.entries) < index_count:
                self.integrity_notes.append("Index truncated: parsed %d of %d entries" % (len(self.entries), index_count))

    def _parse_index(self, data, index_count):
        if len(data) < 4:
            raise PackageError("Index truncated")
        pos = 0
        flags = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        const_type = bool(flags & 0x1)
        const_group = bool(flags & 0x2)
        const_inst_hi = bool(flags & 0x4)

        def take_u32():
            nonlocal pos
            if pos + 4 > len(data):
                raise PackageError("Index truncated while reading entry")
            v = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            return v

        c_type = take_u32() if const_type else None
        c_group = take_u32() if const_group else None
        c_inst_hi = take_u32() if const_inst_hi else None

        for _ in range(index_count):
            try:
                type_id = c_type if const_type else take_u32()
                group_id = c_group if const_group else take_u32()
                inst_hi = c_inst_hi if const_inst_hi else take_u32()
                inst_lo = take_u32()
                offset = take_u32()
                size_flag = take_u32()
                compressed_size = size_flag & 0x7FFFFFFF
                extended = bool(size_flag & 0x80000000)
                uncompressed_size = take_u32()
                compression = COMP_UNCOMPRESSED
                if extended:
                    if pos + 4 > len(data):
                        raise PackageError("Index truncated in extended entry")
                    compression = struct.unpack_from("<H", data, pos)[0]
                    pos += 4  # compression type (2) + committed flag (2)
            except PackageError:
                break
            self.entries.append(ResourceEntry(
                type_id=type_id, group_id=group_id,
                instance_hi=inst_hi, instance_lo=inst_lo,
                offset=offset, compressed_size=compressed_size,
                uncompressed_size=uncompressed_size,
                compression=compression,
            ))

    def integrity_errors(self):
        """Entries that point outside the file.

        Deleted/tombstone records legitimately carry sentinel offsets and
        sizes (0xFFFFFFFF / 0x7FFFFFFF). Tools such as s4pe and Sims 4 Studio
        leave them in packages that load perfectly in the game, so they must
        not be reported as truncated downloads.
        """
        errors = list(getattr(self, 'integrity_notes', []))
        for e in self.entries:
            if e.compression in (COMP_DELETED, COMP_INTERNAL):
                continue
            if e.offset in (0xFFFFFFFF, 0xFFFF) or e.compressed_size in (0xFFFFFFFF, 0x7FFFFFFF):
                continue
            if e.offset + e.compressed_size > self._size:
                errors.append("Resource 0x%016X extends past end of file (truncated download?)" % e.instance_id)
        if not self.entries and self._index_count:
            errors.append("Index declares %d entries but none could be parsed" % self._index_count)
        return errors

    def resource_bytes(self, entry):
        with open(self.path, "rb") as fh:
            fh.seek(entry.offset)
            raw = fh.read(entry.compressed_size)
        if entry.compression == COMP_ZLIB:
            try:
                return zlib.decompress(raw)
            except zlib.error:
                # TS4 zlib streams sometimes carry a small prefix before the zlib stream
                for skip in (9, 2, 1, 16):
                    try:
                        return zlib.decompress(raw[skip:])
                    except zlib.error:
                        continue
                raise PackageError("zlib decompression failed for 0x%016X" % entry.instance_id)
        if entry.compression == COMP_DELETED:
            return b""
        # RefPack stream: explicitly tagged, or an EA RefPack payload the game
        # stored unflagged. Signature wins over the compression flag. Fail loudly
        # rather than hand compressed bytes back to the caller.
        if entry.compression == COMP_REFPACK or raw[:2] == b"\x10\xFB":
            try:
                return _refpack_decompress(raw, entry.uncompressed_size)
            except RefPackError as exc:
                raise PackageError("RefPack decompression failed for 0x%016X: %s" % (entry.instance_id, exc))
        if entry.compression in (COMP_UNCOMPRESSED, COMP_INTERNAL):
            return raw
        return raw

    def tgi_set(self):
        return {e.tgi for e in self.entries}


def describe_header(path):
    """Raw DBPF header fields, for diagnosing packages with unusual layouts."""
    with open(path, 'rb') as fh:
        header = fh.read(96)
    if len(header) < 96:
        return {'error': 'header is %d bytes (expected 96)' % len(header)}
    words = struct.unpack_from('<24I', header, 0)
    return {
        'magic': header[:4].decode('latin-1'),
        'major': words[1],
        'minor': words[2],
        'index_count_0x1C': words[7],
        'offset_0x20': words[8],
        'index_count_0x24': words[9],
        'short_offset_0x28': words[10],
        'index_size_0x2C': words[11],
        'dword_0x3C': words[15],
        'long_offset_0x40': struct.unpack_from('<Q', header, 64)[0],
        'raw_words': ['0x%08X' % w for w in words],
    }


def looks_like_package(path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(4) == b"DBPF"
    except OSError:
        return False
