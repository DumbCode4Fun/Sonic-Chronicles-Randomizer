"""
Sonic Chronicles Mod Pack Maker — the GUI front end.

Per CLAUDE.md this contains **no reverse-engineering logic**. It is a form over the
same feature registry and profile format the CLI uses: it reads `features.REGISTRY`
to discover what exists, reads the ROM through `gamedata` only to *show* current
values, writes a profile JSON, and shells out to `modbuild.py`. Anything it can
build, the CLI builds from the same file.

    py tools/gui/modpack_maker.py

Three tabs:
  Characters  pick a character, then edit their three ability slots and six POW
              moves against what the ROM currently has
  Game        whole-game settings (level cap, scaling, progression curves)
  Items       items, Chao and shop stock, as editable lists
"""
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'build'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'recon'))
sys.path.insert(0, HERE)

import features        # noqa: E402
from gamedata import GameData  # noqa: E402
import icons as iconlib       # noqa: E402

#: Pre-fills the ROM picker so the common case is one click instead of a file dialog.
#: Set SONIC_CHRONICLES_ROM in the environment to point it at your own dump; the project
#: never ships a ROM and never writes to the one you choose.
DEFAULT_ROM = os.environ.get('SONIC_CHRONICLES_ROM', '')

STATS = ['', 'POW', 'ATK', 'DEF', 'SPD', 'GRT', 'LCK', 'MAXHP', 'MAXPP']
ELEMENTS = ['', 'fire', 'water', 'earth', 'wind', 'lightning', 'ice']
MOVE_ELEMENTS = ['(unchanged)'] + sorted(features.MOVE_ELEMENTS)

GAME_FIELDS = {
    'level_cap': [
        ('cap', 'Maximum level', 'int', 50, 'Vanilla is 30.'),
        ('xp_per_level', 'XP per level', 'int', 20000, 'Thresholds flatten to this step.'),
    ],
    'enemy_scaling': [
        ('hp_per_level', 'HP per enemy level', 'float', 0.08,
         'The safe lever: longer fights, damage numbers unchanged.'),
        ('pow_per_level', 'Damage per enemy level', 'float', 0.035,
         'POW is damage dealt (confirmed). Felt directly.'),
        ('grt_per_level', 'Grit per enemy level', 'float', 0.0,
         'GRT is damage reduction. Raising it shrinks YOUR numbers.'),
        ('def_per_level', 'Defense per enemy level', 'float', 0.0,
         'Probably evasion, so this makes you miss. Leave at 0.'),
    ],
    'pp_curve': [
        ('character', 'Progression table', 'char', 'Shadow', ''),
        ('creature', 'Creature row', 'int', 0, 'Explicit when a swap reassigns tables.'),
        ('base', 'Base PP', 'int', 11, 'PP = this + accumulated per-level increments.'),
        ('per_level', 'Extra PP per level', 'float', 0.4, ''),
    ],
    'xp_curve': [
        ('character', 'Character', 'char', 'Shadow', ''),
        ('copy_from', 'Copy thresholds from', 'char', 'Sonic',
         'Mid-game joiners carry curves assuming a head start.'),
    ],
    'stat_curve': [
        ('character', 'Character', 'char', 'Shadow', ''),
        ('stat', 'Stat', 'choice:speed,attack,defense,hp,power,grit,luck,fatigue',
         'power', 'power = damage, grit = armor; both hidden from the game UI.'),
        ('multiplier', 'Multiplier', 'float', 1.15, ''),
        ('bonus', 'Flat bonus', 'int', 0, ''),
    ],
    'chao_level': [
        ('level', 'Grant tier', 'int', 3,
         'A solo player cannot level a Chao past 1; this grants tier 3 anyway.'),
    ],
    'randomize_characters': [
        ('seed', 'Seed', 'int', 1, ''),
        ('moves', 'Deal POW moves across cast', 'bool', False,
         "A move's name, damage, cost and status effect all travel; its animation, "
         'clicks and hit count belong to the character and slot and stay put. So a '
         "borrowed move plays as the holder's own move. Opt-in for that reason."),
        ('stats', 'Shuffle stat lines', 'bool', True,
         'Whole lines across all 30 levels, so nobody gains a bigger budget.'),
        ('recruitment', 'Shuffle recruitment order', 'bool', False,
         'Who each story point hands you. Movement abilities stay with the slot, '
         'so no gate can become impassable.'),
    ],
    'randomize_encounters': [
        ('seed', 'Seed', 'int', 1, 'Same seed, same run.'),
        ('mode', 'Mode', 'choice:reskin,transplant', 'reskin',
         'transplant brings the donor moves and abilities, scaled to the slot.'),
        ('damage_scale', 'Move damage x', 'float', 1.0,
         'Transplant only. 1.0 keeps vanilla multipliers.'),
        ('pow_floor', 'POW floor for new moves', 'bool', True,
         'Transplant only. A creature handed a move gets the POW to swing it.'),
        ('pow_scale', 'POW floor x', 'float', 1.0,
         'Transplant only. Raises the floor further; never past the donor.'),
        ('include_bosses', 'Also reskin bosses', 'bool', False,
         'A boss keeps its squad, stats and trigger either way.'),
    ],
    'randomize_items': [
        ('seed', 'Seed', 'int', 1, ''),
        ('scale', 'Magnitude range', 'range', '0.5, 2.0',
         'Multiplies the vanilla amount, so the item curve survives.'),
        ('describe', 'Rewrite descriptions', 'bool', True,
         'Off leaves every description describing the old effect.'),
    ],
    'randomize_chao': [
        ('seed', 'Seed', 'int', 1, ''),
        ('scale', 'Magnitude range', 'range', '0.5, 2.0', ''),
        ('enrich_unique', 'Stats on unique Chao', 'bool', True,
         'Spartoi and friends keep their ARM9 effect and gain stats on top.'),
        ('unique_amounts', 'Unique amounts by tier', 'range3', '4, 8, 12',
         'Bonus at growth tiers 1 / 2 / 3.'),
        ('describe', 'Rewrite descriptions', 'bool', True,
         'Unique effects keep their text; the stats are appended.'),
    ],
    'randomize_shops': [
        ('seed', 'Seed', 'int', 1, ''),
        ('pool', 'Draw from', 'choice:stocked,all', 'stocked',
         '"all" can stock Chao and quest items.'),
        ('prices', 'Prices stay with', 'choice:slot,follow', 'slot',
         '"slot" keeps a cheap row cheap, so early finds are affordable.'),
    ],
    'randomize_drops': [
        ('seed', 'Seed', 'int', 1, ''),
        ('pool', 'Draw from', 'choice:stocked,all', 'stocked',
         'Weighted drop tables. Rates never change, only the items.'),
    ],
    'randomize_chests': [
        ('seed', 'Seed', 'int', 1, ''),
        ('pool', 'Draw from', 'choice:placed,all', 'placed',
         'All 53 chests. Quest tokens and the Nocturne Relics stay put.'),
    ],
    'randomize_placements': [
        ('seed', 'Seed', 'int', 1, ''),
        ('band', 'Difficulty band', 'int', 3,
         'Groups only swap within this many levels, so areas stay fair.'),
    ],
    'randomize_rewards': [
        ('seed', 'Seed', 'int', 1, ''),
        ('pool', 'Draw from', 'choice:stocked,all', 'stocked',
         'Quest items are frozen, so no quest can be made uncompletable.'),
        ('xp_scale', 'XP multiplier', 'float', 1.0, '1.0 leaves XP alone.'),
        ('gold_scale', 'Gold multiplier', 'float', 1.0, ''),
    ],
}

