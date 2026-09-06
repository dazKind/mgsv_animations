bl_info = {
    "name": "Import MGSV FMDL / GANI",
    "author": "mgsv_animations",
    "version": (0, 8, 3),
    "blender": (4, 2, 0),
    "location": "File > Import",
    "category": "Import-Export",
}

import math
import os
import sys
from pathlib import Path

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy_extras.io_utils import ImportHelper
from mathutils import Matrix, Vector

def _has_fox(path: Path) -> bool:
    return (path / "fox" / "__init__.py").is_file()


def _repo() -> Path:
    env = os.environ.get("MGSV_ANIMATIONS")
    if env:
        path = Path(env).expanduser().resolve()
        if _has_fox(path):
            return path
    here = Path(__file__).resolve()
    for parent in here.parents:
        if _has_fox(parent):
            return parent
    blend = getattr(bpy.data, "filepath", "") or ""
    if blend:
        for parent in Path(blend).resolve().parents:
            if _has_fox(parent):
                return parent
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        if _has_fox(parent):
            return parent
    raise RuntimeError(
        "Cannot find the mgsv_animations repo (fox/ missing). "
        "Set MGSV_ANIMATIONS to the repo root."
    )


def _ensure_fox() -> None:
    root = str(_repo())
    if root not in sys.path:
        sys.path.insert(0, root)


def _tail(head: Vector, target: Vector) -> Vector:
    d = target - head
    if d.length < 1e-4:
        return head + Vector((0.0, 0.03, 0.0))
    if d.length < 0.02:
        return head + d.normalized() * 0.02
    return target


def _is_helper(name: str) -> bool:
    return any(tag in name for tag in ("_HLP", "ITEM_SIM", "ASR", "SNR", "HAIR", "BUD_"))


def _is_body(name: str) -> bool:
    if name == "ROOT" or _is_helper(name):
        return False
    if name.startswith(("SKL_1", "SKL_2", "SKL_3", "SKL_4", "SKL_5", "SKL_6")):
        return False
    return name.startswith("SKL_0")


def _is_finger(name: str) -> bool:
    return name.startswith(("SKL_1", "SKL_2"))


def _should_bake(name: str) -> bool:
    return _is_body(name) or _is_finger(name)


def _primary_child(bones, index: int):
    """Kinematic child that continues the incoming bone direction.

    Waist has spine (+Y) and both thighs (-Y). Min-name used to pick spine;
    max-distance would pick a thigh and the hip bone would point at a leg.
    Hands have no SKL_0* child: fall back to a finger so the hand aims along the digits.
    """
    kids = [j for j, c in enumerate(bones) if c.parent == index and _is_body(c.name)]
    if not kids:
        kids = [j for j, c in enumerate(bones) if c.parent == index and _is_finger(c.name)]
    if not kids:
        return None
    head = bones[index].world_pos
    parent = bones[index].parent
    if parent >= 0:
        px, py, pz = bones[parent].world_pos
        incoming = (head[0] - px, head[1] - py, head[2] - pz)
    else:
        incoming = (0.0, 1.0, 0.0)
    length = (incoming[0] ** 2 + incoming[1] ** 2 + incoming[2] ** 2) ** 0.5
    if length < 1e-8:
        incoming = (0.0, 1.0, 0.0)
        length = 1.0
    incoming = (incoming[0] / length, incoming[1] / length, incoming[2] / length)

    def score(j):
        t = bones[j].world_pos
        d = (t[0] - head[0], t[1] - head[1], t[2] - head[2])
        n = (d[0] ** 2 + d[1] ** 2 + d[2] ** 2) ** 0.5
        if n < 1e-8:
            return -1e9
        return (d[0] * incoming[0] + d[1] * incoming[1] + d[2] * incoming[2]) / n

    return max(kids, key=score)


def _bind_action(obj, action) -> None:
    """Blender 5.x Action Editor is empty unless the action slot is set."""
    if obj.animation_data is None:
        obj.animation_data_create()
    ad = obj.animation_data
    ad.action = action
    if not hasattr(action, "slots"):
        return
    ident = f"OB{obj.name}"
    slot = next((s for s in action.slots if s.identifier == ident), None)
    if slot is None:
        slot = action.slots.new(id_type="OBJECT", name=obj.name)
    ad.action_slot = slot


