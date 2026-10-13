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

### An elemental item is a VFX pair plus an ELEMENT row

**Confidence: high** for the table (read off items 68–73) and **confirmed in play
2026-10-13** — adding the pairs put the element effects on the character, which nothing
else in the build changed.

Each shipped elemental Ring carries **three** effect rows: two `VFX` rows
(`EffectId 5`, `SData1 38`, `Pulse -1`) and one `ELEMENT` row (`EffectId 1`, `Data 1`).
The VFX pair is cosmetic and the ELEMENT row does the work, so an item can have the
element without the visual — which is what `custom_item` produced until 2026-10-13.

| ring | item | VFX pair | `ELEMENT` `SData1` |
|---|---|---|---|
| Fire | 68 | 239, 240 | 107 |
| Water | 69 | 241, 242 | 108 |
| Lightning | 70 | 249, 250 | 111 |
| Ice | 71 | 247, 248 | 112 |
| Wind | 72 | 251, 252 | 110 |
| Earth | 73 | 243, 244 | 109 |

The block runs 239–252 in pairs; **245/246 is unused** by any shipped item. Note the
item ids do **not** run in element order — 70 is Lightning and 73 is Earth.

**Multiple attack-affinity rows on one item all apply.** There is no limit of one element per item — six rows on one item is confirmed in game (the Omni Ring, 2026-10-05) and six Chao (Chao 10–15) also grant attack affinity, while Chao 16–20 grant resistance.

> **Retracted 2026-10-13.** This paragraph used to continue *"the engine evaluates every `ELEMENT` row against the target's resistances and surfaces only the effective ones"*, and the Omni Ring entry drew from it that an all-element item *"always strikes the target's weakness"*. **Neither was ever tested.** The only observation behind them was which element icons the combat panel drew — and that panel reads the *target's* element table, not the attacker's, so it would have drawn exactly the same two icons whichever element the hit actually used. How damage resolves when an item carries several elements is **open**. A player report on 2026-10-13 suggests ineffective elements are not skipped.

Seen from the other side, this is what the **combat panel's element row** is: it reads the
*target's* element table, not the attacker's gear, which is why the same all-six item shows
a different pair of icons on each enemy. The game says so itself — strref **3200**,
*"Try different Element attacks. Most enemies are vulnerable to one Element and resistant to
others!"* The archive holds six element icons plus **`cbt_elem_redx.ncgr.small`**, and rendering
all seven settles what they are: fire is a red flame, water a blue droplet, earth a brown
mountain, wind a silver swirl, lightning a gold bolt, ice a pale crystal, and `redx` a **red
diagonal slash drawn over** one of the other six rather than in place of it. Seen in play
2026-10-13: water slashed and fire clean, side by side on one hit, so the panel shows **two
icons of opposite polarity at once**. Three at once has never been seen. Strref **3226** is
"No effect" (a possible third tier, unconfirmed).

**The shield table's first real test, passed.** Exactly three creature rows in the game
resist water — 38, 39 and 123, all Nrrgal, all via innate ability 255 — and a Nrrgal
encounter slashed water out exactly as that predicted.

**Enemy-side resistance, where it is readable.** Eleven creatures carry one through the
innate ability slots (`creatures.GDA` 51/52), each an ordinary `.itm` effect table on the
same stat ids:

| ability | grants | creature rows |
|---|---|---|
| 255 Water Shield | `ELEMENT` 50 on **76**, `GRT+` 3 | 38, 39, 123 (Nrrgal) |
| 256 Lightning Shield | `ELEMENT` 50 on **79**, `GRT+` 3 | 41 Zoah Brute, 42 Gentleman |
| 257 Air Shield | `ELEMENT` 50 on **78**, `GRT+` 3 | 47 Thelxe, 49–51 the Voxai Overminds, 66, 67 |

**No creature carries two Shields and no Nocturne carries any**, so a target showing two
resisted elements is being driven by something outside the archive — the baseline table
is ARM9 code, plausibly keyed on column 32 but **not established**. See the 2026-10-13
entry in [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md) for the positive test that
would settle it.

### What each stat actually does — the game's own words

**Confidence: high; this is the game explaining itself.** These are its in-game help
strings, recovered from the TLK, not an inference from the data:

