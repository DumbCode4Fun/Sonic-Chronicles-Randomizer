# Known Formats

A reference catalog of file formats **confirmed** against our own ROM copies (not just cited from external research — see [RESEARCH.md](RESEARCH.md) for unconfirmed prior art, and [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md) for the dated evidence behind each entry below).

## Container / archive formats

### NitroROM filesystem (the `.nds` file itself)
Standard Nintendo DS cartridge layout. For this game specifically:
- Root filesystem is **flat**: 1 directory (root), 303 files, no subfolders.
- **No ARM9 or ARM7 overlays** (overlay table size = 0 for both). All game code lives in the single static ARM9 binary loaded at boot.
- Most of the actual game data (assets, items, dialogue, areas...) is not among those 303 loose files — it's packed inside six `.herf` archives (see below).
- Parser: `research/phase0` scripts implement header + FNT/FAT parsing from scratch in pure Python (no external tool dependency needed for this step).

### HERF ("Hashed ERF") — `.herf`
A BioWare archive format, simpler than ERF/RIM, used (per xoreos) **only** in this game. Confirmed structure:

```
Header:
  uint32 magic            = 0x00F1A5C0
  uint32 resourceCount

Resource table (resourceCount × 12 bytes), immediately following the header:
  uint32 nameHash         (DJB2 of the resource's filename)
  uint32 size
  uint32 offset           (relative to the start of this HERF archive)
```

- Hash algorithm: **DJB2, "add" variant** — `h = 5381; for each byte b: h = (h*33 + b) & 0xFFFFFFFF`. Confirmed by computing `djb2("erf.dict")` and matching it to a real resource hash.
- Optional embedded dictionary: a resource literally named `erf.dict`, itself structured as `magic, uint32 nameCount`, then `nameCount × (uint32 hash, 128-byte null-padded ASCII name)` (132 bytes/entry). When present, every other resource's name can be recovered by hash lookup.
- This game's main archive (`/test.herf`, 49 MB, 8691 resources) **has** `erf.dict` and 8689/8691 names resolve cleanly. The five per-language archives (`test_e/f/g/i/s.herf`, 42 resources each) do **not** carry their own `erf.dict` — their contents are currently anonymous.
- Recovered filenames are tracked in `research/phase0/herf_test_contents.tsv` (name, hash, size, offset-in-archive, absolute ROM offset) — treat this as the authoritative file inventory for everything packed inside `/test.herf` going forward, rather than re-deriving it.

## BioWare structured-data formats

### GFF4 (Generic File Format, v4.0/4.1)
Confirmed as the container for: `.gff` (generic/untyped), `.dlg` (dialogue), `.gda`/`.GDA` (tables), `.gui` (UI), `.plo` (placeables), `.are` (areas), `.tlk` (talk tables).

Common 20-byte file header observed across all of the above:

```
offset 0x00  8 bytes  ASCII "GFF V4.0"
offset 0x08  4 bytes  ASCII "PC  " (literal, space-padded — appears fixed/unused on this DS port)
offset 0x0C  8 bytes  ASCII struct-type + version tag, content-specific, e.g.:
                         "CONVV0.1"  -> dialogue/conversation
                         "AREA V0.1" -> area
                         "GUI V0.1"  -> UI layout
                         "PLTSV1.0"  -> placeable template
                         "G2DAV0.2"  -> 2D table (GDA)
                         "TLK V0.2"  -> talk table
                         "GFF V4.0"  -> generic/untyped blob
offset 0x14  4 bytes  uint32 (count? — not yet decoded)
offset 0x18  4 bytes  uint32 (offset? — not yet decoded)
```

**The full field layout is now decoded and validated** — all 1324 GFF4 files in the ROM decode completely (every field, list, nested struct and string) with zero errors. Reader: [tools/recon/gff4.py](tools/recon/gff4.py). Full spec and validation detail in [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md); the essentials:

After the 20-byte magic/version/platform/type header come `uint32 structCount`, (`V4.1` only: `stringCount`, `stringOffset`), `uint32 dataOffset`, then:

