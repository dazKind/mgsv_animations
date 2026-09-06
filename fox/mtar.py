"""MTAR Type 1 (Ground Zeroes). Signature 0x0BFFA89C."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

GZ_MTAR_MAGIC = 0x0BFFA89C
TPP_MTAR_MAGIC = 0x0C012B72
GANI_HASH_BIAS = 0xFC50000000000000


@dataclass
class MtarEntry:
    hash: int
    offset: int
    size: int
    name: str


@dataclass
class MtarFile:
    path: Path
    signature: int
    bone_groups: int
    bone_groups2: int
    entries: list[MtarEntry]


def _gani_name(hashed: int, dictionary: dict[int, str] | None) -> str:
    # Wiki: subtract 0xFC50000000000000 from listed hash to get filename.
    raw = hashed
    if hashed >= GANI_HASH_BIAS:
        raw = hashed - GANI_HASH_BIAS
    if dictionary and hashed in dictionary:
        return dictionary[hashed]
    if dictionary and raw in dictionary:
        return dictionary[raw]
    return f"{raw:x}.gani"


def read_mtar(path: str | Path, name_dict: dict[int, str] | None = None) -> MtarFile:
    path = Path(path)
    data = path.read_bytes()
    if len(data) < 0x20:
        raise ValueError("mtar too small")
    signature, file_count = struct.unpack_from("<II", data, 0)
    bone_groups, bone_groups2 = struct.unpack_from("<QQ", data, 8)
    if signature not in (GZ_MTAR_MAGIC, TPP_MTAR_MAGIC):
        raise ValueError(f"unknown mtar signature 0x{signature:08x}")
    entries: list[MtarEntry] = []
    pos = 0x20
    for _ in range(file_count):
        hashed, offset, size = struct.unpack_from("<QII", data, pos)
        entries.append(
            MtarEntry(
                hash=hashed,
                offset=offset,
                size=size,
                name=_gani_name(hashed, name_dict),
            )
        )
        pos += 16
    return MtarFile(
        path=path,
        signature=signature,
        bone_groups=bone_groups,
        bone_groups2=bone_groups2,
        entries=entries,
    )


def extract_mtar(mtar: MtarFile, dest_root: Path) -> list[Path]:
    blob = mtar.path.read_bytes()
    dest_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for entry in mtar.entries:
        name = entry.name
        if not name.endswith(".gani"):
            name += ".gani"
        out = dest_root / name.lstrip("/")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(blob[entry.offset : entry.offset + entry.size])
        written.append(out)
    return written
