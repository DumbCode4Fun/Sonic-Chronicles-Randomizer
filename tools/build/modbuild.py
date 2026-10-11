"""
Profile-driven mod builder — roadmap Phase 17.

Replaces the eight one-off build drivers written during Phase 0-8. Each of those
re-implemented the same five stages (validate, edit, rebuild, verify, patch) with
only the edits differing, so the edits are now **data** in a JSON profile and the
pipeline is written once.

Per CLAUDE.md the profile only exposes operations whose behaviour has been
**confirmed in game**, not invented ones:

    {
      "name": "Example Mod",
      "edits": [
        {"op": "tlk_string",   "id": 6676, "text": "..."},
        {"op": "twoda_cell",   "resource": "Item34.ITM", "row": "SPD+",
                               "column": "Data", "value": "9"},
        {"op": "twoda_add_row","resource": "Item74.itm", "row": "ELEMENT",
                               "values": {"EffectId":"1","Data":"1","SData1":"107",
                                          "SData2":"0","SData3":"0","Pulse":"-1"}},
        {"op": "gda_cell",     "resource": "Adv_Shadow.GDA", "row": 1,
                               "column": "xp", "value": 200},
        {"op": "gda_string",   "resource": "creatures.GDA", "row": 0,
                               "column": "portrait", "value": "PRT_SP_SDW.ncgr"},
        {"op": "gda_add_row",  "resource": "Adv_Sonic.GDA", "values": [...]},
        {"op": "copy_resource","from": "PRTL_SDWsmg_0.NCGR.small",
                               "to":   "PRTL_SONICamu_0.NCGR.small"},
        {"op": "item_name",    "item": 74, "text": "Omni Ring"},
        {"op": "item_desc",    "item": 74, "text": "..."},
        {"op": "chao_name",    "item": 106, "text": "Prism"}
      ]
    }

Notes on the two naming ops, both learned the hard way:
  * `item_name`/`item_desc` write the strrefs named by `Items.GDA`.
  * `chao_name` writes the **species** name from `Chaos.GDA` — a Chao's displayed
    name does *not* come from its item entry, so `item_name` silently does nothing
    for Chao.

Every stage verifies itself and the build aborts rather than emitting a ROM that
has not been read back successfully. The source ROM is opened read-only.

A profile may also carry a `features` block of named, parameterised features (see
features.py), which expand into exactly these same edits:

    {"features": {"level_cap": {"cap": 99},
                  "pp_curve": {"character": "Shadow", "bonus": 3}}}

`--no-patch` skips BPS generation. The ROM is still fully validated and
regression-swept; only the distributable patch is omitted. Patch creation is the
slowest stage by far on builds that *grow* resources (appended rows change the
archive's size, which relayouts the ROM), so test builds are much faster without it.

A profile may also build on another with `"extends": "other.json"`. The parent's
edits and features apply first, so the child wins on anything they both touch.

Usage:
    py modbuild.py <rom.nds> <profile.json> [--out-dir build] [--no-patch]
    py modbuild.py --list-features
"""
import json
import os
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'recon'))

import bps  # noqa: E402
from rom_build import Rom, verify_noop  # noqa: E402
from herf_write import HerfFile  # noqa: E402
from tlk_write import TlkFile  # noqa: E402
from twoda_write import set_cell, add_row  # noqa: E402
from gda_write import (set_int_cell, set_string_cell, append_row,  # noqa: E402
                       append_rows_clone, _resolve_column)
import are_write  # noqa: E402
from twoda import parse_2da  # noqa: E402
from gff4 import GFF4, read_gda  # noqa: E402
import features  # noqa: E402

ARCHIVE = '/test.herf'
TLK_PATH = '/strings.tlk'


