# Sonic Chronicles Mod Builder

A reverse-engineering project and modding toolkit for **Sonic Chronicles: The Dark
Brotherhood** (Nintendo DS, BioWare, 2008) — including, as far as I can establish, the
first randomizer for the game.

Everything here is written from scratch in pure Python against the ROM's own data. There
is no game data in this repository and never will be: you supply your own legally
obtained dump, and the tools read it, build a modified copy beside it, and never write to
the original.

> **Status.** The data layer is thoroughly mapped and **every randomizer feature is
> confirmed in play**, recruitment order included — it turned out to be editable after
> all, because a story point grants a creature *row* rather than a character. Two things
> remain locked inside the ARM9 executable — party-relative enemy scaling, and the
> animation and stylus pattern a POW move is performed with — and are documented as such
> rather than guessed at. Features carry an honest badge: *confirmed in game* or
> *build-verified only*.

![The Mod Pack Maker's Randomizer tab](assets/mod-pack-maker.png)

*The Randomizer tab. One seed drives all nine randomizers — leave it blank and the build
picks one, then writes it into the profile saved beside the ROM so the run stays
reproducible. Every feature carries the badge it earned, and **all nine are `confirmed in
game`**, each verified against a prediction made from the data before the ROM was built.
`randomize_characters` leads, with its three halves: who each story point hands you, which
POW moves they carry, and whose stat line they grow on. The third of those is the one
exception to the badge — stat shuffling is build-verified only, and is off by default.*

---

## Why this game is interesting

Sonic Chronicles was developed by BioWare and runs on a descendant of the **Aurora**
engine — the lineage behind Neverwinter Nights, KOTOR and Dragon Age. So underneath a
Sonic RPG sit BioWare's data formats: GFF4 structures, TLK string tables, GDA/2DA tables,
and an ERF-family archive.

That is the good news. The bad news, and the thing that shapes this whole project: unlike
every other Aurora game, **Sonic Chronicles ships no scripts at all**. There is no
NWScript, no compiled script resources, nothing. The plot files are a registry of named
flags and journal text with no actions in them. All game *logic* is native ARM9 code.

The practical consequence is a hard line through the middle of the game. Anything
expressed as data — stats, moves, items, encounters, shops, progression — is editable and
most of it is now understood. Anything expressed as logic is not, without debugging the
binary.

---

## What it can do

Eighteen named features, each a parameter block in a JSON profile. Run
`py tools/build/modbuild.py --list-features` for the live list with badges.

### Randomizer

| feature | what it does |
|---|---|
| `randomize_characters` | Deals out who you are given and when, which POW moves they carry, and whose stat line they grow on |
| `randomize_encounters` | Reskins every enemy species, or (in `transplant` mode) appends real new creatures carrying the donor's model, moves and innate abilities at the local power level |
| `randomize_placements` | Moves enemy groups between spawn points, banded by difficulty so an area stays fair |
| `randomize_items` | Re-rolls what each piece of gear does, and rewrites its description to match |
| `randomize_chao` | Re-rolls Chao stat bonuses and gives the hardcoded-effect Chao stats they never had |
| `randomize_shops` | Redeals shop stock; prices stay with the slot so early finds stay affordable |
| `randomize_chests` | Redeals what all 53 chests hold — 120 filled slots, three to a chest |
| `randomize_drops` | Redeals the weighted drop tables, rates untouched |
| `randomize_rewards` | Redeals quest and event rewards, with optional XP/gold scaling |

<table>
<tr>
<td width="50%"><img src="assets/randomized-placement.png" alt="An enemy displaced into the opening zone"></td>
<td width="50%"><img src="assets/randomized-encounter.png" alt="The opening encounter, reskinned"></td>
</tr>
<tr>
<td><em><code>randomize_placements</code> — a Queen Wasp pack displaced into Green Hill.
From a placements-only build, so nothing reskinned it: that group really was moved, and
banding held it to level 5.</em></td>
<td><em><code>randomize_encounters</code> — the tutorial fight, same scripted slot, a
different creature in it.</em></td>
</tr>
</table>

<table>
<tr>
<td width="33%"><img src="assets/randomized-start.png" alt="Omega in the opening zone"></td>
<td width="33%"><img src="assets/randomized-pow-moves.png" alt="Omega's dealt POW move list"></td>
<td width="33%"><img src="assets/randomized-abilities.png" alt="Shadow with a borrowed movement ability"></td>
</tr>
<tr>
<td><em>The run opens as <strong>Omega</strong>. Recruitment grants a creature
<em>row</em>, not a character, so every story recruitment point hands out whoever now
lives in that row.</em></td>
<td><em>Omega's POW list: Rouge's Tornado Kick, Shadow's Chaos Blast, Tails' Tinker and
his own Machine Gunner. A dealt move brings its damage, cost and status effect — and its
description, which still credits whoever it was written for.</em></td>
<td><em>Shadow, recruited where Tails normally joins, keeps Tails' <strong>Fly</strong>
because that slot's abilities are a floor — plus his own Dash. No gate can become
impassable.</em></td>
</tr>
</table>

<table>
<tr>
<td width="50%"><img src="assets/randomized-team-move.png" alt="A team move with a remapped cast"></td>
<td width="50%"><img src="assets/randomized-status-effect.png" alt="A borrowed move's status effect"></td>
</tr>
<tr>
<td><em>Spin Cycle is written for <strong>Amy and Cream</strong> — the description still
says so — but the computed <strong>Team:</strong> line reads Knuckles and Shadow, because
every owner and partner reference is remapped to wherever that character now lives. Get
this wrong and a character cannot use their own solo moves; it was wrong for a few hours
on 2026-10-11.</em></td>
<td><em>A dealt move brings its <strong>effect</strong>, not just its label. This slot
applied Weakened in vanilla; the move that landed in it applies Vulnerable, at its own
80% chance. Damage, PP cost and status all travel — only the animation and the stylus
pattern stay with the character.</em></td>
</tr>
</table>

#### Tuning the difficulty band

`randomize_placements` takes a `band`, and it is the one knob worth understanding before
you turn it. A squad's band is `highest member level ÷ band`, so the number is the
**width of each bucket**, and groups trade only inside one. It controls how far a group
may travel in difficulty — not how much shuffling happens.

Of the game's 332 squads, **118 can move at all**; the rest are bosses, story actors or
single-member squads, which stay put whatever you set. Those 118 run from level 2 to 18:

| `band` | buckets | biggest bucket | what you get |
|---|---|---|---|
| 1 | 16 | 24 squads | tightest — only identical top levels trade |
| **3** | **7** | **32** | the default, and what was playtested |
| 5 | 4 | 44 | loose: level 15 can meet level 19 |
| 10 | 2 | 68 | two buckets, roughly early and late game |
| 25 | 1 | 118 | no banding — a level-18 pack can spawn in Green Hill |

Every value still shuffles nearly everything, so turning it down does not mean less
randomization; it means the randomization stays closer to home.

One catch: **it buckets rather than slides.** At `band: 3` the boundaries sit at levels
3, 6, 9 and 12, so a level-5 and a level-6 group are one level apart in *different*
buckets and never trade, while level-3 and level-5 groups do. It is not "within ±3
levels".

Safety is built in rather than hoped for: quest items and key items never move, bosses and
scripted spawn points are left alone, difficulty banding keeps a level-20 enemy out of the
first zone, and a recruitment shuffle can never cost the party an ability it needed. Those rules were not guesses — each one exists because a playtest broke
something. See [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md).

### Presets

Whole mods, ready to build, assembled only from features confirmed in game. The GUI's
**Presets** tab builds one directly; the CLI takes them like any other profile.

| preset | what you get |
|---|---|
| **Vanilla+** | The game as intended, plus the two things it can no longer give you: Chao reach their Max-tier effects without wireless trading, and every mid-game joiner is put on Sonic's XP curve instead of one that assumes a head start |
| **Hard Mode** | A difficulty curve keyed to each enemy's own level, and the cap raised to 40. Grit is deliberately left alone — it is damage reduction, and raising it makes stalemates rather than challenges |
| **Randomizer** | Every randomizer at one seed and nothing else. Vanilla difficulty, everything else dealt out — plus the whole cast on Sonic's XP curve at 1.5x, because randomized recruitment means *someone other than Sonic starts the game*, and the vanilla curves tax that by up to 132% |
| **Chaos Mode** | The full randomizer on top of the hard-mode curve, with the cap raised and the Chao system unsealed |

### Everything else

`xp_rate`, `level_cap`, `xp_curve`, `pp_curve`, `stat_curve`, `enemy_scaling`,
`movement_slots`, `pow_move`, `custom_item`, `custom_chao`, `chao_level`, `store_stock`.

Highlights: level the whole cast faster with one number, raise the cap past 30, give any
character any movement ability in any of their three slots, convert multi-character POW
moves to solo, build custom gear and Chao, and retune the enemy difficulty curve.

Two notes that save a play session. **XP is changed by lowering thresholds, not by raising
awards** — combat XP is not in the game's data, so there is nothing to multiply; the result
for the player is the same. And **`xp_curve` and `xp_rate` cannot be combined**, because
both write the same cell: use `xp_curve`'s own `rate` instead. The build refuses the
combination rather than picking one for you.

![The Mod Pack Maker's Characters tab](assets/mod-pack-maker-characters.png)

*The Characters tab, for when you want one specific change rather than a shuffle:
movement abilities, POW moves and the stat curve, per character. The values shown are read
from the ROM you selected, so what you see is what is actually in there; anything left
alone is not written. A movement slot and its level live in two different tables and
setting one without the other grants nothing, so the form writes both.*

**Stats are a curve, not a number.** Each row shows what the stat is at level 1 and at
level 30, and takes a multiplier (which keeps the curve's shape, so a character stays
proportionally stronger all the way up) and a flat bonus. Want a god-mode character? Give
them HP x10 and POW +500 and they will out-level the game.

One catch worth knowing before you try it: this edits the table a **level-up** reads. A
character's current numbers live in the save file, so a stat change does nothing to a game
already in progress until somebody gains a level — confirmed in play on 2026-10-10, by a
build that made every character unkillable and visibly did not. Start a new game, or use
`tools/build/save_edit.py --godmode` on the save you are already playing.

`chao_level` is the one that gives something back rather than changing it. A Chao reaches
level 2 only by trading over wireless with one person and level 3 only by trading with a
*different* person — the game tracks **who**, not how often — so in 2026 two thirds of
the Chao system is sealed off for good. The feature grants the Max-tier effects anyway.

---

## Quick start

### The easy way — download the folder

Grab the release zip, extract it anywhere, and run **`ModPackMaker.exe`**. Nothing to
install.

```
SonicChroniclesModBuilder/
├── ModPackMaker.exe     ← run this
├── _internal/           ← Python runtime, leave alone
├── profiles/            ← every profile, including presets/ — edit freely
└── assets/
```

It is a folder rather than a single .exe on purpose. A one-file build unpacks its whole
runtime into a temp directory on every launch, which is the shape antivirus heuristics
are built to catch; this one ships already unpacked, so nothing self-extracts, it starts
faster, and `profiles/` stays where you can read it.

Built ROMs land in `build/` beside the executable. **Your own ROM is never written to.**

### The other way — run from source

Requires **Python 3.8+** from [python.org](https://www.python.org/downloads/) with
*Add python.exe to PATH* ticked. No dependencies for anything in the normal path.
(`capstone` is optional and only used by the ARM9 disassembler.)

Double-click **`ModPackMaker.bat`**, which finds your Python and opens the same GUI. If
Python is missing it says so and points you at the download rather than flashing a
console and vanishing.

To build the release folder yourself: `py tools/build/make_release.py --zip`
(needs `pip install pyinstaller`).

```bash
py tools/build/modbuild.py <your-rom.nds> profiles/full_randomizer.json
```

That writes `build/full_randomizer.nds` plus a `.bps` patch, the recipe, and a JSON
report.

#### What "Skip patch" actually skips

**Not the ROM.** The ROM is always built, always verified, and always written — skipping
the patch returns right after that and nothing about `build/<name>.nds` changes. If you
are building something to play yourself, leave it skipped; it is on by default.

The `.bps` is a **second, separate artifact**: a binary delta between your source ROM and
the built one. It exists because of the one constraint this project cannot engineer around
— **a ROM cannot be shared.** A patch can: it is meaningless without the original game, so
it carries the mod and none of BioWare's data. That is why the build makes one at all.

It is also the slow stage by a wide margin. Measured on the randomizer build,
2026-10-12: **889 s to create the patch, 0.5 s to verify it.** So skipping saves about
fifteen minutes per build, and the half-second that actually proves the patch reproduces
the ROM byte for byte is not what costs you anything.

#### Patch or recipe? They are for different people

Both are ways to hand someone a mod, and the difference that matters is **what the
recipient has to do**:

| | size | they need | their cost |
|---|---|---|---|
| the ROM | 134 MB | nothing | **do not share this** |
| the `.bps` patch | 38 KB | their own ROM, and a patcher | **~1 second** |
| the recipe `.json` | ~3 KB | their own ROM, and this tool | **15–90 minutes** |

That last column is the whole answer. Applying a patch is a one-second memcpy-and-splice;
rebuilding from a recipe re-runs the entire build. For someone who just wants to play your
run, the patch is roughly a thousand times less trouble, and it needs none of this
project installed.

The recipe is for the other reader — the one who wants to see *what you did*, change the
seed, turn a feature off, or build on it. A patch is opaque and reproduces exactly one
build; a recipe is the build, in a form you can read and edit.

So: **send the patch to players and the recipe to tinkerers**, and if you are not sure,
send both. Together they are 41 KB.

#### Applying a patch someone sent you

**In the app: the Patches tab.** Point Source ROM at your own unmodified game, pick the
`.bps` you were sent, choose where the result goes, and press Apply patch. No terminal.

The same tab will also *make* a patch from a ROM you already built, which is the other
half of "Skip patch" being on by default: a run you built, played, liked, and now want to
send someone does not need rebuilding from scratch.

From a command line, the same thing:

```bash
py tools/build/bps.py apply <your-rom.nds> <their-patch.bps> <output.nds>
```

Measured 2026-10-12: **1.3 s**, and the result is byte-identical to the ROM the sender
built — the patch stores a CRC32 of the source, of the target and of itself, so it refuses
to run against the wrong ROM and refuses to produce the wrong output.

If you would rather not install anything, [Floating IPS
(Flips)](https://www.romhacking.net/utilities/1040/) and the browser-based
[RomPatcher.js](https://www.marcrobledo.com/RomPatcher.js/) both read BPS. Those are the
usual tools and the format written here is the standard `BPS1`, but the compatibility
tested in this repository is with the applier above.

There is also a GUI:

```bash
py tools/gui/modpack_maker.py
```

Six tabs — Presets, Characters, Game, Items & Chao, Randomizer, Patches — over the same feature
registry the CLI uses. It reads your ROM to show current values (with decoded in-game item icons)
and writes an ordinary profile. Set `SONIC_CHRONICLES_ROM` to pre-fill the ROM picker.

### Profiles

A mod is a JSON file. Features expand into primitive edits, so there is exactly one
apply-and-verify path:

```json
{
  "name": "My Mod",
  "features": {
    "level_cap": { "cap": 50 },
    "randomize_encounters": { "seed": 1, "mode": "transplant" }
  }
}
```

`extends` inherits from another profile. Explicit `edits` override features, so you can
build on a feature and then hand-correct one cell. Two features writing the same cell
different values is refused rather than resolved — one would silently win, and which one
would depend on key order.

#### Sharing a run

**Every build writes its recipe next to the ROM**, as `build/<name>.json`. That file is
the thing to share: a few KB of JSON that anyone with their own copy of the game can
rebuild from, where a ROM cannot be passed around and a patch says nothing about what it
did. It is already flattened, so it does not need the preset it came from, and a seed
left blank in the GUI is written out as the concrete number that was rolled — "random"
reproduces nothing.

**Load profile…** in the Mod Pack Maker reads one back in, so a run someone sends you can
be opened, inspected, tweaked and rebuilt. Anything the editor has no field for is carried
through untouched rather than dropped, so a loaded mod never comes back smaller than it
went out.

#### Seeds

The Randomizer tab has **one seed** driving all nine randomizers, because one run wants
one number. Leave it blank for a random one. The profile format still accepts a seed per
feature if you want to hand-write one that deals the halves differently.

---

## How it is put together

```
tools/recon/    format readers      nds_rom, gff4, herf, twoda, lz77, disasm, callgraph
tools/build/    writers + pipeline  rom_build, herf_write, gff4_write, gda_write,
                                    twoda_write, tlk_write, are_write, bps,
                                    features, modbuild
tools/gui/      Tkinter front end   modpack_maker, gamedata, icons
profiles/       mods as data
research/       raw Phase 0 dumps
```

Roughly 9,700 lines of Python and 4,800 lines of documentation.

Two rules hold the shape:

- **No reverse-engineering logic in the GUI.** It discovers features from the registry
  and shells out to the same builder the CLI uses.
- **Every stage verifies itself.** A no-op rebuild must be byte-identical before any edit
  is applied; each edit is read back; the archive is revalidated; a generated patch is
  applied to the source and compared. A build that cannot prove itself aborts instead of
  writing a ROM.

### The build pipeline

Validate → expand features into edits → apply → rebuild the archive → rebuild the ROM →
verify → emit a BPS patch.

Appending data is the interesting part, because nothing in these formats can simply grow
in place. Rows, strings and list entries are written at the **end** of the file and the
pointers repointed, so nothing already present moves and every existing offset stays
valid. The old bytes become dead space.

---

## Documentation

This is a research project first. The write-ups are the point, and they distinguish
confirmed facts from hypotheses throughout.

| file | contents |
|---|---|
| [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md) | Dated entries: what was investigated, what was found, the evidence, confidence, and what stayed uncertain. Includes the wrong turns and why they were wrong. |
| [KNOWN_FORMATS.md](KNOWN_FORMATS.md) | File formats — HERF, GFF4, GDA, TLK, NCGR/NCLR, `.gui`, `.are`, `.plo`, the NDS header |
| [KNOWN_IDS.md](KNOWN_IDS.md) | Tables and id spaces — creatures, items, Chao, moves, abilities, stats |
| [KNOWN_FUNCTIONS.md](KNOWN_FUNCTIONS.md) / [KNOWN_MEMORY.md](KNOWN_MEMORY.md) | ARM9 findings |
| [RESEARCH.md](RESEARCH.md) | External prior art, surveyed before any of our own work |
| [ROADMAP.md](ROADMAP.md) | Current status, open projects, hard limits found |

### A few things discovered here

- **POW and GRT, the game's two hidden stats, are damage dealt and damage reduction.**
  Neither is explained anywhere in the game's 18,845 strings — only Attack and Speed are.
  Confirmed by probe ROMs: POW +150 pushed hits past 200 damage while accuracy was
  unchanged; GRT +150 cut incoming damage to 1.
- **POW move damage is a percentage of a basic attack**, in half-percent units. `column x
  2` matches the game's own tier text for 110 of 110 moves.
- **HP is stored twice** in `creatures.GDA`, and writing one column without the other
  gives enemies an inflated maximum they never fill.
- **A chest's loot is three floats**, and the randomizer that writes them is confirmed in
  play. Each of the 53 chests is a placeable in its area
  Each of the 53 chests is a placeable in its area file carrying three `float32`
  parameters, which are `Items.GDA` ids with -1 for an empty slot. A whole day was spent
  proving chest contents were in ARM9 before noticing
  that the triple dismissed early as a position could not be one: the 1,035 rings in the
  game share two distinct triples between them.
- **Creature rows can be appended**, letting a randomizer build genuinely new enemies
  rather than reskins.
- **A POW moveset is bound to its row block, not to the column that names its owner.**
  That column is a *participant requirement*. A build that permuted it looked like a
  clean moveset swap in the table and in play left Sonic holding all six of his own
  moves, each now demanding Rouge before he could use one.
- **A ring and a Chao egg are the same object with one field changed.** Both are
  placeables in an area file; the type field says which. So the game's 1,035 rings are
  1,035 potential Chao.

---

## The icon

`assets/icon-source.png` is hand-drawn, and `assets/icon.ico` is built from it with
**two variants in one file**: 64px and up carry the whole drawing, while 48px and below
carry a crop centred on the head. Windows picks a different size for the titlebar, the
taskbar and Alt-Tab, and lettering that reads fine at 256 is mush at 16 — which is what
the format's multiple images are for.

To change it: redraw at 256x256, drop it in as `assets/icon-source.png`, and rebuild the
`.ico`. The loader prefers `icon.ico` and falls back to `icon.png`, and a missing or
unreadable icon falls back to the Tk default rather than stopping the app.

## Credits

See [CREDITS.md](CREDITS.md). In short: no third-party code is used here, but the
**xoreos** project's reverse engineering of BioWare's Aurora formats is what made it
possible to know where to look.

## Licence

MIT — see [LICENSE](LICENSE). That covers the tooling and documentation here, and nothing
else.

## Legal

Not affiliated with SEGA or BioWare. Sonic Chronicles: The Dark Brotherhood is their
property. This project contains no game assets, ships no ROM, and requires you to supply
your own legally obtained copy. Distribute mods as `.bps` patches, which are useless
without the player's own ROM — never as built ROMs.
