"""Greedy RefPack encoder, written independently of the decoder, for round-trip tests.

Command byte layout (see refpack.py for the decoder side). Pending literals are
emitted as a run of 4-byte 0xE0 commands before a match command, and the final
0-3 literals are carried in the match command's low 2 bits (or the 0xFC|n EOF
byte). Match command bytes are followed immediately by their literal bytes.
"""


def encode(data: bytes) -> bytes:
    if len(data) >= (1 << 24):
        raise ValueError('payload too large for 3-byte size')
    out = bytearray(b'\x10\xFB' + len(data).to_bytes(3, 'big'))
    n = len(data)
    i = 0
    lit_start = 0

    def flush_full_literal_runs():
        nonlocal lit_start, out
        total = i - lit_start
        pos = lit_start
        full = total & ~3
        end = pos + full
        while pos < end:
            take = min(112, end - pos)
            take -= take % 4
            out.append(0xE0 | ((take // 4) - 1))
            out += data[pos:pos + take]
            pos += take
        lit_start = pos

    while i < n:
        best_len = 0
        best_dist = 0
        start = max(0, i - 131071)
        max_len = min(1028, n - i)
        j = start
        while j < i:
            l = 0
            limit = max_len
            while l < limit and data[j + l] == data[i + l]:
                l += 1
            if l > best_len:
                best_len, best_dist = l, i - j
                if l >= max_len:
                    break
            j += 1
        if best_len >= 4:
            flush_full_literal_runs()
            lit = i - lit_start
            d = best_dist - 1  # encoded distance is dist-1
            l = best_len
            if l <= 10 and d <= 1023:
                out.append(((l - 3) << 2) | lit | (((d >> 8) & 0x3) << 5))
                out.append(d & 0xFF)
            elif l <= 67 and d <= 16383:
                out.append(0x80 | (l - 4))
                out.append(((lit & 0x3) << 6) | ((d >> 8) & 0x3F))
                out.append(d & 0xFF)
            elif d <= 131071:
                out.append(0xC0 | (lit & 0x3) | (((l - 5) >> 6) & 0x0C) | (((d >> 16) & 0x1) << 4))
                out.append((d >> 8) & 0xFF)
                out.append(d & 0xFF)
                out.append((l - 5) & 0xFF)
            else:
                raise AssertionError('match out of encodable range')
            if lit:
                out += data[lit_start:i]
            i += l
            lit_start = i
        else:
            i += 1
        if i - lit_start >= 448:
            flush_full_literal_runs()

    flush_full_literal_runs()
    rem = i - lit_start
    out.append(0xFC | rem)
    if rem:
        out += data[lit_start:i]
    return bytes(out)
