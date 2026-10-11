"""
Named, parameterised mod features — roadmap PRODUCTIZE step.

A profile may carry a `features` block alongside (or instead of) raw `edits`:

    {
      "name": "My Mod",
      "features": {
        "level_cap":      {"cap": 99},
        "pp_curve":       {"character": "Shadow", "bonus": 3},
        "enemy_scaling":  {"hp_per_level": 0.05, "pow_per_level": 0.035},
        "custom_item":    [{"item": 78, "name": "Chaos Driver",
                            "effects": {"POW": 8, "SPD": 6, "element": "lightning"}}]
      }
    }

Each feature expands to the same `edits` the hand-written profiles use, so there is
exactly one apply/verify path and features cannot drift from it.

**Scope.** Only mechanisms whose behaviour has been established are exposed, per
CLAUDE.md. Every feature below carries a `confirmed` marker:

    "game"  - observed working in DeSmuME
    "build" - mechanism established and the build verifies statically, but the
              specific effect has not yet been seen in play

Character swapping is deliberately **not** a feature. It couples at least eleven
tables (creature identity, portrait prefix + art payloads, palette, appearance,
team/combat portraits, combo ownership, boss-specific move rows, progression,
movement level, TLK names vs dialogue, and squad appearance), and that list grew
five entries in a single session. It stays a hand-built profile until the coupling
map stops growing.
"""
import sys

REGISTRY = {}
CONFIRMED = {}


def feature(name, confirmed):
    def deco(fn):
        REGISTRY[name] = fn
        CONFIRMED[name] = confirmed
        return fn
    return deco


# Stat ids as used by .ITM effect rows (SData1). Read off the shipped items.
STATS = {'HEAL': 0, 'SPD': 21, 'ATK': 22, 'DEF': 23, 'MAXHP': 24, 'POW': 25,
         'GRT': 26, 'LCK': 27, 'HEALPP': 28, 'MAXPP': 36}
# Element stat ids, for items.
ITEM_ELEMENTS = {'fire': 107, 'water': 108, 'earth': 109,
                 'wind': 110, 'lightning': 111, 'ice': 112}
#: Elemental RESISTANCE stat ids, read off the five shield Chao - Korus (fire),
#: Perty (water), Jirna (earth), Seeri (wind), Knickt (lightning), each granting 50
#: alongside GRT +1 and each described as "creates a shield of <element> to protect
#: against damage". The resistance block sits exactly 32 below the offence block
#: (`ITEM_ELEMENTS`) and in the same element order, which is what makes the mapping
#: trustworthy: two independent orderings agree on all five.
#:
#: **Ice (id 80) is the prediction and is deliberately not offered.** No shipped item
#: grants ice resistance, so there is no ice-shield Chao and nothing in the game
#: exercises that id. Same rule as `MOVE_ELEMENTS` omitting water and ice: a value we
#: have reasoned our way to is not a value we know.
ITEM_RESISTS = {'fire': 75, 'water': 76, 'earth': 77, 'wind': 78, 'lightning': 79}

# Element BITMASK, for combo.GDA moves. A different encoding from items.
# Only the four observed in vanilla are offered: water and ice are presumed to be
# bits 18 and 22 but appear nowhere, so they are not exposed as if they were known.
MOVE_ELEMENTS = {'fire': 131072, 'earth': 524288,
                 'wind': 1048576, 'electricity': 2097152}

# combo.GDA column indices
C_PARTICIPANTS, C_OWNER, C_PARTNERS, C_COST = 1, 2, (3, 4, 5), 11
C_DMG = (12, 13, 14)
#: Targeting is three mutually exclusive modes, not a flag and a modifier. Columns 48
#: and 52 are never both set: 113 moves have neither (single target), 22 have 48 alone
#: and 20 have 52 alone.
#:
#:   * **48 - splash.** A primary target takes full damage and the rest take less. This
#:     is the one the transplanted Hellfire demonstrated in play: 19 to Sonic and 10 to
#:     Amy beside him (2026-10-10), and Hellfire is 48=1.
#:   * **52 - whole team.** Every one of the 20 says so in its own description: "lashing
#:     them all", "the entire opposing team", "hits multiple targets", "the opposing
#:     team". Every single-target move's description says "a foe" or "the target".
#:
#: `C_ELEMFLAG` was the old name for 52, from before the descriptions were read. It is
#: kept as an alias only so nothing silently changes meaning; prefer `C_WHOLE_TEAM`.
#: combo.GDA 34/35: the move's name and description strrefs.
C_NAME, C_DESC = 34, 35
C_CANTMISS, C_BLAST, C_ELEMENT = 47, 48, 51
C_SPLASH, C_WHOLE_TEAM = 48, 52
C_ELEMFLAG = C_WHOLE_TEAM
#: combo.GDA 55: set on 23 moves the game treats as support rather than attack - Heal,
#: Cure, Revive, Scan, Tinker, Taunt, Cloak, Distract and so on. It agrees with "deals no
#: damage at any tier" on 153 of the 155 rows. The two exceptions are what stop this being
#: a definition: Froggy Poison is 55=1 and does 25/38/50, and Chaos Rift is 55=0 and does
#: nothing. So it is a designer's classification, closely but not perfectly correlated
#: with damage, and what the engine does with it is not established.
C_SUPPORT = 55
#: combo.GDA 27/28/29: the status effect the move inflicts, per damage tier, as a
#: spells.GDA row — Stun, Sluggish, Vulnerable, Weakened, Distracted.
C_STATUS = 27
C_STATUS_TIERS = (27, 28, 29)
#: Status effects that have a spells.GDA entry per tier, read straight off the table.
#: Stun is the odd one out: only `Spell_Stun.spl` exists, so all three tiers share it,
#: which is exactly how Metal Storm and Quake Punch are authored.
MOVE_STATUSES = {
    'cursed':     (35, 66, 71),
    'distracted': (36, 67, 72),
    'weakened':   (37, 68, 73),
    'vulnerable': (38, 69, 74),
    'sluggish':   (39, 70, 75),
    'stun':       (41, 41, 41),
    'none':       (-1, -1, -1),
}
#: Giving an element to a move that shipped without one is **not reliably safe**, and
#: nothing in `combo.GDA` predicts which moves tolerate it.
#:
#: The evidence, all from play:
#:   * Focus Field + wind  -> hard crash, with Vulnerable *and* again with Sluggish.
#:   * Metal Storm + earth -> works.
#:   * Atomic Strike       -> works, but it ships with electricity; we never added it.
#:
#: The first theory was that the (element, status) *pairing* had to exist in vanilla.
#: The Sluggish probe was built specifically to test that — wind + Sluggish is exactly
#: how Triple Tornado is authored — and it crashed anyway, so the theory is dead.
#:
#: Nor is there a companion column: across all 155 moves the only field every vanilla
#: wind move shares and Focus Field lacks is the element itself. Atomic Strike is
#: structurally near-identical to Focus Field (2 participants, col44 = 3, the same
#: trailing -1 slots) and works, differing only in that its element is authored rather
#: than added. Whatever an elemental move needs lives outside `combo.GDA` and has not
#: been found; VFX.GDA is a flat 467-row effect registry with no per-move element key.
#:
#: So the rule is drawn around what is observed, not around a mechanism: an element may
#: be changed on a move that already has one, and adding one to a move that lacks one is
#: refused. Metal Storm is the single known-good exception and is not generalisable.
ELEMENTLESS_ADD_IS_UNSAFE = True
# creatures.GDA
CR_NAME, CR_DEF, CR_HP, CR_POW, CR_LEVEL, CR_PLAYERID = 1, 6, 7, 8, 33, 35
#: grit — damage *reduction*, confirmed in play 2026-10-10. Scale with care; see
#: the note on `enemy_scaling` about why this is the lever that ruins a fight.
CR_GRT = 9
#: HP is stored TWICE. Column 2 is what a creature spawns with; column 7 ('health') is
#: the maximum its HP bar is drawn against. They are equal in all 128 vanilla rows, and
#: no other stat is duplicated this way. Writing only one of them desynchronises the
#: pair: `enemy_scaling` originally wrote col 7 alone, which raised every enemy's ceiling
#: while leaving it spawning with vanilla HP (observed in game 2026-10-08 — Imperator Ix
#: spawned at 350 and then healed past it to 377 against a 525 ceiling). Always write
#: both.
CR_HP_SPAWN = 2
# Adv_*.GDA
ADV_ID, ADV_LEVEL, ADV_XP, ADV_FATIGUE, ADV_MOVE1 = 0, 1, 2, 10, 12
# squads.GDA
SQ_APPEARANCE, SQ_MEMBERS = 4, (5, 6, 7, 8)


def _gda(b, name):
    from gff4 import GFF4, read_gda
    cols, rows = read_gda(GFF4(b.herf.read(b.resource(name))))
    return cols, rows, sorted(rows[0].keys())


def _text(b, ref):
    """A TLK string by strref, or '' - used only for name matching, never for output."""
    if not isinstance(ref, int) or ref < 0:
        return ''
    try:
        return b.tlk.get_string(b.tlk.index_of_id(ref)) or ''
    except Exception:
        return ''


def _need(params, *keys):
    missing = [k for k in keys if k not in params]
    if missing:
        raise ValueError('missing required parameter(s): %s' % ', '.join(missing))


# --------------------------------------------------------------------------
# progression
# --------------------------------------------------------------------------

@feature('level_cap', 'game')
def level_cap(params, b):
    """Extend every Adv_<character> progression table to a new maximum level.

    Each added level repeats the final level-29->30 delta per column, so the
    curve continues plausibly rather than flatlining. XP thresholds are then
    flattened to a constant step so the new cap is reachable from any save.
    """
    _need(params, 'cap')
    cap = int(params['cap'])
    xp_per_level = int(params.get('xp_per_level', 20000))
    if cap < 2:
        raise ValueError('cap must be at least 2')
    edits = []
    for name in sorted(n for n in b.herf.names.values()
                       if n.startswith('Adv_') and n.lower().endswith('.gda')
                       and 'VFXTester' not in n):
        cols, rows, K = _gda(b, name)
        if cap <= len(rows):
            continue
        ncols = len(cols)
        last = [rows[-1][K[i]] for i in range(ncols)]
        prev = [rows[-2][K[i]] for i in range(ncols)]
        delta = [(last[i] - prev[i]) if isinstance(last[i], int)
                 and isinstance(prev[i], int) else 0 for i in range(ncols)]
        cur = list(last)
        for lvl in range(len(rows) + 1, cap + 1):
            cur = [cur[i] + delta[i] if isinstance(cur[i], int) else cur[i]
                   for i in range(ncols)]
            cur[ADV_ID] = lvl - 1
            cur[ADV_LEVEL] = lvl
            cur[ADV_XP] = (lvl - 1) * xp_per_level
            edits.append({'op': 'gda_add_row', 'resource': name, 'values': list(cur)})
        for r in range(cap):
            edits.append({'op': 'gda_cell', 'resource': name, 'row': r,
                          'column': ADV_XP, 'value': r * xp_per_level})
    return edits


@feature('pp_curve', 'build')
def pp_curve(params, b):
    """Raise a character's PP pool.

    **PP is not simply the `fatigue` column.** The engine takes a base from
    `creatures.GDA` columns 11/12 and then adds the per-level *increments* implied
    by `fatigue` in Adv_<character>.GDA. Vanilla Shadow is base 7 with +3 of
    increments by level 8, giving 10.

    Consequently a flat bonus added to every level of the Adv table changes nothing
    at all — every increment stays identical. (This feature did exactly that
    originally; the level-up screen reported "PP +0" and the pool never moved.)

    So `base` edits the creature row, which is what actually shifts the pool.
    `per_level` additionally steepens the curve by granting that many extra points
    per level, which does change the increments.
    """
    out = []
    for spec in (params if isinstance(params, list) else [params]):
        _need(spec, 'character')
        adv = 'Adv_%s' % spec['character']
        if 'base' not in spec and 'per_level' not in spec:
            raise ValueError('pp_curve needs base and/or per_level')

        if 'base' in spec:
            cols, rows, K = _gda(b, 'creatures.GDA')
            if 'creature' in spec:
                hits = [int(spec['creature'])]
            else:
                # CAUTION: features expand against the ORIGINAL ROM, before any
                # hand-written edits apply. Inferring the creature row from the
                # progression table it currently names is therefore wrong in any
                # profile that reassigns tables (e.g. a character swap): the lookup
                # sees the pre-swap owner. Pass `creature` explicitly in that case.
                hits = [i for i, r in enumerate(rows) if r[K[34]] == adv]
                if not hits:
                    raise ValueError('no creature row uses %s; pass `creature` '
                                     'explicitly if a swap reassigns it' % adv)
            for i in hits:
                for col in (11, 12):          # fatigue / maxfatigue
                    if rows[i][K[col]] != int(spec['base']):
                        out.append({'op': 'gda_cell', 'resource': 'creatures.GDA',
                                    'row': i, 'column': col,
                                    'value': int(spec['base'])})
        if 'per_level' in spec:
            name = adv + '.GDA'
            cols, rows, K = _gda(b, name)
            extra = float(spec['per_level'])
            baseline = rows[0][K[ADV_FATIGUE]]
            for i in range(len(rows)):
                want = int(round(baseline + (rows[i][K[ADV_FATIGUE]] - baseline)
                                 + extra * i))
                if want != rows[i][K[ADV_FATIGUE]]:
                    out.append({'op': 'gda_cell', 'resource': name, 'row': i,
                                'column': ADV_FATIGUE, 'value': want})
    return out


#: Adv_<character>.GDA stat columns. `power` is damage and `grit` is armor; both
#: are computed by the engine but never shown in the UI, so their effect is only
#: observable through play, not through a stat screen.
ADV_STATS = {'speed': 3, 'attack': 4, 'defense': 5, 'hp': 6,
             'power': 7, 'grit': 8, 'luck': 9, 'fatigue': 10}


@feature('stat_curve', 'build')
def stat_curve(params, b):
    """Scale or offset one stat across a character's whole progression table.

    Takes `multiplier` (applied to every level, rounded) and/or `bonus` (flat).
    A multiplier keeps the curve's shape, so the character stays proportionally
    stronger at every level rather than being front-loaded.

    **It does nothing to a save already in progress.** A character's current stats live
    in the save file, not in this table; the table is what a *level-up* reads. So a
    profile built to make a playtest party unkillable leaves an existing party exactly
    as killable as it was, until somebody gains a level (confirmed in play 2026-10-10,
    by it visibly not working). For an existing save use `tools/build/save_edit.py
    --godmode`, which finds the party's stat blocks and writes them directly.
    """
    out = []
    for spec in (params if isinstance(params, list) else [params]):
        _need(spec, 'character', 'stat')
        stat = str(spec['stat']).lower()
        if stat not in ADV_STATS:
            raise ValueError('unknown stat %r; known: %s' % (spec['stat'], sorted(ADV_STATS)))
        if 'multiplier' not in spec and 'bonus' not in spec:
            raise ValueError('stat_curve needs a multiplier and/or a bonus')
        col = ADV_STATS[stat]
        mult = float(spec.get('multiplier', 1.0))
        bonus = int(spec.get('bonus', 0))
        name = 'Adv_%s.GDA' % spec['character']
        cols, rows, K = _gda(b, name)
        for i in range(len(rows)):
            old = rows[i][K[col]]
            if not isinstance(old, int):
                continue
            new = int(round(old * mult)) + bonus
            if new != old:
                out.append({'op': 'gda_cell', 'resource': name, 'row': i,
                            'column': col, 'value': new})
    return out


