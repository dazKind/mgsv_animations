"""Fox FPK/FPKD. GZ layout from GzsTool v0.2 (magic suffix 'ste', not TPP 'win')."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FpkEntry:
    name: str
    data_offset: int
    data_size: int
    md5: bytes


@dataclass
class FpkFile:
    path: Path
    is_fpkd: bool
    entries: list[FpkEntry]
    references: list[str]


def _clean_fpk_name(name: str) -> str:
    name = name.replace("\\", "/")
    colon = name.find(":")
    if colon != -1:
        name = name[colon + 1 :]
    for marker in ("/Assets/", "Assets/"):
        idx = name.find(marker)
        if idx >= 0:
            name = name[idx:].lstrip("/")
            break
    else:
        name = name.split("/")[-1]
    return name.lstrip("/")


def _read_cstr(data: bytes, offset: int, length: int) -> str:
    chunk = data[offset : offset + length]
    return chunk.split(b"\x00", 1)[0].decode("latin-1", errors="replace")


def parse_fpk(data: bytes, path: str | Path = "") -> FpkFile:
    path = Path(path) if path else Path("memory.fpk")
    if len(data) < 48:
        raise ValueError("fpk too small")
    magic = data[:10]
    if magic[:6] != b"foxfpk":
        raise ValueError(f"not an fpk: {magic!r}")
    is_fpkd = magic[6:7] == b"d"
    file_count, ref_count = struct.unpack_from("<II", data, 36)
    pos = 48
    entries: list[FpkEntry] = []
    for _ in range(file_count):
        data_offset, _, data_size, _ = struct.unpack_from("<IIII", data, pos)
        str_off, _, str_len, _ = struct.unpack_from("<IIII", data, pos + 16)
        md5 = data[pos + 32 : pos + 48]
        name = _clean_fpk_name(_read_cstr(data, str_off, str_len))
        entries.append(
            FpkEntry(name=name, data_offset=data_offset, data_size=data_size, md5=md5)
        )
        pos += 48
    references: list[str] = []
    for _ in range(ref_count):
        str_off, _, str_len, _ = struct.unpack_from("<IIII", data, pos)
        references.append(_read_cstr(data, str_off, str_len))
        pos += 16
    return FpkFile(path=path, is_fpkd=is_fpkd, entries=entries, references=references)


def read_fpk(path: str | Path) -> FpkFile:
    path = Path(path)
    return parse_fpk(path.read_bytes(), path)


def extract_fpk_data(data: bytes, fpk: FpkFile, dest_root: Path) -> list[Path]:
    dest_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for entry in fpk.entries:
        out = dest_root / entry.name.lstrip("/")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data[entry.data_offset : entry.data_offset + entry.data_size])
        written.append(out)
    return written


def extract_fpk(fpk: FpkFile, dest_root: Path) -> list[Path]:
    return extract_fpk_data(fpk.path.read_bytes(), fpk, dest_root)