| stat | strref | the game says |
|---|---|---|
| **Speed (Spd)** | 16273 | "determines who goes in what order each round, and how good a character is at fleeing or chasing" |
| **Attack (Atk)** | 17017 | "determines how likely an attacker is to hit" |
| **Defend (Def)** | 13962 | "determines how hard a target is to hit" |
| **HP** | 6161 | "How much damage you can take before being Knocked Out (KO)" |
| **PP (Fatigue)** | 18463 | "how many POW moves a character can use before becoming exhausted. You can regain PP by defending" |
| **Luck (Lck)** | 8328 | "has many effects. One is your odds of ambushing or being ambushed. See if you can figure out what else luck does!" |

Two of these overturn the obvious reading:

* **Attack is accuracy, not damage.** Strref 17756 says it again from the other side —
  *"You'll notice you might miss some enemies a lot. These creatures are agile. Increase
  your Attack (Atk) or use a POW Move that can't miss."* This matches the item-description
  evidence that **POW** is damage.
* **Defense is evasion, not damage reduction.** "How hard a target is to hit" is the
  mirror of Attack, not armor. Armor is **GRT**, which the game calls "Armor" in item text
  and never displays.

**POW and GRT have no help text at all**, because the game never shows them. Their
meanings come from its own item descriptions instead: *"Very greatly increases damage"* on
a `POW+5` item, *"Greatly increases armor"* on a `GRT+4` one.

So the four stats a player can see and spend bonus points on — Spd, Atk, Def, Lck — are
turn order, accuracy, evasion and luck. **Neither damage nor armor is visible or
allocatable.** That is a deliberate design choice and it is the single best argument for
this project regenerating item descriptions: two of the six combat stats are otherwise
unknowable.

