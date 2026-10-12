# Sonic Chronicles Modding Framework — Roadmap

## Phase 0 — Research and reconnaissance

**Done.** EU ROM `CSNP` (No-Intro #2699) confirmed from the header; HERF/GFF4/TLK/GDA all parse; ChroniclesDX and xoreos surveyed in [RESEARCH.md](RESEARCH.md).

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

**Done.** `tools/build/modbuild.py` rebuilds the ROM from a profile and verifies every stage; a zero-edit rebuild is byte-identical, which is what makes `profiles/control*.json` usable as a baseline.

Build: **Original ROM → validation → extraction → decompression → modification → recompression → rebuild → patch generation**

Requirements:
- Never overwrite original ROM
- Reproducible builds
- Patch generation
- Build report

## Phase 2 — First proof of concept

**Done 2026-10-05.** A single TLK string changed in game, which is what unlocked everything after it.

Modify ONE dialogue string. Prove:
- Extraction
- Editing
- Rebuilding
- Reinsertion
- Emulator verification

Do not proceed to major gameplay hacking until this works.

## Phase 3 — Data discovery

**Done.** The tables that mattered are mapped in [KNOWN_IDS.md](KNOWN_IDS.md); the formats in [KNOWN_FORMATS.md](KNOWN_FORMATS.md).

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

**Done.** `creatures.GDA` is the character record and `Adv_<Name>.GDA` the progression table; the 42 columns that differ among the 11 playable rows are documented.

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

**Confirmed in game 2026-10-07.** Chapter 4 handed over Sonic, which is the finding Phase 14 was later built on: a story point grants a *row*, not a character.

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

**Shipped** as `level_cap`, confirmed in game. Note the 2026-10-11 bug: it used to rewrite the whole XP curve, not just the levels it added. `flatten` is now opt-in.

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

**Shipped** as `movement_slots` (build-verified) and `pow_move` (confirmed in game). The POW *animation and stylus minigame* are the part that did not fall - see Parked below.

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

**Shipped** as `custom_item` and `randomize_items`, both confirmed in game. The hidden stats and what the item panel does and does not draw are in [KNOWN_IDS.md](KNOWN_IDS.md).

Investigate and expose: attack, defense, speed, luck, effects, prices, requirements, drops.

Create equipment rebalance profiles. Goal: make previously weak or unused equipment meaningful.

## Phase 9 — Chao overhaul

**Shipped** as `chao_level`, `custom_chao` and `randomize_chao`, all confirmed in game. The original goal - local Chao levelling to replace wireless trading - is **not** met and cannot be: levels live in the save, so the feature grants a higher tier's *effects* instead. Two thirds of the Chao system is sealed off for good.

Reverse-engineer: Chao storage, stats, bonuses, progression, trading, wireless data, save data.

Investigate replacing multiplayer-dependent progression with local progression.

Potential: **Chao XP → Chao Level → stronger bonuses**

Potential stats: Attack, Defense, Speed, Luck, special effect.

## Phase 10 — Enemy scaling

**Shipped** as `enemy_scaling`, confirmed to the unit 2026-10-12: a level-7 Shield Pawn at 8%/level read 281 HP against a predicted 280.8.

Determine whether enemy stats are: fixed, level-based, formula-based, encounter-based, hardcoded, or hybrid.

First reproduce existing calculations. Then investigate dynamic scaling.

- Potential reference: active character, highest party level, average party level
- Potential scaling: HP, attack, defense, speed, luck, XP, rewards

## Phase 11 — Boss scaling

**Partly shipped.** `enemy_scaling` carries `include_bosses`, so bosses can be scaled with everything else. Boss-specific handling - unique stats, scripted phases, multi-stage fights - was never separated out, and no one has asked for it.

Treat bosses separately. Investigate: unique stats, scripted behavior, phases, AI, HP, damage, encounter structures.

Implement independent boss scaling. Do not break scripted encounters.

## Phase 12 — Party freedom

**Parked by the user's decision, 2026-10-11.** Not blocked - judged too likely to break progression in ways that only show up hours later, since a chapter that scripts a party around two specific characters has no obvious fallback when neither is available.

Preserve story recruitment. Once a character has been unlocked:
- Allow greater party freedom
- Remove unnecessary restrictions
- Preserve mandatory story requirements

Investigate: party slots, mandatory characters, cutscenes, dialogue, story dependencies.

## Phase 13 — New Game+

**Closed 2026-10-12 as largely moot.** The premise was wrong: the game does not have a
New Game+ in the sense the phase assumed.

**There is no completion marker and no cycle counter.** All 649 resolvable plot flags
were searched for anything meaning finished, replayed, cleared, beaten or restarted. The
27 hits are quests, puzzles, chapters and boss *phases* — `FACTORY_QUEST_COMPLETE`,
`GREEN_HILLS_BRIDGE_PUZZLE_COMPLETE`, `IX_PHASE1_COMPLETE`. Not one marks a finished
playthrough. The game's own help text settles the rest: *"To start a new game, select and
then delete one of your save slots"* (string 18271).

So a replay is a player's own decision to keep or delete a save, and nothing in the game
records that it happened. That dissolves most of the phase:

* **retain equipment / Chao / abilities** — there is no reset to opt out of. Keep the
  save and you keep everything already.
* **expanded level cap** — `level_cap` does this, and does not care which run it is.
* **enemy scaling** — `enemy_scaling` does this globally. The version that would make a
  replay meaningful is *party-relative* scaling, which is one of the two ARM9 blockers
  and is tracked there, not here.
* **altered reset behaviour** — there is no reset.

Nothing is left in this phase that is not either already shipped or already tracked as an
ARM9 blocker.

## Phase 14 — Randomized character recruitment

**Confirmed in game 2026-10-11** as `randomize_characters: {"recruitment": true}`, over
three recruitment points and a following fight with multi-character moves. (This line read
"build-verified, awaiting a playtest" until 2026-10-12, two days after the playtest.)

It works by moving a character's whole identity between the eleven playable
`creatures.GDA` rows, because a story point grants a *row*, not a character — the thing
Shadow Mode confirmed in play on 2026-10-07 when Chapter 4 handed over Sonic. So Chapter 2
giving you Shadow is the Chapter 2 row holding Shadow's identity.

The thing that made it buildable earlier than expected: **movement abilities stay with the
slot**, which satisfies the prefix invariant below *without consulting the recruitment
order at all*. The order derived from `plt_fp_*.plo` is still only a derivation, and this
design does not depend on it. Abilities are therefore not randomized, and that is the
trade: a softlock becomes impossible rather than merely unlikely.

Still open: dialogue and cutscenes name characters in authored TLK text and are not
touched, and the bosses' own `combo.GDA` rows keep their original kit. Both cosmetic.

## Phase 15 — Challenge modes

**Shipped 2026-10-11** as four presets (`profiles/presets/`) and a Presets tab in the Mod Pack Maker. Vanilla+, Hard Mode, Randomizer, Chaos Mode.

Create predefined profiles:

- **Vanilla+** — small improvements
- **Hard Mode** — enemy scaling, boss scaling, equipment rebalance, Chao progression, expanded level cap
- **Shadow Mode** — start as Shadow
- **Chaos Mode** — heavily randomized/altered systems
- **Randomizer** — randomized progression

## Phase 16 — Randomizer

**Shipped.** Nine randomizers, all confirmed in game: characters, encounters, placements, items, Chao, shops, chests, drops and rewards. One seed drives the lot.

Potential randomization: character recruitment, encounters, equipment, items, rewards, stats, Chao bonuses, abilities.

Must support deterministic seeds. Example:

```
chronicles randomize --seed 123456
```

Same seed = same result.

## Phase 17 — Mod profiles

**Shipped.** Profiles are the only way anything is built - features expand into primitive edits so there is exactly one apply-and-verify path. `extends` inherits; explicit `edits` override features; two features writing one cell different values is refused.

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

**Shipped.** The Mod Pack Maker (`tools/gui/modpack_maker.py`): five tabs, every feature badged with its own confidence, a one-folder Windows release and a `.bat` for running from source. It drives the same profile system as the CLI, which was the precondition this phase set itself.

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

# CURRENT STATUS (2026-10-12)

Read this first; it is the resume point. Detail lives in
[REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md).

**The phases above are the original brief and are deliberately not rewritten** -
they record what was planned, which is worth keeping separate from what happened.
Each one now carries a status line so the two can be read together.

## What the user is playing

`build/ultimate_lifeform.nds` — a Shadow-led run, currently around Chapter 4-5,
approaching the first Lord Ix fight. `build/ultimate_lifeform_scaled.nds` is the same
build plus the enemy difficulty curve, with the save copied, waiting to be tested on
that fight. DeSmuME 0.9.11; saves live in `Old Desmume/Battery/<romname>.dsv`.

## Shipped and confirmed in game

**`randomize_characters` (2026-10-11)** — recruitment and moves confirmed in play from a new
game. Recruitment moves a character's whole identity between the eleven playable
`creatures.GDA` rows, so a story point hands out whoever now lives in the row it grants;
movement abilities are a floor, so no gate can become impassable. POW moves are dealt
across the cast within participant count, element, role and hit count.

**The `stats` half is the exception and is still unconfirmed in game.** It permutes whole
stat lines across the progression tables, and the registry's per-feature badge cannot say
that one half of a feature is proven and another is not. It is **off in the randomizer
preset** as of 2026-10-12: a derangement is conserved across the cast, but the starting
character is the one roll a player cannot escape, and seed 1 put Omega on Amy's line for
-25% HP by level 8. The decisive reading, if anyone wants to confirm it, is a dealt
character's **level 2** HP — level 1 is masked by `creatures.GDA` column 2, the spawn HP,
which is why an earlier check of level 1 proved nothing.

Phase 14 is closed, and recruitment order turned
out **not** to be behind the ARM9 wall after all — only the animation and stylus pattern
a move is performed with.

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

**The vanilla recruitment order is now derivable from the plot files** (2026-10-10).
Recruitment is one plot file per character — `plt_fp_<char>.plo`, "find party", for all
ten non-Sonic characters, plus `plt_fpa2_<char>.plo` for the nine who can be in Act 2 —
and the flags inside name the join conditions outright: `AMY_GET`, `TAILS_GET`,
`KNUCKLES_FOUND`, `EGGMAN_FOUND`, `SHADOW_GET` behind a three-stage fight,
`FROGGY_QUEST_COMPLETE` → `BIG_GET`, `GOT_CHEESE` → `CREAM_GET`, `OMEGA_FIXED` →
`OMEGA_GET`. The ~70 `MAP_PIN_*` flags place them, and are numbered in area progression
order (GHZ → CCZ → MRZ → BRZ → MET → ANG → GRZ → KRO → NRG → ZOA → VOX → NOC). Full table
in the log.

**That is a derivation, not a confirmation.** It should be checked against a real
playthrough before anything is built on it, because a wrong order here is a softlock
rather than a bad roll.

**Recruitment randomization no longer waits on it** (2026-10-11). Pinning the ability
slots to the recruitment slot satisfies the invariant exactly rather than approximately —
every point grants what vanilla granted there — so the order is not an input. Confirming
it is still the next step for *randomizing abilities*, which remains unbuilt for exactly
the reason above.

*Re-wiring* a flag still needs the debugger: nothing in the data says "this flag means
add this character", ARM9 holds neither the flag names nor their ids (`OMEGA_GET`'s 413
does not appear once as an aligned constant), and a dialogue node carries no party-member
field — all six fields of its action struct were decoded on 2026-10-11 and every one is a
plot/flag reference. Re-*ordering* recruitment turned out not to need any of that: leave
the flags alone and change what lives in the row they grant.

