"""GANI (FoxData motion clip). Layout from kapuragu FoxEngineTemplates."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

NODE_MOTION = 143688520
NODE_SKEL = 1889896775
NODE_SKL_LIST = 2447659851
NODE_MTP_LIST = 3937479969
NODE_MTP_PARENT_LIST = 4042487769
NODE_MTP = 494270195
NODE_EVP = 371357229
NODE_UNIT = 3337172921
NODE_SHADER = 2250865118
NODE_ROOT = 3933341002

SEG_QUAT = 0
SEG_FLOAT = 1
SEG_VEC2 = 2
SEG_VEC3 = 3
SEG_VEC4 = 4
SEG_QUAT_DIFF = 5
SEG_VEC_DIFF = 6

FLAG_LOOP = 0x1
FLAG_HERMITE = 0x2
FLAG_STATIC = 0x4

KNOWN_NODES = {
    NODE_ROOT: "ROOT",
    NODE_MOTION: "MOTION",
    NODE_SKEL: "SKEL",
    NODE_SKL_LIST: "SKL_LIST",
    NODE_MTP_LIST: "MTP_LIST",
    NODE_MTP_PARENT_LIST: "MTP_PARENT_LIST",
    NODE_MTP: "MTP",
    NODE_EVP: "EVP",
    NODE_UNIT: "UNIT",
    NODE_SHADER: "SHADER",
    283103795: "ROTATE",
    2236677358: "SCALE",
    2739596730: "TRANSLATE",
    3552837520: "RIG_ROOT",
}

SEG_NAMES = {
    SEG_QUAT: "QUAT",
    SEG_FLOAT: "FLOAT",
    SEG_VEC2: "VEC2",
    SEG_VEC3: "VEC3",
    SEG_VEC4: "VEC4",
    SEG_QUAT_DIFF: "QUAT_DIFF",
    SEG_VEC_DIFF: "VEC_DIFF",
}


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def _i32(data: bytes, off: int) -> int:
    return struct.unpack_from("<i", data, off)[0]


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def _i16(data: bytes, off: int) -> int:
    return struct.unpack_from("<h", data, off)[0]


def _align(n: int, a: int) -> int:
    r = n % a
    return n if r == 0 else n + (a - r)


def _cstr(data: bytes, off: int) -> str:
    if off <= 0 or off >= len(data):
        return ""
    end = data.find(b"\x00", off)
    if end < 0:
        end = len(data)
    return data[off:end].decode("ascii", errors="replace")


def _half(h: int) -> float:
    return struct.unpack("<e", struct.pack("<H", h))[0]


class BitReader:
    def __init__(self, data: bytes, byte_offset: int):
        self.data = data
        self.bit = byte_offset * 8

    @property
    def byte_pos(self) -> int:
        return (self.bit + 7) // 8

    def read(self, nbits: int) -> int:
        value = 0
        for i in range(nbits):
            byte_i = self.bit >> 3
            if byte_i >= len(self.data):
                break
            bit_i = self.bit & 7
            value |= ((self.data[byte_i] >> bit_i) & 1) << i
            self.bit += 1
        return value


def _quat_from_packed(theta: int, y: int, z: int, xs: int, ys: int, zs: int, bits: int) -> tuple[float, float, float, float]:
    """Fox packed quat: theta + barycentric axis (y, z, 1-y-z), three sign bits.

    Layout matches kapuragu QuatAnim12/13/15 and MrDev/Modders Heaven GANI unpack.
    Scale is packed / 2^bits, not / (2^bits-1). Half-angle is packed * pi/2 (MGS3).
    """
    denom = float(1 << bits)
    t = theta / denom
    ay = y / denom
    az = z / denom
    ax = 1.0 - ay - az
    length = math.sqrt(ay * ay + az * az + ax * ax)
    if length < 1e-12:
        return (0.0, 0.0, 0.0, 1.0)
    half = t * (math.pi * 0.5)
    s = math.sin(half) / length
    qx = ay * s
    qy = az * s
    qz = ax * s
    if xs:
        qx = -qx
    if ys:
        qy = -qy
    if zs:
        qz = -qz
    return (qx, qy, qz, math.cos(half))


def _read_segment_value(kind: int, bits: int, reader: BitReader | None, data: bytes, pos: int) -> tuple[object, int]:
    """Return (value, new_byte_pos). Packed quats use BitReader."""
    if kind in (SEG_QUAT, SEG_QUAT_DIFF):
        if bits not in (12, 13, 15):
            raise ValueError(f"bad quat bits {bits}")
        if reader is None:
            reader = BitReader(data, pos)
        theta = reader.read(bits)
        y = reader.read(bits)
        z = reader.read(bits)
        xs = reader.read(1)
        ys = reader.read(1)
        zs = reader.read(1)
        return _quat_from_packed(theta, y, z, xs, ys, zs, bits), reader.byte_pos
    if kind == SEG_FLOAT:
        if bits == 16:
            return _half(_u16(data, pos)), pos + 2
        if bits == 32:
            return struct.unpack_from("<f", data, pos)[0], pos + 4
        raise ValueError(f"bad float bits {bits}")
    if kind == SEG_VEC2:
        if bits == 16:
            return (_half(_u16(data, pos)), _half(_u16(data, pos + 2))), pos + 4
        if bits == 32:
            return struct.unpack_from("<ff", data, pos), pos + 8
    if kind in (SEG_VEC3, SEG_VEC_DIFF):
        if bits == 0:
            return (0.0, 0.0, 0.0), pos
        if bits == 16:
            return (
                _half(_u16(data, pos)),
                _half(_u16(data, pos + 2)),
                _half(_u16(data, pos + 4)),
            ), pos + 6
        if bits == 32:
            return struct.unpack_from("<fff", data, pos), pos + 12
    if kind == SEG_VEC4:
        if bits == 16:
            return (
                _half(_u16(data, pos)),
                _half(_u16(data, pos + 2)),
                _half(_u16(data, pos + 4)),
                _half(_u16(data, pos + 6)),
            ), pos + 8
        if bits == 32:
            return struct.unpack_from("<ffff", data, pos), pos + 16
    raise ValueError(f"unsupported segment type={kind} bits={bits}")


@dataclass
class Keyframe:
    frame: int
    value: object


@dataclass
class Segment:
    seg_id: int
    kind: int
    bits: int
    static: bool
    keys: list[Keyframe] = field(default_factory=list)

    @property
    def kind_name(self) -> str:
        return SEG_NAMES.get(self.kind, str(self.kind))


@dataclass
class TrackUnit:
    name_hash: int
    flags: int
    segments: list[Segment] = field(default_factory=list)

    @property
    def name(self) -> str:
        return KNOWN_NODES.get(self.name_hash, str(self.name_hash))


@dataclass
class TrackHeader:
    unit_count: int
    segment_count: int
    track_id: int
    frame_count: int
    frame_rate: int
    units: list[TrackUnit] = field(default_factory=list)


@dataclass
class FoxNode:
    name_hash: int
    flags: int
    data_offset: int
    data_size: int
    parent: int
    child: int
    prev: int
    next: int
    params: int
    offset: int
    name: str = ""
    payload: object | None = None
    children: list[FoxNode] = field(default_factory=list)


@dataclass
class GaniFile:
    version: int
    file_size: int
    flags: int
    name: str
    nodes: list[FoxNode]
    motion: TrackHeader | None


def _read_node(data: bytes, offset: int) -> FoxNode:
    name_hash = _u32(data, offset)
    str_off = _u32(data, offset + 4)
    flags = _u32(data, offset + 8)
    data_offset = _i32(data, offset + 12)
    data_size = _u32(data, offset + 16)
    parent = _i32(data, offset + 20)
    child = _i32(data, offset + 24)
    prev = _i32(data, offset + 28)
    next_off = _i32(data, offset + 32)
    params = _i32(data, offset + 36)
    name = KNOWN_NODES.get(name_hash, "")
    if not name and str_off:
        name = _cstr(data, offset + str_off)
    if not name:
        name = str(name_hash)
    return FoxNode(
        name_hash=name_hash,
        flags=flags,
        data_offset=data_offset,
        data_size=data_size,
        parent=parent,
        child=child,
        prev=prev,
        next=next_off,
        params=params,
        offset=offset,
        name=name,
    )


def _walk_nodes(data: bytes, offset: int) -> list[FoxNode]:
    nodes: list[FoxNode] = []
    while offset:
        node = _read_node(data, offset)
        if node.child:
            node.children = _walk_nodes(data, offset + node.child)
        nodes.append(node)
        if node.next == 0:
            break
        offset = offset + node.next
    return nodes


def _read_keys(data: bytes, start: int, kind: int, bits: int, is_static: bool, frame_count: int) -> tuple[list[Keyframe], int]:
    packed = bits not in (0, 16, 32)
    reader = BitReader(data, start) if packed else None
    pos = start
    keys: list[Keyframe] = []
    value, pos = _read_segment_value(kind, bits, reader, data, pos)
    keys.append(Keyframe(frame=0, value=value))
    if is_static:
        end = reader.byte_pos if reader else pos
        return keys, _align(end, 2)
    frame_index = 0
    safety = 0
    while frame_index < frame_count and safety < 100000:
        safety += 1
        if packed and reader is not None:
            span = reader.read(8)
            value, _ = _read_segment_value(kind, bits, reader, data, 0)
        else:
            if pos >= len(data):
                break
            span = data[pos]
            pos += 1
            value, pos = _read_segment_value(kind, bits, None, data, pos)
        if span == 0:
            span = 1
        frame_index += span
        keys.append(Keyframe(frame=min(frame_index, frame_count), value=value))
        if frame_index >= frame_count:
            break
    end = reader.byte_pos if reader else pos
    return keys, _align(end, 2)


def parse_track_header(data: bytes, start: int) -> TrackHeader:
    unit_count = _i32(data, start)
    segment_count = _u32(data, start + 4)
    track_id = _u16(data, start + 8)
    frame_count = _u32(data, start + 12)
    frame_rate = data[start + 16]
    header = TrackHeader(
        unit_count=unit_count,
        segment_count=segment_count,
        track_id=track_id,
        frame_count=frame_count,
        frame_rate=frame_rate or 30,
    )
    if unit_count <= 0:
        return header
    offsets = [
        _u32(data, start + 20 + i * 4) for i in range(unit_count)
    ]
    for unit_off in offsets:
        abs_off = start + unit_off
        name_hash = _u32(data, abs_off)
        seg_count = data[abs_off + 4]
        flags = data[abs_off + 5]
        unit = TrackUnit(name_hash=name_hash, flags=flags)
        cursor = abs_off + 8
        for _ in range(seg_count):
            data_offset = _i32(data, cursor)
            seg_id = _i16(data, cursor + 4)
            packed = data[cursor + 6]
            kind = packed & 0xF
            bits = data[cursor + 7]
            seg = Segment(seg_id=seg_id, kind=kind, bits=bits, static=bool(flags & FLAG_STATIC))
            if data_offset:
                keys, _ = _read_keys(
                    data,
                    cursor + data_offset,
                    kind,
                    bits,
                    seg.static,
                    frame_count,
                )
                seg.keys = keys
            unit.segments.append(seg)
            cursor += 8
        header.units.append(unit)
    return header


def _attach_payloads(data: bytes, nodes: list[FoxNode]) -> None:
    for node in nodes:
        if node.data_offset and (node.flags & 1 or node.data_size):
            payload_at = node.offset + node.data_offset
            if node.name_hash in (
                NODE_MOTION,
                NODE_SKEL,
                NODE_MTP,
                NODE_UNIT,
            ) or node.flags == 1:
                try:
                    node.payload = parse_track_header(data, payload_at)
                except (struct.error, ValueError, IndexError):
                    node.payload = None
        _attach_payloads(data, node.children)


def read_gani(path: str) -> GaniFile:
    data = Path(path).read_bytes()
    version = _u32(data, 0)
    nodes_offset = _u32(data, 4)
    file_size = _u32(data, 8)
    name_hash = _u32(data, 12)
    name_str_off = _u32(data, 16)
    flags = _u32(data, 20)
    name = _cstr(data, 12 + name_str_off) if name_str_off else KNOWN_NODES.get(name_hash, "")
    nodes = _walk_nodes(data, nodes_offset) if nodes_offset else []
    _attach_payloads(data, nodes)
    motion = None
    unit = None
    stack = list(nodes)
    while stack:
        n = stack.pop()
        if isinstance(n.payload, TrackHeader):
            if n.name_hash == NODE_MOTION:
                motion = n.payload
            elif n.name_hash == NODE_UNIT:
                unit = n.payload
        stack.extend(n.children)
    motion = motion or unit
    return GaniFile(
        version=version,
        file_size=file_size,
        flags=flags,
        name=name,
        nodes=nodes,
        motion=motion,
    )


def gani_to_dict(gani: GaniFile) -> dict:
    def unit_d(u: TrackUnit) -> dict:
        return {
            "name": u.name,
            "name_hash": u.name_hash,
            "flags": u.flags,
            "segments": [
                {
                    "id": s.seg_id,
                    "type": s.kind_name,
                    "bits": s.bits,
                    "static": s.static,
                    "keys": [{"frame": k.frame, "value": k.value} for k in s.keys],
                }
                for s in u.segments
            ],
        }

    motion = None
    if gani.motion:
        motion = {
            "frame_count": gani.motion.frame_count,
            "frame_rate": gani.motion.frame_rate,
            "units": [unit_d(u) for u in gani.motion.units],
        }
    return {
        "version": gani.version,
        "name": gani.name,
        "flags": gani.flags,
        "motion": motion,
    }
