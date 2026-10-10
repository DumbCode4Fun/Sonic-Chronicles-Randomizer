# Tooling

Layout follows the separation CLAUDE.md asks for: readers are isolated from writers,
and nothing here contains reverse-engineering logic that a future GUI would need to
duplicate — a GUI should drive `modbuild.py` with a profile, exactly as the CLI does.

## `tools/recon/` — readers (never write)

| Tool | Purpose |
|---|---|
| `nds_rom.py` | NDS header, FNT/FAT filesystem, overlay tables |
| `herf.py` | HERF archive + `erf.dict` filename recovery (DJB2) |
| `lz77.py` | `.small` wrapper: stored (`0x00`) and NDS LZ77 (`0x10`) |
| `twoda.py` | plain-text 2DA (`.itm`, `.spl`, `.2da`) |
| `gff4.py` | GFF4 (`.gff`, `.gda`, `.dlg`, `.gui`, `.plo`, `.are`, `.tlk`), incl. generics |
| `gda_dict.py` | recovers GDA column names from their CRC32 hashes |
| `disasm.py` | targeted ARM9 THUMB/ARM disassembly and BL-caller search (capstone) |
| `gdbstub.py` | GDB remote-protocol client for melonDS' debug stub — memory, registers, breakpoints, watchpoints, RAM search. Pure standard library, so no ARM toolchain to install |
| `gdbstub_selftest.py` | a fake stub that proves the protocol offline. The only test here that is not the build pipeline checking itself |
| `gdb_experiments.py` | the two ARM9 experiments, scripted: find the creature stat loader, and find the plot-flag block |

## `tools/build/` — writers

**`modbuild.py` is the entry point.** It takes a JSON profile from `profiles/` and
runs the whole pipeline: validate → edit → rebuild → verify → patch → report. Every
stage checks itself and the build aborts rather than emitting an unverified ROM.

Supporting layers, each usable on its own:

| Tool | Purpose |
|---|---|
| `rom_build.py` | NDS rebuild. Guarantees a no-op rebuild is **byte-identical** |
| `herf_write.py` | HERF repack (in-place if it fits, else append + repoint) |
| `tlk_write.py` | TLK string editing, preserving the original's string dedup |
| `twoda_write.py` | 2DA cell edits and row appends |
| `gda_write.py` | GDA integer-cell edits, string-cell edits (never rewrites a *shared* string in place) and row appends |
| `save_edit.py` | `.dsv` save editing **with correct checksum resealing** |
| `bps.py` | BPS patch creation/application (IPS cannot address a 128 MB ROM) |

### Features (the mod-builder layer)

A profile may carry a **`features`** block instead of raw edits. Each feature is
named and parameterised, and expands into exactly the same `edits` the hand-written
profiles use — so there is one apply/verify path and features cannot drift from it.

```json
{"features": {"level_cap": {"cap": 99},
              "pp_curve":  {"character": "Shadow", "bonus": 3},
              "custom_item": [{"item": 78, "name": "Chaos Driver",
                               "effects": {"POW": 8, "element": "lightning"}}]}}
```

`py modbuild.py --list-features` prints the registry. Every feature is marked
**confirmed in game** or **build-verified only**, and the build prints that marker
as it expands, so it is always visible which parts of a mod rest on observed
behaviour and which only on a verified build.

**Character swapping is deliberately not a feature.** It couples at least eleven
tables — creature identity, portrait prefix and the art payloads behind it, palette,
appearance, team/combat portraits, `combo.GDA` ownership, boss-specific move rows,
progression, movement level, TLK names versus dialogue, and squad appearance — and
that list grew by five entries in a single session. Encoding a model we know to be
incomplete would bake today's blind spots into the tool, so it stays a hand-written
profile until the coupling map stops growing.

### Profile inheritance

A profile may build on another:

```json
{"extends": "ultimate_lifeform.json",
 "features": {"movement_slots": [{"character": "Shadow", "slot": 2, "ability": "fly"}]}}
```