@feature('xp_curve', 'game')
def xp_curve(params, b):
    """Replace one character's XP thresholds, by copying another's or by scaling.

    Characters who join mid-game carry XP curves that assume a head start. Shadow
    needs 44% more XP than Sonic to reach level 8 (and 132% more to reach level 2),
    because he is balanced around arriving already levelled. Playing such a
    character from level 1 therefore means grinding a curve built for someone who
    skipped the early game — the same class of trap as their PP costs.

    `copy_from` takes another character's thresholds verbatim; `multiplier` scales
    the existing ones.
    """
    out = []
    for spec in (params if isinstance(params, list) else [params]):
        _need(spec, 'character')
        name = 'Adv_%s.GDA' % spec['character']
        cols, rows, K = _gda(b, name)
        if 'copy_from' in spec:
            src, srows, SK = _gda(b, 'Adv_%s.GDA' % spec['copy_from'])
            want = [srows[i][SK[ADV_XP]] if i < len(srows) else None
                    for i in range(len(rows))]
        elif 'multiplier' in spec:
            m = float(spec['multiplier'])
            want = [int(round(rows[i][K[ADV_XP]] * m)) for i in range(len(rows))]
        else:
            raise ValueError('xp_curve needs copy_from or multiplier')
        for i, v in enumerate(want):
            if v is None or v == rows[i][K[ADV_XP]]:
                continue
            out.append({'op': 'gda_cell', 'resource': name, 'row': i,
                        'column': ADV_XP, 'value': int(v)})
    return out


#: movement.GDA ids, with the maximum level each supports.
MOVEMENT = {'dash': (0, 3), 'smash': (1, 3), 'fly': (2, 3), 'jump': (3, 1),
            'climb': (4, 1), 'invulnerable': (5, 3), 'stealth': (6, 1),
            'teleport': (7, 1), 'wriggle': (8, 1), 'detect': (9, 1),
            'ksmash': (10, 1)}
#: creatures.GDA movement slot columns, and the Adv_* column holding each slot's LEVEL.
#: There are THREE slots, not two: Knuckles fills all of them (Climb/Smash/Fly) while
#: Sonic fills one and Eggman none. Columns 12/13/14 of the progression table carry the
#: matching levels, and read 0 for any slot the character does not use.
SLOT_COL = {1: 19, 2: 20, 3: 21}
SLOT_LEVEL_COL = {1: 12, 2: 13, 3: 14}


@feature('movement_slots', 'build')
def movement_slots(params, b):
    """Give any character any movement ability, in any of their three slots.

    A slot holds the ability; its **level** lives in the character's progression
    table — column 12 for slot 1, column 13 for slot 2. Setting the slot alone does
    nothing, because an ability at level 0 is never granted (which is exactly why
    vanilla Sonic's empty slots 2 and 3 pair with columns 13/14 of 0 at every level).
    This writes both.

    `level` is clamped to the ability's own maximum from movement.GDA: Dash, Smash,
    Fly and Invulnerable go to 3; everything else is level 1 only.

    Pass `creature` explicitly when a swap reassigns progression tables — features
    expand against the unmodified ROM.

    Supersedes the old `movement_ability`, which could only touch slot 1 and could
    not choose which ability went there.
    """
    out = []
    for spec in (params if isinstance(params, list) else [params]):
        _need(spec, 'character', 'slot', 'ability')
        slot = int(spec['slot'])
        if slot not in SLOT_COL:
            raise ValueError('slot must be 1, 2 or 3, got %r' % spec['slot'])
        key = str(spec['ability']).lower()
        if key not in MOVEMENT:
            raise ValueError('unknown ability %r; known: %s'
                             % (spec['ability'], ', '.join(sorted(MOVEMENT))))
        ability_id, max_level = MOVEMENT[key]
        want = int(spec.get('level', max_level))
        if want > max_level:
            raise ValueError('%s caps at level %d (movement.GDA maxlevel), asked for %d'
                             % (key, max_level, want))
        if want < 1:
            raise ValueError('level must be at least 1')
        from_level = int(spec.get('from_level', 1))

        # 1. the slot itself, on the creature row
        cols, rows, K = _gda(b, 'creatures.GDA')
        if 'creature' in spec:
            crow = int(spec['creature'])
        else:
            adv = 'Adv_%s' % spec['character']
            hits = [i for i, r in enumerate(rows) if r[K[34]] == adv]
            if not hits:
                raise ValueError('no creature row uses %s; pass `creature` explicitly' % adv)
            crow = hits[0]
        if rows[crow][K[SLOT_COL[slot]]] != ability_id:
            out.append({'op': 'gda_cell', 'resource': 'creatures.GDA', 'row': crow,
                        'column': SLOT_COL[slot], 'value': ability_id})

        # 2. the level it reaches, on the progression table
        name = 'Adv_%s.GDA' % spec['character']
        acols, arows, AK = _gda(b, name)
        lcol = SLOT_LEVEL_COL[slot]
        for i in range(len(arows)):
            lvl = arows[i][AK[ADV_LEVEL]]
            target = want if lvl >= from_level else 0
            if arows[i][AK[lcol]] != target:
                out.append({'op': 'gda_cell', 'resource': name, 'row': i,
                            'column': lcol, 'value': target})
    return out


# --------------------------------------------------------------------------
# difficulty
# --------------------------------------------------------------------------

@feature('enemy_scaling', 'build')
def enemy_scaling(params, b):
    """Static difficulty curve keyed to each enemy's own level (1-20).

    **Which lever to pull matters more than how hard.** Now that the hidden stats are
    confirmed (POW is damage dealt, GRT is damage reduction), the four rates are not
    interchangeable:

    * **`hp_per_level` is the safe lever.** A tougher enemy takes more hits, and every
      hit still shows the number the player earned by levelling. Scale this first.
    * **`pow_per_level` is felt directly** — enemies hit harder. Moderate values only.
    * **`grt_per_level` suppresses the player's damage numbers**, which is the one thing
      that makes levelling up feel pointless: reaching level 50 and still reading "50"
      is worse than a long fight. Enemy grit is also a *small* number doing *large*
      work — vanilla runs 1 at level 1 to 50 at level 20, and a probe at GRT 150 cut
      incoming hits to 1 damage — so a percentage here goes further than it looks.
      **Defaults to 0.** If you want it, 0.01-0.02 is plenty.
    * **`def_per_level` probably means evasion**, by symmetry with Attack, which the
      game defines as hit chance. Scaling it makes the player *miss* more, which reads
      as the game cheating rather than as difficulty. **Defaults to 0.**

    HP is written to **both** of its columns — see `CR_HP_SPAWN`. Scaling only
    `health` (col 7) raises the ceiling without raising what enemies spawn with, which
    is how this shipped until 2026-10-08 and is worth re-checking if HP ever looks
    wrong again. POW and DEF have no second column and were always correct.

    This is NOT reactive party-average scaling: that needs the party level at
    runtime, i.e. an ARM9 patch rather than a data edit. Rows with 9999 HP are
    skipped as scripted/invulnerable, and party members are never touched.
    """
    # key: the columns one rate drives, read from the first of them
    rates = {(CR_HP, CR_HP_SPAWN): float(params.get('hp_per_level', 0.0)),
             (CR_POW,): float(params.get('pow_per_level', 0.0)),
             (CR_GRT,): float(params.get('grt_per_level', 0.0)),
             (CR_DEF,): float(params.get('def_per_level', 0.0))}
    cols, rows, K = _gda(b, 'creatures.GDA')
    edits = []
    for i, r in enumerate(rows):
        if r[K[CR_PLAYERID]] != -1:
            continue
        lv = r[K[CR_LEVEL]]
        if not isinstance(lv, int) or lv < 1:
            continue
        # Skip the WHOLE creature when any stat sits at the 9999 sentinel, not just
        # that one column. These are scripted encounters the player is meant to lose;
        # guarding per-column left the unwinnable Imperator Ix at 9999 HP while still
        # scaling his damage from 3000 to 5100.
        if any(isinstance(r[K[c]], int) and r[K[c]] >= 9999
               for c in (CR_HP, CR_POW, CR_DEF)):
            continue
        # Grit uses a much smaller range than the others — the highest real enemy value
        # is 75 — so 999 is a sentinel here rather than a big number, and scaling it
        # would be meaningless.
        # Skipped per creature, not globally: mutating the shared `rates` here would
        # silently disable grit for every creature processed after the first sentinel.
        grit_sentinel = isinstance(r[K[CR_GRT]], int) and r[K[CR_GRT]] >= 999

        for group, rate in rates.items():
            if not rate or (group == (CR_GRT,) and grit_sentinel):
                continue
            old = r[K[group[0]]]
            if not isinstance(old, int) or old <= 0:
                continue
            new = int(round(old * (1 + rate * lv)))
            if new == old:
                continue
            for col in group:
                edits.append({'op': 'gda_cell', 'resource': 'creatures.GDA',
                              'row': i, 'column': col, 'value': new})
    return edits



# --------------------------------------------------------------------------
# randomizer
# --------------------------------------------------------------------------

#: creatures.GDA columns that carry a creature's *identity* rather than its power.
#: Moving these and nothing else is what makes a Gizoid turn up in an early zone while
#: still fighting like the Wild Boar whose slot it took. Stats, moves and level stay put.
CR_ID_INTS = (1, 14)                     # name strref, appearance id
CR_ID_STRINGS = (16, 17, 18)             # battle portrait, large portrait prefix, palette
CR_APPEARANCE = 14
#: Column 32 is **deliberately not copied.** It looked like a cosmetic organic/robot tag,
#: but it is a creature *type* with mechanical weight: 0 beast, 1 insect (exactly the
#: wasps, the millipede and the worm), 2 robot. Copying it moved Marauder Scout from
#: beast to insect, and the first playtest reported that enemy using its own Stasis
#: Grenade with a block pattern that did not match the move. Type very likely drives
#: elemental weakness and plausibly that pattern, so a reskin leaves it alone: looks
#: change, mechanics do not.
#:
#: Named `CR_TYPE` until 2026-10-10, which was wrong: hashing the column names
#: (`crc32` of the lowercased UTF-16LE name) against the table's own header shows
#: **column 37** is `class`, and it is -1 for 111 of 128 rows - a *character* class that
#: only the playable cast has. Column 32's hash is shared with a column of
#: `appearances.GDA` and its real name is not recovered. The behaviour here is unchanged
#: and still right; only the label was.
CR_TYPE = 32
#: squads.GDA: the overworld model you walk into, same id space as creatures column 14
SQ_APPEARANCE_COL = 4

#: Creatures never remapped. There is **no boss flag in the data** - `type` only separates
#: organic from robot, `class` is -1 for 111 of 114 enemies, and the Imperator Ix squads
#: carry `conversation = -1` exactly like the random trash does. Usage count is the only
#: signal (Ix appears in 3 squads, Nocturnus Velite in 18) and it is too fuzzy to trust,
#: so the list is curated by name.
PROTECTED_NAMES = (
    'imperator ix', 'gizoid guardian', 'commander syrax', 'thelxe', 'power pylon',
    'super sonic', 'procurator shade', 'dominated voxai', 'voxai conspirator',
)
#: The generic NPC statline. 37 rows share level 1 / 100 HP / 11 POW / 18 DEF - shop
#: keepers, GUN soldiers, Vector, the Boy and Dad. They stand in scripted scenes rather
#: than fights, so remapping them would be pointless and risky.
NPC_STATLINE = (1, 100, 11, 18)          # level, hp, power, defense


#: creatures.GDA columns that make a creature's *power*, as opposed to its identity.
#: A transplant takes these from the slot it lands in, so the donor arrives at the local
#: level, and takes everything else from the donor.
CR_STAT_COLS = (2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 33)
CR_MOVE_SLOTS = (22, 23, 24, 25, 26, 27)
#: Columns 51 and 52 are two **innate ability slots** holding ability item ids — Evading,
#: Phase, Self Repair, Immunity, Lock On!, the elemental Shields. They ride along with
#: the donor, confirmed in game 2026-10-09: a transplanted Gizoid regenerated and
#: countered at level 2 with its POW moves blanked, which is what makes a transplant feel
#: like the creature rather than a repaint.
CR_ABILITY_SLOTS = (51, 52)


def _typical_pow(rows, K):
    """level -> the POW a vanilla enemy has at that level. Derived, not invented.

    This is the local power norm, and it is what a transplanted creature should hit
    with: the donor's move *variety* at the slot's own strength. It runs 11 at levels
    1-3 to 72 at level 20, with a +-2 level window to smooth thin bands.

    **Why the median over all enemies and not over move-using ones.** The first version
    of this floor used only enemies that have a POW move, reasoning that those are the
    ones built to swing. That was wrong in exactly the bands that matter. Levels 1-2 have
    almost no move-users (2 of 41), so the window dragged in level 3-5 values and put the
    floor at 18 for a level-2 slot. In play that turned a 2-damage hit into **34 damage
    to a level-2 Amy** - from one end of wrong to the other.

    Two reports from the same creature in the same slot, a Gizoid Centurion on a level-2
    Sentry Drone, pin the damage model down:

    | POW | move | damage |
    |---|---|---|
    | 6 | 150% | 2 |
    | 18 | 350% | 34 |

    Normalising by the multiplier gives a basic attack of 1.33 and 9.71, so
    `basic ~= 0.70 x POW - 2.86` against that target. Damage is **linear in POW with a
    subtraction**, which is why the low end is so steep: POW 6 is almost entirely eaten
    by mitigation, and tripling it multiplies the damage by seven. The median over all
    enemies puts a level-2 slot at POW 11, which the model predicts lands the 350% move
    at about 17 and the 150% move at about 7 - a real threat at level 2 that does not
    delete a party member.
    """
    import statistics
    import collections
    by_level = collections.defaultdict(list)
    for r in rows:
        lv, pw = r[K[CR_LEVEL]], r[K[CR_POW]]
        if r[K[CR_PLAYERID]] != -1 or not isinstance(lv, int) or lv < 1:
            continue
        if isinstance(pw, int):
            by_level[lv].append(pw)
    if not by_level:
        return {}
    out = {}
    for lv in range(1, max(by_level) + 1):
        window = [p for l in range(lv - 2, lv + 3) for p in by_level.get(l, [])]
        if window:
            out[lv] = int(round(statistics.median(window)))
    return out


def _squad_shows(flat, live, app, remapped):
    """Which member, if any, the squad's overworld model is showing.

    A squad carries its own appearance id for the thing you walk into, and it is *not*
    simply its members': 19 of 163 squads show something else entirely. The first version
    of this rule asked whether the squad's appearance equalled the **first** member's, and
    that was far too strict - it fired on 82 of 144 randomized squads and left the other
    62 showing their vanilla model while the battle had changed underneath. That is the
    reported "caterpillar in the overworld, Gentleman in the fight": squad 1 shows
    `SLG_AA` and leads with a Giant Millipede whose own battle appearance is a different
    id again.

    Asking whether the appearance matches **any** member covers 144 of 163 - a mixed
    Wasp Swarm squad that shows its Swat Bot now follows the Swat Bot - and the 19 it
    still refuses are exactly the ones that should be refused. Eight of them are scene
    props: `HNPC_FOR_AA`, `HNPC_CON_AA` and `HNPC_TIM_AA` are the Forester, the
    Contractor and Timmy, quest NPCs you talk to rather than monsters you walk into, and
    the rest are Shade, Commander Syrax, the Marauder chase, Nrrgal and Imperator Ix.
    Repointing those would put a monster where a person should be standing.
    """
    for m in live:
        if app == flat[m][CR_APPEARANCE] and m in remapped:
            return m
    return None


