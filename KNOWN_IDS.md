# Known IDs

Named identifiers confirmed against our own ROM, with source and confidence noted. See [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md) for how each was found.

## Sound/music bank constants (from `sound_data.sadl`)

**Confidence: high that these names/values exist verbatim in the ROM** (directly extracted text) — **unconfirmed** which in-game events actually trigger each one. This is a leftover developer C header, shipped by accident into the retail ROM root (`/sound_data.sadl`, 12,924 bytes). Full text at `research/phase0/sound_data_sadl.txt`.

Player/engine constants:
| Name | Value |
|---|---|
| `SFX_PLAYER` | 10 |
| `MIDI_PLAYER` | 11 |

Combat/UI/exploration sfx groups (first set — appears to repeat under a second naming scheme later in the file, not yet reconciled):
| Name | Value |
|---|---|
| `sfx_arcgui` / `sfx_gui` | 0 |
| `sfx_arcxpl` / `sfx_xpl` | 1 |
| `sfx_arccbt` / `sfx_cbt` | 2 |
| `sfx_arccbt_1`…`sfx_arccbt_5` / `sfx_cbt_act1`…`sfx_cbt_act5` | 3–7 |

Background music banks:
| Name | Value |
|---|---|
| `bgm01_wavearc` … `bgm13_wavearc` (also seen as `bgmusic01`…`bgmusic13`) | 8–20 |

Overworld map ambience:
| Name | Value |
|---|---|
| `s_map_1_1arc` … `s_map_1_6arc` | 21–26 |
| `s_map_2_1arc` … `s_map_2_7arc` | 27–33 |

