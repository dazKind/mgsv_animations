"""FRIG (Fox Rig). Maps GANI track units to FMDL bones."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

ROOT = 1
ORIENTATION = 2
TWO_BONE = 3
LOCAL_ORIENTATION = 4
LOCAL_TRANSFORM = 5
THREE_BONE_LIKE_TWO_BONE = 6
TRANSFORM = 7
ARM = 8
LOCAL_TRANSFORM_SRT = 9
ANIMAL_LEG = 10
MULTI_LOCAL_ORIENTATION = 11
TWO_BONE_TRANS = 12

TYPE_NAMES = {
    ROOT: "ROOT",
    ORIENTATION: "ORIENTATION",
    TWO_BONE: "TWO_BONE",
    LOCAL_ORIENTATION: "LOCAL_ORIENTATION",
    LOCAL_TRANSFORM: "LOCAL_TRANSFORM",
    THREE_BONE_LIKE_TWO_BONE: "THREE_BONE_LIKE_TWO_BONE",
    TRANSFORM: "TRANSFORM",
    ARM: "ARM",
    LOCAL_TRANSFORM_SRT: "LOCAL_TRANSFORM_SRT",
    ANIMAL_LEG: "ANIMAL_LEG",
    MULTI_LOCAL_ORIENTATION: "MULTI_LOCAL_ORIENTATION",
    TWO_BONE_TRANS: "TWO_BONE_TRANS",
}


@dataclass
class RigUnit:
    type: int
    track_count: int
    bone_count: int
    parent_unit: int
    skel: list[int] = field(default_factory=list)
    segments: list[int] = field(default_factory=list)
    effector: int = -1
    pole: tuple[float, float, float] = (0.0, 1.0, 0.0)

    @property
    def type_name(self) -> str:
        return TYPE_NAMES.get(self.type, str(self.type))


@dataclass
class Frig:
    path: Path
    name: str
    version: int
    units: list[RigUnit]
    bones: list[tuple[int, int]]  # (rig_index, name_hash)


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def _i16(data: bytes, off: int) -> int:
    return struct.unpack_from("<h", data, off)[0]


def _cstr12(data: bytes, off: int) -> str:
    return data[off : off + 12].split(b"\x00", 1)[0].decode("ascii", errors="replace")


def read_frig(path: str | Path) -> Frig:
    path = Path(path)
    data = path.read_bytes()
    name_hash = _u32(data, 0)
    name_off = _u32(data, 4)
    name = ""
    if name_off:
        name = data[name_off:].split(b"\x00", 1)[0].decode("ascii", errors="replace")
    version = _u32(data, 8)
    unit_count = _u32(data, 12)
    _segment_count = _u32(data, 16)
    _file_size = _u32(data, 20)
    bone_list_off = _u32(data, 24)
    _mask_off = _u32(data, 28)
    offsets = [_u32(data, 32 + i * 4) for i in range(unit_count)]
    units: list[RigUnit] = []
    for off in offsets:
        utype = _u32(data, off)
        track_count = _i16(data, off + 4)
        bone_count = _i16(data, off + 6)
        parent_unit = _i16(data, off + 10)
        unit = RigUnit(
            type=utype,
            track_count=track_count,
            bone_count=bone_count,
            parent_unit=parent_unit,
        )
        body = off + 16
        if utype == ROOT:
            unit.segments = [_i16(data, body), _i16(data, body + 2)]
        elif utype in (ORIENTATION, LOCAL_ORIENTATION):
            unit.skel = [_i16(data, body)]
            unit.segments = [_i16(data, body + 2)]
        elif utype in (LOCAL_TRANSFORM, TRANSFORM):
            unit.skel = [_i16(data, body)]
            unit.segments = [_i16(data, body + 2), _i16(data, body + 4)]
        elif utype == LOCAL_TRANSFORM_SRT:
            unit.skel = [_i16(data, body)]
        elif utype == TWO_BONE:
            px, py, pz, _pw = struct.unpack_from("<ffff", data, off + 32)
            unit.pole = (px, py, pz)
            p = off + 16 + 16 + 16
            unit.skel = [_i16(data, p), _i16(data, p + 2)]
            unit.segments = [_i16(data, p + 4), _i16(data, p + 6)]
            unit.effector = _i16(data, p + 8)
        elif utype == ARM:
            px, py, pz, _pw = struct.unpack_from("<ffff", data, off + 32)
            # ARM ChainPlaneNormal is stored opposite TWO_BONE for axis×N.
            # Keep _two_bone on one winding: negate here, not in the solver.
            unit.pole = (-px, -py, -pz)
            p = off + 16 + 16 + 16
            unit.skel = [_i16(data, p), _i16(data, p + 2), _i16(data, p + 4)]
            unit.segments = [_i16(data, p + 6), _i16(data, p + 8), _i16(data, p + 10)]
            unit.effector = _i16(data, p + 12)
        elif utype == MULTI_LOCAL_ORIENTATION:
            start = _i16(data, body)
            unit.skel = list(range(start, start + max(bone_count, 0)))
        units.append(unit)
    bones: list[tuple[int, int]] = []
    if bone_list_off and bone_list_off < len(data):
        count = struct.unpack_from("<i", data, bone_list_off)[0]
        pos = bone_list_off + 4
        for _ in range(max(count, 0)):
            rig_index = _u32(data, pos)
            name_h = _u32(data, pos + 4)
            bones.append((rig_index, name_h))
            pos += 8
    return Frig(path=path, name=name or str(name_hash), version=version, units=units, bones=bones)