```
structCount x 16-byte struct templates:
    uint32 label (FourCC), fieldCount, fieldOffset (absolute), size
at each fieldOffset, fieldCount x 12-byte field definitions:
    uint32 label (numeric field ID — GFF4 stores no field names)
    uint32 typeAndFlags   (type = low 16 bits, flags = high 16 bits)
    uint32 offset         (within a struct instance)
```

Flags: `0x8000` LIST, `0x4000` STRUCT, `0x2000` REFERENCE.

- **When STRUCT is set, `type` is a struct-template index**, not a primitive type code.
- **LIST**: the uint32 at `base+offset` is an offset relative to `dataOffset`; a uint32 element count sits there, elements follow, struct elements spaced by template `size`.
- **REFERENCE**: the uint32 at `base+offset` is an offset relative to `dataOffset` of the real value.
- Strings are out-of-line: uint32 character count (including trailing NUL), then characters.

**Two traps that corrupt quietly instead of failing:**
1. `TLK ` files store **8-bit CP-1252** strings; all other types use **UTF-16LE**. Reading a TLK as UTF-16 gives CJK mojibake and overruns into the following string.
2. A string field with the REFERENCE flag must **not** be dereferenced twice — following the reference already lands on the string data. Doing it twice returns junk from an arbitrary offset rather than erroring.

Content types in this ROM (all `V4.0`, platform `PC  `): `GFF ` 740, `G2DA` 229, `PLTS` 107, `CONV` 101, `ARE ` 79, `GUI ` 68. **Extension does not determine content type** — e.g. 134 files end in `.gui` but only 68 are type `GUI `.

### GDA (`G2DA`) tables

Three templates: `gtop` holds two struct lists, `colm` (columns) and `rows`. A `colm` entry is `{10001: columnHash, 10999: type}` with type `1` = integer, `0` = string. Each `rows` entry has one field per column, labelled sequentially from `10005` and mapping positionally onto the column list (verified in all 229 tables).

Columns carry **no names, only a hash**: `crc32(name.lower().encode('utf-16-le'))`. The ROM has **845 distinct column hashes**; 182 (21.5%) are currently recovered by dictionary attack ([tools/recon/gda_dict.py](tools/recon/gda_dict.py)), cached in `research/phase0/gda_columns.tsv`. Unknown names don't block modding — the data decodes regardless, and meaning is often inferable from values.

### 2DA (plain text), not GFF-wrapped
Contrary to the external research notes carried over from other BioWare titles, in **this game** the following extensions are plain, human-readable text, not GFF4:
- `.2da` (61 loose files in the ROM root)
- `.itm` (219 files inside `test.herf`) — **item definitions**
- `.spl` (151 files inside `test.herf`) — **spell/ability definitions**

Format: line 1 is the ASCII header `2DA V2.0` (space-padded), then a blank line, then a column-header row (whose first column — the row label — is unnamed), then data rows. Directly readable/editable with a text editor — no binary parser needed for these three extension families. This is good news for Phase 8 (equipment) and Phase 7 (abilities): the data most relevant to those phases may not require GFF4 decoding at all.

**Delimiter rule — subtle, get this right.** These files are hand-maintained and inconsistent:
- most rows are tab-delimited (runs of tabs = cosmetic alignment);
- some rows use runs of **spaces** instead, in the same file (e.g. trailing `VFX` rows of `Item2.ITM`);
- values can contain **single spaces** and are **not quoted** (`Chaos Emerald 1`).

So: **a tab, or a run of 2+ spaces, delimits a field; a single space belongs to the value.** Drop empty fields, strip the rest. Validated across 431 files (219 `.itm` + 151 `.spl` + 61 `.2da`) with 0 failures and 0 arity mismatches. Parser: [tools/recon/twoda.py](tools/recon/twoda.py), which carries an arity check — keep it, it caught this.

`****` (a run of asterisks) is BioWare's conventional "empty" marker.

