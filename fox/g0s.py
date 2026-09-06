"""Ground Zeroes .g0s archive (GzsTool v0.2 GzsFile). Footer-based QAR."""

from __future__ import annotations

import mmap
import struct
from dataclasses import dataclass
from pathlib import Path

from .crypto import decrypt_g0s_payload
from .hashing import Dictionary

FOOTER_SIZE = 20
FOOTER_MAGIC1 = 0x71610000


@dataclass
class G0sEntry:
    hash: int
    offset_blocks: int
    size: int
    name: str
    named: bool

    @property
    def data_offset(self) -> int:
        return 16 * self.offset_blocks


@dataclass
class G0sArchive:
    path: Path
    entries: list[G0sEntry]
    footer_entry_count: int
    entry_block_offset: int


def _read_footer(mm: mmap.mmap) -> tuple[int, int]:
    if len(mm) < FOOTER_SIZE:
        raise ValueError("file too small for g0s footer")
    footer = mm[-FOOTER_SIZE:]
    entry_count, magic1, entry_block_offset, _magic2, footer_size = struct.unpack_from(
        "<iiiii", footer, 0
    )
    if footer_size != FOOTER_SIZE:
        raise ValueError(f"invalid g0s footer size {footer_size}")
    if magic1 != FOOTER_MAGIC1:
        raise ValueError(f"invalid g0s magic 0x{magic1:08x}")
    return entry_count, entry_block_offset


def open_g0s(path: str | Path, dictionary: Dictionary | None = None) -> G0sArchive:
    path = Path(path)
    with open(path, "rb") as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            entry_count, entry_block_offset = _read_footer(mm)
            table = 16 * entry_block_offset
            entries: list[G0sEntry] = []
            for i in range(entry_count):
                off = table + i * 16
                hashed, offset_blocks, size = struct.unpack_from("<QII", mm, off)
                if dictionary is not None:
                    name, named = dictionary.name_for(hashed)
                else:
                    from .hashing import extension_from_hash, path_hash_from_hash

                    name = f"{path_hash_from_hash(hashed):x}{extension_from_hash(hashed)}"
                    named = False
                entries.append(
                    G0sEntry(
                        hash=hashed,
                        offset_blocks=offset_blocks,
                        size=size,
                        name=name,
                        named=named,
                    )
                )
        finally:
            mm.close()
    return G0sArchive(
        path=path,
        entries=entries,
        footer_entry_count=entry_count,
        entry_block_offset=entry_block_offset,
    )


def read_entry(archive: G0sArchive, entry: G0sEntry) -> bytes:
    with open(archive.path, "rb") as fh:
        fh.seek(entry.data_offset)
        raw = fh.read(entry.size)
    if len(raw) != entry.size:
        raise ValueError(f"short read for {entry.name}")
    return decrypt_g0s_payload(raw, entry.offset_blocks)


def extract_entry(archive: G0sArchive, entry: G0sEntry, dest_root: Path) -> Path:
    data = read_entry(archive, entry)
    rel = entry.name.lstrip("/").replace("\\", "/")
    out = dest_root / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out