class Build:
    def __init__(self, rom_path, column_names=None):
        with open(rom_path, 'rb') as f:
            self.original = f.read()
        self.rom = Rom(self.original)
        self.herf_fid = self.rom.file_id(ARCHIVE)
        self.tlk_fid = self.rom.file_id(TLK_PATH)
        self.herf = HerfFile(self.rom.file_bytes(self.herf_fid))
        # A second, never-mutated view of the same archive. `copy_resource` reads its
        # sources from here so that a *swap* works regardless of edit order: copying
        # A->B first must not destroy the A that B->A still needs.
        self.herf_orig = HerfFile(self.rom.file_bytes(self.herf_fid))
        self.tlk = TlkFile(self.rom.file_bytes(self.tlk_fid))
        self.column_names = column_names or {}
        self.arm9_patches = []          # (ram address, bytes) applied after the rebuild
        self._resource_map = {n.lower(): n for n in self.herf.names.values()}
        self._items = None
        self._chao = None
        self.applied = []

    # --- lookups -------------------------------------------------------

    def resource(self, name):
        key = self._resource_map.get(str(name).lower())
        if key is None:
            raise KeyError(f"no resource named {name!r} in {ARCHIVE}")
        return key

    def items(self):
        """item id -> {'file', 'name_ref', 'desc_ref'} from Items.GDA."""
        if self._items is None:
            g = GFF4(self.herf.read('Items.GDA'))
            cols, rows = read_gda(g)
            K = sorted(rows[0].keys())
            out = {}
            for r in rows:
                iid, nref, dref, typ, sub, base = (r[K[i]] for i in range(6))
                if base and base != 'None':
                    key = self._resource_map.get(str(base).lower())
                    if key:
                        out[iid] = {'file': key, 'name_ref': nref, 'desc_ref': dref}
            self._items = out
        return self._items

    def chao_species_refs(self):
        """any of a species' three item ids -> (name strref, description strref).

        Both live on the *species* row in Chaos.GDA, not on the item, which is the same
        trap `chao_name` documents: an item-level write silently does nothing for Chao.
        """
        if self._chao is None:
            g = GFF4(self.herf.read('Chaos.GDA'))
            cols, rows = read_gda(g)
            K = sorted(rows[0].keys())
            out = {}
            for r in rows:
                v = [r[k] for k in K]
                for item_id in (v[6], v[7], v[8]):
                    out[item_id] = (v[1], v[2])
            self._chao = out
        return self._chao

    def chao_species_nameref(self):
        """any of a species' three item ids -> that species' name strref."""
        return {k: v[0] for k, v in self.chao_species_refs().items()}

    # --- operations ----------------------------------------------------

    def op_tlk_string(self, e):
        idx = self.tlk.index_of_id(int(e['id']))
        note = self.tlk.set_string(idx, e['text'])
        return f"tlk {e['id']}: {note}"

    def op_twoda_cell(self, e):
        key = self.resource(e['resource'])
        raw, note = set_cell(self.herf.read(key), e['row'], e['column'],
                             str(e['value']), allow_noop=bool(e.get('allow_noop')))
        self.herf.replace(key, raw)
        return f"{key}: {note}"

    def op_twoda_add_row(self, e):
        key = self.resource(e['resource'])
        raw, note = add_row(self.herf.read(key), e['row'], e['values'])
        self.herf.replace(key, raw)
        return f"{key}: {note}"

    def op_gda_cell(self, e):
        """Set one numeric cell. A float value goes to a float column unchanged.

        `combo.GDA` mixes four `float32` columns in among fifty integers, so coercing
        every value to `int` here would quietly zero a move's status-effect chances.
        The writer refuses a float into an integer column rather than truncating it.
        """
        key = self.resource(e['resource'])
        v = e['value']
        value = float(v) if isinstance(v, float) else int(v)
        raw, note = set_int_cell(self.herf.read(key), int(e['row']), e['column'],
                                 value, self.column_names)
        self.herf.replace(key, raw)
        return f"{key}: {note}"

    def op_gda_string(self, e):
        key = self.resource(e['resource'])
        raw, note = set_string_cell(self.herf.read(key), int(e['row']), e['column'],
                                    str(e['value']), self.column_names)
        self.herf.replace(key, raw)
        return f"{key}: {note}"

    def op_gda_add_row(self, e):
        key = self.resource(e['resource'])
        raw, note = append_row(self.herf.read(key), e['values'])
        self.herf.replace(key, raw)
        return f"{key}: {note}"

    def op_gda_clone_rows(self, e):
        """Append clones of existing rows, each with per-column overrides.

        For tables `gda_add_row` refuses — `creatures.GDA` carries out-of-line strings
        and has its row array mid-file. Overrides are keyed by column (index or name),
        exactly as `gda_cell` takes them. The whole batch relocates the row array once,
        so one op per resource is much cheaper than many.
        """
        key = self.resource(e['resource'])
        raw = self.herf.read(key)
        g = GFF4(raw)
        specs = []
        for spec in e['rows']:
            # JSON object keys are always strings, so a column given by index arrives as
            # "7" and would otherwise be looked up as a column *name*.
            overrides = {}
            for col, val in (spec.get('overrides') or {}).items():
                if isinstance(col, str) and col.lstrip('-').isdigit():
                    col = int(col)
                overrides[_resolve_column(g, col, self.column_names)] = val
            specs.append((int(spec['source']), overrides))
        raw, note = append_rows_clone(raw, specs)
        self.herf.replace(key, raw)
        return f"{key}: {note}"

    def op_are_cell(self, e):
        """Overwrite one integer field of one placed object in an area file.

        Used for the two things an area actually decides: what a chest holds (the
        `kind == 4` objects in list 40002) and which squad spawns where (field 40005 in
        list 40003). Nothing resizes, so this is as cheap as `gda_cell`.
        """
        key = self.resource(e['resource'])
        raw, note = are_write.set_field(self.herf.read(key), int(e['list']),
                                        int(e['index']), int(e['field']),
                                        int(e['value']))
        self.herf.replace(key, raw)
        return f"{key}: {note}"

    def op_copy_resource(self, e):
        """Overwrite one resource's payload with another's, byte for byte.

        Used for the portrait remap, where Shadow's 64x64 8bpp frames stand in for
        Sonic's. Only valid between resources of identical geometry -- the caller is
        responsible for that; this op just moves bytes. The source is read from the
        pristine archive view, so swaps are order-independent.
        """
        src = self.resource(e['from'])
        dst = self.resource(e['to'])
        payload = self.herf_orig.read(src)
        if not payload:
            raise ValueError(f"source resource {src!r} is empty")
        self.herf.replace(dst, payload)
        return f"{dst} <- {src} ({len(payload)} bytes)"

    def op_arm9_patch(self, e):
        """Patch bytes in the ARM9 executable at a RAM address.

        The ARM9 lives outside the NitroROM filesystem, so this cannot go through the
        normal file-replacement path; the bytes are applied to the finished image and
        the header checksum recomputed. The binary is **not** compressed in this game,
        so addresses map linearly: file = arm9_rom_offset + (address - arm9_ram).

        Patching code is categorically riskier than editing data — a wrong byte here
        crashes rather than looking wrong — so every patch states the bytes it expects
        to find and is refused if they are not there.
        """
        addr = int(e['address'], 0) if isinstance(e['address'], str) else int(e['address'])
        new = bytes(int(x, 16) if isinstance(x, str) else int(x) for x in e['bytes'])
        expect = bytes(int(x, 16) if isinstance(x, str) else int(x)
                       for x in e.get('expect', []))
        hdr = self.rom.header
        off = hdr['arm9_rom_offset'] + (addr - hdr['arm9_ram'])
        if not (hdr['arm9_rom_offset'] <= off < hdr['arm9_rom_offset'] + hdr['arm9_size']):
            raise ValueError('0x%08X is outside the ARM9 image' % addr)
        if expect:
            actual = self.original[off:off + len(expect)]
            if actual != expect:
                raise ValueError('arm9 0x%08X: expected %s, found %s'
                                 % (addr, expect.hex(' '), actual.hex(' ')))
        self.arm9_patches.append((off, new))
        return "arm9 0x%08X: %s -> %s" % (addr, expect.hex(' ') or '??', new.hex(' '))

    def op_item_name(self, e):
        rec = self.items()[int(e['item'])]
        self.tlk.set_string(self.tlk.index_of_id(rec['name_ref']), e['text'])
        return f"item {e['item']} name -> {e['text']!r}"

    def op_item_desc(self, e):
        rec = self.items()[int(e['item'])]
        self.tlk.set_string(self.tlk.index_of_id(rec['desc_ref']), e['text'])
        return f"item {e['item']} desc updated"

    def op_chao_name(self, e):
        sref = self.chao_species_nameref()[int(e['item'])]
        self.tlk.set_string(self.tlk.index_of_id(sref), e['text'])
        return f"chao species of item {e['item']} -> {e['text']!r}"

    def op_chao_desc(self, e):
        sref = self.chao_species_refs()[int(e['item'])][1]
        self.tlk.set_string(self.tlk.index_of_id(sref), e['text'])
        return f"chao species desc of item {e['item']} updated"

    OPS = {'tlk_string': op_tlk_string, 'twoda_cell': op_twoda_cell,
           'twoda_add_row': op_twoda_add_row, 'gda_cell': op_gda_cell,
           'gda_string': op_gda_string, 'gda_add_row': op_gda_add_row,
           'copy_resource': op_copy_resource, 'arm9_patch': op_arm9_patch,
           'gda_clone_rows': op_gda_clone_rows, 'are_cell': op_are_cell,
           'item_name': op_item_name, 'item_desc': op_item_desc,
           'chao_name': op_chao_name, 'chao_desc': op_chao_desc}

    def apply(self, edits):
        for i, e in enumerate(edits):
            op = e.get('op')
            fn = self.OPS.get(op)
            if fn is None:
                raise ValueError(f"edit {i}: unknown op {op!r}; "
                                 f"known ops are {sorted(self.OPS)}")
            self.applied.append(fn(self, e))

    def finish(self, out_dir, name, make_patch=True):
        probs = self.herf.validate()
        if probs:
            raise RuntimeError(f"archive structurally invalid: {probs[:3]}")
        new_rom, br = self.rom.build({self.herf_fid: self.herf.serialize(),
                                      self.tlk_fid: self.tlk.serialize()})
        if self.arm9_patches:
            buf = bytearray(new_rom)
            for off, payload in self.arm9_patches:
                buf[off:off + len(payload)] = payload
            # the ARM9 sits before the filesystem and does not move, but the header
            # checksum covers the header only, so recompute it after touching bytes
            from rom_build import crc16_modbus
            import struct as _s
            _s.pack_into('<H', buf, 0x15E, crc16_modbus(bytes(buf[:0x15E])))
            new_rom = bytes(buf)
        # regression sweep over everything we can parse
        rebuilt = Rom(new_rom)
        rb = HerfFile(rebuilt.file_bytes(rebuilt.file_id(ARCHIVE)))
        bad = []
        for i, n in rb.names.items():
            low = n.lower()
            try:
                if low.endswith(('.itm', '.spl')):
                    parse_2da(rb.read(i))
                elif low.endswith('.gda'):
                    read_gda(GFF4(rb.read(i)))
            except Exception as ex:
                bad.append((n, str(ex)))
        if bad:
            raise RuntimeError(f"{len(bad)} resources no longer parse: {bad[:3]}")

        slug = ''.join(c if c.isalnum() else '_' for c in name).strip('_').lower()
        out_rom = os.path.join(out_dir, f'{slug}.nds')
        with open(out_rom, 'wb') as f:
            f.write(new_rom)
        if not make_patch:
            return new_rom, br, out_rom, None, 0
        patch = bps.create(self.original, new_rom, json.dumps({'mod': name}).encode())
        out_patch = os.path.join(out_dir, f'{slug}.bps')
        with open(out_patch, 'wb') as f:
            f.write(patch)
        if bps.apply(self.original, patch) != new_rom:
            raise RuntimeError('patch does not reproduce the rebuilt ROM')
        return new_rom, br, out_rom, out_patch, len(patch)


