# Reverse Engineering Log

Dated entries for confirmed discoveries, per the project's research process. Each entry: what was investigated, what was discovered, evidence, confidence, relevant offsets, how it was tested, and remaining uncertainty. Hypotheses that haven't been independently confirmed belong in [RESEARCH.md](RESEARCH.md), not here.

Raw outputs referenced below live under [research/phase0/](research/phase0/).

---

## 2026-10-05 — Phase 0: ROM header, revisions, and filesystem mapping

**Investigated:** Which ROM revision(s) we have locally, and the top-level NitroROM (FNT/FAT) filesystem of both.

**Method:** Wrote a pure-Python NDS header/FNT/FAT parser (no third-party tools) and ran it against both local dumps:
- `Old Desmume/Roms/Sonic Chronicles - The Dark Brotherhood (Europe).../2699 - ... .nds`
- `Old Desmume/Roms/Sonic Chronicles_ The Dark Brotherhood/Sonic Chronicles - The Dark Brotherhood (USA)... .nds`

**Discovered (confidence: high — directly read from the files):**

| | EU | US |
|---|---|---|
| Game code | `CSNP` | `YWSE` |
| Maker code | `8P` (Sega) | `8P` (Sega) |
| ROM version byte | 0 | 0 |
| Device capacity | 128 Mbit (0x8000000 bytes) | 128 Mbit |
| ARM9 offset / size | 0x4000 / 0x110DD8 (1,117,656 B) | same ballpark, not yet diffed byte-for-byte |
| FNT files | 303 | 303 (identical count) |
| ARM9/ARM7 overlays | **0 / 0** | **0 / 0** |
| Header CRC16 | 0xE370 | 0xA9D7 (expected — different header content per region) |

- The US game code `YWSE` matches the Action Replay game ID `YWSE-ACB0DF12` found in prior community research — a useful independent cross-check that the US dump is a standard/known build, not a bad or unusual one.
- **No ARM9 or ARM7 overlays are used by this game.** All ARM9/ARM7 code is in the single static binary loaded at boot. This matches the xoreos team's observation that the game "doesn't seem to use any scripts" — there's no dynamic overlay-based code loading to account for, which simplifies any future static/dynamic analysis of game logic (everything lives in one ARM9 binary, no runtime overlay swapping to track).
- The root NitroROM filesystem is **flat — 1 directory (root), 303 files, no subfolders**. Both regions have the exact same 303-file layout and the same extension breakdown (`.cbgt` 62, `.pal` 62, `.2da` 61, `.vx` 59, `.cdpth` 45, `.herf` 6, `.tlk` 5, plus one each of `.sav`, `.sadl`, `.sdat`).
- EU and US `test.herf` (see below) report the **same resource count (8691)** and the five small per-language `.herf` files report the same count (42) in both regions. This strongly suggests EU and US share the same underlying packed game data/IDs, and differ mainly in the loose `.tlk` string tables and possibly a handful of other loose files — not yet proven for every file, but a solid working assumption until contradicted.

**Remaining uncertainty:** Have not yet diffed the ARM9/ARM7 binaries or any individual packed resource byte-for-byte between EU and US — "same structure" is confirmed, "byte-identical game data" is not.

**Evidence:** `research/phase0/rom_report_EU.txt`, `research/phase0/rom_report_US.txt`, and the full per-ROM file listings (`*_filelist.tsv`).

---

## 2026-10-05 — Phase 0: `.herf` archive format and filename recovery

**Investigated:** The internal structure of the six `.herf` files, which account for the bulk of the ROM's actual size (one 49 MB archive + five ~1.5 MB per-language archives, against a ~130 MB total ROM).

**Method:** Confirmed via xoreos source (`src/aurora/herffile.cpp`/`.h`) that HERF is a known, documented BioWare format ("Hashed ERF") exclusive to this game, then implemented the format from the xoreos source description in pure Python and ran it against all six archives in the EU ROM, cross-checked resource counts against the US ROM.

**Discovered (confidence: high — format implemented independently and validated against real data):**

- Header: `uint32 magic (0x00F1A5C0)`, `uint32 resourceCount`, followed by `resourceCount` × 12-byte entries (`uint32 nameHash`, `uint32 size`, `uint32 offset`). Offsets are relative to the start of the HERF archive itself (i.e. add the archive's absolute ROM offset).
- Resources are identified only by a **DJB2 hash** of their filename (`hash = 5381; for each byte: hash = (hash*33 + byte) & 0xFFFFFFFF`) — the "add" variant, not the XOR variant. Confirmed by computing `djb2("erf.dict")` and finding that exact hash present as a resource in `/test.herf`.
- When present, a resource literally named `erf.dict` is itself a small HERF-like structure: `magic`, `uint32 nameCount`, then `nameCount` × (`uint32 hash` + 128-byte null-padded ASCII name) = 132 bytes per entry. This dictionary round-trips: every name in it hashes (via the same DJB2) to its own table's hash field.
- `/test.herf` (EU, 49,289,296 bytes, 8691 resources) **has** an `erf.dict` and **8689/8691 names were recovered** (two resources — including the dictionary's own entry — are expected not to resolve to a "content" name). Extension breakdown of the recovered names:

  | ext | count | likely content |
  |---|---|---|
  | `.small` | 5311 | compressed payloads (see compression entry below) — many of these wrap another real extension, e.g. `PRTL_GGLgen_1.NCGR.small` |
  | `.nsbca` | 1026 | skeletal animation (Nitro model animation, pairs with NSBMD/NSBTX) |
  | `.gff` | 674 | generic/untyped GFF4 blobs |
  | `.emit` | 233 | particle emitter definitions (raw binary, not GFF-wrapped) |
  | `.gda` | 229 | GFF4-wrapped 2D array / table data |
  | `.itm` | 219 | item definitions (**plain-text 2DA**, not GFF — see below) |
  | `.tga` | 177 | Targa images (confirmed real TGA headers) |
  | `.spl` | 151 | spell/ability definitions (**plain-text 2DA**) |
  | `.gui` | 134 | UI layout definitions (GFF4) |
  | `.nbfp`/`.nbfs` | 107/107 | paletted full-screen image pairs |
  | `.plo` | 107 | placeable templates (GFF4, struct type `PLTS`) |
  | `.dlg` | 101 | dialogue/conversation (GFF4, struct type `CONV`) |
  | `.are` | 79 | area definitions (GFF4, struct type `AREA`) |
  | `.nftr` | 14 | fonts |
  | `.smp` | 13 | sound samples |
  | `.ncgr`/`.nclr` | 3/1 | tile graphics / palette (loose, not `.small`-wrapped) |
  | `.dict` | 1 | the `erf.dict` itself |
  | `.raw`, `.txt` | 1 each | unexamined |

- The five per-language `test_e/f/g/i/s.herf` archives each contain **42 resources and have no `erf.dict`** (their resource hashes don't include `djb2("erf.dict")`), so their contents are currently anonymous — not yet identified by content inspection.
- US ROM: same `test.herf` resource count (8691) and same per-language counts (42 × 5), confirming the archive structure (not necessarily every byte) matches between regions.

**This single finding effectively completes most of Phase 3 "data discovery" at the file-inventory level** — we now have real, human-readable filenames for the items, abilities, dialogue, areas, and placeables the roadmap asks about, without having opened a single GFF4 struct yet.

**Evidence:** `research/phase0/herf_analysis.txt`, `research/phase0/herf_all_summary.txt`, `research/phase0/herf_test_contents.tsv` (full 8691-row name→offset→size table), `research/phase0/herf_content_peeks.txt`.

**Remaining uncertainty:** The 5 per-language herf archives are unidentified. Whether `.small` is *always* LZSS/LZ-type compression (vs. just a naming convention) has not been directly decompressed/verified yet — only inferred from the name and from prior external research.

---

## 2026-10-05 — Phase 0: file-format signatures by extension

**Investigated:** What the first bytes of one representative file per extension actually look like, to confirm or correct assumptions carried over from external research.

**Method:** Hex-dumped the first 32–48 bytes of a sample file for each extension found in both the root NitroROM filesystem and inside `test.herf`.

**Discovered (confidence: high for the files sampled; not yet checked file-by-file across every instance of each extension):**

- **`.2da`** (61 loose root files, plus the `.itm`/`.spl` files inside `test.herf`): literal **plain-text** format, starts with the ASCII header `2DA V2.0` followed by a CR/LF and tab-separated column index/data rows. This directly contradicts the "GDA is 2DA in a GFF4 suit" framing carried over from prior external research for *this* extension — in this game, files with extension `.2da`, `.itm`, and `.spl` are the classic plain-text 2DA format, human-readable with a text editor. (`.gda`/`.GDA` is the separate, GFF4-wrapped table format — see next bullet.)
- **`.gda` / `.GDA`**: confirmed GFF4-wrapped, struct type `G2DA`, version `V0.2` — this *is* the format the prior research described, it just isn't what `.2da`/`.itm`/`.spl` use in this game.
- **`.tlk`** (talk tables): GFF4, struct type `TLK `, version `V0.2` — matches prior research.
- **GFF4 files in general** (`.gff`, `.dlg`, `.gda`, `.gui`, `.plo`, `.are`) all start with the same 20-byte pattern: 8-byte literal ASCII `"GFF V4.0"`, then 4 bytes that were `"PC  "` (literal, space-padded) in every sample checked, then an 8-byte struct-type/version tag specific to the content (e.g. `CONVV0.1` for dialogue, `AREA V0.1` for areas, `GUI V0.1` for UI, `PLTSV1.0` for placeables, `G2DAV0.2` for tables, or `GFF V4.0` again for untyped generic blobs), then a `uint32` and a second `uint32` that look like counts/offsets (not yet fully decoded).
  - The `"PC  "` platform tag appearing in a Nintendo DS game's files is notable — almost certainly inherited unmodified from BioWare's PC-targeted GFF4 toolchain and never customized for the DS port. Treat it as a fixed/ignorable constant, not something that varies.
- **`.vx`** (`BIOWARE.vx`, 59 files on the root): starts with ASCII `VXDS`. Purpose not yet identified — not matched to any documented BioWare/Nitro format in research so far. Flagged as an open question.
- **`.cbgt` / `.pal` / `.cdpth`**: no text magic, pure binary — consistent with the CBGT/PAL/CDPTH background-rendering formats described in prior research. The *file-level* first bytes are not an LZSS compression header (`0x10`/`0x11` lead byte), so either these particular sampled files aren't compressed at the whole-file level, or (per prior research) compression is applied to internal 64×64 sub-blocks rather than the file as a whole — not yet resolved.
- **`.nsbca`**: starts with ASCII `BCA0` — standard Nitro skeletal-animation container, pairs with NSBMD/NSBTX models.
- **`.tga`**: real Targa header (`idLength=0, colorMapType=0, imageType=2` = uncompressed true-color) — confirms these are genuine, standard TGA files, not a custom format.
- **`.sadl`** (`sound_data.sadl`, 12,924 bytes): **not a binary format at all** — it's a plain-text C header full of `#define NAME value` sound/music ID constants, apparently a developer leftover shipped into the retail ROM by accident. See `KNOWN_IDS.md`.
- **`.herf`**: all six files are literally named `test.herf`, `test_e.herf`, `test_f.herf`, `test_g.herf`, `test_i.herf`, `test_s.herf` — a strong sign of a leftover **development/debug name** that shipped to retail unchanged (the `e/f/g/i/s` suffixes line up with the five translated `.tlk` languages: French, German, Italian, Spanish, and presumably English/base for the unsuffixed main one — not yet confirmed which language maps to which letter).

**Evidence:** `research/phase0/herf_content_peeks.txt`, `research/phase0/sound_data_sadl.txt` (full extracted text).

---

## 2026-10-05 — Phase 0: `.small` compression solved (all 5311 resources read, zero failures)

**Investigated:** Whether `.small` really is LZSS-family compression (previously only inferred from the filename suffix and external research), and whether we can read all of them.

**Method:** Implemented the Nintendo DS LZ77 (compression type `0x10`) decoder from scratch in pure Python ([tools/recon/lz77.py](tools/recon/lz77.py)) and ran it against **every** `.small` resource in `/test.herf` (not just a sample), checking three independent consistency conditions per file.

**Discovered (confidence: very high — validated across all 5311 files with three independent cross-checks):**

`.small` is a **4-byte wrapper**, not a format of its own:

```
byte  0     compression type: 0x00 = stored (raw), 0x10 = LZ77/LZSS
bytes 1-3   payload size, 24-bit little-endian
bytes 4+    payload
```

The LZ77 variant is the standard GBA/NDS LZ77: a flag byte whose bits (MSB→LSB) describe the next 8 blocks; `0` = copy one literal byte; `1` = read 2 bytes `B1,B2`, then `length = (B1 >> 4) + 3` and `disp = (((B1 & 0x0F) << 8) | B2) + 1`, copying `length` bytes from `outputPos - disp` one byte at a time (overlapping copies are required and do occur).

Results across all 5311 `.small` resources:

| | count |
|---|---|
| Read successfully | **5311 / 5311** |
| Failures | **0** |
| Size mismatches | **0** |
| Compression type `0x10` (LZ77) | 5111 |
| Compression type `0x00` (stored/raw) | 200 |

The 200 stored files are genuinely uncompressed despite the `.small` name (for these, `payload size == resource size - 4` exactly — confirmed on samples). So `.small` means "wrapped", not "compressed"; a reader must handle both types.

Three independent checks passed for **every** file, which is why confidence here is very high rather than merely "it didn't crash":
1. The `.small` header's declared payload size matched the actual decoded byte count.
2. The decoded payload's own **Nitro header internal filesize field** independently matched the decoded byte count.
3. Every decoded payload began with a recognized Nitro format magic — **zero** unrecognized/garbage output:

| Payload format | count |
|---|---|
| NCGR (tile graphics) | 3374 |
| NSBTX (texture archive) | 584 |
| NSBMD (3D model) | 583 |
| NSBTP (texture pattern animation) | 341 |
| NCLR (palette) | 210 |
| NSBTA (texture SRT animation) | 169 |
| NANR (cell animation) | 25 |
| NCER (cell bank) | 25 |

Note these magics are stored byte-reversed on disk (`RGCN` for NCGR, `RLCN` for NCLR, etc.), per normal Nitro convention. The `.nsbca` files seen earlier in the archive listing are *not* `.small`-wrapped — they sit in the archive uncompressed, which is why they don't appear in this table.

**How it was tested:** `py tools/recon/lz77.py <rom.nds> research/phase0/herf_test_contents.tsv` — re-runnable, read-only, and reports any failure/mismatch rather than failing silently. Four files were also extracted to disk as real artifacts and verified to carry correct magics and internal sizes (see `work/samples/`): `PRTL_Shadow.NCLR` (556→552 B), `PRTL_SHDgen_3.NCGR` (2039→4160 B), `PRTL_SHDmad_1.NCGR` (1992→4160 B), `FX_BlobShadow.nsbmd` (284→480 B).

**Practical consequence:** combined with the HERF work, we can now read any of the 8691 packed resources as its real decoded bytes. The read side of the Phase 1 pipeline (ROM → archive → decompressed asset) is effectively proven. The *write* side (recompressing LZ77 and rebuilding a HERF archive with correct hashes/offsets) has **not** been attempted and is a separate problem.

**Remaining uncertainty:** We have never produced a *compressed* `.small` file, so we don't know whether the game tolerates a re-encoded stream that differs from the original encoder's output (it almost certainly would, since LZ77 decoding doesn't care how the stream was chosen, but this is unproven). Stored-type (`0x00`) output is a safe fallback for modding if recompression ever misbehaves — it costs ROM space but is trivially correct, provided total size/offset constraints allow it.

**Incidental find relevant to Phase 5 (Shadow Mode):** the archive contains **78 Shadow-related resources**, including a full portrait expression set (`PRTL_SHDgen/def/hel/int/mad/det/stg/sht_*.NCGR` plus `PRTL_Shadow.NCLR` palette), dialogue (`a2_shadow.dlg`), placeables (`plt_fp_shadow.plo`, `plt_cod_shadow.plo`), a `ChaseShadow.GDA` table, and several scene `.gff` files (`A1C4_Shadow_SonicRun.gff`, `A1C3_ShadowKnockdown.gff`, …). Shadow already has substantial authored assets present, which supports the project brief's premise that Shadow Mode is about redirecting existing systems rather than authoring a new character.

---

## 2026-10-05 — Phase 3 (early): `.itm` item tables decoded; 2DA delimiter rule corrected

**Investigated:** The contents and schema of the plain-text `.itm` item tables, starting from a single file and then auditing all of them.

**Method:** Wrote a 2DA parser ([tools/recon/twoda.py](tools/recon/twoda.py)) with a deliberate arity check (does each row's value count match the column count?), then ran it over all 219 `.itm`, all 151 `.spl`, and all 61 loose `.2da` files. The arity check is what caught the format subtlety below — a single-file read would have left a silently wrong parser in place.

### Delimiter rule (corrected twice — worth reading before writing any parser)

These are hand-maintained files with **inconsistent delimiters inside the same file**:
- Most rows are tab-delimited, with runs of tabs for cosmetic alignment.
- Some rows use runs of **spaces** instead (e.g. the trailing `VFX` rows of `Item2.ITM`).
- Values may contain **single spaces** and are **not quoted** (`Chaos Emerald 1`, `Master Emerald`), so the game's files violate the strict BioWare 2DA convention of quoting such values.

Splitting on general whitespace shreds the item names; splitting only on tabs breaks the space-delimited rows. The rule that satisfies everything: **a tab, or a run of 2+ spaces, delimits a field; a single space belongs to the value.**

**Validation (confidence: high):** under that rule — 219 `.itm` + 151 `.spl` + 61 `.2da` = **431 files, 0 parse failures, 0 arity mismatches**. Before the fix the same audit reported 8 mismatched rows, so the check is live and does detect breakage.

### Schema

`.itm` and `.spl` share **one identical 7-column schema** across all 370 files:

```
<row label>  ID  EffectId  Data  SData1  SData2  SData3  Pulse
```

An item/ability is therefore **a list of effect records, not a flat stat block**. Every one of the 219 items has exactly three universal metadata rows (`SpellData`, `CollectionData_Equip`, `CollectionData_Use`); everything after that is its effects. 56 items have no effect rows at all (key items / pure collectibles).

That `.itm` and `.spl` are the *same* structure is architecturally significant for the project brief's "recombine existing systems" goal — items and abilities speak the same effect language.

### Stat IDs — `SData1` is the target stat (high confidence)

Each stat-modifier label maps to exactly **one** `SData1` value across every occurrence, always with `EffectId=1`:

| SData1 | Stat | Seen on |
|---|---|---|
| 0 | HP | `HealHP` |
| 21 | SPD (Speed) | `SPD+` ×4 |
| 22 | ATK (Attack) | `ATK+` ×17, `ATK-` ×4 |
| 23 | DEF (Defense) | `DEF+` ×23, `DEF-` ×5 |
| 24 | MAXHP | `MAXHP+` ×3 |
| 25 | POW | `POW+` ×43 |
| 26 | GRT (Grit) | `GRT+` ×46 |
| 27 | LCK (Luck) | `LCK+` ×6 |
| 28 | FATIGUE | `HealFATIGUE` ×8 |
| 36 | MAXFP | `MAXFP+` ×3 |
| 48 | AP | `AP+` ×1 |

**Row labels are documentation, not semantics.** Proof: 4 of the 10 rows labelled `HealHP` carry `SData1=28` (FATIGUE), not `0` (HP) — i.e. they are mislabelled by the original authors and actually affect fatigue. The engine must key off `EffectId` + `SData1`, not the label text. **Consequence for modding: edit the numeric fields; never trust or rename a label and expect behavior to follow.**

Other `EffectId` values observed: `0` on the three `CollectionData*`/metadata rows, `1` = modify stat/resource, `5` = VFX, `6` = heal/resurrect family, `7` = `RemoveStatus`.

`RemoveStatus` `Data` is a **bitmask** — individual values 16/32/64/128 for specific statuses, and `131070` (`0x1FFFE`, bits 1–16 set) for what is presumably "remove all". The specific status-per-bit mapping is not yet identified.

### Resource references are normalized (case **and** the `.small` suffix)

218 of 219 items reference icon `ICN_S_MEDKIT.NCGR` in `SpellData.SData3` (the remaining one references `ICN_S_BUGSPRAY.NCGR`). I initially concluded those resources were absent from the archive — **that was wrong**, and the correction matters:

- Table says `ICN_S_MEDKIT.NCGR`; archive stores `ICN_S_Medkit.NCGR.small`.
- Table says `ICN_S_BUGSPRAY.NCGR`; archive stores `ICN_S_BugSpray.NCGR.small`.

So reference→resource resolution normalizes **both letter case and the `.small` wrapper suffix**. This is important because HERF lookup is a **case-sensitive DJB2 hash** (see the HERF entry above): the engine cannot be hashing these strings as written, so it must normalize before hashing (or resolve icons by another path entirely). **Anyone adding a new resource cannot simply hash the name as it appears in a 2DA.**

The archive does contain 147 distinct `ICN_S_*` icons (including per-combo-attack icons like `ICN_S_CAtk_KS`), so distinct item icons exist as assets.

**Remaining uncertainty:** whether `SpellData.SData3` is actually used at runtime is now an open question precisely *because* 218/219 items point at the same icon — real per-item icons may instead resolve through the `ICON` effect row (whose `SData1` varied across 49–54 in the items sampled) or another table. Not yet determined. Also unresolved: the exact meanings of `SData2`, `Pulse` (values `-1`, `0x00000000`, `0x00000002`, `***`), and the `CollectionData_Equip/Use` `Data` fields (which likely encode equip slot and usability, but this is not confirmed).

**Evidence:** `research/phase0/item_catalog.tsv` — all 219 items with name, icon, equip data, and decoded effect list.

**Sample of the decoded equipment data** (showing the readable families — Slippers/Hydraulics/Sneakers tiers):

```
Item22.ITM  LightSlippers       DEF+=1(stat23), GRT+=1(stat26)
Item23.ITM  RuggedSlippers      DEF-=-1(stat23), GRT+=4(stat26)
Item25.ITM  SpikedSlippers      POW+=2(stat25), GRT+=1(stat26)
Item30.ITM  IronHydraulics      POW+=2(stat25), GRT+=2(stat26)
Item31.ITM  TitaniumHydraulics  DEF+=1(stat23), GRT+=3(stat26)
```

### Loose `.2da` files are a different animal

The 61 `.2da` files in the ROM root parse fine with the same parser but use purely **numeric column names** (`0 1 2 3 …`) in 13 distinct layouts — they're grid/index data (consistent with the background palette-assignment tables described in RESEARCH.md), not named-schema records like `.itm`/`.spl`.

---

## 2026-10-05 — Phase 7 (early): `.spl` ability/POW tables decoded

**Investigated:** All 151 `.spl` files — the ability/POW definitions underpinning roadmap Phase 7 — using the same parser and audit approach as the item work above.

**Method:** [tools/recon/twoda.py](tools/recon/twoda.py) across all 151 files (0 parse failures, 0 arity mismatches, single column layout), then targeted cross-checks: tier diffing across every upgrade family, stat-ID cross-validation against the independently-derived item table, and field-distribution analysis on the metadata rows.

### Schema: same as items, with one difference

`.spl` uses the **identical 7-column schema** as `.itm` (`ID EffectId Data SData1 SData2 SData3 Pulse`). The difference is in the universal metadata rows: items have **three** (`SpellData`, `CollectionData_Equip`, `CollectionData_Use`), abilities have **two** (`SpellData`, `CollectionData` — present in all 151). Everything after those is the ability's effect list.

### Upgrade tiers are (almost always) a single number — high confidence

Most abilities ship as triples: `Spell_X.spl` / `Spell_X_2.spl` / `Spell_X_3.spl`, the three upgrade levels. Diffing all 30 such families field-by-field:

| Tiers differ in | Families |
|---|---|
| **Only `Data`** (effect magnitude) | **26** |
| `Data` + `SData2` | 2 (`Spell_Revive_All`, `Spell_TemporalField`) |
| **Nothing at all** | 2 (`Spell_Antidote_All`, `Spell_Reverse_Engineer`) |

Example — `Spell_Tough` tiers 1/2/3 are byte-identical except `GRT+` `Data` = **10 → 15 → 20**. Row sets, `EffectId`, `SData1/2/3` and `Pulse` are untouched.

**Consequence for Phase 7:** rebalancing an ability's power is a one-number edit in a plain-text file, with no cross-references to break. This is the cheapest possible modding surface and it argues for doing ability rebalancing *before* anything requiring GFF4 decoding.

The two zero-difference families are abilities whose effect isn't magnitude-based (`Spell_Antidote_All` = `RemoveStatus` bitmask; `Spell_Reverse_Engineer` = flat `HP-` of -100), so their upgrade tiers confer no mechanical change. Whether that's intentional (a binary effect genuinely can't scale) or an oversight can't be determined from the data alone — but it's the kind of thing the project's "expose interesting systems" goal might want to revisit.

### Stat IDs independently confirmed, and "FP" resolved

The spell files use **different label spellings** than items (`SPEED+` vs `SPD+`, `LUCK+` vs `LCK+`) yet resolve to the **same numeric `SData1` stat IDs** with zero contradictions — two independent file families agreeing, which raises the stat table in [KNOWN_IDS.md](KNOWN_IDS.md) to high confidence: HP=0, SPD=21, ATK=22, DEF=23, POW=25, GRT=26, LCK=27.

This also resolves an open question: spells' `FP+` maps to `SData1=28`, the same ID items reach via `HealFATIGUE`. So **FP = Fatigue Points** — one stat, two naming conventions. (Items' `MAXFP+`=36 is correspondingly the maximum.)

New ID found: `NUMACTIONS+` → `SData1=123` (actions per turn).

### Element IDs — two distinct six-wide blocks

From spells' `RESIST_*` rows, elemental **resistance** IDs are a contiguous block:

| ID | Element |
|---|---|
| 75 | Fire |
| 76 | Water |
| 77 | Earth |
| 78 | Wind |
| 79 | Lightning (**spelled `RESIST_LIGHTING` in the files — a developer typo; match it exactly**) |
| 80 | Ice |

Cross-checking the items' 39 `ELEMENT` rows revealed a **second** six-wide contiguous block: 15 items carry `(Data=50, SData1=75–79)` — i.e. +50 resistance, reusing the IDs above, and notably **no item grants Ice (80) resistance** — while 24 items carry `(Data=1, SData1=107–112)`. That second block being exactly six wide suggests it is elemental **attack affinity** (dealing an element) as opposed to resisting it, but this is **inference, not confirmed**.

### Metadata rows (`CollectionData`) — partially understood

Across all 151 abilities:
- `Data`: a small enum — `3` (83×), `0` (39×), `1` (29×). Meaning unknown; plausibly ability category.
- `SData1`: mostly `0` (78×), otherwise powers of two (16, 32, 64, 256, 1024, 2048, 8192, 16384) **plus `192` (= 64+128)** — the composite value proves this is a **bitfield**, not an enum. Which flag means what is unknown.
- `SData2`: `3000` (74×), `-1` (59×), then `2000`, `4000`, `10000`, `100000`, `1000000`. Round magnitudes with a `-1` sentinel strongly suggest a **duration in milliseconds** (3000 = 3s) with `-1` = instant/permanent — plausible but unconfirmed.

### `SpellData.Data` is a named effect reference, not reliably a self-name

For most files it matches the file's own stem (`Spell_Stun.spl` → `Spell_Stun`), but not always: all three `Spell_Tough*` files reference **`Spell_Fortified`**. Every referenced name resolves to a real resource in the archive. So treat this field as a reference to a named effect/status that several abilities may share — *not* as a guaranteed self-identifier and not as a display name (unlike items, where this field held the human-readable name such as `LightSlippers`).

### Ability effect vocabulary (37 distinct row labels)

Beyond stat modifiers and resistances, the composable pieces are: `VFX` (131×), `ICON` (83×), generic `Effect1`–`Effect5` slots, `RemoveStatus`, `Resurrect`, `HealHP`, `TimedMediBot`, `BEHAVIOR`, `AttractTargetting` (**sic — double-t, match exactly**), and notably **`ApplySpell`** (3×) — an ability that applies another ability, i.e. the system already supports composition. That composability is direct support for the project brief's premise that new abilities can be built by recombining existing effects.

`RemoveStatus` masks refine the earlier item finding: `Spell_Antidote_All` uses `1022` (= bits 1–9) where full cures use `131070` (= bits 1–16). Both leave bit 0 unused, so the status bitfield is ~16 bits with at least two meaningful tiers of "cure" breadth.

### `Spell_Int_*` are enemy/boss intrinsics

13 files prefixed `Spell_Int_` are named after the game's alien races and bosses rather than player abilities: `Kron`, `Nocturn_Water`, `Voxai`, `Zoah`, `Nrrgal`, `Charyb_Water`, `Animal_Fly/Land`, `Robot_Fly/Land`, `GizoidShield`, `Final_IX` (Imperator Ix), and `Super_Sonic`. Plus `Overmind_Distracted`/`Overmind_Sluggish` (the Voxai Overmind) and `Int_Drone.SPL`. These are the natural starting point for Phase 11 (boss scaling), since boss-specific ability data appears to live here rather than in the player ability set.

**Evidence:** `research/phase0/spell_catalog.tsv` — all 151 abilities with the `SpellData` reference, metadata fields, and decoded effect lists.

**Remaining uncertainty:** `CollectionData.Data`/`SData1` semantics; whether `SData2` really is milliseconds; what distinguishes the 33 numbered `SpellN.SPL` files from the named ones; which character learns which ability (**not present in these files** — that mapping must live elsewhere, probably a `.gda` table, and is required before Phase 7 can reassign abilities between characters); and the per-bit status mapping.

---

## 2026-10-05 — GFF4 field layout decoded (all 1324 files, zero errors)

**Investigated:** The GFF4 internal field layout — the blocker for `.dlg`, `.gda`, `.are`, `.gui`, `.plo` and `.tlk`, and therefore for Phase 2 (dialogue PoC), Phase 6 (level cap), Phase 7 (ability→character mapping) and most of Phase 3.

**Method:** Per the project's research process, read xoreos' `gff4file.cpp`/`.h` first rather than guessing at bytes, implemented the format in [tools/recon/gff4.py](tools/recon/gff4.py), then validated structurally *and* semantically against the ROM's own files.

### Layout

```
0x00  char[4]  "GFF "
0x04  char[4]  version — "V4.0" (every file in this game) or "V4.1"
0x08  char[4]  platform — always "PC  " here, even on this DS title
0x0C  char[4]  content type FourCC   (G2DA / CONV / AREA / GUI  / PLTS / TLK  / GFF )
0x10  char[4]  content type version  (e.g. "V0.2")
0x14  uint32   structCount
      [V4.1 only: uint32 stringCount, uint32 stringOffset]
      uint32   dataOffset
then structCount x 16-byte struct templates:
      uint32 label (FourCC: "gtop"/"colm"/"rows"/"IMG "/"PANE"/...)
      uint32 fieldCount
      uint32 fieldOffset   (absolute from file start)
      uint32 size          (byte size of one instance)
then at each fieldOffset, fieldCount x 12-byte field definitions:
      uint32 label         (numeric field ID — GFF4 has no field *names*)
      uint32 typeAndFlags  (type = low 16 bits, flags = high 16 bits)
      uint32 offset        (offset within a struct instance)
```

Flags: `0x8000` LIST, `0x4000` STRUCT, `0x2000` REFERENCE.

**Key deduction — when the STRUCT flag is set, `type` is a struct-template index, not a primitive type code.** Spotted because `Adv_Shade.GDA`'s root fields carried types 1 and 2, which are exactly the template indices of `colm` and `rows`. Tested falsifiably across the whole corpus: every STRUCT-flagged field in all 1324 files resolves to a valid template index (a wrong interpretation would have produced out-of-range indices immediately).

Value location, relative to a struct instance base:
- **LIST**: uint32 at `base+offset` is a list offset relative to `dataOffset`; at `dataOffset+listOffset` sits a uint32 element count, elements immediately after. Struct elements are spaced by the template's `size`.
- **REFERENCE**: uint32 at `base+offset` is an offset relative to `dataOffset` pointing at the actual value.
- otherwise the value is inline at `base+offset`.

Strings are out-of-line: a uint32 count (including a trailing NUL) followed by the characters.

### Two traps that corrupt silently rather than failing

1. **String encoding differs by content type.** `TLK ` files store **8-bit CP-1252** text (1 byte/char); every other type stores **UTF-16LE** (2 bytes/char). Verified both directions: a GUI field decodes cleanly as UTF-16 (`"RootPanel"`) and as nonsense in 8-bit, while TLK is the reverse. Decoding a TLK as UTF-16 yields CJK mojibake (adjacent ASCII bytes pair into CJK code points) *and* reads twice as far as the string extends — so it silently bleeds into the next string instead of erroring.
2. **Do not dereference a REFERENCE'd string twice.** String fields in GDA row structs are `asciistring` **with the REFERENCE flag set**. Following the reference already lands on the string data; calling the normal "read string via offset" path then treats the character count as another offset and returns garbage from an arbitrary location. This was a real bug in the first version of the parser — it produced plausible-looking junk (`6??f????.??`) in `Levels.GDA` rather than throwing, which is exactly why the semantic checks below matter more than "it parsed".

### Validation

| Check | Result |
|---|---|
| Header + template + field-def parse, all GFF4 files | **1324 / 1324**, 0 failures |
| Structural validation (template indices valid, types known, inline fields fit within struct size) | **0 problems** across 1324 files |
| **Full recursive decode** of every file — every field, list, nested struct and string | **0 hard failures, 0 field-level errors** |
| GDA row field count == declared column count | **229 / 229 tables** |
| Semantic: TLK decode | **7,555 readable English strings** out of 18,845 entries |
| Semantic: GDA column hash recipe | 5/5 first probes matched real hashes |
| Semantic: `Statuses.GDA` name refs resolved against TLK | 14 of 16 statuses named |

Content types present (all `V4.0`, all platform `PC  `): `GFF ` 740, `G2DA` 229, `PLTS` 107, `CONV` 101, `ARE ` 79, `GUI ` 68. Note **the extension does not determine the content type** — 134 files have a `.gui` extension but only 68 carry type `GUI `, the rest being generic `GFF `.

The decisive proof is the TLK text, e.g. verbatim from `strings.tlk`:

```
17123  Look, Sonic! The robot's head is another Eggman device. It must be old if
       it's forgotten its programming!
6676   Don't worry. Those are just drones. They won't fight.
13810  We have a shipmmment of N'rrgal sweat for Kronnn. We're afrrraid to sennnd it....
```

Character-specific speech quirks (the N'rrgal's stutter) surviving intact is strong evidence the string offsets, counts and encoding are all correct. **This directly unblocks Phase 2** — the dialogue proof-of-concept now has concrete targets: TLK entries keyed by string ID.

### GDA (`G2DA`) structure, and the column-name problem

Three templates: `gtop` (root) holds two struct lists — `colm` (column definitions) and `rows`. Each `colm` entry is `{10001: columnHash, 10999: type}` where type `1` = integer and `0` = string. Each `rows` entry has one field per column, labelled sequentially from `10005`, mapping positionally onto the column list (verified: row field count equals column count in all 229 tables).

Columns are identified **only by hash**. Confirmed recipe:

```python
crc32(column_name.lower().encode('utf-16-le'))
```

Probes for `id`, `label`, `name`, `hp`, `attack` all matched real hashes on the first attempt. The ROM contains **845 distinct column hashes** — *exactly* the figure the xoreos team reported for their corpus, an independent confirmation that our GDA parse enumerates columns completely.

A dictionary attack ([tools/recon/gda_dict.py](tools/recon/gda_dict.py), ~573k candidates from curated game/RPG vocabulary plus tokens harvested from the ROM's own resource names and 2DA vocabularies) recovered **182/845 (21.5%)** — below xoreos' reported 63%, so **checking whether they ever published their dictionary remains the better path** (already flagged in RESEARCH.md) than grinding our wordlist. Recovered names are cached in `research/phase0/gda_columns.tsv` with per-hash usage counts, so the attack needn't be repeated. The largest unknown cluster is a column set shared by 33–50 cutscene/animation tables (`CH10_Cyclone.GDA`, `AnimationEvents.GDA`, `BasicCombatTut.GDA`).

Important: **unknown column names do not block modding.** The data decodes fine; only the human-readable header is missing, and meaning is often inferable from values (as with `Statuses.GDA` below).

### What the 229 GDA tables are — a map of the game's data

Tables that line up directly with roadmap phases: `Levels.GDA`, `spells.GDA`, `creatures.GDA`, `classes.GDA`, `party.GDA`, `Items.GDA`, `stores.GDA` + `Store1–5.GDA`, `plots.GDA`, `plotflags.GDA`, `chapters.GDA` + `Chapter0–10.GDA`, `Statuses.GDA`, `StatInfos.GDA`, `StatRedirect.GDA`, `statsinfocreature.GDA`, `squads.GDA`, `CombatRules.GDA`, `CombatActions.GDA`, `CombatAI.GDA`, `combo.GDA`, `rewards.GDA`, `RandItems.GDA`, `emeralds.GDA`, `SuperSonic.GDA`, `ChaoGarden.GDA`, `appearances.GDA`, `worldmap.GDA`. There are also 12 per-character `Adv_<Name>.GDA` tables (Sonic, Tails, Knuckles, Amy, Shadow, Rouge, Cream, Big, Omega, Shade, Eggman, plus `Adv_VFXTester`).

**A developer debug system shipped in the retail ROM:** ~30 `debug*.GDA` tables, including `debugLevelUp`, `debugLevelUp2`, `debugParty`, `debugCreateItems`, `debugCreateChao`, `debugCreatureStats`, `debugGameSpeed`, `debugSave`, `debugLoadSlots`, `debugQA`, `debugQAStats`, `debugFootwear`, `debugGloves`, `debugAccessories`, `debugUseItems`, `debugArea`/`2`/`3`, `debugSplash`. If any of this is reachable — or can be *made* reachable — it would accelerate testing for this entire project enormously (instant level-ups, item spawning, party manipulation, area warping are exactly the tools this roadmap needs). **Investigating reachability is now a high-value, low-cost experiment.** Not yet attempted.

**`Levels.GDA` is not the XP curve.** It is only 5×5 and holds schema-ish metadata (type codes like `"I"`, range codes like `"R1000"`, float defaults) rather than per-level data. So the level/XP progression for Phase 6 lives somewhere else — another table, or hardcoded in the ARM9 binary. Finding it is an open task.

### Status effects resolved (closes a loop from the `.itm` work)

`Statuses.GDA` is **16 rows**, matching the ~16-bit `RemoveStatus` bitmask found earlier in the item tables. Its name/description columns hold TLK string references, which resolve to:

| ID | Status | Developer description (verbatim, clearly internal) |
|---|---|---|
| 0 | Dead | "Dead as a door nail" |
| 1 | Paralyzed | "Stiff as a board" |
| 2 | Tinkered | "not tailored" |
| 3 | Poisoned | "only somewhat mildly poisoned" |
| 4 | ATKdown | "down ATK, bad ATK" |
| 5 | DEFdown | "down DEF, bad DEF" |
| 6 | ACCdown | "down ACC, bad ACC" |
| 7 | EVAdown | "down EVA, bad EVA" |
| 8 | LCKdown | "Can we say Black cat?" |
| 9 | ATKup | "Smash Bang Boom" |
| 10 | DEFup | "What a mighty shield" |
| 11 | ACCup | "ACC aCk akkk" |
| 12 | EVAup | "Devilish Dodge" |
| 13 | LCKup | "Lucky Clover" |
| 14, 15 | (unnamed — string ref -1) | — |

This also reveals two stats not in the item/ability stat-ID table: **ACC (accuracy)** and **EVA (evasion)**.

**Remaining uncertainty on the bitmask:** the status *list* is now authoritative, but the exact bit↔status correspondence in `RemoveStatus` masks is **not** pinned down. The obvious `1 << id` reading produces non-intuitive pairings (e.g. it would make the ATK-boosting `RockSalt` cure ATKdown but the ATK-boosting `PruneJuice` cure ACCdown), so this needs a live in-game or debugger test rather than more inference.

---

## 2026-10-05 — Debug menu: data fully intact, code path appears stubbed (likely NOT reachable)

**Investigated:** Whether the developer debug menu found in the previous session is reachable — i.e. whether this is working test infrastructure we could unlock, or just orphaned data.

**Short answer: the data is 100% intact and the `CDebugMenu` class scaffolding is still in the retail binary, but every content-bearing string the menu would need is absent from ARM9. Best current judgement: not reachable by any input combination or flag flip; reviving it would mean re-implementing the menu, not unlocking it. This is not yet proven by a debugger run — see the recommended experiment below.**

### What exists (confidence: high)

The debug menu **data** is complete and readable. `debug.GDA` is a 24-entry root menu with human-readable labels and command strings; ~25 submenu tables hang off it. Full dump: `research/phase0/debug_menu.txt`. Root entries include Save/Load Game, Create Item, Use Item, Player Pos, Toggle Debug Strings, Adjust Placeables, Dump Mem Stats, Level Up, Add/Remove Party Member, Jump To Area, Mem Use, Toggle Enter Combat, Toggle Walk Mesh, QA Console Commands, Create Chao, Show/Fill Inventory, Dump Plot Table, Show Creature Stats.

Two entries — `SaveGameToPC %NITROSDK_ROOT%...` / `LoadGameFromPC %NITROSDK_ROOT%...` — reference the Nintendo SDK root environment variable, confirming this is the genuine internal development menu (those features only work against a devkit host).

Supporting assets exist too: `_debug.dlg` and `walkmeshdebug.NCGR` (a texture matching the "Toggle Walk Mesh" command).

### What's in the code (confidence: high for the addresses)

Following the C++ RTTI chain in ARM9:
- Mangled type name `10CDebugMenu` at ARM9 `0xF8BA4`, plus `9SingletonI10CDebugMenuE` (i.e. `Singleton<CDebugMenu>`) alongside it.
- typeinfo struct at `0xF8B98` → vtable at `0xF8BB8` containing **three THUMB function pointers** (`0x02027881`, `0x020278A5`, `0x0202789D`), all verified to contain valid THUMB prologues/epilogues (`push {r4, lr}` … `pop {r4, pc}`).
- **Three code sites store the class's vptr (`0x020F8BBC`)** — at ARM9 `0x2FE6C`, `0x301D0`, `0x30A50 — so constructors for the class exist in the binary.

Addresses recorded in [KNOWN_FUNCTIONS.md](KNOWN_FUNCTIONS.md). This **disproved my initial hypothesis** that the class had been dead-stripped entirely.

### What's missing — the decisive evidence

Despite the class existing, searches across the whole 1.09 MB ARM9 binary found **none** of the following, in ASCII *or* UTF-16LE:

| Searched | Hits in ARM9 |
|---|---|
| `debug.gda` (the resource the menu must load) | **0** |
| `SubDebug`, `ToggleCombat`, `ToggleWalkmesh`, `DumpPlotTable`, `FillInventory`, `MemUse`, `DumpStats`, `OutputPlayerLoc`, `ShowSquadInventory`, `EnableInteractive`, `SaveGameToPC` | **0 each** |
| any case-insensitive `debug` substring | **2 — both RTTI type names, nothing else** |
| `walkmeshdebug` (the debug texture's name) | **0** |
| a debug-specific `.gui` layout asset in the archive | **none exists** |

Every one of those command strings occurs exactly **once in the entire ROM** — inside the GDA data itself — and `debug.GDA`'s only whole-ROM occurrence is its own `erf.dict` filename entry. **Nothing anywhere references the root debug table.**

This is the crux: the command dispatcher must compare the command strings read from the GDA against something. A binary containing none of those strings cannot dispatch them. So even if a `CDebugMenu` could be constructed and drawn, selecting an entry could not do anything. The pattern — class infrastructure (ctor/dtor/vtable/RTTI) retained while all content strings vanish — is what an `#ifdef`'d-out implementation body looks like: the data files are produced by a separate asset pipeline and shipped wholesale, while the code that consumed them was compiled out of the retail build.

I also checked whether the engine might reference resources by precomputed hash rather than name (it resolves HERF resources by DJB2, and normalizes case — established earlier). Searching ARM9 for DJB2 hashes of `debug.gda`/`debug.GDA` found nothing — **but so did controls** (`erf.dict`, `strings.tlk`, `Statuses.GDA`) and the CRC32 hashes of known GDA columns (`id`, `name`, …). Since the controls also found nothing, that test is **uninformative**, not evidence either way: GDA columns are likely read positionally, and resource names evidently come from data rather than hardcoded hashes. Recording this so nobody repeats the dead end.

### Verdict and remaining uncertainty

**Practical answer: treat the debug menu as not reachable.** Unlocking it is not a matter of finding a button combo or flipping a build flag; the dispatch layer isn't there to unlock. Restoring it would be a code-injection project — re-implement menu rendering and ~30 command handlers against the existing data — which is far beyond current project scope and well down the roadmap.

**What would settle it definitively** (cheap, and worth doing before anyone invests further): set an execution breakpoint at `0x0202FE6C` (a vptr store site) or on the vtable address `0x020F8BBC` in melonDS's GDB stub or DeSmuME's debugger, then play normally. Never hit ⇒ dead code, question closed. Hit ⇒ the object *is* being constructed during play, and the investigation reopens around how it is displayed. I have **not** run this; the verdict above is inference from static analysis only.

### The consolation prize is substantial

The debug data is valuable **regardless of reachability**, because it documents IDs in plain language. Promoted to [KNOWN_IDS.md](KNOWN_IDS.md):

- **Character/party IDs** — Sonic 0, Knuckles 1, Tails 2, Amy 3, **Shadow 4**, Rouge 5, Big 6, Cream 7, Omega 8, Eggman 9, Shade 10-or-27, Super Sonic 68. This is exactly the mapping flagged as a blocker during the `.spl` work, obtained for free. (Shade is genuinely inconsistent in the source data: `AddPartyMember 27` vs `RemovePartyMember 10`.)
- **Area IDs** 0–22 with names (SBG, Well, Kron, Green Hill, Central City, Metropolis, GUN HQ, Workshop, BlueRidgeZone, angelisland, Groundzero, Nrrgal, Tyxis, VoxaiA/B, Nocturne, MysticRuins, Abandoned Lair variants, plus a `GrafXTest` dev area).
- **An engine command glossary** (`GiveXP`, `LevelUp`, `MoveToArea`, `SetPlayerFatigue`, `KillSquad`, `ToggleEnemies`, …) describing what operations the engine actually supports — a useful map of the levers this project will eventually want to pull.

**Evidence:** `research/phase0/debug_menu.txt` (all debug tables decoded in full).

---

## 2026-10-05 — Phase 6: XP curve and stat growth located — **level cap is 30**, and it's per-character

**Investigated:** Where the level/XP progression lives, after `Levels.GDA` turned out to be schema metadata rather than data.

**Method:** Scanned all 229 GDA tables for strictly-increasing integer columns with a meaningful span — a progression curve can't hide from that. Found it immediately.

### The answer: `Adv_<Character>.GDA`

Each of the 11 playable characters has its **own** 16-column × 30-row progression table. Columns (recovered names): `id`, `level`, `xp`, `speed`, `attack`, `defense`, `hp`, `power`, `grit`, `luck`, `fatigue`, `combat`, plus 4 still-unnamed columns.

**The `level` column runs explicitly 1 → 30 in all 11 tables, so the vanilla level cap is 30.** (`Adv_VFXTester.GDA` is a developer test table — 20 rows, flat 100,000,000 XP — not real content.) The roadmap's plan to "first prove level 31" is therefore exactly right: 31 is the first value beyond vanilla.

Full dump of all 12 tables: `research/phase0/progression_tables.txt`.

### XP is a cumulative threshold, and the curve has a sharp design break

Sonic's thresholds: `0, 200, 490, 911, 1520, 2404, 3686, 5545, 8240, 12149, 17815, 26032, 37947, 55223, 80273, 116596, 169265, 225634, 300369, 400935`, then `466487, 543462, 620436, …, 1159258`.

The per-level deltas reveal two distinct regimes:

| Levels | Delta behaviour |
|---|---|
| 1 → 20 | **Exponential** — 200, 290, 421, 609, 884, 1282, … 100,566 |
| 21 → 30 | **Flat** — 76,974 / 76,975 every level, alternating |

So the top ten levels are a constant grind rather than a continuing curve, and the alternating 76974/76975 suggests the linear tail was generated by dividing a total and rounding. Worth knowing for Phase 6: a naive "extend the exponential curve to level 50" would not match the game's own design intent, which deliberately flattens after 20.

### Progression is per-character, with meaningfully different costs

XP required for level 2, by character: **Sonic 200** (cheapest), Cream 226, Tails 253, Knuckles 279, Omega 305, Amy 332, Eggman 358, Big 385, Shade 411, Rouge 437, **Shadow 464** (most expensive). At level 30 the totals range from Rouge's 952,810 to Eggman's 2,643,707.

This matters for Shadow Mode (Phase 5): **Shadow has the most expensive early curve in the game**, so making him the starting character inherits a noticeably slower early progression than Sonic's unless the table is also adjusted.

### Independent cross-validation

`creatures.GDA` (128 rows × 61 columns) holds base stats, and its values match each character's **level-1 row** exactly — e.g. Sonic (creature 0): `speed 7, attack 8, defense 14, health 33`, identical to `Adv_Sonic.GDA` level 1; Shadow (creature 4): `speed 7, attack 8, defense 18, health 30`, identical to `Adv_Shadow.GDA` level 1. Two independently-decoded tables agreeing is good evidence both are being read correctly.

(Incidentally, creature 68 = Super Sonic carries `health 9999, attack 99, power 500` — the transformation entry.)

### Resolved: the Shade ID contradiction was two different ID spaces

The previous session flagged `AddPartyMember 27` vs `RemovePartyMember 10` as an unexplained inconsistency. `party.GDA` settles it — it has both `id` and `creatureid` columns:

| party slot `id` | name | `creatureid` |
|---|---|---|
| 0–9 | Sonic, Knuckles, Tails, Amy, Shadow, Rouge, Big, Cream, Omega, Eggman | 0–9 (identical) |
| 10 | Shade | **27** |
| 11 | SuperSonic | **68** |
| 12 | VFXTester2 | **72** |

The two spaces coincide for the first ten characters and diverge after, so the debug menu's add/remove entries were simply using different ID spaces. Shade is **party slot 10, creature 27**. Corrected in [KNOWN_IDS.md](KNOWN_IDS.md).

### The open question for Phase 6

**Is the cap enforced by the table row count, or by a hardcoded constant?** No GDA column anywhere in the ROM holds a constant 30 (checked all 229 tables), so there is no data-driven cap value to edit. That leaves two possibilities:

1. The engine reads the row count of the `Adv_` table → extending the cap is **pure data editing** (append rows), which would make Phase 6 dramatically cheaper than expected.
2. The cap is a constant in the ARM9 binary → extending it needs a code patch as well as data.

`Adv_VFXTester.GDA` having only 20 rows hints the engine may tolerate varying row counts, but it's a test table that may never be loaded, so that's suggestive, not evidence.

**Recommended experiment (cheap, decisive):** append a level-31 row to one character's `Adv_` table, rebuild, and level that character up in the emulator. If they reach 31, the cap is data-driven. This is a good Phase 6 opener, though it depends on the Phase 1 rebuild pipeline (the write path) which does not exist yet — the `.small` recompression and HERF-rebuild gaps are still open.

**Evidence:** `research/phase0/progression_tables.txt` (all 12 `Adv_` tables in full).

---

## 2026-10-05 — Phase 1 + Phase 2: write pipeline built, dialogue edit round-trips end to end

**Built:** The write side of the pipeline — original ROM → validate → extract → edit → rebuild → verify → patch → report. Driver: [tools/build/build.py](tools/build/build.py). The roadmap's Phase 2 proof of concept (modify ONE dialogue string) now passes every automated stage; only in-game visual confirmation remains.

### ROM layout rules (confirmed)

- Every one of the 303 NitroROM files starts on a **512-byte boundary** (verified: `start % 512 == 0` for all 303).
- Inter-file padding is **`0xFF`**, and every observed gap is < 512, i.e. pure alignment padding with no extra slack.
- Header `0x80` (`total_used_rom_size`) equals the end offset of the last file.
- The header CRC16 at `0x15E` is **CRC-16/MODBUS over bytes `0x000`–`0x15D`** — confirmed by recomputing it and reproducing the stored `0xE370`.

### The foundational guarantee

[tools/build/rom_build.py](tools/build/rom_build.py) is built around one invariant: **a rebuild with no replacements must reproduce the input byte-for-byte.** `--verify` asserts it, and it passes (303 files, 0 moved, 134,217,728 bytes identical). Without that, no edit could be trusted — a plausible-looking ROM proves nothing.

### TLK editing: surgical, not re-serialized

[tools/build/tlk_write.py](tools/build/tlk_write.py) edits talk tables by patching the original bytes rather than re-serializing. Re-serializing would reorder the whole string blob and produce an entirely different file; surgical editing keeps a no-op byte-identical and keeps real diffs minimal.

**A correctness trap found and handled:** the original TLK **deduplicates strings** — 487 distinct offsets are shared, covering **1,448 entries**. Editing a shared string in place would silently rewrite the text of every entry pointing at it. So a shared string is never edited in place; a fresh copy is appended and only the target entry repointed. Verified explicitly: after editing one of 7 entries sharing a string, the edited entry reads back as the new text and a peer entry is unchanged.

Storage strategy: in place when the string is unshared and the new text fits the existing slot (keeping the original count so nothing bleeds into the next string), appended otherwise. All three paths are tested by `--verify`.

### Patch generation: BPS, and why the first attempt was useless

IPS is unusable here — its offsets are 24-bit, capping it at 16 MB against a 128 MB ROM. BPS has no such limit and carries CRC32s of source/target/patch, so applying it to the wrong base ROM is detected rather than silently mis-patching.

My first encoder emitted only `SourceRead`/`TargetRead` and produced a **46 MB patch for a 68-byte text edit**. The cause is worth recording: growing a file pushes every later file forward by one 512-byte sector, so ~80 MB of *byte-identical* data sits at a *different* offset, and a same-position-only encoder has to emit all of it as literals. Adding **`SourceCopy`** (which expresses "same bytes, moved") with candidate offsets probed at whole-sector shifts took the same patch to **303 bytes** — a ~150,000× reduction, still verifying as an exact reproduction. Candidate selection is deliberately targeted at sector-multiple shifts rather than a general content-indexed search, because alignment-driven movement is the only relocation this pipeline produces; it will not spot arbitrary moves the way beat or xdelta would.

### End-to-end result

| Stage | Result |
|---|---|
| 1. No-op rebuild byte-identical | **pass** (303 files, 0 moved) |
| 2. No-op TLK serialize byte-identical | **pass** (18,845 entries) |
| 3. Rebuild with edit | 685,532 → 685,600 byte TLK; 10 files shifted by 512 bytes |
| 4. Edited string read back **from the rebuilt ROM** via the independent GFF4 reader | **pass** |
| 4b. Untouched control string (id 17123) unchanged | **pass** |
| 5. BPS patch reproduces the rebuilt ROM exactly | **pass** (303 bytes) |

Post-build integrity checks on the rebuilt ROM: header CRC16 valid; `test.herf` still reports 8691 resources / 8690 names; all five language TLKs still parse at 18,845 entries each; 7,555 entries still carry text. The 10 shifted files (4 language TLKs + all 6 HERF archives) all survived relocation intact.

**The original ROM was confirmed untouched** — CRC32 `503C3E4C` before and after the run. It is opened read-only and all output goes to `build/`.

### What the pipeline does *not* yet do

- **No HERF rebuild.** The Phase 2 target (`strings.tlk`) is a loose NitroROM file, so this run never had to repack an archive. Editing anything inside `test.herf` — items, abilities, the `Adv_` progression tables, dialogue `.dlg` files — needs a HERF writer that recomputes the resource table's sizes and offsets. **This is now the single biggest gap**, because almost all the interesting data lives in that archive.
- **No `.small` compression.** Writing a `.small` resource can use the trivially-correct stored type (`0x00`); LZ77 re-encoding remains unproven.
- **No GFF4 writer for arbitrary types.** `tlk_write.py` handles TLK specifically. Appending a row to a `G2DA` (needed for the level-cap experiment) requires growing the row list and fixing offsets — a different job.
- **In-game verification is still manual.** The tooling proves the bytes are right; it cannot confirm what appears on screen.

**Artifacts:** `build/sonic_chronicles_modded.nds`, `build/sonic_chronicles_modded.bps` (303 bytes), `build/build_report.json`.

---

## 2026-10-05 — HERF writer built: archive contents are now editable end to end

**Built:** The HERF writer ([tools/build/herf_write.py](tools/build/herf_write.py)) that was blocking every data-driven mod, plus the two small editors needed to make it useful and a driver that takes an archive edit all the way to a verified patch ([tools/build/build_mod.py](tools/build/build_mod.py)).

This unblocks the items, abilities, progression curves, GDA tables and `.dlg` conversations — i.e. essentially all the interesting data, which lives inside the 49 MB `/test.herf` rather than as loose ROM files.

### Archive layout rules (confirmed against `/test.herf`, 8691 resources)

- Resource table runs bytes `8`–`104300` (8 + 8691×12), and the lowest resource offset is **exactly** 104300 — data begins immediately after the table, no padding.
- **Every resource offset is 4-byte aligned** (verified for all 8691).
- Gaps between consecutive resources are 0–3 bytes, i.e. alignment padding only. There is no spare slack anywhere.
- No resources overlap. The archive ends one byte past the last resource.

### Strategy: surgical replace, same as the TLK writer

- New payload **fits the old slot** → written in place; only the table's `size` field changes and nothing moves.
- Otherwise → **appended** at the 4-byte-aligned end and the table's `offset`/`size` repointed.

Either way the other 8690 resources stay put, so a no-op save is byte-identical and real edits produce a minimal diff. That matters disproportionately here: a full relayout of a 49 MB archive would rewrite the entire file and (via the ROM rebuild) produce an enormous patch.

When a payload shrinks, the leftover bytes of the old slot are deliberately **not** zeroed — nothing reads past a resource's recorded `size`, and rewriting them would enlarge the diff for no benefit.

**Deliberately unsupported: adding or removing resources.** That changes the resource-table length, which shifts every resource's data and would also require rebuilding the `erf.dict` name dictionary. Replacement covers the modding cases this project needs.

### Supporting editors

Two small tools, because editing these formats by hand is error-prone:

- [tools/build/twoda_write.py](tools/build/twoda_write.py) — sets a cell in a plain-text 2DA **by row label and column name**, rewriting only that field's characters. This exists because the naive approach fails: my first attempt did a raw `replace('\t10\t', ...)` and silently matched nothing, because the real bytes are `10 ` with a *trailing space* before the tab. The files are inconsistently delimited (tabs, space runs, trailing spaces, names containing spaces), so editing them as plain text without going through the parser is a trap. Every edit is re-read through the parser to prove it took.
- [tools/build/gda_write.py](tools/build/gda_write.py) — sets a fixed-width **integer** cell in a binary GDA in place, so file length is unchanged and there are no offsets to fix. Integer columns only; string columns are out-of-line and variable-length. Row adding/removing is not supported — **that is what the level-cap experiment will need.**

### Verification

`herf_write.py --verify` exercises every path against the real archive:

| Check | Result |
|---|---|
| No-op archive serialize byte-identical | **pass** (49,289,296 bytes, 8691 resources) |
| Structural validation (alignment, bounds, overlaps) | **clean** |
| Text 2DA edit, same length → in-place path | **pass** |
| Text 2DA edit, longer → append path | **pass** (new offset at old EOF) |
| Binary GDA integer edit → in-place | **pass** |
| Untouched control resource bit-identical | **pass** |
| Post-edit structural validation | **clean** |

### End-to-end demonstration mod

`build_mod.py` applies three changes chosen to be real rather than synthetic, one per editable surface:

1. `Spell_Tough.spl` — ability magnitude `GRT+` 10 → 20 (text 2DA)
2. `Item22.ITM` (LightSlippers) — `DEF+` 1 → 5 (text 2DA)
3. `Adv_Shadow.GDA` — XP thresholds for levels 2 and 3 lowered from 464/872 to Sonic's 200/490 (binary GDA)

Edit 3 acts on an earlier finding: Shadow has the most expensive early curve in the game, which would make him a sluggish starting character for Shadow Mode (Phase 5). This is the first change in the project that serves a roadmap goal rather than just proving plumbing.

Results:

| Stage | Result |
|---|---|
| No-op ROM rebuild + no-op archive serialize | **pass** |
| All three edits, in place | archive size **unchanged** (49,289,296 bytes) |
| Post-edit archive validation | **clean** |
| ROM rebuild | **0 files moved**, `total_used_rom_size` unchanged |
| All three edits read back from the **rebuilt ROM** | **pass** |
| Control resource `Item10.ITM` unchanged | **pass** |
| Regression sweep: every GDA table still decodes | **pass** (229/229) |
| Full regression: all GFF4 files in the repacked archive decode | **pass** (1324, 0 failures) |
| BPS patch reproduces the rebuilt ROM exactly | **pass** |

**Patch size: 165 bytes** for three gameplay changes in a 128 MB ROM. Because all three edits fitted their existing slots, the archive didn't change size and **no ROM files moved at all** — the best case for patch size, and a direct argument for preferring same-or-shorter edits where possible.

Original ROM confirmed untouched: CRC32 `503C3E4C` before and after.

### What remains before the level-cap experiment can run

The one missing piece is **adding a row to a GDA**. Extending the cap past 30 means appending a level-31 row to an `Adv_*.GDA`, which grows the row list and shifts every offset after it — a real GFF4 *writer*, not the in-place integer editor built here. With that, the decisive test from the progression work (does the engine read the row count, or is 30 hardcoded in ARM9?) becomes runnable.

Also still open: `.small` recompression (stored type `0x00` remains a correct fallback), and in-game visual confirmation, which tooling cannot do.

**Artifacts:** `build/sonic_chronicles_datamod.nds`, `build/sonic_chronicles_datamod.bps` (165 bytes), `build/build_report_datamod.json`.

---

## 2026-10-05 — Combined build: both write paths in a single ROM rebuild

**Built:** [tools/build/build_combined.py](tools/build/build_combined.py) — applies a loose-ROM-file edit (dialogue in `strings.tlk`) **and** archive-content edits (inside `/test.herf`) in one `Rom.build()` call, so all four demonstration changes ship in a single ROM for one emulator session.

This is the first build to exercise both write paths simultaneously, which is the case that actually matters: the TLK **grows** by 68 bytes, which shifts later ROM files — **including the archive we also edited**. Passing both replacements into one rebuild resolves offsets together rather than in two passes, where the second pass would be working from stale offsets.

| | |
|---|---|
| Source | EU ROM, CRC32 `503C3E4C` |
| Output | `build/sonic_chronicles_combined.nds`, CRC32 `99420726` |
| Files moved | 10 (TLK growth pushed the 4 other language TLKs and all 6 HERF archives forward one sector) |
| Patch | **440 bytes** |

Edits: dialogue id 6676 (appended, TLK grew); `Spell_Tough.spl` `GRT+` 10→20, `Item22.ITM` `DEF+` 1→5, `Adv_Shadow.GDA` xp rows 1–2 → 200/490 (all three in place, archive size unchanged).

Verification — all passed:
1. No-op ROM rebuild byte-identical; no-op TLK and no-op archive serializes byte-identical
2. All four edits read back from the **rebuilt** ROM via the independent readers
3. Control dialogue entry (id 17123) and control resource (`Item10.ITM`) both unchanged
4. Every GFF4 resource in the repacked archive still decodes (0 failures)
5. All four other language TLKs still parse at 18,845 entries each — these were *relocated* by the TLK growth, so this specifically checks that the shift didn't corrupt them
6. BPS patch reproduces the rebuilt ROM exactly

Original ROM confirmed untouched (CRC32 `503C3E4C` before and after).

**Known debt:** this is the third driver (`build.py`, `build_mod.py`, `build_combined.py`) sharing the same stage scaffolding. They should collapse into one profile-driven builder — that is roadmap Phase 17 (mod profiles), deliberately not built yet since the project rules warn against inventing configuration fields before the underlying behavior is confirmed. The behavior for *these* edit types is now confirmed, so Phase 17 has a real foundation to build on when its turn comes.

---

## 2026-10-05 — **PIPELINE CONFIRMED IN GAME** — and stat 26 identified as "Armor"

**The entire read→edit→rebuild→play chain is now verified by the engine itself**, not just by our own readers. A diagnostic build set every positive stat bonus on every item to 99 (163 stat rows across 124 items, 105 of them taking the archive *append* path). In DeSmuME 0.9.11, SpeedySneakers displayed **"Speed +99"** on screen.

This closes the loop that every prior entry could only verify at the byte level: ROM rebuild → HERF repack → 2DA item edit → **engine reads it → renders it**. Evidence: user screenshot of the in-game item panel. Confidence: as high as it gets — this is the game's own renderer.

It also incidentally validates the `.small`/HERF append path under load, since the archive grew ~36 KB and 10 ROM files shifted, and the game still ran.

### Stat 26 (GRT) is the player-facing "Armor"

`Item34.ITM` (SpeedySneakers) grants exactly two bonuses — `SPD+` (stat 21) and `GRT+` (stat 26) — and its in-game description reads:

> "Light and well cushioned for more agility. Slightly increases armor."

"agility" ↔ SPD, "armor" ↔ GRT. The TLK contains both `Grit` and `Armor` as standalone label strings. Recorded in [KNOWN_IDS.md](KNOWN_IDS.md).

### Stat 26 is absent from the item tooltip's numeric list

With every bonus at 99, the tooltip showed **only** `Speed +99` — no Grit/Armor line. The user confirms this matches vanilla, so it is not an artefact of the edit.

The item's two rows are structurally identical apart from the stat ID:

```
SPD+   ID=3  EffectId=1  Data=3  SData1=21  SData2=0  SData3=0  Pulse=-1
GRT+   ID=4  EffectId=1  Data=1  SData1=26  SData2=0  SData3=0  Pulse=-1
```

So nothing in the item data suppresses it — this is UI behaviour. Supporting hint: of the 24 items whose *only* stat bonus is `GRT+`, most are Chao items, consistent with Grit being a secondary stat surfaced through prose rather than the tooltip.

**Two hypotheses, resolved by experiment:**

| | Hypothesis |
|---|---|
| H1 | the tooltip renders only the **first** stat row |
| H2 | the tooltip renders every row **except** stat 26 |

[tools/build/build_stat_test.py](tools/build/build_stat_test.py) retargeted SpeedySneakers' rows — first row → stat 26 (Grit), second row → stat 22 (Attack), both at 99 — so one ROM distinguished them. Built and byte-verified (`build/sonic_chronicles_stattest.nds`, CRC32 `A7A8ECC0`, 420-byte patch).

**Result (confidence: high — observed in game, user screenshot): `Attack +99` displayed, nothing else. H2 confirmed.**

- The **second** row rendered ⇒ the tooltip is *not* limited to the first row, killing H1.
- The **first** row rendered nothing, and that row targeted stat 26 ⇒ the tooltip specifically skips stat 26.

**Conclusion: the item tooltip deliberately omits stat 26 (GRT / "Armor") from its numeric list.** It is not positional and nothing in the item data causes it — the engine's tooltip code excludes that stat. Vanilla behaviour, independent of any modification.

The same screenshot demonstrates the description-staleness problem concretely: the item now grants **zero Speed** and +99 Attack, while its description still reads *"…for more agility. Slightly increases armor."* The description is a hand-written TLK string with no link to the stat rows.

Incidentally this build is a live demonstration of an earlier finding: the row labels still read `SPD+` and `GRT+` while now targeting Grit and Attack respectively. **Labels are comments; the engine keys off `SData1`.**

### Practical consequence for Phase 8

Rebalancing Grit/Armor is **invisible in the item tooltip**, so such changes won't communicate themselves to players. Separately, item descriptions are hand-written TLK strings that do **not** track stat data — a rebalanced item keeps describing its old behaviour unless its description string is edited too. Both constraints should shape the equipment overhaul design rather than being discovered late.

---

## 2026-10-05 — **LEVEL CAP IS DATA-DRIVEN** — level 31 reached in game (Phase 6 unblocked)

**Question:** the vanilla cap is 30 and no GDA column anywhere holds a constant 30, so the cap was either (A) derived from the progression table's **row count**, or (B) a hardcoded constant in ARM9. These have very different costs — (A) makes Phase 6 pure data editing, (B) requires a code patch.

**Experiment:** [tools/build/build_levelcap_test.py](tools/build/build_levelcap_test.py) appended a level-31 row to all 11 playable characters' `Adv_<Character>.GDA` tables and flattened every XP threshold to 100/level (so the cap is reachable from an existing mid-game save rather than requiring a full playthrough). Built, byte-verified, and run in DeSmuME 0.9.11.

**Result (confidence: high — observed in game): the character reached level 31.**

**Conclusion: the level cap is derived from the number of rows in the `Adv_<Character>.GDA` progression table. There is no hardcoded cap to patch.** Extending the cap is pure data editing — append rows, and the engine honours them.

This is the single most valuable finding for the roadmap so far. Phase 6 ("Expanded progression", targeting level 50 and possibly 99) was budgeted as a reverse-engineering problem requiring ARM9 work; it is instead a data problem, already solved by tooling that exists.

### How the row-writer works, and why it was simple

Checking the byte layout before writing code paid off. In `Adv_*.GDA`:
- **all 16 row columns are plain `sint32`** — no strings, lists, references or structs;
- the **row array is the last thing in the file** (verified: `rows_end == EOF`, 0 trailing bytes).

Under those two conditions appending a row needs **no offset fixups at all**: bump the `uint32` count in the row list header, append `rowSize` (64) bytes. `gda_write.append_row` **checks both preconditions and refuses** otherwise, because they are specific to these tables — `Levels.GDA`, for instance, has `asciistring` columns and would need a full re-serializer. Failing loudly beats silently corrupting a file.

Level 31 stats were extrapolated by repeating each column's final 29→30 delta, so the new row is a plausible continuation. Zeroes were deliberately avoided: a character arriving at level 31 with 0 HP would make a "reached 31" result ambiguous.

### Verification chain

| Check | Result |
|---|---|
| No-op ROM rebuild + no-op archive serialize byte-identical | pass |
| All 11 tables: 31 rows, `level` column exactly 1..31, `xp` 0..3000 | pass |
| All 229 GDA tables still decode in the repacked archive | pass |
| BPS patch reproduces the rebuilt ROM exactly | pass (27,246 bytes) |
| **In game: character reached level 31** | **pass** |

**The game states the cap itself.** Shadow's profile at level 31 reads **"Next Lv: Level Cap"** — the UI reads the cap from the same table, so the engine genuinely treats 31 as the maximum rather than merely tolerating the extra row.

### LEVEL 99 REACHED — the cap has no practical ceiling

A follow-up build extended all 11 tables to **99 rows**. **Result (confidence: high — observed in game): Tails reached Level 99.**

**Phase 6 is solved.** The level cap is limited only by the number of rows in the progression table. No ARM9 patch, no hardcoded constant, no UI or save-format ceiling up to at least 99. The roadmap's targets of 50 and 99 are both achievable by data editing alone.

Verification against `Adv_Tails.GDA` level 99 confirmed the stat model a second time, now including values in the thousands:

| Stat | Table (lv99) | In game | Note |
|---|---|---|---|
| HP | 1502 | **1502/1502** | exact |
| Attack | 193 | **193** | exact |
| Luck | 188 | **188** | exact |
| Speed | 112 | 120 | +8 equipment |
| Defense | 132 | 142 | +10 equipment |
| fatigue | 26 | **PP 26/26** | exact |

**This also confirms stat 28 (internally FP / FATIGUE) is displayed as "PP"** — POW Points, the resource POW moves consume. Previously inferred from `HealFATIGUE`/`FP+` sharing an ID; now directly observed.

### Column `#441910439` identified: cumulative bonus points

The level-99 character arrived with only **1 bonus point** despite gaining 69 levels. The cause was in the extrapolation, and it identified the column:

In vanilla, column 11 (`#441910439`) runs **1, 2, 3 … 20 and then plateaus at 20** from level 20 onward. The extrapolation repeats each column's final delta, which for this column is **zero** — so it stayed frozen at 20 across every added level, and the game awarded no points for levels 31–99.

**That failure is itself the evidence: column 11 is the cumulative count of bonus (stat allocation) points available at a given level.** A vanilla level-30 character therefore has 20 to spend. The level-up screen's "Bonus Point!" and the ◀ ▶ allocation arrows on Speed/Attack/Defense/Luck are spending that pool.

`build_levelcap_test.py` now gives this column +1 per added level (rebuilt: level 99 shows **89** = 20 vanilla + 69 added). Confidence: high for the identification, **unverified in game** for the corrected build.

**Implication for Phase 6 design:** extending the cap is not just about adding rows — a real level-cap mod must also decide how bonus points scale, or extra levels confer stat growth but no player agency. Worth a design decision rather than a default.

### Bonus: the stat model is confirmed arithmetic

The same screenshot validated how displayed stats are computed. Shadow at level 31, wearing Speedy Sneakers and Cursed Gloves:

| Stat | `Adv_Shadow.GDA` lv31 | Equipment | Expected | Displayed |
|---|---|---|---|---|
| HP | 535 | — | 535 | **535/535** |
| Atk | 66 | CursedGloves `ATK- -2` | 64 | **64** |
| Def | 62 | CursedGloves `DEF- -2` | 60 | **60** |

**Displayed stat = progression-table value at the character's level + equipment modifiers.** Exact agreement on three independent stats, including a negative modifier.

### The character profile displays only 4 of the ~11 stats

The profile panel shows **Spd (21), Atk (22), Def (23), Lck (27)** and nothing else. **POW (25) and GRT (26) are both hidden** — extending the earlier tooltip finding from stat 26 alone to the stats panel and to POW as well.

This matters because **POW is the damage stat** in this game (Atk governs accuracy). So the game hides the single most important combat number: Shadow's profile declares him "Power Class" while never showing his Power value (60 base at lv31, +6 from Cursed Gloves).

**Lead for Phase 8 / the brief's "expose interesting systems" goal:** the archive holds 134 `.gui` files in GFF4 format, which the project can now both read and write. If the profile panel's stat list is data-driven in one of those, adding POW and GRT rows would make the hidden stats visible — a genuinely useful quality-of-life mod built entirely on confirmed tooling. Not yet investigated.

---

## 2026-10-05 — Profile stat display mapped: POW/GRT need an ARM9 patch, not data

**Investigated:** whether POW (25) and GRT (26) can be made visible in the character profile, which shows only Spd/Atk/Def/Lck plus HP and PP.

**Method:** decoded `ProfileCreaturePanel.gui`, which required extending the GFF4 reader to resolve **generics** — GUI files store heterogeneous child widgets as generic lists, and the reader previously returned them raw. A generic element turned out to be an **8-byte `(typeAndFlags, offset)` pair** using the same encoding as a field definition: when the STRUCT flag is set, `type` is a struct-template index. Verified against the root panel (`0x40000002` → flags `0x4000`, template 2 = `PANE`). [tools/recon/gff4.py](tools/recon/gff4.py) now walks GUI trees.

**Found:** the stat rows are label+value widget pairs in `EquipmentDataPanel` — `CSP`/`CSPV`, `CAT`/`CATV`, `CDE`/`CDEV`, `CLU`/`CLUV`, plus `CLevel`, `CHP` and `CFP` (labelled "PP", confirming stat 28 = FP = PP).

**The decisive detail: value widgets carry no stat binding.** Their only content is the placeholder text `'99'` and their name; field 60029 is a sequential tab index shared by each pair, not a stat ID. The engine fills them **by widget name** — and those names are hardcoded in ARM9 as a **7-entry pointer array at RAM `0x020BE944`** (4-byte spacing), pointing at a contiguous string table at `0x0210666C`.

**Conclusion (answers the question asked): POW and GRT cannot be made visible by data editing.** Adding `CPOWV`/`CGRTV` widgets to the `.gui` would draw labels that nothing populates — they would render the literal `'99'` placeholder. The stat list *is* table-driven, but the table is in the ARM9 binary rather than a GDA, so this needs a code patch.

That is a genuine limit of the current tooling, not a gap in the investigation. The patch target is now precisely located and recorded in [KNOWN_FUNCTIONS.md](KNOWN_FUNCTIONS.md) — the pointer array at `0x020BE944` is the first concrete ARM9 patch candidate this project has identified.

---

## 2026-10-05 — Phase 8 groundwork: equipment balance analysed, and item names/descriptions located

**Investigated:** the brief's goal of making "previously weak or unused equipment meaningful" — which first requires knowing which equipment *is* weak or unused.

### `Items.GDA` is the master item table (and it solves the description problem)

288 rows joining everything together. Recovered columns include `id`, **`name` (TLK strref)**, **`description` (TLK strref)**, `type`, `subtype`, **`baseitem1`** (the `.itm` stat file), plus inventory icon and graphic-prefix columns.

Two consequences:

1. **Internal names are not display names.** The `.itm` file's `SpellData.Data` is a developer name; the player-facing name is a TLK string. `RuggedSlippers` is *Tough Slippers*, `KevlarSlippers` is *Alloy Slippers*, `SturdyHydraulics` is *Dura-Hydraulics*, `IRONWILL` is *Iron Tonic*, `PsyDrops` is *Psychic Water*. Any mod presenting item names must read `Items.GDA`, not the `.itm`.
2. **The description-staleness constraint is solvable.** Earlier it was noted that descriptions are hand-written strings that don't track stat edits. `Items.GDA.description` gives the exact strref per item, and the project already has a working TLK writer — so a rebalance *can* rewrite descriptions to match. The constraint becomes a task, not a blocker.

The graphic-prefix column also encodes the equipment **slot**: `ITM_FOT…` footwear, `ITM_GLV…` gloves, `ITM_ACE…`/`ITM_ACC…` accessory.

### Balance finding: the footwear slot is 95% redundant

Comparing every stat-bearing equipment item against others in the same slot, where "strictly dominated" means another item is ≥ on all six stats (SPD/ATK/DEF/POW/GRT/LCK) and > on at least one:

| Slot | Stat-bearing items | Strictly dominated |
|---|---|---|
| **FOT** (footwear) | 21 | **20 (95%)** |
| GLV (gloves) | 20 | 12 (60%) |
| ACE (accessory) | 6 | 1 (17%) |
| other | 4 | 0 |
| **Total** | **51** | **33 (65%)** |

Footwear is almost a pure linear upgrade chain — there is essentially no meaningful choice in the slot, only a "best so far". Gloves retain some genuine trade-offs (e.g. Cursed Gloves' +6 POW against −2 ATK/−2 DEF). **This is the concrete target for the Phase 8 overhaul**, and it is a data-only fix with tooling that already exists.

### 20 equipment items carry no plain stat bonus — and 7 appear to do nothing at all

Of those 20, several are legitimately special rather than weak:
- the six **elemental Rings** (Fire/Water/Lightning/Ice/Wind/Earth) each grant `ELEMENT=1`, i.e. elemental affinity (stat IDs 107–112);
- **Economizer** grants `COMBODISCOUNT+1`;
- **Immunity Idol** carries `RemoveStatus=1022` (the same nine-status cure mask as Spell_Antidote_All).

But **Scanner, Refresher, Replenisher, Nrrgal Module, Angel Amulet and Spooky Charm have no stat rows and no effect rows whatsoever.** Their item tables are empty beyond the three metadata rows.

**Important caveat — this does not prove they are broken.** Their effects may be implemented in ARM9 keyed by item ID (a "Scanner" revealing enemy stats is exactly the sort of thing that would be coded, not table-driven). What is established is only that *nothing in the item data gives them an effect*. Distinguishing "coded elsewhere" from "unfinished" requires either a debugger session or an in-game test, and is worth doing before a rebalance touches them.

**Evidence:** `research/phase0/equipment_analysis.tsv` (every dominated item, what dominates it, and its description text).

---

## 2026-10-05 — Item descriptions resolve four open questions

**Context:** a stat-only "strictly dominated" comparison is the wrong lens for accessories and misc items, whose value is qualitative (elemental attacks, regeneration, map reveal). Reading every item's **description strref** via `Items.GDA` settled several things the data alone could not.

### 1. Elemental attack affinity confirmed (IDs 107–112)

Previously logged as "unconfirmed inference". The descriptions state it outright — Fire Ring: *"Gives Fire damage to basic attacks"*. Mapping: **107 Fire, 108 Water, 109 Earth, 110 Wind, 111 Lightning, 112 Ice** — the same element order as the resistance block at 75–80. Chao 10–15 grant attack affinity, Chao 16–20 grant resistance.

### 2. POW is confirmed as the damage stat

Kron Hammer (`POW+5`): *"Very greatly increases damage."* Chao Print Dress (`POW+2`): *"Moderately increases damage."* Zoah Shield (`GRT+4`): *"Greatly increases armor."* This independently confirms POW = damage and GRT = armor from the game's own text, and confirms ATK is **not** damage.

Descriptions use a consistent qualitative scale ("Moderately" / "Greatly" / "Very greatly"), which a rebalance should respect when rewriting them.

### 3. The six "empty" items are code-driven, not broken

The previous entry flagged Scanner, Refresher, Replenisher, Nrrgal Module, Angel Amulet and Spooky Charm as having no stat or effect rows, with the caveat that their effects might be coded in ARM9. **Their descriptions confirm the caveat was right** — each has a specific intended effect that is simply not expressible in the item table:

| Item | Description says |
|---|---|
| Scanner | "fully displays map in current area" |
| Refresher | "recovers 1 POW Point at the end of each round of combat" |
| Replenisher | "Regenerates 5% of maximum HP" |
| Nrrgal Module | helps "when trying to escape or catch someone" |
| Angel Amulet | "inexhaustible power to put the fallen back on their feet" (auto-revive) |
| Spooky Charm | "Foes flee more often" |

These are per-round regeneration, map reveal, flee-rate and auto-revive effects — all engine behaviours keyed by item ID. **They are not unfinished, and a rebalance must not treat them as empty.**

### 4. New stat ID: 122 = COMBODISCOUNT

Economizer (`COMBODISCOUNT+1`): *"Lowers PP cost of all POW Moves."*

### Also noted

- The endgame accessory set is named after the alien races: **Kron Hammer** (POW+5), **Zoah Shield** (GRT+4), **Nocturne Blade** (ATK+4), **Voxai Teleporter** (DEF+4).
- "POW Candy/Gum/Drink" carry rows labelled `HealHP` but with `SData1=28` (FP/PP) — they restore PP, not HP. Another instance of **row labels being unreliable**; only `SData1` is authoritative.

**Revised Phase 8 conclusion:** the domination analysis stands for **footwear (20 of 21 dominated)** and partly for gloves, which are pure stat sticks. It should **not** be applied to accessories and misc items, which carry qualitative effects the six-stat comparison cannot see.

---

## 2026-10-05 — Movement-ability system solved: slots in `creatures.GDA`, levels in `Adv_<char>.GDA`

**Investigated:** where a character's current movement-ability level is stored — the blocker for "give Shadow Dash III" and a prerequisite for Phase 5 character work.

**Found — a complete, two-part model:**

1. **`creatures.GDA` assigns up to three movement-ability slots per character**, in columns `#1588449107` (slot 1), `#2147880983` (slot 2) and `#1885680587` (slot 3). Each holds an id from `movement.GDA`, or -1 for none.
2. **`Adv_<Character>.GDA` columns 12, 13 and 14 hold the *level* of slots 1, 2 and 3** at each character level — previously unidentified columns.

| Character | Slot 1 | Slot 2 | Slot 3 | col12 max |
|---|---|---|---|---|
| Sonic | Dash | — | — | 3 |
| **Shadow** | **Dash** | **Teleport** | — | **2** |
| Tails | Fly | — | — | 3 |
| Amy | Smash | Dash | — | 3 |
| Knuckles | Climb | Smash | Fly | 1 |
| Rouge | Fly | Stealth | — | 2 |
| Cream | Fly | — | — | 3 |
| Big | Invulnerable | — | — | 3 |
| Omega | Smash | Invulnerable | — | 2 |
| Shade | Stealth | Climb | Teleport | 1 |
| Eggman | — | — | — | 0 |

**Confidence: high — the model is confirmed by four independent cross-checks**, two of them against the user's own game:

- Shadow's slot 1 is Dash and his col12 caps at **2** → he has **Dash II** in game ✓
- Tails' slot 1 is Fly and his col12 reaches **3** → his profile reads **"Fly LV 3"** ✓ (screenshot)
- Knuckles' slot 1 is **Climb**, which `movement.GDA` gives `maxlevel 1` — and his col12 caps at exactly **1** ✓
- Eggman has **no** slot 1, and his col12 is **all zeros** for all 30 levels ✓

Shade's three slots (Stealth/Climb/Teleport, all `maxlevel 1`) likewise match his col12/13/14 all capping at 1.

**Notable:** Shadow already has **Teleport** in slot 2 — the brief's aspirational "Shadow Chaos Control / teleport" mechanic exists in vanilla.

### Experiment built: Shadow Dash III

[tools/build/build_dash3.py](tools/build/build_dash3.py) rewrites Shadow's column 12 from `111222222…` to Sonic's curve `111222233333…`, which should grant **Dash III from character level 8**. `movement.GDA` already declares Dash `maxlevel 3`, so this asks nothing new of the engine — only that Shadow qualify sooner.

Built and byte-verified (`build/sonic_chronicles_dash3.nds`, CRC32 `088FC3D4`, **151-byte patch**, 0 files moved). **In-game result not yet recorded.** If it works, the model is confirmed and the same single-column edit generalises to any character/ability pair — and raising an ability's `maxlevel` in `movement.GDA` extends the ceiling itself.

---

## 2026-10-05 — Omni Ring built: can one item carry all six elements?

**Built:** [tools/build/build_omniring.py](tools/build/build_omniring.py) — harvests the effect rows from all six elemental Rings (items 68-73) and writes them into a single item, to test whether the engine honours more than one `ELEMENT` row.

Each Ring carries exactly three rows: two `VFX` and one `ELEMENT` whose `SData1` is the element's attack-affinity id. The Omni Ring combines all of them — **6 ELEMENT rows (107-112) and 12 VFX rows**, 22 rows total — onto item 74 (Kron Hammer, internal name `PowerRing`), whose existing `POW+5` is **kept** so the item is purely additive. Renamed to "Omni Ring" with a rewritten description via the `Items.GDA` name/description strrefs.

Target chosen because Kron Hammer is already equipped in the test save, so the result is observable without hunting for the item.

Built and byte-verified: `build/sonic_chronicles_omniring.nds`, CRC32 `5F3C1804`, 1,128-byte patch, item grew 299 -> 741 bytes (append path), all `.itm`/`.spl` tables still parse.

### RESULT: it fully works — the engine honours all six ELEMENT rows

**Confidence: high — observed in game.** Attacking with the Omni Ring equipped produced elemental effects, and only **Water and Earth** displayed against the target tested. Those were the two elements that target was weak to.

**Two findings follow:**

1. **An item may carry any number of `ELEMENT` rows and the engine evaluates them all.** There is no "first element wins" restriction. Composite elemental items are fully viable, which settles the question this build was made to answer.
2. **The engine resolves elements against the target's resistances and surfaces only the effective ones.** The player sees the elements that actually matter rather than all six firing — so the extra rows cost nothing visually.

**Design consequence:** an all-element item is effectively *"always strikes the target's weakness"*, which is extremely strong — it removes elemental counter-play entirely. A shipped version of this should carry a real cost (a large stat penalty, or dropping the `POW+` the test build kept) rather than being the strict upgrade used here for a clean experiment.

This is also the strongest confirmation yet of the project brief's premise that interesting behaviour can be built by **recombining effects the game already contains** — the Omni Ring introduces no new mechanic, only a combination the designers never shipped.

### Tooling fix found by this build

`twoda_write.add_row` verified its work with `table.get(label)`, which returns the **first** row carrying that label. That is fine for unique labels but wrong the moment a label repeats — adding a second `VFX` row "failed" verification while actually being written correctly. It now verifies `rows[-1]`, the row it actually appended. Worth noting because the same first-match assumption would silently mislead anywhere else it appears.

---

## 2026-10-05 — Chao mapped; a vanilla gap found: **Ice resistance has no source in the game**

**Investigated:** the elemental Chao, ahead of a Phase 9 change.

**Structure (confidence: high):** Chao are ordinary items — the 125 **type-3** entries in `Items.GDA`, each backed by its own `.itm`. The elemental ones come in three tiers:

| Chao | Elements | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|---|
| 10–15 (**attack**) | Fire, Water, Lightning, Ice, Wind, Earth — **six** | element only | element + `POW+1` | element + `POW+2` |
| 16–20 (**resistance**) | Fire, Water, Lightning, Wind, Earth — **five** | resist + `GRT+1` | resist + `GRT+2` | resist + `GRT+3` |

**The asymmetry is the finding: there is no Ice resistance Chao.** Combined with the earlier observation that no *item* grants Ice resistance either (item `ELEMENT` rows only use 75–79), **stat 80 (Ice resistance) is a fully defined stat with no source anywhere in the vanilla game.** Ice attack exists via Chao 13; Ice defence is unobtainable.

This looks like an oversight rather than a design choice — the five resistance Chao are a complete set of their own, so the sixth was simply never authored.

### Change built: every elemental Chao now grants its own resistance

[tools/build/build_elemental_chao.py](tools/build/build_elemental_chao.py) adds the matching resistance row (`Data=50`, the strength the vanilla resistance Chao use) to all 18 elemental attack Chao, keeping their existing element and tier `POW+` untouched. Each becomes a coherent package — the Fire Chao both deals and resists Fire — and **Chao 13 makes Ice resistance obtainable for the first time**.

Descriptions rewritten via the `Items.GDA` description strrefs so the items still describe themselves correctly.

Verified from the rebuilt ROM: all 18 carry exactly the resistance matching their attack element; **items granting Ice resistance went 0 → 3**; all `.itm`/`.spl` tables still parse. `build/sonic_chronicles_elemchao.nds`, CRC32 `E6F64221`, 9,424-byte patch. **In-game result not yet recorded.**

**Scope limit worth recording:** this *redefines* existing Chao and cannot create new ones. A new Chao would need a new archive resource (unsupported — it changes the HERF resource-table length) and, more fundamentally, the garden/egg system would have to know how to hand it out. The brief's larger Phase 9 goal — replacing wireless/trading progression with local Chao XP and levels — remains blocked on save-format knowledge, which the save checksum currently gates.

---

## 2026-10-05 — Custom Chao: five new Chao from redundant slots

**Context:** the previous build gave every elemental attack Chao (10-15) its own matching resistance. That made the five resistance-only Chao (16-20) redundant — and therefore reusable. They matter because they are **already obtainable in game**, which is the scarce resource: new Chao cannot be created (that needs a new archive resource, unsupported, and the garden/egg system would have to know how to hand it out).

**Built** ([tools/build/build_custom_chao.py](tools/build/build_custom_chao.py)): all 15 entries (5 types x 3 tiers) redefined, using only mechanics already confirmed in this project.

| Was | Now | Effect (scales with tier) |
|---|---|---|
| Chao 16 | **Prism Chao** | all six attack elements + `POW+` |
| Chao 17 | **Aegis Chao** | all six resistances, 25/50/75 |
| Chao 18 | **Berserk Chao** | `POW+4/8/12`, paying `DEF-` and `GRT-` |
| Chao 19 | **Tempo Chao** | `SPD+`, and **`NUMACTIONS+1`** — an extra action every turn |
| Chao 20 | **Thrift Chao** | `COMBODISCOUNT+` (cheaper POW moves) and `FP+` (more PP) |

Existing effect rows are zeroed rather than deleted (the reader keys on `SData1`, so a zeroed row is inert); new rows appended; names and descriptions rewritten via the `Items.GDA` strrefs.

Verified from the rebuilt ROM: all 15 read back with exactly the intended effect sets, all `.itm`/`.spl` tables still parse. `build/sonic_chronicles_customchao.nds`, CRC32 `7484E93F`, 8,163-byte patch. **In-game result not yet recorded.**

**Balance note:** `NUMACTIONS+` appears on only three abilities in the entire vanilla game and is probably the strongest effect available — an extra action per turn roughly doubles a character's output. Tempo Chao is deliberately the standout and should be treated as a design decision to revisit, not a balanced default.

This is the clearest demonstration yet of the brief's "recombine existing systems" philosophy: five genuinely new Chao, no new mechanics, no new resources — purely a reallocation of slots the game had spent on redundant effects.

---

## 2026-10-05 — **SAVE CHECKSUM CRACKED** by disassembly; save editing unblocked

**Four brute-force search attempts had failed.** The breakthrough came from static analysis instead: capstone was installed and [tools/recon/disasm.py](tools/recon/disasm.py) written to disassemble ARM9 THUMB code at a given RAM address, plus find BL callers of a function.

**The chain:**
1. The CRC32 polynomial `0xEDB88320` appears exactly once in ARM9, at `0x020B7C34` — in a **literal pool**, not inline code.
2. That pool belongs to the function ending at `0x020B7C2E`, which disassembles as a textbook **CRC32 table builder** (256 entries, table written to RAM `0x021AD594`).
3. The next function, `0x020B7C38`, loads that table and is **`crc32(buf, len)`**. Crucially the disassembly shows `crc = 0` on entry and the result returned unmodified: **init = 0, no final XOR** — not the usual convention.
4. Scanning every THUMB `BL` in the binary found **6 callers**. The one at `0x02017558` does `r0 = buf + 7`, `r1 = <literal length>`, `bl crc32`, then stores the four result bytes to `buf + 3`.
5. The literal at `0x02017580` gives the length: **`0x3BF9`**.

**Result, verified against two independent valid saves:**

| | Stored at | Covers | Length |
|---|---|---|---|
| outer | `0x203` | `0x207`… | `0x3BF9` (15353) |
| inner | `0x234` | `0x238`… | `0x21` (33) |

The inner region is nested inside the outer, so the inner must be resealed first.

**Why the searches missed it:** the outer length `0x3BF9` is **odd**, while the scans stepped range-ends in 32/64-byte increments — that end was never tried. The algorithm hypothesis had been right the whole time; only the granularity was wrong. A good reminder that a bounded search can be confidently wrong in a way disassembly simply is not.

**Tooling:** [tools/build/save_edit.py](tools/build/save_edit.py) verifies and reseals both checksums, applies field edits, and refuses to write anything that does not validate.

**Immediate consequence — CONFIRMED IN GAME.** The level-30 save had movement slot 1 set from 2 to 3 and both checksums resealed. Shadow's profile now reads **"Dash III — The fastest run."** (user screenshot). Three things are proven at once:

1. **Save offset `0x026E1` really is movement-ability slot 1's level** — the field identification was right.
2. **The checksum crack is correct.** The game accepted a modified save, so both the algorithm (`init 0`, no final XOR) and both ranges are exactly right.
3. **Save editing works end to end**, which unblocks Phase 13 (New Game+) and Chao progression — both were gated on save access.

It also closes out the Dash question properly: movement-ability level is **pure save state**. The `Adv_<char>.GDA` column-12 theory was wrong — no table edit was ever going to change it, which is why both earlier builds failed. The only route is the save.

---

## 2026-10-05 — Chao system fully mapped via `Chaos.GDA`

**Trigger:** the custom-Chao build appeared to do nothing in game. **Diagnosis: it worked, but edited Chao the player does not own** — it redefined Chao 16–20 (the elemental shields) while the player's collection is Baki, Barbo, Belgog, Bepke, Blayze and others.

**Confirmed by test:** redefining Chao 27 (**Blayze's** type, items 117/157/197) to `SPD+20, NUMACTIONS+1` changed Blayze's in-game description to the new text (user screenshot). Chao redefinition works; it is simply invisible unless the species is owned.

### `Chaos.GDA` is the missing link

45 species, each with name and description strrefs, rarity, palette, and **three item ids — one per Chao level**:

```
species row N  ->  items (91 + N, 131 + N, 171 + N)  =  levels 1, 2, 3
```

Verified: **Blayze is row 26 → items 117/157/197**, exactly the entries the test edited. Rarity splits 20 Common / 15 Rare / 10 Unique. `Baki` (Unique) is notable for using **the same item id (213) at all three levels**, so it does not scale.

Full table: `research/phase0/chao_species.tsv`.

### Two findings that change how Chao should be modded

1. **Go through `Chaos.GDA` to reach a specific Chao.** The `Items.GDA` "Chao N" labels are not species — mapping species → item ids is the only reliable route, and it is why the first custom-Chao build looked broken.
2. **A Chao's displayed name lives in `Chaos.GDA`, not `Items.GDA`.** The test overwrote the *item's* name strref and the on-screen name stayed "Blayze", while the *description* (which does come from the item) changed correctly. So: effects and description from the item, name from the species table.

Also read off the inventory screen: the bracketed number beside a Chao is its **level (1–3)**, matching the three item tiers, and rarity is surfaced to the player.

**Consequence for the custom-Chao build — corrected.** The player owns every Chao, so the build's effects *were* applying; it looked broken only because the **rename went to the wrong table**. The five redefined species are **Korus, Perty, Knickt, Seeri and Jirna** (the elemental shields, items 106-110/146-150/186-190), and they kept those names on screen while their effects had already changed.

Rebuilt renaming through `Chaos.GDA`'s species name strrefs (23246-23250) instead, once per species rather than per tier, and with no tier suffix since the game displays Chao level separately. Verified from the rebuilt ROM: the five now read **Prism / Aegis / Fortune / Tempo / Thrift Chao** with matching descriptions.

The general rule, now confirmed twice: **a Chao's effects and description come from its `.itm` + `Items.GDA` entry, but its name comes from `Chaos.GDA`.**

---

## 2026-10-05 — Stat rows stack on code-driven Chao (confirmed in game)

**Question:** the ten Unique Chao have no effect rows — their behaviour is ARM9 code keyed by item id. Could ordinary stat rows be *added* alongside, or would that displace the coded effect?

**Test:** appended visible-stat rows to two hatchable Uniques, touching nothing that already existed (the build asserts both items start with zero effect rows):

    Spartoi  items 130/170/210   ATK +4/+8/+12, LCK +4/+8/+12
    Ferox    item  128 (all levels)  SPD +10, ATK +5

**Result (confidence: high — observed in game): they stack.** With a Seggo equipped Eggman read `Atk 32 / Lck 40`; with the Spartoi equipped, `Atk 44 / Lck 52` — exactly the +12/+12 of the tier-3 entry.

**Consequence:** a Unique Chao's special behaviour cannot be retuned or copied (there is nothing in the data to edit), but stats can be layered on top of it freely. The Unique roster can therefore be kept competitive with a buffed Common/Rare lineup **without any ARM9 work** — the one lever available for those Chao, and it works.

**Fully confirmed:** Spartoi's instant-KO **still fires** in combat with the added stat rows in place (tested in game). So appending effect rows does **not** displace the ARM9-coded behaviour — the two run side by side, exactly as the item-id vs effect-row separation predicted.

### Two corrections from the same screenshots

1. **The bracketed number in the Chao list is the quantity owned, not the level.** `Seggo (5)` became `Seggo (6)` when a Seggo was unequipped, while the detail panel showed `Level: 3` separately. Previously logged as level — wrong.
2. **Custom Chao names should be bare.** Every vanilla Chao is a single word (Seggo, Baki, Barbo), so "Aegis Chao" read oddly in the list. Rebuilt as **Prism / Aegis / Fortune / Tempo / Thrift**.

---

## 2026-10-05 — Housekeeping: one profile-driven builder (roadmap Phase 17), and Shadow Mode reconnaissance

### Phase 17: mod profiles

Eight one-off build drivers had accumulated, each re-implementing the same five stages with only the edits differing. [tools/build/modbuild.py](tools/build/modbuild.py) now runs the pipeline once and takes the edits as **data** from a JSON profile in `profiles/`.

Per the project's rule against inventing configuration before behaviour is confirmed, the profile exposes **only operations verified in game**: `tlk_string`, `twoda_cell`, `twoda_add_row`, `gda_cell`, `gda_add_row`, `item_name`, `item_desc`, `chao_name`.

`chao_name` exists as a separate op precisely because of the earlier mistake: a Chao's displayed name comes from `Chaos.GDA`, not its item entry, so `item_name` silently does nothing for Chao.

Two profiles ported and built successfully (`profiles/omni_ring.json`, `profiles/unique_chao_stats.json`). [tools/README.md](tools/README.md) documents the layout and the safety invariants.

The algorithmic builds (footwear roles, level-cap extrapolation, elemental-Chao derivation) remain standalone because they *generate* edits rather than list them; the clean end state is for those to emit a profile instead of driving a build.

### Shadow Mode (Phase 5) reconnaissance

**A character is almost entirely data.** Comparing `creatures.GDA` rows 0 (Sonic) and 4 (Shadow): 30 of 61 columns already match, and everything that distinguishes them is data — `namestrref`, base stats, both portrait sets (`PRT_TP_SDW`/`PRT_SP_SDW`/`PRTL_SDW`/`CharPro_SDW` and their palettes), the progression table reference (`Adv_Sonic` vs `Adv_Shadow`), the four combo-move ids (Sonic 1/2/3/4/5, Shadow 13/14/15/16/17), movement-ability slots, `class` and `playerid`.

**Recruitment is plot-flag driven.** The `.plo` files carry flags named `TAILS_GET`, `AMY_GET`, `TAILS_MET`, `A1_STRONGHOLD_SHADOW` and so on — 142 flags mention party members. This is also the groundwork Phase 14 (randomised recruitment) needs.

**No party strings in ARM9.** Searching for `StartingParty`, `InitialParty`, `AddPartyMember`, even bare `party` returns nothing, so the initial party is not assembled via a named lookup.

**Open question — where new-game party state is initialised.** Three candidate routes, in increasing cost:
1. A plot flag set at game start grants Sonic; adding/retargeting one could grant Shadow.
2. Swap the differing `creatures.GDA` columns between rows 0 and 4, so the character the game calls "Sonic" *is* Shadow throughout. This is the purest "redirect existing systems" reading of the brief — but it needs **string-column editing in GDA**, which `gda_write` does not yet support (strings are out-of-line and need appending plus repointing, unlike the integer cells it handles today).
3. ARM9, if the initial party turns out to be hardcoded.

**Route 2 is the most promising and the blocker is clear:** a GDA string-cell writer. That is the same append-and-repoint pattern already proven in `tlk_write.py` and `herf_write.py`, so it is a known quantity rather than new research.

---

## 2026-10-05 — GDA string-cell writer (unblocks Shadow Mode route 2)

**Built:** `set_string_cell` in [tools/build/gda_write.py](tools/build/gda_write.py), the missing piece for editing `creatures.GDA`'s portrait/model/progression references.

Layout confirmed first rather than assumed: GDA string cells are REFERENCE-flagged `asciistring`, pointing at a `uint32` count (including trailing NUL) plus CP-1252 text, stored in a region **after** the row array — in `creatures.GDA`, rows occupy `0x550`–`0x7950` and strings run from there to EOF.

**A real bug the test caught: GDA strings are deduplicated.** Writing a 32-character portrait name over row 4's slot also changed **rows 75, 77 and 116**, which share `PRT_SP_SDW.ncgr` with Shadow. The writer now counts sharers and **never edits a shared string in place** — it appends and repoints only the target row, exactly as the TLK writer does.

Worth noting *why* it was caught: the test asserted **which rows changed**, not merely that the target row held the new value. A test that only checked the target would have passed while silently corrupting three other creatures. That is the third time in this project a check-what-else-moved assertion has paid for itself.

Verified across all three paths — in-place (fits, unshared), append-on-overflow, and append-on-shared — with every other row and every other string column on the edited row confirmed untouched, and all 128 rows still decoding.

**Shadow Mode route 2 is now unblocked:** every differing column between creature 0 (Sonic) and creature 4 (Shadow) is either an integer (`set_int_cell`) or a string (`set_string_cell`), so the two can be swapped entirely in data.

---

## 2026-10-06 — Shadow appearance swap: model works, portraits do not (and why)

**Built** `profiles/shadow_appearance.json` via the new profile builder: creature 0 (Sonic) takes Shadow's name, 3D appearance and portrait references while keeping Sonic's stats, POW moves, progression and abilities.

**Result in game (user screenshot):**
- **The 3D model swapped correctly** — Sonic's overworld model is Shadow. `creatures.GDA` column 14 is an **appearance id** into `appearances.GDA` (Sonic row 0, Shadow row 4), so a single integer swaps the model.
- **The dialogue portrait rendered as corruption** — a garbled rainbow block, the classic signature of an NCGR drawn with a mismatched or missing palette.
- The small speaker icon in the dialogue bubble **stayed Sonic**, so it comes from somewhere other than `creatures.GDA` — source not yet identified.

### Why the portraits broke — portrait sets are not interchangeable

Resource names are built by **concatenating a prefix with an expression suffix**, and the characters have different expression vocabularies:

| Set | Count | Expressions |
|---|---|---|
| `PRTL_SONIC` | **10** | amu con det dis gen imp inq mad sle smg |
| `PRTL_SHD` | 9 | def det gen hel int mad sht stg tht |
| `PRTL_SDW` | **4** | def gen mad smg |

Sonic's dialogue asks for *amused*, *inquisitive*, *sleepy* and others that **Shadow has no art for**. The game requests `PRTL_SDWamu_0`, finds nothing, and draws garbage. Only three expressions overlap, and interestingly there are **two** Shadow sets — `PRTL_SDW` (used by the creature table) and the richer `PRTL_SHD` — but neither covers Sonic's range.

**This is a hard constraint on Shadow Mode, and it is an art problem rather than a data one.** Options: leave dialogue portraits as Sonic's (mismatched but clean), accept corruption in some scenes, or author the missing expressions — which is outside data modding. Choosing `PRTL_SHD` instead does not help: it is missing seven of Sonic's ten either way.

**Revision 2** therefore keeps the model, name, top-screen portraits and character-profile art, and deliberately leaves the dialogue portrait prefix as Sonic's. Built and verified; in-game result not yet recorded.

### What this says about route 2 overall

Swapping a character in data works for everything with a **one-to-one** reference — model, name, stats, progression table, POW moves. It breaks wherever the engine **derives** resource names from a prefix, because the derived names must all exist. Worth checking for the same pattern before trusting any other prefix-style column.

---

## 2026-10-07 — CONFIRMED: the Chapter 4 recruitment works, with no plot-flag edit

**Investigated:** The one claim in the whole Shadow Mode build that was reasoned to rather
than tested — what happens at the Chapter 4 story point where Shadow is normally recruited,
after creature 0 and creature 4 have been swapped.

**The prediction (made before any of it was built):** no plot-flag editing would be needed,
because recruitment grants *creature 4*. With creature 4 holding Sonic's data, the story
point should hand the player Sonic, and the swap should resolve by symmetry.

**CONFIRMED IN GAME (2026-10-07):** reaching Chapter 4 on a run started after the swap:

- the overworld figure is Sonic
- the encounter fights as Sonic
- **the recruitment grants Sonic, who joins the party alongside Shadow**
- story dialogue reads correctly ("Don't get in my way, Shadow!")

`SHADOW_GET` was never touched. The earlier finding that flag->effect wiring is not editable
from `.plo` or `plotflags.GDA` turned out not to matter: the recruitment addresses a creature
slot, and swapping what lives in that slot is sufficient. This also confirms the party system
tolerates a swapped roster — the second member is granted, displayed and selectable.

**Remaining defect found by the same test:** the encounter used **Chaos Rift**. The story
creatures 75/77/116 have *dedicated* combo rows (122, 126, 127, 144, 145) owned by themselves
and carrying Shadow's kit; the 0<->4 owner swap never touched them because they reference
neither 0 nor 4. Their name strings are **shared with the player's own** Chaos Spear/Rift
(strref 20615 used by 4 rows, 20616 by 3), so editing the strings would have renamed the
player's moves — the same pointer-versus-content trap as the text swap undoing the name swap.
Fixed by repointing each boss row's name and description strrefs at Sonic's Axe Kick /
Whirlwind instead, which is a cell edit and touches only those rows.

**Remaining uncertainty:** only the naming follows. The moves keep Shadow's mechanics and
visual effects, so the attack still reads as chaos energy. Giving the encounter genuinely
Sonic-flavoured moves would mean either repointing the creatures' move slots at rows 0-5
(whose owner is creature 4 — untested whether enemy use checks ownership) or re-authoring
the boss rows' spell and VFX fields.

---

## 2026-10-10 — Chest contents are not in any data file

**Investigated:** Where a chest gets its item, after `randomize_drops` and
`randomize_pickups` both failed to change it in play.

**Settled (confidence: high — this is an elimination, each step tested rather than
reasoned):**

A chest is an `itembox` placeable, ARE list 40001 object type 6, **53 of them** across
the 79 areas. Its contents come from **none of the data files**:

| candidate | how it was eliminated |
|---|---|
| the `itembox` object itself | carries no item id; field 40019 is -1 on 52 of 53, 40026 and 40027 constant |
| the ARE kind-4 pickup list | **geometry**: not one of the 47 itemboxes shares a position with any of the 37 pickups. Unrelated objects in unrelated lists — these are the loose items you walk over |
| `RandItems.GDA` | **decisive probe**: every one of the 22 drop tables set to 100% Chaos Driver, new save, first chest still gave a **Health Seed** |
| `.plo` plot files | a flag registry with no actions — 1,041 flags, no opcodes, no item references |
| any other GDA | no table has 53 rows; a per-chest table would |

The `areas.GDA` **column 61** correlation that looked so promising — tracking the section
exactly for every chest-bearing area, a1_s1 to 1, a1_s2 to 2, a1_s5 to 5, a1_s6 to 6 — is
a coincidence. It is a zone index of some kind that happens to climb with progression,
not a tier index into `RandItems`. The probe rules it out regardless of what it means.

**So chest contents live in ARM9**, like the plot logic, the unique Chao effects and the
enemy stat load. That is consistent with the engine having no script files at all.

**Note on method.** This question cost two wrong conclusions before the right one. The
first ("RandItems is not the source") was correct but rested on a playtest that could
have been luck; the second ("column 61 proves it is") was a strong correlation that
reversed the first on no new evidence. What finally settled it was a probe designed so
that *either* outcome was conclusive — every table set to one unmistakable item — rather
than another table correlation. Correlations in this dataset are cheap; 53 chests and 79
areas give plenty of columns that climb with progression.

**Remaining uncertainty:** nothing about *where* in ARM9, and no attempt was made to find
it. The itembox's field 40023 (a per-area object index, e.g. 198-201 and 257 in
`a1_s1_ex`) is the obvious key for a hardcoded table to be indexed by, and is where a
runtime investigation would start.

---

## 2026-10-10 — Spawn points carry script tags, and moving a tagged one empties the battle

**Investigated:** `randomize_placements` left the opening tutorial fight with no enemy in
it — the player stands in an empty arena. Reported twice, the second time after a fix
that turned out to address a different cause.

**Discovered (confidence: high — the failing spawn point was identified directly and the
fix verified across every area):**

`squads.GDA` placements in an ARE (list 40003) carry a **script tag at field 40006**. A
non-zero tag means a plot addresses that spawn point by name; the entry's name string is
the same number. In `a1_s1_ex` alone, **13 of 54** spawn points are tagged.

**Spawn point #0 of the opening area is tagged 5, and holds squad 22 — the Enraged
Armadillo of the combat tutorial.** Randomizing moved it to squad 14 (three Sentry
Drones), and the script that drives that fight no longer found what it expected, so the
battle opened with nothing in it.

Tagged points are now excluded outright (`are_write.squad_placements(include_tagged=False)`).
After the fix: 225 spawn points still randomize, **zero tagged**, and spawn #0 keeps
squad 22.

**A fix that was not the fix.** The first attempt blamed model-less creatures: squad 51
contains creature row 75, a "Shadow the Hedgehog" duel variant on appearance 4, which has
no model, and that squad *had* been moved into an ordinary Green Hill spawn point. That
was a real bug with the same symptom — it is the identical cause as the Marauder crash of
2026-10-08, which had been fixed in `randomize_encounters` and then not applied to
`randomize_placements` — and the model-less check is now a shared `_modelless_creatures()`
helper both features consult. But it was not what the player was hitting, because the
tutorial fight is a *different* spawn point. Two independent bugs, one symptom.

The lesson worth keeping: "empty battle" has at least two causes — a creature with no
model, and a script whose spawn point was reassigned — and fixing one does not test the
other.

**Remaining uncertainty:** whether tags matter outside combat scripting is unknown, and
excluding them is conservative; some tagged points may be safe to move. Nothing was
learned about *which* plot reads a given tag.

---

## 2026-10-10 — Code-driven Chao do scale with level, and Ferox is an outlier for a reason

**Investigated:** three things the Chao work had left loose — why Ferox uses one item for
all three levels, whether the 20 code-driven Chao scale at all, and whether Bepke really
levels backwards. The player supplied the explanation and a reference, **Chao Island's
Sonic Chronicles guide** (<https://chao-island.com/guides/spin-off-games/sonic-chronicles/>),
whose per-level figures are used below as external data.

**1. Ferox is binary, which is why it has no tiers.** Its effect is *"Bonded character
automatically succeeds using their POW moves"* — there is no quantity to scale. A move
cannot succeed more than automatically. The reference agrees, marking it "unaffected by
level". That closes the one genuine outlier among the six Chao that name a single item
for all three levels; the other five are the event Chao, which never had a levelling
path.

**2. The code-driven Chao do scale — the game's own descriptions are written at level 1
and say so.** Three of them have the level-1 *number in the sentence*:

| Chao | in-game description | per level |
|---|---|---|
| Ovus | "automatically revived **once** during a battle" | 1 / 2 / 3 revives |
| Bepke | "**One** enemy will automatically attack the bonded character" | 1 / 2 / 3 enemies |
| Spartoi | "may cause instant KO" | +5% / +7.5% / +10% |

So "code-driven" never meant "flat". The effect scales; it simply is not in `Chaos.GDA`.

**This reframes the open question precisely.** `chao_level` rewrites the item ids in
columns 6-8. Whether that reaches the code-driven Chao depends on something not yet
known: does ARM9 branch on the **item id** it is handed, or on the **stored level**? The
first makes them work for free; the second makes the edit inert for 20 of 45 Chao.

**Ovus is the experiment**, because its effect is a count rather than a rate: equip a
level-1 Ovus, lose its bonded character three times in one battle, and the number of
automatic revives is the answer. One fight, no statistics.

**3. Bepke does not simply level backwards — it trades.** Armour falls (GRT +15 / +10 /
+5) while the taunt it exists for rises (1 / 2 / 3 enemies). Yesterday's guard called
that a downgrade on the strength of the only half it could see. The skip stands, because
less armour for a stronger taunt is a judgement call and silently halving someone's
armour is the worse failure, but the *reason* recorded for it was wrong. The docstring
now says so and gives the two-cell `edits` override for forcing it.

**4. Incidental, from the reference:** Barbo's Max HP tiers of 10/13/15 are **percentages**
(+10% / +12.5% / +15%), which also explains Radu's 20/25/30. The `.ITM` figure is a
percentage wherever it touches a maximum, the same way `HealHP` turned out to be.

**Remaining uncertainty:** the reference lists Pyraz, Seggo, Stiglin and Zimba with
identical level 2 and 3 values and calls that possibly a typo. `Chaos.GDA` says otherwise
— all four read element +1 at tier 1 and element +1 plus POW +2 at tier 3 — so the data
and the guide disagree and the data is the better witness here.

---

## 2026-10-10 — Chao levelling is sealed behind wireless, and two thirds of the system with it

**Investigated:** whether a Chao can be made to level without trading over wireless.

**Discovered (confidence: high — the game states the rule itself):** a solo player cannot
level a Chao **at all**, and the mechanism is not a counter that could be nudged.

> *"Chao are social creatures; you can trade them with **two different friends** to help
> them to grow in power and reach their full potential (Max!)"* — string 5265
>
> *"Neither Chao will level up. You must trade with **someone new** for the Chao to
> increase to Max level."* — string 8951
>
> *"You must trade with a **different friend** to maximize the level of this Chao."* —
> strings 7579 and 18735

Level 2 requires a wireless trade with one person and level 3 a trade with a *different*
person, so the game tracks **who** you have traded with, not how many times. There is no
threshold to lower. In 2026 that seals off two thirds of the Chao system permanently.

**What is reachable instead.** `Chaos.GDA` columns 6, 7 and 8 are the item ids a Chao
grants at levels 1, 2 and 3. Rugle is 99/139/179, carrying Luck +1, +2, +3; Barbo is
Max HP +10/+13/+15. The level selects a column, so pointing the lower columns at the
higher one hands a freshly hatched Chao its Max-level effects without touching levelling
at all.

| | |
|---|---|
| **25 of 45** Chao | escalating stat tiers — gain outright |
| **20 of 45** | code-driven, no stat rows in their `.ITM`; repointed anyway in case ARM9 scales by tier id, which is **unverified** |
| **6** (Ferox, Pooki, Farfinkle, Baki, Stugs, Fimbley) | already name one item for all three levels — skipped, nothing to do |

**How it was tested — CONFIRMED IN GAME 2026-10-10.** `profiles/chao_level_test.json` on
a clean ROM, nothing else on. Equipping a freshly hatched **Level 1 Rugle** took Sonic's
Luck from **50 to 53** — the +3 of its Max tier, where vanilla grants +1. That is a
Max-level Chao effect on a Chao the game will not let a solo player level at all.

Getting there needed one correction to the method. The **Chao Garden and inventory panels
draw a Chao's description and never its numbers** — Rugle reads "Bonded character has
increased luck" with no figure anywhere, unlike the item panel in a shop, which does
print green stat lines. So the check has to be made on the **character sheet**, before
and after equipping. Luck is one of the four stats drawn there.

Two things in the garden look like failures and are not. The panel still reads
**"Level: 1"**, because the level is in the save and this feature does not touch it. And
the garden's **"Maxed: 0"** counter reads that same stored level, so it stays at zero
however many Chao are effectively maxed.

**`Chaos.GDA` columns 3, 4 and 5 identified**, prompted by the garden counting
**"2 / 40"** against the table's 45 rows. The player named the missing five as the event
Chao, and the table agrees exactly:

| column | meaning |
|---|---|
| 3 | rarity, as a strref — **20 Common, 15 Rare, 10 Unique** |
| 4 | obtainable by hatching — 0 for **Cheese** and the five event Chao |
| 5 | **event Chao** — 1 for exactly Pooki, Farfinkle, Baki, Stugs and Fimbley |

45 rows minus the 5 with column 5 set is 40, the garden's own denominator. Cheese is 0 in
column 4 but still counts toward the set, which fits: he is story-given rather than
hatched.

This also resolves an oddity filed earlier. Six Chao name **one item for all three
levels**, which looked like six that simply cannot level — but five of them are the event
Chao, and an event-distributed Chao has no growth tiers because there was never a path to
level it. **Ferox** is the sixth, is Unique and is *not* an event Chao, so it is the only
genuine outlier.

**What this does not do:** the Chao's displayed level stays at 1. The level lives in the
save, and this does not touch it.

**Found while checking a playtest's Chao (2026-10-10):** two corrections to the table
above.

The **five "shield" Chao are not code-driven** — Korus, Perty, Knickt, Seeri and Jirna
each carry an unidentified `stat 79`-family effect at +50 *plus* **GRT +1 / +2 / +3**.
They gain from `chao_level` like any other. But GRT is one of the three stats the item
panel refuses to draw, so the gain is real and invisible: a playtester holding only these
two could not read the difference off the screen.

And **Bepke levels backwards**: GRT **+15 / +10 / +5**. Its Max tier is a third of what
it grants on the day it hatches, so granting tier 3 unconditionally would quietly nerf
it. `chao_level` now refuses any tier whose stat total is lower than the Chao's own
level-1 tier, which costs 2 of the 78 edits and nothing else. Bepke is the only Chao in
the table that does this, which is precisely why it would have shipped unnoticed.

Only **five** Chao show the change on the panel at all — Churdle and Oldarg (Attack),
Koolet and Belgog (Defense), Rugle (Luck). Everything else moves Max HP, Max PP, POW or
GRT, and the panel draws none of those.

**Remaining uncertainty:** whether the 20 code-driven Chao vary their hardcoded effect by
tier id at all. If they do, repointing gets their Max version for free; if not, the edit
is inert for them. Nothing distinguishes the two cases from the data — Spartoi's
instant-KO is in ARM9 either way.

---

## 2026-10-10 — Which item effects the game draws, and which it hides

**Investigated:** the question left open an hour earlier — the item panel evidently draws
*some* effects itself, and it was not known which. Three shop screenshots settled it.

**Discovered (confidence: high, read directly off the screen):**

| stat | drawn? | evidence |
|---|---|---|
| Speed, Defense, Luck | yes | `Speed +1`, `Defense +1`, `Luck -3` |
| HP heal | yes, **with** a percent sign | Revival Ring draws `HP +18%` |
| PP heal | yes, **without** one | Refresher Wave draws `PP +94` |
| **Max HP** | **no** | "Defense +1, Max HP +3" draws only the Defense line |
| **POW** | **no** | "Speed +1, POW +5" draws only the Speed line |
| **GRT** | **no** | "Speed -2, GRT +4, Luck -3" draws only Speed and Luck |

Attack was not observed either way.

So **three of the ten stats an item can carry are invisible** in a normal playthrough.
This settles the generated descriptions' purpose in the opposite direction from what the
open question implied: they are not redundant, and they should keep listing everything
rather than only the hidden stats, because the hidden ones have nowhere else to appear.

**Fixed:** the generated text claimed "Restores 94% PP." where the panel prints `PP +94`.
An earlier fix had made *both* heals percentages on the strength of the one HP
observation. They are not written the same way, and the description now matches whatever
the panel prints for each.

**Remaining uncertainty:** whether the stored number means the same thing for both heals
is still unresolved. Vanilla HP heals run 10/50/100/250 and PP heals 5/10/50/999. A POW
Candy restoring 5% of a seven-point PP pool would do nothing, so the PP figure is almost
certainly flat — but that is an argument, not a measurement, and the HP side is not
explained by it either (a 250% heal is a strange thing to author).

**Worth noting about the method.** All three of these came from a player reading a shop
menu, not from the data. The data says what an item does; only the game says what it
*tells you* it does, and the gap between those two is where every description bug in this
project has lived.

---

## 2026-10-10 — All eight randomizers confirmed, and `stores.GDA` is not a shop

**Investigated:** the last two unverified randomizers, reached with the god-mode save.

**1. `randomize_shops` — confirmed, and it exposed a bug.** Central City's shop stocked
Refresher Wave, Cure All Spray, Revival Ring, Titanium Claws and Cursed Claws where
vanilla sells Health Seeds and POW Candy, at the vanilla prices for those slots.

But two rows were **blank**, priced 70 and 35. The cause: `randomize_shops` globbed
`store*.gda`, and **`stores.GDA` is not a shop**. It is the five-row registry *of* the
shops — column 1 is a TLK strref for each shop's name (17425-17429) and column 2, where
a stock table has a buy price, holds a background image filename (`store_1_bg.tga`).

So the shuffle dealt five shop-name strrefs into the real shops as merchandise, and dealt
real items back into the registry, where they were presumably about to become shop names
and backdrops. `_store_tables` now admits a table only if its price column is an integer
in every row, which is the property that actually distinguishes stock from registry.

**2. `randomize_drops` — confirmed, cleanly.** An Immunity Booster dropped in chapter 1.
It cannot: vanilla lists it in **table 19 alone**, a late one, and seed 1 moves it into
**table 3**, an early generic tier. The player flagged it as "I don't think you can get
this in chapter 1", which is exactly right and is the whole evidence.

**That is all eight randomizers confirmed in game**, each against a prediction made from
the data before the ROM was built: chests, placements, encounters (both modes), rewards,
Chao, items, shops and drops.

**An incidental confirmation worth recording.** The Cursed Claws screenshot shows the
game's own effect lines reading *Speed -2, Luck -3* — while the generated description
reads *Speed -2, **GRT +4**, Luck -3*. GRT appears only in the text this project writes.
That is the clearest demonstration yet of why `randomize_items` rewrites descriptions at
all: two of the game's stats are invisible, and a randomized item that changes one of
them is otherwise unknowable.

**Remaining uncertainty:** which effects the item panel draws itself is still not
surveyed. It evidently covers healing percentages and the visible stats, and evidently
does not cover GRT. POW is untested.

---

## 2026-10-10 — Character stats live in the save, not the progression table

**Investigated:** why `profiles/playtest_god.json` — every playable character given
ATK/POW +250, GRT/DEF +200, HP +500 across their whole `Adv_*.GDA` table — made no
difference at all when loaded into a save in progress.

**Discovered (confidence: high, two independent confirmations):** the progression table
is what a **level-up reads**, not where a character's current stats are kept. Those are
in the save file. A `stat_curve` edit therefore has no retroactive effect whatsoever: the
party keeps the numbers it already has until it gains a level.

This was already half-known and not joined up. `save_edit.py`'s field offsets were
originally "established by diffing a save before/after levelling" — which is a statement
that levelling *writes stats into the save*, and therefore that the save is what the game
reads back. `stat_curve` has carried a `build` badge since it was written, and this is
the first time it was actually run against a live save.

**The save layout, recovered properly this time.** Each character has a stat block of
seven consecutive `uint32`s in `Adv_*.GDA` column order:

    +0x000 speed  +0x004 attack  +0x008 defense  +0x00C hp
    +0x010 power  +0x014 grit    +0x018 luck     +0x024 pp

In the save in hand, Sonic was at `0x01582` reading `(7, 8, 14, 33, 8, 2, 3)` and Amy at
`0x01796` reading `(4, 7, 12, 27, 13, 3, 2)`. What makes that a match rather than a
coincidence is that the run contains **power 8 and grit 2** — two stats the game never
draws anywhere, so nothing but the real structure could put them in that order.

**The old fixed offsets do not transfer.** Every one of the documented
`0x0263D`-and-friends offsets read **zero** in this save. They were correct for the save
they came from; in a late-game save `0x0263D` holds the ninth character. `find_party` now
locates the blocks by shape instead, which turns up 2 in the early save and **22** in the
late-game one — eleven characters, plus a second complete copy of the party that is
presumably the other save slot.

Two details worth keeping. Blocks are *mostly* `0x214` apart but not reliably — the first
gap in the late save is `0x220` — so a stride walk is the wrong tool. And requiring every
value to be at least 2 is what rejects the only two false positives, both of which are
sliding-window artifacts containing a 1.

**How it was tested:** `--godmode` applied to the playtest save, both checksums resealed
and reverified, and the finder re-run against the untouched backup and against an
unrelated level-19 save. **Awaiting the in-game check.**

**Remaining uncertainty:** current HP is not in the block — no field anywhere in Sonic's
`0x214` bytes held the 19 of his 19/33. Either it is stored elsewhere or it is restored
on load. Nothing here depends on the answer, but a save editor that wanted to heal would
need it.

---

## 2026-10-10 — A squad's overworld model follows *any* member, and healing is a percentage

**Investigated:** two things a full_randomizer playtest turned up — an enemy that walked
the overworld as a caterpillar and fought as a Gentleman, and a Revival Ring whose
regenerated description disagreed with the number the game drew beside it.

**1. The overworld model rule was far too strict (confidence: high).**

A squad carries its own appearance id for the thing you walk into. The rule for moving it
asked whether that id equalled the **first** member's battle appearance — which fired on
only 82 of 144 randomized squads and left 62 showing their vanilla model over a battle
that had changed underneath.

The reason is that a creature's overworld model is often a *different row* from its battle
model. Squad 1 shows `SLG_AA` and leads with a Giant Millipede whose battle appearance is
id 18; the Colossal Worm shows `GWR_HF` against battle id 19. Exact equality with the
first member is simply the wrong question.

Asking whether the appearance matches **any** live member covers **144 of 163** squads —
a mixed Wasp Swarm squad showing its Swat Bot now follows the Swat Bot — and the 19 it
still refuses are exactly the ones that must be refused:

| squad | model | what it is |
|---|---|---|
| 4, 5, 6 | `HNPC_FOR_AA`, `HNPC_CON_AA`, `HNPC_TIM_AA` | the Forester, the Contractor, **Timmy** — quest NPCs you talk to |
| 56 | `SHE_AA` | Shade |
| 124 | `SYR_AA` | Commander Syrax |
| 189 | `BSL_AA` | the Green Hill Marauder chase |
| 201, 320 | `NRG_AA`, `IXA_AA` | Nrrgal, Imperator Ix |

Every one is a story actor or a person standing in the world. A rule that repointed them
would put a monster where Timmy should be. That the test separates them without being
told about them is the reason to trust it.

After the fix, 122 of 144 changed squads have their model updated; the remaining 22 are
squads whose shown member was not itself transplanted, so their model still matches what
loads.

**2. Healing is a percentage (confidence: high — read off the screen).**

`HealHP`'s `Data` is a **percent of max HP**, not a flat amount. The item panel draws it
as `HP +18%` in green, directly above the description that `randomize_items` had just
rewritten to say "Restores 18 HP." The generated text now reads "Restores 18% HP."

Worth noting what this says about the description generator's premise. It was built
because POW and GRT are never drawn on the character sheet, so the description is the
only interface — but the item panel evidently *does* draw some effects itself. Which ones
it covers has not been surveyed, and the generated text may be redundant for more than
just healing.

**Also promoted, from the same playtest:** `randomize_chao` (a newly hatched Chao read
"Rugle — POW +2", a stat a vanilla Chao of that tier does not have) and `randomize_items`
(the Revival Ring's rewritten description rendered correctly in game, revive clause and
all).

**Not a bug:** a chest holding two Health Seeds. `pool: placed` redeals the existing
contents among themselves, and Health Seed is the most common chest item in the game —
vanilla `a1_s1_i02` already holds two of them.

---

## 2026-10-10 — Quest rewards were confirmed weeks ago and nobody noticed

**Investigated:** which randomizer features still needed a playtest, before running one.

**Discovered:** `randomize_rewards` was already confirmed and had simply never been
promoted. `rewards.GDA` row 7 is `Woodsman_Reward`, vanilla item **POW Candy** (id 3),
and seed 1 rewrites it to **Ring of Life**. An earlier full_randomizer playtest reported
"got a ring of life for the woodchop" — an exact match for the prediction, against a
vanilla value it could not have been. Moved to **confirmed in game**.

Worth recording as a process note rather than a discovery: the report came in alongside
two genuine failures (the chest and the empty first fight), and the one thing that had
*worked* went unlogged while the failures were chased. A prediction worth testing is
worth writing down before the test, so a pass is as visible as a fail.

**Also fixed, found while building the test checklist:** `_describe` regenerated item
descriptions from `EffectId == 1` rows only. That is correct for *re-rolling* — a Revival
Ring's `Resurrect` row is not a number to shuffle, and it was correctly left alone — but
the description was being rebuilt from the same filtered list, so a Revival Ring came out
reading **"Restores 18 HP."** with no mention of reviving. The item still worked; it just
lied about being an expensive Health Seed.

Across all 219 `.ITM` tables there are exactly three kinds of non-stat effect row: VFX
(105, cosmetic), `RemoveStatus` (15) and `Resurrect` (2). The last two now contribute
sentences, so the Revival Ring reads "Restores 18 HP. Revives a fallen character. Cures
status effects."

This is the second time the description generator has been the bug rather than the
randomizer. The first was consumables being re-rolled into equipment. Both have the same
shape: the thing that decides what to *change* and the thing that decides what to *say*
were reading the same filtered view, and the filter was right for one job and wrong for
the other.

---

## 2026-10-10 — Elemental resistance is stats 75-79, and targeting is three modes

**Investigated:** Three loose ends, all answerable from data: what stat 79 is (the `+50`
on the five shield Chao), what `combo.GDA` column 52 means, and whether the recruitment
order is derivable rather than merely observable.

### Elemental resistance: stats 75-79, and ice is missing on purpose

The five shield Chao each grant `ELEMENT` 50 on a stat in the 75-79 range plus GRT +1, and
each has a description that names its element outright:

| Chao | stat | description |
|---|---|---|
| Korus | 75 | "creates a shield of fire to protect against damage" |
| Perty | 76 | "creates a shield of water…" |
| Jirna | 77 | "creates an earth shield…" |
| Seeri | 78 | "creates a shield of wind…" |
| Knickt | 79 | "creates a shield of lightning…" |

The offence block is already known: fire 107, water 108, earth 109, wind 110,
lightning 111, ice 112. So **resistance is the offence id minus 32, in the same element
order** — and that is what makes this high confidence rather than a guess, because the two
orderings were established independently and agree on all five.

Which also says what is *not* there. Ice resistance should be **stat 80**, and no shipped
item grants it: there is no ice-shield Chao. The offence block has six elements and the
resistance block, as shipped, has five. `ITEM_RESISTS` therefore offers the five that exist
and refuses ice by name, the same rule `MOVE_ELEMENTS` already follows in omitting water
and ice. `custom_item` gained a `resist` effect, verified writing rows identical in shape
to Korus' own: `EffectId 1, Data 50, SData1 75`.

**Uncertainty:** the ids are read from shipped items, but nobody has measured what 50
*does*. "Halves the damage" is the obvious reading and is untested, as is any other value.

### combo.GDA: 48 is splash, 52 is the whole team, and they are exclusive

Columns 48 and 52 are never both set — 113 moves have neither, 22 have 48, 20 have 52 — so
targeting is three modes rather than a flag plus a modifier.

**52 is "hits the whole opposing team"**, and the game says so itself in all twenty
descriptions: Whirlwind "lashing them all", Quake Punch "may stun the entire opposing
team", Flamethrower "hits multiple targets", Bombardment "on the opposing team". Every
single-target move's description says "a foe" or "the target" instead. Column 52 had been
carried as `C_ELEMFLAG` since before the descriptions were read; it has nothing to do with
elements, and the old name is kept only as an alias.

**48 is splash**, and the evidence is a playtest rather than text: Hellfire is 48=1, and a
transplanted Hellfire did 19 to Sonic and 10 to Amy beside him (2026-10-10). All 22 are
damage moves and none is described as hitting everyone.

**Column 55** marks the 23 moves the game treats as support rather than attack — Heal,
Cure, Revive, Scan, Tinker, Taunt, Cloak, Distract. It agrees with "deals no damage at any
tier" on 153 of 155 rows, and the two exceptions are exactly why that is a correlation and
not a definition: Froggy Poison is 55=1 and does 25/38/50, Chaos Rift is 55=0 and does
nothing at all. Recorded as a designer's classification of unknown engine meaning.

### Recruitment: the order is in the plot files after all

Recruitment was previously written off as sealed because the flags a `.dlg` sets are
addressed by plot GUID and ARM9 holds neither names nor ids. That was the wrong place to
look. The **plot registry** is legible, and it is laid out per character:

* **`plt_fp_<char>.plo`** — "find party" — exists for all ten non-Sonic characters: amy,
  big, cream, eggman, knuckles, omega, rouge, shade, shadow, tails.
* **`plt_fpa2_<char>.plo`** — the Act 2 counterpart — exists for nine of them. There is no
  `plt_fpa2_eggman`, which is the data agreeing with the story.

And the flags inside them name the join conditions in plain English:

| character | gate | where |
|---|---|---|
| Amy | `AMY_GET` (flag 23, `plt_ch1_main`) | story, chapter 1 |
| Tails | `GO_TO_TAILS` → `TAILS_MET` → `TAILS_GET` (28/29/30) | story, chapter 1 |
| Knuckles | `KNUCKLES_FOUND` (58, `plt_ch2_main`) | story, chapter 2 |
| Eggman | `EGGMAN_FOUND` (75, `plt_ch3_main`) | story, chapter 3 |
| Shadow | `CH4_SHADOW` → `_FIGHT` → `_DEFEATED` → `SHADOW_GET` | chapter 4, by beating him |
| Rouge | `GUN_MISSION_ACCEPTED` → `GOT_NOCT_1..4` → `STOLEN_5_TECHNOLOGIES` → `GUN_MISSION_COMPLETE` | GUN side mission |
| Cream | `CHEESE_QUEST_GIVEN` → `CHEESE_FOUND` → `GOT_CHEESE` → `CREAM_GET` | side quest, Green Hill |
| Big | `FROGGY_QUEST_ACCEPTED` → `FOUND_FROG_1..3` → `FROGGY_QUEST_COMPLETE` → `BIG_GET` | side quest |
| Omega | `OMEGA_QUEST` → `FOUND_OMEGA` → `OMEGA_FIGHT_OVER` → `OMEGA_FIXED` → `OMEGA_GET` | side quest, Metropolis |
| Shade | `WHY_BELIEVE`, `SHADE_IMPRESSED` | Act 2 story |

The locations come from the 70-odd `MAP_PIN_*` flags, which carry an area prefix and are
numbered in **area progression order**: GHZ → CCZ → MRZ → BRZ → MET → ANG → GRZ → KRO →
NRG → ZOA → VOX → NOC. That matches `areas.GDA` and gives, for free, a progression order
to place the optional recruits against. `MAP_PIN_GHZ_CREAM`, `MAP_PIN_MET_OMEGA` and
`MAP_PIN_MRZ_SHADOW_SIGNAL` place three of them directly.

**What this unblocks.** The abilities half of `randomize_characters` needs the invariant
"for every prefix of the recruitment order, the party can field at least vanilla's
abilities". The order above is derived from data rather than from memory, which is what was
missing. **It is a derivation and not yet a confirmation** — it should be checked against
an actual playthrough before anything is built on it, because a wrong order there is a
softlock rather than a bad roll.

**And a partial answer on ability gates.** Placeable type 1, the 69 "blocks", carries
`(ability, level, 0)` in its three payload parameters, and only two distinct abilities
appear across all of them: Dash (ids 0, levels 0 and 1) and Smash (id 1, level 2). That is
consistent with the two abilities that remove an obstacle. The gates for Fly, Jump, Climb,
Teleport and Stealth are **not** in this list and have not been found. Note also that
`areas.GDA` names a per-area movement table — `GreenHillZoneMovement.gda`,
`CentralCityMovement.gda` — and **none of them is in the archive**: dangling names from the
asset pipeline, the same pattern as the debug menu's missing command strings.

`movement.GDA` itself resolves to 11 abilities with max levels: Dash 3, Smash/Bash 3, Fly
3, Jump 1, Climb 1, "inv" 3, Stealth 1, Teleport 1, two more on the stealth icon, and a
Bash variant.

---

## 2026-10-11 — XP halves for every party level, which is why grinding is impossible

**Investigated:** The shape of the XP decay, by repeating **one** encounter at a fixed
party level and then again after levelling - the experiment the previous session's data
could not support because party level had not been recorded.

**The measurement.** 1 Swat Bot + 2 Wasp Swarm, five times:

| party level | XP |
|---|---|
| 4 | 80, 80, 80, 80 |
| 5 | **40** |

**Two results, both clean:**

1. **XP is deterministic at a fixed party level.** Four identical fights, four identical
   awards. No randomness, no per-kill diminishing return, no first-encounter bonus (that
   last was already ruled out by an earlier pair that both paid 32).
2. **XP halves for every party level gained.** 80 -> 40 on a single level. And the
   previous session's otherwise-ambiguous pair fits exactly: 2 Wasp + 2 Boar paid 75 and
   then **37**, which is 75/2 = 37.5 rounded down. Two independent exact halvings.

A per-enemy award scaled by `2^(enemy level - party level)` reproduces both: every term
halves together when the party gains a level, so the total halves regardless of the
encounter's composition. The per-creature base is not yet separable from the data.

3. **The award never falls below 10.** Three encounters of completely different
   composition - 3 Sentry Drones, 2 Sentry + 2 Armadillo, and 2 Armadillo + 2 Wasp Swarm
   at party level 4 - all paid **exactly 10**. A floor, not a coincidence. Note the third
   of those hit the floor at level 4 while a Swat Bot pack was still paying 80 at the same
   level, so the per-enemy decay against *its own* level is steep: an Armadillo three
   levels down contributes almost nothing.

**A correction to what this entry first claimed.** Before the floor was known, the table
below was computed as a pure halving and the conclusion drawn was that grinding is "not
merely slow, it is self-defeating". **That was wrong**, and wrong by two orders of
magnitude:

| party level | XP per fight | XP to next level | fights | (without the floor) |
|---|---|---|---|---|
| 4 | 80 | 609 | 8 | 8 |
| 5 | 40 | 884 | 22 | 22 |
| 6 | 20 | 1,282 | 64 | 64 |
| 7 | 10 | 1,859 | 186 | 186 |
| 8 | **10** | 2,695 | 270 | 539 |
| 10 | **10** | 5,666 | 567 | 4,533 |
| 12 | **10** | 11,915 | 1,192 | 38,128 |
| 15 | **10** | 36,323 | 3,632 | 929,869 |

Level 4 to 15 is about **11,400 fights with the floor** against 1.4 million without it.
Brutal, and entirely possible for a determined player. The floor is what keeps the level
cap reachable at all.

**What this settles, stated at the strength the evidence supports.** The expected party
level in a zone is *strongly influenced* by the levels of the enemies that live there -
levelling slows by half per level until it hits the floor, so the party naturally sits in
a band a few levels above the local trash. It is not *pinned* there; a player who wants to
out-level a zone can, it just costs hundreds of fights.

That still **supports `enemy_scaling` as already designed.** It keys its curve off each
creature's own level, chosen as a cheap proxy for "where the player is", and the proxy
tracks the typical player well. Party-relative scaling would buy something real for the
grinder who has left the band - just much less than it appeared to before these
measurements, since the XP curve does most of that work already.

---

## 2026-10-11 — The game already scales XP to the party's level

**Investigated:** The combat XP formula, by measuring it in play - nine fights on
`chao_farm.nds`, enemy composition and XP recorded for each.

**Discovered (confidence: high - three independent repeats, all in the same direction):**
**an identical encounter pays less XP as the party levels up.**

| encounter | XP, in play order |
|---|---|
| 2 Sentry Drone + 2 Enraged Armadillo | 32 -> 32 -> **10** |
| 3 Sentry Drone | 25 -> **10** |
| 2 Wasp Swarm + 2 Wild Boar | 75 -> **37** |

Three different compositions, every repeat lower than the one before. The game computes
XP **relative to the party**, not as a fixed award per creature.

**A first-encounter bonus is ruled out.** Fights 1 and 2 were the same composition, the
first of them the party's first ever meeting with both species, and both paid exactly
**32**. So novelty is not a term in the formula, which leaves party level as the only
variable that changed across the repeats.

Normalising by the summed level of each fight's enemies gives XP per enemy-level of 5.33,
5.33, 7.50, 4.17, 9.38, 3.70, 1.67, 3.33, 1.67 in play order - falling overall, and
highest on the two fights whose enemies were at or above the party's level at the time
(2 Swat Bot at level 4, and the Wasp/Boar pack).

**What this kills.** The plan to compute an expected-level curve by summing the XP
available in the game is **dead**: there is no fixed total. Grinding pays less, so the sum
is a function of how you play rather than a property of the data. That was the plan an
hour ago and it does not survive its own first measurement.

**What it gives back, which is more.** Two things:

1. **The game self-balances toward a level band per zone.** An expected party level is
   therefore well-defined by design - it just has to be *observed* rather than computed.
   A playthrough noting the party's level on arriving at each zone produces the curve
   directly, and that curve is what static `enemy_scaling` should key off.
2. **ARM9 reads the party's level during combat resolution.** It must, to compute this.
   That is a second, probably easier, watchpoint target than the stat loader: the
   battle-end XP path is reached on every single fight, where a creature stat load may
   happen once at area entry.

**Still needed to fit the formula:** the party's level at each fight. Everything else is
recorded; that one column was not, and without it the decay cannot be pinned.

---

## 2026-10-11 — No New Game+ counter, and combat XP is not in the tables

**Investigated:** Whether enemy scaling could key off the New Game+ cycle instead of the
party's live level - the point being that a static, build-time curve needs no running
code, where party-relative scaling needs the ARM9.

**There is no NG+ counter.** No plot flag mentions a cycle, replay or completion count;
`YouAreNotDoneYet.GDA` turns out to be the end-screen slideshow (image names, durations)
and nothing more. The game's own help text settles it: *"To start a new game, select and
then delete one of your save slots"* (string 18271). A NG+ run is just a cleared save
carried forward, and nothing counts how many times you have done it. So there is nothing
to key a per-cycle curve off.

**Combat XP is not in the data either, and two plausible homes were tested and rejected.**

* `squads.GDA` column 2 is a float in the right sort of range (40, 50, 81, 200) and looks
  exactly like a per-squad XP award. It is not: correlated against the total level of each
  squad's members across 163 squads, **r = -0.044**. Treating it as XP also gives 33,845
  XP for clearing every encounter in the game against the 1,159,258 that level 30 needs,
  which is its own refutation.
* Several squad columns index `rewards.GDA` plausibly; none of them tracks member level
  either (best **r = +0.046**).

What *is* in `rewards.GDA` is **quest** XP, and it is legible - "Wasp Quest" 50, "Factory
Quest" 500, "Dimensional buffer found" 500, the generic tiers 75 and 2500. Routine
encounter XP is computed in ARM9 from the creature, as the damage model is.

**Which does not block the idea.** The formula is cheaply measurable in play and needs no
debugger: kill a creature whose level `creatures.GDA` states exactly, note the XP, repeat
at two or three different levels. That is the same method that produced the damage model
(basic attack = 0.70 x POW - 2.86, fitted from two in-play measurements), and three points
would pin an XP curve well enough to compute the expected party level at every zone.

The distinction worth keeping straight: **expected-level scaling is static data and is
buildable today; party-relative scaling needs the ARM9.** They are not the same feature,
and the first may well be what is actually wanted.

---

## 2026-10-10 — A Chao cannot be given as loot: the acquisition path is the gate

**Investigated:** Why the five code-driven Chao placed in Green Hill's chests never
reached the Chao collection.

**Observed in game.** The chest opens, the reward screen shows three Chao with the right
names and the right descriptions — "Chao 1", "Chao 2", "Chao 21", which are items 171, 172
and 191, i.e. Stebsly, Choo and Joy at their Max tier, exactly what the build put there.
Then the inventory's Chao tab reads *"There are no items to display"*. The edit was right
and the items went nowhere.

**Discovered (confidence: high — an exhaustive census, and it is unanimous).** Vanilla
**never** grants a Chao through any of these paths:

| path | vanilla instances of a Chao item id |
|---|---|
| chest slots (159 across 53 chests) | **0** |
| shop rows (all `Store*.GDA`) | **0** |
| drop tables (`RandItems.GDA`, item columns only) | **0** |
| placed item objects (list 40002, kind 4) | **1, and it is in `jay_test.are`** |

123 Chao item ids, and not one of them appears in a chest, a shop or a drop anywhere in
the game. The single placed Chao object in the whole ROM sits in the developers' own test
area — which is suggestive about what *might* work, and is not a vanilla player path.

So **the acquisition path is the gate, not the item id.** The chest's reward screen is
generic item presentation and will happily draw a type-3 item; whatever adds an item to
the player's possession then declines to file it, because a Chao's home is the collection
rather than the inventory. This is consistent with the earlier failure to find a 45-entry
per-id Chao array in the save: the collection is its own system, reached its own way.

A caution for the drop and reward censuses: the first pass produced eleven "hits" that
were all false. `RandItems.GDA` is **(weight, item) pairs**, so its odd columns are
percentages, and percentages of 95 or 100 land squarely inside the Chao id range of
91-215. The same trap caught the reward table's XP column. Only the even columns are item
ids, and restricted properly the count is zero.

**Consequence for the build.** `profiles/chao_farm.json` **no longer touches the chests**.
The edits did nothing except cost Green Hill its real loot — Health Seeds, POW Candy,
Prune Juice — which on a fresh playthrough is a straight loss. The 100 ring-to-egg
conversions stay, because those are confirmed. Hatching is the only player path to a Chao
and the ROM now offers 110 chances at it in one zone.

---

## 2026-10-10 — Rings do become Chao eggs, and melonDS freezes in the tutorial

Two results from the same run, one good and one that may close off a route.

**Rings really are eggs — and the game's own counter proves it to the unit.** On
`build/chao_farm.nds`, Green Hill's rings render as Chao eggs, and the zone HUD reads
**0/111 eggs** and **0/85 coins**. Against the build:

| | eggs | coins |
|---|---|---|
| vanilla `a1_s1_*` | 11 | 185 |
| `chao_farm` | **111** | **85** |
| game HUD | **111** | **85** |

So the **collection system** reads `ptype`, not just the renderer: a converted ring is
filed under eggs by the thing that counts them. That is a stronger confirmation than
seeing egg models on the ground, and it settles the mechanism.

**And it revealed how the counter is scoped.** The build puts 110 eggs and 83 rings in
`a1_s1_ex.are`, not 111 and 85. The difference is that **the zone counter aggregates an
area with its interiors**: `a1_s1_i02` and `a1_s1_i03` hold one ring each, and
`a1_s1_i03` holds the eleventh egg. 110 + 1 and 83 + 2 are exact.

That makes the HUD a **free, precise oracle for any area edit** - the count can be read
off the screen on arrival, without collecting anything, and compared against what the
build put there. Worth reaching for before designing another collection playtest.

Still unverified: this was a **fresh** save, so it says nothing about whether a save that
has already swept Green Hill will show the eggs (the collected-state question), and
nothing has been picked up or hatched, so the egg *behaving* like an egg is untested.

**melonDS freezes at the jump tutorial.** First boot, GDB stub on, JIT off, no save:
the game hangs at the jump part of the opening tutorial. This is the risk that was flagged
before the route was chosen — the project plays on DeSmuME 0.9.11 precisely because other
builds misbehave with this game — and it has now been observed rather than feared.

What it does *not* yet establish is that the route is dead, for three reasons worth
testing in this order:

1. **The tutorial may be skippable.** The god-mode save starts in Green Hill, well past
   the jump tutorial. If the game runs from that save, the freeze is a curiosity rather
   than a blocker, because the experiments need a battle and a plot event, not the
   opening. melonDS wants the raw `.sav`, which `save_edit.py --to-raw` now produces.
2. **melonDS' built-in BIOS replacement is a known compatibility limitation.** Real DS
   BIOS and firmware dumps — from the user's own hardware — are the standard next thing
   to try when a game misbehaves there, and a tutorial that hangs on an input prompt is
   the sort of thing that fits.
3. **Only then does the emulator need changing.** DeSmuME supports `--arm9gdb` when built
   with it; 0.9.11 x64 is not (verified against the binary). no$gba has a capable
   debugger but it is the paid build, around US$15, and it has no GDB stub — so the
   client here would not drive it and the experiments would be manual.

Recorded now because "melonDS runs this game" was an assumption the whole debugging plan
rested on, and it has turned out to be at least partly false.

---

## 2026-10-10 — The block rewrite works in play, and the dev block had to be filtered out

**Confirmed in game.** `build/character_randomizer_test.nds` at seed 1, `moves:
"character"`: Sonic's POW menu reads Tornado Kick, Jewel Storm, Rising Knuckle, Plunder,
Distract, Shriek — Rouge's six, in Rouge's order, with Rouge's icons and Rouge's
description text ("Rouge delivers a rapid series of kicks"). Moving the row contents is
the right mechanism; the owner column never was.

Two details worth recording from that screenshot:

* **The game greys out a move whose cast is absent** rather than breaking. Rising Knuckle
  sat in slot 3 reading "Unavailable" because its partner was not in the party. That is
  the engine handling an unmeetable requirement gracefully, and it is what makes a
  per-move deal survivable at all.
* **The description travels with the move**, so a borrowed move still names its original
  owner in its own text. Cosmetic, and arguably correct — it is still Rouge's technique.

### Per-move dealing, and why it runs inside participant classes

Asked for something stronger than trading movesets wholesale: six moves from six different
people. `moves: "move"` deals individual rows across the whole cast, and the deal runs
**within participant class** with each slot keeping its own cast (`COMBO_CAST_COLUMNS`).

That is not a conservative default, it is the thing that makes the mode safe. A slot's
cast is what the game was paced around — Sonic's first two moves are solo because he
starts alone — so pinning it means no opening move can come to depend on a character not
yet recruited. Dealing inside the class also keeps damage in the band it was authored for,
instead of dropping a four-character finisher into a level-1 solo slot. Vanilla holds 38
solo slots, 10 duo, 5 trio and 1 quad; the quad is alone in its class and stays put.

Shade and Eggman, who sit out `"character"` because no other block is their size, do take
part here.

### The filter that was missing: a block whose moves have no names

The first per-move build dealt **nameless developer stubs into real characters' hands**.
Party slot 12 is `VFXTester`, and its twelve contiguous rows at 108-119 are placeholders:
`namestrref` -1, cost 0, damage -1 at every tier. Contiguity did not catch them — they are
perfectly contiguous — and in `"character"` mode they were harmless only by accident,
because nothing else in the table has twelve moves so the block never found a partner to
trade with. Class membership is by participant count, so in a per-move deal all twelve
joined the solo pool, and Knuckles, Tails, Rouge and Big each came out holding a move with
no name that does nothing.

`_move_blocks` now requires **every move in a block to have a name**. That is a data test
for "a player can see this", and it is the right reason rather than a convenient one: a
block whose moves have no names is not a moveset. What survives all three filters is
exactly the eleven recruitable characters.

The general lesson is the one this project keeps relearning: a filter that happens to
exclude the wrong thing is not the same as a filter that excludes it *for a reason*, and
the difference only shows up when the surrounding code changes.

---

## 2026-10-10 — A POW moveset is bound to its block position, not to the owner column

**Investigated:** Why `randomize_characters`' `moves` mode did nothing in play, having
verified statically that it had rewritten every owner and partner in `combo.GDA`.

**The playtest.** On `build/character_randomizer_test.nds` (seed 1), from a fresh start
with Sonic and Amy: *"their POW moves are restricted to rouge for sonic and knuckles for
amy, but sonic still has his own pow moves, they just require rouge to use, and amy has
her own pow moves but requires knuckles"*.

That is diagnostic rather than merely disappointing. At seed 1 the permutation was
sigma(Sonic) = Rouge and sigma(Amy) = Knuckles, so what the player saw was **exactly the
permutation applied to the requirement and not to the menu**.

**Discovered (confidence: high — a prediction and its refutation, from play):**

`combo.GDA` is laid out as one contiguous block of rows per character — Sonic 0-5,
Knuckles 6-11, Shadow 12-17, Tails 18-23, Cream 24-29, Big 30-35, Omega 36-41,
Rouge 42-47, Amy 48-53, Shade 54-57, Eggman 58-59, and then ~90 boss and enemy rows.
**The block is the binding.** A character's menu is its own block, and column 2 — read
until now as "owner" — is a *participant requirement*: the game shows you the moves in
your block and then demands whoever column 2 names before one can be used.

So a moveset swap cannot be done by repointing column 2. It has to move the row
*contents* between blocks: damage tiers, PP cost, status effects and their per-tier
chances, element, name and description strrefs, icons, targeting. Fifty-three of the
fifty-six columns.

**Two further corrections fell out of the same investigation:**

* **Column 2 is in the party-slot id space, not the creature-row space.** This was already
  recorded for the debug menu's add/remove entries (see the 2026-10-05 entry) and was
  missed here: Shade is party slot 10 and creature row 27, and the first version of the
  feature took its cast from `creatures.GDA` row indices and wrote **27** into owner and
  partner cells. `party.GDA` is a four-column table — (id, name, party slot, creature
  row) — and exists precisely to bridge the two spaces. `_party_slots` now does.

* **Four of `combo.GDA`'s columns are `ndsfixed`, not integers.** GFF4 type 18: a signed
  32-bit fixed-point number with 12 fractional bits, which the reader divides by 4096.
  Columns 30/31/32 are a move's status-effect chance per damage tier (0.3 / 0.5 / 0.8 on
  Sonic's Blue Bomber; -1.0 where there is no status) and 46 is a fourth. `set_int_cell`
  had no case for the type and `op_gda_cell` coerced every value with `int()`, so moving
  those cells would have silently zeroed every status chance in the game. Both now handle
  the type, and the writer **refuses** a fractional value into an integer column rather
  than truncating it.

**How it was tested.** `_move_blocks` recovers the blocks from the table rather than
hardcoding them, and only equal-length blocks trade, so nobody ends up with more moves
than their menu has slots: the nine six-move characters shuffle among themselves while
Shade (four) and Eggman (two) keep their own. A block must also be contiguous, which is
what drops Super Sonic — party slot 11, but his three rows sit at 143, 153 and 154.

Rebuilt at seed 1 and read back out of the finished ROM: Sonic now fights with Rouge's six
moves and Rouge with Sonic's; Knuckles has Big's, Big has Omega's, Omega has Tails',
Tails has Cream's, Cream has Knuckles'; Amy and Shadow trade. Every move's participant
count still matches its cast, no cast names the same character twice, and no id outside
the party space appears. The stat half, unchanged, is a clean derangement of all eleven
`Adv_*.GDA` tables with level and XP columns untouched.

**Remaining uncertainty — and it is the interesting one.** Column 33 is a per-character
art prefix (`BIF_SON`, `BIF_BIG`) and is deliberately **left with the character** rather
than moved with the move. Handing Knuckles a row that asks for Big's animation bank asks
his model for a clip it does not have, and this game is already known to hard-crash on a
VFX lookup it cannot satisfy (Focus Field plus an element, 2026-10-08). Keeping the prefix
means a borrowed move plays in the borrower's own animation: visually wrong, and safe.
Whether that is actually enough is unknown — the VFX ids in columns 15-24 do travel with
the move, and nothing in the table predicts which combinations the engine tolerates. A
crash on using a borrowed move is the thing to watch for, and would mean the VFX columns
have to stay behind too.

---

## 2026-10-10 — Chao eggs are placeables, and a ring is one field away from being one

**Investigated:** Where Chao eggs live, after the user asked for roughly a hundred of them
at once rather than hunting the game's own supply one at a time. The need behind it is the
Ovus test: `chao_level` can only be settled by a **Level 1** code-driven Chao with a
countable effect, and which species an egg hatches into is random.

**Discovered (confidence: high — read from the area files, and the shapes are identical):**

Chao eggs are **placeables**, list 40001 in an `.are` file, `ptype` (field 40018) **32**.
There are 115 of them across the 79 areas. This was already in the census recorded with
the chest work; what is new is that **a ring and a Chao egg differ in exactly one field**.
Comparing an authored egg against an authored ring in the same area, every other field of
the struct agrees: the position vector at label 4, the tag at 40006, the three payload
floats at 40020-40022, the per-area index at 40023, and 40019/40026/40027. Only `ptype`
distinguishes a thing that gives you five rings from a thing that gives you a Chao.

So converting a ring into an egg is a one-field, in-place, no-resize edit — the same class
of edit as redealing a chest.

**Also established while looking:** there is no "Chao Egg" row in `Items.GDA`. Eggs are
not inventory items, they are world objects, which is why nothing in the item catalogue
ever matched. The icons `ITM_CHAO_egg_0/3.NCGR` and `GUI_Items_ChaoEgg.NCLR` are for the
top-screen incubation indicator (string 6327: *"The Chao Egg icon on the top screen is
shaking! That means a Chao hatched in your Chao Garden!"*).

**And an independent confirmation of an earlier finding.** `Chaos.GDA` row 37, Ferox, names
item **128 for all three tiers** — the only row of the forty that does. The user's
explanation for why Ferox is unaffected by level ("Ferox automatically makes POW moves
successful, so having more levels can't make a POW move *more* successful") is matched
exactly by the data: Ferox has no second or third tier to reach.

**How it was tested.** `profiles/chao_farm.json` converts 100 of Green Hill Zone's 183
rings (area `a1_s1_ex.are`, `areas.GDA` row 3) to `ptype` 32, taking the target shape from
the ten eggs the area already contains rather than from a guess — any field of a converted
ring that disagrees with the authored shape is written to match. Read back out of the
built ROM: 110 eggs, 83 rings, and no egg with a field out of shape. The same profile
refills all five of Green Hill's chests with the five code-driven Chao whose effect is a
count rather than a percentage, so the test does not depend on the hatch lottery at all.

**Remaining uncertainty.** Whether a placeable's collected state is tracked per placeable
in the save — if it is, and the player has already swept Green Hill, the converted rings
may come back already taken. A fresh save settles that. And whether anything caps how many
eggs can be in incubation at once is unknown; the game has never had more than a handful
to hold.

---

## 2026-10-10 — The POW floor lands, and the damage model predicts out of sample

**Investigated:** whether the recalibrated floor produces a sensible encounter.

**Discovered (confidence: high):** it does, and the model held on a point it was not
fitted to. A level-2 transplanted Gizoid Centurion at the new floor of POW 11 used
Hellfire (350%) for **19 damage, with 10 splash**. The prediction was ~17 — about 12%
under, on a fit taken from two measurements against a different party member.

| test | POW | main target | damage | predicted |
|---|---|---|---|---|
| before the floor | 6 | Amy | 2 | — (fitted) |
| first floor, too high | 18 | Amy | 34 | — (fitted) |
| **recalibrated floor** | **11** | **Sonic** | **19** | **17** |

`randomize_encounters` moves to **confirmed in game**, in both modes: reskin earlier
today, transplant now. That is the whole point of transplant mode demonstrated — a
creature from the endgame, using its own move, at the power level of the slot it
replaced.

**Incidental observation, not a decoded field:** splash damage ran **16 against a 34
main hit** and **10 against a 19 main hit** — 47% and 53%, so about half. Nothing in
`combo.GDA` row 140 looks like a splash fraction (the only unexplained numerics are
columns 7, 31, 32 and 54, and columns 31/32 are both the float 1.0), so the halving is
presumably in ARM9. Recorded as a regularity, not a finding.

**Remaining uncertainty:** the 12% under-prediction is consistent with the party having
levelled or geared between tests, or with Sonic and Amy simply taking different damage,
and nothing here separates those. The constants are good enough for choosing a floor and
should not be trusted further than that.

---

## 2026-10-10 — The damage model, measured: linear in POW with a subtraction

**Investigated:** the POW floor shipped an hour earlier overshot. The same transplanted
Gizoid Centurion went from a 2-damage move to **34 damage on a level-2 Amy, with 16
splash onto Sonic**.

**Discovered (confidence: high — two measurements of the same creature in the same
slot):** damage is **linear in POW with a flat subtraction**, which is why the bottom of
the range is so violent.

| POW | move | multiplier | damage | implied basic attack |
|---|---|---|---|---|
| 6 | combo 139 | 150% | 2 | 1.33 |
| 18 | combo 140 (Hellfire) | 350% | 34 | 9.71 |

Dividing out the multiplier gives `basic ≈ 0.70 × POW − 2.86` against that target. **A
3× POW raise multiplied the damage by seventeen**, because at POW 6 almost the whole hit
was being eaten by mitigation and at POW 18 almost none of it was. Any floor placed in
this region is on a knife edge, which is worth knowing before tuning anything else that
touches enemy POW — `enemy_scaling` included.

**What was wrong with the floor.** It took the median POW of enemies *that have POW
moves*. Levels 1-2 have almost none (2 of 41), so the ±2 window pulled in level 3-5
values and set a level-2 slot at POW 18. The population was selected by the very property
that makes it unrepresentative of the band.

**The correction:** `_typical_pow` — the median POW of **all** enemies at that level, 11
at levels 1-3 rising to 72 at level 20. Same bounds as before. The model predicts the
350% move at **~17** and the 150% move at **~7** for a level-2 slot: a real threat that
does not delete a party member.

**How it was tested:** seed 1, 15 creatures raised, 0 lowered, and only genuinely
low-POW victims move — a level-4 Laser Drone with vanilla POW 30 is left alone and still
hits for ~63 with a 350% donor move, which is vanilla difficulty rather than anything
this feature added. `transplant_test.nds` rebuilt and verified. **Not yet played.**

**Remaining uncertainty:** the model is fitted to two points from one creature against
one party member at one level. The constants are almost certainly target-dependent —
Amy's defense is not Sonic's, which the 34/16 split against the same move already shows.
It is good enough to choose a floor and not much more.

---

## 2026-10-10 — Why a transplanted move does 2 damage, and the POW floor that fixes it

**Investigated:** whether the 2-damage Quake Punch from a transplanted Gizoid Centurion
was a bug, and what the right correction is.

**Discovered (confidence: high):** it was not a bug, and "raise POW" needed a reason
before it needed a number.

Seed 1 puts the Gizoid Centurion's move set on creature 74, a **level-2 Sentry Drone with
POW 6**. A POW move does a percentage of a *basic attack* and a basic attack runs on POW,
so the Centurion's 75 (= 150%) move resolves to about 2. Correct arithmetic, bad
encounter.

The real finding is in the vanilla table. **The game barely gives POW moves to low-level
enemies at all:**

| levels | enemies | with any POW move | median POW |
|---|---|---|---|
| 1-2 | 41 | **2** | 11 |
| 3-5 | 13 | 13 | 18 |
| 6-8 | 17 | 17 | 30 |
| 15-17 | 13 | 13 | 70 |

Moves start at about level 3, which is about where POW starts being worth having. So a
transplant into an early slot does something the game never does: it hands a move to a
creature built never to swing one. The victim's stat block is correct for the victim; it
is not a stat block that can carry a move set.

**The fix is derived, not invented** — though the first draft drew it from the wrong
population; see the entry below for the correction. It takes the median POW of vanilla
enemies at each level, over a ±2 level window to smooth thin bands. A transplanted
creature that **gained at least one move** is raised to that floor, bounded twice — never
below the victim's own POW, never above the donor's. A transplant therefore always sits
between the creature it replaced and the creature it imitates.

**How it was tested:** seed 1 over the 60 transplanted creatures — **16 raised, 44
unchanged, 0 lowered**. The reported case, Sentry Drone POW 6 against a Gizoid Centurion
donor, becomes POW 18, so the 2-damage move should land near 6. `transplant_test.nds`
rebuilt (creatures 128 → 188) and verified; the appended low-level rows read back at POW
12-18 where they were 2-8. **Not yet played.**

**Remaining uncertainty:** the floor is calibrated from the vanilla table, not from
observed damage, so "POW 18 gives a satisfying hit at level 2" is a prediction. One fight
settles it, and `pow_scale` is the dial if it is still limp. The reverse risk is real
too: these creatures now hit roughly three times harder than the trash they replaced, in
the opening zone.

---

## 2026-10-10 — Confirmed in play: chest contents, placement shuffling, and transplant damage

**Investigated:** the three predictions made earlier today, each checked in DeSmuME
0.9.11 on the EU build.

**1. Chest contents — confirmed.** A fresh save on `world_randomizer_test.nds`, and Green
Hill's first chest handed over a **Cure All Spray** where vanilla gives a Health Seed.
That is exactly what writing `Items.GDA` id 13 into field 40020 of placeable 175
predicted, and it is the end of the question: a chest's loot is three `float32` slots in
its own area file. `randomize_chests` moves to **confirmed in game**.

**2. Placement shuffling — confirmed, on the third attempt.** The Green Hill Marauder
encounter is a Marauder again, and groups elsewhere are still displaced (a Queen Wasp
pack at level 5 in the opening zone). All three protections are now carrying weight:
tagged spawn points, protected creatures, and the solo-squad rule added this morning.
`randomize_placements` moves to **confirmed in game**. The history is worth keeping — two
different causes produced the identical symptom of an empty battle, a day apart, and the
first fix was reported as solved before there was any way to tell them apart.

**3. Transplant damage — confirmed harmless.** A transplanted **Gizoid Centurion used
Quake Punch for 2 damage**. This follows from what was already known and is worth stating
as a rule: POW move damage is a *percentage of a basic attack*, so the multiplier rides
on the creature's own POW. A donor's 300-multiplier move lands on a creature built at the
local power level and resolves to nothing. The danger that `damage_scale` was built for
does not exist, and the real risk runs the other way — transplanted enemies have the
donor's spectacle and none of its bite. Raising POW for transplants is the open tuning
question.

**Evidence:** in-game screenshots for 1 and 3, player report for 2.

**Remaining uncertainty:** none for 1. For 2, only seed 1 band 3 has been played, so the
protections are confirmed against one deal of the cards rather than all of them. For 3,
one move on one creature.

---

## 2026-10-10 — The plot flag registry is readable by name, and what it says about recruitment

**Investigated:** Where recruitment order lives, and whether party-relative enemy scaling
can be reached without a debugger — after the chest result showed that "it must be in
ARM9" deserves one more look at the data first.

**Discovered (confidence: high):** every plot flag in the game can now be resolved to the
name its designers gave it. `tools/recon/plotflags.py` does it: **649 of 657** flags
resolve. The chain is `plotflags.GDA` (657 rows of global id → plot index + flag index) →
`plots.GDA` (102 plot indices → 95 distinct `.plo` files) → the `.plo` itself, whose root
list holds plot *headers*, each carrying a **nested** list of flag entries with the name
at field 13002. The nesting is why earlier reads of a `.plo` showed one entry and no
flags.

This is what identified the `kind == 4` objects — see the chest entry above — and it
names the gates on everything an area references.

**What it says about recruitment (confidence: high for the facts, and the conclusion is
a negative result):**

* Recruitment is flag-driven, and the flags are explicit: `AMY_GET` (23), `TAILS_GET`
  (30), `BIG_GET` (56), `SHADOW_GET` (124), `OMEGA_GET` (413), `CREAM_GET` (450).
  Knuckles, Rouge and Shade use differently named flags (`KNUCKLES_FOUND`, `MET_ROUGE`,
  `SHADE_IMPRESSED`), so the pattern is not uniform.
* `plt_gbl_misc` holds a contiguous block, `DISPLAY_AMY` (114) through `DISPLAY_OMEGA`
  (123). **It is not a character index** — the order is Amy, Big, Tails, Rouge, Knuckles,
  Shadow, Cream, Shade, Eggman, Omega, while `creatures.GDA`'s `playerid` runs Sonic 0,
  Knuckles 1, Tails 2, Amy 3, Shadow 4, Rouge 5, Big 6, Cream 7, Omega 8, Eggman 9,
  Shade 10. Two different authoring orders, not one table.
* **Dialogue references plots by GUID.** `a1_big.dlg` contains
  `1E2CD4BBBC114BA48F917BF5AD7CB7D7`, which is exactly `plt_fp_big.plo`'s field 13007.
  No data file anywhere contains the string `BIG_GET` — flags are addressed as
  (plot GUID, flag index) pairs, never by name.
* **ARM9 contains no flag names and no table of the recruitment flag ids.** `OMEGA_GET`'s
  id 413 does not appear once as an aligned 16- or 32-bit constant in the whole 1.1 MB
  binary, so there is no flag-id → "add this character" table for a static search to
  find.

**Conclusion:** recruitment order stays behind the ARM9 wall, but the debugger session
now has a precise entry point rather than a vague one — breakpoint on the write that sets
flag 56, 124, 413 or 450 and watch what reads it.

**Party-relative scaling, tried and failed statically:** `creatures.GDA` column names are
recoverable by hashing (`crc32` of the lowercased UTF-16LE name) against the table's own
header, which independently confirms the project's column map and names 13 of 61 columns:
`id` 0, `speed` 4, `attack` 5, `defense` 6, `health` 7, `power` 8, `grit` 9, `luck` 10,
`fatigue` 11, `appearance` 14, `level` 33, `playerid` 35, `class` 37. **None of those
hashes appears in ARM9**, so the binary does not look columns up by hash at the point of
use — it was compiled against fixed indices, which a static scan cannot tell from any
other small constant. Party-relative scaling needs the GDB session; this was the cheap
attempt and it did not work.

**Incidental correction:** `CR_CLASS = 32` was the wrong name. Column **37** is `class`
and is -1 for 111 of 128 rows — a *character* class only the playable cast has. Column 32
is the beast/insect/robot *type*, its hash is shared with a column of `appearances.GDA`,
and its real name is not recovered. Renamed `CR_TYPE`; behaviour unchanged, and leaving
it uncopied in a reskin is still right.

**Remaining uncertainty:** what sets a `_GET` flag is a dialogue node, and the `.dlg`
action structs (templates 35/36, fields 12300–12305) were only identified in outline, not
decoded. If those turn out to carry a party-member id, recruitment becomes data-editable
after all. That is the next cheap thing to try before the debugger.

---

## 2026-10-10 — Chest contents found: three floats in the area file, not ARM9

**Investigated:** Where a chest gets its loot — reopened after the ARE placeable list was
re-read field by field rather than through the integer-only convenience reader.

**Discovered (confidence: very high):** a chest is a **placeable of type 6** in the area's
list **40001**, and its contents are the three `float32` parameters at fields **40020,
40021 and 40022** — `Items.GDA` ids, with `-1` for an empty slot. 53 chests, 159 slots,
120 of them filled.

| area | chest | slots |
|---|---|---|
| `a1_s1_ex` | 175 | Health Seed · — · — |
| `a1_s1_ex` | 176 | Prune Juice · Health Seed · — |
| `a1_s1_ex` | 218 | Boxing Gloves · — · — |
| `a2_s4_i03` | 0 | Voxai Teleporter · Immunity Booster · Med Emitter |
| `a2_s5_i05` | 0 | Zoah Shield · — · Psychic Water |
| `a2_s2_i04`, `a2_s3_ex`, `a2_s4_i05`, `a2_s5_i04`, `a2_s6_ex` | one each | Nocturne Relic · — · — |
| `jay_test` | 3–7 | Health Seed · Health Seed · Health Seed |

**Evidence (four independent strands):**

1. **Every one of the 120 filled slots resolves to a real `Items.GDA` id.** No value is
   out of range, in a field that was supposed to be floating-point geometry.
2. **The difficulty gradient is exact.** Green Hill holds Health Seeds, POW Candy, Prune
   Juice and Boxing Gloves. Act 2 holds the Zoah Shield in the Zoah area, the Voxai
   Teleporter in a Voxai interior, and the five Nocturne Relics one per chest — which is
   precisely how many the game asks you to collect.
3. **The first chest in the game is a lone Health Seed**, which is exactly what every
   playtest has reported finding in it, across every randomizer build.
4. **`jay_test`** — a developer area left in the retail archive — has five chests holding
   three Health Seeds each. Item id 0, three times over, is what a placeholder looks like.

**Why this was missed for a day.** Three mistakes compounded. The search looked at list
40002's `kind == 4` item *objects* and at `RandItems.GDA`, both of which are real things
that are not chests. The triple was dismissed as a position early on and never revisited.
And `are_write.read_list` only returns fields whose type is in `UNPACK`, which silently
hid the **vector3f at label 4** — the actual position — so the only float triple on
screen looked like the only candidate for one.

**The test that should have been run on day one:** 1,035 rings are scattered across the
world, and between them they share **exactly two distinct values** of the 40020/21/22
triple, `(0,0,0)` and `(-1,-1,-1)`. No coordinate field behaves that way. One line of
census would have shown the triple was a per-type payload, and the real position was
sitting unread at label 4 the whole time.

**How it was tested:** `randomize_chests` writes the slots in place (float32, nothing
resizes) and `world_randomizer_test.nds` rebuilt clean through every verification stage.
Reading the built ROM back shows Green Hill's first chest holding a Cure All Spray
instead of a Health Seed. **Awaiting the in-game check**, which is one chest away from
the start of a run.

**Corrected documentation:** README, `KNOWN_FORMATS.md`, `ROADMAP.md` and the
`randomize_pickups` docstring all claimed chest contents were in ARM9. They are not. The
earlier entry on `RandItems.GDA` stands on its own — those tables are real drop tables,
they are simply not what a chest reads.

**Also learned:** field **40013** on list-40002 objects is a plot-flag id, not a float.
Flag numbers rise monotonically with chapter order — Green Hill's objects sit at 42–59,
the last Nocturne interiors at 259–280 — which is the likeliest reason a player finishes
a run without ever meeting one of the 39 item objects. The three Voxai Teleporters in the
opening zone all share flag 308: one late-game object with three possible homes, not
three teleporters lying in Green Hill.

**Remaining uncertainty:** what the triple means for the other 40 placeable types. Doors
(type 37) mostly carry `(-1, 190, 0)` and signs (type 35) a single rising id, so both look
like references into tables that have not been identified. Chests and rings are solved;
the rest is unexamined.

---

## 2026-10-10 — A lone enemy is a story actor: squad size is the tag a spawn point lacks

**Investigated:** Why the Green Hill Marauder encounter in `world_randomizer_test.nds`
started with no enemy in it, stranding the run before Central City — the same symptom the
script-tag rule was supposed to have cured a day earlier.

**Discovered (confidence: high for the rule, medium for the mechanism):** the Marauder's
two spawn points in `a1_s1_ex.are` are `L_SQUADS` entries 40 and 41, both holding squad
**264 — a single Marauder Scout** — and **both carry `F_TAG == 0`**. The tag rule
therefore does not protect them, and the seed-1 shuffle moved squad 39 and squad 283 into
them, evicting the Marauder from the area entirely.

So `F_TAG != 0` is a *sufficient* marker of a script-driven spawn point, not a necessary
one. What does separate story actors from roaming trash is **squad size**. Of the 332 rows
in `squads.GDA`, 155 are actually placed in an area; **25 of those have exactly one
member**, and read as a cast list:

| | |
|---|---|
| tagged (21) | Shadow the Hedgehog ×3, Imperator Ix ×3, Shade, Procurator Shade, General Raxos, the Gentleman, Prefect Scylla ×2, Prefect Charyb ×2, Dragodon ×2, Colossal Worm, Kron Warrior, Nocturne Hastatus, Bomb Pawn, Swat Bot, Enraged Armadillo (the tutorial fight), Sentry Drone |
| untagged (4) | Raxos / the Gentleman / Scylla / Charyb again in `arena_act_*`, **and squad 264, the Green Hill Marauder** |

Roaming trash travels in threes and fours — the placed-squad size histogram is 1:25,
2:28, 3:52, 4:38. A solitary enemy is a set piece. Size is the signal that a missing tag
does not give.

**Evidence:** static read of `squads.GDA` columns 5–8 cross-referenced against the
`L_SQUADS` list of all 79 area files. Every single-member squad either carries a tag, or
is a named character that also appears tagged elsewhere, or is squad 264.

**How it was tested:** `randomize_placements` now returns `None` from `squad_band` for any
squad with fewer than two live members. Seed 1 / band 3 drops from 225 placement edits to
210, spawn points 40 and 41 are untouched, and no edit writes a single-member squad
anywhere. Rebuilt `world_randomizer_test.nds`; awaiting the playtest that walks back to
the Marauder.

**What this does *not* explain:** the mechanism. A shuffle always writes a valid squad id,
so an empty battle means the *script* that drives the encounter could not find what it
wanted — most likely it addresses the spawn by the instance id in field `40023` (63 and 64
here) and expects the Marauder specifically. That is a guess. The rule stands on the
census above, not on the mechanism.

**Remaining uncertainty:** squad 247 (Zoah Brute, 10 untagged placements across three
`a2_s4` areas) is genuine roaming trash that the size rule now freezes unnecessarily.
Accepted: one over-protected trash squad costs nothing, one stranded run costs the save.
Also unexamined: whether `F_TAG`'s larger values (701, 500, 300, 91 in `a1_s1_ex`) are
plot-flag ids rather than local handles. They are unique within an area, which fits a
handle; the 1,041-entry `.plo` flag registry has not been cross-referenced against them.

---

## 2026-10-10 — POW confirmed as the damage stat; the element-crash theory disproven

Two experiments, one confirming and one killing a theory of mine.

### 1. POW drives damage. Attack is accuracy. (confirmed in play)

The game never explains POW or Grit — a search of all **18,845** TLK entries finds stat
definitions only for Attack (*"determines how likely an attacker is to hit"*, strref
17017) and Speed. So what POW does had been an assumption since `enemy_scaling` was
written.

`profiles/pow_probe.json` settles it: Rock Salt, a battle consumable normally granting
POW +10, amplified to **POW +150** and sold for 1 ring in every shop. Used mid-battle,
basic-attack damage went **over 200 per hit**, and an attack still **missed**.

POW raises damage and does nothing for accuracy. The assumption was right.

This also resolves the reading of the move tier text. `combo.GDA` damage columns are a
percentage in half-percent units (`column x 2` matches the description for 110 of 110
moves), and **"225% of Attack damage" means 225% of a basic attack's damage** — not 225%
of the Attack stat, which would contradict Attack being accuracy. A POW move is a
multiple of a POW-driven basic attack.

`grt_probe.json` is built on the same pattern (Iron Tonic to GRT +150) and is untested.

### 2. The (element, status) pairing theory is dead

Yesterday's conclusion — that Focus Field crashed because wind + Vulnerable is a pairing
the shipped game never contains — was wrong. `profiles/focus_field_probe.json` tested it
directly by giving Focus Field **wind + Sluggish**, which is exactly how Triple Tornado
is authored. It **crashed again**, same element, different status.

What the follow-up ruled out:

* **No companion column.** Across all 155 moves, the only field every vanilla wind move
  shares and Focus Field lacks is the element itself.
* **Not the structure.** **Atomic Strike** is near-identical to Focus Field — 2
  participants converted to 1, `col44 = 3`, the same trailing `-1` slots in all three
  per-participant triplets — and works. Whirlwind is a 1-participant wind move with the
  same trailing `-1`s and is fine in vanilla, so those are not the issue either.
* **Not VFX.GDA**, at least not visibly: it is a flat 467-row effect registry with no
  per-move element key.

The only discriminator left is that Atomic Strike's element is **authored** and Focus
Field's was **added**. Whatever an elemental move requires therefore lives outside
`combo.GDA`, and has not been found. Finding it likely needs runtime debugging rather
than more table reading.

**The guard was redrawn around the evidence rather than the theory.** `pow_move` now
refuses to add an element to a move that ships without one, and still allows changing an
element a move already has. Metal Storm + earth remains the single known-good addition
and is explicitly documented as not generalisable. `force_element` overrides, with the
message telling the caller to test that specific move before playing a run on it.

**Remaining uncertainty:** why Metal Storm tolerates an added element and Focus Field
does not is unexplained, and the guard is deliberately conservative because of it — it
will refuse additions that would in fact have worked.

---

## 2026-10-10 — The ARE writer: placed loot and spawn points are editable in place

**Investigated:** How to edit what a chest holds and which enemy group spawns where, now
that both were located in the area files.

**Discovered / built (confidence: high — verified by rebuild and read-back; not yet run
in game):**

### Editing an ARE needs none of the GDA machinery

An area is GFF4 type `ARE` whose root holds several LIST|STRUCT fields, each a `uint32`
count followed by fixed-size structs laid out inline — the same shape as a GDA row array.
The two that matter:

| list label | holds | key field |
|---|---|---|
| **40002** | placed objects, as (kind, id) | 40008 kind, 40009 payload |
| **40003** | spawn points | **40005 squad id** |

Both edits are **in-place integer writes**. The value is a fixed-width int at a known
offset inside an inline array, so nothing resizes, no offsets move and no array has to be
relocated — unlike the creature-row cloning, which needed all three. `tools/build/are_write.py`
plus the `are_cell` op is the whole of it.

Adding or removing objects is deliberately not implemented: that would mean relocating a
list and repointing the root, and unlike a GDA there are several lists per file whose
relative order the engine may care about. Randomizing what is already placed needs no
growth.

### `randomize_chests` now edits the right table

The previous feature of that name edited `RandItems.GDA` and was renamed
**`randomize_drops`**, because the playtest disproved the assumption behind it: Health
Seed was removed from every early weighted tier and the first chest still produced one.
Those 22 tables feed something else — enemy drops being the obvious candidate — and what
a chest actually gives is the `kind == 4` object in the area's own list.

39 such placements exist across 17 areas. **24 are eligible**, using the same "ordinary
loot" rule as the other loot randomizers (sold in a shop, or dropped by a generic chest
tier). A wider rule was tried and rejected: admitting any named item with effect rows
pulled in the **Voxai Teleporter**, which is a key item, while excluding ordinary
consumables that happen to appear as quest rewards. Verified after the build — all three
Voxai Teleporter placements untouched.

### `randomize_placements` moves groups, banded by difficulty

Spawn points name a `squads.GDA` row. Shuffling them unbanded would simply drop a level-20
Gizoid Guardian into Green Hill, since a squad's stats travel with it, so squads trade
places only within a band — the highest level among a squad's members, floor-divided by
`band` (default 3). Squads containing a protected creature never move, so story fights
stay put.

Built at seed 1: **281 spawn points changed, zero band violations**, confirmed by
recomputing every moved squad's band from the vanilla tables.

**Remaining uncertainty:** neither has been run in game. For placements the thing to watch
is whether any spawn point is special in a way the squad id does not capture — a point the
plot expects to hold a particular group, for instance; the protected-creature filter
covers boss squads but not a scripted *location*. 14 of the 53 itemboxes still have no
kind-4 placement, so something else sources those.

---

## 2026-10-10 — A move element crashes the game when its status pairing is unprecedented

> **Superseded.** The pairing theory below was tested with a wind + Sluggish probe and
> **disproven** — Focus Field crashed again. See the correction entry above. The crash
> and the fix are real; the explanation was not.

**Investigated:** A hard crash reported in play. On `ultimate_lifeform.nds`, using
**Focus Field** for the first time froze the game and cost a chunk of progress. Metal
Storm and Atomic Strike, both altered by the same feature in the same build, are fine.

**Discovered (confidence: high for the pattern and the fix; the mechanism itself is
inferred):**

`combo.GDA` columns **27/28/29 are the status effect a move inflicts**, per damage tier,
as a `spells.GDA` row: `Spell_Stun`, `Spell_Sluggish`, `Spell_Vulnerable`,
`Spell_Weakened`, `Spell_Distracted`.

Vanilla pairs an element with a status **very sparingly**. Across all 155 moves the only
(element, status) combinations that ship are:

| element | status |
|---|---|
| fire (131072) | none |
| earth (524288) | none, or Stun |
| wind (1048576) | none, or Sluggish |
| electricity (2097152) | none |

The profile had given Shadow's moves elements, producing:

| row | move | element | status | precedent | result |
|---|---|---|---|---|---|
| 14 | Chaos Blast | fire | Weakened | **none** | untested |
| 15 | Atomic Strike | electricity | none | yes | works |
| 16 | Focus Field | wind | **Vulnerable** | **none** | **hard crash** |
| 17 | Metal Storm | earth | Stun | yes (Quake Punch) | works |

The two that work are exactly the two whose resulting configuration exists in the shipped
game; the one that crashed is one that does not. Chaos Blast is the same kind of
unprecedented pairing and should be assumed to crash too.

Everything else was ruled out along the way. The element *values* are all genuine —
wind 1048576 appears on Whirlwind, Triple Tornado and Tornado Kick. Participant count is
not it: Metal Storm went 3 -> 1 and Focus Field 2 -> 1, and Atomic Strike also went
2 -> 1. Focus Field is not a zero-damage support move (113/125/138). Column 44 is not an
element gate — elemental moves span every one of its values.

**Also learned: column 52 is not an "element flag".** `features.py` named it
`C_ELEMFLAG` and `pow_move` sets it to 1 whenever an element is applied. In vanilla **20
moves set it and only 6 of those are elemental**, while Blazing Tornado and Tornado Kick
carry an element with it at **0**. Its real meaning is unknown. It is still written,
because both moves confirmed working in play were built with it set and removing it would
introduce an untested variable, but the constant's name is now documented as a
mis-inference.

**Fixes applied:**

* `pow_move` refuses to add an element to a move whose status has no vanilla pairing with
  that element, naming the move, the status and the alternatives, overridable with
  `force_element`. Verified: Focus Field + wind is refused, Metal Storm + earth builds.
* `profiles/ultimate_lifeform.json` had the four offending cells removed (rows 14 and 16,
  columns 51 and 52) and was rebuilt. The previous profile is kept as
  `ultimate_lifeform.json.before-element-fix`. Shadow keeps all six moves solo-castable
  at the same costs; Atomic Strike and Metal Storm keep their elements.

**Remaining uncertainty:** *why* the combination crashes is not established — the
hypothesis is that the engine composes a status VFX with an elemental one and lacks a
case for the pairing, but that is inference from four data points, one of them a crash.
The guard is drawn around the evidence (what vanilla ships) rather than around a
mechanism. Whether Chaos Blast would have crashed is a prediction, not an observation.
An element could still be given to Focus Field by also changing its status to Sluggish,
which is the pairing wind already has — untested, and it changes what the move does.

---

## 2026-10-09 — Groundwork for character randomization: abilities, gates and the plot format

**Investigated:** What a character randomizer would have to respect to avoid softlocking
a run, i.e. where traversal gates state their requirement and what each character can do.

### 1. Obstacles do not carry a requirement; the object *type* is the requirement

Every interactable in the ARE object list has its requirement-shaped fields constant
across all instances of its type — `block` (type 1, 60 instances), `bounce` (2, 53),
`pressureplate` (4, 22), `WoodPile` (15), `turret` (23), `greenhillwinch` (40) all read
`40006=0, 40019=-1, 40026=-1, 40027=0` on every instance. Nothing varies per obstacle, so
"which ability opens this" is a property of the type, resolved in code.

`PlaceableStates.GDA` (196 rows) is animation id, walkmesh .tga and sound — not
requirements. So there is **no table mapping obstacle type to required ability**; it would
have to be established per type by experiment or ARM9 work.

### 2. movement.GDA — 11 abilities, 4 of them unused by the party

Rows: 0 Dash, 1 Smash, 2 Fly, 3 Jump, 4 Climb, 5 Invulnerable, 6 Stealth, 7 Teleport,
8 Wriggle, 9 Detect, 10 KSmash. Column 10 is `maxlevel` (3 for Dash/Smash/Fly/Invulnerable,
1 for the rest); columns 11-13 are the strrefs for the three tiers' names and descriptions.

**Jump, Wriggle, Detect and KSmash are on no character.** They exist as mechanics with
names and descriptions but nothing in the roster carries them.

### 3. The vanilla ability map

Slots are `creatures.GDA` 19/20/21; the level each unlocks at is the first non-zero row in
`Adv_<name>.GDA` columns 12/13/14.

| character | slot 1 | slot 2 | slot 3 |
|---|---|---|---|
| Sonic | Dash | — | — |
| Tails | Fly | — | — |
| Knuckles | Climb | Smash (L4) | Fly (L8) |
| Amy | Smash | Dash (L4) | — |
| Shadow | Dash | Teleport (L8) | — |
| Rouge | Fly | Stealth (L8) | — |
| Big | Invulnerable | — | — |
| Cream | Fly | — | — |
| Omega | Smash | Invulnerable (L4) | — |
| Shade | Stealth | Climb (L4) | Teleport (L8) |
| Eggman | — | — | — |

Coverage: Dash 3 characters, Smash 3, Fly 4, Climb 2, Invulnerable 2, Stealth 2,
Teleport 2. Eggman is the only party member with no traversal ability at all.

### 4. The softlock rule does not need a gate map

Worth stating because it changes the scope of the work: a character randomizer does
**not** need to know which obstacle demands which ability. It needs the recruitment order,
and then this invariant:

> For every prefix of the recruitment order, the set of abilities the party can field
> must be a superset of the vanilla set at that point.

Any gate passable in vanilla at that moment is then passable in the randomized run, by
construction, whatever the gate happens to require. Ability *level* needs the same
treatment, since Dash III opens things Dash I does not.

So the remaining input is recruitment order, not a gate survey.

### 5. The plot format is readable, and plot flags are named

`party.GDA` is only the slot-to-creature mapping (13 rows) and carries no order.
Recruitment is plot-driven, and the plot layer turns out to be tractable:

* `plots.GDA` maps 102 rows onto **95 distinct `.plo` files**, named by chapter —
  `plt_ch1_main.plo`, `plt_ch3_shadow.plo`, `plt_a1_amy.plo` — plus `cod_*` (31 codex
  entries), `fp_*` / `fpa2_*` (per-character, one each, act 1 and act 2) and `gbl_*`.
* A `.plo` is **GFF4 with type `PLTS`**, three templates: root holds a list of 32-byte
  entries (T1) and 52-byte entries (T2).
* **Field 13002 is a human-readable flag name.** `plt_gbl_inparty.plo` contains exactly
  `SONIC_IN_PARTY`, `TAILS_IN_PARTY`, `KNUCKLES_IN_PARTY`, `AMY_IN_PARTY`,
  `ROUGE_IN_PARTY`, `SHADOW_IN_PARTY`, `BIG_IN_PARTY`, `CREAM_IN_PARTY`,
  `OMEGA_IN_PARTY`, `EGGMAN_IN_PARTY`, `SHADE_IN_PARTY`, `PARTY_1_ACTIVE`.
  `plt_ch3_shadow.plo` names its own chain: `CH3_SHADOW`, `CH3_SHADOW_MET`,
  `SHADOW_SPOTTED`, `SHADOW_FIGHT_CH3`, `CH3_SHADOW_ESCAPED`, `AVOID_SHADOW_FIGHT`.
* Field 13009 is a plot category (`plot_core`), 13007 a 32-hex GUID.

`plotflags.GDA` has 657 rows with a `plotid` column, which is presumably the global flag
registry these names resolve against.

**Remaining uncertainty:** which plot *action* sets a flag, and therefore where each
character actually joins, is not decoded — that is inside the T1/T2 entry structure
(uint8 fields 13011-13014 and a nested list at 13000). That is the next piece, and it is
also what a recruitment randomizer would have to edit. Decoding it would give the
recruitment order the softlock rule needs, and the hook for reordering recruitment itself.


### 6. The four unassigned abilities look engine-side, not unlockable

Jump, Wriggle, Detect and KSmash are carried by **nobody at all** — not a party member,
not an enemy, in any of the 128 creature rows.

They also have **no description strings**. Every player-facing ability carries one (Dash:
"Provides the ability to run through loops and other speed areas."); these four repeat
their bare name in all three tier slots. A description exists because the ability is
drawn on the character sheet, so having none fits a verb the engine grants implicitly
rather than something a character unlocks. Jump having real tier-1 parameters
(45 / 45 / 1.0, the same distance-height-duration shape as Dash's 800 and Fly's
60 / 80 / 0.75) while belonging to no one supports the same reading: every character can
hop a small ledge.

The **strref numbering shows the authoring order**, which is more informative than the
table order:

| strref | ability | table row |
|---|---|---|
| 16954 | Dash | 0 |
| 16955 | Smash | 1 |
| **16956** | **KSmash** | **10** |
| 16957 | Fly | 2 |
| 16958 | Jump | 3 |
| 16959 | Climb | 4 |
| 16960 | Invulnerable | 5 |
| 16961 | Stealth | 6 |
| 20201 / 20202 / 20203 | Teleport / **Wriggle** / **Detect** | 7 / 8 / 9 |

Two things follow. **KSmash was authored immediately after Smash** and only later moved
to the end of the table, so it is a Smash variant — "K" most plausibly Knuckles, whose
smash is the one the tutorial teaches. And **Wriggle and Detect were added later**, in a
block with Teleport, rather than belonging to the original eight.

Confidence: high that nothing carries them and that they lack descriptions (both read
directly); the readings of what KSmash, Wriggle and Detect *do* are inference from
authoring order and remain unconfirmed.

---

## 2026-10-09 — Appended creature rows work in game; innate abilities and move damage decoded

**Investigated:** Whether the engine tolerates a `creatures.GDA` index past the vanilla
127, and what else a cloned row brings with it.

### 1. Appending creature rows is CONFIRMED IN GAME

`profiles/clone_probe.json` built a 129-row `creatures.GDA` and pointed squad 40 (the
first Wild Boar group in Green Hill) at new row 128 — a Gizoid's model, portrait and
robot class carrying Wild Boar's level-2 stats.

In play: the creature appeared correctly in the **overworld and in the battle**, fought
normally over 7 rounds, and the victory screen read **"First Fight With: Gizoid"**, so the
engine resolved the new row's name as well as its model. Damage taken was 61 across the
fight, consistent with the transplanted level-2 stats rather than the donor's.

`creatures.GDA` had carried exactly 128 rows in every build until now and many tables
index into it, so this was the gate for the whole transplant idea. It is open.

### 2. creatures.GDA columns 51 and 52 are innate ability slots

The probe's Gizoid **regenerated and countered** despite its POW move slots being blanked,
which located the passives: two columns holding ids in the status/ability range of
`Items.GDA`.

Observed values across the roster include 219 `Evading`, 220 `Phase`, 221/225/229
`Self Repair`, 231/253/282/283/285 `Immunity`, 232 `Lock On!`, 233 `Shields Up!`, 234
`Charging!`, 280 `Energize!`, 255-257 the elemental Shields, plus several unnamed ids
(223, 224, 230, 277, 278, 279) that behave the same way — code-driven, like the unique
Chao effects, and keyed by id.

Examples: Gizoid 278 + 224; Wild Boar 224; Marauder Scout 220 (`Phase`); Swat Bot 225
(`Self Repair`); Imperator Ix 285 (`Immunity`) + 230.

These ride along with a clone, which is desirable — it is what makes a transplant feel
like the donor rather than a repaint.

### 3. combo.GDA damage columns are a multiplier, not HP

Columns 12/13/14 do **not** hold hit points. Evidence:

* They do not scale with level at all. Level-2 moves read 400, level-3 moves 50-150,
  level-18 moves cluster at 75-175.
* The same move reads the same value on creatures of very different power: Quake Punch is
  75 on the level-14 Gizoid (POW 40) **and** on the level-18 Gizoid Mk. II (POW 65).
* Party moves share the range — Sonic's starting Axe Kick is 75/88/100, Whirlwind
  50/55/63 — and plainly do not deal 75-100 raw damage against 45 HP enemies in a fight
  that runs seven rounds.

So the column is a per-move power multiplier and real damage derives from the attacker's
POW. **A transplanted move therefore needs no damage adjustment**: giving the clone the
victim's POW already lands it at the local tier. The first draft scaled the column by the
POW ratio as well, which double-counted — and reasoned about "75 damage versus Sonic's 33
HP" as if the number were HP, which it is not. `damage_scale` remains as a deliberate
tuning knob, default 1.0.

### 4. `randomize_encounters` gained a transplant mode

`mode: "transplant"` clones each used enemy species into a new `creatures.GDA` row with
the donor's identity, class, innate abilities and entry animation plus the victim's stat
columns, and clones the donor's moves into new `combo.GDA` rows.

Each cloned move's **owner (combo column 2) is repointed at the new creature** — that
column is the owning creature id, and a move whose owner does not match shows as
"Unavailable", the same trap that broke Shadow's POW moves during the character swap.

Only species that actually appear in a squad are cloned. Built at seed 1:
`creatures.GDA` 128 -> 188, `combo.GDA` 155 -> 230, every original row byte-identical,
every cloned move owned by its own creature. Squad 7 becomes three Gizoid Mk. IIs at
level 3 / 30 HP / POW 6 carrying all four Gizoid moves.

`mode: "reskin"` stays the default, since it is the one proven in play.

**Remaining uncertainty:** the transplant has not been run in game. The specific thing to
watch is whether a high-multiplier move on a low-POW creature is survivable — Super Shot
is a 300 multiplier and now sits on a level-2 Guardian Pawn with POW 8. If that hurts more
than it should, `damage_scale` is the knob, and the multiplier reading above is the first
thing to re-examine.

---

## 2026-10-09 — Cloning GDA rows: appending past the end of creatures.GDA

**Investigated:** How to append a row to `creatures.GDA`, which `append_row` refuses, so
that a randomized enemy can be a real transplanted creature rather than a reskin.

**Discovered / built (confidence: high for the writer, which round-trips through the
reader and builds a verified ROM; the in-game half is untested):**

`creatures.GDA` fails **both** of `append_row`'s preconditions at once:

1. **Out-of-line strings.** Creature rows carry nine `asciistring` cells (portrait and
   palette resources). `append_row` requires every cell to be a fixed-size inline integer.
2. **The row array is not last in the file.** 4,443 bytes of string pool follow it, so
   growing the array in place would shift every string and invalidate every offset.

Both dissolve if the new row is a **clone** rather than a construction:

* A string cell *is* four inline bytes — an offset relative to `dataOffset`. A copy of an
  existing row can keep the source's offsets verbatim, because it points at the same
  portraits. **No new string data is written and no re-serializer is needed.** The price
  is that a clone cannot be given new text; overriding a string cell is refused outright
  rather than half-supported.
* The array is rewritten one row longer at the **end** of the file and the root's list
  offset repointed at the copy. Nothing that already exists moves, so every string offset
  stays valid. The old array becomes dead space. Same append-and-repoint strategy
  `gff4_write.append_clone` uses for widget lists.

**Batching matters.** Each relocation copies the whole array, and `creatures.GDA` is
~30 KB, so cloning row-by-row is quadratic: five separate calls would add ~150 KB, and the
ROM has only ~3.8 MB of headroom before it outgrows its declared cartridge size. One
batched call adds 30,861 bytes for five clones versus 29,933 for one.

**API:** `gda_write.append_rows_clone(raw, [(source_index, overrides), ...])`, the
`append_row_clone` single-row wrapper, and the `gda_clone_rows` builder op. Overrides are
keyed by column index or name like `gda_cell`; note that JSON object keys arrive as
strings, so numeric keys are coerced. The writer verifies every clone through the reader:
each non-overridden, non-string field must equal its source, and each override must read
back.

**Demonstrated:** cloning the Gizoid (row 31) with Wild Boar's stat columns produces a
row with the Gizoid's model (appearance 31), portrait, robot class and move slots, and the
Boar's 45 HP / 8 POW / level 2. That is the "scaled-down Gizoid" shape the whole exercise
is for.

**`profiles/clone_probe.json`** builds a 129-row `creatures.GDA` and points squad 40 — a
Wild Boar group in the opening Green Hill area — at the new row.

Its POW moves are deliberately blanked. The Gizoid's first move is Quake Punch at **75
damage** and Sonic starts the game on 33 HP, so a transplanted move would one-shot the
party before the probe told us anything. The probe tests one thing only: whether the
engine tolerates a creature index past the vanilla 127.

**Remaining uncertainty — this is the whole point of the probe:** `creatures.GDA` has
carried exactly 128 rows in every build so far, and a great many tables index into it.
Nothing guarantees the engine does not assume that count somewhere. If the probe loads and
fights normally, transplanted enemies are viable; if it crashes or renders wrong, the
fallback is repurposing the handful of genuinely unused rows, which is far more limited
(38 rows are unreferenced by any squad but nearly all are scripted NPCs).

Moves are the next piece and need the same treatment applied to `combo.GDA`, with damage
rescaled on the clone, because combo rows are shared between creatures.

---

## 2026-10-08 — Chest loot and quest rewards decoded

**Investigated:** Where a chest's contents and a quest's reward are stored, after a
playtest confirmed neither randomized.

**Discovered (confidence: high — read from the tables, and one row matches an observed
in-game reward exactly):**

### Chests carry no loot of their own

A chest is an `itembox` placeable: object **type 6** in the ARE object list (root list
label 40001), **53 of them across the 79 area files**. The object struct holds a name, a
facing, a type, a position and an instance index — and **no item id**. Field 40019 is -1
on 52 of the 53, 40026 is -1 on all, 40027 is 0 on all.

(Other placeable types in the same list, for reference: 0 `ring` x726, 37 `placeablearrow`
x176, 32 `chaoegg` x100, 1 `block` x60, 2 `bounce` x53, 4 `pressureplate` x22, 23 `turret`
x6, 15 `WoodPile`.)

### RandItems.GDA — 22 weighted drop tables

17 columns: id, then **eight (weight, item) pairs**. Weights are percentages and sum to
100 on 19 of the 22 rows, which is what confirms the pairing.

* **Rows 1-10** are the escalating generic chest tiers — row 1 is `25% Health Seed, 25%
  POW Candy, 25% Revival Ring, 25% Antidote`; row 8 adds Med Emitter and Refresher Wave
  at 5% each.
* **Rows 11-21** are quest and special drops, mostly `95% <quest token>, 5% <gear>`.

Randomizing the item columns changes what every chest gives without needing to know which
chest reads which table — which is fortunate, because that mapping is still unknown.

### rewards.GDA — 70 quest and event rewards

Columns: 0 id, **1 a readable label**, 4 gold, 5 XP, **6-11 up to six item ids**. The
labels are plain English and make this table self-documenting: `Wasp Quest`,
`Factory Quest`, `Woodsman_Reward`, `Knuckles_get_Reward`, `Eggman_parts`,
`All_Eggman_parts`, `Boy escorted`, `GenericSmall`, `GenericLarge`.

**Row 7 `Woodsman_Reward` is 50 XP and item 3, POW Candy** — exactly what the
wood-chopping mission paid in the playtest screenshot, which independently confirms the
column reading.

### Protecting quest items: "has a name" is not the rule

The nameless ids (259-266, 270-275) are obvious quest tokens, but **Eggman Device (237)
and Pattern Generator (238) are named** and equally critical — the first draft of
`randomize_rewards` swapped the Eggman Device straight out of the `Eggman_parts` reward
that needs it.

The rule that holds: an item is ordinary loot if **the game hands it out through an
ordinary channel** — sold in one of the five stores, or dropped by a generic chest tier
(RandItems rows 1-10). That is **62 items**. Quest items appear only in specific reward
rows and special drop tables, so they fall outside it and never move. Verified: with the
rule in place, 48 chest entries and 17 reward entries changed, no non-ordinary entry
moved, every weight column untouched, and `Eggman_parts` / `All_Eggman_parts` still hand
over their parts.

**Remaining uncertainty:** which `RandItems.GDA` row a given chest reads is still unknown
— the link is not in the ARE object, so it is presumably by area or chapter, or driven
from a plot file. Not needed to randomize loot, but it would be needed to make a specific
chest hold a specific item.

---

## 2026-10-08 — Second randomizer playtest: appearance sharing, and `type` is a class

**Investigated:** Two reports from the second run of `profiles/full_randomizer.json` — a
squad showing one creature in the overworld and a different one in the battle, and an
enemy using its own move with a block pattern that did not match it.

### 1. Appearance ids are shared, so an old→new map is last-writer-wins

**19 appearance ids are used by more than one enemy creature**, and id 26 (`BSL_AA`) by
five: Marauder Scout, Marauder Vet Scout, Nocturnus Velite and two more. `randomize_encounters`
repointed each squad's overworld model through a map keyed by the *old* appearance, so for
any shared id the last creature processed won, and the squad's overworld model followed a
different creature than the one that loaded in the battle. Reported as a wild boar outside
and a Gizoid inside.

**`squads.GDA` column 4 is also not simply the members' model.** Of 163 squads with live
members, **97 match the first member's appearance and 66 deliberately differ** — several
point at ids well outside the range any creature uses, i.e. overworld-only models. Repointing
all of them was wrong independently of the map bug.

Now: the squad model is repointed only where vanilla had it tracking the first member, and
then from that member's own new appearance. Verified — 82 squads repointed, every tracking
squad agrees with its member, every non-tracking squad untouched.

### 2. `creatures.GDA` column 32 is a creature class, not a cosmetic tag

Earlier notes called it organic/robot and the remap copied it as part of "identity". It is
a three-way class with mechanical weight:

| value | count | members |
|---|---|---|
| 0 | 78 | beasts — Wild Boar, Marauder Scout, Imperator Ix |
| 1 | **5** | insects — Wasp Swarm x2, Queen Wasp, Giant Millipede, Colossal Worm |
| 2 | 31 | robots — Swat Bot, Laser Drone, Gizoid |

Copying it moved Marauder Scout from beast to insect. The playtest then reported that
enemy using its own Stasis Grenade (`combo.GDA` row 73) with a block pattern far more
complex than that move's. The move itself was *not* changed — the creature's move slots
still read `[73, -1, -1, -1, -1, -1]` and **`combo.GDA` is untouched by the feature** — so
the only candidates were class and appearance.

Class is now left alone: a reskin changes looks, not mechanics. Whether class drives the
block pattern, elemental weakness, or both is **not confirmed** — the correlation is strong
and the conservative fix removes the variable, but a controlled experiment has not been run.

Also noted, unconfirmed: `appearances.GDA` columns 11 and 12 are a small index (16 and 14
distinct values, range -1..29, mostly -1) attached to the model. They are *not* combo rows
despite the numeric overlap — those indices only ever reach party moves like Flash Bang,
which makes no sense for an enemy.

### 3. What a real scaled-down enemy needs

Reskinning cannot give a transplanted enemy its own moves, which is the difference between
a costume and a randomizer. That needs cloned creature rows. Two facts settle the approach:

* **`creatures.GDA`'s row array is not last in the file** — 4,443 bytes of string pool
  follow it — so `append_row`'s "nothing may follow" precondition fails regardless of the
  string-cell problem. Appending must relocate the array to EOF and repoint, the same
  strategy `gff4_write.py` already uses for GENERIC lists.
* **A cloned row needs no new string data.** Its nine string cells are 4-byte offsets, and a
  clone can reuse the donor's offsets verbatim, since it points at the same portraits. So no
  full re-serializer is required after all.

Repurposing spare rows instead is not viable: 38 creature rows are referenced by no squad,
but nearly all are scripted NPCs (Vector appears six times, plus Shop Keeper, Boy, Dad),
and overwriting them would break dialogue scenes.

---

## 2026-10-08 — Three bugs the first randomizer playtest found

**Investigated:** The first in-game test of `profiles/full_randomizer.json`, which produced
a launch warning, a hung battle, and an item that looked untouched.

### 1. A grown ROM must update the device capacity byte

Header **0x14** is the cartridge size as a shift: the chip holds `128 KiB << cap`. Vanilla
ships `cap = 0x0A` (128 MiB) with the image exactly that size and `total_used_rom_size`
130,414,400 — about **3.8 MB of headroom**. Appending TLK strings for randomized item
descriptions crossed it: the build reached 134,444,352 bytes, 226 KB over, while still
declaring 128 MiB.

DeSmuME 0.9.11 reports *"The ROM header is invalid. The device size has been increased to
allow for the provided file size"* and plays on, so this is not fatal — but it warns on
every launch and real hardware is entitled to refuse. `rom_build.build()` now raises the
byte until the image fits (and recomputes the header CRC, which it already did). The file
is **not** padded up to the new capacity; the declared chip size may legitimately exceed
the image, and padding would double the file for nothing.

Confidence: high — read from the header, reproduced and fixed, and the warning's own text
names the cause.

### 2. An appearance with no model black-screens the battle

`randomize_encounters` repoints a creature's appearance id (`creatures.GDA` column 14) and
the squad's overworld model (`squads.GDA` column 4). Both index **`appearances.GDA`**, 222
rows whose column 3 is the model prefix (`ArmBoar_AB`, `BuzWasN_AB`, `GZD_AA`).

**Three of those rows carry no model name at all: ids 0, 4 and 72.** Exactly three creature
rows point at one — 75, 77 and 116, the playable-character duel variants, all on appearance
4 — because party models load through a different path than enemy ones, leaving their
appearance row an empty shell.

Handing that appearance to an ordinary enemy makes the battle try to load a model that does
not exist. Observed: the Marauder ambush showed bees in the overworld and then **black-screened
on battle entry and never started**. Other remapped fights in the same run (the armadillo,
the fleeing drone) were fine, which is what made it look like "scripted fights break" rather
than "one appearance is empty".

Fixed by excluding every creature whose appearance row has no model, as donor *and* as
victim. After the fix: 64 creatures remapped, none model-less, no squad repointed to one.

**This also corrects a claim made earlier the same day** — that an identity remap "cannot
break a scripted fight" because stats, moves, squad and trigger all stay put. The reasoning
was about the right things and ignored that the model is loaded too. Battles that play a
creature-specific animation remain an uncharacterised risk.

Confidence: high — the failing creature, its appearance id and that row's empty model field
were all read directly, and the fix was verified across the whole table.

### 3. An item's .ITM file is named by Items.GDA, not by its id

`item<id>.itm` holds for **213 of 230** items and is wrong for the other **17**. The real
resource is `Items.GDA` column 5, which `modbuild.items()` already used and the feature
layer did not:

| item | id | actual file |
|---|---|---|
| Health Seed | 0 | `item1.itm` |
| Bug Spray | 1 | `item2.itm` |
| Immunity, and 4 other ids | 231, 253, 282, 283, 285 | `item12.itm` |
| Fire / Water / Lightning / Air Shield | 251, 252, 256, 257 | `item186-189.itm` |

Assuming the convention does not merely skip those items — it edits **a different item's**
table while writing the description to the original. In the playtest build this left Health
Seed apparently untouched (its own `item0.itm` has no effect rows) while its real table was
re-rolled under Bug Spray's name, and Bug Spray's description described someone else's
effects. `custom_item` and `custom_chao` carried the same assumption; no shipped profile
referenced an affected id, so nothing already built was wrong.

Two further consequences, both of which surfaced as build aborts rather than silent damage:

* **Several ids share one table** (five point at `item12.itm`), so work must be grouped by
  resource, not by id — otherwise the same table is re-rolled repeatedly, each time
  computing from the original values, and the second write collides.
* **The four elemental Shields share their tables with Chao tiers** (`item186-189.itm`), so
  the `randomize_items` / `randomize_chao` split must exclude by resource as well.
* **Items.GDA spells filenames in mixed case** (`item1.itm` but `Item130.itm`), so grouping
  keys must be lowercased or one table groups as two.

Confidence: high — counted across the whole table and verified by rebuild; Health Seed now
reads `HEAL 50 -> 35` with the description `"Restores 35 HP."`.

**Remaining uncertainty:** chest contents and quest rewards are still undecoded, so neither
randomizes; the first chest yielding a Health Seed and the wood-chopping reward were both
vanilla, as expected. Whether a remapped enemy's *moves* matter is still unobserved — the
reskinned Nocturnus died before acting.

---

## 2026-10-08 — Correction: `enemy_scaling` was a two-column bug, not an ARM9 one

**Supersedes the conclusion of the entry below** ("`enemy_scaling` inflates the HP maximum
but not what enemies spawn with"). The symptom described there was real and the
measurements were right; the cause was not. No ARM9 work is needed.

**Discovered (confidence: high — verified by rebuild and read-back):**

`creatures.GDA` stores HP **twice**:

| column | role |
|---|---|
| **2** (unnamed) | the HP a creature actually spawns with |
| **7** (`health`) | the maximum its HP bar is drawn against |

They are equal in **all 128 vanilla rows**. No other stat is duplicated this way — a
duplicate-column sweep across `speed`, `attack`, `defense`, `power`, `grit` and `luck`
returns nothing, so HP is the single exception.

`enemy_scaling` wrote only column 7. That raised every enemy's ceiling while leaving it
spawning with vanilla HP, which is exactly what was observed: Velites at 90/122, Hastatus
at 150/202, and Imperator Ix spawning at 350 and then being healed *past* his vanilla
value to 377 against a 525 ceiling. Ix exceeding 350 is the cleanest single proof, since
it is impossible under a 350 maximum and needs no bar measurement.

**Why the earlier entry reached the wrong conclusion:** the elimination sweep searched for
a *health-named* column hash and for HP in other files, and column 2 is unnamed in
`research/phase0/gda_columns.tsv`, so it was never a candidate. Searching by name rather
than by value is the mistake — the column was found immediately by asking which columns
in the scaled ROM still held the vanilla HP value. The eliminations in that entry remain
valid and useful (ARE encounter layer, save file, language HERFs); only the conclusion
drawn from them was wrong.

**POW and DEF were always correct.** They have no second column, so the Lord Ix fight
fought on the pre-fix build did have enemies dealing scaled damage (Ix 45 -> 61) with
vanilla HP pools.

**Fix:** `enemy_scaling` now drives both columns from one rate (`CR_HP_SPAWN = 2` in
features.py). Rebuilt `ultimate_lifeform_scaled.nds` and read back: Velite 122/122,
Hastatus 202/202, Ix 525/525, Praetorian 756/756; zero rows desynced across the table.

**Remaining uncertainty:** not yet observed in play after the fix. The general lesson is
worth carrying: a GDA stat may be stored in more than one column, and a feature that
writes one of a matched pair produces a *partly* working mod, which is harder to notice
than one that fails outright. Any future stat feature should sweep for duplicate columns
before shipping.

---

## 2026-10-08 — `enemy_scaling` inflates the HP maximum but not what enemies spawn with

> **Superseded** by the correction entry above: the cause is a second, unnamed HP column
> in `creatures.GDA` (column 2), not ARM9. The measurements and the eliminations below
> still hold; the conclusion does not.

**Investigated:** A player report that enemies in the Lord Ix sequence "spawned in with
missing health" on `ultimate_lifeform_scaled.nds`. Four identical enemies, each reading
90 HP, each with a visibly partial bar, while all four party bars were solid.

**Method:** Measured the HP bars off the screenshot directly, using the party's full-HP
bars as the control for the bar geometry (both bars are an 83 px skewed track; a full bar
is 75 px of bright red between a 3 px left bevel and a 5 px right bevel). The enemy bars
carried 54 px of bright red, i.e. **0.72 of full**. Then eliminated every data-side
source of the number by reading the ROM.

**Discovered (confidence: high):**

The enemies are **Nocturnus Velite** (`creatures.GDA` rows 108 and 118, level 7), spawned
as **squad 67** — the only all-Velite four-member squad in the game, and placed in
`a1_s6_ex.are` alongside squads 66, 82 and 191, which are the three Imperator Ix squads.
That identification is independent of the HP numbers and fixes the area.

| | vanilla | scaled profile |
|---|---|---|
| Velite HP (`creatures.GDA` col 7) | 90 | 122 |

Observed in play: **current 90, max 122.** 90/122 = 0.738 predicts 55 px of bright red;
54 px was measured. The displayed number is the current HP and it is exactly the vanilla
value, while the bar's denominator is exactly our scaled value. The deficit ratio
122/90 = 1.355 is precisely the feature's own level-7 multiplier (1 + 0.05x7 = 1.35).

**So the UI reads the patched table for the maximum, and something else — which our edit
never reaches — initialises the current HP.** Every data-side candidate was eliminated:

- **`.are` placement data carries no HP.** The encounter layer is root list label 40003,
  a list of the 48-byte template whose fields are: name string, position (vector3f at
  offset 0), facing (float32), **squad id (sint32, label 40005)**, a tag (40006), a
  waypoint list (40007, vector3f list — patrol paths), and an instance index (40023).
  There is no stat block and no HP field in it. Found the Velite/Ix area by scanning all
  79 ARE files for squad ids 67/68 in that field.
- **`creatures.GDA` is the only table in the game with a real health column.** Scanning
  every GDA in `test.herf` for the `health` column hash (1212918477) returns three tables:
  `creatures.GDA`, `statsinfocreature.GDA` and `StatRedirect.GDA`. The latter two hold
  strrefs (20000-range) and field indices respectively — they are **stat-screen layout**
  tables, not stat values. `statsinfosquad.GDA` is the same kind of layout table.
- **The save is not carrying stale values.** `ultimate_lifeform_scaled.dsv` is
  byte-for-byte identical to `ultimate_lifeform.dsv` (no save had been made since
  switching builds), and the whole 64 KB image contains only 11 occurrences of the byte
  90 and no cluster of four.
- **The language HERFs hold no creature data.** `test_e.herf` etc. are real HERFs
  (magic 0x00F1A5C0, 42 entries) but contain zero `GFF V4.0` or `GDA ` signatures, so
  there is no second `creatures.GDA` for the game to prefer.

**Consequence for the feature:** `enemy_scaling` as built is **not doing what the profile
says**. It raises the maximum that the bar is drawn against while enemies continue to
spawn with vanilla HP, so the practical effect is cosmetic at best. Whether the POW and
DEF columns are read by the same unscaled path is untested but likely, in which case the
feature changes nothing about difficulty at all. Its `confirmed` marker was `'build'` —
statically verified, never observed — and this is exactly the failure mode that marker
exists to warn about.

**How it was tested:** Static only. The measurement is from a single screenshot, and the
elimination is from reading the EU ROM, the two battery saves, and all 79 ARE files.

**Remaining uncertainty:** Where the current HP actually comes from is still unknown. It
is not in any file we can read, so it is computed in ARM9 at squad construction time. This
is the same wall as the runtime-scaling hunt in the entry below, and it now blocks
*static* scaling too, not just party-relative scaling — which raises the value of the
melonDS GDB session, since one breakpoint on the enemy stat load would answer both. Also
unknown: whether POW/DEF behave like HP here, and what `squads.GDA` column 2 is (a float
per squad, 20.0-300.0, 80.0 for squad 67; its column-name hash 2580217947 survived a
dictionary attack over several thousand candidates, and it is not a straight HP
percentage — 80% of neither 90 nor 122 gives any observed number).

---

## 2026-10-08 — Static hunt for a runtime-scaling hook: where it stops, and why

**Investigated:** A hook point for scaling enemy stats against the **party's** level at
runtime. Motivation, from the user: static scaling helps a first playthrough (350 vs 525 HP
is ~3 extra turns) but is pointless on NG+ at level 20, where both die in one turn. Only
reactive scaling addresses that.

**Built:** `tools/recon/callgraph.py` — decodes every THUMB `BL` in ARM9 into a
target -> callers map. **4409 distinct targets, and it is the only way to ask "what calls
this?" in this binary.**

**Three properties of this ARM9 that defeat the usual static approaches:**

1. **Not compressed** — the entry point disassembles as ordinary ARM, so code and literal
   pools are directly readable. (Good news; it was the first thing suspected.)
2. **THUMB with PC-relative literals** — a 32-bit address appears only inside a literal
   pool, never in an instruction. Searching for a function or table address and getting
   **zero** hits means "loaded PC-relative", not "unused". This is what made
   `0x020BE944` look unreferenced.
3. **Resource loading is table-driven** — `creatures.GDA`, bare `creatures`, and the
   archive's DJB2 hash of either are **all absent** from ARM9. So GDA files are not
   opened by name or hash in code; something maps indices to names (`2DA.GDA` is the
   obvious candidate). There is therefore no "load creatures.GDA" call site to hook.

**Followed and rejected:** the character sheet's stat path. Each UI stat block calls
`0x020BC2FC` (13 callers) with the stat id in r2, which in turn calls `0x020083D0`
(235 callers). The latter is a general utility, not a stat accessor — too widely used to
hook without hitting everything.

**Conclusion: static analysis is exhausted for this hook.** What remains needs a live
DeSmuME session — break on a combat encounter starting, watch which code reads the
creature stats into the combat struct, and read back the party level's RAM address at
that moment. The call graph then turns that one observed address into its callers, which
is exactly the step that was impossible before.

**Not blocked on capability.** `modbuild.py` gained an `arm9_patch` op (with a required
expected-bytes assertion) and it is proven: one byte at `0x020BE668` repointed a stat row,
confirmed in game. There are 1186 bytes of code cave, largest run 274. The hook address
is the only missing piece.

---

## 2026-10-07 — Why POW and GRT are not displayed: seven unrolled blocks, two never written

**Investigated:** What it would take to show the two hidden stats (POW = damage,
GRT = armor) on the character sheet.

**Two earlier claims corrected.**

1. `0x020BE944` was recorded as "the stat list, a hardcoded 7-pointer array". It is an
   array of **7 widget-name strings** (`CLevelV CHPV CFPV CSPV CATV CDEV CLUV`), and it
   is not a standalone array at all — it is a **literal pool embedded inside a THUMB
   function**. That is why nothing in the binary references its address: THUMB loads
   each entry with a PC-relative `LDR`, so no absolute address appears anywhere. A
   reference search returning *zero* hits was the clue, not a dead end.
2. The ARM9 is **not compressed** — the entry point at `0x02000800` disassembles as
   ordinary ARM (`mov ip, #0x4000000; str ip, [ip, #0x208]`), so literal pools and code
   are readable directly.

**Discovered (confidence: high — read from the disassembly):** the stat rows are built
by **seven identical 110-byte blocks**, exactly 110 bytes apart, each loading one widget
name and ending in `movs r2, #<stat id>` before the call that fills the value:

| widget | `movs r2` | stat | at |
|---|---|---|---|
| CLevelV | 61 | level | `0x020BE65C` |
| CHPV | 0 | HP | `0x020BE6CA` |
| CFPV | 28 | PP | `0x020BE738` |
| CSPV | 21 | SPD | `0x020BE7A6` |
| CATV | 22 | ATK | `0x020BE814` |
| CDEV | 23 | DEF | `0x020BE882` |
| CLUV | 27 | LCK | `0x020BE8F0` |

**The numbering is the same one item effects use** — 21 SPD, 22 ATK, 23 DEF, 27 LCK all
match `SData1` in the `.ITM` tables exactly. **25 (POW) and 26 (GRT) are valid ids in
that same space; no block was ever written for them.** The display routine takes the
stat id as a parameter and is not specialized per stat, so the machinery to show them
already exists and is simply never asked.

Blocks differ only in: the widget-name literal, the `movs r2` immediate, and their
stack slots (each block uses 0xC more than the previous).

**Minimal experiment built — `build/statprobe_pow.nds`:** one byte at file offset
`0xC2668` (`0x020BE668`), changing CLevelV's `movs r2, #61` to `#25`, so the Level row
should display POW instead. `3D 22` -> `19 22`. If the row shows a plausible damage
value, the entire theory is confirmed: the stat id drives the display, the ids are
shared with items, and POW/GRT are reachable. Untested in game.

**CONFIRMED IN GAME (2026-10-07):** the probe works. The Level row stopped reporting the
character level (8) and reported **24** instead — a value in POW's range, not the level's.
The stat id in `movs r2` therefore drives which stat the row displays, and **25 is accepted
and rendered**, so POW is reachable by the existing display routine.

Caveat on the exact number: 24 was not predicted precisely. The probe is built from vanilla
(base POW 20 at level 8, +1 from the equipped Boxing Gloves = 21), but the save loaded into
it was made under a modded build with a different POW curve, and it is not established
whether the sheet recomputes stats from the progression table or reads them from the save.
The qualitative result — the row changed stat, and 25 renders — is unambiguous; the
arithmetic is not reconciled. A fresh game in the probe ROM would settle it.

**Remaining work now that the probe has succeeded:** two more 110-byte blocks (220 bytes; the
largest code cave is 274, total 1186 — it fits, barely), new `CPOV`/`CGRV` strings and
literal-pool entries, and the function's stack frame grown by ~0x18 for the two extra
blocks' slots. The GUI side is already done: `tools/build/gff4_write.py` appends the
four widgets and the panel has room at y=126 and y=141.

---

## 2026-10-07 — ARM9 feasibility for runtime (party-level) enemy scaling

**Investigated:** Whether reactive enemy scaling — enemy stats computed from the *party's*
current level, as the original design sketch envisions — is achievable, time-boxed to a
first feasibility pass.

**Why it cannot be done with data edits:** nothing in the shipped tables reacts to party
level. `squads.GDA` was surveyed column by column looking for an existing multiplier the
engine already applies: column 28 (`#3949145325`) is the only candidate and it holds
`1.2998` on **331 of its 332 rows**, i.e. a global constant rather than a per-encounter
knob. Columns 29/30 (150.0 / 190.0) behave like detection and chase radii. Column 23
`level` is the sentinel `99` on 267 of 332 rows. There is no latent scaling mechanism to
enable, so runtime scaling means injected code.

**Discovered (confidence: high — read from the ROM header and binary):**

| | |
|---|---|
| ARM9 size | 1,117,656 bytes (1091 KB), loaded at RAM `0x02000000` |
| **ARM9 overlays** | **none — the overlay table is empty (offset 0, size 0)** |
| code caves (>=64 bytes of 0x00/0xFF) | 9 runs, **1186 bytes total** |
| largest cave | `0x02110756`, 274 bytes |

Two useful consequences. **There are no overlays**, so all game code lives in one resident
binary — no bank-switching to reason about, and a hook cannot be invalidated by an overlay
swap. And 274 contiguous bytes is comfortably enough for a stat-scaling routine (a
multiply-and-clamp hook is tens of bytes), though the 1.2 KB total is a hard ceiling on how
much injected code this ROM can ever host without relocating something.

**Verdict: feasible, not trivial.** The blocking work is not space, it is *locating the hook
point* — the instruction that loads an enemy's stats into its combat struct, plus a reliable
RAM address for party level at that moment. Neither can be found by static analysis alone
with confidence; it needs a live breakpoint in DeSmuME at combat start, watching reads from
the creature data. That is the multi-session part, and it is unstarted.

**Remaining uncertainty:** everything beyond the table above. In particular it is unknown
whether enemy stats are copied into a struct once at encounter start (easy: one hook) or
read repeatedly per attack (harder: the hook must be cheap and re-entrant).

---

## 2026-10-06 — Overworld encounter models live in squads.GDA, not in the creature row

**Investigated:** After the creature swap, the Chapter 3 Egg Hunt encounter fought as Sonic
(correct) but the figure standing on the overworld map was still Shadow. `creatures.GDA`
column 14 (appearance) was already 0 for rows 75/77/116, so something else drew the map model.

**Method and a wrong turn worth recording:** ARE files decode cleanly as GFF4 and contain
three relevant lists — placeables (name, position, rotation, creature id), environment
effects (`waterfallmist`, `toxicgas` with VFX ids), and a spawn list whose entries carry a
creature id and a position. Creature 75/77 appear in the **placeable** list of `a2_s3_ex.are`
and `act2_world0.are`. I first read field `#40005` on those placeables as an appearance id;
it is `None` on every one of them. That reading came from walking a different list in
`a1_s3_ex.are` and carrying the field number across — **placeables do not carry an
appearance**, they reference a creature id only.

**Discovered (confidence: high — the column hash is decisive):** `squads.GDA` column 4 is
`#86764033`, the **same column hash as `creatures.GDA` column 14**, i.e. an appearance id.
Columns 5-8 are the squad's member creature ids. A squad therefore carries its *own*
overworld model, independent of the creature it spawns:

| squad row | members | appearance | drew |
|---|---|---|---|
| 0 | creature 0 | 0 | Sonic's model for the now-Shadow player |
| 51 | creature 75 | 4 | Shadow's model for "Sonic the Hedgehog" |
| 55 | creature 77 | 4 | same |
| 295 | creature 116 | 4 | same |

That cleanly explains the split symptom: the map figure is the squad's appearance, the
combat portrait is the creature row's.

**Caution for anyone searching this table:** `squads.GDA` also has an `xpvalue` column that
is frequently exactly 75, so a naive scan for "rows mentioning creature 75" returns 27 rows
of which only one is real. Member slots are columns 5-8 and nothing else.

**Applied:** four squad appearances repointed to follow their lead creature's appearance.

**Remaining uncertainty:** untested in game. Only squads whose members include creatures
0/4/75/77/116 were adjusted; any other squad that hardcodes an appearance mismatched to its
creature would have the same issue and has not been audited.

**Why this matters beyond the cosmetic fix:** the ARE spawn lists plus `squads.GDA` are the
encounter layer. Randomising encounters means editing those spawn entries and squad member
slots, so this work is a prerequisite for the randomizer rather than a detour.

---

## 2026-10-06 — Movement ability level IS Adv_*.GDA column 12 (an earlier "disproof" was a bad test)

**Investigated:** How a character gains Dash II / Dash III, in order to grant Shadow Dash III.
An earlier session concluded column 12 was **not** the movement ability level after two
failed in-game tests, and located the live value at save offset `0x026E1` instead.

**Discovered (confidence: high — the pattern matches observed play exactly):** column 12 of
`Adv_<character>.GDA` is the movement ability's level, indexed by character level:

| character | column 12 across levels 1-30 |
|---|---|
| Sonic | 1,1,1,2,2,2,2,**3**,3,3 … 3 |
| Shadow | 1,1,1,2,2,2,2,**2**,2,2 … 2 |
| Amy | 1,1,1,2,2,2,2,**3**,3,3 … 3 |
| Knuckles | 1 throughout (his upgrades are on column 13) |

`movement.GDA` gives ability id 0 (Dash) `maxlevel = 3`, so Dash III is legal — **Shadow's
table simply never grants it**. That is exactly the user-reported behaviour ("shadow has
dash II") and it is a property of his progression table, not of the ability.

**Why the earlier tests failed, and the lesson:** the table is consumed **at level-up**. The
character's current ability level already lives in the save (`0x026E1`, found earlier), so
editing the ROM table does nothing for a character who is not going to level up again. Both
earlier tests were run on an already-levelled save, which could not have shown a change
whether the theory was right or wrong. The experiment could not distinguish the hypotheses
it was meant to test. **A data table that is read only at a transition must be tested across
that transition** — here, by levelling up after the edit, which a fresh run makes possible.

**Applied:** `Adv_Shadow.GDA` column 12 set to 3 from character level 8, matching Sonic's
schedule. Creature 0 reads `Adv_Shadow` after the swap, so this targets the playable
character. Verified statically: `1,1,1,2,2,2,2,3,3,3`.

**CONFIRMED IN GAME (2026-10-07):** on a run started after the edit, reaching character
level 8 granted **Dash LV 3**. The same screen also shows **Teleport LV 1** — the second
movement slot, which the creature swap filled when Sonic's empty `-1` in `creatures.GDA`
column 20 became Shadow's `7`.

**CORRECTION (2026-10-07) — there are THREE movement slots, not two.** This entry originally
described a pair. `creatures.GDA` columns **19, 20 and 21** are movement slots, with their
levels in `Adv_<character>.GDA` columns **12, 13 and 14** respectively. The error came from
inspecting only the two columns the Sonic/Shadow swap happened to touch and generalising.
Knuckles disproves it outright:

| character | slot 1 | slot 2 | slot 3 | Adv 12/13/14 at level 10 |
|---|---|---|---|---|
| Sonic | Dash | — | — | 3, 0, 0 |
| Shadow | Dash | Teleport | — | 2, 1, 0 |
| **Knuckles** | Climb | Smash | **Fly** | **1, 2, 1** |
| Omega | Smash | Invulnerable | — | 2, 2, 0 |
| Eggman | — | — | — | 0, 0, 0 |

The level columns line up exactly with the filled slots, and read 0 for every unused one —
which is also why assigning an ability to a slot without setting its level column grants
nothing at all.

The eleven abilities (`movement.GDA`, with their `maxlevel`): Dash 3, Smash 3, Fly 3, Jump 1,
Climb 1, Invulnerable 3, Stealth 1, Teleport 1, Wriggle 1, Detect 1, KSmash 1. Column 12 of `Adv_<character>.GDA` is therefore confirmed as
the movement ability level, and column 20 of `creatures.GDA` as the second movement slot.

This also retrospectively confirms the diagnosis of the two earlier failed tests: the table
is consumed at level-up, those tests ran on an already-levelled save, and the hypothesis was
never actually exercised. The theory had been correct for months.

**Remaining uncertainty:** none for Dash III itself. Whether other movement abilities honour
`movement.GDA`'s `maxlevel` the same way is untested — only Dash (id 0, maxlevel 3) has been
exercised.

---

## 2026-10-06 — Two correct swaps cancelling: the text swap undid the name swap

**Investigated:** A blanket Sonic<->Shadow swap of TLK dialogue, so NPCs address the player
as Shadow.

**Discovered (confidence: high — caught in post-build verification, before play):** swapping
every capitalised whole-word "Sonic"/"Shadow" in the TLK **silently reverted the character
names**. The creature swap works by *repointing* row 0's `namestrref` from 21778 to 21782;
the text swap then rewrote the contents of 21782 from "Shadow" to "Sonic". Two individually
correct transformations composed to a no-op, and the playable character was called Sonic
again. The same cancellation hit rows 75/77/116, which had been repointed to 14286.

**Fix:** exclude every strref used as a `creatures.GDA` name (89 of them, plus 14279/14286)
from the text swap. Identity is the creature swap's job; the text swap owns dialogue only.

**Lesson worth keeping:** edits that are each correct in isolation can cancel when they
address the same data through different mechanisms — one by *pointer*, one by *content*.
Verifying the end state (what name does row 0 actually render?) caught this; verifying each
edit in isolation would not have.

**Text-swap scope notes (confidence: high):** 991 capitalised "Sonic" and 70 "Shadow" across
824 strings. Lowercase "shadow" is a **common noun** in this script (8 occurrences, e.g.
"running around like a shadow") and is deliberately not swapped; word boundaries protect
"supersonic"/"hypersonic" and the lowercase URL `sonic.bioware.com`. Known cosmetic side
effects: "Super Sonic" becomes "Super Shadow", and an in-game mention of "Sonic Chronicles"
becomes "Shadow Chronicles".

---

## 2026-10-06 — combo.GDA fully enough decoded to author POW moves

**Investigated:** Which `combo.GDA` columns actually define a POW move's behaviour, with the
aim of designing moves rather than nudging numbers.

**Method:** correlated each candidate column's value against the move's own **authored**
effect text (columns 36-41), which states the behaviour in words. A column whose every
`1` row says "Can't miss" is a can't-miss flag; this cross-check is what makes the
identifications evidence rather than guesses.

**Discovered (confidence: high for the named columns, all cross-checked against text):**

| col | meaning | evidence |
|---|---|---|
| 1 | participant count (1 solo … 4 quad) | matches partner columns in use |
| 2 | owner creature id | see the previous entry |
| 3-5 | partner creature ids, `-1` unused | |
| 11 | PP cost | matches the UI |
| 12-14 | damage % at upgrade tiers I / II / III | matches "200% of Attack damage" text |
| 27-29 | status effect id per tier | |
| 30-32 | **proc chance per tier**, as a float | `0.3/0.5/0.8` against "(30% chance)…(80% chance)" |
| 34 | name strref | |
| 35 | description strref | |
| 36-41 | per-tier text, alternating damage line / effect line | |
| 47 | **can't miss** | all 7 rows set say "Can't miss" |
| 48 | **blast** (hits all enemies) | |
| 51 | **element bitmask** | `131072` Fire, `524288` Earth, `1048576` Wind, `2097152` Electricity |
| 52 | elemental flag, set alongside an element | |

Bits 17, 19, 20, 21 are observed; Water and Ice are presumably 18 and 22 but **neither
appears in vanilla**, so that pairing is inference, not fact.

The per-tier text is *authored*, not generated from the numbers. Changing damage or an
element therefore does **not** update the description — the UI will state the old behaviour
until the strings are rewritten too. That is a trap for any future move edit.

**Applied as `profiles/ultimate_lifeform.json`:** Shadow's three party-gated moves become
solo (participants → 1, partners → -1) with raised PP cost; Chaos Blast / Focus Field /
Metal Storm gain Fire / Wind / Earth; descriptions and tier text rewritten to match.

**Verified after rebuild (static):** all six of Shadow's moves are solo, owned by creature 0,
with the intended costs and elements, and **no other move's text changed** — the TLK
writer's shared-string guard held, which matters because strings like "150% of Attack
damage" are reused across many moves and an in-place edit would have rewritten them all.

**CONFIRMED IN GAME (2026-10-06):** all six moves appear and are selectable on a level-2
Shadow; Metal Storm shows "Damage: 300% of Attack damage", "Effect: Stun (20% chance),
Element: Earth", "PP Cost: 8" and a "Team:" row containing Shadow alone. So the solo
conversion, the **element bitmask (column 51) and the authored tier text all take effect** —
the element encoding here does work, and differs from the item encoding used by the Omni Ring.

**Follow-up defect found by that same test — PP, not availability.** `fatigue` in the
`Adv_<character>.GDA` tables is the **PP pool**, and it is only 7 at levels 1-2, rising
about 1 per two levels to 22 at level 30. An 8-cost move is therefore uncastable at level 2.
This is not purely self-inflicted: **vanilla Chaos Rift already costs 8**, so it too is
uncastable at level 2 — Shadow's costs are balanced around him *joining* mid-game at a
higher level, an assumption a Shadow-led run from level 1 silently breaks. Raising the
converted moves' cost to "pay for" losing the party requirement recreated exactly the block
the mod existed to remove.

Retuned: Atomic Strike 4, Focus Field 4, Metal Storm 6, Chaos Rift 8 -> 6, plus a flat +3
`fatigue` at every level in `Adv_Shadow.GDA`. All six became castable and this was
**confirmed in game (2026-10-06)**.

**CORRECTION (2026-10-07) — the PP half of that change did nothing, and the conclusion drawn
from it was wrong.** The kit became castable because the *costs* were lowered; the PP bonus
contributed nothing, and crediting it was a mis-attribution.

`fatigue` in the Adv table is **not** the PP pool. The engine takes a base from
`creatures.GDA` columns 11/12 and adds the per-level **increments** implied by `fatigue`:

    PP(level) = creatures.GDA[row].fatigue  +  sum of (fatigue[n] - fatigue[n-1])

Vanilla Shadow: base 7, increments +3 by level 8, giving 10. A flat bonus added to *every*
Adv level leaves every increment identical, so it cannot move the pool at all. Worse, the
creature swap had meanwhile copied Shadow's base 6 onto creature 0, replacing Sonic's 7 —
so the character had **less** PP than vanilla while the profile claimed +3.

**How it was caught:** a level-8 screenshot showed `PP 9/9` where the Adv table said 13, and
the level-up panel read **"PP +0"**. Computing base + increments reproduces the game's 9
exactly, for both the vanilla and modified ROMs.

**Lesson:** a column's name is not its semantics. `fatigue` correlating with PP across levels
made "fatigue is the PP pool" look confirmed, but the correlation held for a curve whose
*shape* carried the information while the absolute values did not. The earlier entry recorded
it as confirmed on the strength of an in-game result that the change had not actually caused.

**Fixed:** `pp_curve` now edits the creature row's base (and can steepen increments via
`per_level`), and is demoted to build-verified until observed in play.

**Remaining uncertainty:** whether the engine enforces anything about a move whose icon
still depicts a team attack. Six solo moves on a level-2 character is deliberately strong.

---

## 2026-10-06 — POW moves are gated by creature id, not by character identity

**Investigated:** After the Sonic<->Shadow creature swap, a fresh game showed the starting
character correctly as Shadow (name, model, level, portrait) but **all six POW moves greyed
out** with "You do not have the characters required to use this technique" — including the
*solo* moves, which should need nobody. Amy's moves were unaffected.

**Discovered (confidence: high — read from `combo.GDA`, mechanism matches the symptom
exactly, including why solo moves failed and why the "Team:" icon showed a darkened Shadow):**

`combo.GDA` (155 rows x 56 cols) describes every POW move. Four columns carry the cast:

| col | meaning |
|---|---|
| 1 | number of participants (1 = solo, 2 = duo, 3 = trio, 4 = quad) |
| 2 | **owner creature id** |
| 3, 4, 5 | partner creature ids, `-1` when unused |

Columns 2-5 hold **creature ids, not party slots or names**, and for creature rows 0-8 the
id, the row index and `playerid` all coincide. Vanilla Sonic's six moves (rows 0-5) are
owned by id 0; Shadow's (rows 12-17) by id 4.

The swap moved Shadow's *data* onto creature 0 but deliberately left the structural ids
alone, so creature 0 carried move slots 12-17 while those rows still demanded creature **4**
— who on a fresh game is not recruited. The engine correctly reported the owner as missing,
which is why even a solo move failed: a solo move's single required participant is its own
owner. The darkened "Team:" portrait was the engine drawing that missing owner, Shadow.

**Fix applied:** exchange 0 and 4 wherever they appear in columns 2-5 — 18 cell edits across
17 rows. Beyond Sonic's and Shadow's own twelve moves this also covers the Knuckles duos
that name one of them as a partner (rows 8-11 "Revolver Slam", "Knuckles Express",
"Knuckles Sandwich", "Hard Line") and row 57 "Blade Drop".

**Verified after rebuild (static):** every one of creature 0's six move slots (12-17) is now
owned by creature 0, and every one of creature 4's (0-5) by creature 4.

**Checked and found NOT to need the same treatment:**
- `movement.GDA` (11 rows) holds ability definitions only, with no owner or creature column,
  so the movement ability granted to creature 0 by `creatures.GDA` column 20 needs no fix.
- `party.GDA` maps party slot -> `creatureid` (slot 0 -> creature 0, slot 4 -> creature 4);
  leaving the structural ids unswapped keeps it valid.

**CONFIRMED IN GAME (2026-10-06):** after the rebuild the three solo moves (Chaos Spear,
Chaos Rift, Chaos Blast) are available and usable on a fresh run. The creature-id gating
theory is therefore confirmed, not merely consistent with the symptom.

**Remaining uncertainty:** Three of Shadow's six moves are genuine duos/trios — Atomic Strike needs creature 4, Focus Field needs 8 (Omega),
Metal Storm needs 5 and 8 (Rouge, Omega) — so they are *expected* to stay unavailable until
those characters join. Only the three solo moves (Chaos Spear, Chaos Rift, Chaos Blast)
should become usable immediately. A broader question this raises: any other table that
addresses characters by creature id will have the same blind spot, and only `combo.GDA`,
`movement.GDA` and `party.GDA` have been checked so far.

---

## 2026-10-06 — BPS patch creation degraded to one literal byte per position

**Investigated:** Why `bps.create()` never finished on a build that replaced 56 archive
resource payloads, having taken ~10 minutes on an earlier build that edited one resource.

**Discovered (confidence: high — read from the code, then measured):** The matcher only
probed **whole-sector** candidate shifts (`±k*512`, `MAX_SECTOR_SHIFT = 64`) plus the
previous source pointer. That is sufficient when edits stay inside one resource, because
NitroROM file alignment keeps the ROM-level displacement sector-aligned. It fails when
resources *inside* `test.herf` change size: the archive's internal offsets then shift by an
arbitrary byte count, every sector candidate misses, `best_len` stays 0, and control reaches
`literals.append(target[pos]); pos += 1`. The remaining ~130 MB was emitted **one byte at a
time**, each iteration first trying 129 candidate matches.

**Fix:** two additions, both cheap.
1. `recent` — a small most-recently-used list of deltas that actually worked, probed before
   the sector candidates, so once a shift is known the next position hits immediately.
2. `resync()` — when every candidate misses, locate the target run in the source with
   `bytes.find()` (C speed, memchr-backed) over a ±4 MB window first and the whole buffer
   as a fallback, then remember that delta. It runs only on a *new* shift, i.e. tens of
   times for a whole ROM, so a full-buffer scan is affordable.

**Measured (EU ROM, 134,217,728 bytes, 111-edit portrait build):**

| | before | after |
|---|---|---|
| `create()` | did not finish (>45 min, killed) | **70 s** |
| patch size | — | **3,421 bytes** |
| `apply()` round-trip | — | byte-identical |

The patch is also *smaller* than the 873,767 bytes the old code produced for the simpler
50-edit `shadow_mode` build, because that build was already paying literals for shifts the
sector search could not express — the bug was inflating patches long before it stopped
finishing them. `shadow_mode.bps` was regenerated afterwards.

**How it was tested:** `bps.create()` on the unmodified EU ROM against the built portrait
ROM, timed, then `bps.apply()` compared byte-for-byte against the build output. The full
`modbuild.py` pipeline then passed all stages, including its own patch-reproduces-ROM check.

**Remaining uncertainty:** `RESYNC_WINDOW` is 32 bytes; a target region whose first 32 bytes
are not unique in the source could resync to a coincidental match. That costs patch size,
never correctness, because the pipeline verifies that applying the patch reproduces the ROM
exactly and aborts if it does not.

**UPDATE (same day) — this fix is INCOMPLETE. It covers shifts, not growth.**
A later build (`profiles/example_features.json`, which uses the `level_cap` feature) ran
**23 minutes in `bps.create()` and had to be killed**. The difference from the builds the
fix was tested against: those edited cells *in place*, so resource sizes were unchanged and
the archive's tail shifted by a constant delta that `resync()` recovers in one `find`.
`level_cap` **appends 221 rows**, which grows eleven `Adv_*.GDA` resources, changes the
archive's total size, and makes the NDS rebuild relayout the ROM (`files moved 10`). Many
independent shift points plus moved file boundaries defeat the small `recent` delta cache,
and the matcher degrades again.

I had described the earlier fix as resolving the slow path in general, having verified it
against one pattern only. It resolves the *shift* pattern. Growth remains unfixed.

**Workaround shipped:** `modbuild.py --no-patch` skips BPS entirely. The ROM is still built,
validated and regression-swept; only the distributable patch is omitted. The same profile
then completes in about 4 minutes instead of 25+.

**Proper fix, not yet done:** replace the `find`-based resync with an index over the source
(a hash of fixed-width windows at a stride, mapping to offsets), so the matcher can relocate
a run regardless of how many independent shifts precede it. This matters before any mod is
distributed as a patch, since a growth-heavy profile currently cannot produce one in
reasonable time. It does not affect ROMs built locally.

---

## 2026-10-06 — Dialogue portraits: prefix/palette split, and why the expression sets differ

**Investigated:** Whether a Sonic<->Shadow identity swap can carry the *dialogue* portraits
with it. A previous appearance-only swap rendered corruption when the portrait prefix was
swapped, and the cause needed pinning down before Shadow Mode could be built.

**Discovered (confidence: high — all read directly from `test.herf` and `creatures.GDA`):**

1. **`creatures.GDA` columns 17 and 18 are independent.** Col 17 is an *image name prefix*,
   col 18 is a *separate palette resource*:

   | row | character | col 17 (prefix) | col 18 (palette) |
   |---|---|---|---|
   | 0 | Sonic  | `PRTL_SONIC` | `PRTL_Sonic.nclr` |
   | 4 | Shadow | `PRTL_SDW`   | `PRTL_Shadow.nclr` |

   The engine composes `<prefix><expression>_<frame>.NCGR`. Because the prefix is only a
   stem, swapping col 17 alone requests art that does not exist — that is the corruption,
   missing resources rather than a wiring fault. Colour and pixels are separately
   addressable, so a palette change is a one-cell edit.

2. **Three portrait sets exist, with different expression coverage:**

   | set | belongs to | expressions | count |
   |---|---|---|---|
   | `PRTL_SONIC` | Sonic  | amu con det dis gen imp inq mad sle smg | 10 x 4 frames = 40 |
   | `PRTL_SHD`   | **Shade** | def det gen hel int mad sht stg tht  | 9 x 4 = 36 |
   | `PRTL_SDW`   | Shadow | def gen mad smg                         | 4 x 4 = 16 |

   **`PRTL_SHD` is Shade, not Shadow** — confirmed by resolving `namestrref` through the
   TLK for every row that uses each prefix. Shadow's *only* portrait art is the
   4-expression `PRTL_SDW` set. Sonic and Shadow share just `gen mad smg`.

   Prefix usage across all 128 creature rows (the prefix is the only thing that selects
   a set, and it appears nowhere except column 17):

   | prefix | rows |
   |---|---|
   | `PRTL_SONIC` | 0 Sonic, 68 Super Sonic |
   | `PRTL_SDW`   | 4 Shadow, 75 / 77 / 116 "Shadow the Hedgehog" (story + boss variants) |
   | `PRTL_SHD`   | 27 Shade, 65 Procurator Shade |

3. **Every portrait frame is geometrically identical** — 8x8 tiles (64x64 px), 8bpp,
   `pixeldata=4096`, 4160 bytes raw after `.small` decompression, for all three sets.
   Compressed sizes differ (Shadow's compress smaller) but that is compressibility only.
   **Frames are therefore freely interchangeable as payloads.**

4. **The HERF hash table is sorted ascending by DJB2 hash, and payload offsets ascend with
   it.** `herf_write.py` currently has `replace` but no `add`; adding a resource would
   require a sorted insertion plus a full offset rebuild.

**Consequence for Shadow Mode (confidence: high for the mechanism, untested in game):**
Because (3) holds and (1) separates palette from pixels, a full portrait swap needs **no new
resources and no HERF writer extension** — only `replace` of 56 payloads (40 under
`PRTL_SONIC*`, 16 under `PRTL_SDW*`) plus two palette cell edits. But because `PRTL_SHD`
turned out to be Shade, the source art is only Shadow's **4** expressions covering Sonic's
**10** slots: `gen mad smg` match exactly, `det` takes `def`, and the remaining six must
reuse one of those four. Every slot resolves to real art, so nothing corrupts — Shadow is
simply less expressive in dialogue than Sonic was.

Two side effects follow from prefixes being shared: overwriting `PRTL_SONIC*` also changes
**Super Sonic** (row 68), and overwriting `PRTL_SDW*` also changes the three story/boss
Shadow rows (75/77/116). The latter is consistent; the former means Super Sonic would show
Shadow's face.

**How it was tested:** Not yet tested in game. Facts 1-4 are static reads. The shipped
`profiles/shadow_mode.json` deliberately leaves columns 17/18 alone, so it is unaffected.

**What else references these prefixes (confidence: high — exhaustive scan):** nothing.
All 8691 archive resources were scanned raw and LZ77-decompressed, ASCII and UTF-16LE, plus
ARM9, ARM7 and all 302 files outside `test.herf`. The only hits are `creatures.GDA` itself
and `erf.dict` (the archive's own name table). The 101 DLG, 674 GFF, 79 ARE, 107 PLO and
134 GUI resources contain no portrait names, so dialogue must select a speaker's portrait
by creature id rather than by name.

**Remaining uncertainty:** The three-letter expression codes are inferred from their
abbreviations (`amu`=amused, `tht`=thoughtful, `sht`=shout, `stg`=?, `hel`=?); `stg` and
`hel` are genuinely unclear. Any stand-in mapping is an aesthetic judgement, not a
confirmed one, and should be reviewed in game.

---

## 2026-10-05 — Phase 0: save data present locally

**Investigated:** Whether any real save data already exists locally to seed future save-format reverse engineering.

**Discovered (confidence: high, just a filesystem check):** `Old Desmume/Battery/2699 - Sonic Chronicles - The Dark Brotherhood (Europe)....dsv` (65,658 bytes) is a real DeSmuME battery save from actual play (dated 2025-11-25), plus two DeSmuME save states (`.ds1`, `.ds2`). No save-format reverse engineering has been attempted yet — this entry just records that we have real save data to work from when Phase 13 (NG+) or save-related Chao/equipment-retention work starts. Note there is also a loose `SaveTest1.sav` (21,504 bytes) *inside the ROM itself* (file ID 255, NitroROM root) — almost certainly a leftover developer test save shipped in the retail ROM, distinct from a DeSmuME battery file and worth comparing against the real `.dsv` for save-structure clues.

**Remaining uncertainty:** Save format itself (header, fields, checksums) has not been investigated at all yet.

---

## 2026-10-11 — `rewards.GDA` column 5 is NOT the quest XP award (tested and rejected)

**Investigated:** Where XP comes from, after the combat measurements of earlier the same day showed per-fight XP halving per party level and flooring at 10. Those numbers made grinding theoretically possible (~11,400 fights from level 4 to 15) but absurd, which raises the obvious question: on the intended route, where do the levels actually come from?

**Method:** Enumerated the archive's table resources for the first time — `cut -f1` over the recovered `erf.dict` listing in [research/phase0/herf_test_contents.tsv](research/phase0/herf_test_contents.tsv) filtered to `.GDA`/`.2DA`. 229 tables ship, of which four had never been opened: `rewards.GDA`, `CombatRules.GDA`, `Levels.GDA`, `classes.GDA`. Dumped the first three.

**Discovered (confidence: high for the structure, medium for the column meaning):**

`rewards.GDA` is **70 rows × 12 columns**, and uniquely among the GDA tables it carries a **plain-text designer name per row** rather than a strref — `Wasp Quest`, `Krag met`, `Pirates defeated`, `Argus Event complete`, `Green Hills Bridge puzzle`. Layout:

| col | meaning | evidence |
|---|---|---|
| 0 | id | equals the row index in all 70 rows |
| 1 | designer name (ASCIISTRING) | self-describing |
| 2 | plot id, or −1 | 7 on the three quest rows, −1 on the rest |
| 3, 4 | 0 in all 70 rows | — |
| **5** | **XP award** | magnitudes track story importance exactly: 25 for `Boy escorted`, 1,000 for `Krag met`, 10,000 for `Argus Event complete` |
| 6–11 | up to six item ids, or −1 | values land in the known item id range |

Three things make column 5 worth building on:

1. **The hint ladder.** Eight puzzles each appear three times — no hint, `, 1 hint`, `, 2 hint` — and the value *decreases monotonically* in every one of the eight. `Voxai Alpha Puzzle` pays 3,500 / 2,625 / 1,750; `Tyxis Puzzle` 1,850 / 1,387 / 925. Those are exactly **75%** and **50%**, rounded down, in all eight cases. A column that is docked a quarter per hint taken is a reward, and the only per-quest reward a puzzle grants is XP.
2. **Row 6 is named `GenericLargeXPOnly`** and is identical to row 5 `GenericLarge` (2,500) except that `GenericLarge` is the one referenced where items are also given. The designers named the column for us.
3. **Rows 64/65 (`Scylla Defeated`, `Charyb Defeated`) hold −1**, i.e. "no XP", while still granting an item. The two endgame bosses award their XP through the combat path, not the quest path.

**The number that matters.** Summing column 5 across all 70 rows gives 73,033. Excluding the 16 hint-variant rows, which are mutually exclusive with their own no-hint parents, the **maximum quest XP a single playthrough can collect is 62,723**. Against Sonic's cumulative curve in `Adv_Sonic.GDA`:

| level | cumulative XP |
|---|---|
| 14 | 55,223 |
| **15** | **80,273** |
| 20 | 466,487 |
| 30 (cap) | 1,159,258 |

So **quest XP alone takes a completionist to about level 14** — 5.4% of the way to the cap. Everything above that is combat XP.

**Why this resolves the grinding paradox rather than deepening it.** The earlier measurement looked damning: XP halves per party level and floors at 10, so a level-7 party farming Green Hill's level-1-to-4 trash earns nothing. But the halving is *relative* — enemy level against party level — and enemy levels rise to 20 across the game. The intended route keeps the party inside the band where fights still pay, which is the same conclusion the XP measurements reached from the other end. The game is not stingy; it is **directional**. It pays you to move forward and declines to pay you to stand still.

**What this means for the per-NG+ scaling idea.** The user's proposal was to find the XP an average run earns, derive the level that implies, and scale per New Game+ cycle from it. The quest half of that is now a known constant — 62,723, fixed, not an average — but it is only ~5% of the total, so it cannot carry the estimate. The combat half is self-regulating by construction, which means **"average XP per run" is not a usable free variable**: a run's ending level is set by how far the player walked, not by how much XP exists. The sound version of the same idea is to balance each NG+ cycle against a party **at or near the level cap**, since the curve pulls every route to roughly the same place by the end, and to treat the cycle number as a straight multiplier rather than something derived from an XP budget.

**Confidence:** high that `rewards.GDA` is the quest reward table with 70 rows and the layout above; high that the 62,723 total and the level-14 consequence follow from it; **medium that column 5 is XP specifically** rather than rings. The hint ladder and `GenericLargeXPOnly` are strong but circumstantial — rings would also be docked per hint. Untested in game.

**Remaining uncertainty:** whether quest XP is awarded to the whole roster or only the active four; whether the three `Generic*` rows are referenced repeatedly (which would raise the 62,723 figure, possibly a lot). Both are visible from the plot files and neither was chased tonight.

**TESTED 2026-10-11, AND THE HYPOTHESIS IS REJECTED.** The probe was rebuilt to set **all 64** positive column-5 values to 777 (the single-row version targeted `Wasp Quest`, which hangs off `plt_ch2_main.plo` and is not a findable side quest). Reading the built ROM back confirms 64 rows at 777 and **no row anywhere reading 250**. In play, a completed quest paid **250 XP** — a vanilla-looking number that the mod does not contain.

So column 5 is not the number shown to the player. Everything this entry derived from it falls with it:

* **The 62,723 total is withdrawn**, and with it the claim that quest XP is worth about level 14 and ~5% of a run. That figure described a column whose meaning is unknown.
* **The per-NG+ conclusion is withdrawn too.** "Average XP per run is not a usable variable" was argued *from* the 62,723 being small. The argument has no basis now. The NG+ question is simply open again.
* What survives is **structural only**: `rewards.GDA` is 70 rows × 12 columns, it names its own rows in plain text (unique among the GDA tables), column 2 is a plot id, and column 5 decreases to exactly 75% / 50% across all 16 puzzle hint variants. Something real is in column 5 — it is simply not the XP the player is shown.

**Where I went wrong.** The hint ladder and the row named `GenericLargeXPOnly` are genuinely suggestive, and I said so, but I rated the conclusion "high confidence" for the 62,723 total while rating its only load-bearing premise "medium". A total computed from an unconfirmed column cannot be more certain than the column. I should have labeled the whole entry a hypothesis and left the arithmetic out of the summary until the probe came back.

**Still open:** what column 5 *is* (rings is the obvious next guess, and the player did not report 777 rings, which argues against it), and where the 250 actually came from.

**The experiment that settled it:** [profiles/xp_rules_probe.json](profiles/xp_rules_probe.json) sets `Wasp Quest` (row 1) from 50 to **777**. That quest is early in Green Hill, so one completion settles whether column 5 is XP, rings, or neither.

---

## 2026-10-11 — `CombatRules.GDA`: 74 unnamed tuning constants, two of which are candidates for the XP floor

**Investigated:** Whether the measured combat-XP floor of 10 is a table value or computed in ARM9.

**Discovered (confidence: high for the structure, explicitly unconfirmed for the mapping):**

`CombatRules.GDA` is **74 rows × 2 columns**: `(id, value)`, where id equals the row index throughout. There are **no names anywhere** — not in the table, not as column hashes (the labels are the sequential 0x2715+n form, so `gda_dict.py` hashing has nothing to recover), and `CombatRules.GDA` is **absent from `2DA.GDA`**, the 31-entry registry of tables the engine loads by index. It is reached by a hardcoded row index from ARM9, so every row's meaning has to be established by experiment.

The values are visibly a combat tuning block — `90 60 2 1 1 24 24 7 20 1000 …` with hit-chance-looking percentages (85, 90, 95, 100, 110, 120, 135, 150, 200, 230, 250) and penalty-looking negatives (−4, −10, −20, −50).

**Exactly two rows hold 10**: row 34 and row 47. If the XP floor is table-driven at all, it is one of those two.

**Confidence:** high on the shape and the row count; the floor mapping is a **two-candidate hypothesis and nothing more**. Recorded here rather than in RESEARCH.md only because the structural facts are confirmed; the mapping is not.

**TESTED 2026-10-11, AND BOTH CANDIDATES ARE REJECTED.** With row 34 at 77 and row 47 at 33 in the built ROM (read back out to confirm), overleveled Green Hill trash still paid **exactly 10**. The floor is therefore **not table-driven** — it is computed in ARM9, and `CombatRules.GDA` is not the lever. This closes the cheap route to it; changing the floor needs the code, which means the watchpoint work.

A clean negative, and worth the build: it was two candidates and one fight.

**The experiment that settled it:** the same [profiles/xp_rules_probe.json](profiles/xp_rules_probe.json) set row 34 to **77** and row 47 to **33**. Fighting overleveled Green Hill trash then reads the answer directly off the reward screen — 77 means row 34, 33 means row 47, and a stubborn 10 means the floor is computed in ARM9 and this table is not the lever. The three edits in that profile are mutually non-confounding: one is a quest award, two are combat constants with distinct values.

**Also noted:** `Levels.GDA` turned out **not** to be an XP curve. It is a 5×5 schema stub holding type codes (`I`, `R1000`, `IM3`, `N1`) and defaults — leftover tooling metadata, with no game data in it. The real XP curves are the per-character `Adv_<name>.GDA` tables, as already documented.

---

## 2026-10-11 — Enemy HP in battle is the table value **plus a flat +60**, and `enemy_scaling` works exactly as written

**Investigated:** Why on-screen enemy HP matched no row in `creatures.GDA`, in either a modded or an unmodified ROM.

**Method:** Built `control.nds`, a **zero-edit rebuild whose CRC32 (503C3E4C) equals the source ROM's**, so it is vanilla under a different filename and therefore gets its own DeSmuME save slot. The same save was then loaded against `control.nds` and `enemy_scaling_test.nds` and the same two encounters fought in each, giving eight paired readings.

| encounter | control | enemy_scaling |
|---|---|---|
| A | 90, 105 | 94, 110 |
| B | 85, 90 | 88, 92 |

A multiplicative model was tested first and **rejected**: no single factor, searched over all 128 creature rows with both members of an encounter constrained to share it, reproduces either pair. An additive model was then solved over the same space.

**Discovered (confidence: high — unique solution, eight of eight exact):**

A flat **+60 HP** on every enemy, and nothing else:

| encounter | creature | lv | table (vanilla → scaled) | +60 → displayed |
|---|---|---|---|---|
| A | Wasp Swarm | 3 | 30 → 34 | **90 → 94** |
| A | Wild Boar | 2 | 45 → 50 | **105 → 110** |
| B | Sentry Drone | 2 | 25 → 28 | **85 → 88** |
| B | Enraged Armadillo | 1 | 30 → 32 | **90 → 92** |

Every one of the eight numbers is reproduced to the unit, and the search returned **exactly one** creature pairing per encounter out of 128 rows. The offset is the same 60 in both encounters despite different creatures and different levels (1, 2, 2, 3).

**Two things follow.**

1. **`enemy_scaling` is correct.** Its output is precisely what `creatures.GDA` says it should be — the feature was never broken and the earlier "enemies have way more HP" reading was the +60, which is present in vanilla too. This is the first in-play confirmation of the feature since the HP-column fix of 2026-10-08.

2. **The flat term dominates the percentage one, and that is a design problem.** +5%/level on a level-2 Sentry Drone is +3 HP against an actual pool of 85 — a **3.5%** change, not the 12% the rate implies. Any percentage applied to the table is diluted by whatever is adding 60, and at low levels the dilution is near-total. A static curve on `creatures.GDA` cannot be the whole of `enemy_scaling` while this term exists.

**What +60 is NOT.** It is not per-squad: the two encounters are `squads.GDA` rows 207 and 208, whose only percentage-shaped column (22) reads **65 and 75** respectively — different values, identical offset. It is not per-creature-level either, being flat across levels 1 through 3.

**Remaining uncertainty — this is the open question.** What sets 60. The live candidates are party level, New Game+ cycle, and chapter/area progression; the save used descends from a god-mode playtest save, so an artifact of that cannot be excluded either. All are distinguishable by one observation.

**Next experiment:** start a **new game** on `control.nds` and read the HP of the first Sentry Drone encounter in Green Hill. Vanilla table HP is 25. A fresh party seeing **25** means the offset is driven by party level or progression, and the term that `enemy_scaling` actually needs to reach has been found. A fresh party seeing **85** means the +60 is unconditional and belongs to the encounter setup instead. Roughly five minutes of play, and it splits the hypothesis space cleanly in two.

---

## 2026-10-11 — The +60 is a property of the **save**, not the ROM: zero on a new game, +60 on the test save

**Investigated:** What sets the flat enemy-HP offset found earlier today.

**Method:** Two saves, one ROM. `control.nds` is a zero-edit rebuild whose CRC32 equals the source ROM's, so the game data is provably identical in both runs and any difference has to come from the save.

| save | enemy | displayed | `creatures.GDA` | offset |
|---|---|---|---|---|
| test save (god-mode lineage) | Sentry Drone ×3 | **85** | row 17 = 25 | **+60** |
| brand new game | Sentry Drone | **20** | row 74 = 20 | **0** |

**Discovered (confidence: high):**

The offset is **0 on a fresh save and +60 on the test save, against byte-identical game data**. Enemy HP is therefore not a function of `creatures.GDA` alone — there is a runtime term driven by save state, and it is **large**: +60 on a 25 HP creature is +240%, which dwarfs everything `enemy_scaling` does to the table.

A note on the fresh reading: two Sentry Drone rows exist, 17 (25 HP) and 74 (20 HP). The new game's 20 matches row 74 **exactly with no offset**, which is the clean interpretation; reading it as row 17 would require an implausible −5.

**Narrowing it.** Party blocks were read out of both saves using `save_edit.find_party`, with level at speed+0x7C (the two documented absolute offsets are 0x7C apart, and the field reads plausibly in every block tested — 4s and 5s in one save, a uniform 19 in the other):

| | party levels | HP | power | attack |
|---|---|---|---|---|
| test save | **4, 4, 4, 5** | 537 / 530 / 515 / 72 | 259 / 258 / 256 / 10 | 259 / 259 / 257 / 14 |
| real playthrough | **19** (all) | 366 / 300 / 300 / … | 38 / 43 / 26 / … | 43 / 48 / 37 / … |

This kills the simplest hypothesis. The test save's party is **level 4-5** — barely above a new game's 1-2 — yet it carries the full +60. What *is* dramatically different is its stats: three characters sit at ~259 power and attack against a normal ~10-14, because the save descends from a god-mode edit. A 3-level gap producing +60 would need +20/level; a 25× stat gap producing +60 is far less strained.

So the user's own hypothesis — **that the game scales enemies off party stats rather than party level** — is now the better-supported of the two, and it is testable in one fight.

**Confidence:** high that the offset is save-driven and that it is +60 here; **the stats-vs-level question is explicitly open.** Neither is established.

**Next experiment:** `control_lv19.nds` — a second zero-edit vanilla rebuild carrying a **copy** of the real playthrough save (the original is untouched; the copy was verified byte-identical). That save is the opposite corner of the square: **level 19 with ordinary stats**, against the test save's **level 4-5 with maxed stats**. Fight anything, report the enemy and its HP, and the table gives the offset:

* a **large** offset at level 19 with ordinary stats → party **level** drives it
* an offset near **zero** → party **stats** drive it, and `enemy_scaling` has been working on the wrong variable all along

Two saves differing on the two candidates in opposite directions is what makes one fight enough.

---

## 2026-10-11 — The enemy-HP offset tracks party **stats**, not level or progression — and `enemy_scaling` is fine

**Investigated:** Whether the +60 enemy-HP offset is driven by party level, story progression, or party stats.

**Method:** Three saves against **byte-identical vanilla game data** (`control.nds` and `control_lv19.nds`, both zero-edit rebuilds whose CRC32 equals the source ROM's). The saves differ on the candidate variables in opposite directions, which is what lets three readings settle it.

| save | party level | party stats | chapter | enemy | shown | table | **offset** |
|---|---|---|---|---|---|---|---|
| new game | 1-2 | ordinary | 1 | Sentry Drone (row 74) | 20 | 20 | **0** |
| test save | **4-5** | **maxed (~259 pow)** | 1 | Sentry Drone (row 17) | 85 | 25 | **+60** |
| real playthrough | **19** | ordinary (26-48 pow) | **5** | **Shield Pawn (row 28, lv7)** | **180** | **180** | **0** |

**Discovered (confidence: high, by elimination):**

* **Party level does not drive it.** A level-19 party produces an offset of exactly **zero**. If level were the variable, 19 would show the largest offset of the three; it shows none.
* **Story progression does not drive it.** The same reading is from **chapter 5**, as far from the opening as the save goes.
* **Party stats remain.** The only save showing an offset is the only save with inflated stats — a god-mode lineage at ~259 power and attack against a normal 26-48.

The game appears to carry a **rubber band keyed to party stats**: when a party is abnormally strong for its level, enemies gain HP to compensate. That is a real mechanic, not an artifact of our tooling, and it is the first evidence of any *reactive* enemy scaling in this game.

**A correction to what this project concluded three hours ago.** The previous entry's inference — that the flat term "dilutes any percentage applied to the table" and that `enemy_scaling` had been "working on the wrong variable" — **is wrong, and the opposite is true.** The +60 was a property of the god-mode test save. For a normal save the offset is **zero at level 1 and still zero at level 19**, so enemy HP *is* exactly the `creatures.GDA` value and `enemy_scaling`'s static curve is the whole story for any real player. The feature needs no redesign. The alarm was raised from a single save that happened to be the one abnormal case in the set.

The lesson is the same one as this morning's XP entry: every scaling observation so far has been made on a god-mode save, and a save chosen for convenience in one experiment silently became the control in the next.

**Remaining uncertainty.** Stats win by elimination, and only **one** save in the set has inflated stats — so strictly, what is established is that *something about the god-mode save* adds 60, with stats the known difference. What the function is (which stat, party average or maximum, continuous or thresholded) is entirely unknown, as is whether POW and other enemy stats get the same treatment or only HP.

**Next experiment:** a **new game, saved at the first opportunity, then god-moded on a copy** — level 1, chapter 1, maxed stats. That holds level and progression still and moves only stats, confirming directly rather than by elimination. The test save's **fourth party member sits at ordinary stats (72 HP, 10 power) beside three maxed ones**, which is a free second probe: it distinguishes a party *average* from the party *maximum* without needing another save.

---

## 2026-10-11 — Party stats are rejected too. All three candidates are out, and the +60 is an unexplained outlier

**Investigated:** Direct confirmation of the stat hypothesis, which the previous entry accepted by elimination.

**Method:** `control_fresh.nds` (a third zero-edit rebuild, CRC32 equal to the source) with a brand new save, god-moded in place after a verified backup. `save_edit`'s GODMODE writes the eight stat fields and never touches level, so level and chapter were held still and only stats moved.

| | before | after |
|---|---|---|
| level | 1 | **1** |
| HP | 33 / 27 | **500 / 500** |
| power | 8 / 13 | **255 / 255** |
| attack | 8 / 7 | **255 / 255** |

**Result: the Sentry Drone still reads 20 HP** — `creatures.GDA` row 74 exactly, offset **0**, unchanged from the same encounter on the same party before the edit.

(The battle HUD showed Sonic at 33 HP, which looked at first like the edit had not reached the game. It had: the HUD draws **current** HP and only max HP was raised, so the party was at 33/500. Noted because the same display will mislead the next person to try this.)

**So party stats are rejected.** The scoreboard for the enemy-HP offset:

| variable | test | offset | verdict |
|---|---|---|---|
| party level | 19 vs 1 | 0 | **rejected** |
| story progression | chapter 5 vs 1 | 0 | **rejected** |
| party stats | 255 vs 8 power | 0 | **rejected** |

All three are out, and yet the original test save produces a clean, reproducible **+60 across three different creatures in two different encounters**, solved uniquely against all 128 creature rows.

**What this costs.** The previous entry concluded "the offset tracks party stats" from three data points by elimination, and that conclusion is now dead. Twice today an inference has been promoted to a finding on the strength of *everything else having been ruled out*, and twice the remaining candidate was wrong too. Elimination across three hypotheses is only as good as the assumption that the list is complete, and in both cases it was not.

**What is actually still standing.** Only the measurements. Three configurations read an offset of exactly 0; one reads exactly +60. That is a fact about one save, and it has survived every attempt to attribute it to something general.

**Candidates not yet tested**, none favored over the others:

* **Enemy count.** The 0-offset readings came from encounters of 1 enemy (new game) and 2 (the Shield Pawns). Both +60 encounters had 3 and 4. No ordering is implied by two points on each side.
* **Party size.** 2 characters at offset 0 against the test save's 4 — though the chapter-5 save likely fielded 4 as well, which would rule this out if confirmed.
* **New Game Plus**, or any other per-save flag. The test save descends from `playtest_god_mode` by way of `chao_farm` and its history is not fully known.
* **Equipped Chao.** The test save is a Chao-farming save and may carry many; the chapter-5 and fresh saves do not.

Not a candidate: `squads.GDA`. The two +60 encounters are rows 207 and 208, and **no column holds 60 in both** — the nearest, column 22, reads 65 and 75.

**Next experiment, in order:**

1. **Re-confirm the anomaly.** Fight the same Sentry Drone encounter on the test save again and check it still reads 85. Three configurations now read 0; the outlier is the thing that deserves re-measuring before any more theory is built on it.
2. **While there, record the enemy count and the party size.** Those are the two cheapest live candidates and both are readable from the same screenshot.
3. Only then pick a hypothesis.

---

## 2026-10-11 — The +60 reproduces, every encounter now identified, and the offsets line up by enemy count

**Re-measured the outlier** (per the evidence standards, rule 3). On the test save, three Sentry Drones read **85 HP** again — the same value as before, with a party of four (537 / 526 / 513 / 71 HP). The anomaly is real and repeatable, not a misread.

**Squad membership resolved.** `squads.GDA` columns **5-8 are the member slots**; column 4 is the overworld appearance, as `features.py` already had it. An earlier search here read columns 4-8 as members and produced encounter sizes one too large. With the correct span every encounter observed today matches a squad exactly:

| squad | members (cols 5-8) | enemies | observed |
|---|---|---|---|
| 198 | row 74 | **1** | 20 = 20 + 0 |
| 14 / 321 | row 17 ×3 | **3** | 85 = 25 + 60 |
| 207 | rows 17, 12, 12, 17 | **4** | 85, 90, 90, 85 |
| 208 | rows 14, 13, 13, 14 | **4** | 90, 105, 105, 90 |

**This also answers a question the player raised and resolves an apparent contradiction.** Two Sentry Drone rows exist — row 17 at 25 HP and row 74 at 20 HP — and the new game's scripted encounter (squad 198) uses **row 74**, while the repeatable one (squads 14 / 321) uses **row 17**. The bases genuinely differ, so "the drone has 20 base HP" was true of one encounter and not the other. Worth recording because it is exactly the kind of thing that looks like a contradiction in the data and is not.

**A pattern, explicitly not a finding.** Ordering every reading by how many enemies the squad fields:

| enemies | offset |
|---|---|
| 1 | 0 |
| 2 | 0 |
| 3 | **+60** |
| 4 | **+60** |

All five readings fit "3 or more enemies → +60". **It is also perfectly confounded**: every 0 reading comes from a fresh or chapter-5 save and every +60 from the god-mode test save, so "enemy count" and "something about that save" predict the identical table. Naming either would repeat today's mistake twice over.

**Next experiment:** `enemy_count_probe.nds` — squad 14 reduced to **one** Sentry Drone and squad 321 to **two**, by writing −1 into the surplus member slots (the same empty-slot value squad 198 already uses). Fought **on the test save**, which reads 85 for the unmodified three-drone version, this moves enemy count alone and holds the save fixed. The two encounters label themselves by how many enemies appear.

Written before running, per rule 5:

* either reads **25** → the offset tracks **enemy count**; the save is unremarkable and the game toughens larger packs
* either reads **85** → the offset tracks **the save**, and enemy count is dead
* 1 enemy at 25 but 2 enemies at 85 → the threshold sits between 2 and 3, which the chapter-5 Shield Pawns (2 enemies, offset 0) would then contradict, meaning both variables are in play

The scripted lone drone of squad 198 was considered first and rejected: it is a one-off tutorial encounter that flees, and cannot be revisited on a save past that point.

---

## 2026-10-11 — Enemy count rejected. The offset belongs to the save, and party size is the last cheap candidate

**Result:** `enemy_count_probe.nds` on the test save. Squad 14, reduced from three Sentry Drones to **one**, still reads **85 HP** — identical to the three-drone reading on the same save.

This is a **positive test, not an elimination**: enemy count was moved deliberately from 3 to 1, holding the save, the creature (row 17, base 25) and the map location fixed, and the offset did not move with it. Enemy count is rejected on its own evidence.

| variable | how tested | offset | verdict |
|---|---|---|---|
| party level | 19 vs 1 | 0 | rejected |
| story progression | chapter 5 vs 1 | 0 | rejected |
| party stats | 255 vs 8 power, god-mode on a fresh save | 0 | rejected |
| **enemy count** | **3 → 1, same save, same squad** | **+60 unchanged** | **rejected** |

So the +60 is a property of **that save**, and the pattern "3 or more enemies → +60" recorded in the previous entry was coincidence — exactly the confounding that entry flagged, now resolved the unfavourable way. Recording that because the pattern was clean across five readings and still meant nothing.

**What differs about the test save, and what it would cost to test:**

| candidate | test save | fresh save (offset 0) | how to check |
|---|---|---|---|
| **party size** | **4** (Sonic, Amy, Tails, Rouge) | **2** (Sonic, Amy) | free — read the chapter-5 save's party size; 4 there kills it outright |
| equipped Chao | a Chao-farming save, likely many | none | one menu visit and one fight: unequip everything, refight |
| New Game Plus, or another per-save flag | unknown | no | not directly observable |
| save lineage | `playtest_god_mode` → `chao_farm` | clean | — |

**Party size is the one worth checking first, because it is free.** The chapter-5 save reads offset 0; if it was fielding four characters, party size dies without anyone fighting anything. Its earlier screenshot was cropped to the enemies, so the party was never recorded — a reminder to capture the whole battle screen rather than the interesting corner of it.

**A note on the chapter-5 reading, since it is now load-bearing.** 180 was read as Shield Pawn (row 28, 180 HP) at offset 0. The alternative reading — a 120 HP creature at +60 — is available in the table (row 79, Assault Drone Mk. II), so the identification rests on the player naming the enemy as a Shield Pawn. The only other Shield Pawn row is 82, Mk. II at 360, which cannot produce 180 at either offset. The reading stands, but it stands on the name.

---

## 2026-10-11 — Party size rejected; and the party-stats rejection is withdrawn as unsafe

**Party size is rejected.** The chapter-5 save fields a **full party of four** and reads offset **0**; the test save fields four and reads **+60**. Same party size, opposite offsets.

**The party-stats rejection does not hold, and I am withdrawing it.** That test god-moded a fresh save and fought a Sentry Drone reading 20 HP — which is **squad 198, member row 74**, and squad 198 is the **scripted tutorial encounter that flees**, as the player identified when asked to find a lone drone for a later experiment. A scripted one-off fight is exactly the kind of encounter an engine exempts from scaling, so a 0 offset there is not evidence that stats do nothing; it may only be evidence that *that fight* never scales. The conclusion was drawn from the wrong encounter and the error was mine for not noticing that the only lone-drone encounter in the game is the scripted one.

This is the fifth variable tested today and the second time a rejection has had to be taken back. The standing list is now:

| variable | how tested | verdict |
|---|---|---|
| party level | 19 vs 1 | rejected |
| story progression | chapter 5 vs 1 | rejected |
| enemy count | 3 → 1, same save, same squad | rejected (positive test) |
| party size | 4 vs 4, opposite offsets | rejected |
| **party stats** | god-mode on a fresh save | **withdrawn — scripted encounter** |

**Next experiment — the same question asked properly.** Rather than raising stats on a save with no offset, lower them on the save that has one. `enemy_count_probe.dsv` (the test save, backed up first as `.godmode-baseline`) has had the three god-moded characters' eight stat fields overwritten with the **fourth member's own ordinary level-4 line** — speed 9, attack 14, defense 26, HP 72, power 10, grit 7, luck 10, PP 8 — so the whole party is now ordinary for its level and **nothing but stats has moved**. Checksums reseal clean.

Refought against the **one-drone squad 14** on `enemy_count_probe.nds`, which read **85** with god-mode stats minutes earlier, this holds the save, the encounter, the creature, the party size and the map position fixed.

Written before running:

* reads **25** → **party stats drive the offset**, the withdrawn rejection was wrong, and the mechanism is found
* reads **85** → party stats are genuinely out, this time on a repeatable encounter, and the candidate list drops to equipped Chao and per-save flags

The god-mode party is recoverable at any time from `enemy_count_probe.dsv.godmode-baseline`.

**Method note worth keeping.** Both of today's withdrawn rejections share a shape: a 0 reading taken from a configuration that could not have produced a non-zero one. Rule 5 says to write down what each outcome means before running; the missing half is to also ask **whether the setup is capable of showing the effect at all** — a null result from an exempt encounter, or from a save that never had the property, is not evidence.

---

## 2026-10-11 — Party stats rejected on a repeatable fight; the save-edit tooling is cleared; the untested cell found

**Party stats are now properly rejected.** The three god-moded characters in the test save had their eight stat fields overwritten with the fourth member's ordinary level-4 line (power 259 → 10), and the one-drone squad 14 **still reads 85**. Same save, same encounter, same creature, same party size, only stats moved — and this time on a repeatable encounter rather than the scripted one. The withdrawn rejection is reinstated on sound evidence.

**The save-editing tooling is cleared.** The player's hypothesis was that an earlier edit planted something in the god-mode save. A controlled before/after of `--godmode` — the untouched fresh save against the same save immediately after the operation — shows **17 differing runs, every one inside a party stat block or a checksum, and zero outside**. `save_edit --godmode` writes only what it claims to. (The `playtest_god_mode.dsv.before-godmode` pair is *not* a controlled diff — it differs in hundreds of runs across the plot and inventory regions, consistent with play between the two snapshots, so it cannot be used for this.)

**Squad data is cleared too.** Comparing all 40 `squads.GDA` columns between the four +60 squads (14, 207, 208, 321) and the two 0-offset ones (198, and 214 — the only Shield-Pawn-only squad, matching the chapter-5 reading) finds **no column on which the two groups agree internally and differ from each other**. The offset is not a squad property.

**The cell nobody has measured.** Every 0 reading today came from either the **scripted** tutorial encounter (squad 198, which flees and may be exempt) or a **chapter-5** encounter. Every +60 reading came from a **repeatable chapter-1** encounter on the god-mode-lineage save. So two explanations remain and they are **not** distinguished by any data collected so far:

* **A — the save.** Something in the god-mode lineage adds 60, independent of current stats.
* **B — the content.** Chapter-1 repeatable encounters add 60 for everyone, and the fresh save never fought one.

This is the same error shape as the two withdrawn rejections: the configurations that read 0 were not configurations capable of showing the effect.

**Next experiment:** `encounter_probe_fresh.nds` carries the **untouched fresh save** (level 1, two characters, ordinary stats, never edited — a copy of `control_fresh.dsv.vanilla-baseline`) plus the same squad shrink so the deciding fight is one enemy. Play forward past the scripted tutorial drone to the first **repeatable** Sentry Drone encounter.

Written before running:

* reads **25** → **A**. The content is innocent, and whatever adds 60 lives in that save.
* reads **85** → **B**. Chapter-1 repeatable encounters carry +60 for everyone; the save is innocent; and the chapter-5 zero means the term is area- or chapter-scoped, which would make it the reactive scaling hook this project has been looking for.

---

## 2026-10-11 — The content is innocent: same ROM bytes, same squad, same creature, two saves, 25 vs 85

**Result:** an untouched fresh save, played forward to the **repeatable** squad-14 encounter, reads the Sentry Drone at **25 HP** — `creatures.GDA` row 17 exactly, offset **0**.

This is the cleanest comparison of the day. `encounter_probe_fresh.nds` and `enemy_count_probe.nds` are **byte-identical (both CRC32 7D32D15A)**, carry the same squad shrink, and were fought at the same squad against the same creature with the same party size of four. The only difference is which save was loaded:

| save | drone |
|---|---|
| untouched fresh | **25** |
| god-mode lineage, stats normalized | **85** |

So hypothesis **B is rejected**: chapter-1 repeatable content does not carry +60. The offset is a property of the save, as the player argued.

**And party level comes back.** With both parties now at four characters, ordinary stats and the same encounter, the surviving difference is level:

| save | levels | power | offset |
|---|---|---|---|
| fresh | **3, 2, 2, 1** | 10, 14, 8, 7 | 0 |
| god-mode lineage | **5, 4, 4, 4** | 10, 10, 10, 10 | +60 |

Level was rejected earlier because a **level-19** party read 0 — but that reading came from **chapter 5**, where level 19 is the appropriate level. Both facts fit one hypothesis the project has not yet stated:

> **The offset tracks how far the party's level exceeds the level the area expects.** Green Hill expects 1-3, so a level 4-5 party is overlevelled and enemies gain 60; chapter 5 expects ~19, so a level-19 party there is on-level and gains nothing.

That is a **rubber band keyed to level-relative-to-area**, and it is consistent with the independent XP measurements of this morning, where per-fight XP halved for every party level above the local enemies and floored at 10. Two unrelated systems decaying against the same quantity is the kind of agreement worth taking seriously — but it remains a hypothesis that fits, not a finding.

**Next experiment — a positive test, not another elimination.** The fresh save (backed up as `.level23-baseline`) has had **only the level field** written, from 3/2/2/1 to **5/4/4/4**, matching the +60 save exactly. Stats, HP, power, inventory and plot state are untouched; checksums reseal clean. Refight the same one-drone squad 14 on `encounter_probe_fresh.nds`.

Written before running:

* reads **85** → **confirmed**. The level field alone drives the offset, the mechanism is found, and it is the reactive scaling hook `enemy_scaling` has been approximating with a static table.
* reads **25** → the level *field* is not the input. The game is reading something level-derived that the save stores elsewhere (accumulated XP is the obvious candidate), and the next step is to find it.

Either answer is useful, which is the first time today that has been true of a test of this question.

---

## 2026-10-11 — The chapter-5 control is on New Game Plus 2, which weakens three rejections

**Correction supplied by the player:** the level-19 save used as the chapter-5 control is **on New Game Plus 2** — the game has been completed twice on it. This was not known when that reading was taken or when conclusions were drawn from it.

**What it costs.** That save was the sole evidence behind two rejections and part of a third:

| rejection | what it rested on | status now |
|---|---|---|
| party level | level 19 reading 0 | **weakened** — NG+2 is a different regime |
| story progression | chapter 5 reading 0 | **weakened** — same reading |
| party size | 4 characters reading 0 | **weakened** — same reading |

And the explanation offered in the previous entry — "chapter 5 expects ~19, so a level-19 party is on-level" — was **invented to fit**. On a second replay a level-19 party in chapter 5 is most likely *overlevelled* for that content, which is the opposite of what the story required. The hypothesis it supported ("the offset tracks level above what the area expects") now has a clear counterexample: twelve levels above a level-7 Shield Pawn produced an offset of **zero**.

**Why this keeps happening.** The chapter-5 save was adopted as a control because it was convenient, and its own properties were never established — exactly the failure the evidence standards' rule 4 names, and the third time today an uncontrolled property of a save has driven a wrong conclusion. **A control whose relevant state has not been read is not a control.** NG+ status is now a known variable and was never checked on any save in the set.

**What survives, and it is the strongest result of the day.** The 25-vs-85 comparison is untouched by this: two byte-identical ROMs, the same squad, the same creature, the same party size, differing only in which save was loaded. The offset is a property of the save. That stands.

**The pending experiment is unaffected and still decisive.** Writing only the level field on the fresh save, 3/2/2/1 → 5/4/4/4, tests whether the level field drives the offset **within chapter 1**, with everything else held fixed and no reliance on the NG+2 save at all. It should be run as planned.

**Added to the candidate list:** New Game Plus state. It is not known for any save here, including the god-mode lineage one that produces the +60, and it should be established before any save is used as a control again.

---

## 2026-10-11 — Party level rejected by positive test: identical levels, identical squad, 0 vs +60

**Result:** the fresh save, with both level stores written to **5/4/4/4** to match the god-mode save exactly, fights **squad 207** and reads **25, 30, 30, 25** — Sentry Drone 25, Enraged Armadillo 30, Enraged Armadillo 30, Sentry Drone 25, in squad order. Those are the raw `creatures.GDA` values. Offset **0**.

Squad 207 is the same encounter that read **85, 90, 90, 85** on the god-mode save. Side by side:

| | ROM | squad | creatures | party | levels | stats | **reads** |
|---|---|---|---|---|---|---|---|
| fresh | CRC 7D32D15A | 207 | rows 17,12,12,17 | 4 | **5/4/4/4** | ordinary | **25, 30, 30, 25** |
| god-mode lineage | CRC 7D32D15A | 207 | rows 17,12,12,17 | 4 | **5/4/4/4** | ordinary | **85, 90, 90, 85** |

Byte-identical ROMs, the same squad, the same creature rows, the same party size, the same party levels, both with ordinary stats — and a 60-point difference. **Party level is rejected**, and this time by a positive test rather than by elimination: the variable was deliberately moved to match and the offset did not follow.

**With one honest limit.** What was written is the level *field* (both copies — see `KNOWN_FORMATS.md`), not the progression that normally accompanies it. A quantity that merely correlates with level, such as accumulated XP, would not have moved. So *level-derived state* is still live; the level **number** is not the input.

**Standing after a full day on this question:**

| variable | how tested | verdict |
|---|---|---|
| party stats | normalized 259 → 10 on the +60 save | rejected (positive) |
| enemy count | 3 → 1, same save and squad | rejected (positive) |
| party size | 4 vs 4, opposite offsets | rejected |
| **party level** | **5/4/4/4 on both, same squad** | **rejected (positive)** |
| chapter-1 content | same ROM bytes, two saves | rejected (positive) |
| save-edit tooling | controlled `--godmode` diff, 0 runs outside party blocks | rejected |
| squad data | all 40 columns, +60 group vs 0 group | rejected |
| story progression | only ever via the NG+2 save | **weak** |
| New Game Plus | never checked on any save | **untested** |
| equipped Chao | never checked | **untested** |
| accumulated XP | never checked | **untested** |

**Next, and it costs nothing:** the file-select screen reports zone, chapter, **Chao count** and rings. The fresh save reads `0/40` Chao. Reading the same screen for the god-mode save gives the Chao count and chapter for free, and the Chao count is directly the untested candidate most specific to that save — it is the `chao_farm` lineage, built by converting a hundred-odd rings into Chao eggs. No fight required.

---

## 2026-10-11 — Chao and chapter cleared; bisecting the god-mode save's history

**Free readings from the file-select screen**, which reports zone, chapter, Chao count and rings:

| | levels | zone | chapter | Chao | rings | offset |
|---|---|---|---|---|---|---|
| fresh save | 5/4/4/4 | Green Hill | 2 | **0**/40 | 38 | **0** |
| god-mode lineage | 5/4/4/4 | Green Hill | 2 | **2**/40 | 97 | **+60** |

**Same zone, same chapter, same levels.** Story progression is therefore rejected on a comparison that owes nothing to the NG+2 save — the two are at the same point in the game. **Chao is all but rejected too**: the +60 save holds **two** Chao, not the hundred the `chao_farm` name suggests, and two Chao granting enemies 60 HP between them has no mechanism behind it. The remaining differences are 2 Chao and 59 rings, neither of which plausibly scales an enemy.

**So the offset is in that save's history, as the player has argued throughout.** Their account is specific: an earlier god-mode edit, made during the HP-curve work, before the current `--godmode` existed. That is testable by bisection, because every step of the lineage was kept:

| save | party | power | role |
|---|---|---|---|
| `playtest_god_mode.dsv.before-godmode` | 2 chars | 8, 13 | before any edit |
| `playtest_god_mode.dsv` | 3 chars | 257, 256, 9 | **the first god-mode edit** |
| `chao_level_test.dsv`, `character_randomizer_test.dsv` | 3 chars | 255 ×3 | intermediate |
| `chao_farm.dsv` → `control` / `enemy_count_probe` | 4 chars | 259, 258, 256, 10 | **shows +60** |

**Next experiment:** `lineage_probe.nds` carries a **copy** of `playtest_god_mode.dsv` — the earliest edited point, from exactly the session the player describes. Same squad shrink, so one short fight decides:

* reads **+60** → the first god-mode edit introduced it, and the cause is an early save edit, as the player suspected. The next step is diffing that save against its own `.before-godmode` for writes outside the party blocks.
* reads **0** → the cause entered *later*, between that save and `chao_farm`, and `chao_level_test` / `character_randomizer_test` bisect the remaining span.

Either way the search space halves, which is the first time today a single fight has been guaranteed to do that.

**Note on the earlier `.before-godmode` diff.** It was dismissed as uncontrolled because it showed hundreds of differing runs across the plot and inventory regions. That reasoning still holds for proving the tooling clean — but if the bisect lands on this step, that diff becomes the primary evidence and will need reading properly rather than being set aside.

---

## 2026-10-11 — Bisect step 1: the first two god-mode edits are both innocent

**Result:** `playtest_god_mode.dsv` — the earliest edited save, from the HP-curve session — fights the one-drone squad and reads **25 HP**. Offset **0**. The first god-mode edit did not introduce the offset.

**And the second edit is cleared from data, without a fight.** `playtest_god_mode.dsv` and `chao_level_test.dsv` sit at the same point in the game (both summary levels `[3,2,3,1]`), so the diff between them is close to a pure record of the edit. It shows **25 differing runs, every one inside a party stat block, a checksum, or the save-select summary — zero outside**. The second god-mode edit (Tails, from two god-moded characters to three) wrote only what it should.

So **no save edit in the lineage has planted anything**. Three separate checks now agree on that: the controlled `--godmode` diff, this one, and the in-play reading above.

| lineage step | party | offset |
|---|---|---|
| `.before-godmode` | 2 chars, ordinary | not measured |
| `playtest_god_mode` | 2 god-moded + Tails 57 + Rouge 42 | **0 (measured)** |
| `chao_level_test` / `character_randomizer_test` | 3 god-moded, levels `[3,2,3,1]` | **← testing now** |
| `chao_farm` → the +60 save | 3 god-moded + Rouge, levels `[5,4,4,4]` | **+60 (measured)** |

**What is distinctive about the remaining span.** Every earlier step was an *edit* between otherwise identical saves. The span from `chao_level_test` to `chao_farm` is the only one containing **real play** — Rouge is recruited, the party levels from 3/2/3/1 to 5/4/4/4, and this is the save the XP grinding measurements were taken on. Whatever the +60 is, it was acquired by playing, not by editing. That reframes it: the candidate is no longer "a corrupted byte" but **a legitimate piece of game state the save accumulated**.

The player's suggestion that the Tails edit was responsible is ruled out by the diff above, but the suggestion is what prompted checking that step directly rather than assuming.

**Next:** `lineage_probe2.nds`, carrying a copy of `chao_level_test.dsv` — the near end of the remaining span.

* reads **85** → the offset predates the `chao_farm` play session, and the cause sits between the Tails edit and there despite the diff showing no stray writes, which would mean it is something the diff cannot see as anomalous
* reads **25** → the offset was acquired during the `chao_farm` session itself, i.e. **by playing**, and the search narrows to what that session did: recruiting Rouge, levelling to 5/4/4/4, extensive grinding, and playing a ROM whose rings had been replaced with Chao eggs

---

## 2026-10-11 — Bisect complete: the offset was acquired by playing, not by editing

**Result:** `chao_level_test.dsv` reads **25 HP**. Offset **0**.

| lineage step | party | offset |
|---|---|---|
| `playtest_god_mode` | 2 god-moded | **0** |
| `chao_level_test` | 3 god-moded, levels `[3,2,3,1]` | **0** |
| `chao_farm` → the +60 save | 3 god-moded + Rouge, levels `[5,4,4,4]` | **+60** |

Every save edit in the lineage is now cleared, by three independent methods: a controlled `--godmode` diff, a step diff showing 25 runs all inside party blocks and checksums, and two in-play readings of 0. **The offset was acquired during the `chao_farm` play session**, by playing.

That session: recruited Rouge, levelled 3/2/3/1 → 5/4/4/4, ground out the XP measurements, and ran a ROM whose Green Hill rings had been replaced with 100 Chao eggs, with `Chaos.GDA` effect ids shifted 91-98 → 171-178 by `chao_level`.

**Party size is now properly rejected**, independent of the NG+2 save: the fresh save fields four characters at levels 5/4/4/4 and reads 0, against the same four at the same levels reading +60.

**The twin-save diff.** Two saves now sit at near-identical game state — Green Hill, chapter 2, levels 5/4/4/4, four characters — one at offset 0 and one at +60. Diffing them gives **235 differing runs in 10 clusters**, all within the first ~0x3900 bytes:

| region | span | bytes changed |
|---|---|---|
| 0x00203-0x002A1 | 158 | 69 (header / summary / checksums) |
| 0x0041C-0x00511 | 245 | 41 |
| 0x006AD-0x006BC | 15 | 6 |
| 0x00818-0x00871 | 89 | 14 |
| 0x00C8B-0x00C8E | 3 | 3 |
| 0x00EBC-0x013A5 | 1257 | 60 |
| 0x014BA-0x01D74 | 2234 | 76 (contains the party blocks) |
| 0x02E1E-0x02E9C | 126 | 38 |
| 0x032D7-0x0370F | 1080 | 166 |
| 0x03844-0x038DC | 152 | 16 |

Ten regions is a tractable binary search: build hybrid saves that transplant half the regions from the 0-offset save into the +60 save and fight once per split, roughly four fights to isolate the region. Worth holding in reserve rather than starting, because a cheaper test exists.

**Next experiment, one menu visit and one fight.** The two saves differ by **2 Chao against 0**. Chao was set aside earlier as implausible — two of them granting enemies 60 HP has no obvious mechanism — but it is the most save-specific difference left, and those particular Chao were obtained under a ROM where `Chaos.GDA` carried effect ids **171-178**, far outside the known stat range (`STATS` 0-36, resists 75-79, elements 107-112). An out-of-range effect id is exactly the kind of thing that produces an arbitrary constant.

Unequip both Chao on `enemy_count_probe.nds` and refight the one-drone squad:

* reads **25** → Chao drive it, and specifically Chao obtained under the shifted effect ids
* reads **85** → Chao are out, and the region bisection above becomes the method

---

## 2026-10-11 — Chao rejected; region bisection of the save begins

**Chao are rejected.** Both Chao unequipped on the +60 save, and the one-drone squad still reads **85**. The out-of-range effect id theory (ids 171-178 from `chao_level`) is dead, and so is the last cheap candidate.

Eight variables now rejected, five by positive test: party stats, party level, party size, enemy count, chapter-1 content, story progression, equipped Chao, the save-edit tooling — plus squad data from the GDA side.

**So the cause is read directly out of the bytes.** Two saves sit at near-identical game state (Green Hill, chapter 2, levels 5/4/4/4, four characters), differing in 235 runs across 10 clusters. Transplanting clusters from the offset-0 save into the +60 save and fighting once per split isolates the region by binary search, in roughly four fights:

| probe | regions replaced from the clean save | bytes |
|---|---|---|
| `hybrid_a.nds` | 0x00203-0x00C8E (clusters 1-5) | 510 |
| `hybrid_b.nds` | 0x00EBC-0x038DC (clusters 6-10) | 4,849 |

Both reseal clean. Everything outside the replaced regions is the +60 save unchanged.

Written before running:

* **`hybrid_a` reads 25** → the cause is in the first 510 bytes of differences, which is already small enough to read by hand
* **`hybrid_b` reads 25** → the cause is in the later clusters, and the next split is clusters 6-7 against 8-10
* **both read 85** → the offset is not carried by any byte that differs between these two saves, which would mean the saves differ somewhere the diff cannot see (a region excluded as "identical" because both happen to agree) or the state lives outside the 64 KB save entirely
* **both read 25** → more than one region contributes, and each must be split separately

This is the first method of the day with a guaranteed terminating condition rather than a list of guesses, which is what eight rejected hypotheses buys.

**Caveat on hybrids.** Transplanting bytes between saves can produce inconsistent game state — mismatched position, flags, or inventory. They are disposable probes for reading one number off a battle screen, not saves to play on, and anything odd about them outside that number is expected and uninformative.

---

## 2026-10-11 — Bisection step 1: the offset lives in the save's later half

**Result:** `hybrid_a` (clusters 1-5 replaced from the clean save) reads **85**; `hybrid_b` (clusters 6-10 replaced) reads **25**. The two answers agree, which also rules out the awkward outcomes written down beforehand — the state is carried by bytes that *do* differ between the saves, and by **one half only**.

The cause is somewhere in **4,849 bytes** across five clusters:

| cluster | range | bytes changed | note |
|---|---|---|---|
| 6 | 0x00EBC-0x013A5 | 60 | |
| 7 | 0x014BA-0x01D74 | 76 | contains the party stat blocks |
| 8 | 0x02E1E-0x02E9C | 38 | |
| 9 | 0x032D7-0x0370F | 166 | largest change count in the save |
| 10 | 0x03844-0x038DC | 16 | |

**Probes built for the next two steps**, so no further waiting between fights. All seven ROMs are byte-identical to the others (CRC 7D32D15A) and were copied rather than rebuilt; only the saves differ:

| probe | regions taken from the clean save |
|---|---|
| `hybrid_c` | 6 + 7 |
| `hybrid_d` | 8 + 9 + 10 |
| `hybrid_r6` … `hybrid_r10` | one cluster each |

**Procedure:** fight `hybrid_c`. A **25** puts the cause in cluster 6 or 7, a **85** puts it in 8, 9 or 10 (and `hybrid_d` need not be fought). Then fight the single-cluster probes from the surviving set until one reads 25. **Three fights maximum**, two likely.

**A prediction worth recording.** Cluster 7 contains the party stat blocks, and party stats and levels have both been rejected by positive test — so if cluster 7 turns out to carry the offset, something *else* in that span does, since 0x014BA-0x01D74 is wider than the blocks themselves. Clusters 8 and 9 sit well past the party data in a region this project has never examined.

---

## 2026-10-11 — Isolated to 16 bytes, and stopping there

**Bisection results:** `hybrid_c` (clusters 6+7) **85**, `hybrid_r9` **85**, `hybrid_r8` **85**. With `hybrid_b` (clusters 6-10) reading 25, the offset is carried by **cluster 10 — 0x03844-0x038DC, 16 changed bytes**.

That is by **elimination within the cluster set, not a positive test** — `hybrid_r10.nds` is built and would confirm it directly. Flagged rather than glossed because rule 1 exists precisely for this.

**What is in those 16 bytes.** Two structures are legible:

1. **A count at 0x038C4 followed by that many 2-byte entries.** The clean save reads **4**, the +60 save reads **5**, and the first four entries are identical in both — `(03,03) (04,03) (07,03) (06,03)`. The +60 save carries **one extra: `(13,03)`**, id 19, value 3.
2. **A lone `01` in an 0xFF-filled array**, at 0x03866 in the clean save and 0x038A2 in the +60 save — a position difference of 0x3C, which is 60. **Recorded as almost certainly coincidence**: offsets are not values, and four separate patterns today have fit the data perfectly and meant nothing.

**Stopping here, by agreement with the player**, who asked the right question: what is this for? The honest answer is that the question which justified the work — *is `enemy_scaling` broken, and does the game scale enemies behind the static table?* — **was answered hours ago and the feature passed**. On a normal save, enemy HP is exactly the `creatures.GDA` value at level 1 and at level 19. Everything after that point has been debugging one save that will not be played on, and it does not touch recruitment order (plot flags) or NG+ level curves (`Adv_*.GDA`), which are the project's actual open questions.

**What was bought, and it is not nothing:**

* `enemy_scaling` confirmed working in play for the first time since the HP-column fix.
* Nine variables rejected, six by positive test.
* The save-editing tooling cleared by controlled diff.
* `squads.GDA` member columns pinned to 5-8, with column 4 as the overworld appearance.
* Party level found to be stored **twice**, which would have silently broken any future level editing (`KNOWN_FORMATS.md`).
* The anomaly reduced from "something, somewhere" to **16 bytes with one identified extra record**.

**If it is ever picked up again,** the next three steps are: confirm cluster 10 positively with `hybrid_r10`; transplant *only* the 0x038C4 count-and-entries structure to see whether the extra `(13,03)` record alone carries it; and if so, identify what a 5-entry list of `(id, 3)` pairs with ids 3, 4, 6, 7, 19 describes. The probe ROMs and saves are all retained.

**Method note.** Nine rejections and not one confirmation is itself a result worth stating plainly: the project went looking for a mechanism and found that there is no *gameplay* variable behind this at all. That outcome was only reachable because the rejections were made properly, and the three that had to be withdrawn were withdrawn rather than defended.

**Confirmed positively 2026-10-11:** `hybrid_r10` — the +60 save with **only** cluster 10 (0x03844-0x038DC, 16 bytes) replaced from the clean save — reads **25 HP**. Cluster 10 alone removes the offset, so this is a positive result rather than the elimination the entry above recorded. The `+60` enemy-HP offset is carried by **16 bytes at 0x03844-0x038DC** of the save, most likely the count-and-entries structure at 0x038C4 whose extra record is `(13,03)`.

**Thread closed here.** It is a localized save anomaly, not a game mechanic, and it has no bearing on the project's open questions.

---

## 2026-10-11 — `randomize_characters`: a crash caught before the playtest, and the recruitment half built

**Investigated:** Both halves of the queued `randomize_characters` work — the per-move POW
deal that was built on 2026-10-10 and never played, and recruitment order, which had been
derived from `plt_fp_*.plo` and never confirmed.

### The POW deal was going to crash, and static verification found it

Diffing `combo.GDA` between vanilla and `build/character_randomizer_test.nds` showed the
deal itself was sound — 60 dealt rows, a true permutation, participant counts preserved,
nothing touched outside the playable blocks. But **seven rows had been handed an element
they shipped without**, because the deal moved whole row contents and the element column
traveled with them:

| row | slot | arrived carrying |
|---|---|---|
| 18 | Tails 1 | Tornado Kick, wind |
| **17** | **Shadow 6** | **Triple Tornado, wind** |
| 36 | Omega 1 | Whirlwind, wind |
| 39 | Omega 4 | Atomic Strike, electricity |
| 54, 55, 56 | Shade 1-3 | Flamethrower / Quake Punch / Blazing Tornado |

Adding an element to a move that lacks one is the operation `pow_move` **refuses
outright**, because it hard-crashed the battle twice on Focus Field. Row 17 is the same
character and the same added element as that crash. The guard existed, but it lived in
`pow_move` and `randomize_characters` never consulted it — one feature forbidding what
another did silently, seven times, in a build that was one play session away from being
tested.

**Fixed two ways.** `moves: "move"` now deals within **(participants, elemental)** rather
than participants alone, so elemental moves travel only into slots that were already
elemental and *which* element a slot has — the part that was always editable — is still
free to change. `moves: "character"` trades whole blocks and cannot be re-classed, so the
copy loop refuses to write an element onto a row that shipped without one; the move
arrives elementless instead. Rebuilt and re-verified: **zero rows gain or lose an
element**, and the five that change one all had one before.

A pleasant side effect: seed 1 no longer opens with two zero-damage support moves on
Sonic. His first two slots are elemental-and-solo and solo, so they now draw Machine
Gunner and Tornado Kick.

Also verified statically on the rebuild: the stat half is a derangement of all eleven
curves, whole lines across all 30 levels, with level, XP and the move-unlock columns
untouched.

### The dialogue-action lead: a clean negative, and the struct fully decoded

The 2026-10-10 entry left one cheap thing to try — whether the `.dlg` action structs
(templates 35/36, fields 12300-12305) carry a party-member id, which would make
recruitment data-editable directly. **They do not.** All six fields are now accounted for
and every one is a plot/flag reference; there is no opcode and no creature id. Field
**12305 is the `plots.GDA` row index** of the plot its GUID names — confirmed by lookup,
not inference: structs naming `plt_fp_big.plo` carry 38, structs naming
`plt_a2_stronghold.plo` carry 36, and `plots.GDA` maps those indices to exactly those
files. A node can gate on a flag and set a flag, and nothing else. Full layout in
KNOWN_FORMATS.

So recruitment stays a flag the dialogue sets and ARM9 reacts to. The lead is closed.

### Recruitment order, built — and it never needs the order confirmed

The route that works is the one Shadow Mode already proved: **recruitment grants a
creature row, not a character**, so the Chapter 4 point that normally hands over Shadow
hands over whatever lives in row 4. That was confirmed in play on 2026-10-07. The new
`recruitment` half generalizes that single 2-cycle to a derangement of all eleven playable
rows.

The design question was which columns travel. Answered empirically: 42 of 61 columns
differ between at least two playable rows, and Shadow Mode's proven set is exactly "every
column that differs, minus id, playerid, class, the two dialogue portrait fields and the
map-pin icon". Two more are pinned here, and they are the point:

**Movement abilities (19/20/21) and their companion flags (39/40/41) stay with the
slot.** Columns 39/40/41 were identified on the way — each reads -1 at exactly the empty
slots, across all eleven rows. Pinning the group means every recruitment point grants the
abilities vanilla granted there, so the ability timeline is unchanged and no obstacle gate
can become impassable.

This is what makes the half buildable *now*. The roadmap's invariant — for every prefix of
the recruitment order, the party can field at least vanilla's abilities — is satisfied
**without consulting the order**, which matters because the order derived from
`plt_fp_*.plo` is still a derivation and per evidence-standards rule 1 is not something to
build on. The design sidesteps the unconfirmed input rather than depending on it.

Pinning the slot alone is not sufficient, though: the progression table travels with the
identity (column 34) and carries the donor's ability-*level* schedule in columns 12/13/14,
and the gates demand specific levels — Dash 0/1 and Smash 2 are the only ones that appear
on a placeable. Since the deal is a permutation of the same eleven tables, each table is
rewritten exactly once with the schedule its new row had in vanilla.

**Statically verified on `build/recruit_order_test.nds` (seed 1):** a true derangement of
all eleven rows; all twelve pinned columns untouched; the 117 non-playable creature rows
untouched; and **the ability a slot grants, at every one of the 30 levels, identical to
vanilla for all three slots** — checked cell by cell, not argued.

Seed 1 deals: the starting row holds **Rouge**, Amy's point gives Knuckles, Tails' gives
Shade, Knuckles' gives Eggman, Shadow's gives Amy, Rouge's gives Tails, Big's gives Sonic,
Cream's gives Big, Omega's gives Shadow, Eggman's gives Omega, Shade's gives Cream. So
Sonic becomes an optional side-quest recruit.

**Confidence:** the mechanism is confirmed in play for one pair; the generalization and
both column sets are build-verified only. Dialogue portraits are knowingly wrong — a
conversation shows the slot's original face while the party screen, overworld model and
battle portrait show who you actually have. That is the safe side of a known crash, not an
oversight.

**What is still unconfirmed, and what would confirm it:** that an eleven-way identity
permutation behaves in play the way the single swap did. The decisive early reading is the
starting character — a new game on `recruit_order_test.nds` should open as Rouge, with
Rouge's model in the overworld, Rouge's stats on the party screen, and Dash still
available at the first Dash obstacle. If the model and the ability both come out right
there, the mechanism has generalized and the rest is the same operation repeated.

---

## 2026-10-11 — First playtest of both halves: recruitment works, one real bug, and a claim withdrawn

**Tested in game** (`character_randomizer_test.nds`, level 19 save; `recruit_order_test.nds`,
new game).

### Confirmed

* **The POW menu deals correctly.** Tails' list read Low Blow, Jewel Storm, Froggy Poison,
  Scan, Feel No Pain, Beam Cannon — six moves from six different characters, matching the
  prediction written before the test, with the right icons and descriptions.
* **The recruitment half works.** A new game opened as **Rouge**, the first obstacles were
  passable with Dash, Amy's cutscene played as Amy (expected — portraits are pinned) and
  handed over **Knuckles**. The eleven-way identity permutation therefore behaves the way
  the single Sonic/Shadow swap did on 2026-10-07, which is the generalization confirmed.

### BUG, found in play and fixed: every dealt move demanded the wrong character

Rouge, in the starting row, could not use her own **solo** moves without Tails; Knuckles
needed Eggman. Reproduced statically and it was all eleven rows, systematically.

The cause is the 2026-10-10 finding applied one step further than it had been. An identity
brings its move block with it, because `creatures.GDA` 22-27 are pointers — but
`combo.GDA` column 2 is a *participant requirement in party-slot space*, and it stayed
behind. A block that moved to another row therefore demanded whoever now occupies the slot
it came from. Rouge's block asks for slot 5, and slot 5 now holds Tails.

Fixed by remapping owner and partner references through the same permutation, so a
team-up move names the same *character* it was authored for at their new slot. Verified on
the rebuilt ROM: all 60 moves demand the character who holds them, participant counts
unchanged, no move names a slot twice, and the team-ups still read Sonic + Tails for Blue
Bomber and Sonic + Knuckles + Tails + Amy for Hail Storm.

Both halves can touch those columns, so they are now computed once and emitted at the end
rather than written twice with the later write silently winning.

### The move animation is positional, and that is confirmed by naming

Shadow's first slot holds Uppercut in every column except the row id, the owner and the
art prefix — damage, cost, status, element, name, description, icon and tier text all
moved, verified in the built ROM. It performed Chaos Spear.

The archive explains it. Solo POW animations are **`<CHAR>_CB_PAttack<N>.nsbca`**, keyed by
performer and slot index — Shadow has three for six moves, Sonic two — and team animations
are **`C_<cast>_<who>.nsbca`** (`C_KnShaShe_Kn`). Named effects follow the same scheme
(`FX_SHA_Rift_prj`, `FX_SHASON_Atom`). **Nothing in the archive is named after a move.** So
the performance is addressed by who is acting and with whom, and no column edit can move
it. This is a positive identification from the resource names, not an elimination.

**Incidental correction:** column 33 was described in `features.py` as an animation bank
prefix. It is not. The only `BIF*` resources are twelve `bif_<CHAR>.nbfs`/`.nbfp` pairs — a
tilemap and palette, one per playable character — so it names a per-character image.
Pinning it remains right, for the plainer reason that character art belongs to the
character.

### WITHDRAWN: "a dealt move's mechanics travel completely"

Written earlier today on the strength of the column diff. The player reports the move
landed **two damage instances where Uppercut lands one** — Chaos Spear's structure, not
Uppercut's. Column 49 is set on exactly two of the sixty playable moves, Machine Gunner
and Chaos Spear, which are precisely the two that fire several shots; it travelled and
reads 0 on that row in the built ROM. So the hit structure came from somewhere the deal
does not reach.

A verified column diff shows what the *table* says, and that is not the same as what the
engine *reads* — exactly the distinction evidence-standards rule 1 exists for, and the
diff was treated as if it settled behavior. It does not.

**Open, and the next measurement:** whether the damage *numbers* travel. A dealt move doing
a normal chunk of damage means the data applies and only the performance does not; a dealt
move doing a couple of points means the damage columns are not reaching the engine either.
Until that is measured, `moves` is confirmed only as far as the menu.

---

## 2026-10-11 — The POW deal crashes, and the move's identity is positional

**Four more readings from the same session**, all on `character_randomizer_test.nds`:

| slot | vanilla | dealt | result |
|---|---|---|---|
| Shadow 1 | Chaos Spear (`2x 100%`) | Uppercut (`135%`, 1 hit) | **two** ticks of 148 |
| Shadow 2 | Chaos Rift | Tinker | Chaos Rift's animation, **Tinker's effects** |
| Shadow 3 | Chaos Blast (`150%`) | Refresh (support) | **HARD CRASH on use** |
| Eggman 1 | Bombardment (`200%`, 1 hit) | Chaos Spear (`2x 100%`) | Bombardment's animation **and damage**, one tick |

Plus, from the first reading: Shadow's "Uppercut" used **Chaos Spear's POW minigame** — the
same clicks and slider.

### What is now confirmed

**A POW move's identity lives at its `combo.GDA` row position, not in its cells.** Four
independent properties stay with the slot while the data is replaced: the animation, the
minigame, the hit count, and — on the Eggman reading — the damage magnitude. Vanilla
Chaos Spear is authored `2x 100%` and Uppercut `135%` in one hit; the dealt rows produced
their *slot's* hit count both times, in opposite directions.

The minigame is the reading that settles it. An animation could plausibly be a lookup we
had not found; a per-move stylus pattern is the move's own interaction, and it did not
move with the data.

**And the deal can crash the game.** Cream's Refresh, dealt into Chaos Blast's offensive
slot, hard-crashed on use. Column 55 marks a move as support and tracks "deals no damage"
on 58 of the 60 playable moves, so the line crossed is (offensive slot, support move) —
the same shape as `ELEMENTLESS_ADD_IS_UNSAFE`, a property of the slot that the arriving
move must match, with no known mechanism. Tinker, dealt into Chaos Rift's slot, did *not*
crash, and Chaos Rift is the one 0-damage move that is not support-flagged: the pair that
worked and the pair that crashed differ in exactly that column.

Column 55 is now part of the deal's class. It costs three moves out of sixty.

### What this means for `moves`

The content deal is the wrong mechanism. Copying cells into a row produces a vanilla move
wearing another move's name, icon, description and status effect — which is why Tinker
"seemed to do Tinker's effects" while Eggman's "Chaos Spear" did Bombardment's damage in
one tick. The status effect columns point into `spells.GDA` and are read; the performance
is not.

The 2026-10-10 lesson was "a moveset is bound to its block position." We took half of it —
stop permuting the owner column — and missed the other half: **move the pointer, not the
contents.** `creatures.GDA` 22-27 are the slots, and the recruitment half already moves
them, which is why Rouge arrived in the starting row with six working moves.

### The probe that decides it

`profiles/pow_pointer_probe.json` — four cells on a clean ROM, no contents copied.
Shadow's slot 1 points at Knuckles' Uppercut row and his slot 3 at Cream's Refresh row,
and those two rows are re-owned to Shadow so he can use them alone. His other four slots
are untouched and are the in-ROM control.

Written before the test:

* **Slot 1 → Uppercut's row.** If identity is positional, Shadow performs a real Uppercut:
  one tick, Knuckles' minigame, 135%. If instead the performance is keyed by *performer
  and slot index* rather than by row, he performs his own slot-1 Chaos Spear routine
  carrying Uppercut's numbers — in which case no data edit can move a move at all, and
  POW randomization is impossible without ARM9 work.
* **Slot 3 → Refresh's row.** This is exactly the pair that crashed. If it works, the
  crash belongs to content copying and the pointer route is sound. If it crashes too, the
  slot index itself carries the offensive/support expectation and neither mechanism can
  cross it.

The two outcomes are independent and the build answers both at once.

---

## 2026-10-11 — RESULT: POW moves cannot be moved by editing data. Both mechanisms rejected.

**The pointer probe came back negative, and so the question is closed.**

`pow_pointer_probe.nds` repointed Shadow's slot 1 at Knuckles' Uppercut row and his slot 3
at Cream's Refresh row — four cells, **no row contents copied anywhere**. In play:

* **Slot 1 still played Chaos Spear's animation and Chaos Spear's clicks and slider.**
* **Slot 3 still used Shadow's clicks, and still crashed.**

Both outcomes were written down before the build, and both are the failing branch.

### What is now established, by positive test on two independent mechanisms

**A POW move's performance is keyed by `(performer, slot index)`.** Not by the
`combo.GDA` row's contents — copying them does nothing — and not by which row the
character's slot points at — repointing does nothing either. The animation, the stylus
minigame and the hit count all come from that pair. This matches the archive exactly,
where the only POW animations are `<CHAR>_CB_PAttack<N>.nsbca` and `C_<cast>_<who>.nsbca`
and nothing is named after a move.

What `combo.GDA` supplies is the **label and the effect**: name, description, icon, tier
text and the status effect, which points into `spells.GDA` and was observed applying
(Tinker's effects showed up on Chaos Rift's animation).

**The crash belongs to the slot, not to the mechanism.** A support move in an offensive
slot hard-crashes on use whether it arrives by content copy or by pointer. So it is a
property of the slot, like `ELEMENTLESS_ADD_IS_UNSAFE`, and no amount of care in *how* the
move is placed avoids it — only not placing it there.

### Consequence

**Moveset randomization is out of reach of data editing.** It would need ARM9 work, and
the melonDS GDB route is where it would start — breakpoint on the POW execution path and
find what consumes the `(character, slot)` pair. That is parked, not scheduled; nothing
else in the roadmap depends on it.

`moves` now defaults to **false** and is documented as what it is: a retune, which changes
a move's name, description, icon, numbers and status effect while leaving the performance
alone. It is crash-gated but no longer presented as a moveset shuffle.

**What reaches the same goal from the other side is `recruitment`, which works.** It
changes the *performer*, and the performer is half the key. A run that opens as Rouge
opens with Rouge's six moves performed properly, because the engine's positional lookup
now resolves to Rouge. Moveset variety per run is therefore delivered — just not by
dealing moves.

**Small open question, free to answer:** whether a transplanted identity performs its own
animations because the engine keys off `appearance` (column 14, which travels) or off the
creature row index (which does not). The recruitment ROM answers it on sight — if Rouge in
the starting row performs Rouge's attacks rather than Sonic's, it is appearance. Worth
noting next time that ROM is played; not worth a run of its own.

**CONFIRMED, same session — the performer half of the key is `appearance`.** On
`recruit_order_test.nds`, Rouge in the starting creature row performs her own Tornado
Kick, and Knuckles in Amy's row his own Uppercut; the movesets are coherent throughout.
So the engine resolves the performer through `creatures.GDA` column 14, which travels with
an identity, and not through the creature row index, which does not.

That completes the model and explains the whole thread in one line: **the POW lookup key
is (appearance, slot index), and `recruitment` is the only edit that moves either half of
it.** Dealing move data changes neither, which is why four playtests of `moves` all
returned the slot's own move.

`recruitment` is therefore confirmed in game on every claim made for it: starting
character, ability gates passable, a story point handing over the right character, move
requirements naming the right partners, and animations correct. The one piece of
`randomize_characters` still never played is `stats`, which is on by default and only
shows on a level-up.

---

## 2026-10-11 — Abilities become a floor, and `animations.GDA` reopens the moves question

### Movement abilities: the slot's own, plus whatever else fits

The invariant was being satisfied too literally. "For every prefix of the recruitment
order the party can field at least vanilla's abilities" is one-directional — a slot must
not grant *less*, and nothing stops it granting *more* — but `recruitment` pinned the
ability slots outright, so a character arriving anywhere lost every ability they had.

Now the slot's vanilla abilities are kept in their vanilla positions on their vanilla
schedules, and the arriving character's own fill whatever slots are left. Three slots is
the hard limit, and the surplus is dropped in the character's own slot order; a required
ability is never what gets dropped. The `Adv_*` level columns are written per slot from
whichever table authored that ability's schedule — the taker's for a required ability, the
donor's for a bonus one.

Seed 1 now gives: the starting row holds Rouge with **Dash** (required) plus Fly and
Stealth; Amy's point gives Knuckles with **Smash and Dash** plus Climb; Big's point gives
Sonic with **Invulnerable** plus Dash; Eggman's point, which requires nothing, gives Omega
with his own Smash and Invulnerable instead of nothing at all.

Verified on the built ROM: no slot loses a required ability, none is under-levelled at any
of the 30 levels, and the companion-flag rule (1 on an occupied first slot, 0 on an
occupied second or third, -1 on an empty one) holds throughout.

### `animations.GDA` — the table we had never opened

Searching every GDA for a string matching a POW animation name turned up
**`animations.GDA`, 56 rows and 103 columns, and it is transposed**: the *columns* are
per-character animation sets and the *rows* are animation slots.

Row 22 is POW slot 1. It holds `SHA_CB_PAttack01` in column 64, `KNU_CB_PAttack1` in
column 7, `SON_CB_PAttack01` in column 16, `CRM_CB_PAttack01` in column 13. Reading
Shadow's column down the POW rows gives `PAttack01, PAttack02, PAttack03, C_SoSh_Sh,
C_ShaOm_Sha, C_ShaRoOm_Sha` — which is exactly his six moves in slot order, including the
right team combos for Atomic Strike (Shadow+Sonic), Focus Field (Shadow+Omega) and Metal
Storm (Shadow+Rouge+Omega). The match is too complete to be coincidence.

**So the performance is data after all — just not data in `combo.GDA`.** That is why both
earlier mechanisms failed: copying move cells and repointing move slots both leave this
table untouched.

**Still unknown:** how a creature reaches its column. It is not `appearances.GDA` column 3
(the `GenKnuN_AA` / `BIG_AA` names do not hash to any animations column), and no
appearances column holds 64 for Shadow or 7 for Knuckles. A probe does not need the
answer, though — editing the cell works whatever the path to it is.

### The probe

`profiles/pow_animation_probe.json` — **one string cell**, Knuckles' slot-1 clip written
into Shadow's slot-1 cell on an otherwise clean ROM. Shadow's first move is still Chaos
Spear in every data respect, so anything that changes is caused by that cell, and the
player already knows what the move normally looks like.

Written before the test:

* **Shadow performs Knuckles' uppercut animation** → the animation is data, and
  `animations.GDA` is the lever. If the **clicks and slider change with it**, the whole
  performance is data and moveset randomization is achievable after all.
* **Animation changes, minigame does not** → the minigame is separate and still
  unlocated; partial progress.
* **Nothing changes** → the engine does not read this table for Shadow's slot 1, and the
  moves question goes back to ARM9.
* **Crash** → animations are bound to their skeleton and cannot cross characters, which
  caps what any animation edit can do.

---

## 2026-10-11 — The animation probe lands, and the minigame is a separate system

**Result (in play):** Shadow began Knuckles' animation, **stopped just before the uppercut
itself**, reverted to his own chaos-spear charge, and then the whole move cancelled with
nothing happening. The clicks stayed Chaos Spear's throughout, and the cancellation came
just before Chaos Spear's diagonal slider.

### Confirmed: `animations.GDA` drives the POW animation

One string cell changed the animation, so the engine reads this table for Shadow's slot 1.
That is the positive confirmation the two earlier probes failed to produce, and it
overturns the 2026-10-11 conclusion that the performance was beyond data editing — it is
data, it was simply in a table nobody had opened.

**And the table names its own rows**, which removes the guesswork entirely. Reading the
label column: row 22 `CB_PAttack`, row 13 `POWER MOVE 2`, row 24 `POWER MOVE 3`, row 25
`POWER MOVE 4`, row 26 `POWER MOVE 5`, row 27 `POWER MOVE 6`, and rows 28/29/42/46
`COMBO SUPPORT 1`-`4`. Columns are per-character animation sets: Knuckles 7, Tails 8,
Amy 9, Rouge 11, Big 12, Cream 13, Omega 14, Eggman 15, Sonic 16, Shadow 64, Shade 89.
The rest of the 56 rows are the ordinary states — `EX_WALK`, `CB_IDLE`, `CB_DAMAGE`,
`EX_DASH`, `EX_CLIMB`.

### Confirmed: the animation and the stylus minigame are separate, and must agree

The move did not crash; it **aborted**. The minigame stayed Chaos Spear's while the
animation became Knuckles', and execution stalled at the step where the two no longer
lined up — just before the slider. So the minigame is keyed somewhere else, and the engine
advances the move by matching the two against each other.

That is a better failure than a crash: it means an animation edit is recoverable, and that
a *matched* pair should work.

### Identified: `realtime.GDA` is the minigame's step table

65 rows, 16 columns, one row per input step. Column 1 is the step type (3 = a tap at the
(x, y) in columns 3/4, 4 = a traced gesture, 5 = a second tap variant), column 7 is the
time allowed, and **column 8 names the gesture path**: `CCW_SE_NE.gff` — counter-clockwise,
south-east to north-east — is the diagonal slider the move cancelled in front of. Other
rows name themselves after moves outright: `Son_AxeKick.gff`, `Son_BlueBomber_0.gff`,
`Amy_Crush.gff`. Columns 9/10 are speed and scale; columns 11-15 are the same five
`CFX_rtip1_rt*.emit` sparkle effects on every row.

**What is still missing is the sequence** — what tells a given move to run steps *these*
and in *this* order. It is not `combo.GDA` columns 19 or 54: both travelled in the deal and
the minigame did not change with them. Finding it is the last piece, and it is an offline
search rather than a playtest.

### Testing aid: `profiles/recruit_order_fastxp.json`

A 20x XP acceleration layered on `recruit_order_test` with `extends`, so a recruitment
shuffle can be checked without a playthrough — level 10 costs 607 XP instead of 12,149 and
level 20 costs 20,047 instead of 400,935. It touches the threshold column and nothing
else: verified that `creatures.GDA` is byte-identical to the plain build, so identities,
abilities and unlock levels behave exactly the same. It is a testing ROM, not a play ROM.

---

## 2026-10-11 — Where the POW minigame is not, and recruitment signed off

### Recruitment is finished

The ability floor was confirmed in play. At level 5 the starting row (Rouge) showed two
movement abilities with Stealth still pending, which is exactly the authored schedule —
Dash and Fly reach level 1 immediately, Stealth only by level 10. Amy's row (Knuckles)
likewise showed two, with Dash still to come at level 10.

The progression tables also travel correctly: Rouge's level-5 line read Spd 11 / Atk 16 /
Def 25 / HP 88 and Knuckles' Spd 12 / Atk 12 / Def 20 / HP 107, matching `Adv_Rouge` and
`Adv_Knuckles` cell for cell. (Luck reads +4 against the table on *both*, consistently, so
that is a flat offset on that stat rather than anything the shuffle does. Noted, not
chased.)

Known and accepted cosmetic limits, all recorded earlier: dialogue portraits and the class
label stay with the slot (Rouge reads "Power Class" because that is Sonic's row), story
text names characters in authored TLK strings, and the bosses keep their own move rows.

**Nothing is outstanding.** The one untested piece of `randomize_characters` is `stats`,
which is a separate half and not part of recruitment.

### The minigame sequence: six places it is not

The stylus sequence that binds a POW slot to its `realtime.GDA` steps was searched for and
**not found**. Eliminated, each by evidence rather than by looking and shrugging:

* **`combo.GDA`, any column.** Every non-pinned column travelled in the content deal and
  the minigame did not change with them; the pointer probe then redirected the slot to a
  different row entirely and the minigame still did not change. So it is keyed neither by
  the row's contents nor by the row's index.
* **`animations.GDA`.** Its cells are animation names, and changing one changed the
  animation while leaving the minigame alone — which is what separated the two systems in
  the first place.
* **`realtime.GDA`.** 65 rows, each a single input step; nothing orders them.
* **`RealtimeWidgets.GDA`** (named by the `2DA.GDA` registry and never opened before). Six
  rows of button art — `CBT_BTN_Success.GUI`, `CBT_BTN_PathDot.GUI`.
* **The 31 gesture `.gff` files.** All present in the archive, all 692 bytes, and all pure
  path geometry: two strokes of start/end coordinates plus 21 sample points. The one
  struct that looked like it might hold references (`71050`-`71061`, twelve slots) is -1
  in every file.
* **The `2DA.GDA` registry**, which names only `realtime.GDA` and `RealtimeWidgets.GDA`
  for this subsystem.

**The residual is ARM9**, and per evidence-standards rule 1 that is a residual and not a
finding: the above are ruled out, the location is unknown, and the positive test would be a
melonDS GDB session breakpointing the POW execution path to see what consumes the
`(character, slot)` pair.

### What this leaves

`animations.GDA` is a real and confirmed lever, but on its own it only desynchronises a
move — animation and minigame must agree or the move aborts. So **POW randomization beyond
changing the performer is blocked on ARM9 work**, and changing the performer is what
`recruitment` already does: an eleven-way shuffle of who holds which coherent moveset,
animations and minigames intact. That is the deliverable, and it works.