def build_armature(context, skel, frig=None):
    arm = bpy.data.armatures.new("sna2")
    obj = bpy.data.objects.new("sna2", arm)
    context.collection.objects.link(obj)
    context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.edit_bones

    root = eb.new("ROOT")
    root.head = Vector((0.0, 0.0, 0.0))
    root.tail = Vector((0.0, 0.05, 0.0))

    bones = skel.bones
    created = {"ROOT": root}
    for i, bone in enumerate(bones):
        b = eb.new(bone.name)
        head = Vector(bone.world_pos)
        kid = _primary_child(bones, i)
        if kid is not None:
            tail = _tail(head, Vector(bones[kid].world_pos))
        else:
            parent_head = Vector(bones[bone.parent].world_pos) if bone.parent >= 0 else Vector((0, 0, 0))
            direction = head - parent_head
            if direction.length < 1e-4:
                direction = Vector((0.0, 0.03, 0.0))
            tail = head + direction.normalized() * 0.03
        b.head = head
        b.tail = tail
        b.use_connect = False
        b.align_roll(Vector((0.0, 0.0, 1.0)))
        created[bone.name] = b

    for i, bone in enumerate(bones):
        child = created[bone.name]
        if bone.parent >= 0:
            child.parent = created[bones[bone.parent].name]
        else:
            child.parent = root

    bpy.ops.object.mode_set(mode="POSE")
    obj.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    obj.show_in_front = True
    arm.display_type = "OCTAHEDRAL"
    while arm.collections:
        arm.collections.remove(arm.collections[0])
    body = arm.collections.new("body")
    fingers = arm.collections.new("fingers")
    ikc = arm.collections.new("ik")
    extra = arm.collections.new("extra")
    for bone in arm.bones:
        n = bone.name
        if n == "ROOT":
            ikc.assign(bone)
        elif _is_finger(n):
            fingers.assign(bone)
        elif (
            n.startswith("SKL_3")
            or n.startswith("SKL_4")
            or n.startswith("SKL_5")
            or n.startswith("SKL_6")
            or _is_helper(n)
        ):
            extra.assign(bone)
        else:
            body.assign(bone)
    extra.is_visible = False
    obj.animation_data_create()
    return obj


def _aim(head: Vector, tail: Vector, rest: Matrix, prev: Matrix | None) -> Matrix:
    """Aim bone Y at tail. Twist from rest on frame 0, then parallel-transport."""
    y = tail - head
    if y.length < 1e-6:
        y = rest.to_3x3().col[1].copy()
    y.normalize()
    if prev is not None:
        hint = prev.to_3x3().col[0]
    else:
        hint = rest.to_3x3().col[0]
    x = hint - y * y.dot(hint)
    if x.length < 1e-6:
        hint = rest.to_3x3().col[2]
        x = hint - y * y.dot(hint)
    if x.length < 1e-6:
        x = Vector((1.0, 0.0, 0.0)) if abs(y.x) < 0.9 else Vector((0.0, 1.0, 0.0))
        x = x - y * y.dot(x)
    x.normalize()
    z = x.cross(y)
    z.normalize()
    x = y.cross(z)
    x.normalize()
    rot = Matrix((x, y, z)).transposed()
    return Matrix.Translation(head) @ rot.to_4x4()


def _linearize(action) -> None:
    """Look-at quats plus Bézier overshoot = spin. Force linear keys."""

    def do(fcu):
        for kp in fcu.keyframe_points:
            kp.interpolation = "LINEAR"

    if hasattr(action, "layers") and hasattr(action, "slots"):
        for layer in action.layers:
            for strip in getattr(layer, "strips", []):
                for slot in action.slots:
                    bag = strip.channelbag(slot) if hasattr(strip, "channelbag") else None
                    if bag is None:
                        continue
                    for fcu in bag.fcurves:
                        do(fcu)
        return
    for fcu in getattr(action, "fcurves", []):
        do(fcu)