### `.itm` / `.spl` schema

Both share one identical 7-column schema across all 370 files:

```
<row label>  ID  EffectId  Data  SData1  SData2  SData3  Pulse
```

An item or ability is **a list of effect records**, not a flat stat block: universal metadata rows first, then the effects. The metadata rows differ by family — items have **three** (`SpellData`, `CollectionData_Equip`, `CollectionData_Use`), abilities have **two** (`SpellData`, `CollectionData`). `SData1` identifies the target stat or element; see [KNOWN_IDS.md](KNOWN_IDS.md) for the confirmed stat/element ID tables and `EffectId` values.

`SpellData.Data` means different things in the two families: on an **item** it is the human-readable name (`LightSlippers`); on an **ability** it is a reference to a named effect/status that several abilities may share, and is *not* reliably the file's own name (all `Spell_Tough*` files reference `Spell_Fortified`).

Ability upgrade tiers are separate files (`Spell_X`, `Spell_X_2`, `Spell_X_3`) that in 26 of 30 cases differ **only in the `Data` magnitude column** — so ability rebalancing is a one-number text edit.

**Row labels are comments, not behavior** — some are demonstrably mislabelled (rows marked `HealHP` that actually modify FATIGUE). Mod by editing numeric fields, not labels.

### Resource name references are normalized

2DA fields that reference a packed resource do so with **different case and without the `.small` suffix** than the archive stores: the tables say `ICN_S_MEDKIT.NCGR` while the archive holds `ICN_S_Medkit.NCGR.small`. Since HERF lookup is a case-sensitive DJB2 hash, the engine must normalize case (and the `.small` suffix) before hashing. Do not hash a name as written in a 2DA and expect it to match.

The loose `.2da` files in the ROM root are a different kind of table: purely **numeric** column names across 13 distinct layouts — grid/index data rather than named-schema records.

The *separate* `.gda`/`.GDA` extension is the actual GFF4-wrapped table format (struct type `G2DA`) — don't confuse the two; same underlying "table" concept, different file extension and format in this game.

## Nintendo DS native formats

| Extension | Format | Notes |
|---|---|---|
| `.nsbca` | NSBCA (skeletal animation) | Magic `BCA0`. Pairs with NSBMD models / NSBTX textures (not yet seen loose — likely inside `.small`-compressed wrappers or not present as separate top-level resources). |
| `.ncgr` / `.nclr` | Tile graphics / palette | Standard Nitro 8×8-tile graphics + separate palette. **Decoded** — see the dedicated section below. |
| `.nbfs` / `.nbfp` | Raw paletted full-screen image + palette | 107 of each inside `test.herf`. |
| `.cbgt` / `.pal` / `.cdpth` | Background tiles / palette / depth | 62/62/45 in ROM root. No file-level LZSS header observed on the samples checked — compression (if any) may be applied to internal 64×64 sub-blocks rather than the whole file; not yet confirmed either way. |
| `.nftr` | Bitmap font | 14 inside `test.herf`. |
| `.sdat` | Nintendo Sound Archive (SDAT/NitroComposer) | Magic `SDAT`. Standard, well-documented format — existing third-party tools (e.g. sdat tooling referenced by various NDS modding communities) should read this without custom work. |
| `.small` | **Confirmed** 4-byte wrapper: type `0x00` stored or `0x10` NDS LZ77 — see dedicated section below | A naming *suffix* appended after the real extension, e.g. `PRTL_GGLgen_1.NCGR.small`. 5311 of the 8691 resources in `test.herf` use it; all 5311 read successfully. |
| `.nsbtp` / `.nsbta` | NSBTP (texture pattern animation) / NSBTA (texture SRT animation) | Magics `BTP0` / `BTA0`. Found as `.small` payloads (341 and 169 respectively), not as loose resources. |
| `.emit` | Particle emitter | Raw binary, not GFF-wrapped. Structure not yet decoded. |
| `.vx` | Unknown — `BIOWARE.vx` | Magic `VXDS`. Purpose not identified yet; not matched to any documented format so far. Open question. |
| `.tga` | Targa image | Confirmed genuine TGA headers (uncompressed true-color). |
| `.sav` (in-ROM) | Unknown structure | `SaveTest1.sav` (21,504 B) is a loose file inside the ROM itself — likely a leftover developer test save, distinct from a real DeSmuME `.dsv` battery save. Not yet analyzed. |