The parent's edits and features apply **first**, so the child wins wherever both touch the
same thing — the same precedence features have over hand-written edits. This is what lets a
small generated profile extend a large hand-written one such as the Shadow Mode work, rather
than the two being mutually exclusive. Circular references and missing parents both raise.

### GUI

`tools/gui/modpack_maker.py` is a Tkinter front end holding **no reverse-engineering logic**,
per CLAUDE.md. It reads `features.REGISTRY` to discover what exists, reads the ROM through
`tools/gui/gamedata.py` purely to *display* current values, writes an ordinary profile, and
shells out to `modbuild.py`. Anything it builds, the CLI builds from the same file.

Four tabs: **Characters** (pick a character, edit their three ability slots and six POW
moves against what the ROM currently has — untouched fields produce no edits), **Game**
(level cap, enemy scaling, progression curves), **Items & Chao** (editable lists) and
**Randomizer** (encounters, gear, Chao, shops). Every feature shows its confirmed-in-game
or build-verified badge.

The Game and Randomizer tabs share one schema (`GAME_FIELDS`); `GAME_TAB` and `RANDOM_TAB`
only decide which features each renders, so a new parameterised feature needs a schema
entry and a name in one of those tuples, nothing more.

A build writes `build/<profile name slugified>.nds`, so two profiles sharing a `name`
target the same file. `modbuild.py` refuses a cross-profile overwrite — it records the
source profile in each report and checks it — because a built ROM is often the one being
played, with an emulator save beside it. `--overwrite` forces it.

### Profile operations

`modbuild.py` exposes only operations whose in-game effect has been confirmed:

| Op | Edits |
|---|---|
| `tlk_string` | a TLK string by id |
| `twoda_cell` / `twoda_add_row` | a 2DA (`.ITM`, `.SPL`) cell or appended row |
| `gda_cell` / `gda_string` / `gda_add_row` | a GDA integer cell, string cell, or appended row |
| `copy_resource` | replaces one archive resource's payload with another's, byte for byte |
| `item_name` / `item_desc` | an item's name/description strrefs via `Items.GDA` |
| `chao_name` | a Chao **species** name via `Chaos.GDA` (an item name does *not* rename a Chao) |
| `chao_desc` | a Chao **species** description, same species-level lookup as `chao_name` |
| `gda_clone_rows` | append copies of existing GDA rows with per-column overrides, for tables `gda_add_row` refuses |
| `are_cell` | one integer field of one placed object in an area file (chest contents, spawn points) |

`copy_resource` reads its source from a pristine, never-mutated view of the archive, so
a *swap* (A→B and B→A in one profile) is order-independent. It moves bytes only — the
profile author is responsible for the two resources being compatible. It is used for the
portrait remap, where Shadow's frames stand in for Sonic's; all portrait NCGRs are
64×64 8bpp / 4160 bytes raw, which is what makes them interchangeable.

### Still-standalone drivers

These predate `modbuild.py` and remain because they **generate** edits
algorithmically rather than just listing them — the design logic is the point:

- `build_footwear.py` — computes the five role profiles across four tiers
- `build_levelcap_test.py` — extrapolates stat curves for added levels (`--cap N`)
- `build_elemental_chao.py` — derives each Chao's matching resistance
- `build_custom_chao.py` — the five redefined Chao
- `build_unique_chao_stats.py`, `build_omniring.py`, `build_stat_test.py`,
  `build_diagnostic.py`, `build_combined.py`, `build_mod.py`, `build.py`

The natural next step for these is to have them **emit a profile** instead of
driving a build directly, so there is one pipeline and many generators.

## Safety invariants

1. The source ROM is opened **read-only** and never written.
2. A rebuild with no replacements is **byte-identical** to the input — asserted
   before any real edit.
3. Edits are re-read through the independent readers after the rebuild; a mismatch
   aborts the build.
4. Patches are verified by applying them back and comparing to the built ROM.
5. `save_edit.py` refuses to write a save whose checksums do not validate.
