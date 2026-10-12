"""
Read-only view of a ROM, for the GUI to show what a character currently has.

Kept separate from the GUI so the window stays a form and the parsing stays with
the rest of the tooling. Nothing here writes; edits are produced as ordinary
feature entries by the GUI and applied by modbuild.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'build'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'recon'))

from rom_build import Rom              # noqa: E402
from herf_write import HerfFile        # noqa: E402
from tlk_write import TlkFile          # noqa: E402
from gff4 import GFF4, read_gda        # noqa: E402
import features                        # noqa: E402

CR_NAME, CR_ADV = 1, 34
CR_SLOTS = (19, 20, 21)                # three movement slots
CR_MOVES = (22, 23, 24, 25, 26, 27)    # six POW move slots
CB_PARTICIPANTS, CB_OWNER, CB_COST, CB_ELEMENT, CB_NAME = 1, 2, 11, 51, 34
MV_ID, MV_MAXLEVEL, MV_NAME = 0, 10, 11


class GameData:
    def __init__(self, rom_path):
        rom = Rom(open(rom_path, 'rb').read())
        self.herf = HerfFile(rom.file_bytes(rom.file_id('/test.herf')))
        self.tlk = TlkFile(rom.file_bytes(rom.file_id('/strings.tlk')))
        self.creatures = self._gda('creatures.GDA')
        self.combo = self._gda('combo.GDA')
        self.movement = self._gda('movement.GDA')
        self.items_tbl = self._gda('Items.GDA')
        self.chaos_tbl = self._gda('Chaos.GDA')
        self.stores_tbl = self._gda('stores.GDA')

    def _gda(self, name):
        key = {n.lower(): n for n in self.herf.names.values()}[name.lower()]
        cols, rows = read_gda(GFF4(self.herf.read(key)))
        K = sorted(rows[0].keys())
        return [[r[K[j]] for j in range(len(cols))] for r in rows]

    def text(self, ref):
        try:
            return self.tlk.get_string(self.tlk.index_of_id(ref)) or ''
        except Exception:
            return ''

    # --- what the GUI asks for -------------------------------------------

    def abilities(self):
        """ability id -> (name, maxlevel)"""
        return {r[MV_ID]: (self.text(r[MV_NAME]) or 'id %s' % r[MV_ID], r[MV_MAXLEVEL])
                for r in self.movement}

    def playable(self):
        """[(creature row, display name, Adv table name)] for rows with a progression table."""
        out = []
        for i, r in enumerate(self.creatures):
            adv = r[CR_ADV]
            if not isinstance(adv, str) or not adv.startswith('Adv_'):
                continue
            if 'VFXTester' in adv:
                continue
            name = self.text(r[CR_NAME]) or adv.replace('Adv_', '')
            out.append((i, name, adv))
        # keep the first row per progression table: the party member, not boss variants
        seen, uniq = set(), []
        for row, name, adv in out:
            if adv in seen:
                continue
            seen.add(adv)
            uniq.append((row, name, adv))
        return uniq

    def slots_of(self, crow):
        """[(slot number, ability id or -1, ability name)] for a creature."""
        ab = self.abilities()
        out = []
        for n, col in enumerate(CR_SLOTS, start=1):
            aid = self.creatures[crow][col]
            out.append((n, aid, ab.get(aid, ('empty', 0))[0] if aid != -1 else 'empty'))
        return out

    def moves_of(self, crow):
        """[(combo row, name, cost, participants, element name)] for a creature."""
        inv = {v: k for k, v in features.MOVE_ELEMENTS.items()}
        out = []
        for col in CR_MOVES:
            idx = self.creatures[crow][col]
            if not isinstance(idx, int) or not (0 <= idx < len(self.combo)):
                continue
            m = self.combo[idx]
            out.append((idx, self.text(m[CB_NAME]) or 'row %d' % idx,
                        m[CB_COST], m[CB_PARTICIPANTS],
                        inv.get(m[CB_ELEMENT], '')))
        return out


# Items.GDA columns: 0 id, 1 name strref, 5 .ITM file, 10 icon sprite PREFIX,
# 14 palette. The icon on the .ITM row itself is a generic placeholder shared by
# almost every item (138 of 139 use ICN_S_MEDKIT), so the real per-item art is the
# prefix here, resolved as "<prefix>0.NCGR.small".
IT_ID, IT_NAME, IT_FILE, IT_ICON, IT_PAL = 0, 1, 5, 10, 14
# Chaos.GDA: 1 species name strref, 6/7/8 the three growth-tier item ids
CH_NAME, CH_TIERS = 1, (6, 7, 8)
ST_NAME = 1


def _item_icon(row):
    """(sprite prefix, palette resource) — the icon is FOUR resources, not one.

    Each item's art is split into `<prefix>0..3`, four 64x64 quadrants forming a
    128x128 picture. The prefix is returned rather than a single resource name so
    the caller assembles all four; rendering only `<prefix>0` shows the top-left
    corner, which reads as a fragment of unrelated art rather than an obviously
    missing piece.
    """
    pre, pal = row[IT_ICON], row[IT_PAL]
    if not isinstance(pre, str) or pre in ('', 'None'):
        return None, None
    if not isinstance(pal, str) or pal in ('', 'None'):
        return None, None
    return pre, pal + '.small'


def _items(self):
    """[(id, name, icon resource or None, palette or None)] sorted by id."""
    out = []
    for r in self.items_tbl:
        name = self.text(r[IT_NAME])
        if not name:
            continue
        ncgr, nclr = _item_icon(r)
        out.append((r[IT_ID], name, ncgr, nclr))
    return sorted(out)


CH_DESC = 2
_BOILERPLATE = {'SpellData', 'CollectionData_Equip', 'CollectionData_Use'}


def _chao(self):
    """[(base item id, species name)] — one entry per species, lowest tier."""
    return sorted({(iid, nm) for iid, nm, _, _ in self.chao_detail()})


def _chao_detail(self):
    """[(item id, name, description, unique)] where `unique` means CODE-driven.

    A Chao's effect is either rows in its own .ITM table (stat boosts, elements —
    editable) or hardcoded in ARM9 and keyed by item id (instant KO, auto-revive,
    auto-succeed — not editable, and its odds are code constants). The two are
    distinguishable from the data: a code-driven Chao's item table holds nothing but
    boilerplate, while a data-driven one carries real effect rows. 18 are code-driven.

    Such a slot can still be repurposed — renaming and restatting it keeps the
    unique effect, because the effect follows the id, not the name.
    """
    import twoda
    rmap = {n.lower(): n for n in self.herf.names.values()}
    out = []
    for r in self.chaos_tbl:
        name, desc = self.text(r[CH_NAME]), self.text(r[CH_DESC])
        ids = [r[c] for c in CH_TIERS if isinstance(r[c], int) and r[c] >= 0]
        if not (name and ids):
            continue
        iid = min(ids)
        # Check ALL three tiers, not just one: a species counts as code-driven only
        # when every tier's table is boilerplate. Sampling a single tier misclassified
        # two species (giving 20 instead of 18). No species is mixed, so this is
        # unambiguous once all three are read.
        rows = []
        for t in ids:
            key = rmap.get('item%d.itm' % t)
            if not key:
                continue
            try:
                rows += [l for l in twoda.parse_2da(self.herf.read(key)).labels
                         if l not in _BOILERPLATE]
            except Exception:
                pass
        out.append((iid, name, desc, not rows))
    return sorted(set(out))


def _shops(self):
    """[(shop number, place name)] — Store1..Store5 are real locations."""
    return [(i + 1, self.text(r[ST_NAME]) or 'Store%d' % (i + 1))
            for i, r in enumerate(self.stores_tbl)]


GameData.items = _items
GameData.chao = _chao
GameData.chao_detail = _chao_detail
GameData.shops = _shops


#: Where each stat's *starting* value lives on the creature row, for display. `fatigue`
#: is here as column 11 although `stat_curve` refuses to write it - PP's base belongs to
#: `pp_curve` - because a stat row that cannot show where it starts is worse than one
#: that shows a number it does not own.
_START_COL = dict(features.CR_START_STATS, fatigue=(11,))


def _stats_of(self, adv, crow):
    """[(stat, at level 1, at level 30, growth)] - the numbers a character will HAVE.

    **Not the progression table's cells.** The table holds *increments*, confirmed in
    game 2026-10-12:

        stat at level L  =  creatures.GDA base  +  (table[L] - table[1])

    An earlier version of this printed `table[1]` and `table[30]` straight out and
    called them "at lv1" and "at lv30". In vanilla that is right by coincidence, because
    the creature row and the table's first line carry the same seven numbers - which is
    exactly why the increment rule stayed hidden for so long. The moment anything edits
    either one they diverge, and the display was then confidently wrong in a form that
    looked authoritative. So the level-1 figure now comes from the creature row, and the
    level-30 figure is that base plus the growth the table actually describes.
    """
    # `playable` yields the table as the creature row stores it - "Adv_Sonic",
    # with no extension - while the archive names it "Adv_Sonic.GDA".
    if not adv.lower().endswith('.gda'):
        adv += '.GDA'
    rows = self._gda(adv)          # already flattened to [row][column]
    out = []
    for name, col in sorted(features.ADV_STATS.items(), key=lambda kv: kv[1]):
        first = rows[0][col] if rows else 0
        last = rows[min(29, len(rows) - 1)][col] if rows else 0
        growth = last - first
        base = self.creatures[crow][_START_COL[name][0]]
        if not isinstance(base, int):
            base = first
        out.append((name, base, base + growth, growth))
    return out


GameData.stats_of = _stats_of