def _transplant_edits(b, rng, rows, K, flat, donor_of, srows, SK, params):
    """Clone donors into new creature rows carrying the victim's power.

    Three tables move together:

    * **combo.GDA** gets a clone of each of the donor's moves, **unscaled**. The damage
      columns are a percentage in half-percent units: every one of the game's own tier
      descriptions agrees with `column x 2` (110 of 110 checked), so Focus Field's
      113/125/138 reads "225% / 250% / 275% of Attack damage" — a multiple of a *basic
      attack's* damage, and a basic attack is driven by **POW** (confirmed in play
      2026-10-10: POW +150 took hits past 200 damage while accuracy was untouched).
      The clone takes the victim's POW along with the rest of its stat block, so a
      transplanted move lands at the local tier on its own. Scaling the column too would
      double-count — the first draft did, and turned a 300 into 96 while believing 96 was
      HP. `damage_scale` is there to tune it deliberately.
    * Each clone's **owner** (column 2) is repointed at the new creature. That column is
      the owning creature id, and a move whose owner does not match shows as
      "Unavailable" — the same trap that broke Shadow's POW moves during the character
      swap.
    * **creatures.GDA** gets a clone of the donor with the victim's stat columns, its
      move slots pointing at the cloned combos.

    **POW gets a floor** (`pow_floor`, on by default), because the victim's stat block is
    not always a stat block that can use a move. The game hands out POW moves from about
    level 3 - 2 of the 41 enemies at levels 1-2 have one, against 13 of 13 at levels 3-5 -
    so a transplant into an early slot gives a move to a creature built never to swing
    one. Seed 1 put a Gizoid Centurion on a level-2 Sentry Drone with **POW 6**, and its
    move landed for **2 damage**: correct arithmetic, bad encounter. The floor is
    `_typical_pow`, the median POW of vanilla enemies at that level - 11 at levels 1-3
    rising to 72 at level 20. It applies only to creatures that gained a move, never
    drops POW below the victim's own, and never raises it above the donor's. `pow_scale`
    multiplies the target afterwards for taste, within the same bounds.

    Only creatures that actually appear in a squad are cloned; the rest would be dead
    rows. Both tables relocate their row array once for the whole batch.
    """
    ccols, crows, CK = _gda(b, 'combo.GDA')
    cflat = [[r[CK[j]] for j in range(len(ccols))] for r in crows]

    pow_floor = params.get('pow_floor', True)
    floor_of = _typical_pow(rows, K) if pow_floor else {}
    pow_scale = float(params.get('pow_scale', 1.0))

    used = {m for s in srows for c in (5, 6, 7, 8)
            for m in (s[SK[c]],) if isinstance(m, int) and 0 <= m < len(rows)}

    next_creature = len(rows)
    next_combo = len(crows)
    combo_specs, creature_specs, remap = [], [], {}

    for victim in sorted(v for v in donor_of if v in used):
        donor = donor_of[victim]
        new_row = next_creature
        next_creature += 1

        scale = float(params.get('damage_scale', 1.0))

        slots = []
        for col in CR_MOVE_SLOTS:
            src = flat[donor][col]
            if not isinstance(src, int) or not (0 <= src < len(crows)):
                slots.append(-1)
                continue
            ov = {C_OWNER: new_row}
            if scale != 1.0:
                for dcol in C_DMG:
                    dmg = cflat[src][dcol]
                    if isinstance(dmg, int) and dmg > 0:
                        ov[dcol] = max(1, int(round(dmg * scale)))
            combo_specs.append((src, ov))
            slots.append(next_combo)
            next_combo += 1

        ov = {0: new_row}
        for col in CR_STAT_COLS:
            ov[col] = flat[victim][col]
        for col, value in zip(CR_MOVE_SLOTS, slots):
            ov[col] = value

        # A creature that has just been handed POW moves needs the POW to swing them.
        # Only POW moves it actually *gained* count, and the raise is bounded twice: it
        # never goes below the victim's own POW, and never above the donor's, so a
        # transplant stays between the creature it replaced and the creature it imitates.
        gained = sum(1 for v in slots if v != -1)
        vpow, dpow = flat[victim][CR_POW], flat[donor][CR_POW]
        if gained and isinstance(vpow, int) and isinstance(dpow, int):
            target = max(vpow, floor_of.get(flat[victim][CR_LEVEL], 0))
            if pow_scale != 1.0:
                target = int(round(target * pow_scale))
            ov[CR_POW] = max(vpow, min(target, max(vpow, dpow)))
        creature_specs.append((donor, ov))
        remap[victim] = new_row

    edits = []
    if combo_specs:
        edits.append({'op': 'gda_clone_rows', 'resource': 'combo.GDA',
                      'rows': [{'source': s, 'overrides': o} for s, o in combo_specs]})
    if creature_specs:
        edits.append({'op': 'gda_clone_rows', 'resource': 'creatures.GDA',
                      'rows': [{'source': s, 'overrides': o} for s, o in creature_specs]})

    for si, srow in enumerate(srows):
        first_new = None
        for col in (5, 6, 7, 8):
            m = srow[SK[col]]
            if m in remap:
                edits.append({'op': 'gda_cell', 'resource': 'squads.GDA', 'row': si,
                              'column': col, 'value': remap[m]})
                if first_new is None:
                    first_new = remap[m]
        # Same rule as the reskin: move the squad's overworld model only where vanilla
        # had it showing one of its own members.
        live = [srow[SK[c]] for c in (5, 6, 7, 8)
                if isinstance(srow[SK[c]], int) and 0 <= srow[SK[c]] < len(rows)]
        app = srow[SK[SQ_APPEARANCE_COL]]
        shown = _squad_shows(flat, live, app, remap)
        if shown is not None and shown in donor_of:
            donor_app = flat[donor_of[shown]][CR_APPEARANCE]
            if donor_app != app:
                edits.append({'op': 'gda_cell', 'resource': 'squads.GDA', 'row': si,
                              'column': SQ_APPEARANCE_COL, 'value': donor_app})
    return edits


def _playable(b):
    """[(creature row, name, Adv table)] for the cast with a progression table.

    `playerid != -1` catches Super Sonic and the two duel variants as well, which have
    no `Adv_*` table of their own, so the table is what decides membership.
    """
    cols, rows, K = _gda(b, 'creatures.GDA')
    have = {n.lower(): n for n in b.herf.names.values()}
    out = []
    for i, r in enumerate(rows):
        if r[K[CR_PLAYERID]] == -1:
            continue
        name = _text(b, r[K[CR_NAME]]).strip()
        res = have.get(('adv_%s.gda' % name).lower())
        if name and res:
            out.append((i, name, res))
    return out


#: `combo.GDA` is laid out as one contiguous block of rows per character - Sonic 0-5,
#: Knuckles 6-11, Shadow 12-17, and so on - and **a character's moveset is bound to that
#: block, not to the owner column.** Column 2 is a *participant requirement*: the game
#: shows a character the moves in their own block and then demands whoever column 2
#: names before one can be used.
#:
#: This was learned the hard way. The first version of `randomize_characters` permuted
#: column 2 and the partner columns and nothing else, which read as a clean moveset swap
#: in the table and was not one in play: a seed-1 run reported Sonic still holding all
#: six of his own POW moves, each now demanding Rouge, and Amy hers demanding Knuckles -
#: exactly sigma(Sonic)=Rouge and sigma(Amy)=Knuckles applied to the requirement while
#: the menu stayed put (observed 2026-10-10).
#:
#: So a real swap has to move the row *contents*. Note also that column 2 is in the
#: **party-slot** id space, not the creature-row space: Shade is slot 10 and creature 27,
#: and the first version wrote 27 into it.
#:
#: Three columns must not travel with the data. Column 0 is the row's own id and column 2
#: is the binding itself. Column 33 is the per-character art prefix - `BIF_SON`,
#: `BIF_BIG` - and stays with the character.
#:
#: **What column 33 is, corrected 2026-10-11.** It was described here as an animation
#: bank, on the theory that a borrowed move would ask the borrower's model for a clip it
#: does not have. That was wrong: the only `BIF*` resources in the archive are twelve
#: `bif_<CHAR>.nbfs` / `.nbfp` pairs - a tilemap and its palette, one per playable
#: character - so column 33 names a per-character *image*, not a clip. Pinning it was
#: still the right call, for the simpler reason that character art belongs to the
#: character.
#:
#: **And the move's animation does not live in `combo.GDA` at all.** The archive settles
#: it by naming: solo POW animations are `<CHAR>_CB_PAttack<N>.nsbca`, keyed by performer
#: and slot index - Shadow has three for six moves, Sonic two - and team animations are
#: `C_<cast>_<who>.nsbca`, such as `C_KnShaShe_Kn`, keyed by the cast. Named effects
#: follow the same scheme (`FX_SHA_Rift_prj`, `FX_SHASON_Atom`). Nothing anywhere is
#: named after a move. Confirmed in play 2026-10-11: Shadow's first slot, holding
#: Uppercut's damage, cost, status, name and icon, performed Chaos Spear.
#:
#: **How much of a move actually travels is an open question, and the first reading says
#: less than this feature claims.** Shadow's first slot was reported performing Chaos
#: Spear's two damage instances where Uppercut lands one - and the column that marks the
#: two multi-projectile moves in the whole table, 49, set on exactly Machine Gunner and
#: Chaos Spear, *did* travel and reads 0 on that row in the built ROM. So the hit
#: structure came from somewhere the deal does not reach, most likely the animation,
#: which is positional. Whether the damage *numbers* travel is not yet established and is
#: the thing to measure next: a dealt move doing a normal chunk of damage means the data
#: applies and only the performance does not, and a dealt move doing a couple of points
#: means the damage columns are not reaching the engine either.
#:
#: Until that is measured, do not describe `moves` as working. The menu, the names, the
#: descriptions and the icons are confirmed correct in play; everything past the menu is
#: unconfirmed.
COMBO_ART_PREFIX = 33
COMBO_FIXED_COLUMNS = (0, C_OWNER, COMBO_ART_PREFIX)
#: **Column 55 joins the class on 2026-10-11, because crossing it crashed the game.**
#: Shadow's third slot - vanilla Chaos Blast, an offensive move - was dealt Cream's
#: Refresh, and selecting it hard-crashed. Column 55 marks a move as support and tracks
#: "deals no damage" on 58 of the 60 playable moves, so the pair (offensive slot, support
#: move) is the line that was crossed. Adding it to the class costs three moves out of
#: sixty, which is a cheap price for a crash.
#:
#: This is the same shape as `ELEMENTLESS_ADD_IS_UNSAFE`: a property of the *slot* that
#: the move arriving there has to match, with no mechanism known for why.
#: `moves: "move"` additionally pins the cast: the participant count and the three
#: partner slots stay with the *slot* rather than traveling with the move. A slot's cast
#: is what the game was balanced and paced around - Sonic's first two moves are solo
#: because he starts alone - so leaving it alone means a per-move deal cannot make a
#: character's opening move depend on someone they have not met. It also means the
#: "Team:" line on the move panel still reads true.
COMBO_CAST_COLUMNS = (C_PARTICIPANTS,) + C_PARTNERS


#: combo.GDA 36/38/40: the authored per-tier effect text. Its leading "Nx " is the only
#: place the game states how many times a move lands - the engine takes the hit count
#: from the *slot*, not from the move, so a dealt move inherits the host slot's and its
#: damage total changes by that ratio. Confirmed in play 2026-10-11: Lure Whip, a
#: one-hit 50% move, landed twice for 49 each in Chaos Rift's two-hit slot.
C_TIER_TEXT = (36, 38, 40)


def _hit_count(b, tier1_ref):
    """How many times a move lands, read from its own tier-1 description.

    Returns an int for a damaging move, or None for one that does no damage and so
    never states a count. `None` is "unknown", not "one": Chaos Rift says "No damage"
    and still animates two hits.
    """
    import re
    text = _text(b, tier1_ref)
    m = re.match(r'\s*(\d+)\s*x\s', text, re.I)
    if m:
        return int(m.group(1))
    return 1 if '%' in text else None


def _elemental(v):
    """True if a `combo.GDA` element cell holds an element at all.

    The element column is a bitmask and 0 means "none", so this is the distinction
    `ELEMENTLESS_ADD_IS_UNSAFE` is drawn around: *which* element a move has is editable,
    whether it has one is not.
    """
    return isinstance(v, int) and v != 0


#: `creatures.GDA` columns that must NOT travel when a character's identity is moved to
#: another row. Everything else that differs between two playable rows does travel, which
#: is the rule Shadow Mode used and had confirmed in play on 2026-10-07.
#:
#: * **0** is the row's own id, and **35** (`playerid`) and **37** (`class`) are the
#:   party-slot identity the engine indexes characters by. Shadow Mode left all three
#:   alone so the party slots stayed intact, and it worked.
#: * **17/18** are the dialogue portrait prefix and its palette. The engine builds a
#:   portrait name from the prefix plus an expression suffix, and two characters share
#:   only about three of the ten expressions, so swapping them corrupts conversation art
#:   in *both* directions. Shadow Mode found this and pinned them; the cost is that
#:   dialogue shows the recruitment slot's original face.
#: * **36** is a map-pin icon only Sonic has.
#: * **19/20/21 are the three movement ability slots, and 39/40/41 are their companion
#:   flags** (each reads -1 exactly where its slot is empty — Eggman, who has no
#:   abilities, is -1 in all six). Pinning them is what makes a recruitment shuffle
#:   **softlock-proof rather than merely likely to work**: every recruitment point still
#:   grants exactly the abilities vanilla granted there, so the ability timeline is
#:   byte-identical to vanilla and no gate can become impassable. It also means the
#:   roadmap's invariant — for every prefix of the recruitment order, the party can
#:   field at least vanilla's abilities — is satisfied *without knowing the order*,
#:   which is the one input we have derived from `plt_fp_*.plo` but never confirmed in
#:   play. Abilities are therefore not randomized, and deliberately so.
CR_IDENTITY_PINNED = (0, 17, 18, 19, 20, 21, 35, 36, 37, 39, 40, 41)
#: `Adv_*.GDA` columns 12/13/14 hold the *level* each movement slot reaches (see
#: `SLOT_LEVEL_COL`). An ability at level 0 is never granted, and the obstacle gates
#: demand specific levels — Dash 0/1 and Smash 2 are the only ones that appear — so
#: pinning the slot on the creature row is not enough on its own: the progression table
#: travels with the identity, and a borrowed table carries the *donor's* schedule. These
#: columns are therefore written back to the schedule the recruitment slot had in
#: vanilla, which is the other half of the softlock proof.
ADV_ABILITY_LEVEL_COLS = tuple(SLOT_LEVEL_COL[s] for s in sorted(SLOT_LEVEL_COL))
#: The three movement slots and their companion flags, in slot order.
SLOT_ORDER = tuple(SLOT_COL[s] for s in sorted(SLOT_COL))
SLOT_FLAG_ORDER = (39, 40, 41)


def _party_slots(b):
    """{creature row: party slot} - the two id spaces `party.GDA` exists to bridge.

    They coincide for the first ten characters and diverge after, which is the whole
    reason this lookup is needed: Shade is party slot 10 but creature row 27.
    """
    pcols, prows, PK = _gda(b, 'party.GDA')
    return {r[PK[3]]: r[PK[2]] for r in prows}


def _move_blocks(b):
    """{party slot: [combo.GDA row, ...]} for every character with a real POW-move block.

    Three filters, each earning its place:

    * **The owner must be a real party slot**, which drops the 90-odd boss and enemy move
      rows further down the table - their owner column runs on up into the creature rows.
    * **The block must be contiguous**, which drops Super Sonic: he is party slot 11 but
      his three rows sit at 143, 153 and 154.
    * **Every move in it must have a name.** This drops `VFXTester` (slot 12), whose
      twelve contiguous rows are developer stubs: `namestrref` -1, cost 0, damage -1.
      Contiguity alone did not catch it, and in a per-move deal that mattered - the stubs
      were dealt into real characters' solo slots, handing them a nameless move that does
      nothing. A block whose moves have no names is not a moveset.

    What is left in vanilla is exactly the eleven recruitable characters: nine with six
    moves each, Shade with four and Eggman with two.
    """
    slots = set(_party_slots(b).values())
    ccols, crows, CK = _gda(b, 'combo.GDA')
    blocks = {}
    for i, r in enumerate(crows):
        owner = r[CK[C_OWNER]]
        if owner in slots:
            blocks.setdefault(owner, []).append(i)
    named = {i: bool(_text(b, crows[i][CK[C_NAME]]).strip()) for i in range(len(crows))}
    return {slot: rowsel for slot, rowsel in blocks.items()
            if rowsel == list(range(rowsel[0], rowsel[0] + len(rowsel)))
            and all(named[i] for i in rowsel)}


