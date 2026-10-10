# Sonic Chronicles Modding Framework — Roadmap

## Phase 0 — Research and reconnaissance

- Identify supported ROM revision(s)
- Map ROM filesystem
- Identify compression
- Identify ARM9/ARM7 binaries
- Identify overlays
- Identify GFF4
- Identify TLK
- Identify GDA/2DA-style data
- Identify graphics formats
- Investigate save data
- Study ChroniclesDX
- Study xoreos
- Study xoreos-tools
- Study melonDS debugging
- Study Nintendo DS ROM tooling

Create:
- `RESEARCH.md`
- `KNOWN_FORMATS.md`
- `KNOWN_IDS.md`
- `KNOWN_FUNCTIONS.md`
- `KNOWN_MEMORY.md`
- `REVERSE_ENGINEERING_LOG.md`

## Phase 1 — Reproducible build pipeline

Build: **Original ROM → validation → extraction → decompression → modification → recompression → rebuild → patch generation**

Requirements:
- Never overwrite original ROM
- Reproducible builds
- Patch generation
- Build report

## Phase 2 — First proof of concept

Modify ONE dialogue string. Prove:
- Extraction
- Editing
- Rebuilding
- Reinsertion
- Emulator verification

Do not proceed to major gameplay hacking until this works.

## Phase 3 — Data discovery

Identify:

- **Characters**
  - IDs
  - Party slots
  - Active character
  - Recruitment flags
  - Stats
  - Animations
  - Portraits
  - Combat data
- **Progression**
  - XP
  - Levels
  - Level-up calculations
  - Stat growth
  - Stat points
  - POW progression
  - Level cap
- **Items**
  - Equipment
  - Stat bonuses
  - Effects
  - Prices
  - Rewards
  - Drops
- **Chao**
  - IDs
  - Data
  - Bonuses
  - Progression
  - Wireless/trading
  - Save representation
- **Enemies**
  - IDs
  - Stats
  - Levels
  - Encounters
  - Bosses
  - XP
  - Rewards

## Phase 4 — Character system

Understand how existing playable characters are represented. Do not create a new character. Investigate:

- Character IDs
- Party membership
- Recruitment
- Active character
- Story requirements
- Combat
- POW abilities
- Animations
- Portraits
- Overworld behavior
- Save data

## Phase 5 — Shadow Mode

Goal: start a new game with Shadow as the primary character instead of Sonic. Investigate:

- Active character
- Starting party
- Starting stats
- Equipment
- Character flags
- Story conditions
- Dialogue
- Cutscenes
- Animations
- Portraits
- Combat
- Save/load

Prefer redirecting existing systems over creating new ones.

## Phase 6 — Level cap

Investigate the original level cap.

- Target: Level 50, potentially Level 99
- Investigate:
  - Cap constants
  - XP
  - Level tables
  - Stat growth
  - POW progression
  - UI
  - Save data

First prove level 31. Then level 50. Then investigate level 99.

## Phase 7 — Character abilities

Investigate the ability/POW architecture. Determine whether abilities consist of:

- Effects
- IDs
- Animations
- Targeting
- Formulas
- Timing
- Resource costs
- Native functions

Experiment with:
- Modifying existing abilities
- Giving existing abilities to different characters
- Combining existing effects
- Eventually creating new behavior

Potential ideas:
- Sonic: teleport, high-speed dash, multi-target attack
- Shadow: Chaos Control, multi-dash, teleport, defensive effect

## Phase 8 — Equipment

Investigate and expose: attack, defense, speed, luck, effects, prices, requirements, drops.

Create equipment rebalance profiles. Goal: make previously weak or unused equipment meaningful.

## Phase 9 — Chao overhaul

Reverse-engineer: Chao storage, stats, bonuses, progression, trading, wireless data, save data.

Investigate replacing multiplayer-dependent progression with local progression.

Potential: **Chao XP → Chao Level → stronger bonuses**

Potential stats: Attack, Defense, Speed, Luck, special effect.

## Phase 10 — Enemy scaling

Determine whether enemy stats are: fixed, level-based, formula-based, encounter-based, hardcoded, or hybrid.

First reproduce existing calculations. Then investigate dynamic scaling.