## NCGR / NCLR (decoded — `tools/gui/icons.py`)

Decoded far enough to render inventory icons and portraits. Both are the standard
Nitro layout: a 16-byte generic header, then one named section.

**NCGR** (`RGCN`), section `RAHC`, fields relative to the section start:

| offset | field |
|---|---|
| `0x08` / `0x0A` | height / width **in 8×8 tiles** (u16 each) |
| `0x0C` | format: `3` = 4bpp, `4` = 8bpp |
| `0x14` | tiled/linear flag — bit 0 set means linear (do **not** de-tile) |
| `0x18` | pixel data size |
| `0x1C` | data offset (24, giving data at section + 32) |

Pixels are palette **indices** stored one whole 8×8 tile at a time, not row by row,
so they must be de-tiled. Every item icon and portrait checked is 8×8 tiles (64×64),
8bpp, 4096 bytes, tiled flag 0, data at +32 — confirmed two ways, since
`section size - data size` also gives 32.

**NCLR** (`RLCN`), section `PLTT`: `0x08` bit depth (`4` = 256 colours), `0x10`
palette size in bytes, `0x14` data offset (16, giving colours at section + 24).
Colours are BGR555 — one u16 each, 5 bits per channel, low-to-high R/G/B, expanded
to 8-bit by `c << 3 | c >> 2`. All item palettes checked are a single 256-colour
bank of 512 bytes.

**Index 0 is transparent**, by DS convention. This matters more than it sounds: a
typical 64×64 item icon is ~92% index 0, so the art is a small sprite adrift in a
mostly empty canvas and must be cropped to its bounding box to look right.

### Where an item's real icon lives

The icon named on an item's own `.ITM` row is a **generic placeholder** — 138 of 139
items share `ICN_S_MEDKIT.NCGR`, so it identifies nothing. The real per-item art is
in `Items.GDA`:

| column | meaning |
|---|---|
| 9 | category icon (8 distinct, e.g. `INVENT_icon_ASS.ncgr`) |
| 10 | **per-item sprite prefix** (105 distinct, e.g. `ITM_ACE_kron_`) |
| 14 | palette (12 distinct, e.g. `GUI_items_Accessories.nclr`) |

**An item icon is four resources, not one.** The prefix resolves to
`<prefix>0..3.NCGR.small`: four 64×64 quadrants laid out left-to-right then
top-to-bottom, forming one 128×128 picture. Every item icon in the game has
exactly four parts (110 of them). Rendering only `<prefix>0` shows the top-left
corner — which, because the art is centred across the seam, reads as a fragment of
unrelated graphics rather than an obviously missing piece, and is easy to
misdiagnose as a broken tile decoder. 108 of the 250 named items have icons, and
all 108 assemble.

## `.gui` (decoded) — widget trees

All 134 `.gui` resources are **GFF4** (`GFF V4.0` / `PC  ` / `GUI V0.1`), with struct
templates `GUI `, `TEXT`, `PANE`. They parse with the existing reader. Each file is a
tree of widgets; 2964 widgets across 1035 distinct names.

| field | meaning |
|---|---|
| `#62000` | widget **name** (`RootPanel`, `CLevelV`, `TGuiImage18`) |
| `#62002` | **children** list |
| `#60007` | widget type — 1 image, 2 text, 3 panel, 6 composite |
| `#60018` / `#60019` | x / y, relative to the parent panel |
| `#60020` / `#60021` | width / height |
| `#60022` | draw layer |
| `#60004` / `#60015` | image `.ncgr` / palette `.nclr` |

### The character sheet, and why POW and GRT are missing

