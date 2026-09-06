"""Fox PathCode hashes. GZ uses GzsTool v0.2 HashFileName (CityHash legacy)."""

from __future__ import annotations

from pathlib import Path

from .cityhash import cityhash64_with_seeds

SEED0 = 0x9AE16A3B2F90404F
PATH_MASK = 0xFFFFFFFFFFFF

# GzsTool v0.2 TypeExtensions. Index is packed at bits 52+.
TYPE_EXTENSIONS = {
    0: "",
    1: ".xml",
    2: ".json",
    3: ".ese",
    4: ".fxp",
    5: ".fpk",
    6: ".fpkd",
    7: ".fpkl",
    8: ".aib",
    9: ".frig",
    10: ".mtar",
    11: ".gani",
    12: ".evb",
    13: ".evf",
    14: ".ag.evf",
    15: ".cc.evf",
    16: ".fx.evf",
    17: ".sd.evf",
    18: ".vo.evf",
    19: ".fsd",
    20: ".fage",
    21: ".fago",
    22: ".fag",
    23: ".fagx",
    24: ".fagp",
    25: ".frdv",
    26: ".fdmg",
    27: ".des",
    28: ".fdes",
    29: ".aibc",
    30: ".mtl",
    31: ".fsml",
    32: ".fox",
    33: ".fox2",
    34: ".las",
    35: ".fstb",
    36: ".lua",
    37: ".fcnp",
    38: ".fcnpx",
    39: ".sub",
    40: ".fova",
    41: ".lad",
    42: ".lani",
    43: ".vfx",
    44: ".vfxbin",
    45: ".frt",
    46: ".gpfp",
    47: ".gskl",
    48: ".geom",
    49: ".tgt",
    50: ".path",
    51: ".fmdl",
    52: ".ftex",
    53: ".htre",
    54: ".tre2",
    55: ".grxla",
    56: ".grxoc",
    57: ".mog",
    58: ".pftxs",
    59: ".nav2",
    60: ".bnd",
    61: ".parts",
    62: ".phsd",
    63: ".ph",
    64: ".veh",
    65: ".sdf",
    66: ".sad",
    67: ".sim",
    68: ".fclo",
    69: ".clo",
    70: ".lng",
    71: ".uig",
    72: ".uil",
    73: ".uif",
    74: ".uia",
    75: ".fnt",
    76: ".utxl",
    77: ".uigb",
    78: ".vfxdb",
    79: ".rbs",
    80: ".aia",
    81: ".aim",
    82: ".aip",
    83: ".aigc",
    84: ".aig",
    85: ".ait",
    86: ".fsm",
    87: ".obr",
    88: ".obrb",
    89: ".lpsh",
    90: ".sani",
    91: ".rdb",
    92: ".phep",
    93: ".simep",
    94: ".atsh",
    95: ".txt",
    96: ".1.ftexs",
    97: ".2.ftexs",
    98: ".3.ftexs",
    99: ".4.ftexs",
    100: ".5.ftexs",
    101: ".sbp",
    102: ".mas",
    103: ".rdf",
    104: ".wem",
    105: ".lba",
    106: ".uilb",
}

EXT_TO_TYPE = {ext: idx for idx, ext in TYPE_EXTENSIONS.items() if ext}


def hash_file_name(text: str) -> int:
    """GzsTool v0.2 HashFileName. Dictionary lines use this (no extension)."""
    raw = text.encode("ascii")
    seed1 = ((raw[0] << 16) + len(raw)) if raw else 0
    hashed = cityhash64_with_seeds(raw + b"\x00", SEED0, seed1)
    return hashed & PATH_MASK


def extension_id_from_hash(full_hash: int) -> int:
    return (full_hash >> 52) & 0xFFFF


def path_hash_from_hash(full_hash: int) -> int:
    return full_hash & PATH_MASK


def extension_from_hash(full_hash: int) -> str:
    return TYPE_EXTENSIONS.get(extension_id_from_hash(full_hash), "")


class Dictionary:
    def __init__(self) -> None:
        self.by_hash: dict[int, str] = {}

    def load(self, path: str | Path) -> None:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                self.by_hash[hash_file_name(line)] = line

    def name_for(self, full_hash: int) -> tuple[str, bool]:
        path_hash = path_hash_from_hash(full_hash)
        ext = extension_from_hash(full_hash)
        base = self.by_hash.get(path_hash)
        if base is None:
            return f"{path_hash:x}{ext}", False
        return f"{base}{ext}", True