Of the other three pieces, two need no new research — stats via the `Adv_*` tables that
`stat_curve` already writes, ability slots via `creatures.GDA` 19/20/21 with levels in
`Adv_*` 12/13/14 — and the third was **wrong until 2026-10-10**: POW moves do *not* move
via `combo.GDA` column 2. That column is a participant requirement; a moveset is bound to
its block of rows. `randomize_characters` now moves the row contents, and the playtest
that disproved the old approach is in the log.

## Published

The project is on GitHub as a **private** repo:
`DumbCode4Fun/Sonic-Chronicles-Randomizer`. 80 files, MIT licensed, with README,
CREDITS and screenshots under `assets/`. `.gitignore` excludes the ~1.8 GB of built ROMs,
saves and `CLAUDE.md`; commits use the GitHub noreply address, no personal email. Flip to
public when ready — note that going public exposes the whole history, so never commit a
ROM even temporarily.

## Two things behind the ARM9 wall

Everything reachable from the data files is built. These two need the melonDS GDB
session and nothing else will unblock them:

1. **Party-relative enemy scaling** — needs the combat stat-load address. The cheap
   static route was tried and failed: `creatures.GDA` column names are recoverable by
   hashing, but none of those hashes appears in ARM9, so the binary was compiled against
   fixed indices that look like any other small constant.