@feature('randomize_characters', 'build')
def randomize_characters(params, b):
    """Shuffle which character has which POW moves, stat line and recruitment slot.

    Three independent permutations of the playable cast, so a run stops being the same
    eleven characters in the same eleven roles.

    **`moves`** moves whole move *rows* between characters' blocks in `combo.GDA` —
    damage tiers, PP cost, status effects and their chances, element, name and
    description strrefs, icons and animation prefix, all of it — because a character's
    moveset is bound to its **block position**, not to the owner column. Permuting the
    owner column alone looks like a moveset swap in the table and is not one in play; the
    note on `COMBO_FIXED_COLUMNS` records the playtest that settled it.

    Every character reference inside the moved data is rewritten so a move's cast travels
    with it: the donor's own name in a partner list becomes the new owner, and the other
    partners map the same way. So Blue Bomber still needs its owner plus one named
    partner — it is simply a different pair, performing a different move.

    **`moves` is opt-in**, because what it moves and what it cannot move are both real.
    See "What the playtests settled" below.

    `moves` takes **`"character"`** or **`"move"`**; `true` means `"character"`.

    * **`"character"`** trades movesets wholesale: Sonic fights with Rouge's six, Rouge
      with Sonic's. Only equal-length blocks trade, so nobody ends up with more moves
      than their menu has slots - the nine six-move characters shuffle among themselves
      while Shade (four moves) and Eggman (two) keep their own.
    * **`"move"`** deals individual moves across the whole cast, so a character ends up
      with six moves from six different people. The deal runs **within participant
      class** - solo slots draw from solo moves, duo from duo - and the slot's own cast
      stays put. That is what makes it safe rather than merely exciting: a character
      keeps exactly the partners they needed in vanilla, so no opening move can come to
      depend on somebody not yet recruited, and a four-character finisher cannot land in
      a level-1 solo slot carrying damage it was never balanced for. Vanilla holds 38
      solo slots, 10 duo, 5 trio and 1 quad; the quad is alone in its class and stays.
      Shade and Eggman, who sit out `"character"` because no other block is their size,
      do take part here: their moves join the pool and their slots draw from it.

      The class is **(participants, elemental)**, not participants alone. Giving an
      element to a move that shipped without one is the operation `pow_move` refuses -
      it hard-crashed the battle twice on Focus Field - and a per-move deal does exactly
      that unless the pool is split. Vanilla's playable blocks hold eight elemental
      moves: four solo (Whirlwind, Quake Punch, Flamethrower, Tornado Kick), two duo
      (Atomic Strike, Blazing Tornado) and Triple Tornado, which is alone in its class
      and stays. So elemental moves still travel, but only into slots that were already
      elemental, and *which* element a slot has is the part that was always editable.

    One honest consequence of `"move"`: Tails and Cream are the party's healers and
    nothing reserves healing for anybody, so a deal can leave the cast without a Cure.
    That makes a run harder, not unwinnable - items still heal - but it is a real swing
    and worth knowing before a long playthrough.

    **`stats`** permutes whole stat lines across all 30 levels — speed, attack, defense,
    HP, power, grit, luck and PP together, as a block. Moving them as a block is what
    keeps a character's budget intact, which is the thing worth preserving: shuffling
    stats *within* a character instead would hand Sonic his grit as a defense score and
    his defense as speed, and the ranges are not remotely comparable (defense runs 10-22
    at level 1 while grit runs 1-7). Level and XP columns are untouched, so a character
    who joins late still joins on their own curve.

    **`recruitment`** moves a character's whole *identity* between the eleven playable
    `creatures.GDA` rows — name, 3D model, portraits, base stats, progression table and
    POW move block — which changes **who you are given and when**. It works because
    recruitment grants a *creature row*, not a character: the Chapter 4 point that
    normally hands you Shadow hands you whatever lives in row 4. That was predicted and
    then confirmed in play on 2026-10-07, when a Sonic/Shadow swap made Chapter 4 grant
    Sonic — overworld figure, encounter and story dialogue all correct, with
    `SHADOW_GET` never touched. This is that swap generalized from one pair to a
    derangement of all eleven.

    What that buys: Sonic's slot is the starting character, so a run can open as Big or
    Omega, and the story's recruitment points deal out the rest in a different order
    every seed.

    Two things deliberately stay with the slot rather than the character:

    **The `recruitment` half is confirmed in game** (starting character, ability gates,
    a story recruitment handing over the right character, move requirements, and the
    animations above). `stats` is still build-verified only, and is on by default — it
    shows on the next level-up, not on an existing save.

    * **Movement abilities are a floor, not a swap** (2026-10-11). Every recruitment
      point still grants at least the abilities vanilla granted there, at vanilla's
      levels, so no obstacle gate can become impassable — but the arriving character
      also keeps as many of their own as the three slots allow. A starting row that
      receives Knuckles keeps Dash because it must, and picks up Climb and Smash
      besides. Required abilities are never the ones dropped when a character has more
      than fits. This is why the feature does not need the recruitment order confirmed
      first: the order derived from `plt_fp_*.plo` is still only a derivation, and the
      invariant is satisfied per-slot without consulting it.
    * **Dialogue portraits**, for the reason recorded on `CR_IDENTITY_PINNED`: the
      alternative corrupts conversation art. So a conversation shows the slot's original
      face while the party screen, the overworld model and the battle portrait all show
      who you actually have. Visually wrong, and the safe side of a known crash.

    Parameters: `seed`, `moves` (`"character"` | `"move"` | false, default **false**),
    `stats` (default true), `recruitment` (default false — the half that changes who is
    in the party).

    ## What the playtests settled, 2026-10-11

    A POW move is **two things that are keyed separately**, and the day was spent
    finding the line between them.

    **What travels with the move data — confirmed in play:** name, icon, description,
    tier text, PP cost, **damage** and **status effect**. The decisive reading was
    Shadow's second slot, which in vanilla holds Chaos Rift: *no damage*, Distracted,
    8 PP. Dealt Lure Whip, it dealt damage and **stunned**. Neither could come from the
    slot, because the slot's own move deals none and applies a different status.

    **What stays with the slot — also confirmed in play:** the animation, the stylus
    minigame and the **hit count**. Shadow's slot holding Uppercut's cells landed Chaos
    Spear's two ticks with Chaos Spear's clicks and slider; Eggman's slot holding Chaos
    Spear's cells landed one. Pointing the slot at a different row instead
    (`profiles/pow_pointer_probe.json`, nothing copied) changed neither. The archive
    agrees: POW animations are `<CHAR>_CB_PAttack<N>.nsbca` and `C_<cast>_<who>.nsbca`,
    and nothing is named after a move. `animations.GDA` *is* editable - one cell moved
    Shadow onto Knuckles' clip - but the minigame is keyed elsewhere and the two must
    agree, so moving the animation alone makes the move abort.

    **So a dealt move is that move's numbers and effect, performed as the host's own
    move.** Sonic can genuinely carry Quake Punch and Blade Drop - right damage, right
    status, right cost - and they will look like Sonic's own moves and use his clicks.
    That is the shape of the feature, and it is why `moves` is opt-in rather than on.

    **Two things the class must therefore prevent.** A support move in an offensive slot
    hard-crashes on use (Cream's Refresh in Shadow's third slot, by both mechanisms), so
    column 55 is part of the class. And because the hit count comes from the slot, a
    move's damage *total* changes by the ratio of the two counts unless they match -
    Lure Whip, a one-hit 50% move, landed twice for 49 each in Chaos Rift's two-hit slot.
    So the authored hit count is part of the class too. Together they freeze 7 moves of
    60, which is the price of a deal that neither crashes nor rebalances itself.

    `recruitment` is the other half of the answer and a different one: it changes the
    *performer*, so a character arrives with their own coherent moveset, animations and
    minigames intact.

    **Confirmed in play 2026-10-11:** on `recruit_order_test.nds`, Rouge in the starting
    creature row performs her own Tornado Kick and Knuckles in Amy's row his own
    Uppercut — correct animations, correct minigames, whole movesets coherent. So the
    performer half of the key resolves through `appearance` (column 14), which travels
    with an identity, and **not** through the creature row index, which does not. That is
    why moving an identity gives a character their real moveset while moving move data
    does not, and it is moveset variety in the only form this engine allows.

    **Abilities are deliberately not included yet.** Moving a movement ability needs the
    recruitment-order invariant — for every prefix of the order, the party must be able
    to field at least vanilla's abilities — and a wrong guess there is a softlock, not a
    bad roll. See ROADMAP.

    **Status after the 2026-10-11 playtest.** The menu half is confirmed: a character's
    POW list reads as six moves from six different people, with the right names, icons
    and descriptions. What happens when one is *used* is not confirmed - see the note on
    `COMBO_ART_PREFIX`. The `stats` half has still not been played either way.

    **Corrected 2026-10-11, before that playtest ever ran.** The rewrite moved the
    element column with the rest of the row, so at seed 1 it handed an element to seven
    rows that shipped without one - including Shadow's sixth slot, which is the same
    character and the same added element as the Focus Field crash. Nothing in the
    feature noticed, because the guard lived in `pow_move` and not in the data. Both
    halves now respect it: `move` splits the pool, `character` drops the element rather
    than adding it.
    """
    import random
    rng = random.Random(int(params.get('seed', 0)))
    cast = _playable(b)
    if len(cast) < 2:
        raise ValueError('randomize_characters: fewer than two playable characters')

    def derange(items):
        """A shuffle where nothing keeps its own place."""
        order = list(items)
        for _ in range(64):
            rng.shuffle(order)
            if all(a != b_ for a, b_ in zip(order, items)):
                return order
        return order[1:] + order[:1]

    out = []
    #: Combo cast columns - the owner requirement and the three partner slots - are
    #: computed here and emitted once at the end, because *both* halves can touch them
    #: and a later absolute write would otherwise silently discard an earlier one.
    #: `moves: "character"` rewrites partners so a move's cast travels with it;
    #: `recruitment` then remaps every reference to where that identity now lives.
    cast_now = {}

    mode = params.get('moves', False)
    mode = {True: 'character', False: None}.get(mode, mode)
    if mode not in (None, 'character', 'move'):
        raise ValueError("randomize_characters: moves must be 'character', 'move', "
                         "true or false, got %r" % (params.get('moves'),))
    if mode:
        blocks = _move_blocks(b)
        ccols, crows, CK = _gda(b, 'combo.GDA')
        ncol = len(ccols)
        flat = [[r[CK[j]] for j in range(ncol)] for r in crows]

        pairs, pinned = [], COMBO_FIXED_COLUMNS
        if mode == 'character':
            # Only equal-length blocks may trade, or a character ends up with more or
            # fewer moves than their menu has slots. In vanilla that means the nine
            # six-move characters shuffle among themselves while Shade (four) and Eggman
            # (two) keep their own - the conservative thing to do with two late joiners.
            by_size = {}
            for slot, rowsel in blocks.items():
                by_size.setdefault(len(rowsel), []).append(slot)
            sigma = {}
            for size, group in sorted(by_size.items()):
                if len(group) < 2:
                    continue
                group = sorted(group)
                for taker, donor in zip(group, derange(group)):
                    sigma[taker] = donor
            if not sigma:
                raise ValueError(
                    'randomize_characters: no two move blocks are the same size')
            # donor -> taker, which is how a character reference inside the moved data is
            # rewritten: the donor's own name in its partner list becomes the new owner.
            inv = {d: t for t, d in sigma.items()}
            for taker, donor in sorted(sigma.items()):
                pairs += list(zip(blocks[taker], blocks[donor]))
        else:
            # Per-move: deal individual moves across the whole cast instead of trading
            # movesets wholesale. The deal happens **within participant class** - every
            # solo slot draws from the solo moves, every duo slot from the duo moves -
            # which is what makes it safe without a single special case. A character
            # keeps exactly the cast requirements they had, so no opening move can come
            # to depend on somebody not yet recruited, and a move's damage stays in the
            # band it was balanced for rather than a four-character finisher landing in
            # a level-1 solo slot. In vanilla the classes hold 38 solo slots, 10 duo,
            # 5 trio and 1 quad; the quad is alone in its class and so stays put.
            inv = {}
            pinned = COMBO_FIXED_COLUMNS + COMBO_CAST_COLUMNS
            by_class = {}
            for slot in sorted(blocks):
                for row in blocks[slot]:
                    key = (flat[row][C_PARTICIPANTS],
                           _elemental(flat[row][C_ELEMENT]),
                           bool(flat[row][C_SUPPORT]),
                           _hit_count(b, flat[row][C_TIER_TEXT[0]]))
                    by_class.setdefault(key, []).append(row)
            for klass, slots in sorted(by_class.items(), key=repr):
                if len(slots) < 2:
                    continue
                pairs += list(zip(slots, derange(slots)))

        for dst, src in pairs:
            for col in range(ncol):
                if col in pinned:
                    continue
                old_v, new_v = flat[dst][col], flat[src][col]
                if col in C_PARTNERS and isinstance(new_v, int):
                    new_v = inv.get(new_v, new_v)
                if (col == C_ELEMENT and ELEMENTLESS_ADD_IS_UNSAFE
                        and _elemental(new_v) and not _elemental(old_v)):
                    # Never hand an element to a row that shipped without one - the
                    # operation `pow_move` refuses outright. Losing one is allowed; the
                    # hazard is only ever in the adding. In `move` mode the classing
                    # above means this never fires; in `character` mode whole blocks
                    # trade, so it does, and the move arrives elementless.
                    continue
                if new_v is None or new_v == old_v:
                    # A None cell cannot be written; column 33 carries a string on every
                    # playable row, so this only ever skips a real no-op.
                    continue
                if col in COMBO_CAST_COLUMNS:
                    cast_now[(dst, col)] = new_v
                    continue
                op = 'gda_string' if isinstance(new_v, str) else 'gda_cell'
                out.append({'op': op, 'resource': 'combo.GDA',
                            'row': dst, 'column': col, 'value': new_v})

    if params.get('recruitment'):
        ccols, crows, CK = _gda(b, 'creatures.GDA')
        rows_of = [row for row, _, _ in cast]
        table_of = {row: res for row, _, res in cast}
        cflat = {row: [crows[row][CK[j]] for j in range(len(ccols))]
                 for row in rows_of}
        takers = sorted(rows_of)
        donors = derange(takers)
        for taker, donor in zip(takers, donors):
            for col in range(len(ccols)):
                if col in CR_IDENTITY_PINNED:
                    continue
                old_v, new_v = cflat[taker][col], cflat[donor][col]
                if new_v is None or new_v == old_v:
                    continue
                op = 'gda_string' if isinstance(new_v, str) else 'gda_cell'
                out.append({'op': op, 'resource': 'creatures.GDA',
                            'row': taker, 'column': col, 'value': new_v})
            # --- movement abilities: the slot's own, plus whatever else fits --------
            #
            # The requirement is one-directional. Every recruitment point must still
            # grant at least what vanilla granted there, or a gate it opened becomes
            # impassable; nothing stops it granting *more*. So the slot's vanilla
            # abilities are kept in their vanilla positions on their vanilla schedules,
            # and the arriving character's own abilities fill whatever slots are left.
            # A starting row that receives Knuckles therefore keeps Dash - it has to -
            # and picks up Climb and Smash besides.
            #
            # Three slots is the hard limit, so a character with more abilities than
            # there are free slots loses the surplus, taken in their own slot order.
            # A required ability is never the one dropped.
            req_slots = [cflat[taker][c] for c in SLOT_ORDER]
            own_slots = [cflat[donor][c] for c in SLOT_ORDER]
            final = {}                       # slot -> (ability, table, level column)
            for i, ability in enumerate(req_slots):
                if ability != -1:
                    final[i] = (ability, table_of[taker], ADV_ABILITY_LEVEL_COLS[i])
            have = {v[0] for v in final.values()}
            free = [i for i in range(len(SLOT_ORDER)) if i not in final]
            for i, ability in enumerate(own_slots):
                if ability == -1 or ability in have or not free:
                    continue
                final[free.pop(0)] = (ability, table_of[donor],
                                      ADV_ABILITY_LEVEL_COLS[i])
                have.add(ability)
            for i, (scol, fcol) in enumerate(zip(SLOT_ORDER, SLOT_FLAG_ORDER)):
                ability = final[i][0] if i in final else -1
                # The companion flag reads 1 on an occupied first slot, 0 on an occupied
                # second or third and -1 on an empty one - true for all eleven rows.
                flag = -1 if ability == -1 else (1 if i == 0 else 0)
                for col, value in ((scol, ability), (fcol, flag)):
                    if cflat[taker][col] != value:
                        out.append({'op': 'gda_cell', 'resource': 'creatures.GDA',
                                    'row': taker, 'column': col, 'value': value})
            # The progression table traveled with the identity, so the ability levels it
            # carries are the donor's. Rewrite them to match the assignment above, each
            # from the table that authored that ability's schedule. The deal is a
            # permutation of the same eleven tables, so each is rewritten exactly once.
            arrived = table_of[donor]
            acols, arows, AK = _gda(b, arrived)
            loaded_adv = {t: _gda(b, t) for t in {v[1] for v in final.values()}}
            for i, col in enumerate(ADV_ABILITY_LEVEL_COLS):
                if i in final:
                    _, src, srccol = final[i]
                    scols, srows, SK = loaded_adv[src]
                    levels = [srows[r][SK[srccol]] for r in range(len(srows))]
                else:
                    levels = [0] * len(arows)
                for r in range(min(len(arows), len(levels))):
                    want, has = levels[r], arows[r][AK[col]]
                    if isinstance(want, int) and want != has:
                        out.append({'op': 'gda_cell', 'resource': arrived,
                                    'row': r, 'column': col, 'value': want})

        # An identity brought its POW move block with it (creature columns 22-27 are
        # pointers), but every move in that block still demands its *old* party slot.
        # Column 2 is a participant requirement in party-slot space, so a block that
        # moved to another row asks for whoever now occupies the slot it came from -
        # observed in play 2026-10-11, where Rouge in the starting row could not use her
        # own solo moves without Tails, and Knuckles needed Eggman. Remapping every
        # owner and partner reference through the same permutation fixes it and keeps a
        # team-up move naming the same *character* it was authored for, at their new
        # slot. Partner references in moves the recruit cannot field yet simply grey the
        # move out, exactly as vanilla does with Sonic's Blue Bomber before Tails joins.
        slot_of = _party_slots(b)
        sigma = {slot_of[d]: slot_of[t] for t, d in zip(takers, donors)
                 if d in slot_of and t in slot_of}
        blocks = _move_blocks(b)
        bcols, brows, BK = _gda(b, 'combo.GDA')
        for rowsel in blocks.values():
            for row in rowsel:
                for col in (C_OWNER,) + C_PARTNERS:
                    have = cast_now.get((row, col), brows[row][BK[col]])
                    if isinstance(have, int) and have in sigma:
                        cast_now[(row, col)] = sigma[have]

    if params.get('stats', True):
        tables = [c[2] for c in cast]
        donors = derange(tables)
        loaded = {t: _gda(b, t) for t in tables}
        for table, donor in zip(tables, donors):
            cols, rows, K = loaded[table]
            dcols, drows, DK = loaded[donor]
            for i in range(min(len(rows), len(drows))):
                for col in sorted(ADV_STATS.values()):
                    old, new = rows[i][K[col]], drows[i][DK[col]]
                    if isinstance(new, int) and new != old:
                        out.append({'op': 'gda_cell', 'resource': table,
                                    'row': i, 'column': col, 'value': new})

    if cast_now:
        ccols2, crows2, CK2 = _gda(b, 'combo.GDA')
        for (row, col), value in sorted(cast_now.items()):
            if value != crows2[row][CK2[col]]:
                out.append({'op': 'gda_cell', 'resource': 'combo.GDA',
                            'row': row, 'column': col, 'value': value})
    return out


