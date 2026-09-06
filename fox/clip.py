"""Map one GANI clip onto FMDL bones using FRIG units."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .fmdl import Skeleton
from .frig import (
    ARM,
    LOCAL_ORIENTATION,
    LOCAL_TRANSFORM,
    LOCAL_TRANSFORM_SRT,
    MULTI_LOCAL_ORIENTATION,
    ORIENTATION,
    ROOT,
    TRANSFORM,
    TWO_BONE,
    Frig,
)
from .gani import SEG_QUAT, SEG_QUAT_DIFF, SEG_VEC3, SEG_VEC_DIFF, GaniFile, TrackUnit


@dataclass
class BoneTrack:
    loc: list[tuple[int, tuple[float, float, float]]] = field(default_factory=list)
    rot: list[tuple[int, tuple[float, float, float, float]]] = field(default_factory=list)


@dataclass
class Clip:
    name: str
    frame_count: int
    fps: int
    tracks: dict[str, BoneTrack]
    ik: dict[str, str]  # constrained bone -> IK target bone


def _keys_as(seg) -> list[tuple[int, tuple]]:
    out = []
    for k in seg.keys:
        v = k.value if isinstance(k.value, tuple) else (k.value,)
        out.append((k.frame, v))
    return out


def _rot_seg(unit: TrackUnit):
    segs = [s for s in unit.segments if s.kind in (SEG_QUAT, SEG_QUAT_DIFF) and s.keys]
    return segs


def _loc_seg(unit: TrackUnit):
    segs = [s for s in unit.segments if s.kind in (SEG_VEC3, SEG_VEC_DIFF) and s.keys]
    return segs


def _bone_name(skel: Skeleton, index: int) -> str | None:
    if 0 <= index < len(skel.bones):
        return skel.bones[index].name
    return None


def _ground_y(skel: Skeleton) -> float:
    """FMDL hip is at y=0. GANI loc Y is metres above the floor."""
    ys = [b.world_pos[1] for b in skel.bones if b.name in ("SKL_032_LFOOT", "SKL_042_RFOOT")]
    return sum(ys) / len(ys) if ys else 0.0


def _shift_y(keys: list[tuple[int, tuple]], dy: float) -> list[tuple[int, tuple]]:
    out = []
    for frame, value in keys:
        if len(value) < 3:
            out.append((frame, value))
            continue
        out.append((frame, (value[0], value[1] + dy, value[2])))
    return out


def evaluate_clip(skel: Skeleton, gani: GaniFile, frig: Frig | None, name: str = "") -> Clip:
    motion = gani.motion
    frame_count = motion.frame_count if motion else 1
    fps = 30
    tracks: dict[str, BoneTrack] = {}
    ik: dict[str, str] = {}
    ground_y = _ground_y(skel)

    def track(name: str) -> BoneTrack:
        t = tracks.get(name)
        if t is None:
            t = BoneTrack()
            tracks[name] = t
        return t

    if not motion:
        return Clip(name=name, frame_count=frame_count, fps=fps, tracks=tracks, ik=ik)

    units = frig.units if frig else []
    for ui, gunit in enumerate(motion.units):
        runit = units[ui] if ui < len(units) else None
        rots = _rot_seg(gunit)
        locs = _loc_seg(gunit)

        if runit is None:
            continue

        if runit.type == ROOT:
            t = track("ROOT")
            if rots:
                t.rot = _keys_as(rots[0])
            if locs:
                t.loc = _keys_as(locs[0])
            continue

        if runit.type in (ORIENTATION, LOCAL_ORIENTATION, LOCAL_TRANSFORM_SRT):
            bname = _bone_name(skel, runit.skel[0]) if runit.skel else None
            if bname and rots:
                track(bname).rot = _keys_as(rots[0])
            if bname and locs and runit.type == LOCAL_TRANSFORM_SRT:
                track(bname).loc = _keys_as(locs[0])
            continue

        if runit.type in (TRANSFORM, LOCAL_TRANSFORM):
            bname = _bone_name(skel, runit.skel[0]) if runit.skel else None
            if bname and rots:
                track(bname).rot = _keys_as(rots[0])
            if bname and locs:
                track(bname).loc = _shift_y(_keys_as(locs[0]), ground_y)
            continue

        if runit.type in (ARM, TWO_BONE):
            eff = _bone_name(skel, runit.effector)
            ik_name = f"IK_{eff}" if eff else None
            if ik_name:
                if locs:
                    track(ik_name).loc = _shift_y(_keys_as(locs[0]), ground_y)
                if rots:
                    track(ik_name).rot = _keys_as(rots[-1])
                driven = _bone_name(skel, runit.skel[-1]) if runit.skel else None
                if driven:
                    ik[driven] = ik_name
            if runit.type == ARM and runit.skel and rots:
                shoulder = _bone_name(skel, runit.skel[0])
                if shoulder:
                    track(shoulder).rot = _keys_as(rots[0])
            continue

        if runit.type == MULTI_LOCAL_ORIENTATION:
            for bi, seg in zip(runit.skel, gunit.segments):
                bname = _bone_name(skel, bi)
                if bname and seg.keys and seg.kind in (SEG_QUAT, SEG_QUAT_DIFF):
                    track(bname).rot = _keys_as(seg)
            continue

    return Clip(name=name, frame_count=frame_count, fps=fps, tracks=tracks, ik=ik)


def _slerp(a, b, t: float):
    """Unit quaternion slerp. Flip b if the short arc would go the long way."""
    dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]
    if dot < 0.0:
        b = (-b[0], -b[1], -b[2], -b[3])
        dot = -dot
    if dot > 0.9995:
        s = (
            a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t,
            a[3] + (b[3] - a[3]) * t,
        )
        n = math.sqrt(s[0] * s[0] + s[1] * s[1] + s[2] * s[2] + s[3] * s[3]) or 1.0
        return (s[0] / n, s[1] / n, s[2] / n, s[3] / n)
    omega = math.acos(max(-1.0, min(1.0, dot)))
    so = math.sin(omega)
    w0 = math.sin((1.0 - t) * omega) / so
    w1 = math.sin(t * omega) / so
    return (a[0] * w0 + b[0] * w1, a[1] * w0 + b[1] * w1, a[2] * w0 + b[2] * w1, a[3] * w0 + b[3] * w1)


def _sample(keys: list[tuple[int, tuple]], frame: int):
    if not keys:
        return None
    if frame <= keys[0][0]:
        return keys[0][1]
    if frame >= keys[-1][0]:
        return keys[-1][1]
    for i in range(1, len(keys)):
        if keys[i][0] >= frame:
            a, b = keys[i - 1], keys[i]
            span = b[0] - a[0]
            t = 0.0 if span <= 0 else (frame - a[0]) / span
            va, vb = a[1], b[1]
            n = min(len(va), len(vb))
            if n == 4:
                return _slerp(va[:4], vb[:4], t)
            return tuple(va[j] + (vb[j] - va[j]) * t for j in range(n))
    return keys[-1][1]


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _qrot(q, v):
    qx, qy, qz, qw = q
    vx, vy, vz = v
    uvx = qy * vz - qz * vy
    uvy = qz * vx - qx * vz
    uvz = qx * vy - qy * vx
    return (
        vx + 2 * (qw * uvx + (qy * uvz - qz * uvy)),
        vy + 2 * (qw * uvy + (qz * uvx - qx * uvz)),
        vz + 2 * (qw * uvz + (qx * uvy - qy * uvx)),
    )


def _vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vmul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _vlen(a):
    return math.sqrt(_vdot(a, a))


def _vnorm(a):
    length = _vlen(a)
    if length < 1e-12:
        return (0.0, 1.0, 0.0)
    return _vmul(a, 1.0 / length)


def _two_bone(p0, len1, len2, target, ref_dir, prev_mid=None):
    """Two-bone IK. The mid joint bends toward ref_dir (body space): knees
    bend body-forward, elbows body-backward. A fixed world pole inverts
    elbows on hanging arms and knees on turns."""
    to = _vsub(target, p0)
    dist = _vlen(to)
    maxd = max(len1 + len2 - 1e-4, 1e-4)
    mind = abs(len1 - len2) + 1e-4
    dist = min(max(dist, mind), maxd)
    axis = _vnorm(to)
    end = _vadd(p0, _vmul(axis, dist))
    cos_a = (len1 * len1 + dist * dist - len2 * len2) / (2.0 * len1 * dist)
    cos_a = max(-1.0, min(1.0, cos_a))
    sin_a = math.sqrt(max(0.0, 1.0 - cos_a * cos_a))
    bend = _vsub(ref_dir, _vmul(axis, _vdot(ref_dir, axis)))
    if _vlen(bend) < 1e-5 and prev_mid is not None:
        pref = _vsub(prev_mid, p0)
        bend = _vsub(pref, _vmul(axis, _vdot(pref, axis)))
    if _vlen(bend) < 1e-5:
        ortho = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
        bend = _vcross(axis, ortho)
    bend = _vnorm(bend)
    mid = _vadd(p0, _vadd(_vmul(axis, cos_a * len1), _vmul(bend, sin_a * len1)))
    return mid, end


def solve_joints(
    skel: Skeleton,
    clip: Clip,
    frig: Frig | None,
    frame: int,
    prev_pos: dict[str, tuple[float, float, float]] | None = None,
) -> dict[str, tuple[float, float, float]]:
    """Fox identity-rest FK, then two-bone IK. Returns armature-space joint positions."""
    bones = skel.bones
    local = []
    for b in bones:
        if b.parent >= 0:
            p = bones[b.parent].world_pos
            w = b.world_pos
            local.append((w[0] - p[0], w[1] - p[1], w[2] - p[2]))
        else:
            local.append(b.world_pos)
    world_rot = set()
    if frig is not None:
        for unit in frig.units:
            if unit.type == ORIENTATION:
                for bi in unit.skel:
                    if 0 <= bi < len(bones):
                        world_rot.add(bones[bi].name)

    pos = [b.world_pos for b in bones]
    rot = [(0.0, 0.0, 0.0, 1.0)] * len(bones)
    ident = (0.0, 0.0, 0.0, 1.0)
    root_off = (0.0, 0.0, 0.0)
    root_q = ident
    root_track = clip.tracks.get("ROOT")
    if root_track and root_track.loc:
        sampled = _sample(root_track.loc, frame)
        if sampled and len(sampled) >= 3:
            root_off = sampled[:3]
    if root_track and root_track.rot:
        sampled = _sample(root_track.rot, frame)
        if sampled and len(sampled) >= 4:
            root_q = sampled[:4]
    for i, b in enumerate(bones):
        q = ident
        t = clip.tracks.get(b.name)
        if t and t.rot:
            sampled = _sample(t.rot, frame)
            if sampled and len(sampled) >= 4:
                q = sampled[:4]
        if b.parent < 0:
            # FMDL root is the waist. ROOT track is locomotion (XYZ) and
            # turns the whole rig; dropping its rotation leaves IK limbs on
            # the wrong side during turns.
            rot[i] = _qmul(root_q, q)
            loc = b.world_pos
            if t and t.loc:
                sampled = _sample(t.loc, frame)
                if sampled and len(sampled) >= 3:
                    loc = sampled[:3]
            pos[i] = (root_off[0] + loc[0], root_off[1] + loc[1], root_off[2] + loc[2])
            continue
        pq = rot[b.parent]
        pp = pos[b.parent]
        # ORIENTATION is character space: model pose after ROOT yaw.
        # Using q alone leaves the spine facing the old way on turns.
        # Multiplying by the waist parent restacks the crouch fold.
        rot[i] = _qmul(root_q, q) if b.name in world_rot else _qmul(pq, q)
        pos[i] = _vadd(pp, _qrot(pq, local[i]))

    if frig is not None:
        for unit in frig.units:
            if unit.type not in (ARM, TWO_BONE) or unit.effector < 0 or len(unit.skel) < 2:
                continue
            if unit.type == ARM:
                upper, lower = unit.skel[1], unit.skel[2]
            else:
                upper, lower = unit.skel[0], unit.skel[1]
            eff = unit.effector
            if not (0 <= upper < len(bones) and 0 <= lower < len(bones) and 0 <= eff < len(bones)):
                continue
            len1 = _vlen(_vsub(bones[lower].world_pos, bones[upper].world_pos))
            len2 = _vlen(_vsub(bones[eff].world_pos, bones[lower].world_pos))
            ik_name = f"IK_{bones[eff].name}"
            target = pos[eff]
            t = clip.tracks.get(ik_name)
            if t and t.loc:
                sampled = _sample(t.loc, frame)
                if sampled and len(sampled) >= 3:
                    target = sampled[:3]
            # Bend side in the chain-root's parent frame. Knee: body-forward.
            # Elbow: out-back plus world-down. Out-back alone projects up on
            # a forward-reaching arm (reload). Pure world-down is a world
            # pole and pops the crouch get-up. Outward still conditions the
            # plane when the chest faces the floor and the arm hangs.
            chain_root = unit.skel[0]
            par = bones[chain_root].parent if 0 <= chain_root < len(bones) else -1
            if par < 0:
                ref_dir = (0.0, 0.0, 1.0)
            elif unit.type == TWO_BONE:
                ref_dir = _qrot(rot[par], (0.0, 0.0, 1.0))
            else:
                side = 1.0 if bones[chain_root].world_pos[0] >= 0 else -1.0
                f = _qrot(rot[par], (0.0, 0.0, 1.0))
                o = _qrot(rot[par], (side, 0.0, 0.0))
                ob = _vnorm(_vsub(o, f))
                ref_dir = _vnorm((ob[0], ob[1] - 0.5, ob[2]))
            prev_mid = prev_pos.get(bones[lower].name) if prev_pos else None
            mid, end = _two_bone(pos[upper], len1, len2, target, ref_dir, prev_mid)
            pos[lower] = mid
            pos[eff] = end

        # IK moved the effector. Re-FK its children (toes, fingers) with the
        # effector ORIENTATION so look-at tails stay on the bone.
        effectors = set()
        for unit in frig.units:
            if unit.type in (ARM, TWO_BONE) and 0 <= unit.effector < len(bones):
                effectors.add(unit.effector)
        for i, b in enumerate(bones):
            if b.parent < 0:
                continue
            if i in effectors:
                t = clip.tracks.get(b.name)
                if t and t.rot:
                    sampled = _sample(t.rot, frame)
                    if sampled and len(sampled) >= 4:
                        q = sampled[:4]
                        rot[i] = _qmul(root_q, q) if b.name in world_rot else _qmul(rot[b.parent], q)
                continue
            anc = b.parent
            while anc >= 0 and anc not in effectors:
                anc = bones[anc].parent
            if anc not in effectors:
                continue
            q = ident
            t = clip.tracks.get(b.name)
            if t and t.rot:
                sampled = _sample(t.rot, frame)
                if sampled and len(sampled) >= 4:
                    q = sampled[:4]
            rot[i] = _qmul(root_q, q) if b.name in world_rot else _qmul(rot[b.parent], q)
            pos[i] = _vadd(pos[b.parent], _qrot(rot[b.parent], local[i]))

    return {b.name: pos[i] for i, b in enumerate(bones)}