#: which features each parameter tab renders; the schema above is shared
GAME_TAB = ('level_cap', 'enemy_scaling', 'xp_curve', 'pp_curve', 'stat_curve',
            'chao_level')
RANDOM_TAB = ('randomize_characters', 'randomize_encounters',
              'randomize_placements', 'randomize_items',
              'randomize_chao', 'randomize_shops', 'randomize_chests',
              'randomize_drops', 'randomize_rewards')

LIST_FIELDS = {
    'custom_item': [
        ('item', 'Item', 'item', 78, 'Items 78/79/80 ship with no effects at all.'),
        ('name', 'Name', 'str', 'Chaos Driver', ''),
        ('description', 'Description', 'str', '', ''),
        ('_stat1', 'Effect 1 stat', 'choice:' + ','.join(STATS), 'POW', ''),
        ('_amt1', 'Effect 1 amount', 'int', 8, ''),
        ('_stat2', 'Effect 2 stat', 'choice:' + ','.join(STATS), 'SPD', ''),
        ('_amt2', 'Effect 2 amount', 'int', 6, ''),
        ('_stat3', 'Effect 3 stat', 'choice:' + ','.join(STATS), '', ''),
        ('_amt3', 'Effect 3 amount', 'int', 0, ''),
        ('_el_fire', 'Fire', 'bool', False, ''),
        ('_el_water', 'Water', 'bool', False, ''),
        ('_el_earth', 'Earth', 'bool', False, ''),
        ('_el_wind', 'Wind', 'bool', False, ''),
        ('_el_lightning', 'Lightning', 'bool', False, ''),
        ('_el_ice', 'Ice', 'bool', False,
         'Tick any number — elements stack, confirmed by the Omni Ring.'),
    ],
    'custom_chao': [
        ('item', 'Chao species', 'chao', 121,
         '★ marks a unique effect that lives in code. Renaming or restatting such a '
         'slot keeps it — the effect follows the id.'),
        ('name', 'Name', 'str', 'Revenant', 'Renames the species, which is what the game shows.'),
        ('_statA', 'Stat A', 'choice:' + ','.join(STATS), 'MAXHP', ''),
        ('_a1', 'A — tier 1', 'int', 15, ''),
        ('_a2', 'A — tier 2', 'int', 25, ''),
        ('_a3', 'A — tier 3', 'int', 40, ''),
        ('_statB', 'Stat B', 'choice:' + ','.join(STATS), 'GRT', ''),
        ('_b1', 'B — tier 1', 'int', 3, ''),
        ('_b2', 'B — tier 2', 'int', 6, ''),
        ('_b3', 'B — tier 3', 'int', 10, ''),
    ],
    'store_stock': [
        ('store', 'Shop', 'shop', 1, ''),
        ('_item', 'Item', 'item', 78, ''),
        ('_buy', 'Buy price', 'int', 40, ''),
        ('_sell', 'Sell price', 'int', 20, ''),
    ],
}


