"""Write Source SMD from FMDL skeleton + GANI tracks. Blender Source Tools import this."""

from __future__ import annotations

import math
from pathlib import Path

from .fmdl import Skeleton
from .frig import ARM, LOCAL_ORIENTATION, LOCAL_TRANSFORM, LOCAL_TRANSFORM_SRT, ORIENTATION, ROOT, TRANSFORM, TWO_BONE, Frig
from .gani import SEG_QUAT, SEG_QUAT_DIFF, SEG_VEC3, SEG_VEC_DIFF, GaniFile


def _quat_to_euler(q: tuple[float, float, float, float]) -> tuple[float, float, float]:
    x, y, z, w = q
    sinr = 2 * (w * x + y * z)
    cosr = 1 - 2 * (x * x + y * y)
    roll = math.atan2(sinr, cosr)
    sinp = 2 * (w * y - z * x)
    sinp = max(-1.0, min(1.0, sinp))
    pitch = math.asin(sinp)
    siny = 2 * (w * z + x * y)
    cosy = 1 - 2 * (y * y + z * z)
    yaw = math.atan2(siny, cosy)
    return roll, pitch, yaw


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _sample_keys(keys, frame: int, ncomp: int):
    if not keys:
        return tuple(0.0 for _ in range(ncomp))
    if frame <= keys[0].frame:
        v = keys[0].value
        return v if isinstance(v, tuple) else (v,)
    if frame >= keys[-1].frame:
        v = keys[-1].value
        return v if isinstance(v, tuple) else (v,)
    for i in range(1, len(keys)):
        if keys[i].frame >= frame:
            a, b = keys[i - 1], keys[i]
            span = b.frame - a.frame
            t = 0.0 if span <= 0 else (frame - a.frame) / span
            va = a.value if isinstance(a.value, tuple) else (a.value,)
            vb = b.value if isinstance(b.value, tuple) else (b.value,)
            return tuple(_lerp(va[j], vb[j], t) for j in range(min(len(va), len(vb))))
    v = keys[-1].value
    return v if isinstance(v, tuple) else (v,)


def write_smd(skel: Skeleton, gani: GaniFile, dest: Path, frig: Frig | None = None) -> None:
    bones = skel.bones
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = ["version 1", "nodes"]
    for i, bone in enumerate(bones):
        parent = bone.parent if bone.parent >= 0 else -1
        lines.append(f'{i} "{bone.name}" {parent}')
    lines.append("end")
    lines.append("skeleton")
    frame_count = gani.motion.frame_count if gani.motion else 1
    fps = gani.motion.frame_rate if gani.motion else 30
    unit_by_index = list(frig.units) if frig else []
    motion_units = gani.motion.units if gani.motion else []

    bone_rot: dict[int, object] = {}
    bone_pos: dict[int, object] = {}
    if frig and motion_units:
        for ui, unit in enumerate(frig.units):
            if ui >= len(motion_units):
                break
            tracks = motion_units[ui]
            rot_keys = None
            pos_keys = None
            for seg in tracks.segments:
                if seg.kind in (SEG_QUAT, SEG_QUAT_DIFF) and rot_keys is None:
                    rot_keys = seg.keys
                if seg.kind in (SEG_VEC3, SEG_VEC_DIFF) and pos_keys is None:
                    pos_keys = seg.keys
            targets = list(unit.skel)
            if unit.effector >= 0:
                targets.append(unit.effector)
            if unit.type in (
                ROOT,
                ORIENTATION,
                LOCAL_ORIENTATION,
                TRANSFORM,
                LOCAL_TRANSFORM,
                LOCAL_TRANSFORM_SRT,
                TWO_BONE,
                ARM,
            ):
                for bi in targets:
                    if 0 <= bi < len(bones):
                        if rot_keys:
                            bone_rot[bi] = rot_keys
                        if pos_keys and unit.type in (
                            ROOT,
                            TRANSFORM,
                            LOCAL_TRANSFORM,
                            LOCAL_TRANSFORM_SRT,
                        ):
                            bone_pos[bi] = pos_keys

    for frame in range(frame_count):
        lines.append(f"time {frame}")
        for i, bone in enumerate(bones):
            px, py, pz = bone.local_pos
            rx = ry = rz = 0.0
            if i in bone_pos:
                sampled = _sample_keys(bone_pos[i], frame, 3)
                if len(sampled) >= 3:
                    px, py, pz = sampled[0], sampled[1], sampled[2]
            if i in bone_rot:
                sampled = _sample_keys(bone_rot[i], frame, 4)
                if len(sampled) >= 4:
                    rx, ry, rz = _quat_to_euler(sampled)  # type: ignore[arg-type]
            lines.append(f"{i} {px:.6f} {py:.6f} {pz:.6f} {rx:.6f} {ry:.6f} {rz:.6f}")
    lines.append("end")
    dest.write_text("\n".join(lines) + "\n", encoding="ascii")
    _ = fps
    _ = unit_by_index