def resolve_extends(profile, path, _seen=None):
    """Fold in a parent profile named by `extends`.

    A profile may build on another:  {"extends": "ultimate_lifeform.json", ...}

    The parent's edits and features are applied FIRST, so the child wins wherever
    they touch the same thing — the same precedence features already have against
    hand-written edits. This lets the GUI emit a small feature-only profile that
    still carries a large hand-written base such as the Shadow Mode work, instead
    of the two being mutually exclusive.
    """
    parent_name = profile.get('extends')
    if not parent_name:
        return profile
    _seen = _seen or set()
    base_dir = os.path.dirname(os.path.abspath(path))
    parent_path = parent_name if os.path.isabs(parent_name) else         os.path.join(base_dir, parent_name)
    if not os.path.exists(parent_path):
        raise FileNotFoundError('extends: no such profile %r' % parent_path)
    real = os.path.realpath(parent_path)
    if real in _seen:
        raise ValueError('extends: circular reference via %r' % parent_name)
    _seen.add(real)
    with open(parent_path, encoding='utf-8') as f:
        parent = resolve_extends(json.load(f), parent_path, _seen)
    merged = dict(parent)
    merged.update({k: v for k, v in profile.items() if k != 'extends'})
    merged['edits'] = (parent.get('edits') or []) + (profile.get('edits') or [])
    feats = dict(parent.get('features') or {})
    feats.update(profile.get('features') or {})
    merged['features'] = feats
    merged['description'] = ((parent.get('description', '') + ' ').strip() + ' ' +
                             profile.get('description', '')).strip()
    print(f"  extends {os.path.basename(parent_path)}: "
          f"+{len(parent.get('edits') or [])} edits, "
          f"+{len(parent.get('features') or {})} features")
    return merged