def to_feature_entry(fname, raw):
    e = {k: v for k, v in raw.items() if not k.startswith('_') and v not in ('', None)}
    if fname == 'custom_item':
        eff = {}
        for i in (1, 2, 3):
            stat, amt = raw.get('_stat%d' % i), raw.get('_amt%d' % i)
            if stat and amt:
                eff[stat] = int(amt)
        picked = [e for e in ('fire', 'water', 'earth', 'wind', 'lightning', 'ice')
                  if raw.get('_el_' + e)]
        if picked:
            eff['element'] = picked          # the feature accepts one or many
        e['effects'] = eff
    elif fname == 'custom_chao':
        tiers = []
        for t in (1, 2, 3):
            d = {}
            if raw.get('_statA') and raw.get('_a%d' % t):
                d[raw['_statA']] = int(raw['_a%d' % t])
            if raw.get('_statB') and raw.get('_b%d' % t):
                d[raw['_statB']] = int(raw['_b%d' % t])
            tiers.append(d)
        e['tiers'] = tiers
    elif fname == 'store_stock':
        e['items'] = [{'item': int(raw['_item']), 'buy': int(raw['_buy']),
                       'sell': int(raw['_sell'])}]
    return e


def summarise(fname, entry):
    if fname == 'custom_item':
        eff = dict(entry.get('effects', {}))
        els = eff.pop('element', None)
        bits = ['%s %s' % kv for kv in eff.items()]
        if els:
            bits.append('element: ' + ('+'.join(els) if isinstance(els, list) else str(els)))
        return '#%s %s — %s' % (entry.get('item'), entry.get('name', ''),
                                ', '.join(bits) or 'no effects')
    if fname == 'custom_chao':
        return '#%s %s' % (entry.get('item'), entry.get('name', ''))
    if fname == 'store_stock':
        return 'Shop %s — %d item(s)' % (entry.get('store'), len(entry.get('items', [])))
    return json.dumps(entry)[:70]


