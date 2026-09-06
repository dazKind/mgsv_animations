import unittest

from fox.cityhash import K2, cityhash64
from fox.crypto import deencrypt_qar
from fox.hashing import hash_file_name


class CityHashTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(cityhash64(b""), K2)


class PathDiscoveryTests(unittest.TestCase):
    def test_default_game_is_under_home(self):
        from pathlib import Path

        from fox.__main__ import DEFAULT_GAME

        home = str(Path.home())
        self.assertTrue(str(DEFAULT_GAME).startswith(home))
        self.assertNotIn("/home/mib/Development", str(DEFAULT_GAME))
        self.assertNotIn("/home/username", str(DEFAULT_GAME))

    def test_sources_have_no_hardcoded_homes(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        bad = []
        for folder in ("fox", "blender_addon"):
            for path in (root / folder).rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                if "/home/mib" in text or "/home/username" in text:
                    bad.append(str(path.relative_to(root)))
        self.assertEqual(bad, [])


class HashFileNameTests(unittest.TestCase):
    def test_stable(self):
        a = hash_file_name("/Assets/tpp/motion/mtar/player/TppGzPlayer_layers")
        b = hash_file_name("/Assets/tpp/motion/mtar/player/TppGzPlayer_layers")
        self.assertEqual(a, b)
        self.assertLess(a, 1 << 48)


class GaniNameTests(unittest.TestCase):
    def test_known_clip_uses_basename(self):
        from fox.gani_names import action_name, fox_path

        self.assertEqual(action_name("b0109dae79c7f5"), "snapnon_q_idl_l")
        self.assertTrue(fox_path("b0109dae79c7f5").endswith("snapnon_q_idl_l"))

    def test_unknown_clip_keeps_hash_stem(self):
        from fox.gani_names import action_name

        self.assertEqual(action_name("b095d9d20e8988"), "b095d9d20e8988")


class QarCryptoTests(unittest.TestCase):
    def test_roundtrip_xor(self):
        raw = bytes(range(64))
        once = deencrypt_qar(raw, 3)
        twice = deencrypt_qar(once, 3)
        self.assertEqual(bytes(twice), raw)


if __name__ == "__main__":
    unittest.main()