def load_column_names(path='research/phase0/gda_columns.tsv'):
    names = {}
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            next(f)
            for line in f:
                h, nm, cnt, ex = line.rstrip('\n').split('\t')
                if nm:
                    names[int(h)] = nm
    return names


def _clobber_guard(out_dir, name, profile_path):
    """Refuse to overwrite a built ROM that came from a *different* profile.

    The output filename is the profile's `name` slugified, so two profiles that happen
    to share a name write to the same file and the second silently destroys the first.
    That matters because a built ROM is often the one actually being played, with a
    matching emulator save beside it — the user's `ultimate_lifeform.nds` is exactly
    this case. Rebuilding a profile over its own output is normal and stays allowed;
    only a cross-profile clobber is blocked, and `--overwrite` forces it.
    """
    slug = ''.join(c if c.isalnum() else '_' for c in name).strip('_').lower()
    out_rom = os.path.join(out_dir, f'{slug}.nds')
    report = os.path.join(out_dir, f'{slug}_report.json')
    if not os.path.exists(out_rom) or not os.path.exists(report):
        return None
    try:
        with open(report, encoding='utf-8') as f:
            prior = json.load(f).get('profile')
    except Exception:
        return None
    if not prior or os.path.abspath(prior) == os.path.abspath(profile_path):
        return None
    return '\n'.join([
        f"!! {out_rom} was built from {prior}, not {os.path.abspath(profile_path)}.",
        f"   Two profiles are named {name!r}, so this build would overwrite that ROM"
        f" (and orphan any emulator save beside it).",
        "   Rename this profile's \"name\" field, or pass --overwrite if you really"
        " mean to replace it.",
    ])