def apply_clip(obj, clip, skel, frig=None, replace_action: bool = False):
    from fox.clip import solve_joints
    from fox.gani_names import action_name, fox_path

    stem = clip.name or "gani"
    action = bpy.data.actions.new(action_name(stem))
    action.use_fake_user = True
    action["fox_hash"] = stem
    path = fox_path(stem)
    if path:
        action["fox_path"] = path
    _bind_action(obj, action)

    bones = skel.bones
    child_of = {}
    for i, bone in enumerate(bones):
        kid = _primary_child(bones, i)
        child_of[bone.name] = bones[kid].name if kid is not None else None

    for pb in obj.pose.bones:
        pb.rotation_mode = "QUATERNION"

    prev_q = {}
    prev_W: dict[str, Matrix] = {}
    prev_pos = None
    for frame in range(0, clip.frame_count + 1):
        joints = solve_joints(skel, clip, frig, frame, prev_pos=prev_pos)
        prev_pos = joints
        world: dict[str, Matrix] = {}
        for bone in bones:
            if not _should_bake(bone.name):
                continue
            pb = obj.pose.bones.get(bone.name)
            if pb is None:
                continue
            head = Vector(joints[bone.name])
            cname = child_of[bone.name]
            if cname and cname in joints:
                tail = Vector(joints[cname])
            elif bone.parent >= 0:
                parent_head = Vector(joints[bones[bone.parent].name])
                direction = head - parent_head
                if direction.length < 1e-6:
                    direction = Vector((0.0, 0.05, 0.0))
                tail = head + direction.normalized() * 0.05
            else:
                tail = head + Vector((0.0, 0.05, 0.0))
            W = _aim(head, tail, pb.bone.matrix_local, prev_W.get(bone.name))
            prev_W[bone.name] = W.copy()
            world[bone.name] = W
        for bone in bones:
            if bone.name not in world:
                continue
            pb = obj.pose.bones.get(bone.name)
            if pb is None:
                continue
            W = world[bone.name]
            rest = pb.bone.matrix_local
            if pb.parent and pb.parent.name in world:
                rest_local = pb.parent.bone.matrix_local.inverted() @ rest
                basis = rest_local.inverted() @ world[pb.parent.name].inverted() @ W
            elif pb.parent:
                rest_local = pb.parent.bone.matrix_local.inverted() @ rest
                basis = rest_local.inverted() @ pb.parent.matrix.inverted() @ W
            else:
                basis = rest.inverted() @ W
            pb.matrix_basis = basis
            q = pb.rotation_quaternion.copy()
            old = prev_q.get(bone.name)
            if old is not None and q.dot(old) < 0.0:
                q.negate()
                pb.rotation_quaternion = q
            prev_q[bone.name] = q
            f = frame + 1
            pb.keyframe_insert("location", frame=f, group=bone.name)
            pb.keyframe_insert("rotation_quaternion", frame=f, group=bone.name)
            pb.keyframe_insert("scale", frame=f, group=bone.name)
    _linearize(action)
    return action


def import_player(context, fmdl_path: str, gani_dir: str, frig_path: str = "", max_clips: int = 0):
    _ensure_fox()
    from fox.clip import evaluate_clip
    from fox.fmdl import read_skeleton
    from fox.frig import read_frig
    from fox.gani import read_gani

    skel = read_skeleton(fmdl_path)
    frig = read_frig(frig_path) if frig_path else None
    obj = build_armature(context, skel, frig)
    files = sorted(Path(gani_dir).glob("*.gani"))
    if max_clips > 0:
        files = files[:max_clips]
    actions = []
    last_frame = 2
    best_action = None
    best_frames = -1
    for path in files:
        gani = read_gani(str(path))
        clip = evaluate_clip(skel, gani, frig, name=path.stem)
        action = apply_clip(obj, clip, skel, frig)
        actions.append(action.name)
        last_frame = max(last_frame, clip.frame_count + 1)
        if path.stem == "b081ddd62c1ffc" or (best_action is None and clip.frame_count > best_frames):
            best_frames = clip.frame_count
            best_action = action
    stand = None
    for act in bpy.data.actions:
        if act.get("fox_hash") == "b081ddd62c1ffc" or act.name == "b081ddd62c1ffc":
            stand = act
            break
    if stand is not None:
        best_action = stand
    if best_action is not None:
        _bind_action(obj, best_action)
        last_frame = max(last_frame, best_frames + 1)
    context.scene.frame_start = 1
    context.scene.frame_end = last_frame
    context.scene.render.fps = 30
    context.scene.frame_set(1)
    screen = getattr(context, "screen", None)
    if screen is not None:
        for area in screen.areas:
            if area.type == "DOPESHEET_EDITOR":
                area.spaces.active.mode = "ACTION"
    return obj.name, actions


