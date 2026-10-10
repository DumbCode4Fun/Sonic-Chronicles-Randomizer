# Sonic Chronicles Mod Builder

A reverse-engineering project and modding toolkit for **Sonic Chronicles: The Dark
Brotherhood** (Nintendo DS, BioWare, 2008) — including, as far as I can establish, the
first randomizer for the game.

Everything here is written from scratch in pure Python against the ROM's own data. There
is no game data in this repository and never will be: you supply your own legally
obtained dump, and the tools read it, build a modified copy beside it, and never write to
the original.

> **Status.** The data layer is thoroughly mapped and most features are confirmed in
> play. Three things remain locked inside the ARM9 executable — chest contents,
> party-relative enemy scaling, and recruitment order — and are documented as such rather
> than guessed at. Features carry an honest badge: *confirmed in game* or
> *build-verified only*.

![The Mod Pack Maker's Randomizer tab](assets/mod-pack-maker.png)

*The Randomizer tab. Every feature carries the badge it earned — these are all
`build-verified only`, meaning the build checks out but nobody has played them yet.*

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
| `randomize_encounters` | Reskins every enemy species, or (in `transplant` mode) appends real new creatures carrying the donor's model, moves and innate abilities at the local power level |
| `randomize_placements` | Moves enemy groups between spawn points, banded by difficulty so an area stays fair |
| `randomize_items` | Re-rolls what each piece of gear does, and rewrites its description to match |
| `randomize_chao` | Re-rolls Chao stat bonuses and gives the hardcoded-effect Chao stats they never had |
| `randomize_shops` | Redeals shop stock; prices stay with the slot so early finds stay affordable |
| `randomize_pickups` | Redeals the 39 item pickups placed around the world — the Health Leaves and Spiked Slippers, not the 1,035 rings |
| `randomize_drops` | Redeals the weighted drop tables, rates untouched |
| `randomize_rewards` | Redeals quest and event rewards, with optional XP/gold scaling |

<table>
<tr>
<td width="50%"><img src="assets/randomized-placement.png" alt="An enemy displaced into the opening zone"></td>
<td width="50%"><img src="assets/randomized-encounter.png" alt="The opening encounter, reskinned"></td>
</tr>
<tr>
<td><em><code>randomize_placements</code> — an enemy group moved into the opening zone,
banded so it still belongs there.</em></td>
<td><em><code>randomize_encounters</code> — the tutorial fight, same scripted slot, a
different creature in it.</em></td>
</tr>
</table>

Safety is built in rather than hoped for: quest items and key items never move, bosses and
scripted spawn points are left alone, and difficulty banding keeps a level-20 enemy out of
the first zone. Those rules were not guesses — each one exists because a playtest broke
something. See [REVERSE_ENGINEERING_LOG.md](REVERSE_ENGINEERING_LOG.md).

### Everything else

`level_cap`, `xp_curve`, `pp_curve`, `stat_curve`, `enemy_scaling`, `movement_slots`,
`pow_move`, `custom_item`, `custom_chao`, `store_stock`.

Highlights: raise the cap past 30, give any character any movement ability in any of their
three slots, convert multi-character POW moves to solo, build custom gear and Chao, and
retune the enemy difficulty curve.

---

## Quick start

Requires **Python 3.8+**. No dependencies for anything in the normal path.
(`capstone` is optional and only used by the ARM9 disassembler.)

```bash
py tools/build/modbuild.py <your-rom.nds> profiles/full_randomizer.json
```

That writes `build/full_randomizer.nds` plus a `.bps` patch and a JSON report. Pass
`--no-patch` to skip patch generation, which is the slow stage.

There is also a GUI:

```bash
py tools/gui/modpack_maker.py
```

Four tabs — Characters, Game, Items & Chao, Randomizer — over the same feature registry
the CLI uses. It reads your ROM to show current values (with decoded in-game item icons)
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
build on a feature and then hand-correct one cell.

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
- **A chest carries no loot.** Its contents are not in the area file, not in the drop
  tables, not in the plot files, and not in any GDA. They are in ARM9.
- **Creature rows can be appended**, letting a randomizer build genuinely new enemies
  rather than reskins.

---

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