class EntryDialog(tk.Toplevel):
    def __init__(self, parent, title, spec, initial=None, characters=None, data=None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result, self.vars, self.spec = None, {}, spec
        self.data = data
        self.icon_label = self.icon_img = None
        initial = initial or {}
        # "78 — Chaos Driver" rather than a bare id, so the lists are readable
        self.item_opts, self.item_ids = [], {}
        self.chao_opts, self.chao_ids = [], {}
        self.shop_opts, self.shop_ids = [], {}
        if data:
            for iid, nm, ncgr, nclr in data.items():
                label = '%d — %s' % (iid, nm)
                self.item_opts.append(label)
                self.item_ids[label] = (iid, ncgr, nclr)
        self.chao_desc = {}
        if data:
            for cid, nm, desc, unique in data.chao_detail():
                label = '%d — %s%s' % (cid, nm, '  ★ unique effect' if unique else '')
                self.chao_opts.append(label)
                self.chao_ids[label] = cid
                self.chao_desc[label] = desc
            for n, nm in data.shops():
                label = '%d — %s' % (n, nm)
                self.shop_opts.append(label)
                self.shop_ids[label] = n
        body = ttk.Frame(self, padding=12)
        body.pack(fill='both', expand=True)
        for r, (param, label, kind, default, hint) in enumerate(spec):
            ttk.Label(body, text=label, width=20).grid(row=r, column=0, sticky='w', pady=2)
            val = initial.get(param, default)
            if kind == 'bool':
                self.vars[param] = tk.BooleanVar(value=bool(val))
                ttk.Checkbutton(body, variable=self.vars[param]).grid(row=r, column=1, sticky='w')
            elif kind in ('item', 'chao', 'shop'):
                opts = {'item': self.item_opts, 'chao': self.chao_opts,
                        'shop': self.shop_opts}[kind]
                lookup = {'item': self.item_ids, 'chao': self.chao_ids,
                          'shop': self.shop_ids}[kind]
                cur = next((o for o in opts
                            if o.startswith('%s —' % val)), opts[0] if opts else str(val))
                self.vars[param] = tk.StringVar(value=cur)
                cb = ttk.Combobox(body, textvariable=self.vars[param], values=opts,
                                  width=34, state='readonly')
                cb.grid(row=r, column=1, sticky='w')
                if kind in ('item', 'chao'):
                    cb.bind('<<ComboboxSelected>>',
                            lambda e, pm=param, k=kind: self.on_target_change(pm, k))
            elif kind == 'char' or kind.startswith('choice'):
                opts = (characters or []) if kind == 'char' else kind.split(':', 1)[1].split(',')
                self.vars[param] = tk.StringVar(value=str(val))
                ttk.Combobox(body, textvariable=self.vars[param], values=opts,
                             width=22, state='readonly').grid(row=r, column=1, sticky='w')
            else:
                self.vars[param] = tk.StringVar(value='' if val is None else str(val))
                ttk.Entry(body, textvariable=self.vars[param],
                          width=46 if kind == 'str' else 22).grid(row=r, column=1, sticky='w')
            if hint:
                ttk.Label(body, text=hint, foreground='#777', wraplength=320,
                          justify='left').grid(row=r, column=2, sticky='w', padx=8)
        self.icon_label = ttk.Label(body)
        self.icon_label.grid(row=len(spec), column=1, sticky='w', pady=(6, 0))
        self.effect_label = ttk.Label(body, foreground='#555', wraplength=440,
                                      justify='left')
        self.effect_label.grid(row=len(spec) + 1, column=1, columnspan=2,
                               sticky='w', pady=(4, 0))
        for param, label, kind, default, hint in spec:
            if kind in ('item', 'chao'):
                if not (initial or {}).get('name'):
                    self.on_target_change(param, kind)
                elif kind == 'item':
                    self.show_icon(param)
                break
        bar = ttk.Frame(self, padding=(12, 0, 12, 12))
        bar.pack(fill='x')
        ttk.Button(bar, text='OK', command=self.ok).pack(side='right')
        ttk.Button(bar, text='Cancel', command=self.destroy).pack(side='right', padx=6)
        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def on_target_change(self, param, kind):
        """Keep the Name field on the thing actually selected.

        Without this the picker and the name drift apart: choose item 63 while the
        box still reads a name typed for item 78 and you rename 63 by mistake. The
        field is refilled with the selection's current in-game name, so overwriting
        it is a deliberate act rather than an accident.
        """
        label = self.vars[param].get()
        current = label.split(' — ', 1)[1] if ' — ' in label else ''
        current = current.split('  ★')[0].strip()
        if 'name' in self.vars and current:
            self.vars['name'].set(current)
        if kind == 'item':
            self.show_icon(param)
        elif kind == 'chao' and getattr(self, 'effect_label', None) is not None:
            desc = self.chao_desc.get(label, '')
            star = '★' in label
            self.effect_label.configure(
                text=(('Unique effect — hardcoded, and kept if you rename or restat '
                       'this slot, but its odds cannot be changed:\n' if star
                       else 'Effect: ') + desc) if desc else '')

    def show_icon(self, param):
        """Draw the selected item's real inventory sprite, when it has one."""
        if not (self.data and self.icon_label):
            return
        entry = self.item_ids.get(self.vars[param].get())
        self.icon_img = None
        if entry:
            _, ncgr, nclr = entry
            if ncgr and nclr:
                ppm = iconlib.load_parts(self.data.herf, ncgr, nclr, scale=2)
                if ppm:
                    try:
                        self.icon_img = tk.PhotoImage(data=ppm)
                    except Exception:
                        self.icon_img = None
        self.icon_label.configure(image=self.icon_img or '',
                                  text='' if self.icon_img else '(no icon)')

    def ok(self):
        out = {}
        for param, label, kind, default, hint in self.spec:
            raw = self.vars[param].get()
            if kind in ('item', 'chao', 'shop'):
                lookup = {'item': self.item_ids, 'chao': self.chao_ids,
                          'shop': self.shop_ids}[kind]
                v = lookup.get(raw)
                if v is None:
                    continue
                out[param] = v[0] if kind == 'item' else v
                continue
            if kind == 'bool':
                out[param] = bool(raw)
            elif raw == '':
                continue
            elif kind == 'int':
                out[param] = int(raw)
            elif kind == 'float':
                out[param] = float(raw)
            else:
                out[param] = raw
        self.result = out
        self.destroy()


class App:
    def __init__(self, root):
        self.root = root
        root.title('Sonic Chronicles — Mod Pack Maker')
        root.geometry('960x820')
        self.data = None
        self.slot_over = {}     # (character, slot) -> dict
        self.move_over = {}     # combo row -> dict
        self.move_owner = {}    # combo row -> character (for the summary only)
        self.vars, self.enabled, self.lists, self.listboxes = {}, {}, {}, {}

        top = ttk.Frame(root, padding=10)
        top.pack(fill='x')
        ttk.Label(top, text='Source ROM').grid(row=0, column=0, sticky='w')
        self.rom = tk.StringVar(value=DEFAULT_ROM if os.path.exists(DEFAULT_ROM) else '')
        ttk.Entry(top, textvariable=self.rom, width=84).grid(row=0, column=1, padx=6)
        ttk.Button(top, text='Browse…', command=self.pick_rom).grid(row=0, column=2)
        ttk.Label(top, text='Mod name').grid(row=1, column=0, sticky='w', pady=(6, 0))
        self.name = tk.StringVar(value='My Mod')
        ttk.Entry(top, textvariable=self.name, width=84).grid(row=1, column=1, padx=6, pady=(6, 0))
        ttk.Label(top, text='Build on top of').grid(row=2, column=0, sticky='w', pady=(6, 0))
        existing = [''] + sorted(f for f in os.listdir(os.path.join(ROOT, 'profiles'))
                                 if f.endswith('.json'))
        self.extends = tk.StringVar(value='')
        ttk.Combobox(top, textvariable=self.extends, values=existing, width=81,
                     state='readonly').grid(row=2, column=1, padx=6, pady=(6, 0), sticky='w')

        self.nb = ttk.Notebook(root)
        self.nb.pack(fill='both', expand=True, padx=10, pady=8)
        self.tab_presets = ttk.Frame(self.nb)
        self.tab_chars = ttk.Frame(self.nb)
        self.tab_game = ttk.Frame(self.nb)
        self.tab_items = ttk.Frame(self.nb)
        self.tab_random = ttk.Frame(self.nb)
        self.nb.add(self.tab_presets, text='Presets')
        self.nb.add(self.tab_chars, text='Characters')
        self.nb.add(self.tab_game, text='Game')
        self.nb.add(self.tab_items, text='Items & Chao')
        self.nb.add(self.tab_random, text='Randomizer')

        self.build_presets_tab()
        self.build_chars_tab()
        self.build_game_tab()
        self.build_items_tab()
        self.build_random_tab()

        bar = ttk.Frame(root, padding=10)
        bar.pack(fill='x', side='bottom')
        self.status = tk.StringVar(value='Ready.')
        ttk.Label(bar, textvariable=self.status).pack(side='left')
        self.nopatch = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text='Skip patch (much faster)',
                        variable=self.nopatch).pack(side='right', padx=6)
        ttk.Button(bar, text='Build ROM', command=self.build).pack(side='right')
        ttk.Button(bar, text='Save profile', command=self.save_profile).pack(side='right', padx=6)

        self.load_rom()

    # --- presets tab ------------------------------------------------------

    def build_presets_tab(self):
        """Whole mods, ready to build, assembled only from features confirmed in game.

        A preset builds **its own profile directly** rather than filling in the other
        tabs. That keeps one obvious meaning for the Build ROM button at the bottom - it
        builds what the tabs say - and means a preset cannot be half-applied by someone
        switching tabs afterwards. The seed box is the one thing worth changing without
        editing the file, so it is offered here.
        """
        f = ttk.Frame(self.tab_presets, padding=10)
        f.pack(fill='both', expand=True)
        ttk.Label(f, justify='left', wraplength=900, foreground='#a70',
                  text='A preset is a whole mod. Pick one, give it a mod name above, and '
                       'press Build preset — it builds that profile directly and ignores '
                       'the other tabs. Every preset is assembled only from features '
                       'confirmed in game.').pack(anchor='w', pady=(0, 10))
        self.preset_choice = tk.StringVar()
        self.preset_seed = tk.StringVar(value='1')
        for slug, title, blurb in self._presets():
            box = ttk.LabelFrame(f, text=title, padding=8)
            box.pack(fill='x', pady=4)
            ttk.Radiobutton(box, text='Use this one', value=slug,
                            variable=self.preset_choice).pack(anchor='w')
            ttk.Label(box, text=blurb, justify='left', wraplength=880,
                      foreground='#555').pack(anchor='w', pady=(2, 0))
        row = ttk.Frame(f)
        row.pack(fill='x', pady=(12, 0))
        ttk.Label(row, text='Seed', width=8).pack(side='left')
        ttk.Entry(row, textvariable=self.preset_seed, width=12).pack(side='left')
        ttk.Label(row, foreground='#777',
                  text='  Only affects presets that randomize. Same seed, same ROM.'
                  ).pack(side='left')
        ttk.Button(row, text='Build preset',
                   command=self.build_preset).pack(side='right')

    def _presets(self):
        """[(slug, name, description)] read from profiles/presets, newest schema first."""
        out = []
        d = os.path.join(ROOT, 'profiles', 'presets')
        for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if not fn.endswith('.json'):
                continue
            try:
                with open(os.path.join(d, fn), encoding='utf-8') as fh:
                    prof = json.load(fh)
            except Exception:
                continue
            out.append((fn[:-5], prof.get('name', fn[:-5]), prof.get('description', '')))
        return out

    def build_preset(self):
        if not os.path.exists(self.rom.get()):
            messagebox.showerror('No ROM', 'Select a source ROM first.')
            return
        slug = self.preset_choice.get()
        if not slug:
            messagebox.showerror('No preset', 'Pick a preset first.')
            return
        src = os.path.join(ROOT, 'profiles', 'presets', slug + '.json')
        with open(src, encoding='utf-8') as fh:
            prof = json.load(fh)
        # The seed box edits every feature that takes one, so a preset is re-rollable
        # without opening the file. Everything else stays exactly as the preset ships.
        try:
            seed = int(self.preset_seed.get())
        except ValueError:
            seed = 1
        for params in (prof.get('features') or {}).values():
            if isinstance(params, dict) and 'seed' in params:
                params['seed'] = seed
        name = (self.name.get() or prof.get("name") or slug).strip()
        prof['name'] = name
        # Written beside the presets so `extends` still resolves against that folder.
        path = os.path.join(ROOT, 'profiles', 'presets', '_built_%s.json' % slug)
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(prof, fh, indent=2)
        cmd = [sys.executable, '-u', os.path.join(ROOT, 'tools', 'build', 'modbuild.py'),
               self.rom.get(), path]
        if self.nopatch.get():
            cmd.append('--no-patch')
        self.status.set('Building %s… (several minutes)' % name)
        threading.Thread(target=self._run, args=(cmd,), daemon=True).start()

    # --- characters tab ---------------------------------------------------

    def build_chars_tab(self):
        f = self.tab_chars
        head = ttk.Frame(f, padding=8)
        head.pack(fill='x')
        ttk.Label(head, text='Character').pack(side='left')
        self.char = tk.StringVar()
        self.char_box = ttk.Combobox(head, textvariable=self.char, width=24, state='readonly')
        self.char_box.pack(side='left', padx=8)
        self.char_box.bind('<<ComboboxSelected>>', lambda e: self.show_character())
        ttk.Label(head, foreground='#555',
                  text='Values shown are the ROM\'s current ones. Change what you want; '
                       'anything left alone is untouched.').pack(side='left', padx=10)
        self.char_body = ttk.Frame(f, padding=8)
        self.char_body.pack(fill='both', expand=True)

    def load_rom(self):
        path = self.rom.get()
        if not path or not os.path.exists(path):
            self.status.set('Select a source ROM to load character data.')
            return
        try:
            self.data = GameData(path)
        except Exception as e:
            self.status.set('Could not read ROM: %s' % e)
            return
        self.chars = self.data.playable()
        self.char_box['values'] = ['%s  (creature %d)' % (n, r) for r, n, a in self.chars]
        if self.chars:
            self.char_box.current(0)
            self.show_character()
        self.status.set('Loaded %d characters from the ROM.' % len(self.chars))

    def current_char(self):
        i = self.char_box.current()
        return self.chars[i] if 0 <= i < len(self.chars) else None

    def show_character(self):
        for w in self.char_body.winfo_children():
            w.destroy()
        cur = self.current_char()
        if not cur:
            return
        crow, name, adv = cur
        short = adv.replace('Adv_', '')
        ab = self.data.abilities()
        ability_names = ['(empty)'] + [v[0] for v in ab.values()]
        maxlevels = {v[0]: v[1] for v in ab.values()}

        box = ttk.LabelFrame(self.char_body, text=' Movement ability slots ', padding=8)
        box.pack(fill='x', pady=4)
        ttk.Label(box, foreground='#777', wraplength=880, justify='left',
                  text='Every character has three slots; most leave some empty. A slot holds '
                       'the ability, while its level lives in the progression table — setting '
                       'one without the other grants nothing, so both are written.'
                  ).pack(anchor='w', pady=(0, 6))
        self.slot_widgets = {}
        for slot, aid, aname in self.data.slots_of(crow):
            row = ttk.Frame(box)
            row.pack(fill='x', pady=2)
            ttk.Label(row, text='Slot %d' % slot, width=8).pack(side='left')
            ttk.Label(row, text='now: %-12s' % aname, width=18,
                      foreground='#555').pack(side='left')
            key = (short, slot)
            over = self.slot_over.get(key, {})
            av = tk.StringVar(value=over.get('ability', aname if aid != -1 else '(empty)'))
            lv = tk.StringVar(value=str(over.get('level', maxlevels.get(aname, 1))))
            fl = tk.StringVar(value=str(over.get('from_level', 1)))
            ttk.Combobox(row, textvariable=av, values=ability_names, width=15,
                         state='readonly').pack(side='left', padx=4)
            ttk.Label(row, text='level').pack(side='left')
            ttk.Entry(row, textvariable=lv, width=4).pack(side='left', padx=3)
            ttk.Label(row, text='from character level').pack(side='left')
            ttk.Entry(row, textvariable=fl, width=4).pack(side='left', padx=3)
            self.slot_widgets[key] = (av, lv, fl, aname)

        box2 = ttk.LabelFrame(self.char_body, text=' POW moves ', padding=8)
        box2.pack(fill='both', expand=True, pady=4)
        ttk.Label(box2, foreground='#777', wraplength=880, justify='left',
                  text='"Solo" clears the partner requirement so a move works without the '
                       'characters it was written for. Only the four elements seen in vanilla '
                       'are offered.').pack(anchor='w', pady=(0, 6))
        self.move_widgets = {}
        for idx, mname, cost, parts, el in self.data.moves_of(crow):
            row = ttk.Frame(box2)
            row.pack(fill='x', pady=2)
            ttk.Label(row, text=mname, width=20).pack(side='left')
            ttk.Label(row, text='%d-char' % parts, width=8, foreground='#555').pack(side='left')
            over = self.move_over.get(idx, {})
            so = tk.BooleanVar(value=over.get('solo', False))
            co = tk.StringVar(value=str(over.get('cost', cost)))
            ev = tk.StringVar(value=over.get('element', el or '(unchanged)'))
            ttk.Checkbutton(row, text='solo', variable=so).pack(side='left', padx=4)
            ttk.Label(row, text='PP').pack(side='left')
            ttk.Entry(row, textvariable=co, width=4).pack(side='left', padx=3)
            ttk.Combobox(row, textvariable=ev, values=MOVE_ELEMENTS, width=13,
                         state='readonly').pack(side='left', padx=4)
            self.move_widgets[idx] = (so, co, ev, cost, el)
            self.move_owner[idx] = short

    def harvest_character(self):
        """Fold the on-screen character edits into the override dicts."""
        cur = self.current_char()
        if not cur or not self.data:
            return
        short = cur[2].replace('Adv_', '')
        for (ch, slot), (av, lv, fl, was) in getattr(self, 'slot_widgets', {}).items():
            picked = av.get()
            if picked == '(empty)' or picked == was:
                self.slot_over.pop((ch, slot), None)
                continue
            self.slot_over[(ch, slot)] = {'ability': picked.lower(),
                                          'level': int(lv.get() or 1),
                                          'from_level': int(fl.get() or 1)}
        for idx, (so, co, ev, was_cost, was_el) in getattr(self, 'move_widgets', {}).items():
            spec = {}
            if so.get():
                spec['solo'] = True
            if co.get() and int(co.get()) != was_cost:
                spec['cost'] = int(co.get())
            if ev.get() not in ('(unchanged)', was_el, ''):
                spec['element'] = ev.get()
            if spec:
                self.move_over[idx] = spec
            else:
                self.move_over.pop(idx, None)

    # --- game / items tabs ------------------------------------------------

    def _head(self, parent, fname):
        box = ttk.LabelFrame(parent, padding=8, text='')
        box.pack(fill='x', pady=4, padx=4)
        head = ttk.Frame(box)
        head.pack(fill='x')
        self.enabled[fname] = tk.BooleanVar(value=False)
        ttk.Checkbutton(head, text=fname, variable=self.enabled[fname]).pack(side='left')
        conf = features.CONFIRMED[fname]
        ttk.Label(head, text='[%s]' % ('confirmed in game' if conf == 'game'
                                       else 'build-verified only'),
                  foreground='#2a7' if conf == 'game' else '#a70').pack(side='left', padx=8)
        doc = (features.REGISTRY[fname].__doc__ or '').strip().splitlines()[0]
        ttk.Label(box, text=doc, foreground='#555', wraplength=860,
                  justify='left').pack(anchor='w', pady=(2, 4))
        return box

    def build_game_tab(self):
        self._build_param_tab(self.tab_game, GAME_TAB)

    def build_random_tab(self):
        note = ttk.Label(
            self.tab_random, justify='left', foreground='#a70', wraplength=860,
            text='Each feature carries its own badge below. Give the profile its own '
                 'name — a build writes to build/<name>.nds, and a name collision '
                 'with a ROM you are playing is refused rather than silently '
                 'overwriting it.')
        note.pack(anchor='w', padx=6, pady=(8, 2))
        self._build_param_tab(self.tab_random, RANDOM_TAB)

    def _build_param_tab(self, parent, names):
        chars = ['Sonic', 'Shadow', 'Knuckles', 'Tails', 'Amy', 'Rouge',
                 'Big', 'Cream', 'Omega', 'Shade', 'Eggman']
        for fname in names:
            box = self._head(parent, fname)
            for param, label, kind, default, hint in GAME_FIELDS[fname]:
                row = ttk.Frame(box)
                row.pack(fill='x', pady=1)
                ttk.Label(row, text=label, width=30).pack(side='left')
                key = (fname, param)
                self.vars[key] = tk.StringVar(value=str(default))
                if kind == 'bool':
                    self.vars[key].set('yes' if default else 'no')
                    ttk.Combobox(row, textvariable=self.vars[key], values=['no', 'yes'],
                                 width=16, state='readonly').pack(side='left')
                elif kind == 'char' or kind.startswith('choice'):
                    opts = chars if kind == 'char' else kind.split(':', 1)[1].split(',')
                    ttk.Combobox(row, textvariable=self.vars[key], values=opts,
                                 width=16, state='readonly').pack(side='left')
                else:
                    ttk.Entry(row, textvariable=self.vars[key], width=18).pack(side='left')
                if hint:
                    ttk.Label(row, text=hint, foreground='#777', wraplength=440,
                              justify='left').pack(side='left', padx=8)

    def build_items_tab(self):
        for fname in ('custom_item', 'custom_chao', 'store_stock'):
            box = self._head(self.tab_items, fname)
            self.lists[fname] = []
            row = ttk.Frame(box)
            row.pack(fill='x')
            lb = tk.Listbox(row, height=5)
            lb.pack(side='left', fill='x', expand=True)
            self.listboxes[fname] = lb
            btns = ttk.Frame(row)
            btns.pack(side='left', padx=6)
            for text, cmd in (('Add…', self.add_entry), ('Edit…', self.edit_entry),
                              ('Remove', self.remove_entry)):
                ttk.Button(btns, text=text, width=9,
                           command=lambda f=fname, c=cmd: c(f)).pack(pady=1)

    def refresh(self, fname):
        lb = self.listboxes[fname]
        lb.delete(0, 'end')
        for raw, entry in self.lists[fname]:
            lb.insert('end', summarise(fname, entry))

    def add_entry(self, fname):
        dlg = EntryDialog(self.root, 'Add — %s' % fname, LIST_FIELDS[fname],
                          data=self.data)
        if dlg.result:
            self.lists[fname].append((dlg.result, to_feature_entry(fname, dlg.result)))
            self.enabled[fname].set(True)
            self.refresh(fname)

    def edit_entry(self, fname):
        sel = self.listboxes[fname].curselection()
        if not sel:
            return
        raw, _ = self.lists[fname][sel[0]]
        dlg = EntryDialog(self.root, 'Edit — %s' % fname, LIST_FIELDS[fname], raw,
                          data=self.data)
        if dlg.result:
            self.lists[fname][sel[0]] = (dlg.result, to_feature_entry(fname, dlg.result))
            self.refresh(fname)

    def remove_entry(self, fname):
        sel = self.listboxes[fname].curselection()
        if sel:
            self.lists[fname].pop(sel[0])
            self.refresh(fname)

    def pick_rom(self):
        path = filedialog.askopenfilename(title='Select the source ROM',
                                          filetypes=[('NDS ROM', '*.nds'), ('All', '*.*')])
        if path:
            self.rom.set(path)
            self.load_rom()

    # --- profile ----------------------------------------------------------

    def collect(self):
        self.harvest_character()
        feats = {}
        slots = [dict(character=ch, slot=sl, **spec)
                 for (ch, sl), spec in sorted(self.slot_over.items())]
        if slots:
            feats['movement_slots'] = slots
        moves = [dict(move=idx, **spec) for idx, spec in sorted(self.move_over.items())]
        if moves:
            feats['pow_move'] = moves
        for fname, on in self.enabled.items():
            if not on.get():
                continue
            if fname in LIST_FIELDS:
                entries = [e for _, e in self.lists[fname]]
                if not entries:
                    raise ValueError('%s is ticked but has no entries.' % fname)
                feats[fname] = entries
            else:
                params = {}
                for param, label, kind, default, hint in GAME_FIELDS[fname]:
                    raw = self.vars[(fname, param)].get().strip()
                    if raw == '':
                        continue
                    if kind == 'bool':
                        params[param] = raw.lower() in ('yes', 'true', '1')
                    elif kind in ('range', 'range3'):
                        want = 2 if kind == 'range' else 3
                        parts = [p for p in raw.replace(',', ' ').split() if p]
                        if len(parts) != want:
                            raise ValueError('%s.%s wants %d numbers, e.g. %r'
                                             % (fname, param, want,
                                                '0.5, 2.0' if want == 2 else '4, 8, 12'))
                        nums = [float(p) for p in parts]
                        params[param] = ([int(n) for n in nums] if kind == 'range3'
                                         else nums)
                    else:
                        params[param] = (int(raw) if kind == 'int'
                                         else float(raw) if kind == 'float' else raw)
                feats[fname] = params
        if not feats and not self.extends.get():
            raise ValueError('Nothing to build: change a character or tick a feature.')
        prof = {'name': self.name.get().strip() or 'My Mod',
                'description': 'Built with the Mod Pack Maker.',
                'features': feats}
        if self.extends.get():
            prof['extends'] = self.extends.get()
        return prof

    def profile_path(self):
        slug = ''.join(c if c.isalnum() else '_' for c in self.name.get()).strip('_').lower()
        return os.path.join(ROOT, 'profiles', '%s.json' % (slug or 'my_mod'))

    def save_profile(self):
        try:
            prof = self.collect()
        except Exception as e:
            messagebox.showerror('Cannot save', str(e))
            return None
        path = self.profile_path()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(prof, f, indent=2)
        self.status.set('Saved %s' % os.path.relpath(path, ROOT))
        return path

    def build(self):
        if not os.path.exists(self.rom.get()):
            messagebox.showerror('No ROM', 'Select a source ROM first.')
            return
        path = self.save_profile()
        if not path:
            return
        cmd = [sys.executable, '-u', os.path.join(ROOT, 'tools', 'build', 'modbuild.py'),
               self.rom.get(), path]
        if self.nopatch.get():
            cmd.append('--no-patch')
        self.status.set('Building… (several minutes)')
        threading.Thread(target=self._run, args=(cmd,), daemon=True).start()

    def _run(self, cmd):
        try:
            out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        except Exception as e:
            self.root.after(0, lambda: self.status.set('Build failed: %s' % e))
            return
        ok = 'ALL STAGES PASSED' in out.stdout
        tail = [l for l in out.stdout.splitlines()
                if l.startswith('  ') or 'PASSED' in l or l.startswith('!!')]

        def done():
            self.status.set('Build succeeded.' if ok else 'Build FAILED — see details.')
            win = tk.Toplevel(self.root)
            win.title('Build %s' % ('succeeded' if ok else 'failed'))
            win.geometry('800x500')
            txt = tk.Text(win, wrap='none')
            txt.insert('1.0', '\n'.join(tail[-200:]) or out.stdout[-6000:] or out.stderr[-6000:])
            txt.configure(state='disabled')
            txt.pack(fill='both', expand=True)
        self.root.after(0, done)


def _set_icon(root):
    """Give the window and the Windows taskbar a real icon, if one is on disk.

    Two separate things have to happen on Windows. `iconbitmap` sets the window icon,
    and **the taskbar button only follows it once the process declares its own
    AppUserModelID** - without that, Windows groups the window under the Python
    launcher and shows the interpreter's icon instead, which is where the Tk feather
    comes from. Both steps are best-effort: a missing or unreadable icon falls back to
    the default rather than stopping the app from opening.
    """
    assets = os.path.normpath(os.path.join(HERE, '..', '..', 'assets'))
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                'DumbCode4Fun.SonicChronicles.ModPackMaker')
        except Exception:
            pass
    ico = os.path.join(assets, 'icon.ico')
    if os.path.exists(ico):
        try:
            root.iconbitmap(default=ico)
            return
        except Exception:
            pass
    png = os.path.join(assets, 'icon.png')
    if os.path.exists(png):
        try:
            # The reference has to be kept alive or Tk drops the image.
            root._icon_image = tk.PhotoImage(file=png)
            root.iconphoto(True, root._icon_image)
        except Exception:
            pass


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use('vista')
    except Exception:
        pass
    _set_icon(root)
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