class IMPORT_OT_mgsv_player(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.mgsv_player"
    bl_label = "Import MGSV Player (FMDL + GANI folder)"
    filename_ext = ".fmdl"
    filter_glob: StringProperty(default="*.fmdl", options={"HIDDEN"})
    gani_dir: StringProperty(name="GANI folder", subtype="DIR_PATH")
    frig_path: StringProperty(name="FRIG", subtype="FILE_PATH")
    max_clips: IntProperty(name="Max clips (0=all)", default=0, min=0, max=10000)
    def_paths: BoolProperty(name="Use repo extract defaults", default=True)

    def execute(self, context):
        fmdl = self.filepath
        gani_dir = self.gani_dir
        frig = self.frig_path
        if self.def_paths:
            base = _repo() / "extracted" / "player"
            if not gani_dir:
                gani_dir = str(base / "mtar" / "TppGzPlayer_layers")
            if not frig:
                frig = str(base / "fpk" / "Assets" / "tpp" / "rig" / "frig" / "human_finger.frig")
            if not fmdl:
                fmdl = str(base / "fpk" / "sna2_main0_def.fmdl")
        if not Path(gani_dir).is_dir():
            self.report({"ERROR"}, f"GANI folder missing: {gani_dir}")
            return {"CANCELLED"}
        name, actions = import_player(context, fmdl, gani_dir, frig, self.max_clips)
        self.report({"INFO"}, f"{name}: {len(actions)} actions. Switch them in Action Editor.")
        return {"FINISHED"}


class IMPORT_OT_mgsv_gani_folder(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.mgsv_gani_folder"
    bl_label = "Import MGSV GANI folder (actions)"
    filename_ext = ""
    directory: StringProperty(subtype="DIR_PATH")
    frig_path: StringProperty(name="FRIG", subtype="FILE_PATH")
    max_clips: IntProperty(name="Max clips (0=all)", default=0, min=0, max=10000)

    def execute(self, context):
        obj = context.object
        if obj is None or obj.type != "ARMATURE":
            self.report({"ERROR"}, "Select the sna2 armature first")
            return {"CANCELLED"}
        _ensure_fox()
        from fox.clip import evaluate_clip
        from fox.fmdl import read_skeleton
        from fox.frig import read_frig
        from fox.gani import read_gani

        fmdl = _repo() / "extracted" / "player" / "fpk" / "sna2_main0_def.fmdl"
        frig_path = self.frig_path or str(
            _repo() / "extracted" / "player" / "fpk" / "Assets" / "tpp" / "rig" / "frig" / "human_finger.frig"
        )
        skel = read_skeleton(fmdl)
        frig = read_frig(frig_path)
        files = sorted(Path(self.directory).glob("*.gani"))
        if self.max_clips > 0:
            files = files[: self.max_clips]
        for i, path in enumerate(files):
            gani = read_gani(str(path))
            clip = evaluate_clip(skel, gani, frig, name=path.stem)
            apply_clip(obj, clip, skel, frig)
        self.report({"INFO"}, f"{len(files)} actions. Action Editor dropdown lists them.")
        return {"FINISHED"}


def menu_fn(self, _context):
    self.layout.operator(IMPORT_OT_mgsv_player.bl_idname, text="MGSV Player (FMDL + GANI folder)")
    self.layout.operator(IMPORT_OT_mgsv_gani_folder.bl_idname, text="MGSV GANI folder (actions)")


def register():
    bpy.utils.register_class(IMPORT_OT_mgsv_player)
    bpy.utils.register_class(IMPORT_OT_mgsv_gani_folder)
    bpy.types.TOPBAR_MT_file_import.append(menu_fn)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_fn)
    bpy.utils.unregister_class(IMPORT_OT_mgsv_gani_folder)
    bpy.utils.unregister_class(IMPORT_OT_mgsv_player)


if __name__ == "__main__":
    register()