2. **Re-ordering recruitment** — plot logic is native code. Note this is now a smaller
   claim than it was: *reading* the vanilla order turned out to be a data problem and is
   solved (see Character randomization above). What still needs the debugger is making
   recruitment happen in a different order. The entry point is precise: breakpoint the
   write that sets flag 56, 124, 413 or 450 (`BIG_GET`, `SHADOW_GET`, `OMEGA_GET`,
   `CREAM_GET`) and watch what reads it.
3. **Ability gates beyond Dash and Smash.** Placeable type 1 — the 69 "blocks" — carries
   `(ability, level, 0)`, and only Dash and Smash appear, which fits: they are the two
   abilities that remove an obstacle. Where Fly, Jump, Climb, Teleport and Stealth are
   gated is unknown, and the per-area movement tables `areas.GDA` names
   (`GreenHillZoneMovement.gda` and friends) are **not in the archive** — dangling
   asset-pipeline names, exactly like the debug menu's missing command strings. This
   matters less than it sounds, because the softlock invariant does not need a gate map.

**Chest contents came off this list on 2026-10-10.** They were never in ARM9: a chest's
three item slots are the `float32` triple at fields 40020/40021/40022 of its placeable.
The elimination that put them here was sound at every step and still reached the wrong
answer, because the one field nobody read was the one that mattered. Worth remembering
before trusting the other two.