Interior/area ambience (naming pattern `int_<area>_<stage>_i<NN>arc`, e.g. `int_a2_s7_i02arc` = Area 2, Stage 7, interior ambience #2):
| Name | Value |
|---|---|
| `int_s1_i01arc` … `int_s5_i04arc` | 34–45 (Area 1 stages) |
| `int_a2_s1_i01arc` … `int_a2_s7_i03arc` | 46–56 (Area 2 stages) |

The `a2_s7`, `a1_s1` style area/stage naming also appears directly as filenames elsewhere (e.g. `a1_s1_ex.2da`, `a2_s7_ex.are` in `research/phase0/herf_test_contents.tsv`) — this is a reusable convention: **`a<area>_s<stage>`** identifies a chapter/zone throughout the game's data, not just in audio.

**Open question:** two near-duplicate naming schemes appear in the same file (`sfx_arc*` vs `sfx_*`, `bgm*_wavearc` vs `bgmusic*`) with overlapping values — not yet clear whether these are two independent ID spaces (e.g. one for an SDAT bank index, one for a wave-archive index) or just an old/new naming pass left in by the developers. Needs the full file reviewed, not just the excerpt above.

## Stat IDs (`SData1` in `.itm` / `.spl` effect tables)

**Confidence: high.** Confirmed independently by **two** file families: all 219 `.itm` and all 151 `.spl` files. The two use *different label spellings* (`SPD+` vs `SPEED+`, `LCK+` vs `LUCK+`) yet agree on every numeric ID with zero contradictions, always alongside `EffectId=1`. See [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md) for method and counts.

| ID | Stat | Labels seen |
|---|---|---|
| 0 | HP | `HealHP`, `HP+`, `HP-` |
| 21 | SPD (Speed) | `SPD+`, `SPEED+` |
| 22 | ATK (Attack) | `ATK+`, `ATK-`, `ATK++` |
| 23 | DEF (Defense) | `DEF+`, `DEF-`, `DEF++` |
| 24 | MAXHP | `MAXHP+`, `MAXHP++` |
| 25 | POW | `POW+`, `POW-`, `POW++` |
| 26 | GRT (Grit) — **player-facing name is "Armor"** (see below) | `GRT+`, `GRT-`, `GRT++` |
| 27 | LCK (Luck) | `LCK+`, `LUCK+`, `LUCK-` |
| 28 | FP / FATIGUE — **displayed in game as "PP"** (POW Points) | `HealFATIGUE`, `FP+` |
| 36 | MAXFP | `MAXFP+`, `FPMAX+` |
| 48 | AP | `AP+` |
| 122 | COMBODISCOUNT (reduces PP cost of POW moves) | `COMBODISCOUNT+` |
| 123 | NUMACTIONS (actions per turn) | `NUMACTIONS+` |

**"FP" = Fatigue Points** — items reach stat 28 via `HealFATIGUE`, spells via `FP+`; same ID, two naming conventions.

**Stat 25 (POW) is the damage stat, confirmed by in-game descriptions** — Kron Hammer (`POW+5`): *"Very greatly increases damage"*; Chao Print Dress (`POW+2`): *"Moderately increases damage"*. ATK (22) governs accuracy, not damage. Neither POW nor GRT is shown anywhere in the UI.

**Stat 26 (GRT) is displayed to the player as "Armor"** — confirmed in game. `Item34.ITM` (SpeedySneakers) grants exactly `SPD+3` and `GRT+1`, and its in-game description reads *"Light and well cushioned for more agility. Slightly increases armor."* — "agility" ↔ SPD, "armor" ↔ GRT. Both `Grit` and `Armor` exist as standalone strings in the TLK, so the engine has display labels for both names.

**Stat 26 does not appear in the item tooltip's numeric stat list.** Observed in game with a build setting every item bonus to 99: SpeedySneakers displayed only `Speed +99`, never a Grit/Armor line — and the user confirms this matches vanilla behaviour. The item's two effect rows are byte-for-byte identical in structure apart from `SData1`, so nothing in the data suppresses it; this is UI behaviour. Of the 24 items whose *only* stat bonus is `GRT+`, most are Chao items, consistent with Grit being treated as a secondary stat surfaced through prose rather than the tooltip.

**Consequence for Phase 8 (equipment overhaul):** rebalancing Grit/Armor is invisible in the item tooltip, so such changes won't communicate themselves to the player. Note also that item *descriptions* are hand-written TLK strings that do **not** update when stat data changes — a rebalanced item keeps describing its old behaviour unless the string is edited too.

**Resolved by experiment (observed in game):** a test ROM retargeted SpeedySneakers' first row to stat 26 and its second row to stat 22, both at 99. The tooltip showed **`Attack +99` and nothing else** — the second row rendered (so the tooltip is not limited to the first row) while the stat-26 row rendered nothing. **The tooltip specifically excludes stat 26.** See [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md).

Which other stats the tooltip hides is not yet mapped — only 21 (Speed) and 22 (Attack) are confirmed visible, and 26 confirmed hidden. Worth checking before building an equipment pass around any stat.

Gaps in the numbering are stats not referenced by any item or ability effect — they may still exist. This table is "every stat an item or ability can modify", not necessarily "every stat the game has".

## Element IDs

**Confidence: high for the resistance block** (from 11 consistent `RESIST_*` rows each across `.spl`), **inference for the second block**.

Elemental **resistance** (`SData1` on `RESIST_*` rows in `.spl`, and on `ELEMENT` rows in 15 items granting `Data=50` resistance):

| ID | Element |
|---|---|
| 75 | Fire |
| 76 | Water |
| 77 | Earth |
| 78 | Wind |
| 79 | Lightning — **the label is `RESIST_LIGHTING` (developer typo); match it exactly** |
| 80 | Ice |

No item grants Ice (80) resistance — item `ELEMENT` rows only use 75–79.

**Elemental attack affinity — CONFIRMED** (was previously an inference). A second six-wide block, `107`–`112`, appears on `ELEMENT` rows with `Data=1`. The in-game item descriptions state it outright — Fire Ring: *"Gives Fire damage to basic attacks"*:

| ID | Element | Item |
|---|---|---|
| 107 | Fire | Fire Ring |
| 108 | Water | Water Ring |
| 109 | Earth | Earth Ring |
| 110 | Wind | Wind Ring |
| 111 | Lightning | Lightning Ring |
| 112 | Ice | Ice Ring |

Both blocks run in the same element order (Fire, Water, Earth, Wind, Lightning, Ice): **75–80 = resistance, 107–112 = attack affinity**.

**Multiple attack-affinity rows on one item all apply** (confirmed in game via the Omni Ring build): the engine evaluates every `ELEMENT` row against the target's resistances and surfaces only the effective ones. There is no limit of one element per item. Six Chao (Chao 10–15) also grant attack affinity; Chao 16–20 grant resistance.

## Status effects

**Confidence: high for the list** — decoded from `Statuses.GDA` with names resolved through TLK string references. See [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md).

| ID | Status |
|---|---|
| 0 | Dead |
| 1 | Paralyzed |
| 2 | Tinkered |
| 3 | Poisoned |
| 4 | ATKdown |
| 5 | DEFdown |
| 6 | ACCdown |
| 7 | EVAdown |
| 8 | LCKdown |
| 9 | ATKup |
| 10 | DEFup |
| 11 | ACCup |
| 12 | EVAup |
| 13 | LCKup |
| 14 | unnamed (name string ref = -1) |
| 15 | unnamed (name string ref = -1) |

16 statuses total, matching the ~16-bit `RemoveStatus` mask width. This also reveals two stats absent from the item/ability stat-ID table above: **ACC (accuracy)** and **EVA (evasion)**.

### Bitmask correspondence — still open

`RemoveStatus.Data` is a bitmask (observed: 16/32/64/128 individually on items; `1022` on `Spell_Antidote_All`; `131070` = `0x1FFFE` on full cures/revives). The status list is now authoritative but **which bit maps to which status is not confirmed**: the obvious `1 << id` reading yields non-intuitive pairings (it would have the ATK-boosting `RockSalt` cure ATKdown while the ATK-boosting `PruneJuice` cures ACCdown). Needs a live in-game or debugger test, not more inference.

## Effect IDs (`EffectId` column in `.itm` / `.spl`)

**Confidence: medium-high** — consistent across all observed rows, but inferred from the row labels they appear with rather than from engine code.

| EffectId | Meaning |
|---|---|
| 0 | metadata row (`SpellData`, `CollectionData_Equip`, `CollectionData_Use`) |
| 1 | modify stat/resource — target stat in `SData1`, amount in `Data` |
| 5 | VFX |
| 6 | heal / resurrect family |
| 7 | `RemoveStatus` |

## Status effect bitmask (`RemoveStatus.Data`)

**Confidence: medium** — the bitmask nature is clear, the per-bit meanings are not.

`RemoveStatus` rows carry a bitmask in `Data`: individual values 16, 32, 64, 128 target specific statuses, and `131070` (`0x1FFFE` = bits 1–16 set) appears to mean "remove all". Which status corresponds to which bit is **not yet identified**.

## Filename → resource hash dictionary (`test.herf`)

Not "IDs" in the gameplay sense, but a confirmed, complete mapping worth recording here as the canonical reference: `research/phase0/herf_test_contents.tsv` contains all 8691 resources in the main archive — name, DJB2 hash, size, offset-in-archive, and absolute ROM offset — for every named resource (8689 resolved). Use this file instead of re-deriving offsets by hand.

## Character IDs — two distinct ID spaces

**Confidence: high** — from `party.GDA`, which carries both spaces side by side (`id` and `creatureid` columns), corroborated by `debugParty.GDA` and `creatures.GDA`.

There are **two ID spaces, and they are not interchangeable.** They coincide for the first ten characters and diverge after, which is why the debug menu appeared self-contradictory (`AddPartyMember 27` uses the creature ID, `RemovePartyMember 10` the party slot).

| Party slot `id` | Internal name | Creature ID |
|---|---|---|
| 0 | Sonic | 0 |
| 1 | Knuckles | 1 |
| 2 | Tails | 2 |
| 3 | Amy | 3 |
| 4 | **Shadow** | **4** |
| 5 | Rouge | 5 |
| 6 | Big | 6 |
| 7 | Cream | 7 |
| 8 | Omega | 8 |
| 9 | Eggman | 9 |
| 10 | Shade | **27** |
| 11 | SuperSonic | **68** |
| 12 | VFXTester2 | **72** (developer test entry) |

**Shadow is party slot 4 and creature 4** — directly relevant to Phase 5 (Shadow Mode).

The creature ID space is wider than the playable roster because `creatures.GDA` (128 rows) covers enemies too. Creature 68 (Super Sonic) carries `health 9999, attack 99, power 500`.

### HP is stored in two columns

**Confidence: high** — verified across all 128 rows and confirmed in play on 2026-10-08.

| column | role |
|---|---|
| **2** (unnamed) | the HP a creature **spawns with** |
| **7** (`health`) | the **maximum** its HP bar is drawn against |

The two are equal in every vanilla row. **No other stat is duplicated** — a sweep over `speed`, `attack`, `defense`, `power`, `grit` and `luck` finds no second column for any of them.

Writing only one desynchronises the pair, and the result is a *partly* working mod rather than an obvious failure: enemies keep vanilla HP under an inflated ceiling, and anything that heals them can climb past their vanilla value. That is how `enemy_scaling` shipped until it was caught in the Lord Ix fight (Imperator Ix spawned at 350, healed to 377, ceiling 525). Always write both columns. See the 2026-10-08 correction entry in [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md).

## Level cap and progression

**Confidence: high** — read from the 11 per-character `Adv_<Name>.GDA` tables, whose explicit `level` column runs 1→30 in every case.

**The vanilla level cap is 30.** Progression is **per-character**: each has its own 30-row table of XP thresholds (cumulative) plus per-level `speed`, `attack`, `defense`, `hp`, `power`, `grit`, `luck`, `fatigue` and `combat` values. There is **no level-cap constant anywhere in the GDA data** (no column holds a constant 30 in any of the 229 tables), so the cap is either implied by row count or hardcoded in ARM9 — unresolved, and the key question for Phase 6. See [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md).

XP to reach level 2, by character: Sonic 200 (cheapest), Cream 226, Tails 253, Knuckles 279, Omega 305, Amy 332, Eggman 358, Big 385, Shade 411, Rouge 437, **Shadow 464** (most expensive). The curve is exponential to level 20 then **flat at ~76,974 XP per level for 21–30**.

Base (level-1) stats also appear in `creatures.GDA`, where they match each `Adv_` table's first row exactly.

Full tables: `research/phase0/progression_tables.txt`.

### Progression table columns (16, positional)

`id, level, xp, speed, attack, defense, hp, power, grit, luck, fatigue, #441910439, #3395337964, #3779980591, #4166442094, combat`

**Column 11 (`#441910439`) is the cumulative bonus-point count** — the stat-allocation points a character has available at that level. In vanilla it runs 1,2,3…20 then plateaus at 20 from level 20 on, so a level-30 character has 20 points to spend across Speed/Attack/Defense/Luck. Identified when an extended-level build froze this column and the level-99 character arrived with no new bonus points. See [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md).

**The level cap equals the number of rows in this table** — confirmed in game at both 31 and 99. There is no hardcoded cap.

### Stats shown in the UI

The character profile displays only **Spd (21), Atk (22), Def (23), Lck (27)**, plus HP and PP (stat 28). **POW (25) and GRT (26) are never shown** — and POW is the damage stat while Atk governs accuracy, so the game hides its most important combat number. The item tooltip likewise omits stat 26 (confirmed by experiment).

## Area IDs

**Confidence: high** — read from `debugArea.GDA` (`MoveToArea <id>`); `debugArea2.GDA`/`debugArea3.GDA` continue the list.

| ID | Area | | ID | Area |
|---|---|---|---|---|
| 0 | SBG | | 12 | Tyxis |
| 1 | Well | | 13 | VoxaiB |
| 2 | Kron | | 14 | VoxaiA |
| 3 | Green Hill | | 15 | Nocturne |
| 4 | Central City | | 16 | GrafXTest |
| 5 | Metropolis | | 17 | MysticRuins_int |
| 6 | GUN HQ | | 18 | MysticRuins |
| 7 | Workshop | | 19 | Abandoned Lair no vines |
| 8 | BlueRidgeZone | | 20 | Abandoned Lair with vines |
| 9 | angelisland | | 21 | Abandoned Lair Sewer |
| 10 | Groundzero | | 22 | Abandoned Lair Alley |
| 11 | Nrrgal | | | |

Note `GrafXTest` (16) is a developer graphics test area, not game content.

## Engine debug command vocabulary

From the `debug*.GDA` tables — these name real engine operations, useful as a glossary of what the engine can do even though the menu itself appears unreachable (see [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md)):

`SubDebug <file>.gda` (open submenu), `LevelUp <n>`, `AddPartyMember <id>`, `RemovePartyMember <id>`, `MoveToArea <id>`, `GiveXP <n>`, `GiveRings <n>`, `HealAll`, `SetPlayerHealth <who> <n>`, `SetPlayerFatigue <who> <n>`, `SetEnemyHealth <who> <n>`, `DamagePlayer <n>`, `KillSquad`, `ToggleEnemies 0|1`, `ToggleTriggers 0|1`, `ToggleCombat`, `ToggleWalkmesh`, `ToggleDebugStrings`, `EnableInteractive`, `DumpPlotTable`, `DumpStats`, `MemUse`, `FillInventory`, `ShowSquadInventory`, `OutputPlayerLoc`, `ProfilePlayer`, `ProfileCombatEnemy`, `GuiAnimManagerStats`, `SaveGameScreen`, `SaveGameToPC`/`LoadGameFromPC` (devkit-host only, reference `%NITROSDK_ROOT%`).

`SetPlayerFatigue` independently corroborates that **FP = Fatigue** (see the stat table above).

## Ability (`.spl`) naming conventions

- **Upgrade tiers**: `Spell_X.spl` / `Spell_X_2.spl` / `Spell_X_3.spl` are the three levels of one ability. 26 of the 30 tiered families differ **only** in effect magnitude (the `Data` column); see the log for the four exceptions.
- **`_All` suffix**: multi-target variant of a single-target ability (`Spell_Stun` vs `Spell_Stun_All`).
- **`Spell_Int_*`**: enemy/boss intrinsic abilities, named after the game's races and bosses — `Kron`, `Nocturn_Water`, `Voxai`, `Zoah`, `Nrrgal`, `Charyb_Water`, `Animal_Fly/Land`, `Robot_Fly/Land`, `GizoidShield`, `Final_IX` (Imperator Ix), `Super_Sonic`. Also `Overmind_Distracted`/`Overmind_Sluggish` and `Int_Drone.SPL`. Starting point for Phase 11 (boss scaling).
- 33 files are plainly numbered `Spell1`–`Spell33.SPL`; what distinguishes them from the named set is not yet known.

Full decoded catalog: `research/phase0/spell_catalog.tsv`.

**Not in these files:** which character learns which ability. That mapping must live elsewhere (likely a `.gda`) and is a prerequisite for Phase 7's "give an existing ability to a different character" experiments.

## Item IDs

The 219 item files are named `Item1`…`Item219` (extension case varies: `.ITM` on the low numbers, `.itm` on the rest — and since HERF hashing is case-sensitive, that case matters for lookup). The number in the filename is very likely the item's ID, though this has **not** been confirmed against anything in-game yet. Full decoded catalog with names and effects: `research/phase0/item_catalog.tsv`.

## Not yet known

- Character IDs, party-slot IDs, recruitment-flag IDs, enemy IDs, Chao-related IDs, placeable type IDs (xoreos' blog post mentions 43 hardcoded placeable type values, 0–42, but we haven't independently located/confirmed that table in our own ARM9 binary yet).
- Memory addresses for any of the above (see [KNOWN_MEMORY.md](KNOWN_MEMORY.md) — community-sourced addresses exist but are unverified).

## POW moves (`combo.GDA`) and movement abilities (`movement.GDA`)

**Confidence: high** — decoded tables with names resolved through the TLK.

**`combo.GDA` — 155 POW moves, fully data-driven.** Recovered columns include `namestrref`, `cost` (PP), `damage1/2/3`, `spell1/2/3` (links into `spells.GDA` → `.spl` files), `sound`, `image`, `smallicon`, `largeicon`, `blast`, plus a participants count (1–4, i.e. solo/duo/trio/quad moves). Examples: Axe Kick (solo, 4 PP, 75 dmg), Blue Bomber (duo, 4 PP, 100 dmg), Chaos Spear / Chaos Rift / Chaos Blast (Shadow's), Triple Tornado (trio), Hail Storm (quad). **Every property of a POW move — name, cost, damage, effects — is editable with existing tooling.**

**`spells.GDA` — 151 rows, just `id` → `.spl` filename.** A lookup index; the content is in the `.spl` tables.

**`movement.GDA` — 11 movement abilities, each with a `maxlevel`:**

| ID | Ability | maxlevel |
|---|---|---|
| 0 | Dash | **3** |
| 1 | Smash | 3 |
| 2 | Fly | 3 |
| 3 | Jump | 1 |
| 4 | Climb | 1 |
| 5 | Invulnerable | 3 |
| 6 | Stealth | 1 |
| 7 | **Teleport** | 1 |
| 8 | Wriggle | 1 |
| 9 | Detect | 1 |
| 10 | KSmash | 1 |

These are the "Movement Abilities" on the character profile (Tails shows "Fly LV 3"). **Dash already has a max level of 3**, so Dash III is legal vanilla content — Shadow simply has level 2. `Teleport` existing as a first-class movement ability is directly relevant to the brief's "Sonic teleport / Shadow teleport" ideas.

**Not yet known:** where a character's *current* movement-ability level is stored (per-creature table, plot flag, or save data). That is the blocker for granting Shadow Dash III.

## Chao are items

The 125 **type-3** entries in `Items.GDA` are Chao (`Chao 1`…), each backed by its own `.itm` file exactly like equipment. Their bonuses are ordinary effect rows — stat modifiers, elemental attack affinity (Chao 10–15, IDs 107–112) and elemental resistance (Chao 16–20, IDs 75–80). **Chao bonuses are editable today with the same tooling as equipment.**

## Chao roster — stat coverage (vanilla)

Surveyed across all 125 type-3 entries (75 of which carry effects), to find design gaps.

| Stat | Chao granting it | Values seen |
|---|---|---|
| GRT | **24** | 1–15 |
| POW | **18** | 1–6 |
| ATK | 6 | 1–6 |
| DEF | 6 | 1–6 |
| MAXHP | 6 | 10–30 |
| MAXPP | 6 | 2–12 |
| LCK | **3** | 1–3 only |
| attack elements (107–112) | 3 each, all six | 1 |
| resistances (75–80) | 3 each, **five only — no Ice** | 50 |

**Stats with no Chao at all:** **SPD (21)**, HP (0), PP (28), AP (48), COMBODISCOUNT (122), NUMACTIONS (123).

Two things fall out:

1. **The roster is heavily skewed to GRT and POW** (42 of the effect-bearing Chao between them) while LCK gets three Chao capped at +3, and **Speed gets none at all**.
2. **Ice resistance is missing** here as well as from items — consistent with the earlier finding that stat 80 has no source anywhere in vanilla.

These gaps are what the custom-Chao build targets: Tempo covers Speed and NUMACTIONS, Fortune covers LCK (the most under-served covered stat), Thrift covers COMBODISCOUNT and PP, and Aegis covers Ice resistance along with the rest.

## `Chaos.GDA` — the Chao species master table

**Confidence: high** — verified in game. 45 species, each with a name strref, a description strref, a rarity, a palette code, and **three item ids, one per Chao level**.

```
species row N  ->  item ids  (91 + N, 131 + N, 171 + N)   = levels 1, 2, 3
```

Verified end to end: the Chao named **Blayze** is row 26 and maps to items **117 / 157 / 197** — exactly the "Chao 27" entries edited in the visibility test, whose description duly changed in game.

| Rarity | Species |
|---|---|
| Common | 20 |
| Rare | 15 |
| Unique | 10 |

Examples: Stebsly (HP regen), Choo (PP regen), Barbo (max HP), Oolean (max PP), Churdle, Koolet (harder to hit), Cheezlet (damage), Rugle (luck), Pyraz/Ghise/Zimba/Griff/Seggo/Stiglin (the six attack elements), Korus+ (elemental shields), Belgog (*Rare*, much harder to hit), **Blayze** (*Rare*, much more damage), Bepke (*Rare*, enemy auto-targets), Baki (*Unique*, counter-attack — and notably uses the **same item id 213 for all three levels**).

Full dump: `research/phase0/chao_species.tsv`.

### Two consequences for modding Chao

1. **To change a Chao the player actually owns, you must go through this table** to find its item ids. Editing "Chao 16–20" blindly does nothing visible unless those species happen to be in the player's collection.
2. **A Chao's displayed name comes from `Chaos.GDA`, not from `Items.GDA`.** Overwriting the item's name strref changed nothing on screen while the description (which *does* come from the item) changed correctly. Rename a Chao via `Chaos.GDA`.

Also read off the in-game inventory: the bracketed number beside a Chao's name is the **quantity owned** (unequipped copies), **not** its level — confirmed by watching `Seggo (5)` become `Seggo (6)` when a Seggo was unequipped, while the detail panel independently showed `Level: 3`. Level and rarity are shown in the detail panel instead.

### Unique Chao — effects are code-driven, and "Unique" is NOT the same as "event"

All **10 Unique** species have **no effect rows whatsoever** in their `.itm` files. Their behaviour is implemented in ARM9, keyed by item id, exactly like the code-driven accessories (Scanner, Replenisher, Angel Amulet).

**Rarity does not determine obtainability.** A separate flag does — `Chaos.GDA` column **`#3678486078`**, which is `1` for exactly **five** species and `0` for the other forty:

| Flag | Species | Notes |
|---|---|---|
| `#3678486078 = 1` | **Pooki, Farfinkle, Baki, Stugs, Fimbley** | the genuinely unobtainable/event Chao |
| `#3678486078 = 0` | everything else, **including the Unique Ferox, Spartoi, Ovus, Choopaloo, Cheese** | hatchable |

The five flagged species share two further traits that corroborate the reading: they use **the same item id at all three levels** (211–215, so they do not scale with Chao level at all), and they all sit in palette group `F`.

A related column, `#1586539016`, is `0` for those five **plus Cheese** (whose effect is team-wide rather than per-character), so it marks some separate special-handling case rather than obtainability.

| Species | Items | Rarity | Described effect |
|---|---|---|---|
| Cheese | 126/166/206 | Unique | greatly increases luck of **all** team members |
| Choopaloo | 127/167/207 | Unique | increases XP gained from each battle |
| Ferox | 128/128/128 | Unique | POW moves automatically succeed |
| Ovus | 129/169/209 | Unique | auto-revive once per battle |
| Spartoi | 130/170/210 | Unique | basic attacks may instantly KO |
| **Pooki** | 211 | Unique, **event** | takes less damage, spreads the rest across the team |
| **Farfinkle** | 212 | Unique, **event** | normal attacks inflict a random status |
| **Baki** | 213 | Unique, **event** | successful counter grants free attacks |
| **Stugs** | 214 | Unique, **event** | avoided by enemies unless last target standing |
| **Fimbley** | 215 | Unique, **event** | automatically misses some basic attacks each round |

Note Ferox also repeats its item id across levels (128/128/128) despite being hatchable, so "does not scale" and "is an event Chao" are related but not identical.

**Modding consequence:** the most interesting Chao effects in the game cannot be changed or copied by data editing — there is nothing in the data to change.

**But they can be added to — CONFIRMED IN GAME.** The coded effect fires from the item id, while stat bonuses come from the item's effect rows; the two are independent. Appending `ATK+12` and `LCK+12` to Spartoi's tier-3 item (210) produced exactly that in game: Eggman read `Atk 32 / Lck 40` with a Seggo equipped and `Atk 44 / Lck 52` with the Spartoi — a clean +12/+12, on a Chao that has no effect rows of its own in vanilla.

Confirmed complete: Spartoi's instant-KO **still fires** with the stat rows in place, so appending rows does not displace the coded behaviour.

So the whole Unique roster can be kept competitive with a buffed Common/Rare lineup **without touching ARM9**: you cannot change what a Unique Chao *does*, but you can freely add stats alongside it, and both apply.


## Chao (`Chaos.GDA`)

45 species. Columns 6/7/8 are the three growth-tier item ids; column 1 is the name
strref and column 2 the effect description.

- **Growth:** most species are spaced 40 apart (Choo 92 -> 132 -> 172). **Six repeat
  one id in all three slots** and have a single fixed form: Ferox, Pooki, Farfinkle,
  Baki, Stugs, Fimbley. Tier ids must be read, never computed as `N, N+40, N+80`.
- **Event flag:** column 5 (`#3678486078`) = 1 on exactly five species, items 211-215
  (Pooki, Farfinkle, Baki, Stugs, Fimbley). **Ferox is single-tier with the flag at 0**
  — it does not grow but is hatchable. Growth and obtainability are independent.
- **Effect source:** 20 species have *no* effect rows in their item tables while their
  description promises an effect — those are hardcoded in ARM9 and keyed by item id.
  The remaining 25 express their effect as ordinary `.ITM` rows (stat boosts, elements)
  and are fully editable. A code-driven slot can be renamed, restatted and given
  elements while keeping its coded behaviour, because the effect follows the id.

### creatures.GDA column 32 is a creature class

**Confidence: high** for the grouping (read from the table); **unconfirmed** for what it drives.

| value | count | members |
|---|---|---|
| 0 | 78 | beasts |
| 1 | 5 | insects — Wasp Swarm x2, Queen Wasp, Giant Millipede, Colossal Worm |
| 2 | 31 | robots |

Not a cosmetic organic/robot tag. Changing it very likely changes elemental weakness and
possibly the block pattern an enemy's POW move demands, so cosmetic features must leave it
alone. See the 2026-10-08 second-playtest entry in [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md).

### Appearance ids are shared between creatures

19 appearance ids serve more than one enemy; id 26 (`BSL_AA`) serves five. Any mapping
keyed on an appearance id rather than on a creature row is therefore ambiguous.
`squads.GDA` column 4 is a separate overworld model: 97 of 163 squads match their first
member's appearance, 66 deliberately do not.

### creatures.GDA columns 51 and 52 are innate ability slots

**Confidence: high** — confirmed in game 2026-10-09 (a cloned Gizoid regenerated and
countered with its POW move slots blanked).

Two slots holding ability ids from the `Items.GDA` status range. Named ones include
219 `Evading`, 220 `Phase`, 221/225/229 `Self Repair`, 231/253/282/283/285 `Immunity`,
232 `Lock On!`, 233 `Shields Up!`, 234 `Charging!`, 280 `Energize!`, 255-257 the
elemental Shields. Several ids are unnamed (223, 224, 230, 277, 278, 279) and behave the
same way — code-driven and keyed by id, like the unique Chao effects.

Gizoid 278 + 224 · Wild Boar 224 · Marauder Scout 220 · Swat Bot 225 · Imperator Ix
285 + 230.

### combo.GDA damage columns are a percentage, in half-percent units

**Confidence: high for the arithmetic, open for what it is a percentage *of*.**
Columns 12/13/14 satisfy `column x 2 == the percentage in that tier's own description`
for **110 of 110** moves where both exist. Focus Field's 113/125/138 is
"225% / 250% / 275% of Attack damage"; Sonic's Axe Kick 75/88/100 is
"2x 150% of Attack damage".

**"Attack damage" means "the damage of a basic attack", not "the Attack stat".**

**POW drives damage. Confirmed in play, 2026-10-10.** A probe ROM amplified Rock Salt
from POW +10 to POW +150 (`profiles/pow_probe.json`); used mid-battle it took basic-attack
damage to **over 200 per hit**, and an attack still **missed**. So POW raises damage and
does nothing for accuracy — which matches the game's own help text, *"Attack (Atk)
determines how likely an attacker is to hit"* (strref 17017). Attack is accuracy; POW is
damage; a POW move deals a multiple of a POW-driven basic attack.

**GRT reduces damage taken. Confirmed in play, 2026-10-10.** The same method
(`profiles/grt_probe.json`, Iron Tonic amplified from GRT +10 to GRT +150) dropped
incoming damage to **1 per hit**.

So the four combat stats split into a clean pair of pairs:

| | chance to connect | magnitude |
|---|---|---|
| offence | **Attack** (stated by the game) | **POW** (confirmed) |
| defence | **Defense** (inferred) | **GRT** (confirmed) |

POW and GRT are the two the character sheet hides and the text never explains; Attack
and GRT's counterpart Defense are the visible pair. That Defense is the evade-chance
counterpart to Attack is **inference from the symmetry, not tested** — the game defines
neither Defense nor GRT anywhere.

This is the first direct evidence of what POW and GRT do. The game never defines POW or Grit in
any string — a search of all 18,845 TLK entries finds definitions only for Attack and
Speed — and `enemy_scaling` had been assuming the POW reading since it was written. The
assumption was correct.

They are therefore not hit points, which the data also shows independently: they do not
scale with level (level-2 moves read 400, level-18 moves 75-175) and the same move reads
the same value on creatures of very different power (Quake Punch is 75 on both the
level-14 Gizoid and the level-18 Gizoid Mk. II). A move transplanted onto a weaker
creature needs no adjustment — it inherits that creature's Attack.

### combo.GDA status effects are tiered

Columns 27/28/29 name a `spells.GDA` row per damage tier. Most statuses have three
variants: Cursed 35/66/71, Distracted 36/67/72, Weakened 37/68/73, Vulnerable 38/69/74,
Sluggish 39/70/75. **Stun is the exception** — only `Spell_Stun.spl` (41) exists, so
moves using it repeat it across all three tiers, which is how Metal Storm and Quake Punch
are authored. Focus Field repeats tier-1 Vulnerable (38/38/38) despite tiered variants
existing.

## Movement abilities

`movement.GDA`, 11 rows. Column 10 is `maxlevel`; 11-13 are the per-tier name/description
strrefs; 1-9 are three groups of three per-tier parameters (Dash 800/-1/-1, Fly
60/80/0.75, Jump 45/45/1.0 — distance / height / duration).

| id | ability | max level | carried by |
|---|---|---|---|
| 0 | Dash | 3 | Sonic, Amy (L4), Shadow |
| 1 | Smash | 3 | Knuckles (L4), Amy, Omega |
| 2 | Fly | 3 | Knuckles (L8), Tails, Rouge, Cream |
| 3 | Jump | 1 | **nobody** |
| 4 | Climb | 1 | Knuckles, Shade (L4) |
| 5 | Invulnerable | 3 | Big, Omega (L4) |
| 6 | Stealth | 1 | Rouge (L8), Shade |
| 7 | Teleport | 1 | Shadow (L8), Shade (L8) |
| 8 | Wriggle | 1 | **nobody** |
| 9 | Detect | 1 | **nobody** |
| 10 | KSmash | 1 | **nobody** |

Slots are `creatures.GDA` 19/20/21; the unlock level is the first non-zero row in that
character's `Adv_<name>.GDA` columns 12/13/14. Eggman has no traversal ability.

The four unassigned ones have no description strings either, unlike every assigned
ability, which suggests engine-granted verbs rather than unlocks. Strref order puts
KSmash immediately after Smash (a Smash variant) and Wriggle/Detect in a later block with
Teleport.

## Plot files

`plots.GDA` maps to 95 `.plo` files named by chapter. A `.plo` is GFF4 type `PLTS`, and
**field 13002 is a human-readable flag name** — `plt_gbl_inparty.plo` holds
`SONIC_IN_PARTY` through `SHADE_IN_PARTY` plus `PARTY_1_ACTIVE`. Field 13009 is a
category (`plot_core`), 13007 a GUID. Which action *sets* a flag is not yet decoded.

## combo.GDA: status effects and the element pairing rule

Columns **27/28/29** are the status a move inflicts, per damage tier, as a `spells.GDA`
row — Stun (41), Sluggish (39), Vulnerable (38), Weakened, Distracted.

**Adding an element to a move that shipped without one is unsafe, and nothing in
combo.GDA predicts which moves tolerate it.** Observed in play: Focus Field + wind
hard-crashes, under Vulnerable *and* under Sluggish; Metal Storm + earth works; Atomic
Strike works but ships with its element.

An earlier theory — that the (element, status) *pairing* had to exist in vanilla — was
tested directly with a wind + Sluggish probe, the pairing Triple Tornado uses, and it
crashed anyway. Dead. There is also no companion column: across all 155 moves the only
field every vanilla wind move shares and Focus Field lacks is the element itself, and
Atomic Strike is structurally near-identical to Focus Field yet fine. Whatever an
elemental move requires lives outside this table and has not been found.

`pow_move` therefore refuses to add an element to an elementless move unless
`force_element` is passed, and permits changing one that already exists.

**Column 52 is not an element flag**, despite being named `C_ELEMFLAG`: 20 moves set it
and only 6 are elemental, while Blazing Tornado and Tornado Kick carry an element with it
at 0. Its meaning is unknown.

## ARE item placements

The ARE list at label **40002** carries placed objects as (kind, id) at fields
40008/40009. **kind 4 is an item placement** — 39 of them across 17 areas, every id valid
in `Items.GDA` (Health Leaf, Clover Juice, Psychic Water, Voxai Teleporter, Ring of Life).
This is the real loot layer, not `RandItems.GDA`: removing Health Seed from every early
`RandItems` tier did **not** stop the first chest giving one. There are 53 itemboxes
against 39 placements, so some chests are still sourced elsewhere.

## `creatures.GDA` column names, recovered by hash

A GDA header stores each column as `crc32` of its **lowercased UTF-16LE name**, so the
authored names can be recovered by hashing candidates and matching. 13 of the 61 columns
in `creatures.GDA` are named this way, and they confirm the column map the tooling was
already using:

| column | name | column | name |
|---|---|---|---|
| 0 | `id` | 10 | `luck` |
| 4 | `speed` | 11 | `fatigue` |
| 5 | `attack` | 14 | `appearance` |
| 6 | `defense` | 33 | `level` |
| 7 | `health` | 35 | `playerid` |
| 8 | `power` | 37 | `class` |
| 9 | `grit` | | |

Two notes. **Column 37 is `class`**, not column 32 — it is -1 for 111 of 128 rows, so it
is a *character* class the playable cast has and enemies do not. Column 32, the
beast/insect/robot type that a reskin must not copy, shares its hash with a column of
`appearances.GDA` and its real name is not recovered.

And **there is no `maxhealth`**: column 7 is `health` and column 2 — the spawn value that
must be written alongside it — did not match any name tried.

## Playable character ids (`creatures.GDA` column 35)

| id | character | id | character |
|---|---|---|---|
| 0 | Sonic | 6 | Big |
| 1 | Knuckles | 7 | Cream |
| 2 | Tails | 8 | Omega |
| 3 | Amy | 9 | Eggman |
| 4 | Shadow | 10 | Shade |
| 5 | Rouge | 11 | Super Sonic |

Id 12 is shared by two rows (the duel variants). This order is **not** the order the
`DISPLAY_*` plot flags use, which is Amy, Big, Tails, Rouge, Knuckles, Shadow, Cream,
Shade, Eggman, Omega — two different authoring orders, so neither can be assumed to be
the other.

## Plot flags

657 global ids in `plotflags.GDA`, 649 of which resolve to an authored name through
`plots.GDA` and the `.plo` files. `tools/recon/plotflags.py` does the lookup. Useful
ones:

| id | name | what it gates |
|---|---|---|
| 23 / 30 | `AMY_GET` / `TAILS_GET` | the first two recruitments |
| 56 / 124 / 413 / 450 | `BIG_GET` / `SHADOW_GET` / `OMEGA_GET` / `CREAM_GET` | the optional recruitments |
| 42 | `MY_FIRST_ACTION` | the combat tutorial |
| 308 | `PROJECTOR_QUEST_GIVEN` | the three projectors in the opening zone |
| 552 | `MARAUDER_SCOUT_TRIGGER_APPEAR` | the Green Hill Marauder chase |
| 600 | `FROGGY_QUEST_ACCEPTED` | Big's four frogs |
| 114-123 | `DISPLAY_AMY` … `DISPLAY_OMEGA` | party portraits |