The stat panel lives in three files — `ProfileCreaturePanel.gui`,
`InventoryEquipmentData.gui` and `StoreEquipmentData.gui` — as paired label/value
widgets inside `EquipmentDataPanel`:

    label  CLevel CHP CFP CSP CAT CDE CLU     at x=2
    value  CLevelV CHPV CFPV CSPV CATV CDEV CLUV   at x=23
    y      21, 36, 51, 66, 81, 96, 111            (15px apart)

ARM9 `0x020BE944` is **not** a stat-value array as previously recorded — it is an
array of **7 widget-name strings**, the ones listed above, sitting beside
`CreatureRadioGro`, `Slot0Btn`, `CName` and `OBJArrayDisplay`. POW and GRT are absent
because *the panel has no widget for them*, not because their values are suppressed.

Two further value widgets exist that the array does not list: **`CHMV`** and
**`CFMV`**, the maxima in "148/148", so they are driven by some other path.

**Adding POW/GRT is layout-feasible.** `EquipmentDataPanel` is 128 tall from y=32, so
it ends at y=160 while the last row ends at y=125; rows at y=126 and y=141 fit inside
the existing panel. What it needs is (a) a GFF4 **writer** able to append widgets to a
list — the current writer only appends GDA rows — and (b) an ARM9 patch extending the
7-entry name array and whatever loop bound reads it. Neither is done.

## `.small` wrapper (compression)

Confirmed against all 5311 `.small` resources in `/test.herf` — zero failures, zero size mismatches, every payload a recognized Nitro format. Reader: [tools/recon/lz77.py](tools/recon/lz77.py).

```
byte  0     compression type: 0x00 = stored (payload copied verbatim)
                              0x10 = NDS LZ77/LZSS
bytes 1-3   payload size, 24-bit little-endian
bytes 4+    payload
```

LZ77 decoding (the standard GBA/NDS variant): read a flag byte; its bits from MSB (bit 7) to LSB (bit 0) each describe one block.
- bit `0` → literal: copy the next 1 input byte to the output.
- bit `1` → back-reference: read 2 bytes `B1`,`B2`; `length = (B1 >> 4) + 3`; `disp = (((B1 & 0x0F) << 8) | B2) + 1`; copy `length` bytes starting at `outputPos - disp`, **one byte at a time** (overlapping self-referencing copies occur and must work).

Repeat until the output reaches the declared payload size.

Distribution in `/test.herf`: 5111 LZ77, 200 stored. **"`.small`" means "wrapped", not necessarily "compressed"** — any reader must handle both types. Payload formats, once unwrapped: NCGR 3374, NSBTX 584, NSBMD 583, NSBTP 341, NCLR 210, NSBTA 169, NANR 25, NCER 25.

Not yet done: **compression** (writing a `.small`). Stored type `0x00` is a trivially-correct fallback for modding if re-encoding ever proves troublesome, at a cost in ROM space.

## Developer-leftover text content

`sound_data.sadl` (12,924 bytes, loose in the ROM root) is **not** a binary audio format despite the name — it's a plain-text C header of `#define NAME value` constants for sound/music bank indices (e.g. `bgm01_wavearc`, `sfx_cbt_act1`, per-area ambience like `int_a2_s7_i02arc`). Shipped into the retail ROM by accident. Full text preserved at `research/phase0/sound_data_sadl.txt`; named constants promoted to [KNOWN_IDS.md](KNOWN_IDS.md).

### GDA string columns (writing)

String cells are **REFERENCE-flagged `asciistring`**: the row field holds a `uint32`
offset relative to `dataOffset`, pointing at a `uint32` character count — **including
the trailing NUL** — followed by CP-1252 text. The string region sits **after** the row
array (in `creatures.GDA`, rows end at `0x7950` and strings run to EOF at `0x8AAB`).