**Which Chao hatches from an egg was dropped**, not solved. All 115 eggs carry `(0,0,0)`
and it would need the same debugger session, but nobody wants randomized eggs — see the
Chao section below for what is actually wanted.

**How to get a lot of Chao did get solved, from the other end** (2026-10-10). A ring and a
Chao egg are the same placeable struct with one field different, so any ring can be turned
into an egg in place: `profiles/chao_farm.json` makes 100 of Green Hill's 183 rings hatch
Chao. Which species each one gives is still the lottery, but the sample size stops
mattering when you have a hundred of them.

That session is now the single highest-value piece of work left, and **the tooling for
it is built** (2026-10-10): `tools/recon/gdbstub.py` speaks the GDB remote protocol to
melonDS' stub in pure standard library, and `tools/recon/gdb_experiments.py` scripts both
experiments. No ARM toolchain to install — which matters, because a 1 GB devkitARM for
two watchpoints is a poor trade, and a scripted experiment can be re-run and pasted into
the log where an interactive gdb session cannot.

What is still needed from a human is the emulator half:

1. **Install melonDS**, enable the GDB stub (Config → Emu settings → Devtools), and
   **turn the JIT off** or stepping misbehaves.
2. **Check this game actually runs on it.** This is not a formality: the project plays on
   DeSmuME 0.9.11 precisely because other builds misbehave with Sonic Chronicles, and
   DeSmuME 0.9.11 has no GDB stub at all (confirmed — no stub strings in the shipped
   binary, no `--arm9gdb` flag). If melonDS cannot boot the game, the whole route needs
   rethinking and that is worth knowing in ten minutes rather than after an afternoon.
   `py tools/recon/gdbstub.py probe` reports whether the PC is moving and RAM changing.
3. Then run the experiments.

**Scaling** is the easier of the two and should go first. The creature table is 232 bytes
per row and is almost certainly in main RAM in its file form, so the script searches for a
known row's bytes, puts a read watchpoint on its HP field and waits for a battle; the PC
that fires is inside the stat loader. **Recruitment** needs the plot-flag block, which was
*not* findable in a save file — an 83-byte window that only gains bits matches 1,078
places in a 64 KB save — but is findable in RAM by snapshotting around two separate plot
events and intersecting, since monotonicity across two events is a far stronger filter
than across one.

## Chao — the direction that is actually wanted

**Not** randomized eggs. Dropped on 2026-10-10 as pointless: it would cost the same
debugger session as enemy scaling and nobody wants the result.

What is wanted is **a way for a Chao to level up that does not require trading over
wireless.** In the retail game a Chao grows through local multiplayer trades, which in
2026 means the feature is effectively dead for a single player — the Chao system is
present, authored and unreachable.

Nothing is known yet. The starting points, from a survey on 2026-10-10:

* `Chaos.GDA` — 45 rows, 14 columns, the Chao definitions `randomize_chao` and
  `custom_chao` already write. Growth tiers live here; what *advances* a tier does not.