@feature('randomize_encounters', 'game')
def randomize_encounters(params, b):
    """Give every enemy species a different look, keeping its stats where they are.

    The point is variety of *appearance*, not of difficulty. A species keeps its own
    level, stats, moves and XP value and only changes what it looks like and what it is
    called, so a Gizoid that turns up in an early zone arrives at that zone's power. The
    alternative - moving creatures between squads - either trivialises the early game or
    makes it unplayable, because a creature's stats travel with it.

    The remap is a **derangement**: every species becomes a different one, and the swap
    is global, so a species that appears in eleven squads looks the same in all eleven.
    That keeps the world coherent - you learn that the thing which looks like a Gizoid is
    actually the local trash - rather than making each encounter independently random.

    Identity is six columns (`CR_ID_INTS`, `CR_ID_STRINGS`) plus the squad's own
    overworld model, which is repointed too so that what you walk into matches what you
    fight.

    `mode` selects what "different" means:

    * **`reskin`** (default, proven in play) moves identity only. Cheap and safe, but a
      transplanted enemy fights with whatever moves its slot had, so it is a costume.
    * **`transplant`** appends a real creature: the donor's model, portraits, class,
      innate abilities *and its own POW moves*, with the victim's stats and the moves'
      damage rescaled to the victim's POW. This is the one that makes a Green Hill
      Gizoid feel like a Gizoid. It appends rows to `creatures.GDA` and `combo.GDA`,
      which is confirmed to work in game (2026-10-09) but is newer and less tested.

    Parameters: `seed` (int, reproducible), `mode` (`reskin` | `transplant`), `protect`
    (extra creature row ids to leave alone on top of the curated boss and NPC lists),
    `include_bosses` (default false).

    Bosses are protected by default. A boss keeps its squad, stats, moves and the plot
    that triggers it, so `include_bosses` is mostly a taste decision about cutscenes -
    but **not purely one**, because the skin itself can break a battle. Repointing a
    squad at an appearance whose `appearances.GDA` row has no model name black-screens
    the fight on entry; three creature rows carry such an appearance and are excluded
    automatically. Any battle that plays a creature-specific animation is a similar
    risk that has not been characterised, so an unexpected hang after a remap is worth
    reporting rather than assuming impossible.

    **Confirmed in game 2026-10-10, in both modes.** Reskin first: enemies changed
    species and the overworld model matched what loaded in the battle, once the
    appearance bug was fixed. Then transplant: a Gizoid Centurion on a level-2 slot used
    Hellfire for 19 damage with 10 splash, which is the donor's move at the local power
    level and is exactly what the mode is for.
    """
    import random

    rng = random.Random(int(params.get('seed', 0)))
    cols, rows, K = _gda(b, 'creatures.GDA')
    scols, srows, SK = _gda(b, 'squads.GDA')
    ncol = len(cols)
    flat = [[r[K[j]] for j in range(ncol)] for r in rows]

    extra = {int(x) for x in params.get('protect', [])}

    include_bosses = bool(params.get('include_bosses', False))

    def protected(i):
        r = rows[i]
        if i in extra or r[K[CR_PLAYERID]] != -1:
            return True
        if (r[K[CR_LEVEL]], r[K[CR_HP]], r[K[CR_POW]], r[K[CR_DEF]]) == NPC_STATLINE:
            return True
        if include_bosses:
            return False
        name = _text(b, r[K[CR_NAME]]).lower()
        return any(p in name for p in PROTECTED_NAMES)

    # A creature whose appearance row carries no model name must not take part. Three
    # rows do: the playable-character duel variants (75, 77, 116) all point at
    # appearance 4, which is an empty shell because party models load through a
    # different path than enemy ones. Handing that appearance to an enemy makes the
    # battle try to load a model that does not exist, and it black-screens on entry
    # instead of starting — observed in the Marauder ambush, 2026-10-08.
    modelless = _modelless_creatures(b)

    def usable(i):
        lv, hp = rows[i][K[CR_LEVEL]], rows[i][K[CR_HP]]
        return (isinstance(lv, int) and lv >= 1 and isinstance(hp, int)
                and 0 < hp < 9999 and i not in modelless
                and not protected(i))

    pool = [i for i in range(len(rows)) if usable(i)]
    if len(pool) < 2:
        raise ValueError('randomize_encounters: fewer than two remappable species')

    # Derange: rotating a shuffled list guarantees nobody keeps their own identity,
    # which a plain shuffle does not.
    order = pool[:]
    rng.shuffle(order)
    donor_of = {victim: order[(i + 1) % len(order)] for i, victim in enumerate(order)}

    if str(params.get('mode', 'reskin')) == 'transplant':
        return _transplant_edits(b, rng, rows, K, flat, donor_of, srows, SK, params)

    edits, new_app = [], {}
    for victim, donor in sorted(donor_of.items()):
        for c in CR_ID_INTS:
            value = flat[donor][c]
            if value != flat[victim][c]:
                edits.append({'op': 'gda_cell', 'resource': 'creatures.GDA',
                              'row': victim, 'column': c, 'value': value})
        for c in CR_ID_STRINGS:
            value = flat[donor][c]
            if isinstance(value, str) and value != flat[victim][c]:
                edits.append({'op': 'gda_string', 'resource': 'creatures.GDA',
                              'row': victim, 'column': c, 'value': value})
        new_app[victim] = flat[donor][CR_APPEARANCE]

    # The squad carries its own overworld model, and it is **not** simply the members':
    # 66 of 163 squads deliberately differ, some pointing well outside the creature
    # range at models no creature uses. So it is repointed only where vanilla had it
    # following the first member, and then from that member's *own* new appearance.
    #
    # Keying this off a shared old->new appearance map was the earlier bug: 19
    # appearance ids are used by more than one creature — id 26 by five of them — so the
    # map was last-writer-wins and a squad's overworld model followed a different
    # creature than the one that actually loaded in the battle. That is the reported
    # "wild boar in the overworld, Gizoid in the fight".
    for si, srow in enumerate(srows):
        members = [srow[SK[c]] for c in (5, 6, 7, 8)]
        live = [m for m in members if isinstance(m, int) and 0 <= m < len(rows)]
        shown = _squad_shows(flat, live, srow[SK[SQ_APPEARANCE_COL]], new_app)
        if shown is None:
            continue                       # squad does not track a member; leave it
        if new_app[shown] != srow[SK[SQ_APPEARANCE_COL]]:
            edits.append({'op': 'gda_cell', 'resource': 'squads.GDA', 'row': si,
                          'column': SQ_APPEARANCE_COL, 'value': new_app[shown]})
    return edits


# --------------------------------------------------------------------------
# items, gear and Chao
# --------------------------------------------------------------------------

def _item_effect_rows(res, effects):
    out = []
    for key, amount in effects.items():
        if key.lower() == 'element':
            for el in ([amount] if isinstance(amount, str) else amount):
                if el.lower() not in ITEM_ELEMENTS:
                    raise ValueError('unknown item element %r; known: %s'
                                     % (el, sorted(ITEM_ELEMENTS)))
                out.append((res, 'ELEMENT', 1, ITEM_ELEMENTS[el.lower()]))
            continue
        if key.lower() == 'resist':
            # Authored exactly as the five shield Chao author it: a row labelled
            # ELEMENT carrying the resistance stat id and a magnitude. The shipped
            # ones all use 50, and a dict form lets a profile pick its own.
            items = amount.items() if isinstance(amount, dict) else [
                (el, 50) for el in ([amount] if isinstance(amount, str) else amount)]
            for el, pct in items:
                if el.lower() not in ITEM_RESISTS:
                    raise ValueError(
                        'unknown resistance element %r; known: %s. Ice resistance is '
                        'predicted to be stat 80 but no shipped item grants it, so it '
                        'is not offered.' % (el, sorted(ITEM_RESISTS)))
                out.append((res, 'ELEMENT', int(pct), ITEM_RESISTS[el.lower()]))
            continue
        stat = key.upper().rstrip('+')
        if stat not in STATS:
            raise ValueError('unknown stat %r; known: %s' % (key, sorted(STATS)))
        out.append((res, stat + '+', int(amount), STATS[stat]))
    return [{'op': 'twoda_add_row', 'resource': r, 'row': label,
             'values': {'EffectId': '1', 'Data': str(data), 'SData1': str(stat),
                        'SData2': '0', 'SData3': '0', 'Pulse': '-1'}}
            for r, label, data, stat in out]


@feature('custom_item', 'game')
def custom_item(params, b):
    """Give an item a set of stat effects, and optionally rename/redescribe it.

    Effects are additive rows on the item's own .ITM table, which is how the
    shipped items express their bonuses. `element` grants that element to basic
    attacks and may be a single name or a list (all six stack — confirmed).

    `resist` grants elemental **resistance**, authored the way the five shield Chao
    author it. It takes a name, a list of names, or a dict of name to magnitude; the
    shipped Chao all use 50, which is the default:

        {"item": 79, "name": "Aegis Amulet", "effects": {"resist": ["fire", "wind"]}}
        {"item": 79, "effects": {"resist": {"lightning": 80}, "GRT": 2}}

    Resistance is offered for the five elements a shipped item actually grants. Ice is
    predicted to be stat 80 by the same offset that fits the other five and is refused,
    because nothing in the game exercises it. **The magnitudes are build-verified only** —
    the ids come from shipped items, but no resistance value other than 50 has been seen
    in play, and whether 50 means "half damage" has never been measured.
    """
    out = []
    for spec in (params if isinstance(params, list) else [params]):
        _need(spec, 'item')
        item = int(spec['item'])
        res = _itm_res(b, item)
        out += _item_effect_rows(res, spec.get('effects', {}))
        if 'name' in spec:
            out.append({'op': 'item_name', 'item': item, 'text': spec['name']})
        if 'description' in spec:
            out.append({'op': 'item_desc', 'item': item, 'text': spec['description']})
    return out


@feature('custom_chao', 'game')
def custom_chao(params, b):
    """Effects for a Chao across its growth tiers.

    The tier item ids are **read from Chaos.GDA**, not computed. Most species are
    spaced 40 apart (92 -> 132 -> 172), but six repeat one id in all three slots and
    so have a single fixed form: Ferox, Pooki, Farfinkle, Baki, Stugs and Fimbley.
    Assuming `N, N+40, N+80` both points at files that do not exist and, worse, would
    apply three tiers of effects to one item and silently triple them.

    Note that single-tier does **not** mean event-only. `Chaos.GDA` column 5
    (`#3678486078`) is the event flag and is set on exactly five species, items
    211-215; **Ferox has it at 0** and is hatchable despite not growing. Growth and
    obtainability are independent properties and should not be inferred from one
    another.

    A Chao's displayed name comes from its **species** entry in Chaos.GDA, not from
    its item, so renaming uses `chao_name`; `item_name` silently does nothing.

    `max_tier: true` points all three tier columns at the top-tier item, so the Chao
    is at full strength immediately — see the comment on that branch for why this is
    the only way to reach a code-driven Chao's full effect without trading.
    """
    cols, rows, K = _gda(b, 'Chaos.GDA')
    tier_map = {}
    for r in rows:
        ids = [r[K[c]] for c in (6, 7, 8)]
        ids = [i for i in ids if isinstance(i, int) and i >= 0]
        for i in ids:
            tier_map[i] = ids

    out = []
    for spec in (params if isinstance(params, list) else [params]):
        _need(spec, 'item')
        base = int(spec['item'])
        ids = tier_map.get(base)
        if ids is None:
            raise ValueError('item %d is not a Chao in Chaos.GDA' % base)
        tiers = spec.get('tiers') or [spec.get('effects', {})] * 3
        if len(tiers) != 3:
            raise ValueError('custom_chao needs exactly 3 tiers, got %d' % len(tiers))
        # Emit the rename FIRST: `chao_name` resolves a species through the very tier
        # columns that `max_tier` rewrites, so remapping first makes the lookup fail.
        if 'name' in spec:
            out.append({'op': 'chao_name', 'item': base, 'text': spec['name']})

        if spec.get('max_tier'):
            # Point every tier column at the top-tier item, so the species is at full
            # strength from the moment it is obtained.
            #
            # This exists because Chao normally level up by TRADING over the
            # discontinued Nintendo WFC, so on a modern playthrough they are stuck at
            # tier 1. Flattening the item *effects* is not enough for a code-driven
            # Chao: its hardcoded behaviour (Spartoi's instant-KO odds, say) is not in
            # the item table at all. The three tier items are byte-identical and empty,
            # so the only thing distinguishing a level-1 from a level-3 Spartoi is which
            # id is held — which is what the code must key on. Remapping the columns
            # hands over the top id immediately.
            #
            # The engine already accepts this: the event Chao (211-215) ship with all
            # three columns set to one id and work in game.
            top = ids[-1]
            row_idx = next(i for i, r in enumerate(rows)
                           if any(r[K[c]] == base for c in (6, 7, 8)))
            for col in (6, 7, 8):
                if rows[row_idx][K[col]] != top:
                    out.append({'op': 'gda_cell', 'resource': 'Chaos.GDA',
                                'row': row_idx, 'column': col, 'value': top})

        seen = set()
        for t, item_id in enumerate(ids):
            if item_id in seen:
                continue          # single-tier species: apply the top tier once only
            seen.add(item_id)
            effects = tiers[-1] if len(set(ids)) == 1 else tiers[t]
            out += _item_effect_rows(_itm_res(b, item_id), effects)
    return out