- Potential reference: active character, highest party level, average party level
- Potential scaling: HP, attack, defense, speed, luck, XP, rewards

## Phase 11 — Boss scaling

Treat bosses separately. Investigate: unique stats, scripted behavior, phases, AI, HP, damage, encounter structures.

Implement independent boss scaling. Do not break scripted encounters.

## Phase 12 — Party freedom

Preserve story recruitment. Once a character has been unlocked:
- Allow greater party freedom
- Remove unnecessary restrictions
- Preserve mandatory story requirements

Investigate: party slots, mandatory characters, cutscenes, dialogue, story dependencies.

## Phase 13 — New Game+

The original game already has NG+. Investigate modifying it rather than recreating it.

Potential: retain equipment, retain Chao, retain abilities, expanded level cap, enemy scaling, altered reset behavior.

## Phase 14 — Randomized character recruitment

Investigate randomizing character unlock locations.

Example:
- Original: Chapter 2 → Tails, Chapter 3 → Knuckles
- Randomized: Chapter 2 → Shadow, Chapter 3 → Rouge

First understand: recruitment flags, story dependencies, dialogue, cutscenes, party requirements, character-specific quests.

## Phase 15 — Challenge modes

Create predefined profiles:

- **Vanilla+** — small improvements
- **Hard Mode** — enemy scaling, boss scaling, equipment rebalance, Chao progression, expanded level cap
- **Shadow Mode** — start as Shadow
- **Chaos Mode** — heavily randomized/altered systems
- **Randomizer** — randomized progression

## Phase 16 — Randomizer

Potential randomization: character recruitment, encounters, equipment, items, rewards, stats, Chao bonuses, abilities.

Must support deterministic seeds. Example:

```
chronicles randomize --seed 123456
```

Same seed = same result.

## Phase 17 — Mod profiles

Create human-readable profiles. Example:

```json
{
  "name": "Shadow Hard Mode",
  "characters": { "starting_character": "shadow" },
  "progression": { "level_cap": 50 },
  "enemy_scaling": { "enabled": true, "reference": "party_average", "percent_per_level": 8 },
  "boss_scaling": { "enabled": true },
  "equipment": { "rebalance": true },
  "chao": { "local_progression": true }
}
```

## Phase 18 — Mod Builder GUI

Only build the GUI once the underlying CLI/profile system is stable.

Categories:
- **Characters** — starting character, recruitment, party restrictions
- **Progression** — level cap, XP, stat growth, POW progression
- **Abilities** — ability modifications, special abilities
- **Items** — equipment, effects, prices, rewards
- **Chao** — progression, bonuses
- **Enemies** — scaling (HP, attack, defense, XP)
- **Bosses** — scaling
- **NG+** — persistence, reset behavior
- **Randomizer** — characters, encounters, equipment, items, stats
- **Advanced** — experimental patches, raw data editing, debug features

---

# CURRENT STATUS (2026-10-09)

Read this first; it is the resume point. Detail lives in
[REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md).

## What the user is playing

`build/ultimate_lifeform.nds` — a Shadow-led run, currently around Chapter 4-5,
approaching the first Lord Ix fight. `build/ultimate_lifeform_scaled.nds` is the same
build plus the enemy difficulty curve, with the save copied, waiting to be tested on
that fight. DeSmuME 0.9.11; saves live in `Old Desmume/Battery/<romname>.dsv`.

## Shipped and confirmed in game

Shadow Mode end to end — creature 0/4 swap (identity, portraits, progression, POW moves),
Chapter 4 recruitment grants Sonic with **no plot-flag edit** (predicted, then verified),
Dash III at level 8, Sonic<->Shadow dialogue swap, custom gear and Chao, POW/GRT/LCK
rebalance, and **the character sheet's Level row repointed to POW** via a one-byte ARM9
patch plus a TLK relabel.

## Character randomization — groundwork done, one gap left

Researched 2026-10-09. The vanilla ability map, unlock levels and carriers are in
[KNOWN_IDS.md](KNOWN_IDS.md).

**The softlock rule does not need a gate map**, which is the useful finding. Obstacles
carry no requirement field — every instance of a type reads identically, so the type *is*
the requirement, resolved in code. But a randomizer does not need to know which obstacle
wants what. It needs the recruitment order plus this invariant:

> For every prefix of the recruitment order, the set of abilities (and levels) the party
> can field must be a superset of vanilla's at that point.

Any gate passable in vanilla then stays passable, whatever it requires.

**The gap is recruitment order.** `party.GDA` is only a slot-to-creature mapping. Order
is plot-driven, and the plot layer is now readable — `.plo` is GFF4 `PLTS` with named
flags, and `plt_gbl_inparty.plo` enumerates every `<CHAR>_IN_PARTY`. What is not decoded
is which plot *action* sets a flag, inside the T1/T2 entry structure. Decoding that gives
both the order the rule needs and the hook for reordering recruitment itself.

The other three pieces need no new research: POW moves move via `combo.GDA` column 2
(proven), stats via the `Adv_*` tables that `stat_curve` already writes, and ability
slots via `creatures.GDA` 19/20/21 with levels in `Adv_*` 12/13/14.

## Waiting on a playtest

Two builds are ready and neither has been run:

* **`build/full_randomizer.nds`** — all six randomizers at seed 1, with the three fixes
  from the second playtest (no model-less appearances, squad overworld model tracking its
  own member, creature class left alone). Watch for: the overworld model matching what
  loads in the battle, and whether an enemy's block pattern now matches its move.
* ~~**`build/clone_probe.nds`**~~ — **passed.** The appended creature loaded in the
  overworld and the battle, fought normally, and the victory screen named it.
* **`build/transplant_test.nds`** — the transplant mode at seed 1, nothing else
  randomized. Watch whether a high-multiplier move on a low-POW creature is survivable:
  Super Shot is a 300 multiplier and now sits on a level-2 Guardian Pawn with POW 8.
  `damage_scale` is the knob if it hurts.

`build/ultimate_lifeform.nds` is the playthrough build and is not to be rebuilt by any
other profile; the clobber guard enforces that.

## Tooling

`modbuild.py` drives everything from a JSON profile: 10 named features, profile
inheritance via `extends`, and ops for TLK/2DA/GDA/resource/ARM9 edits. `--no-patch`
skips BPS, which is the slow stage. The Tkinter GUI (`tools/gui/modpack_maker.py`) is a
form over the same registry — Characters / Game / Items tabs, reads the ROM to show
current values, named pickers with decoded item icons. `tools/recon/callgraph.py` maps
every THUMB BL in ARM9.

## The two open projects

**Runtime party-level enemy scaling.** Wanted because static scaling helps a first
playthrough but does nothing on NG+ at level 20, where 350 or 525 HP both die in one
turn. Capability is ready — `arm9_patch` is proven in game and there are 1186 bytes of
code cave (largest run 274). **Blocked on one address**: where combat loads enemy stats.
Static analysis is exhausted (see the 2026-10-08 log entry); this needs melonDS GDB
breakpoints. (Static scaling briefly looked blocked on the same address; it was not —
see the 2026-10-08 correction entry.) The party level's RAM address is separately findable with DeSmuME's RAM
search.

**Randomizer.** Eight features exist and build: `randomize_encounters` (species
appearance remap), `randomize_items`, `randomize_chao`, `randomize_shops`,
`randomize_chests` (placed loot), `randomize_placements` (which enemy group spawns
where, banded by difficulty), `randomize_drops` and `randomize_rewards`, all exposed on
the GUI's Randomizer tab. `randomize_encounters` also has a `transplant` mode that
appends real creatures rather than reskinning. **None is confirmed in play yet.** `profiles/full_randomizer.json`
builds all four at seed 1.

Two pieces are still missing:

* ~~**Moves do not travel with a reskin.**~~ **Done** (2026-10-09). `randomize_encounters`
  gained `mode: "transplant"`, which clones each used species into a real new creature
  row with the donor's identity, class, innate abilities and its own POW moves, carrying
  the victim's stats. Appending creature rows is **confirmed in game**: the clone probe's
  level-2 Gizoid loaded in the overworld and the battle and the victory screen named it.
  `profiles/transplant_test.json` builds it at seed 1 (creatures 128 -> 188, combo
  155 -> 230) and has **not been run in game yet**. Old note, for context: `randomize_encounters` moves identity only, so a
  Gizoid-looking enemy fights with whatever moves its slot had. A real swap needs cloned
  `creatures.GDA` rows *and* cloned `combo.GDA` rows with rescaled damage, because combo
  rows are shared and a level-4 enemy swinging a level-14 move is not a fight.

  **The row writer is done** (2026-10-09): `gda_write.append_rows_clone` plus the
  `gda_clone_rows` op. It sidesteps both of `append_row`'s preconditions — a clone keeps
  the source's string offsets so no new string data is needed, and the row array is
  relocated to end-of-file rather than grown in place. Batched, so 5 clones cost 31 KB
  rather than 150 KB. `profiles/clone_probe.json` builds a 129-row `creatures.GDA` with a
  level-2 Gizoid in the opening area; **it has not been run in game yet**, and whether the
  engine tolerates a creature index past the vanilla 127 is exactly what it tests.

  Still to build on top: cloning `combo.GDA` rows with rescaled damage, then rewriting
  `randomize_encounters` to transplant whole creatures instead of skins.
* **Chest contents live in ARM9.** Settled 2026-10-10 by elimination, each step tested:
  not the `itembox` object (no item id), not the ARE pickup list (no itembox shares a
  position with any pickup), not `RandItems.GDA` (every table set to 100% of one item,
  new save, chest still gave a Health Seed), not the `.plo` files (a flag registry with
  no actions), and no GDA has the 53 rows a per-chest table would need. Randomizing them
  needs the same ARM9 capability as runtime enemy scaling and recruitment order.
* ~~**Chest contents are not decoded.**~~ ~~Done~~ — chests are `itembox` placeables
  (ARE object type 6) carrying no loot; the items come from `RandItems.GDA` (22 weighted
  drop tables) and quest payouts from `rewards.GDA` (70 labelled rows). Both now have
  randomizers. The remaining unknown is which drop table a *specific* chest reads, which
  loot randomization does not need.

`randomize_items` and `randomize_chao` rewrite item and Chao descriptions to match what
they now do, which is not cosmetic: POW and GRT are never drawn on the character sheet, so
a player cannot equip a randomized item and read off the difference. The description is
the only interface. Code-driven Chao keep their vanilla description — the ARM9 effect it
describes is still true — and the new stats are appended to it.

The alternative would be showing POW and GRT on the character sheet directly. The
mechanism is known and half-proven: the sheet is seven unrolled 110-byte blocks each
ending `movs r2, #<stat id>`, and repointing the Level row to POW took **one byte** and is
confirmed in game. But all seven rows are spoken for, so GRT costs another row — the
cheap win has already been taken.

## Known-unverified

`stat_curve` and `store_stock` are build-verified but never observed in play.

`enemy_scaling` gained `grt_per_level` on 2026-10-10 and was retuned once POW and GRT
were confirmed in play. The levers are not interchangeable: **HP is the safe one**
(longer fights, damage numbers intact), POW is felt directly, **GRT shrinks the player's
damage numbers** and **Defense most likely makes the player miss** — both default to 0,
because a difficulty curve that hides your own progress reads as the game cheating.
`ultimate_lifeform_scaled` now runs HP 8%/level, POW 3.5%, grit and defense 0.

`enemy_scaling` was found broken in play on 2026-10-08 and **fixed the same day**. HP is
stored in two `creatures.GDA` columns — 2 (spawn) and 7 (`health`, the bar's maximum) —
and the feature wrote only column 7, so enemies kept vanilla HP under an inflated ceiling.
POW and DEF were never affected. Both columns are now written; rebuilt and read back
clean, but **not yet observed in play after the fix**.

## Hard limits found

Three movement slots maximum; a fourth needs ARM9. Chao unique effects and their odds are
hardcoded by item id — 20 such slots can be repurposed but no 21st created. Water and Ice
move elements are unconfirmed and deliberately refused by `pow_move`.

## Development rule

Every major feature follows: **RESEARCH → PROOF OF CONCEPT → TEST → DOCUMENT → PRODUCTIZE**

Never skip the research stage. Never assume something is possible simply because it sounds technically straightforward. Never build the GUI around an unverified feature.

The goal is a stable, reproducible, documented modding framework — not a fragile one-off ROM hack.