**Luck is the one the game refuses to answer.** It names ambush odds as *one* effect and
invites the player to work out the rest — strref 4599 repeats the ambush half ("Team
members with high luck make getting an ambush more likely"). Critical-hit chance is the
common player belief and it is **not confirmed here**; nothing in the data or the text
establishes it. Treat anything more specific than "ambush odds, plus unnamed effects" as
folklore until somebody measures it.

### POW move elements — `combo.GDA` column 51 is a contiguous six-bit field

**Confidence: high — all six confirmed in game 2026-10-12.**

| bit | value | element | in vanilla? |
|---|---|---|---|
| 2^17 | 131072 | fire | yes |
| **2^18** | **262144** | **water** | **no — confirmed by test** |
| 2^19 | 524288 | earth | yes |
| 2^20 | 1048576 | wind | yes |
| 2^21 | 2097152 | lightning / electricity | yes |
| **2^22** | **4194304** | **ice** | **no — confirmed by test** |

Vanilla authors only four of these, across all 155 rows including enemy and boss moves.
Water and ice were **predicted** from the fact that the item element ids are sequential
and all six *are* observed there — 107 fire, 108 water, 109 earth, 110 wind, 111
lightning, 112 ice, each on a Ring plus three Chao tiers — so that ordering maps onto
these bits exactly and leaves holes at 2^18 and 2^22 where water and ice belong. Two
independent orderings agreeing is the same reasoning behind `ITEM_RESISTS`.

Both were then **tested rather than assumed**. Axe Kick — the only Sonic move that is
elementless *and* statusless — carried each in turn, written as a raw cell edit with
column 52 left at 0, and performed with the right VFX both times without crashing.

So the engine supported all six all along; vanilla simply never authored a water or ice
move. The game's own help text names them: *"The types of Elements are: Fire, Water, Wind,
Earth, Lightning, and Ice"* (strref 9760).

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

### Recruitment is one plot file per character

`plt_fp_<char>.plo` ("find party") exists for all ten non-Sonic characters, and
`plt_fpa2_<char>.plo` for the nine who can be in Act 2 — there is no `plt_fpa2_eggman`.
The flags inside name the join conditions outright (`AMY_GET`, `SHADOW_GET`,
`FROGGY_QUEST_COMPLETE` → `BIG_GET`, `GOT_CHEESE` → `CREAM_GET`, `OMEGA_FIXED` →
`OMEGA_GET`), and the ~70 `MAP_PIN_*` flags carry an area prefix numbered in progression
order: GHZ → CCZ → MRZ → BRZ → MET → ANG → GRZ → KRO → NRG → ZOA → VOX → NOC. Full
table in the 2026-10-10 log entry. **Derived from data, not yet confirmed against a
playthrough.**

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

## Chao cannot be given as loot

**Confidence: high** — exhaustive census plus a playtest. Chao are type-3 rows in
`Items.GDA` with real ids, and those ids can be written into a chest: the reward screen
shows the right Chao with the right description, and **nothing enters the collection**.

Vanilla never does it either. Across the whole game, the 123 Chao item ids appear in
**0** chest slots, **0** shop rows and **0** drop-table item cells. The only placed Chao
item object in the ROM is in `jay_test.are`, the developers' test area.

The acquisition path is the gate, not the id. Hatching an egg is the player path.

## Elemental offence and resistance stat ids

**Confidence: high** — read from shipped items, and two independent orderings agree.

Item effect rows (`SData1`) address elements in two parallel blocks **32 apart**:

| element | offence | resistance | granted by |
|---|---|---|---|
| fire | 107 | **75** | Pyraz / Korus |
| water | 108 | **76** | Ghise / Perty |
| earth | 109 | **77** | Stiglin / Jirna |
| wind | 110 | **78** | Seggo / Seeri |
| lightning | 111 | **79** | Zimba / Knickt |
| ice | 112 | **80 (predicted, unused)** | Griff / — |

The five shield Chao each grant `ELEMENT` 50 on their resistance id plus GRT +1, and each
description names the element ("creates a shield of fire to protect against damage").
**There is no ice-shield Chao**, so stat 80 is an extrapolation from the offset and nothing
in the game exercises it; `ITEM_RESISTS` offers the five that exist and refuses ice by
name. What the magnitude 50 actually means has never been measured.

## POW moves (`combo.GDA`) and movement abilities (`movement.GDA`)

**Confidence: high** — decoded tables with names resolved through the TLK.

**`combo.GDA` — 155 POW moves, fully data-driven.** Recovered columns include `namestrref`, `cost` (PP), `damage1/2/3`, `spell1/2/3` (links into `spells.GDA` → `.spl` files), `sound`, `image`, `smallicon`, `largeicon`, `blast`, plus a participants count (1–4, i.e. solo/duo/trio/quad moves). Examples: Axe Kick (solo, 4 PP, 75 dmg), Blue Bomber (duo, 4 PP, 100 dmg), Chaos Spear / Chaos Rift / Chaos Blast (Shadow's), Triple Tornado (trio), Hail Storm (quad). **Every property of a POW move — name, cost, damage, effects — is editable with existing tooling.**

**The table is one contiguous block of rows per character, and the block is what binds
a moveset to a character** — Sonic 0-5, Knuckles 6-11, Shadow 12-17, Tails 18-23,
Cream 24-29, Big 30-35, Omega 36-41, Rouge 42-47, Amy 48-53, Shade 54-57, Eggman 58-59,
then ~90 boss and enemy rows. Column 2, long read as "owner", is a **participant
requirement**: the game offers a character the moves in its own block and then demands
whoever column 2 names. Repointing column 2 therefore does *not* move a moveset — it
changes who you need in the party to use it. Confirmed by playtest 2026-10-10; see the log.

Column 2 is in the **party-slot** id space, not the creature-row space (see the two ID
spaces above: Shade is slot 10, creature 27). For enemy rows it runs on up into the
creature rows, which is how the two spaces came to look like one.

**Targeting is three mutually exclusive modes**, in columns 48 and 52, which are never
both set (113 moves have neither, 22 have 48, 20 have 52):

| mode | column | evidence |
|---|---|---|
| single target | neither | every description says "a foe" or "the target" |
| splash | **48** (`blast`) | Hellfire is 48=1; a transplanted Hellfire did 19 to Sonic and 10 to Amy beside him |
| whole opposing team | **52** | all twenty say so — "lashing them all", "the entire opposing team", "hits multiple targets" |

Column 52 was carried as `C_ELEMFLAG` until the descriptions were read; it has nothing to
do with elements. **Column 55** marks the 23 moves the game classes as support rather than
attack (Heal, Cure, Revive, Scan, Taunt, Cloak, Distract…). It agrees with "deals no damage
at any tier" on 153 of 155 rows; Froggy Poison (55=1, 25/38/50 damage) and Chaos Rift
(55=0, no damage) are the exceptions, so it is a correlation, not a definition.

**Four columns are `ndsfixed` (GFF4 type 18), not integers** — a signed 32-bit
fixed-point number with 12 fractional bits. Columns 30/31/32 are a move's status-effect
chance per damage tier (0.3 / 0.5 / 0.8 on Blue Bomber, -1.0 for no status) and 46 is a
fourth. An integer write to one of these zeroes it.

**`spells.GDA` — 151 rows, just `id` → `.spl` filename.** A lookup index; the content is in the `.spl` tables.

**Ability gates are partly in the area files.** Placeable type 1 — the 69 "blocks" —
carries `(ability, level, 0)` in its three payload parameters, and only two abilities
appear: Dash (levels 0 and 1) and Smash (level 2), i.e. the two that remove an obstacle.
The gates for Fly, Jump, Climb, Teleport and Stealth are not in that list and have not been
found. `areas.GDA` names a per-area movement table for each area
(`GreenHillZoneMovement.gda`, `CentralCityMovement.gda`) and **none of them is in the
archive** — dangling asset-pipeline names, the same pattern as the debug menu's missing
command strings.

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

**Columns 39/40/41 are the slots' companion flags** (2026-10-11). Each reads -1 at
exactly the slots that are empty and 0 or 1 otherwise, across all eleven playable rows —
Knuckles fills three slots and has all three set, Sonic fills one, and Eggman, who has no
ability at all, is -1 in all six columns. Shadow Mode swapped 20 and 40 together without
knowing why, which is consistent. Treat 19/20/21 and 39/40/41 as one group: anything that
moves an ability must move or pin all six.

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

**Adding an element to a move that shipped without one works.** Confirmed in play on
**six distinct moves across all six elements** — every element by *addition*, not merely
by appearing on a move that shipped with it:

| move | added | result |
|---|---|---|
| Metal Storm | earth (and 3 participants → 1) | works |
| Axe Kick | ice / water / wind | works |
| Axe Kick | ice **and** Vulnerable together | works |
| Focus Field | wind, solo, vanilla Vulnerable kept | works |
| Chaos Spear | fire | works |
| Chaos Blast | electricity | works, on target **and** splash target |
| Chaos Rift | electricity, on a 0-damage move | no crash — see below |

Chaos Rift is listed for completeness but cannot support the element claim: it deals
0/0/0 damage and is a KO-chance move, so an element had nothing to color. It stands as a
different result — adding an element to a zero-damage move does not crash either.

This reverses the 2026-10-11 reading. Focus Field + wind did hard-crash, twice, under two
different statuses — but only ever inside `profiles/ultimate_lifeform.json`, and when the
same move was rebuilt with that profile stripped away it worked. Attribution had rested on
deleting the element cells and the crash going away, which shows the element was
*involved* and not that it was sufficient.

Two columns still differ between the crashing build and the working probe, and neither is
a finding because **Metal Storm carried both and worked**: column 2 (owner, retargeted
0 ← 4 by that profile's identity swap) and column 52 (set to 1 by the old `C_ELEMFLAG`
mis-inference). The cause of that crash remains unknown.

An earlier theory — that the (element, status) *pairing* had to exist in vanilla — was
tested directly with a wind + Sluggish probe, the pairing Triple Tornado uses, and it
crashed anyway. Dead on its own terms, and now doubly so: Axe Kick carries ice and
Vulnerable together, a pairing no vanilla move has, and works.

`pow_move` **warns** when adding an element to an elementless move, naming the sample size
and asking that the move be cast once before a run is played on it. `force_element` is
still accepted and now silences the warning rather than unlocking the operation.

**Column 52 is whole team, not an element flag**, despite once being named `C_ELEMFLAG`.
All 20 moves that set it say so in their own descriptions — "the entire opposing team",
"hits multiple targets" — and every single-target move's description says "a foe" or "the
target". `pow_move` no longer writes it when applying an element; doing so had been
silently converting single-target moves to whole-team ones.

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

## What makes a playable character, column by column (2026-10-11)

Of `creatures.GDA`'s 61 columns, **42 differ between at least two of the eleven playable
rows** and 18 are identical across all of them. The 42 are what a character *is*, and
moving them to another row moves the character — which is how `randomize_characters`'
`recruitment` half reorders recruitment, since a story point grants a creature *row*
(confirmed in play 2026-10-07).

Twelve of the 42 must stay behind, and each has a reason:

| columns | what | why pinned |
|---|---|---|
| 0 | the row's own id | structural |
| 35, 37 | `playerid`, `class` | the party-slot identity the engine indexes by; Shadow Mode left them alone and the party held together |
| 17, 18 | dialogue portrait prefix, palette | the engine builds a portrait name from prefix + expression suffix and two characters share only ~3 of ~10 expressions, so swapping corrupts conversation art both ways |
| 36 | a map-pin icon | only Sonic has one (`EXP_MapPinQ.ncgr`) |
| 19, 20, 21, 39, 40, 41 | the three movement ability slots and their companion flags | pinning them keeps the ability timeline byte-identical to vanilla, so no obstacle gate can become impassable |

The remaining 30 travel. The notable ones: **1** name strref, **2** and **7** the HP pair,
**4-12** the stat line, **14** and **47** the 3D model (identical values in all eleven
rows, so 47 is a second reference to the same appearance), **15/16/44** the three
portraits, **22-27** the six POW move slots (pointers into `combo.GDA`), **34** the
`Adv_<name>` progression table, **42/43** the character-profile art, and **32/56** the
creature type, which is the pair that marks Omega a robot.

`Adv_*.GDA` columns 12/13/14 are the exception that needs writing back rather than
pinning: the progression table travels with the identity (column 34), so a borrowed table
brings the donor's ability-level schedule with it. Since the deal is a permutation of the
same eleven tables, each table can be rewritten exactly once with the schedule its new
row had in vanilla.

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

## What the item panel draws, and what it hides

An item's panel prints its effects in green (or red, when negative) beneath the
description. It does **not** print all of them. Read off the screen on 2026-10-10:

| stat | id | drawn by the game? | evidence |
|---|---|---|---|
| Speed | 21 | yes | Master Hydraulics shows `Speed +1` |
| Defense | 23 | yes | Shielded Sneakers shows `Defense +1` |
| Luck | 27 | yes | Cursed Claws shows `Luck -3` |
| HP heal | 0 | yes, as a **percentage** | Revival Ring shows `HP +18%` |
| PP heal | 28 | yes, with **no** percent sign | Refresher Wave shows `PP +94` |
| **Max HP** | 24 | **no** | Shielded Sneakers is "Defense +1, Max HP +3"; only Defense is drawn |
| **POW** | 25 | **no** | Master Hydraulics is "Speed +1, POW +5"; only Speed is drawn |
| **GRT** | 26 | **no** | Cursed Claws is "Speed -2, GRT +4, Luck -3"; only Speed and Luck are drawn |
| Attack | 22 | not observed | — |

Three of the ten stats an item can carry are therefore invisible in a normal playthrough.
That is the whole justification for `randomize_items` rewriting descriptions: a
randomized item that changes POW, GRT or Max HP would otherwise be unknowable, and it is
also why the generated text lists every effect instead of only the hidden ones.

The two heals are written differently — one with a percent sign and one without — and
whether the stored number means the same thing in both is unresolved. Vanilla HP heals
are 10/50/100/250 and PP heals 5/10/50/999; a POW Candy restoring "5%" of a seven-point
PP pool would do nothing, so the PP figure is almost certainly flat.

## `Chaos.GDA` — the Chao table

45 rows, 14 columns.

| column | meaning |
|---|---|
| 0 | id |
| 1 | name strref |
| 2 | description strref |
| 3 | rarity strref — 20 Common, 15 Rare, 10 Unique |
| 4 | obtainable by hatching; 0 for Cheese and the five event Chao |
| 5 | **event Chao** — 1 for Pooki, Farfinkle, Baki, Stugs, Fimbley |
| 6, 7, 8 | the **item ids granted at levels 1, 2 and 3** — Rugle is 99/139/179, carrying Luck +1, +2, +3 |
| 9 | model/texture key (`JH`, `JG`, …) |
| 10-12 | position in the garden |
| 13 | garden group (`J1`, `J2`, …) |

The garden's collection counter reads **40**, which is the 45 rows minus the 5 with
column 5 set.

Columns 6-8 are what `chao_level` edits: a Chao's level selects one of the three, and a
solo player can never reach the second or third, because level 2 requires a wireless
trade with one person and level 3 a trade with a *different* one.

**Six Chao name one item for all three levels.** Five are the event Chao, which never had
a levelling path. The sixth is Ferox, which is Unique, not an event Chao, and unexplained.

**Bepke levels backwards**: GRT +15 / +10 / +5. It is the only row in the table whose Max
tier is worth less than the tier it hatches with.

## `rewards.GDA` — quest rewards (70 rows)

> **Column 5 is NOT the XP award.** Tested 2026-10-11: with all 64 positive values set
> to 777, a completed quest still paid 250. The total below is **withdrawn** and kept only
> to record what was tried. The structure, the plain-text row names and the hint ladder are
> confirmed; the meaning of column 5 is unknown.

Layout: `0` id, `1` designer name (plain ASCII, not a strref — unique among the GDA
tables), `2` plot id or −1, `3`/`4` always 0, **`5` XP award**, `6`–`11` up to six item
ids or −1. Column 5 as XP is high-confidence but unconfirmed in game; see the log entry
for 2026-10-11 and [profiles/xp_rules_probe.json](profiles/xp_rules_probe.json).

~~Maximum collectable in one playthrough: 62,723~~ — withdrawn, see above. For the record it was computed as (all 70 rows total 73,033; the 16
`, 1 hint` / `, 2 hint` rows are mutually exclusive with their no-hint parents). That is
level 14 on the `Adv_*.GDA` curve, against 1,159,258 for the level-30 cap.

Every puzzle's hint ladder is exactly **75% / 50% of the no-hint award, floored** — all
16 variant rows, no exceptions.

| row | name | XP | row | name | XP |
|---|---|---|---|---|---|
| 1 | Wasp Quest | 50 | 29 | Scylla Complete | 2,000 |
| 2 | Factory Quest | 500 | 30 | nrrgal shipment | 2,500 |
| 3 | Timmy Quest | 500 | 31 | Kron Payment | 2,500 |
| 4 | GenericSmall | 75 | 32 | Pirates defeated | 5,000 |
| 5 | GenericLarge | 2,500 | 33 | Haniman defeated | 3,000 |
| 6 | GenericLargeXPOnly | 2,500 | 34 | Voxdad complete | 4,500 |
| 24 | Krag met | 1,000 | 35 | Brief History complete | 8,000 |
| 27 | Queen Met | 1,500 | 36 | Argus Event complete | 10,000 |

Rows 17, 28, 38 (`Omega found`, `Raxos Defeated`, `Cream Found`) pay 0; rows 64/65
(`Scylla Defeated`, `Charyb Defeated`) pay −1 — the endgame bosses award XP through the
combat path, not this table. The eight puzzles are rows 40–47, their hint variants 48–63.

## `CombatRules.GDA` — 74 unnamed tuning constants

`(id, value)` only, id == row index, no names recoverable (sequential 0x2715+n labels)
and **not listed in `2DA.GDA`**, so ARM9 reads it by hardcoded index. Values:

```
90 60 2 1 1 24 24 7 20 1000 1 1 1 1 0 100 135 250 -20 15 -50 0 100 230 0 85 200 100
100 250 -20 -10 -50 4 10 833 11 54 16 100 5 30 1000 90 110 60 150 10 150 200 250 7369
120 100 50 2 6 0 3 1 0 20 2 6 -4 2 2 5 2 5 0 90 95 100
```

Rows 34 and 47 are the only two holding 10, the measured combat-XP floor. **Both were
tested 2026-10-11 and both are rejected** — set to 77 and 33, the floor stayed at 10. The
XP floor is computed in ARM9, not read from this table. No row's meaning is established.

## `2DA.GDA` — the engine's table registry (31 rows)

`(id, filename, flagA, flagB)`. The 31 tables the engine loads by index:
`animations`, `spells`, `appearances`, `RealtimeWidgets`, `realtime`, `movement`,
`PlaceableStates`, `Statuses`, `VFX`, `Conversations`, `PlotFlags`, `Rewards`,
`RandItems`, `Projectiles`, `AreaMove`, `CompoundEvents`, `SplashLists`,
`CombatActions`, `CombatAI`, `Chaos`, `Party`, `combo`, `Items`, `guis`,
`TextureAnimations`, `creatures`, `MovieList`, `MovementSounds`, `squads`,
`waterslides`, `combatsounds`.

Useful as a negative filter: a table **absent** from this list (`CombatRules.GDA`,
`Adv_*.GDA`, the per-area tables) is reached some other way, so its rows cannot be
identified by watching a registry lookup.

## `Levels.GDA` — not an XP curve

A 5×5 schema stub of type codes (`I`, `R1000`, `IM3`, `N1`, `4.000000`) and defaults.
Leftover tooling metadata with no game data. The XP curves are `Adv_<character>.GDA`.