def main():
    if '--list-features' in sys.argv:
        print('Available features (profile key -> status):\n')
        for fname in sorted(features.REGISTRY):
            conf = features.CONFIRMED[fname]
            doc = (features.REGISTRY[fname].__doc__ or '').strip().splitlines()[0]
            mark = 'confirmed in game' if conf == 'game' else 'build-verified only'
            print('  %-16s [%-19s] %s' % (fname, mark, doc))
        print('\nCharacter swapping lives in randomize_characters (recruitment); see features.py.')
        sys.exit(0)
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    rom_path, profile_path = sys.argv[1], sys.argv[2]
    out_dir = 'build'
    if '--out-dir' in sys.argv:
        out_dir = sys.argv[sys.argv.index('--out-dir') + 1]
    os.makedirs(out_dir, exist_ok=True)

    with open(profile_path, encoding='utf-8') as f:
        profile = json.load(f)
    profile = resolve_extends(profile, profile_path)
    name = profile.get('name') or os.path.splitext(os.path.basename(profile_path))[0]
    edits = profile.get('edits', [])

    print(f"=== {name} ===")
    guard = _clobber_guard(out_dir, name, profile_path)
    if guard and '--overwrite' not in sys.argv:
        print(guard)
        sys.exit(1)
    if not verify_noop(rom_path):
        print("!! no-op rebuild is not byte-identical; aborting")
        sys.exit(1)

    b = Build(rom_path, load_column_names())
    if b.herf.serialize() != b.rom.file_bytes(b.herf_fid) or \
       b.tlk.serialize() != b.rom.file_bytes(b.tlk_fid):
        print("!! a no-op serialize differs from input; aborting")
        sys.exit(1)
    print(f"  source CRC32 {zlib.crc32(b.original) & 0xFFFFFFFF:08X}")

    # Named features expand into ordinary edits, so there is one apply/verify path
    # and features cannot drift from it. They run first, so an explicit `edits`
    # entry can still override whatever a feature produced.
    feats = profile.get('features') or {}
    if feats:
        try:
            expanded, summary = features.expand(feats, b)
        except Exception as e:
            print(f"\n!! feature expansion failed: {e}")
            sys.exit(1)
        for fname, conf, n in summary:
            mark = 'confirmed in game' if conf == 'game' else 'build-verified only'
            print(f"  feature {fname:18} {n:5d} edits   [{mark}]")
        edits = expanded + edits
    print(f"  profile: {profile_path}  ({len(edits)} edits)")

    try:
        b.apply(edits)
    except Exception as e:
        print(f"\n!! edit failed: {e}")
        sys.exit(1)
    for line in b.applied[:40]:
        print(f"    {line}")
    if len(b.applied) > 40:
        print(f"    ... and {len(b.applied) - 40} more")

    try:
        new_rom, br, out_rom, out_patch, psize = b.finish(
            out_dir, name, make_patch='--no-patch' not in sys.argv)
    except Exception as e:
        print(f"\n!! build failed: {e}")
        sys.exit(1)

    print(f"  wrote {out_rom}  (CRC32 {zlib.crc32(new_rom) & 0xFFFFFFFF:08X}, "
          f"files moved {br['moved_files']})")
    if out_patch:
        print(f"  wrote {out_patch} ({psize} bytes), verified")
    else:
        print("  patch skipped (--no-patch); the ROM is still fully verified")
    report = os.path.join(out_dir, f'{os.path.basename(out_rom)[:-4]}_report.json')
    with open(report, 'w', encoding='utf-8') as f:
        json.dump({'generated': time.strftime('%Y-%m-%d %H:%M:%S'), 'mod': name,
                   'profile': os.path.abspath(profile_path),
                   'edits': len(edits), 'applied': b.applied,
                   'output_rom': os.path.abspath(out_rom),
                   'patch_bytes': psize,
                   'patch_skipped': out_patch is None}, f, indent=2)
    print(f"  report {report}")
    print("ALL STAGES PASSED")


if __name__ == '__main__':
    main()