**GDA strings are deduplicated.** Several rows — and several columns — can point at the
same string. In `creatures.GDA`, creatures 4, 75, 77 and 116 all share one
`PRT_SP_SDW.ncgr`. Editing such a string in place silently rewrites it for every sharer.
[tools/build/gda_write.py](tools/build/gda_write.py) therefore counts sharers first and
**never edits a shared string in place** — it appends a fresh copy at the aligned end of
file and repoints only the target row, the same strategy used by the TLK and HERF writers.

**Ordering constraint:** appending a string places data after the row array, which breaks
`append_row`'s precondition that rows are last. Do row appends before string appends on
the same table. In practice they do not collide — tables with string columns already have
string data after their rows, so `append_row` correctly refuses them anyway.

### Derived resource names (a modding trap)

Some `creatures.GDA` columns hold a **prefix** rather than a complete resource name; the
engine appends a suffix at runtime. Dialogue portraits are the clearest case: the column
holds `PRTL_SONIC` and the engine requests `PRTL_SONIC<expr>_<n>.NCGR` for an expression
such as `amu`, `inq` or `sle`.

**Swapping such a prefix only works if every derived name exists.** Character portrait
sets have different expression vocabularies — `PRTL_SONIC` has 10, `PRTL_SHD` 9 and
`PRTL_SDW` only 4 — so pointing Sonic's dialogue at Shadow's set makes the game request
art that was never drawn, and it renders corrupted tiles rather than failing cleanly.

By contrast, columns holding a **complete** resource name (`PRT_SP_SDW.ncgr`,
`CharPro_SDW`) swap safely, as does the integer appearance id into `appearances.GDA`.
Check whether a column is a prefix or a full name before swapping it.

## NDS header: device capacity (0x14)

One byte, a shift: the cartridge holds `128 KiB << cap`. Vanilla Sonic Chronicles ships
`0x0A` (128 MiB) with only ~3.8 MB spare. A build that appends enough data — randomized
item descriptions are enough — must raise it, or DeSmuME warns on every launch
("The ROM header is invalid. The device size has been increased...") and hardware may
refuse. The image need not be padded up to the declared size. The header CRC16 at 0x15E
covers 0x000-0x15D and must be recomputed afterwards.

## appearances.GDA

222 rows, indexed by `creatures.GDA` column 14 and `squads.GDA` column 4 (the overworld
model). Column 0 is the id, 1 a type, 2 a scale, **3 the model prefix** (`ArmBoar_AB`,
`GZD_AA`), 8 an optional named animation.

**Rows 0, 4 and 72 have no model name.** Appearance 4 belongs to the playable-character
duel variants (creature rows 75, 77, 116), whose models load through a different path.
Pointing an ordinary enemy at a model-less appearance black-screens the battle on entry.

## Items.GDA: an item's .ITM file is column 5, not its id

`item<id>.itm` is right for 213 of 230 items and wrong for 17. Health Seed is id 0 in
`item1.itm`; five ids share `item12.itm`; the four elemental Shields share
`item186-189.itm` with Chao growth tiers. Spellings are mixed case (`item1.itm` but
`Item130.itm`), so any grouping by filename must lowercase first. Resolving by convention
edits the wrong item's table rather than failing.

## ARE placeables vs item pickups

Two different lists, routinely confused:

**List 40001 — placeables**, the things drawn in the world, each with a type at field
40018: **1,035 rings** (type 0), 176 arrows (37), **115 Chao eggs** (32), 69 blocks (1),
57 bounces (2), **53 chests** (`itembox`, type 6), 22 pressure plates (4).

Every placeable also carries **three `float32` parameters at fields 40020/40021/40022**
whose meaning depends on its type, and a **position**, which is the `vector3f` at label 4
— *not* the triple. The giveaway: 1,035 rings are scattered across the world and share
exactly two distinct triples between them, `(0,0,0)` and `(-1,-1,-1)`.

**For a chest the triple is its three item slots** — `Items.GDA` ids, -1 for empty. 53
chests, 120 filled slots, every one a valid id, laid out in a clean difficulty gradient
(Health Seeds in Green Hill, the Zoah Shield in the Zoah area, one Nocturne Relic in each
of five Act 2 chests). See the 2026-10-10 log entry for the full evidence.

