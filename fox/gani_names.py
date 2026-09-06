"""Resolve GANI PathCode hashes to Fox clip names when the path is known."""

from __future__ import annotations

from pathlib import Path

from .hashing import PATH_MASK, hash_file_name

DEFAULT_DICT = Path(__file__).resolve().parent.parent / "dict" / "gani_gz.txt"

_names: dict[int, str] | None = None
_paths: dict[int, str] | None = None


def _load() -> None:
    global _names, _paths
    if _names is not None:
        return
    _names = {}
    _paths = {}
    if not DEFAULT_DICT.is_file():
        return
    for line in DEFAULT_DICT.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith(".gani"):
            line = line[:-5]
        key = hash_file_name(line)
        _paths[key] = line
        _names[key] = line.rsplit("/", 1)[-1]


def _path_hash(stem: str) -> int | None:
    text = stem.strip().lower()
    if text.endswith(".gani"):
        text = text[:-5]
    if not text or any(c not in "0123456789abcdef" for c in text.lstrip("b")):
        return None
    if not all(c in "0123456789abcdef" for c in text):
        return None
    return int(text, 16) & PATH_MASK


def action_name(stem: str) -> str:
    """Blender action name: clip basename if the path is known, else the hash stem."""
    _load()
    key = _path_hash(stem)
    if key is None:
        return stem
    return _names.get(key, stem)


def fox_path(stem: str) -> str | None:
    _load()
    key = _path_hash(stem)
    if key is None:
        return None
    return _paths.get(key)
