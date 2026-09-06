"""CLI: python3 -m fox <command> ..."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .fmdl import read_skeleton
from .fpk import extract_fpk, parse_fpk, read_fpk
from .frig import read_frig
from .g0s import extract_entry, open_g0s, read_entry
from .gani import gani_to_dict, read_gani
from .hashing import Dictionary, extension_id_from_hash
from .mtar import extract_mtar, read_mtar
from .smd import write_smd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DICT = ROOT / "dict" / "gzs_dictionary.txt"
DEFAULT_GAME = Path(
    "/home/username/.local/share/Steam/steamapps/common/Metal Gear Solid Ground Zeroes"
)
PLAYER_EXTS = {".mtar", ".frig", ".fmdl", ".gani", ".fpk", ".fpkd", ".mog", ".parts"}
PLAYER_HINTS = (
    "player",
    "sna2",
    "sna0",
    "plparts",
    "TppGzPlayer",
    "motion",
)


def _load_dict(path: Path | None) -> Dictionary:
    d = Dictionary()
    p = path or DEFAULT_DICT
    if p.is_file():
        d.load(p)
    return d


def cmd_list(args: argparse.Namespace) -> int:
    d = _load_dict(Path(args.dictionary) if args.dictionary else None)
    archive = open_g0s(args.archive, d)
    named = sum(1 for e in archive.entries if e.named)
    print(f"{archive.path.name}: {len(archive.entries)} files, {named} named")
    for e in archive.entries:
        if args.filter and args.filter.lower() not in e.name.lower():
            continue
        flag = "" if e.named else "  [hash]"
        print(f"{e.size:9}  {e.name}{flag}")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    d = _load_dict(Path(args.dictionary) if args.dictionary else None)
    archive = open_g0s(args.archive, d)
    dest = Path(args.out)
    n = 0
    for e in archive.entries:
        if args.filter and args.filter.lower() not in e.name.lower():
            continue
        extract_entry(archive, e, dest)
        n += 1
        print(e.name)
    print(f"wrote {n} files -> {dest}")
    return 0


def cmd_unpack_fpk(args: argparse.Namespace) -> int:
    fpk = read_fpk(args.file)
    written = extract_fpk(fpk, Path(args.out))
    print(f"fpk entries {len(written)} -> {args.out}")
    return 0


def cmd_unpack_mtar(args: argparse.Namespace) -> int:
    mtar = read_mtar(args.file)
    written = extract_mtar(mtar, Path(args.out))
    print(f"mtar {mtar.signature:#x} clips {len(written)} -> {args.out}")
    return 0


def cmd_dump_gani(args: argparse.Namespace) -> int:
    g = read_gani(args.file)
    json.dump(gani_to_dict(g), sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def cmd_to_blend(args: argparse.Namespace) -> int:
    import shutil
    import subprocess

    blender = (
        args.blender
        or shutil.which("blender")
        or "/home/username/Tools/blender-5.2.1-linux-x64/blender"
        or "/home/username/Tools/blender-4.5.3-linux-x64/blender"
    )
    if not Path(blender).is_file():
        print("blender not found", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    script = Path("/tmp/mgsv_to_blend.py")
    script.write_text(
        "\n".join(
            [
                "import sys",
                f"sys.path.insert(0, {str(ROOT / 'blender_addon')!r})",
                f"sys.path.insert(0, {str(ROOT)!r})",
                "import bpy",
                "for obj in list(bpy.data.objects):",
                "    bpy.data.objects.remove(obj, do_unlink=True)",
                "from io_import_mgsv import import_player",
                f"name, actions = import_player(bpy.context, {args.fmdl!r}, {args.gani_dir!r}, {args.frig!r}, {args.max})",
                "print('object', name, 'actions', len(actions))",
                f"bpy.ops.wm.save_as_mainfile(filepath={str(out)!r})",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    cmd = [blender, "-b", "-noaudio", "--python", str(script)]
    print(" ".join(cmd))
    return subprocess.call(cmd)


def cmd_to_smd(args: argparse.Namespace) -> int:
    skel = read_skeleton(args.fmdl)
    gani = read_gani(args.gani)
    frig = read_frig(args.frig) if args.frig else None
    write_smd(skel, gani, Path(args.out), frig)
    print(f"smd {args.out} bones={len(skel.bones)} frames={gani.motion.frame_count if gani.motion else 0}")
    return 0


def _want_player(name: str) -> bool:
    lower = name.lower()
    if any(h.lower() in lower for h in PLAYER_HINTS):
        return True
    return Path(name).suffix.lower() in {".mtar", ".frig", ".fmdl", ".gani"}


def cmd_extract_player(args: argparse.Namespace) -> int:
    game = Path(args.game)
    dest = Path(args.out)
    d = _load_dict(Path(args.dictionary) if args.dictionary else None)
    g0s_path = Path(args.g0s) if args.g0s else game / "data_02.g0s"
    archive = open_g0s(g0s_path, d)
    fpk_root = dest / "fpk"
    pulled: list[Path] = []
    for e in archive.entries:
        eid = extension_id_from_hash(e.hash)
        if eid not in (5, 6):
            continue
        data = read_entry(archive, e)
        try:
            fpk = parse_fpk(data, e.name)
        except ValueError as err:
            print(f"skip fpk {e.name}: {err}", file=sys.stderr)
            continue
        keep = [
            fe
            for fe in fpk.entries
            if _want_player(fe.name)
            or Path(fe.name).suffix.lower() in {".mtar", ".frig", ".fmdl", ".gani", ".mog"}
        ]
        if args.filter:
            keep = [fe for fe in keep if args.filter.lower() in fe.name.lower()]
        if not keep:
            continue
        for fe in keep:
            out = fpk_root / fe.name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data[fe.data_offset : fe.data_offset + fe.data_size])
            pulled.append(out)
            print(fe.name)
    mtar_root = dest / "mtar"
    for path in pulled:
        if path.suffix.lower() != ".mtar":
            continue
        try:
            mtar = read_mtar(path)
        except ValueError as err:
            print(f"skip mtar {path}: {err}", file=sys.stderr)
            continue
        n = extract_mtar(mtar, mtar_root / path.stem)
        print(f"mtar {path.name} -> {len(n)} gani")
    print(f"player extract {len(pulled)} files -> {dest}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python3 -m fox")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list", help="list g0s entries")
    s.add_argument("archive")
    s.add_argument("--filter", default="")
    s.add_argument("--dictionary")
    s.set_defaults(func=cmd_list)
    s = sub.add_parser("extract", help="extract g0s")
    s.add_argument("archive")
    s.add_argument("out")
    s.add_argument("--filter", default="")
    s.add_argument("--dictionary")
    s.set_defaults(func=cmd_extract)
    s = sub.add_parser("unpack-fpk")
    s.add_argument("file")
    s.add_argument("out")
    s.set_defaults(func=cmd_unpack_fpk)
    s = sub.add_parser("unpack-mtar")
    s.add_argument("file")
    s.add_argument("out")
    s.set_defaults(func=cmd_unpack_mtar)
    s = sub.add_parser("dump-gani")
    s.add_argument("file")
    s.set_defaults(func=cmd_dump_gani)
    s = sub.add_parser("to-smd")
    s.add_argument("--fmdl", required=True)
    s.add_argument("--gani", required=True)
    s.add_argument("--frig")
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_to_smd)
    s = sub.add_parser("to-blend", help="build a .blend with skeleton + GANI actions")
    s.add_argument("--fmdl", default=str(ROOT / "extracted/player/fpk/sna2_main0_def.fmdl"))
    s.add_argument("--frig", default=str(ROOT / "extracted/player/fpk/Assets/tpp/rig/frig/human_finger.frig"))
    s.add_argument("--gani-dir", default=str(ROOT / "extracted/player/mtar/TppGzPlayer_layers"))
    s.add_argument("--out", default=str(ROOT / "extracted/player/sna2.blend"))
    s.add_argument("--max", type=int, default=32, help="0 = all clips")
    s.add_argument("--blender", default="")
    s.set_defaults(func=cmd_to_blend)
    s = sub.add_parser("extract-player", help="pull player mtar/fmdl/frig from GZ install")
    s.add_argument("--game", default=str(DEFAULT_GAME))
    s.add_argument("--g0s", default="")
    s.add_argument("--out", default=str(ROOT / "extracted" / "player"))
    s.add_argument("--filter", default="")
    s.add_argument("--dictionary")
    s.set_defaults(func=cmd_extract_player)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