@feature('store_stock', 'build')
def store_stock(params, b):
    """Add items to a shop, so custom gear is actually reachable in a normal run.

    Store<N>.GDA rows are (id, item id, buy price, sell price).
    """
    out = []
    for spec in (params if isinstance(params, list) else [params]):
        _need(spec, 'store', 'items')
        name = 'Store%d.GDA' % int(spec['store'])
        cols, rows, K = _gda(b, name)
        next_id = max(r[K[0]] for r in rows) + 1
        for entry in spec['items']:
            item = int(entry['item'] if isinstance(entry, dict) else entry)
            buy = int(entry.get('buy', 40)) if isinstance(entry, dict) else 40
            sell = int(entry.get('sell', buy // 2)) if isinstance(entry, dict) else 20
            out.append({'op': 'gda_add_row', 'resource': name,
                        'values': [next_id, item, buy, sell]})
            next_id += 1
    return out



# --------------------------------------------------------------------------
# randomizer: loot, shops and Chao
# --------------------------------------------------------------------------

#: Rows every .ITM table carries that describe the item rather than an effect. The
#: effect rows are whatever is left: 'SPD+', 'POW+', 'ELEMENT' and so on.
ITM_BOILERPLATE = ('SpellData', 'CollectionData_Equip', 'CollectionData_Use')
#: Stats worth rolling onto gear. HEAL/HEALPP are consumable behaviour rather than a
#: worn bonus, so rolling them onto a ring produces an item that does nothing.
ROLLABLE_STATS = ('SPD', 'ATK', 'DEF', 'MAXHP', 'POW', 'GRT', 'LCK', 'MAXPP')
_ELEMENT_IDS = set(ITEM_ELEMENTS.values())


def _itm_effects(b, res):
    """[(row label, SData1, Data)] for the real effect rows of an .ITM table.

    Returns [] for an item whose table is nothing but boilerplate — which is also how
    a code-driven Chao presents, so those fall out of every randomizer here for free.
    """
    import twoda
    try:
        t = twoda.parse_2da(b.herf.read(b.resource(res)))
    except Exception:
        return []
    out = []
    for label, vals in t.rows:
        if label in ITM_BOILERPLATE or vals.get('EffectId') != '1':
            continue
        try:
            out.append((label, int(vals['SData1']), int(vals['Data'])))
        except (KeyError, ValueError):
            continue
    return out


#: Effect rows that are not stat effects and are never re-rolled, but **must still be
#: described**. `_itm_effects` keeps only `EffectId == 1`, which is right for randomizing
#: - a Revival Ring's revival is not a number to shuffle - but it meant the regenerated
#: text silently dropped it, and a Revival Ring that reads "Restores 18 HP." looks like
#: an expensive Health Seed. Across all 219 `.ITM` tables there are exactly three kinds
#: of non-stat row: VFX (105, cosmetic), RemoveStatus (15) and Resurrect (2).
ITM_SPECIAL_WORDS = {
    'Resurrect': 'Revives a fallen character.',
    'RemoveStatus': 'Cures status effects.',
}


def _itm_specials(b, res):
    """The non-stat effects of an .ITM table, as finished sentences."""
    import twoda
    try:
        t = twoda.parse_2da(b.herf.read(b.resource(res)))
    except Exception:
        return []
    out = []
    for label, vals in t.rows:
        if label in ITM_BOILERPLATE or vals.get('EffectId') == '1':
            continue
        word = ITM_SPECIAL_WORDS.get(label)
        if word and word not in out:
            out.append(word)
    return out


#: how a stat id reads in an item description. POW and GRT are spelled out because
#: neither appears on the character sheet, so the description is the *only* place a
#: player can learn what a randomized item did.
STAT_WORDS = {
    0: 'HP', 21: 'Speed', 22: 'Attack', 23: 'Defense', 24: 'Max HP', 25: 'POW',
    26: 'GRT', 27: 'Luck', 28: 'PP', 36: 'Max PP',
}
_ELEMENT_WORDS = {v: k for k, v in ITEM_ELEMENTS.items()}


#: What the item panel draws for itself, in green, beneath the description. Established
#: by reading it off the screen on 2026-10-10:
#:
#:   * **shown** — Speed (`Speed +1`), Defense (`Defense +1`), Luck (`Luck -3`), and
#:     both heals.
#:   * **not shown** — **POW**, **GRT** and **Max HP**. Master Hydraulics reads
#:     "Speed +1, POW +5" and the panel draws only `Speed +1`; Shielded Sneakers reads
#:     "Defense +1, Max HP +3" and the panel draws only `Defense +1`; Cursed Claws reads
#:     "Speed -2, GRT +4, Luck -3" and the panel draws only the Speed and Luck lines.
#:
#: Attack has not been observed either way. This is why the generated description lists
#: *everything* rather than only the hidden stats: three of the ten stats an item can
#: carry have no other place in the game where a player could read them.
PANEL_HIDES = (STATS['MAXHP'], STATS['POW'], STATS['GRT'])


def _describe(effects):
    """A short description matching what an item now actually does.

    Randomizing effects without rewriting the text leaves every description lying, and
    for three stats there is no way to check in game — see `PANEL_HIDES`. For those the
    description *is* the interface.
    """
    heal, stats, elements = [], [], []
    for _, stat, amount in effects:
        if stat in _ELEMENT_WORDS:
            elements.append(_ELEMENT_WORDS[stat])
        elif stat in (STATS['HEAL'], STATS['HEALPP']):
            # The two heals are **not** written the same way, so match whatever the
            # panel prints rather than guessing at a shared meaning. An HP heal of 18
            # draws as `HP +18%`; a PP heal of 94 draws as `PP +94`, no percent sign
            # (both observed in play 2026-10-10). Whether the underlying number means
            # the same thing in both is unresolved - vanilla HP heals run 10/50/100/250
            # and PP heals 5/10/50/999, and a POW Candy restoring "5%" of a seven-point
            # PP pool would do nothing, so PP at least is almost certainly flat.
            unit = '%' if stat == STATS['HEAL'] else ''
            heal.append('%d%s %s' % (abs(amount), unit, STAT_WORDS.get(stat, '?')))
        else:
            word = STAT_WORDS.get(stat)
            if word:
                stats.append('%s %+d' % (word, amount))
    parts = []
    if heal:
        parts.append('Restores %s.' % ' and '.join(heal))
    if stats:
        parts.append('%s.' % ', '.join(stats))
    if elements:
        parts.append('Grants %s.' % ', '.join(sorted(set(elements))))
    return ' '.join(parts) or 'No effect.'


def _applied_effects(effects, edits, res):
    """The effect list as it will be *after* `edits`, for describing the result."""
    by_label = {}
    for e in edits:
        if e.get('resource') == res and e.get('op') == 'twoda_cell':
            by_label.setdefault(e['row'], {})[e['column']] = e['value']
    out = []
    for label, stat, amount in effects:
        changed = by_label.get(label, {})
        out.append((label, int(changed.get('SData1', stat)),
                    int(changed.get('Data', amount))))
    return out


def _itm_res(b, item_id):
    """The .ITM resource an item actually uses, from Items.GDA rather than its id.

    `item<id>.itm` holds for 213 of 230 items and is wrong for the other 17: Health
    Seed is id 0 but lives in `item1.itm`, Bug Spray is id 1 in `item2.itm`, and four
    separate ids share `item12.itm`. Assuming the convention does not merely skip those
    items, it edits *a different item's* table while writing the description to the
    original - which is how a randomized run ended up with an untouched Health Seed and
    a Bug Spray describing someone else's effects.
    """
    try:
        rec = b.items().get(int(item_id))
    except Exception:
        rec = None
    return rec['file'] if rec and rec.get('file') else 'item%d.itm' % item_id


def _tlk_ok(b, ref):
    """Whether a strref actually resolves, so a description edit cannot abort a build."""
    if not isinstance(ref, int) or ref < 0:
        return False
    try:
        b.tlk.index_of_id(ref)
        return True
    except Exception:
        return False


def _chao_tier_ids(b):
    """Every item id that is a Chao growth tier, read from Chaos.GDA."""
    cols, rows, K = _gda(b, 'Chaos.GDA')
    return {v for r in rows for c in (6, 7, 8)
            for v in (r[K[c]],) if isinstance(v, int) and v >= 0}


def _reroll_effects(rng, res, effects, scale, stats):
    """Edits that re-roll one table's effect rows in place.

    The row *label* is left alone while `SData1` and `Data` are rewritten, so a row
    still called 'SPD+' may grant luck. The game reads the numeric stat id, not the
    label — every shipped item agrees between the two, which is why this is worth
    stating: if a build ever shows the wrong bonus, the label is the first suspect.
    """
    lo, hi = scale
    rollable = {STATS[s] for s in stats}

    def rescale(amount):
        """Scale magnitude, keep sign. A cursed item must stay cursed: clamping to a
        positive floor turns a -10 GRT penalty into a +1 bonus and quietly deletes a
        whole category of item."""
        sign = -1 if amount < 0 else 1
        return sign * max(1, int(round(abs(amount) * rng.uniform(lo, hi))))

    out = []
    for label, stat, amount in effects:
        if stat in _ELEMENT_IDS:
            # Keep an element row an element row. Rolling a stat id into it would ask
            # the engine to grant "fire 7", which is not a thing the format expresses.
            new_stat = ITEM_ELEMENTS[rng.choice(sorted(ITEM_ELEMENTS))]
            new_amount = 1
        elif stat in (STATS['HEAL'], STATS['HEALPP']):
            # Potency varies, but a potion stays a potion. Re-rolling these onto worn
            # stats leaves the run with no healing items whatsoever, which is both
            # unplayable and not what anyone means by randomizing loot.
            new_stat, new_amount = stat, rescale(amount)
        elif stat in rollable:
            new_stat, new_amount = STATS[rng.choice(list(stats))], rescale(amount)
        else:
            # An id outside the confirmed table - revive and the other scripted effects
            # live here. Per CLAUDE.md, leave alone what has not been confirmed.
            continue
        if new_stat != stat:
            out.append({'op': 'twoda_cell', 'resource': res, 'row': label,
                        'column': 'SData1', 'value': new_stat})
        if new_amount != amount:
            out.append({'op': 'twoda_cell', 'resource': res, 'row': label,
                        'column': 'Data', 'value': new_amount})
    return out


@feature('randomize_items', 'game')
def randomize_items(params, b):
    """Re-roll what each piece of gear does, keeping roughly how much it does.

    Every effect row on every item gets a new stat, and its magnitude is multiplied by
    a factor drawn from `scale` (default 0.5x to 2x). Magnitude is scaled rather than
    drawn fresh so the item curve survives: a late-game ring stays better than a
    starter one, and the randomizer changes *what* you hunt for, not whether the
    economy still works.

    Three kinds of row are deliberately **not** re-rolled onto new stats:

    * **HEAL / HEALPP** keep their stat and only vary in potency. A potion stays a
      potion — re-rolling these onto worn stats leaves a run with no healing items at
      all, which is unplayable and is not what randomizing loot means.
    * **Element rows** stay element rows. They are a different id space
      (`ITEM_ELEMENTS`) and the format has no way to express "fire 7".
    * **Anything with a stat id outside the confirmed table** is left completely alone.
      Revive and the other scripted effects live there, and per CLAUDE.md unconfirmed
      behaviour does not get rewritten on a guess.

    Magnitude scaling keeps the **sign**, so a cursed item stays cursed. Clamping to a
    positive floor would turn a -10 GRT penalty into a +1 bonus and silently delete a
    whole category of item.

    Parameters: `seed`, `scale` (two numbers, default [0.5, 2.0]), `stats` (names from
    `ROLLABLE_STATS`), `items` (explicit item ids; default every item that has effects).

    **Untested in game.** Rewrites existing rows via `twoda_cell`, which is proven, but
    no build has yet been played with gear whose effects disagree with their row labels.
    """
    import random
    rng = random.Random(int(params.get('seed', 0)))
    scale = tuple(params.get('scale', (0.5, 2.0)))
    stats = tuple(params.get('stats', ROLLABLE_STATS))
    for s in stats:
        if s not in STATS:
            raise ValueError('unknown stat %r; known: %s' % (s, sorted(STATS)))

    if params.get('items'):
        ids = [int(i) for i in params['items']]
    else:
        cols, rows, K = _gda(b, 'Items.GDA')
        ids = [r[K[0]] for r in rows if isinstance(r[K[0]], int) and r[K[0]] >= 0]

    # Chao are items too, and `randomize_chao` owns them. Both features expand against
    # the *original* ROM, so if both re-rolled the same table the second would compute
    # its edits from values the first had already replaced and the build would fail on
    # a stale no-op. The exclusion has to be by **resource**, not by id: the four
    # elemental Shield items share their .ITM tables with Chao tiers (item186-189.itm),
    # so filtering ids alone still lets both features write the same file.
    # Keys are lowercased throughout: Items.GDA spells the same file both
    # 'item1.itm' and 'Item130.itm', and two spellings of one table group as two.
    chao_res = {_itm_res(b, i).lower() for i in _chao_tier_ids(b)}

    describe = bool(params.get('describe', True))

    # Group by *resource*, not by item id. Several ids share one .ITM table — five point
    # at `item12.itm` alone — so rolling per id would re-roll the same table repeatedly,
    # each time computing from the original values (features expand against the original
    # ROM) and colliding on a stale no-op. One roll per table, one description per id
    # that uses it.
    by_res = {}
    for item in sorted(set(ids)):
        by_res.setdefault(_itm_res(b, item).lower(), []).append(item)

    out = []
    for res, members in sorted(by_res.items()):
        if res in chao_res:
            continue
        effects = _itm_effects(b, res)
        if not effects:
            continue
        rolled = _reroll_effects(rng, res, effects, scale, stats)
        if not rolled:
            continue
        out += rolled
        if not describe:
            continue
        text = ' '.join([_describe(_applied_effects(effects, rolled, res))]
                        + _itm_specials(b, res))
        for item in members:
            # A few items have effects but no resolvable description strref. Re-rolling
            # them is still correct; only the description is skipped.
            if _tlk_ok(b, (b.items().get(item) or {}).get('desc_ref')):
                out.append({'op': 'item_desc', 'item': item, 'text': text})
    return out


@feature('chao_level', 'game')
def chao_level(params, b):
    """Grant every Chao the effects of a higher growth tier than it can reach alone.

    **A single player cannot level a Chao at all.** The game says so itself, in its own
    help text: *"you can trade them with two different friends to help them to grow in
    power and reach their full potential (Max!)"* (string 5265), and, when a trade would
    not count, *"Neither Chao will level up. You must trade with someone new for the Chao
    to increase to Max level."* (8951). Level 2 needs a wireless trade with one person
    and level 3 needs a trade with a **different** person, so the game tracks who you
    have traded with rather than how often. In 2026 that is two thirds of the Chao system
    sealed off.

    `Chaos.GDA` columns 6, 7 and 8 are the item ids a Chao grants at levels 1, 2 and 3 —
    Rugle is 99/139/179, which carry Luck +1, +2 and +3. This feature points the lower
    columns at the chosen tier, so a Chao hands over that tier's effects from the moment
    it hatches. **25 of the 45 Chao** have escalating stat tiers and gain outright; the
    other 20 are code-driven, with no stat rows to read, and are pointed at the same tier
    in case ARM9 scales its own effects by tier id — unverified, and harmless if not.
    Six Chao (Ferox, Pooki, Farfinkle, Baki, Stugs, Fimbley) already name one item for
    all three levels and are skipped.

    **Bepke is skipped**, because its tiers run GRT +15 / +10 / +5 and this code can only
    see the half of the trade that goes down. Its real effect is a taunt — "One enemy
    will automatically attack the bonded character instead of other team members" — and
    that side goes *up* with level, to two enemies and then three. So Max Bepke is less
    armour and a stronger taunt, which is a judgement call rather than an upgrade, and
    the safe default is to leave it alone. To force it anyway, override the two cells
    directly in a profile's `edits`:

        {"op": "gda_cell", "resource": "Chaos.GDA", "row": 34, "column": 6, "value": 205}
        {"op": "gda_cell", "resource": "Chaos.GDA", "row": 34, "column": 7, "value": 205}

    **The 20 code-driven Chao are the open question.** They do scale with level — Spartoi
    is +5% / +7.5% / +10% instant KO, Ovus revives once / twice / three times, Stebsly
    regenerates 5% / 8% / 10% — so the effect is not flat, it is just not in the table.
    What is unknown is whether ARM9 reads the **item id** in columns 6-8, which this
    feature rewrites, or the **stored level**, which it cannot touch. If the former, they
    come along for free; if the latter, the edit is inert for them.

    **Ovus settles it in one battle.** Its effect is a count, not a percentage: a level-1
    Ovus revives its bonded character once, a Max one three times. Equip it, die three
    times, and the answer is however many times you got up.

    The Chao's displayed level does not change — that is in the save, and this does not
    touch it. What changes is what the level you are stuck on is worth.

    Parameters: `level` (1-3, default 3).

    **Confirmed in game 2026-10-10.** Equipping a freshly hatched Level 1 Rugle took
    Sonic's Luck from 50 to **53** — the +3 of its Max tier, where vanilla grants +1.
    Note the garden and inventory panels draw a Chao's *description* and never its
    numbers, so the check has to be made on the character sheet.
    """
    level = int(params.get('level', 3))
    if not 1 <= level <= 3:
        raise ValueError('chao_level: level must be 1, 2 or 3, got %r' % level)
    source = (6, 7, 8)[level - 1]

    def weight(iid):
        """How much a tier is worth, as the total magnitude of its stat effects."""
        if not isinstance(iid, int) or iid < 0:
            return 0
        try:
            return sum(abs(d) for _, st, d in _itm_effects(b, _itm_res(b, iid))
                       if st in STAT_WORDS)
        except Exception:
            return 0

    cols, rows, K = _gda(b, 'Chaos.GDA')
    out = []
    for i, r in enumerate(rows):
        want = r[K[source]]
        if not isinstance(want, int) or want < 0:
            continue
        # **Levelling is not always an upgrade.** Bepke runs GRT +15 / +10 / +5, so its
        # "Max" tier is a third of what it grants on the day it hatches, and granting
        # tier 3 unconditionally would quietly nerf it. Nothing else in the table does
        # this, which is exactly why it would have gone unnoticed.
        if weight(want) < weight(r[K[6]]):
            continue
        for col in (6, 7, 8):
            if col == source:
                continue
            old = r[K[col]]
            if isinstance(old, int) and old >= 0 and old != want:
                out.append({'op': 'gda_cell', 'resource': 'Chaos.GDA',
                            'row': i, 'column': col, 'value': want})
    return out


@feature('randomize_chao', 'game')
def randomize_chao(params, b):
    """Re-roll Chao stat bonuses, and give the code-driven ones stats they never had.

    Tier item ids come from `Chaos.GDA` rather than the `N, N+40, N+80` spacing, for
    the reason spelled out on `custom_chao`: six species repeat one id in all three
    slots, and assuming the spacing would triple one species' effects.

    Two kinds of species, handled differently:

    * **Data-driven** Chao carry stat rows in their .ITM tables; those rows get
      re-rolled exactly as `randomize_items` re-rolls gear.
    * **Code-driven** Chao (~18 of them — Spartoi's instant KO, Ovus's revive, Ferox's
      free POW moves) carry nothing but boilerplate, because their behaviour is
      hardcoded in ARM9 and keyed by item id. That makes their tables *empty*, not
      off-limits: stat rows stack on top and the unique effect is untouched, which was
      confirmed in game on 2026-10-05 and is what `profiles/unique_chao_stats.json`
      does. `enrich_unique` (default true) gives each of them two random stats, growing
      across tiers by `unique_amounts` (default 4 / 8 / 12, the magnitudes that profile
      used). A single-tier species gets the top amount once.

    Descriptions are rewritten to match, at the **top tier**, because otherwise every
    Chao in a randomized run describes an effect it no longer has — and unlike gear you
    cannot check by equipping, since POW and GRT are never drawn on the character sheet.

    Parameters: `seed`, `scale`, `stats` as `randomize_items`, plus `enrich_unique`,
    `unique_amounts` and `describe`.

    **Untested in game**, though both halves rest on confirmed mechanisms.
    """
    import random
    rng = random.Random(int(params.get('seed', 0)))
    scale = tuple(params.get('scale', (0.5, 2.0)))
    stats = tuple(params.get('stats', ROLLABLE_STATS))
    enrich = bool(params.get('enrich_unique', True))
    amounts = list(params.get('unique_amounts', (4, 8, 12)))
    describe = bool(params.get('describe', True))

    cols, rows, K = _gda(b, 'Chaos.GDA')
    out = []
    for r in rows:
        ids = [r[K[c]] for c in (6, 7, 8)]
        ids = [i for i in ids if isinstance(i, int) and i >= 0]
        if not ids:
            continue
        tiers = list(dict.fromkeys(ids))          # de-duplicated, tier order preserved
        effects = {i: _itm_effects(b, _itm_res(b, i)) for i in tiers}
        final, keep_text = [], ''

        if any(effects.values()):
            for i in tiers:
                if not effects[i]:
                    continue
                res = _itm_res(b, i)
                rolled = _reroll_effects(rng, res, effects[i], scale, stats)
                out += rolled
                final = _applied_effects(effects[i], rolled, res)
        elif enrich:
            # Distinct stats, so the added rows get distinct labels ('POW+', 'LCK+')
            # and nothing collides inside one .ITM table.
            picks = rng.sample(list(stats), min(2, len(stats)))
            # A code-driven Chao's vanilla description describes its ARM9 effect, which
            # is still true after enrichment — Spartoi still instant-KOs. Replacing the
            # text would delete the only place that effect is written down, so the new
            # stats are appended to it instead.
            keep_text = _text(b, r[K[2]]).strip()
            for t, i in enumerate(tiers):
                amount = (amounts[-1] if len(tiers) == 1
                          else amounts[min(t, len(amounts) - 1)])
                out += _item_effect_rows(_itm_res(b, i),
                                         {s: amount for s in picks})
                final = [(s + '+', STATS[s], amount) for s in picks]
        else:
            continue

        if describe and final and _tlk_ok(b, r[K[2]]):
            text = _describe(final)
            if keep_text:
                text = '%s %s' % (keep_text.rstrip(), text)
            out.append({'op': 'chao_desc', 'item': ids[0], 'text': text})
    return out


@feature('randomize_shops', 'game')
def randomize_shops(params, b):
    """Shuffle shop stock, so what is for sale where stops being fixed.

    Default `pool` is `stocked`: the items already sold anywhere are redealt across
    all the shops, which keeps the total economy intact while moving late-game gear
    somewhere early (or the reverse). `pool: "all"` instead draws from every item in
    `Items.GDA`, which is wilder and can stock things the shops were never meant to
    sell — including Chao and quest items, so it is not the default.

    Prices stay with the **slot**, not the item, so a shop's cheap row stays cheap.
    That is what makes an early shop holding a strong item feel like a lucky find
    rather than a shop you cannot afford; `prices: "follow"` moves them with the item
    instead.

    Parameters: `seed`, `pool` (`stocked` | `all`), `prices` (`slot` | `follow`).

    Only the five real stock tables take part — see `_store_tables` for why
    `stores.GDA` must be kept out of it.

    **Confirmed in game 2026-10-10**: Central City's shop stocked Refresher Wave, Cure
    All Spray, Revival Ring and Titanium Claws where vanilla sells Health Seeds and POW
    Candy, at the vanilla prices for those slots.
    """
    import random
    rng = random.Random(int(params.get('seed', 0)))
    pool_mode = str(params.get('pool', 'stocked'))
    prices_follow = str(params.get('prices', 'slot')) == 'follow'

    slots = []          # (resource, row index, item, buy, sell)
    for name in _store_tables(b):
        try:
            cols, rows, K = _gda(b, name)
        except Exception:
            continue
        for i, r in enumerate(rows):
            item, buy, sell = r[K[1]], r[K[2]], r[K[3]]
            if isinstance(item, int) and item >= 0:
                slots.append([name, i, item, buy, sell])
    if not slots:
        return []

    if pool_mode == 'all':
        cols, rows, K = _gda(b, 'Items.GDA')
        pool = [r[K[0]] for r in rows if isinstance(r[K[0]], int) and r[K[0]] >= 0]
        deal = [(rng.choice(pool), None, None) for _ in slots]
    else:
        carried = [(s[2], s[3], s[4]) for s in slots]
        rng.shuffle(carried)
        deal = carried

    out = []
    for slot, (item, buy, sell) in zip(slots, deal):
        name, i, old_item, old_buy, old_sell = slot
        if item != old_item:
            out.append({'op': 'gda_cell', 'resource': name, 'row': i,
                        'column': 1, 'value': item})
        if prices_follow and buy is not None:
            if buy != old_buy:
                out.append({'op': 'gda_cell', 'resource': name, 'row': i,
                            'column': 2, 'value': buy})
            if sell != old_sell:
                out.append({'op': 'gda_cell', 'resource': name, 'row': i,
                            'column': 3, 'value': sell})
    return out



# --------------------------------------------------------------------------
# randomizer: chest loot and quest rewards
# --------------------------------------------------------------------------

#: RandItems.GDA is 22 weighted drop tables: column 0 is the id, then eight
#: (weight, item) pairs. Weights are percentages and sum to 100 on most rows, so the
#: item columns can be shuffled freely while the weights stay put and drop rates with
#: them. Rows 1-10 are the escalating generic chest tiers; the rest are quest-specific.
RI_ITEM_COLS = tuple(range(2, 17, 2))
#: rewards.GDA: 0 id, 1 a readable label ('Woodsman_Reward', 'Wasp Quest'),
#: 4 gold, 5 xp, 6-11 up to six item ids.
RW_LABEL, RW_GOLD, RW_XP = 1, 4, 5
RW_ITEM_COLS = tuple(range(6, 12))


def _store_tables(b):
    """The shop *stock* tables — `Store1.GDA` … `Store5.GDA`, and nothing else.

    A glob of `store*.gda` also catches **`stores.GDA`, which is not a shop**. It is the
    five-row registry *of* the shops: column 1 is a TLK strref for the shop's name
    (17425-17429) and column 2, where a stock table has a buy price, holds a background
    image filename (`store_1_bg.tga`). Treating it as stock let `randomize_shops` deal
    those five strrefs into the real shops as merchandise — the **blank rows priced 70
    and 35** in Central City's shop, reported in play 2026-10-10 — and deal real items
    back into the registry, where they would have become shop names and backdrops.

    The discriminator is the price column: a stock table's is an integer in every row.
    """
    out = []
    for name in sorted(n for n in b.herf.names.values()
                       if n.lower().startswith('store') and n.lower().endswith('.gda')):
        try:
            cols, rows, K = _gda(b, name)
        except Exception:
            continue
        if rows and all(isinstance(r[K[2]], int) for r in rows):
            out.append(name)
    return out


def _ordinary_items(b):
    """Item ids that are ordinary loot, and therefore safe to move between rewards.

    "Has a name" is not enough. Nameless ids (259-266, 270-275) are obviously quest
    tokens, but **Eggman Device and Pattern Generator are named** and are just as
    quest-critical — the first draft happily swapped the Eggman Device out of the
    `Eggman_parts` reward, which is the quest that needs it.

    The rule that holds instead: an item is ordinary if the game itself hands it out
    through an ordinary channel — sold in a shop, or dropped by one of the generic chest
    tiers (`RandItems.GDA` rows 1-10). Quest items appear only in specific reward rows
    and special drop tables, so they fall outside and never move. That is 62 items,
    fewer than the 230 in the table, and the cost of the missing variety is a class of
    softlock that cannot happen.
    """
    cols, rows, K = _gda(b, 'Items.GDA')
    named = {r[K[0]] for r in rows
             if isinstance(r[K[0]], int) and r[K[0]] >= 0 and _text(b, r[K[1]]).strip()}

    ok = set()
    for name in _store_tables(b):
        try:
            scols, srows, SK = _gda(b, name)
        except Exception:
            continue
        for r in srows:
            if isinstance(r[SK[1]], int) and r[SK[1]] >= 0:
                ok.add(r[SK[1]])

    rcols, rrows, RK = _gda(b, 'RandItems.GDA')
    for i, r in enumerate(rrows):
        if not 1 <= i <= 10:            # generic chest tiers only
            continue
        for c in RI_ITEM_COLS:
            if isinstance(r[RK[c]], int) and r[RK[c]] >= 0:
                ok.add(r[RK[c]])
    return ok & named


def _shuffle_slots(rng, slots, pool_mode, named, universe):
    """Redeal the item ids in `slots`, returning the new value for each.

    `slots` is a list of current ids. Nameless and empty (-1) entries are returned
    unchanged and never take part.
    """
    movable = [i for i, v in enumerate(slots) if v in named]
    if not movable:
        return list(slots)
    out = list(slots)
    if pool_mode == 'all':
        for i in movable:
            out[i] = rng.choice(universe)
    else:
        carried = [slots[i] for i in movable]
        rng.shuffle(carried)
        for i, v in zip(movable, carried):
            out[i] = v
    return out


@feature('randomize_drops', 'game')
def randomize_drops(params, b):
    """Redeal the weighted drop tables, keeping the rates.

    `RandItems.GDA` is 22 weighted tables of eight (weight, item) pairs: rows 1-10 are an
    escalating generic tier, 11-21 are quest-specific.

    **Whether these feed chests is an open question.** A playtest seemed to rule it out —
    Health Seed was emptied from every early tier and the first chest still gave one —
    but `areas.GDA` **column 61** was later found to track the section exactly for every
    chest-bearing area (a1_s1 -> 1, a1_s2 -> 2, a1_s5 -> 5, a1_s6 -> 6, a2_s4 -> 8), which
    is precisely the shape of a per-area tier index into this table, and row 1 is 25%
    Health Seed. Both cannot be right. `profiles/chest_probe.json` settles it by setting
    every row to 100% of one unmistakable item.

    Only the item columns move; the weight beside each one stays, so a 35/35/10/10/10
    table still pays out 35/35/10/10/10. `pool` defaults to `stocked` (redeal the items
    already in the tables) rather than `all` (draw from every named item), because
    `stocked` keeps early chests holding early-game quantities.

    Nameless quest tokens never move — see `_named_items`.

    Parameters: `seed`, `pool` (`stocked` | `all`).

    **Confirmed in game 2026-10-10.** An Immunity Booster dropped in chapter 1, where it
    cannot: vanilla stocks it in table 19 alone, a late one, and seed 1 moves it into
    table 3, an early generic tier.
    """
    import random
    rng = random.Random(int(params.get('seed', 0)))
    pool_mode = str(params.get('pool', 'stocked'))
    named = _ordinary_items(b)
    universe = sorted(named)

    cols, rows, K = _gda(b, 'RandItems.GDA')
    flat = [[r[K[j]] for j in range(len(cols))] for r in rows]

    slots, where = [], []
    for ri, row in enumerate(flat):
        for c in RI_ITEM_COLS:
            slots.append(row[c])
            where.append((ri, c))
    new = _shuffle_slots(rng, slots, pool_mode, named, universe)

    return [{'op': 'gda_cell', 'resource': 'RandItems.GDA', 'row': ri,
             'column': c, 'value': v}
            for (ri, c), old, v in zip(where, slots, new) if v != old]


@feature('randomize_rewards', 'game')
def randomize_rewards(params, b):
    """Redeal quest and event rewards, and optionally scale their XP and gold.

    `rewards.GDA` is 70 rows carrying a readable label, gold, XP and up to six item ids
    — `Woodsman_Reward` is 50 XP and a POW Candy, which is what the wood-chopping
    mission pays. Items move between rewards; nameless quest tokens never do, so
    `Eggman_parts` still hands over the parts that quest needs.

    `xp_scale` and `gold_scale` multiply those columns (default 1.0, i.e. untouched).

    Parameters: `seed`, `pool` (`stocked` | `all`), `xp_scale`, `gold_scale`.

    **Untested in game.**
    """
    import random
    rng = random.Random(int(params.get('seed', 0)))
    pool_mode = str(params.get('pool', 'stocked'))
    xp_scale = float(params.get('xp_scale', 1.0))
    gold_scale = float(params.get('gold_scale', 1.0))
    named = _ordinary_items(b)
    universe = sorted(named)

    cols, rows, K = _gda(b, 'rewards.GDA')
    flat = [[r[K[j]] for j in range(len(cols))] for r in rows]

    slots, where = [], []
    for ri, row in enumerate(flat):
        for c in RW_ITEM_COLS:
            slots.append(row[c])
            where.append((ri, c))
    new = _shuffle_slots(rng, slots, pool_mode, named, universe)

    out = [{'op': 'gda_cell', 'resource': 'rewards.GDA', 'row': ri,
            'column': c, 'value': v}
           for (ri, c), old, v in zip(where, slots, new) if v != old]

    for col, scale in ((RW_XP, xp_scale), (RW_GOLD, gold_scale)):
        if scale == 1.0:
            continue
        for ri, row in enumerate(flat):
            old = row[col]
            if not isinstance(old, int) or old <= 0:
                continue
            v = max(1, int(round(old * scale)))
            if v != old:
                out.append({'op': 'gda_cell', 'resource': 'rewards.GDA',
                            'row': ri, 'column': col, 'value': v})
    return out



# --------------------------------------------------------------------------
# randomizer: what is placed in the world
# --------------------------------------------------------------------------

def _modelless_creatures(b):
    """Creature rows whose appearance has no model — placing one black-screens a battle.

    `appearances.GDA` column 3 is the model prefix, and rows 0, 4 and 72 have none.
    Appearance 4 belongs to the playable-character duel variants (creature rows 75, 77
    and 116), whose models load through a different path than enemy ones, leaving their
    appearance row an empty shell.

    **Every feature that can put a creature somewhere new must consult this**, and the
    obvious filters do not cover it: those rows carry `playerid = -1` so the party check
    misses them, and they are named "Shadow the Hedgehog" so no boss list catches them.
    This is shared rather than inlined because it has now caused the same hang twice —
    first through `randomize_encounters` donating appearance 4 to a Marauder (2026-10-08),
    then through `randomize_placements` moving squad 51 into an ordinary Green Hill
    spawn point (2026-10-10), where the fight loaded with no enemy in it.
    """
    acols, arows, AK = _gda(b, 'appearances.GDA')
    with_model = {i for i, r in enumerate(arows)
                  if isinstance(r[AK[3]], str) and r[AK[3]] not in ('', 'None')}
    cols, rows, K = _gda(b, 'creatures.GDA')
    return {i for i, r in enumerate(rows) if r[K[CR_APPEARANCE]] not in with_model}


def _are_names(b):
    return sorted(n for n in b.herf.names.values() if n.lower().endswith('.are'))


@feature('randomize_chests', 'game')
def randomize_chests(params, b):
    """Redeal what the world's 53 chests hold.

    A chest is a **placeable of type 6** in the area's list 40001, and its contents are
    the three float32 parameters at fields 40020/40021/40022 - `Items.GDA` ids, -1 for an
    empty slot. 159 slots in all, of which 120 are filled.

    This replaces a documented dead end. The project spent a day concluding that chest
    contents lived in ARM9, because the search looked at list 40002 (the `kind == 4`
    item *objects*), at `RandItems.GDA`, and at the plot files, and found nothing that
    could be a chest. The triple was dismissed early as a position. It is not: the
    position is the vector3f at label 4, and the 1,035 rings in the game share exactly
    two distinct triples between them, which no coordinate ever would.

    What settles it is that the ids read as loot. Green Hill's five chests hold Health
    Seeds, POW Candy, Prune Juice and Boxing Gloves; the first one is a lone Health Seed,
    which is exactly what every playtest reported finding in it. The five single-slot
    chests scattered through Act 2 hold the five Nocturne Relics. And the developers'
    own `jay_test` area has five chests of three Health Seeds each - item id 0, three
    times over, which is what a placeholder looks like from the inside.

    Only **ordinary loot** moves, the same rule the other redeals use, so the Nocturne
    Relics and the Voxai Teleporter stay exactly where the quests that need them expect.

    Nothing resizes: each slot is a float32 at a fixed offset, written in place.

    Parameters: `seed`, `pool` (`placed` redeals what the chests already hold, the
    default; `all` draws from every ordinary item).

    **Confirmed in game 2026-10-10**: a fresh save on `world_randomizer_test.nds`, and
    Green Hill's first chest handed over a Cure All Spray instead of its Health Seed.
    """
    import random
    rng = random.Random(int(params.get('seed', 0)))
    pool_mode = str(params.get('pool', 'placed'))
    ordinary = _ordinary_items(b)
    universe = sorted(ordinary)
    if not universe:
        return []

    import are_write
    where, slots = [], []
    for res in _are_names(b):
        for index, items in are_write.chest_placements(b.herf.read(b.resource(res))):
            for n, item in enumerate(items):
                where.append((res, index, are_write.F_SLOTS[n]))
                slots.append(item)

    new = _shuffle_slots(rng, slots, pool_mode, ordinary, universe)
    return [{'op': 'are_cell', 'resource': res, 'list': are_write.L_PLACEABLES,
             'index': index, 'field': field, 'value': v}
            for (res, index, field), old, v in zip(where, slots, new) if v != old]


# `randomize_pickups` was removed on 2026-10-10. It rewrote field 40009 of the
# `kind == 4` entries in area list 40002, believing them to be item pickups because every
# payload happened to land inside the `Items.GDA` id range. Resolving the plot flag at
# field 40013 showed what that list really is: a **plot-event trigger table**. In the
# opening area alone it holds the four frogs of the Froggy side quest (kind 23, gated on
# `FROGGY_QUEST_ACCEPTED`), the three animation events of the bridge puzzle (kind 29,
# `GREEN_HILLS_BRIDGE_PUZZLE_COMPLETE`) and the three projectors of the scientist's quest
# (kind 4, `PROJECTOR_QUEST_GIVEN`) — which is what the "three Voxai Teleporters lying in
# Green Hill" really were. The payload is not an item id, the feature never had a visible
# effect, and writing to it could break a side quest. Chests are randomized by
# `randomize_chests`, which edits a field whose meaning is established.

@feature('randomize_placements', 'game')
def randomize_placements(params, b):
    """Move enemy groups around: which squad spawns at which point.

    This is the other half of an encounter randomizer. `randomize_encounters` changes
    *what a species is*; this changes *where a group stands*. Spawn points live in the
    area's own list at label 40003, one integer per point naming a `squads.GDA` row.

    Shuffling is **banded by difficulty**, because a squad carries its members' stats
    with it and an unbanded shuffle is just a way to put a level-20 Gizoid Guardian in
    Green Hill. A squad's band is the highest level among its members, and squads only
    trade places within a band, so an area stays roughly as hard as it was.

    Three things never move. **Tagged spawn points** (`are_write.F_TAG`) are addressed by
    name from plot scripts — 13 of 54 in the opening area, the tutorial fight among them —
    and moving a squad out of one leaves the battle with no enemy in it. Squads containing
    a **protected creature** — bosses, the curated list, or a creature with no model —
    stay put, so story fights keep their cast. And **single-member squads** stay put
    whether or not they are tagged, because a lone enemy is always a story actor; the
    Green Hill Marauder is one and carries no tag, and moving it stranded a run.

    Parameters: `seed`, `band` (level width of a band, default 3).

    **Confirmed in game 2026-10-10**, on the third attempt. Groups move and banding holds
    - a Queen Wasp pack displaced into Green Hill at level 5 - and with the solo-squad
    rule in place the story spawns survive: the Marauder chase is a Marauder again.
    """
    import random
    import collections
    rng = random.Random(int(params.get('seed', 0)))
    band = max(1, int(params.get('band', 3)))

    cols, rows, K = _gda(b, 'creatures.GDA')
    scols, srows, SK = _gda(b, 'squads.GDA')
    extra = {int(x) for x in params.get('protect', [])}
    modelless = _modelless_creatures(b)

    def protected_creature(i):
        r = rows[i]
        if i in extra or r[K[CR_PLAYERID]] != -1 or i in modelless:
            return True
        if (r[K[CR_LEVEL]], r[K[CR_HP]], r[K[CR_POW]], r[K[CR_DEF]]) == NPC_STATLINE:
            return True
        return any(p in _text(b, r[K[CR_NAME]]).lower() for p in PROTECTED_NAMES)

    def squad_band(si):
        members = [srows[si][SK[c]] for c in (5, 6, 7, 8)]
        live = [m for m in members if isinstance(m, int) and 0 <= m < len(rows)]
        if not live or any(protected_creature(m) for m in live):
            return None
        # A squad of ONE is a story actor, not roaming trash, and must not move.
        # Of the 25 single-member squads actually placed in the world, 21 are
        # script-tagged and read like a cast list: Shadow, Imperator Ix, Shade, General
        # Raxos, the Gentleman, Prefect Scylla and Charyb, Dragodon, the Colossal Worm.
        # The remaining four are the same characters again in the battle arena, plus the
        # lone **Marauder Scout** of squad 264 - the Green Hill chase, placed twice in
        # `a1_s1_ex` with *no* tag on either point. Moving it left the encounter with
        # nothing in it and the run unable to progress to Central City (reported
        # 2026-10-10). Roaming trash travels in threes and fours; a solitary enemy is a
        # set piece, so size is the signal that a missing tag does not give.
        if len(live) < 2:
            return None
        levels = [rows[m][K[CR_LEVEL]] for m in live]
        levels = [l for l in levels if isinstance(l, int) and l >= 1]
        if not levels:
            return None
        return max(levels) // band

    import are_write
    slots = []
    for res in _are_names(b):
        raw = b.herf.read(b.resource(res))
        try:
            # Script-referenced spawn points are left exactly where they are. A plot
            # that drives a specific encounter addresses it by tag, and moving the squad
            # out from under one starts the battle with no enemy in it — the tutorial
            # armadillo fight in the opening area is tagged, and randomizing it left the
            # player standing in an empty arena (reported twice, 2026-10-10).
            points = are_write.squad_placements(raw, include_tagged=False)
        except KeyError:
            continue
        for index, sid in points:
            if isinstance(sid, int) and 0 <= sid < len(srows):
                slots.append([res, index, sid])

    by_band = collections.defaultdict(list)
    for n, (res, index, sid) in enumerate(slots):
        bd = squad_band(sid)
        if bd is not None:
            by_band[bd].append(n)

    out = []
    for bd, idxs in sorted(by_band.items()):
        if len(idxs) < 2:
            continue
        ids = [slots[n][2] for n in idxs]
        rng.shuffle(ids)
        for n, new in zip(idxs, ids):
            res, index, old = slots[n]
            if new != old:
                out.append({'op': 'are_cell', 'resource': res,
                            'list': are_write.L_SQUADS, 'index': index,
                            'field': are_write.F_SQUAD, 'value': new})
    return out

# --------------------------------------------------------------------------
# POW moves
# --------------------------------------------------------------------------

@feature('pow_move', 'game')
def pow_move(params, b):
    """Retune a POW move: cost, damage tiers, solo conversion, element, flags.

    `solo: true` sets participants to 1 and clears the partner slots, which frees
    a move from needing party members the run may never have.

    The per-tier effect text in the UI is **authored, not generated** — changing
    damage or element here does not update what the move says it does. Pass
    `tier_text` to keep the description honest.
    
    **`whole_team` was discovered late and is why this function changed on 2026-10-10.**
    Column 52 is "hits the whole opposing team" (all twenty vanilla moves that set it say
    so in their own description), and this feature used to set it **as a side effect of
    changing an element** - on the theory that it was an "element flag", which it is not.
    So asking for an elemental Metal Storm also, silently, made Metal Storm hit everybody.
    It is now its own parameter, and `blast` writes column 48, which is splash: a primary
    target at full damage and the rest reduced, as the transplanted Hellfire showed. The
    two are exclusive in all 155 vanilla rows, so setting `whole_team` clears splash.

    One consequence worth stating plainly: the "Metal Storm + earth works" result was
    obtained on a build that *also* made Metal Storm whole-team, so that playtest does not
    cleanly isolate the element. `profiles/example_features.json` now passes
    `whole_team: true` explicitly, so it still reproduces the configuration that was
    actually verified rather than a new, untested one.
"""
    out = []
    cols, rows, K = _gda(b, 'combo.GDA')
    for spec in (params if isinstance(params, list) else [params]):
        _need(spec, 'move')
        row = int(spec['move'])
        if not 0 <= row < len(rows):
            raise ValueError('combo.GDA has no row %d' % row)
        r = rows[row]

        def cell(col, val):
            out.append({'op': 'gda_cell', 'resource': 'combo.GDA',
                        'row': row, 'column': col, 'value': val})
        if spec.get('solo'):
            cell(C_PARTICIPANTS, 1)
            for p in C_PARTNERS:
                if r[K[p]] != -1:
                    cell(p, -1)
        if 'cost' in spec:
            cell(C_COST, int(spec['cost']))
        if 'damage' in spec:
            dmg = spec['damage']
            if len(dmg) != 3:
                raise ValueError('damage needs 3 tier values, got %d' % len(dmg))
            for col, v in zip(C_DMG, dmg):
                cell(col, int(v))
        # Status is applied BEFORE the element, because the element guard tests the
        # pair and must see the status this build is actually giving the move, not the
        # one it is replacing.
        status_cols = None
        if 'status' in spec:
            st = str(spec['status']).lower()
            if st not in MOVE_STATUSES:
                raise ValueError('unknown status %r; known: %s'
                                 % (spec['status'], sorted(MOVE_STATUSES)))
            status_cols = MOVE_STATUSES[st]
            for col, value in zip(C_STATUS_TIERS, status_cols):
                if r[K[col]] != value:
                    cell(col, value)

        if 'element' in spec:
            el = str(spec['element']).lower()
            if el not in MOVE_ELEMENTS:
                raise ValueError(
                    'unknown move element %r; confirmed: %s. (water and ice are '
                    'presumed to be bits 18 and 22 but appear nowhere in vanilla, '
                    'so they are not offered as known values.)'
                    % (spec['element'], sorted(MOVE_ELEMENTS)))
            value = MOVE_ELEMENTS[el]
            vanilla_element = r[K[C_ELEMENT]]
            vanilla_element = vanilla_element if isinstance(vanilla_element, int) else 0
            if not spec.get('force_element') and vanilla_element == 0:
                raise ValueError(
                    'move %d ships with no element, and giving one to a move that lacks '
                    'it crashes the battle on some moves and not others, with nothing in '
                    'combo.GDA predicting which. Focus Field + wind hard-crashed twice, '
                    'under two different status effects; Metal Storm + earth works and we '
                    'cannot explain why. Change the element of a move that already has '
                    'one, or pass force_element and test that specific move before '
                    'playing a run on it.' % row)
            cell(C_ELEMENT, value)
        if 'cant_miss' in spec:
            cell(C_CANTMISS, 1 if spec['cant_miss'] else 0)
        if 'blast' in spec:
            cell(C_SPLASH, 1 if spec['blast'] else 0)
        if 'whole_team' in spec:
            # Exclusive with splash in all 155 vanilla rows, so setting one clears the
            # other rather than trusting a profile to keep them consistent.
            on = bool(spec['whole_team'])
            cell(C_WHOLE_TEAM, 1 if on else 0)
            if on and r[K[C_SPLASH]]:
                cell(C_SPLASH, 0)
        if 'name' in spec:
            out.append({'op': 'tlk_string', 'id': r[K[34]], 'text': spec['name']})
        if 'description' in spec:
            out.append({'op': 'tlk_string', 'id': r[K[35]],
                        'text': spec['description']})
        for tier, text in enumerate(spec.get('tier_text', [])):
            out.append({'op': 'tlk_string', 'id': r[K[37 + tier * 2]], 'text': text})
    return out


# --------------------------------------------------------------------------

def expand(features, b):
    """Expand a profile's `features` block into ordinary edits."""
    edits, summary = [], []
    for name, params in features.items():
        fn = REGISTRY.get(name)
        if fn is None:
            raise ValueError('unknown feature %r; available: %s'
                             % (name, ', '.join(sorted(REGISTRY))))
        produced = fn(params, b)
        edits += produced
        summary.append((name, CONFIRMED[name], len(produced)))
    return edits, summary
