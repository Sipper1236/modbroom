import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from refpack_helper import encode  # noqa: E402

from modbroom import refpack  # noqa: E402


def test_header_roundtrip_empty():
    assert refpack.decompress(encode(b'')) == b''


def test_header_roundtrip_short():
    assert refpack.decompress(encode(b'abc')) == b'abc'


@pytest.mark.parametrize('size', [1, 3, 4, 5, 63, 64, 255, 256, 1024, 4097])
def test_roundtrip_sizes(size):
    import random
    rng = random.Random(1234 + size)
    data = bytes(rng.randrange(256) for _ in range(size))
    assert refpack.decompress(encode(data)) == data


def test_roundtrip_repetitive():
    data = b'The Sims 4 modding community ' * 400
    assert refpack.decompress(encode(data)) == data


def test_roundtrip_binary_with_runs():
    data = bytes(range(256)) * 8 + b'\x00' * 1000
    assert refpack.decompress(encode(data)) == data


def test_known_vector_literals_only():
    # 5 literal bytes, no matches: header(5) + 0xE0-style command + EOF.
    payload = b'hello'
    stream = b'\x10\xFB' + len(payload).to_bytes(3, 'big') + b'\xE0\x00' + payload[:0] + b''
    # build a valid stream manually: one 4-literal command for 'hell', then EOF with 1 literal
    stream = b'\x10\xFB' + b'\x00\x00\x05' + b'\xE0' + b'hell' + b'\xFD\x6F'
    assert refpack.decompress(stream) == payload


def test_rejects_bad_magic():
    with pytest.raises(refpack.RefPackError):
        refpack.decompress(b'\x10\x00\x00\x00\x00')


def test_rejects_truncated_stream():
    stream = encode(b'a' * 500)
    with pytest.raises(refpack.RefPackError):
        refpack.decompress(stream[: len(stream) - 2])


def test_rejects_oversize_declared():
    stream = b'\x90\xFB' + (200_000_000).to_bytes(4, 'big') + b'\xFC'
    with pytest.raises(refpack.RefPackError):
        refpack.decompress(stream)


def test_match_overlapping_runs():
    # distance 1, long match: decoder must copy byte-by-byte
    data = b'\x7f' * 1000
    assert refpack.decompress(encode(data)) == data


def test_looks_like_refpack():
    assert refpack.looks_like_refpack(b'\x10\xFB\x00\x00\x01body')
    assert not refpack.looks_like_refpack(b'\x10\xFA\x00\x00\x01body')
    assert not refpack.looks_like_refpack(b'')
