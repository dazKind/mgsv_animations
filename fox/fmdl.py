"""FMDL skeleton. Bone defs + string table. Mesh skipped."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

FEATURE_BONE_DEFS = 0
FEATURE_STRING_HEADER = 12
BUFFER_STRINGS = 3
BONE_DEF_SIZE = 48


@dataclass
class Bone:
    name: str
    parent: int
    local_pos: tuple[float, float, float]
    world_pos: tuple[float, float, float]


@dataclass
class Skeleton:
    path: Path
    version: float
    bones: list[Bone]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def _i16(data: bytes, off: int) -> int:
    return struct.unpack_from("<h", data, off)[0]


def _f32(data: bytes, off: int) -> float:
    return struct.unpack_from("<f", data, off)[0]


def _feature_count(header: bytes, off: int) -> int:
    overflow = header[off + 1]
    count = _u16(header, off + 2)
    return overflow * 0x10000 + count


def read_skeleton(path: str | Path) -> Skeleton:
    path = Path(path)
    data = path.read_bytes()
    if data[:4] != b"FMDL":
        raise ValueError("not an fmdl")
    version = _f32(data, 4)
    file_desc = _u32(data, 8)
    feature_types = _u32(data, 16)
    buffer_types = _u32(data, 24)
    feature_count = _u32(data, 32)
    buffer_count = _u32(data, 36)
    features_data = _u32(data, 40)
    buffers_data = _u32(data, 48)

    feat_index = [-1] * 23
    real = 0
    bit = 1
    for i in range(23):
        if feature_types & bit:
            feat_index[i] = real
            real += 1
        bit <<= 1

    buf_index = [-1] * 4
    real = 0
    bit = 1
    for i in range(4):
        if buffer_types & bit:
            buf_index[i] = real
            real += 1
        bit <<= 1

    feat_headers = data[file_desc : file_desc + feature_count * 8]
    buf_headers = data[file_desc + feature_count * 8 : file_desc + feature_count * 8 + buffer_count * 12]

    strings: list[str] = []
    if feat_index[FEATURE_STRING_HEADER] != -1 and buf_index[BUFFER_STRINGS] != -1:
        sh = feat_index[FEATURE_STRING_HEADER] * 8
        str_count = _feature_count(feat_headers, sh)
        str_off = features_data + _u32(feat_headers, sh + 4)
        bh = buf_index[BUFFER_STRINGS] * 12
        str_buf_off = buffers_data + _u32(buf_headers, bh + 4)
        for i in range(str_count):
            rec = str_off + i * 8
            length = _u16(data, rec + 2)
            rel = _u32(data, rec + 4)
            raw = data[str_buf_off + rel : str_buf_off + rel + length]
            strings.append(raw.split(b"\x00", 1)[0].decode("ascii", errors="replace"))

    bones: list[Bone] = []
    if feat_index[FEATURE_BONE_DEFS] != -1:
        bh = feat_index[FEATURE_BONE_DEFS] * 8
        count = _feature_count(feat_headers, bh)
        off = features_data + _u32(feat_headers, bh + 4)
        for i in range(count):
            rec = off + i * BONE_DEF_SIZE
            name_index = _u16(data, rec)
            parent = _i16(data, rec + 2)
            lx, ly, lz, _lw = struct.unpack_from("<ffff", data, rec + 16)
            wx, wy, wz, _ww = struct.unpack_from("<ffff", data, rec + 32)
            name = strings[name_index] if name_index < len(strings) else f"bone_{i}"
            bones.append(
                Bone(
                    name=name,
                    parent=parent,
                    local_pos=(lx, ly, lz),
                    world_pos=(wx, wy, wz),
                )
            )
    return Skeleton(path=path, version=version, bones=bones)
