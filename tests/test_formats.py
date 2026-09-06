import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FMDL = ROOT / "extracted/player/fpk/sna2_main0_def.fmdl"
GANI_DIR = ROOT / "extracted/player/mtar/TppGzPlayer_layers"
FRIG = ROOT / "extracted/player/fpk/Assets/tpp/rig/frig/human_finger.frig"


def _in_root(clip, frame, p):
    """Point in character space (undo ROOT yaw/loc)."""
    from fox.clip import _qrot, _sample

    rq = (0.0, 0.0, 0.0, 1.0)
    off = (0.0, 0.0, 0.0)
    root = clip.tracks.get("ROOT")
    if root and root.rot:
        sampled = _sample(root.rot, frame)
        if sampled and len(sampled) >= 4:
            rq = sampled[:4]
    if root and root.loc:
        sampled = _sample(root.loc, frame)
        if sampled and len(sampled) >= 3:
            off = sampled[:3]
    v = (p[0] - off[0], p[1] - off[1], p[2] - off[2])
    return _qrot((-rq[0], -rq[1], -rq[2], rq[3]), v)


@unittest.skipUnless(FMDL.is_file(), "run extract-player first")
class FormatTests(unittest.TestCase):
    def test_fmdl_bones(self):
        from fox.fmdl import read_skeleton

        skel = read_skeleton(FMDL)
        names = [b.name for b in skel.bones]
        self.assertGreater(len(skel.bones), 50)
        self.assertIn("SKL_000_WAIST", names)
        self.assertIn("SKL_013_LHAND", names)

    def test_gani_unit_tracks(self):
        from fox.gani import read_gani

        gani = next(GANI_DIR.glob("*.gani"))
        g = read_gani(str(gani))
        self.assertIsNotNone(g.motion)
        self.assertEqual(len(g.motion.units), 18)
        self.assertGreater(g.motion.frame_count, 0)
        self.assertTrue(any(s.keys for u in g.motion.units for s in u.segments))

    def test_frig_units(self):
        from fox.frig import read_frig

        frig = read_frig(FRIG)
        self.assertEqual(len(frig.units), 18)

    def test_packed_quat_identity_and_unit(self):
        from fox.gani import _quat_from_packed, read_gani

        ident = _quat_from_packed(0, 0, 0, 0, 0, 0, 12)
        self.assertAlmostEqual(ident[0], 0.0, places=6)
        self.assertAlmostEqual(ident[1], 0.0, places=6)
        self.assertAlmostEqual(ident[2], 0.0, places=6)
        self.assertAlmostEqual(ident[3], 1.0, places=6)

        gani = next(GANI_DIR.glob("*.gani"))
        g = read_gani(str(gani))
        norms = []
        for unit in g.motion.units:
            for seg in unit.segments:
                if not seg.keys or not isinstance(seg.keys[0].value, tuple):
                    continue
                if len(seg.keys[0].value) != 4:
                    continue
                for key in seg.keys:
                    x, y, z, w = key.value
                    norms.append(abs((x * x + y * y + z * z + w * w) ** 0.5 - 1.0))
        self.assertTrue(norms)
        self.assertLess(max(norms), 1e-5)

    def test_clip_ik_in_fmdl_space(self):
        from fox.clip import evaluate_clip
        from fox.fmdl import read_skeleton
        from fox.frig import read_frig
        from fox.gani import read_gani

        skel = read_skeleton(FMDL)
        frig = read_frig(FRIG)
        g = read_gani(str(next(GANI_DIR.glob("*.gani"))))
        clip = evaluate_clip(skel, g, frig, name="t")
        self.assertIn("IK_SKL_032_LFOOT", clip.tracks)
        foot = clip.tracks["IK_SKL_032_LFOOT"].loc[0][1]
        self.assertLess(foot[1], 0.4)
        waist = clip.tracks["SKL_000_WAIST"].loc
        if waist:
            self.assertLess(abs(waist[0][1][1]), 0.6)

    def test_solve_joints_standing_laterality(self):
        from fox.clip import evaluate_clip, solve_joints
        from fox.fmdl import read_skeleton
        from fox.frig import read_frig
        from fox.gani import read_gani

        skel = read_skeleton(FMDL)
        frig = read_frig(FRIG)
        path = GANI_DIR / "b081ddd62c1ffc.gani"
        if not path.is_file():
            self.skipTest("standing clip missing")
        g = read_gani(str(path))
        clip = evaluate_clip(skel, g, frig, name="stand")
        j = solve_joints(skel, clip, frig, 0)
        hip = j["SKL_000_WAIST"]
        head = _in_root(clip, 0, j["SKL_004_HEAD"])
        lh = _in_root(clip, 0, j["SKL_013_LHAND"])
        rh = _in_root(clip, 0, j["SKL_023_RHAND"])
        lf = j["SKL_032_LFOOT"]
        rf = j["SKL_042_RFOOT"]
        self.assertGreater(j["SKL_004_HEAD"][1] - hip[1], 0.4)
        self.assertLess(abs(head[0]), 0.12)
        self.assertGreater(lh[0], 0.05)
        self.assertLess(rh[0], lh[0])
        self.assertLess(lf[1], hip[1] - 0.5)
        self.assertLess(rf[1], hip[1] - 0.5)

    def test_solve_joints_ik_keeps_foot_toe_length(self):
        from fox.clip import evaluate_clip, solve_joints
        from fox.fmdl import read_skeleton
        from fox.frig import read_frig
        from fox.gani import read_gani

        skel = read_skeleton(FMDL)
        frig = read_frig(FRIG)
        path = GANI_DIR / "b081ddd62c1ffc.gani"
        if not path.is_file():
            self.skipTest("standing clip missing")
        g = read_gani(str(path))
        clip = evaluate_clip(skel, g, frig, name="stand")
        j = solve_joints(skel, clip, frig, 0)
        bind = {b.name: b.world_pos for b in skel.bones}

        def dist(a, b):
            return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5

        for foot, toe in (("SKL_032_LFOOT", "SKL_033_LTOE"), ("SKL_042_RFOOT", "SKL_043_RTOE")):
            bind_len = dist(bind[foot], bind[toe])
            pose_len = dist(j[foot], j[toe])
            self.assertAlmostEqual(bind_len, pose_len, places=3, msg=f"{foot}->{toe}")

    def test_slerp_double_cover_stays_short(self):
        from fox.clip import _slerp

        a = (0.0, 0.0, 0.0, 1.0)
        b = (0.0, 0.0, 0.0, -1.0)
        mid = _slerp(a, b, 0.5)
        n = (mid[0] ** 2 + mid[1] ** 2 + mid[2] ** 2 + mid[3] ** 2) ** 0.5
        self.assertAlmostEqual(n, 1.0, places=6)
        self.assertGreater(mid[3], 0.9)

    def test_finger_tracks_keep_bind_length(self):
        from fox.clip import evaluate_clip, solve_joints
        from fox.fmdl import read_skeleton
        from fox.frig import read_frig
        from fox.gani import read_gani

        skel = read_skeleton(FMDL)
        frig = read_frig(FRIG)
        path = GANI_DIR / "b081ddd62c1ffc.gani"
        if not path.is_file():
            self.skipTest("standing clip missing")
        clip = evaluate_clip(skel, read_gani(str(path)), frig, name="stand")
        self.assertIn("SKL_101_LF10", clip.tracks)
        self.assertTrue(clip.tracks["SKL_101_LF10"].rot)
        j = solve_joints(skel, clip, frig, 0)
        bind = {b.name: b.world_pos for b in skel.bones}

        def dist(a, b):
            return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5

        err = 0.0
        for b in skel.bones:
            if not (b.name.startswith("SKL_1") or b.name.startswith("SKL_2")):
                continue
            if b.parent < 0:
                continue
            parent = skel.bones[b.parent].name
            err = max(err, abs(dist(bind[parent], bind[b.name]) - dist(j[parent], j[b.name])))
        self.assertLess(err, 1e-4)

    def test_solve_joints_root_y_keeps_feet_below_hip(self):
        from fox.clip import evaluate_clip, solve_joints
        from fox.fmdl import read_skeleton
        from fox.frig import read_frig
        from fox.gani import read_gani

        path = GANI_DIR / "b015a285aaffd4.gani"
        if not path.is_file():
            self.skipTest("crouch clip missing")
        skel = read_skeleton(FMDL)
        frig = read_frig(FRIG)
        clip = evaluate_clip(skel, read_gani(str(path)), frig, name="crouch")
        j0 = solve_joints(skel, clip, frig, 0)
        j42 = solve_joints(skel, clip, frig, 42)
        self.assertLess(j0["SKL_000_WAIST"][1], -0.2)
        self.assertGreater(j0["SKL_004_HEAD"][1] - j0["SKL_000_WAIST"][1], 0.15)
        self.assertLess(j0["SKL_032_LFOOT"][1], j0["SKL_000_WAIST"][1])
        self.assertGreater(j42["SKL_000_WAIST"][1], j0["SKL_000_WAIST"][1] + 0.3)
        self.assertLess(j42["SKL_032_LFOOT"][1], j42["SKL_000_WAIST"][1] - 0.2)
        self.assertGreater(j42["SKL_004_HEAD"][1], j0["SKL_004_HEAD"][1] + 0.3)

    def test_crouch_elbows_bend_outward(self):
        from fox.clip import evaluate_clip, solve_joints
        from fox.fmdl import read_skeleton
        from fox.frig import read_frig
        from fox.gani import read_gani

        path = GANI_DIR / "b015a285aaffd4.gani"
        if not path.is_file():
            self.skipTest("crouch clip missing")
        skel = read_skeleton(FMDL)
        frig = read_frig(FRIG)
        clip = evaluate_clip(skel, read_gani(str(path)), frig, name="crouch")
        j = solve_joints(skel, clip, frig, 40)
        hip = j["SKL_000_WAIST"]

        def inward_dot(upper, mid, end):
            p0, p1, p2 = j[upper], j[mid], j[end]
            ax, ay, az = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
            al = (ax * ax + ay * ay + az * az) ** 0.5 or 1.0
            ax, ay, az = ax / al, ay / al, az / al
            tx, ty, tz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
            proj = tx * ax + ty * ay + tz * az
            bx, by, bz = tx - ax * proj, ty - ay * proj, tz - az * proj
            hx, hy, hz = hip[0] - p0[0], hip[1] - p0[1], hip[2] - p0[2]
            hp = hx * ax + hy * ay + hz * az
            return bx * (hx - ax * hp) + by * (hy - ay * hp) + bz * (hz - az * hp)

        self.assertLess(inward_dot("SKL_011_LUARM", "SKL_012_LFARM", "SKL_013_LHAND"), 0.0)
        self.assertLess(inward_dot("SKL_021_RUARM", "SKL_022_RFARM", "SKL_023_RHAND"), 0.0)

    def test_jump_knees_bend_forward(self):
        from fox.clip import evaluate_clip, solve_joints
        from fox.fmdl import read_skeleton
        from fox.frig import read_frig
        from fox.gani import read_gani

        path = GANI_DIR / "b081ddd62c1ffc.gani"
        if not path.is_file():
            self.skipTest("standing clip missing")
        skel = read_skeleton(FMDL)
        frig = read_frig(FRIG)
        clip = evaluate_clip(skel, read_gani(str(path)), frig, name="stand")
        j = solve_joints(skel, clip, frig, 0)

        def bend_z(upper, mid, end):
            p0 = _in_root(clip, 0, j[upper])
            p1 = _in_root(clip, 0, j[mid])
            p2 = _in_root(clip, 0, j[end])
            ax, ay, az = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
            al = (ax * ax + ay * ay + az * az) ** 0.5 or 1.0
            ax, ay, az = ax / al, ay / al, az / al
            tx, ty, tz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
            proj = tx * ax + ty * ay + tz * az
            return tz - az * proj

        self.assertGreater(bend_z("SKL_030_LTHIGH", "SKL_031_LLEG", "SKL_032_LFOOT"), 0.0)
        self.assertGreater(bend_z("SKL_040_RTHIGH", "SKL_041_RLEG", "SKL_042_RFOOT"), 0.0)

    def test_turn_yaws_chest_with_root(self):
        from fox.clip import evaluate_clip, solve_joints
        from fox.fmdl import read_skeleton
        from fox.frig import read_frig
        from fox.gani import read_gani

        path = GANI_DIR / "b0a96adc14a984.gani"
        if not path.is_file():
            self.skipTest("turn clip missing")
        skel = read_skeleton(FMDL)
        frig = read_frig(FRIG)
        clip = evaluate_clip(skel, read_gani(str(path)), frig, name="turn")
        j0 = solve_joints(skel, clip, frig, 0)
        j1 = solve_joints(skel, clip, frig, clip.frame_count)

        def chest_yaw(j):
            s, c = j["SKL_001_SPINE"], j["SKL_002_CHEST"]
            return math.atan2(c[0] - s[0], c[2] - s[2])

        delta = abs(chest_yaw(j1) - chest_yaw(j0))
        if delta > math.pi:
            delta = 2 * math.pi - delta
        self.assertGreater(delta, math.radians(60))

    def test_crouch_elbow_does_not_jump(self):
        from fox.clip import evaluate_clip, solve_joints
        from fox.fmdl import read_skeleton
        from fox.frig import read_frig
        from fox.gani import read_gani

        path = GANI_DIR / "b015a285aaffd4.gani"
        if not path.is_file():
            self.skipTest("crouch clip missing")
        skel = read_skeleton(FMDL)
        frig = read_frig(FRIG)
        clip = evaluate_clip(skel, read_gani(str(path)), frig, name="crouch")
        prev = None
        last = None
        for frame in range(0, clip.frame_count + 1):
            j = solve_joints(skel, clip, frig, frame, prev_pos=prev)
            e = j["SKL_012_LFARM"]
            if last is not None:
                d = ((e[0] - last[0]) ** 2 + (e[1] - last[1]) ** 2 + (e[2] - last[2]) ** 2) ** 0.5
                self.assertLess(d, 0.12, msg=f"L elbow jump at frame {frame}")
            last = e
            prev = j

    def test_reload_elbows_bend_down(self):
        from fox.clip import evaluate_clip, solve_joints
        from fox.fmdl import read_skeleton
        from fox.frig import read_frig
        from fox.gani import read_gani

        path = GANI_DIR / "b095d9d20e8988.gani"
        if not path.is_file():
            self.skipTest("reload clip missing")
        skel = read_skeleton(FMDL)
        frig = read_frig(FRIG)
        clip = evaluate_clip(skel, read_gani(str(path)), frig, name="reload")
        j = solve_joints(skel, clip, frig, 0)
        hip = j["SKL_000_WAIST"]

        def planar_y(upper, mid, end):
            p0, p1, p2 = j[upper], j[mid], j[end]
            ax, ay, az = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
            al = (ax * ax + ay * ay + az * az) ** 0.5 or 1.0
            ax, ay, az = ax / al, ay / al, az / al
            tx, ty, tz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
            proj = tx * ax + ty * ay + tz * az
            return ty - ay * proj

        def inward_dot(upper, mid, end):
            p0, p1, p2 = j[upper], j[mid], j[end]
            ax, ay, az = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
            al = (ax * ax + ay * ay + az * az) ** 0.5 or 1.0
            ax, ay, az = ax / al, ay / al, az / al
            tx, ty, tz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
            proj = tx * ax + ty * ay + tz * az
            bx, by, bz = tx - ax * proj, ty - ay * proj, tz - az * proj
            hx, hy, hz = hip[0] - p0[0], hip[1] - p0[1], hip[2] - p0[2]
            hp = hx * ax + hy * ay + hz * az
            return bx * (hx - ax * hp) + by * (hy - ay * hp) + bz * (hz - az * hp)

        self.assertLess(planar_y("SKL_011_LUARM", "SKL_012_LFARM", "SKL_013_LHAND"), 0.0)
        self.assertLess(planar_y("SKL_021_RUARM", "SKL_022_RFARM", "SKL_023_RHAND"), 0.0)
        self.assertLess(inward_dot("SKL_011_LUARM", "SKL_012_LFARM", "SKL_013_LHAND"), 0.02)
        self.assertLess(inward_dot("SKL_021_RUARM", "SKL_022_RFARM", "SKL_023_RHAND"), 0.02)