**List 40002 — triggers/entities**, with a kind at 40008 and a payload at 40009.
**kind 4 is an item object**: 39 across 17 areas, each naming an `Items.GDA` id. Most
carry a **plot-flag id at field 40013**, and the flag numbers rise with chapter order, so
many are gated and never appear in an ordinary run.

**Chao eggs carry no payload.** All 115 have their triple at `(0,0,0)`, so which Chao
hatches is still decided in ARM9. Chests, which looked identical in this respect, were
not — their payload was in a field the integer-only reader never showed.

## ARE spawn points carry a script tag

List **40003** holds squad placements: position, facing, squad id (**40005**), waypoint
list (40007), instance index (40023) — and a **script tag at 40006**. Non-zero means a
plot addresses that spawn point by name, and the entry's name string is the same number.
13 of the 54 in `a1_s1_ex` are tagged, including spawn #0 (tag 5), which holds the combat
tutorial's Enraged Armadillo.

Reassigning the squad at a tagged point **starts the battle with no enemy in it**.
Anything that moves encounters must leave tagged points alone.

## .plo — plot files (GFF4 type `PLTS`)

`plots.GDA` maps 102 rows onto 95 distinct `.plo` resources, named by chapter
(`plt_ch1_main.plo`, `plt_ch3_shadow.plo`, `plt_gbl_inparty.plo`).

Structure: the root holds a list (field **13016**) of **plot** structs; each plot has a
name (3), a GUID (13007), a category (13009, e.g. `plot_core`), and a list (**13000**) of
**flag** structs. A flag carries an index (13001, 0-108 within its plot), a
**human-readable name (13002)** such as `SHADOW_IN_PARTY` or `CH3_SHADOW_ESCAPED`, a TLK
string (13004, the journal text), two booleans (13005/13006, 0 or 255), and two sparse
integers (13003, 13019). 1,041 flags across all 107 files, 1,028 distinct names.

**A `.plo` is a flag registry, not a script.** There are no actions, no opcodes and no
item references anywhere in it — the integer fields top out at 652 and none correlate
with item ids. This matches the xoreos wiki's note that Sonic Chronicles "doesn't seem to
use any scripts at all", unlike other Aurora-engine games: the plot *logic* is native
ARM9 code, and these files only declare the flags it reads and the journal text it shows.

Consequence for modding: anything driven by plot logic — recruitment order, what a chest
contains, when a reward fires — cannot be retargeted by editing these files.

## `.dlg` conversation nodes, and how a plot flag is set

A `.dlg` root holds a **list of generics** at field 12002 — one per conversation node,
each an 8-byte `(typeAndFlags, offset)` pair pointing at a 112-byte struct of template
38 or 39. The fields that matter:

| field | meaning |
|---|---|
| 12201 | the spoken line, as a TLK string |
| 12202 | the speaker's portrait prefix (`prtl_bighap`) |
| 12203 | `'PLAYER'` on a reply node |
| **12208** | **condition** — an inline struct: plot GUID, flag index, expected value |
| **12209** | **result** — the same shape: the flag this node sets when taken |
| 12212 | the node's child links |

**Flags are addressed by plot GUID, never by name or by global id.** `a1_big.dlg`
carries `1E2CD4BBBC114BA48F917BF5AD7CB7D7`, which is field 13007 of `plt_fp_big.plo`.
No data file in the game contains the string `BIG_GET`; only the `.plo` registry has the
names, and `tools/recon/plotflags.py` is what puts them back together.

So a conversation *is* the game's scripting, in the only form this game has: a graph of
lines, each gated on a flag and each able to set one. What a node cannot do is carry an
arbitrary action — there is no opcode field, and the two integers that sit beside the
result (12214, 12215) take the same handful of values whether the node recruits Big,
Cream or Omega, so they are not a party-member id. Recruitment is a flag the dialogue
sets and native code reacts to.