* **`ChaoGarden_ExpBot.gui`** — the name says experience, and it is the one Chao GUI
  that implies a progression counter rather than a display.
* **`ChaoGarden_WireIcons.gui`** — the wireless-trade UI. Whatever gates a trade is
  reachable from whatever this screen talks to.
* `ChaoGarden.GDA` is **not** it — one row of intro-screen parameters.

**Answered 2026-10-10, and the answer is that there is no counter.** The game's own help
text states the rule: level 2 needs a wireless trade with one person and level 3 a trade
with a *different* person, so it tracks **who** you traded with, not how often. There is
no threshold to lower and nothing to nudge.

`chao_level` takes the reachable path instead, and is **confirmed in game**: a Level 1
Rugle took Sonic's Luck from 50 to 53, its Max-tier value. `Chaos.GDA` columns 6/7/8 are the item ids
a Chao grants at each level, so pointing the lower ones at the higher hands a freshly
hatched Chao its Max-level effects. 25 of the 45 Chao gain outright; 20 are code-driven
and repointed on spec; 6 already use one item for all three levels.

Still open, if the displayed level itself matters: it lives in the save, and the save's
Chao records have not been located. `save_edit.py --party` finds character stat blocks by
shape and the same approach should work here — a Chao record must hold at least an id, a
level and a copy count.

## Waiting on a playtest

Two builds are ready and neither has been run:

* **`build/full_randomizer.nds`** — all six randomizers at seed 1, with the three fixes
  from the second playtest (no model-less appearances, squad overworld model tracking its
  own member, creature class left alone). Watch for: the overworld model matching what
  loads in the battle, and whether an enemy's block pattern now matches its move.
* ~~**`build/transplant_test.nds`** — is a transplanted enemy's high-multiplier move
  survivable at local power?~~ **Passed.** A transplanted Gizoid Centurion used Quake
  Punch for **2 damage**. POW move damage is a percentage of a basic attack, so the
  multiplier rides on the creature's own POW and a donor move arrives harmless at a low
  level. Transplant mode is safe; if anything it is now too gentle, and nudging POW up
  for transplants is the open tuning question.
* ~~**Are the kind-4 "pickups" real?**~~ **Answered: no, and the feature is gone.**
  The player's doubt was right. Resolving the plot flag at field 40013 against
  `plotflags.GDA` showed list 40002 to be a plot-event trigger table - the three "Voxai
  Teleporters" in Green Hill are the three projectors of the scientist's side quest,
  gated on `PROJECTOR_QUEST_GIVEN`. The payload was never an item id. `randomize_pickups`
  was removed on 2026-10-10; `randomize_chests` does the job it was meant to.
* ~~**`build/clone_probe.nds`**~~ — **passed.** The appended creature loaded in the
  overworld and the battle, fought normally, and the victory screen named it.
* ~~**`build/transplant_test.nds`**~~ — **passed**, and answered its own question: a
  transplanted Gizoid Centurion's Quake Punch did 2 damage. `damage_scale` is not needed
  downward; the open question is whether transplants need POW *raised* to matter.

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
`randomize_chests` (all 53 chests), `randomize_placements` (which enemy group spawns where, banded by difficulty),
`randomize_drops` and `randomize_rewards`, all exposed on the GUI's Randomizer tab.
`randomize_encounters` also has a `transplant` mode that appends real creatures rather
than reskinning. **All eight are confirmed in play** (2026-10-10), each against a prediction made from
the data before the ROM was built: `randomize_chests`, `randomize_placements`,
`randomize_encounters` (both modes), `randomize_rewards`, `randomize_chao`,
`randomize_items`, `randomize_shops` and `randomize_drops`. `profiles/playtest_god.json`
is what cleared the last two — the full randomizer plus a party that cannot lose. `profiles/full_randomizer.json` builds
them all at seed 1.

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
* ~~**Chest contents live in ARM9.**~~ **Wrong, corrected 2026-10-10.** A chest's loot is
  the `float32` triple at fields 40020/40021/40022 of its type-6 placeable in area list
  40001 — three `Items.GDA` ids, -1 for an empty slot, 120 filled slots across 53 chests.
  `randomize_chests` writes them in place. The elimination that reached the ARM9 answer
  tested each of its steps and was sound; it simply never read label 4, which is where
  the position actually lives, and so the one float triple on screen looked like it had
  to be geometry.

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
