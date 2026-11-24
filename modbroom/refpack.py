"""EA RefPack (a.k.a. QFS / FB10) decompression.

Spec reference: OpenReliant project, docs/formats/refpack.md, which documents the
command encodings used by EA's own games. The format:

    offset  size  field
    0       1     flags   (0x10 in every stream The Sims 4 writes)
    1       1     0xFB    ("RefPack" magic; hence "FB10")
    2       3 or 4  compressed size, big-endian, present only if flag bit 0x01
    ...     3 or 4  decompressed size, big-endian

Flags: bit 0x01 -> a compressed size precedes the decompressed size;
       bit 0x80 -> sizes are 4 bytes instead of 3.
Sizes are big-endian.

Commands (first byte selects the encoding):

    0x00-0x7F  2 bytes  lit=b0&3                    len=((b0>>2)&7)+3     dist=((b0&0x60)<<3)+b1+1
    0x80-0xBF  3 bytes  lit=(b1>>6)&3               len=(b0&0x3F)+4       dist=((b1&0x3F)<<8)+b2+1
    0xC0-0xDF  4 bytes  lit=b0&3                    len=((b0&0x0C)<<6)+b3+5
                                                        dist=((b0&0x10)<<12)+(b1<<8)+b2+1
    0xE0-0xFB  1 byte   lit=((b0&0x1F)<<2)+4        no match
    0xFC-0xFF  1 byte   lit=b0&3                    end of stream

A match may overlap the bytes it produces, so the copy is byte-by-byte.
"""

MAGIC_SECOND = 0xFB
MAX_WINDOW = 131072  # matches reach back at most this far
MAX_OUTPUT = 64 * 1024 * 1024  # sanity bound against corrupt headers

COMP_REFPACK = 0x0010  # compression id used by DBPF for RefPack payloads


class RefPackError(Exception):
    pass


def looks_like_refpack(data):
    return len(data) >= 5 and data[1] == MAGIC_SECOND and (data[0] & 0x3E) == 0x10


def decompress(data, expected_size=None):
    if len(data) < 5:
        raise RefPackError('RefPack stream too short (%d bytes)' % len(data))
    flags = data[0]
    if data[1] != MAGIC_SECOND:
        raise RefPackError('Not a RefPack stream (second byte 0x%02X, expected 0xFB)' % data[1])

    size_len = 4 if (flags & 0x80) else 3
    has_csize = bool(flags & 0x01)
    pos = 2
    if has_csize:
        if pos + size_len > len(data):
            raise RefPackError('Truncated compressed-size field')
        pos += size_len  # compressed size is not needed; we decode by output size
    if pos + size_len > len(data):
        raise RefPackError('Truncated decompressed-size field')
    dsize = int.from_bytes(data[pos:pos + size_len], 'big')
    pos += size_len

    if expected_size is not None and dsize != expected_size:
        # Not fatal: the header is authoritative, but callers often know better.
        expected_size = None
    if dsize > MAX_OUTPUT:
        raise RefPackError('Refusing to decompress %d bytes (limit %d)' % (dsize, MAX_OUTPUT))

    out = bytearray()
    src_end = len(data)
    while len(out) < dsize:
        if pos >= src_end:
            raise RefPackError('Stream ended before the declared decompressed size')
        b0 = data[pos]; pos += 1

        if b0 <= 0x7F:
            lit = b0 & 0x03
            length = ((b0 >> 2) & 0x07) + 3
            if pos >= src_end:
                raise RefPackError('Truncated 2-byte command')
            dist = (((b0 & 0x60) << 3) | data[pos]) + 1
            pos += 1
        elif b0 <= 0xBF:
            if pos + 2 > src_end:
                raise RefPackError('Truncated 3-byte command')
            lit = (data[pos] >> 6) & 0x03
            length = (b0 & 0x3F) + 4
            dist = (((data[pos] & 0x3F) << 8) | data[pos + 1]) + 1
            pos += 2
        elif b0 <= 0xDF:
            if pos + 3 > src_end:
                raise RefPackError('Truncated 4-byte command')
            lit = b0 & 0x03
            length = (((b0 & 0x0C) << 6) | data[pos + 2]) + 5
            dist = (((b0 & 0x10) << 12) | (data[pos] << 8) | data[pos + 1]) + 1
            pos += 3
        elif b0 <= 0xFB:
            lit = ((b0 & 0x1F) << 2) + 4
            length = 0
            dist = 0
        else:  # 0xFC-0xFF: terminator
            lit = b0 & 0x03
            if lit:
                _copy_literals(data, pos, out, lit, src_end)
                pos += lit
            break

        if lit:
            _copy_literals(data, pos, out, lit, src_end)
            pos += lit
        if length:
            if dist > len(out):
                raise RefPackError('Match distance %d exceeds produced output %d' % (dist, len(out)))
            start = len(out) - dist
            for i in range(length):
                out.append(out[start + i])
        if len(out) > dsize:
            raise RefPackError('Stream produced more bytes than declared (%d > %d)' % (len(out), dsize))

    if len(out) != dsize:
        raise RefPackError('Produced %d bytes, expected %d' % (len(out), dsize))
    return bytes(out)


def _copy_literals(data, pos, out, count, src_end):
    if pos + count > src_end:
        raise RefPackError('Literal run overruns end of stream')
    out += data[pos:pos + count]
