"""Ground Zeroes QAR payload crypto. Port of GzsTool v0.2 Encryption.cs."""

from __future__ import annotations

import struct


def _i32(x: int) -> int:
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x


def _u32(x: int) -> int:
    return x & 0xFFFFFFFF


def _u64(high: int, low: int) -> int:
    return ((_u32(high) << 32) + _u32(low)) & 0xFFFFFFFFFFFFFFFF


def deencrypt_qar(data: bytes | bytearray, offset: int) -> bytearray:
    """XOR stream keyed by 16-byte block index. In-place on a copy."""
    p = bytearray(data)
    block_count = len(p) // 8
    v5 = 8 * (block_count + 2 * offset)
    low = _i32(101436752 * offset + 12679594)
    buffer_offset = 0
    for _ in range(block_count):
        ulow = low & 0xFFFFFFFFFFFFFFFF
        p[buffer_offset] ^= ((ulow - 12679594) & 0xFFFFFFFFFFFFFFFF) >> 16 & 0xFF
        p[buffer_offset + 1] ^= ((ulow - 6339797) & 0xFFFFFFFFFFFFFFFF) >> 16 & 0xFF
        p[buffer_offset + 2] ^= (ulow >> 16) & 0xFF
        p[buffer_offset + 3] ^= ((ulow + 6339797) & 0xFFFFFFFFFFFFFFFF) >> 16 & 0xFF
        p[buffer_offset + 4] ^= ((ulow + 12679594) & 0xFFFFFFFFFFFFFFFF) >> 16 & 0xFF
        p[buffer_offset + 5] ^= ((ulow + 19019391) & 0xFFFFFFFFFFFFFFFF) >> 16 & 0xFF
        p[buffer_offset + 6] ^= ((ulow + 25359188) & 0xFFFFFFFFFFFFFFFF) >> 16 & 0xFF
        p[buffer_offset + 7] ^= ((ulow + 31698985) & 0xFFFFFFFFFFFFFFFF) >> 16 & 0xFF
        buffer_offset += 8
        low = _i32(low + 50718376)
    remaining = len(p) & 7
    v10 = _u32(6339797 * v5)
    v11 = 0
    for _ in range(remaining):
        pair = _u64(v11, v10)
        p[buffer_offset] ^= (pair >> 16) & 0xFF
        v11 = _u32((pair + 6339797) >> 32)
        v10 = _u32(v10 + 6339797)
        buffer_offset += 1
    return p


def deencrypt(data: bytes | bytearray, key: int) -> bytearray:
    """Second-stage decrypt when payload starts with 0xA0F8EFE6."""
    src = bytes(data)
    n = len(src)
    out = bytearray(n)
    offset = 0
    v5 = _u32(key | (((key ^ 0xFFFFCDEC) & 0xFFFFFFFF) << 16))
    i = _u32(69069 * key)
    remaining = n
    while remaining >= 64:
        for _ in range(16):
            block = v5 ^ struct.unpack_from("<I", src, offset)[0]
            struct.pack_into("<I", out, offset, _u32(block))
            offset += 4
            v5 = _u32(3 * (i + 23023 * v5))
        remaining -= 64
    while remaining >= 16:
        b0, b1, b2, b3 = struct.unpack_from("<IIII", src, offset)
        v9 = _u32(3 * (i + 23023 * v5))
        struct.pack_into("<I", out, offset, _u32(v5 ^ b0))
        v11 = _u32(3 * (i + 23023 * v9))
        struct.pack_into("<I", out, offset + 4, _u32(v9 ^ b1))
        struct.pack_into("<I", out, offset + 8, _u32(v11 ^ b2))
        v12 = _u32(3 * (i + 23023 * v11))
        struct.pack_into("<I", out, offset + 12, _u32(v12 ^ b3))
        remaining -= 16
        offset += 16
        v5 = _u32(3 * (i + 23023 * v12))
    while remaining >= 4:
        block = v5 ^ struct.unpack_from("<I", src, offset)[0]
        struct.pack_into("<I", out, offset, _u32(block))
        remaining -= 4
        offset += 4
        v5 = _u32(3 * (i + 23023 * v5))
    if remaining:
        out[offset:] = src[offset:]
    return out


KEY_MAGIC = 0xA0F8EFE6


def decrypt_g0s_payload(raw: bytes, block_offset: int) -> bytes:
    data = deencrypt_qar(raw, block_offset)
    if len(data) >= 8 and struct.unpack_from("<I", data, 0)[0] == KEY_MAGIC:
        key = struct.unpack_from("<I", data, 4)[0]
        data = deencrypt(data[8:], key)
    return bytes(data)
