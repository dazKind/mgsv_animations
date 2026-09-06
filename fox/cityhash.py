"""Google CityHash64. Needed for Fox PathCode / GzsTool v0.2 hashes."""

from __future__ import annotations

import struct

K0 = 0xC3A5C85C97CB3127
K1 = 0xB492B66FBE98F273
K2 = 0x9AE16A3B2F90404F
K3 = 0xC949D7C7509E6557
K_MUL = 0x9DDFEA08EB382D69
MASK64 = 0xFFFFFFFFFFFFFFFF


def _u64(x: int) -> int:
    return x & MASK64


def _fetch64(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def _fetch32(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _rotate(val: int, shift: int) -> int:
    val = _u64(val)
    if shift == 0:
        return val
    return _u64((val >> shift) | (val << (64 - shift)))


def _shift_mix(val: int) -> int:
    val = _u64(val)
    return _u64(val ^ (val >> 47))


def _hash128to64(low: int, high: int) -> int:
    a = _u64((_u64(low) ^ _u64(high)) * K_MUL)
    a ^= a >> 47
    b = _u64((_u64(high) ^ a) * K_MUL)
    b ^= b >> 47
    return _u64(b * K_MUL)


def _hash_len_16(u: int, v: int, mul: int | None = None) -> int:
    if mul is None:
        return _hash128to64(u, v)
    a = _u64((_u64(u) ^ _u64(v)) * mul)
    a ^= a >> 47
    b = _u64((_u64(v) ^ a) * mul)
    b ^= b >> 47
    return _u64(b * mul)


def _hash_len_0to16(s: bytes) -> int:
    length = len(s)
    if length >= 8:
        mul = K2 + length * 2
        a = _fetch64(s) + K2
        b = _fetch64(s, length - 8)
        c = _u64(_rotate(b, 37) * mul + a)
        d = _u64((_rotate(a, 25) + b) * mul)
        return _hash_len_16(c, d, mul)
    if length >= 4:
        mul = K2 + length * 2
        a = _fetch32(s)
        return _hash_len_16(length + (a << 3), _fetch32(s, length - 4), mul)
    if length > 0:
        a = s[0]
        b = s[length >> 1]
        c = s[length - 1]
        y = a + (b << 8)
        z = length + (c << 2)
        return _u64(_shift_mix(_u64(y * K2) ^ _u64(z * K3)) * K2)
    return K2


def _hash_len_17to32(s: bytes) -> int:
    length = len(s)
    mul = K2 + length * 2
    a = _u64(_fetch64(s) * K1)
    b = _fetch64(s, 8)
    c = _u64(_fetch64(s, length - 8) * mul)
    d = _u64(_fetch64(s, length - 16) * K2)
    return _hash_len_16(
        _u64(_rotate(_u64(a - b), 43) + _rotate(c, 30) + d),
        _u64(a + _rotate(_u64(b ^ K3), 20) - c + length),
        mul,
    )


def _weak_hash_len32_with_seeds(s: bytes, offset: int, a: int, b: int) -> tuple[int, int]:
    w = _fetch64(s, offset)
    x = _fetch64(s, offset + 8)
    y = _fetch64(s, offset + 16)
    z = _fetch64(s, offset + 24)
    a = _u64(a + w)
    b = _rotate(_u64(b + a + z), 21)
    c = a
    a = _u64(a + x)
    a = _u64(a + y)
    b = _u64(b + _rotate(a, 44))
    return _u64(a + z), _u64(b + c)


def _hash_len_33to64(s: bytes) -> int:
    length = len(s)
    mul = K2 + length * 2
    a = _u64(_fetch64(s) * K2)
    b = _fetch64(s, 8)
    c = _fetch64(s, length - 24)
    d = _fetch64(s, length - 32)
    e = _u64(_fetch64(s, 16) * K2)
    f = _u64(_fetch64(s, 24) * 9)
    g = _fetch64(s, length - 8)
    h = _u64(_fetch64(s, length - 16) * mul)
    u = _u64(_rotate(_u64(a + g), 43) + (b + _rotate(c, 30)) * 9 + f)
    v = _u64(_u64(a + g) ^ d + c + 1)
    w = _u64(_u64(b + _rotate(c, 30)) * 9 + _u64(_shift_mix(_u64(u * mul) ^ v) * mul))
    x = _u64(e + f)
    y = _rotate(_u64(e + h), 42)
    z = _u64(d + g)
    a = _u64(_shift_mix(_u64((v + w) * mul) + z) * mul + x)
    b = _u64(_shift_mix(_u64(x + y) * mul + a + z) * mul)
    return _hash_len_16(a, b, mul)


def cityhash64(s: bytes) -> int:
    length = len(s)
    if length <= 16:
        return _hash_len_0to16(s)
    if length <= 32:
        return _hash_len_17to32(s)
    if length <= 64:
        return _hash_len_33to64(s)

    x = _fetch64(s, length - 40)
    y = _u64(_fetch64(s, length - 16) + _fetch64(s, length - 56))
    z = _hash_len_16(_fetch64(s, length - 48) + length, _fetch64(s, length - 24))
    v = _weak_hash_len32_with_seeds(s, length - 64, length, z)
    w = _weak_hash_len32_with_seeds(s, length - 32, _u64(y + K1), x)
    x = _u64(x * K1 + _fetch64(s))
    offset = 0
    remaining = (length - 1) & ~63
    while remaining > 0:
        x = _u64(_rotate(_u64(x + y + v[0] + _fetch64(s, offset + 8)), 37) * K1)
        y = _u64(_rotate(_u64(y + v[1] + _fetch64(s, offset + 48)), 42) * K1)
        x ^= w[1]
        y = _u64(y + v[0] + _fetch64(s, offset + 40))
        z = _u64(_rotate(_u64(z + w[0]), 33) * K1)
        v = _weak_hash_len32_with_seeds(s, offset, _u64(v[1] * K1), _u64(x + w[0]))
        w = _weak_hash_len32_with_seeds(
            s, offset + 32, _u64(z + w[1]), _u64(y + _fetch64(s, offset + 16))
        )
        x, z = z, x
        offset += 64
        remaining -= 64
    return _hash_len_16(
        _u64(_hash_len_16(v[0], w[0]) + _shift_mix(y) * K1 + z),
        _u64(_hash_len_16(v[1], w[1]) + x),
    )


def cityhash64_with_seeds(s: bytes, seed0: int, seed1: int) -> int:
    return _hash_len_16(_u64(cityhash64(s) - seed0), seed1)
