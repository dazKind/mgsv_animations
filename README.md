# MGSV Ground Zeroes - Animation Tools

Python 3 tools for **reading** Metal Gear Solid V: Ground Zeroes (Fox Engine)
player animation data and importing it into Blender. Reads the FMDL skeleton,
GANI clips, and FRIG rig, solves two-bone IK for the arms and legs, and
bakes Blender actions (or Source SMD).

GANI write-back is not supported.

## Layout

- `fox/` - format readers + CLI (`python3 -m fox`)
  - `gani` motion clips, `fmdl` skeleton, `frig` rig, `g0s`/`fpk`/`mtar` archives
  - `clip` - maps a clip onto bones and runs the two-bone IK solver
  - `gani_names` - PathCode lookup for the few recovered clip names
  - `smd` - Source SMD writer
- `blender_addon/io_import_mgsv/` - Blender import addon (File > Import)
- `tests/` - unittest suite
- `dict/gzs_dictionary.txt` - hash dictionary for named archive entries
- `dict/gani_gz.txt` - recovered GANI paths (Fox PathCode, no `.gani` suffix)
- `extracted/player/` - extracted game data and generated `.blend` files

## Quick start

```bash
# pull player data from a GZ install
python3 -m fox extract-player

# build a .blend with the skeleton + all motion clips (2406 actions)
python3 -m fox to-blend --max 0 --out extracted/player/sna2_all.blend

# one clip to Source SMD
python3 -m fox to-smd --gani <clip.gani> --out <clip.smd>
```

Existing `.blend` files keep their baked actions until you re-import
(File > Import > MGSV GANI folder, or `to-blend`). The solver in `fox/clip.py`
is what a new bake uses.

## Pose solver

Fox identity-rest FK, then two-bone IK. GANI stores positions for the
**end effectors** (hands, feet) and ROOT - not for the elbow or knee.
FRIG marks each limb as a two-bone chain, so the mid joint is solved at
import time (not a Blender IK constraint). Keyframes are loc+rot per bone.

**ROOT** is locomotion: XYZ in metres, plus yaw. The FMDL root is the waist.
Waist rotation is `ROOT × waist`. **ORIENTATION** bones (spine, chest, neck,
head, and the hand/foot effectors) are character space: `ROOT × q`. Using `q`
alone leaves the spine facing the old way on turns. Multiplying by the waist
parent restacks the crouch fold. IK targets are already in world space
(they already include the turn).

**Bend direction** is body space, not a fixed world pole:

- knees: parent-frame forward (`+Z`)
- elbows: parent-frame out-back plus a half world-down bias, so a
  forward-reaching arm (reload) drops the elbow instead of IK-ing it up

`prev_mid` is only a fallback when that projection is degenerate.

Packed GANI quats are theta + barycentric axis (QuatAnim12/13/15), not xyz+w.

## Clip names

MTAR stores GANI by PathCode hash (`b0…`). Most Ground Zeroes player paths
were never recovered. `dict/gani_gz.txt` holds the known ones (~50 of 2406).
The addon names those actions by the Fox clip id (`snapnon_s_idl_l`) and
stores `fox_hash` / `fox_path` on the Action. Unknown clips keep the hash
stem. Add a path (no `.gani`) to the dict to resolve more names on the next
import.

`snap` = player, `non` = unarmed, `s/q/c` = stand / squat / crawl.

## Why a custom IK solver

- the pipeline **bakes keyframes**, so the solve must run while importing
- the **bend follows the body** (root yaw / chest facing), not a fixed world
  pole - a fixed pole inverts elbows and knees on turns and crouches
- previous-frame mid is only used when the bend projection is degenerate

## CLI

| command | purpose |
|---|---|
| `list` | list entries in a `.g0s` archive |
| `extract` | extract a `.g0s` archive |
| `extract-player` | pull player `mtar`/`fmdl`/`frig` from a GZ install |
| `unpack-fpk` / `unpack-mtar` | unpack FPK / MTAR archives |
| `dump-gani` | dump one clip to JSON |
| `to-smd` | write one clip to Source SMD |
| `to-blend` | build a `.blend` with skeleton + GANI actions |

Run `python3 -m fox <command> -h` for options. `to-blend --max 0` = all clips.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Blender addon

Enable `Import MGSV FMDL / GANI` (0.8.2). File > Import offers:

- **MGSV Player (FMDL + GANI folder)** - build armature + import clips
- **MGSV GANI folder (actions)** - bake clips onto the selected `sna2` armature

Switch clips in the Action Editor. Playback is 30 fps. Re-import after a
solver change; old actions are not updated in place.

## Media
<img width="1271" height="720" alt="snapdam_s_die_idl_l" src="https://github.com/user-attachments/assets/135ab57b-fcaf-4222-84eb-968ea70a4192" />
<img width="1271" height="720" alt="ride-getout" src="https://github.com/user-attachments/assets/353e7193-a773-411f-bdc0-6c199c2236d2" />
<img width="1271" height="720" alt="grab-90" src="https://github.com/user-attachments/assets/76287874-56da-44bd-ad72-af38159baf55" />

## References and thanks

This work sits on years of Fox Engine reverse engineering by the MGSV
modding community. Formats, hashes, and dictionaries used here come from
that record. Thank you.

**Formats and templates**

- [kapuragu/FoxEngineTemplates](https://github.com/kapuragu/FoxEngineTemplates) - 010 Editor templates for GANI (QuatAnim12/13/15), FRIG, MTAR, MOG, FMDL
- [MGSV Modding Wiki](https://mgsvmoddingwiki.github.io/) - MTAR Type 1, PathCode notes, extension list
- [unknown321, MGSV technical notes](https://unknown321.github.io/mgsv_research/motions.html) - motion archives and playback

**Archives, hashes, dictionaries**

- [Atvaark/GzsTool](https://github.com/Atvaark/GzsTool) (v0.2) - Ground Zeroes `.g0s` / CityHash `HashFileName`
- [TinManTex/GzsTool](https://github.com/TinManTex/GzsTool) and [mgsv-lookup-strings](https://github.com/TinManTex/mgsv-lookup-strings) - PathCode dictionaries, including GZ GANI matches
- [TinManTex/MtarTool](https://github.com/TinManTex/MtarTool) - MTAR unpack; GANI listed hashes use bias `0xFC50000000000000`
- [emoose/MGSV-QAR-Dictionary-Project](https://github.com/emoose/MGSV-QAR-Dictionary-Project) - community QAR filename dictionary

**Unpack notes**

- MrDev / Modders Heaven GANI unpack - packed quat layout used alongside the FoxEngineTemplates QuatAnim docs

FoxEngineTemplates also credits Atvaark, BobDoleOwndU, Half Way Lambda,
HeartlessSeph, id-Daemon, Jayveer, and many others who mapped this engine
before this repo existed.
