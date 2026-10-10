"""
Recover GDA column names from their hashes by dictionary attack.

GDA (GFF4-wrapped 2DA) tables identify columns only by a 32-bit hash, not by
name. The hash is:

    crc32( column_name.lower().encode('utf-16-le') )

(verified: probes for "id", "label", "name", "hp", "attack" all matched hashes
present in the ROM's tables on the first try).

This script builds a candidate wordlist — hand-curated game/RPG terms, plus
tokens harvested from the game's own resource names and 2DA vocabularies — hashes
each candidate, and reports which of the ROM's 845 distinct column hashes it can
name. Recovered names are written to a TSV for reuse so the attack doesn't have
to be repeated.

Usage:
    py gda_dict.py <rom.nds> <herf_contents.tsv> [out.tsv]
"""
import collections
import itertools
import os
import re
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gff4 import GFF4, read_gda, load_index  # noqa: E402
from twoda import parse_2da  # noqa: E402


def gda_hash(name: str) -> int:
    return zlib.crc32(name.lower().encode('utf-16-le')) & 0xFFFFFFFF


# Hand-curated vocabulary: generic table/record fields, stats, combat, economy,
# progression, and Sonic-Chronicles-specific terms.
BASE_WORDS = """
id label name type subtype value index key order sort group category class kind
icon image portrait model texture anim animation sound sfx vfx effect script
desc description text string strref tooltip help title header footer
hp maxhp minhp fp maxfp pp mp atk attack def defense defence spd speed lck luck
pow power grt grit sta stamina fatigue level lvl xp exp experience ap cost price
value gold rings money buy sell shop stock rarity weight slot equip equipped
usable consumable stackable quantity count amount number num total sum
min max base bonus mod modifier multiplier percent pct rate chance prob probability
duration time turns rounds delay cooldown recharge range radius area target
targets targeting element resist resistance immunity weakness status ailment
damage dmg heal cure revive buff debuff stun poison burn freeze shock curse
sleep slow haste shield guard block dodge evade crit critical accuracy hit miss
char character hero player party member slot active leader recruit unlock
enemy monster boss creature race faction team ally foe npc
chapter area zone map room scene stage level world region spawn encounter
quest mission objective reward drop loot treasure chest
chao egg pet companion bonus ability skill spell move combo special
tier rank grade stars upgrade evolve growth curve table formula
gender size color colour palette frame width height x y z scale rot rotation
pos position offset start end first last next prev parent child root
flag flags bit mask enabled disabled visible hidden locked active inactive
sonic tails knuckles amy shadow rouge cream big omega eggman shade ix
kron nocturn voxai zoah nrrgal charyb gizoid metal robot animal
fire water earth wind lightning ice light dark neutral
"""


def build_candidates(resource_names, extra_tokens):
    words = set(w for w in BASE_WORDS.split() if w)
    words |= set(extra_tokens)

    # Harvest tokens from resource names: split on separators and camelCase.
    for rn in resource_names:
        stem = os.path.splitext(rn)[0]
        for part in re.split(r'[_\.\-\s]+', stem):
            if not part:
                continue
            words.add(part.lower())
            for piece in re.findall(r'[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+|\d+', part):
                if len(piece) > 1:
                    words.add(piece.lower())

    words = {w for w in words if 1 <= len(w) <= 24}

    candidates = set(words)
    # Common decorations.
    for w in list(words):
        candidates.update((w + 's', w + 'id', w + '_id', w + 'name', w + '_name',
                           w + 'type', w + '_type', w + 'count', w + '_count',
                           'max' + w, 'max_' + w, 'min' + w, 'min_' + w,
                           'base' + w, 'base_' + w, 'num' + w, 'num_' + w,
                           w + 'bonus', w + '_bonus', w + 'mod', w + '_mod'))

    # Pairwise joins of a focused subset (full cross-product would explode).
    focus = [w for w in words if len(w) <= 10]
    core = ['hp', 'fp', 'atk', 'def', 'spd', 'lck', 'pow', 'grt', 'xp', 'ap',
            'level', 'cost', 'value', 'name', 'id', 'icon', 'type', 'min', 'max',
            'base', 'bonus', 'mod', 'rate', 'chance', 'element', 'resist',
            'damage', 'target', 'duration', 'count', 'index', 'label']
    for a, b in itertools.product(core, focus):
        if a != b:
            candidates.add(a + b)
            candidates.add(a + '_' + b)
            candidates.add(b + a)
            candidates.add(b + '_' + a)
    return candidates


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    rom_path, tsv_path = sys.argv[1], sys.argv[2]
    out_path = sys.argv[3] if len(sys.argv) > 3 else None
    sys.stdout.reconfigure(encoding='utf-8')

    with open(rom_path, 'rb') as f:
        data = f.read()
    index = load_index(tsv_path)

    # Collect every distinct column hash, and which tables use it.
    hash_tables = collections.defaultdict(list)
    gdas = sorted(n for n in index if n.lower().endswith('.gda'))
    for n in gdas:
        size, off = index[n]
        g = GFF4(data[off:off + size])
        cols, _rows = read_gda(g)
        for c in cols:
            hash_tables[c['hash']].append(n)

    # Harvest extra tokens from the plain-text 2DA vocabularies.
    extra = set()
    for n in index:
        if n.lower().endswith(('.itm', '.spl')):
            size, off = index[n]
            try:
                t = parse_2da(data[off:off + size])
            except Exception:
                continue
            extra.update(c.lower() for c in t.columns)
            for lbl, _ in t.rows:
                extra.add(re.sub(r'[^A-Za-z0-9_]', '', lbl).lower())

    candidates = build_candidates(list(index.keys()), extra)
    print(f"distinct column hashes in ROM: {len(hash_tables)}")
    print(f"candidate names generated: {len(candidates)}")

    recovered = {}
    for cand in candidates:
        h = gda_hash(cand)
        if h in hash_tables and h not in recovered:
            recovered[h] = cand

    pct = 100.0 * len(recovered) / len(hash_tables) if hash_tables else 0
    print(f"recovered: {len(recovered)}/{len(hash_tables)} ({pct:.1f}%)")

    by_use = sorted(hash_tables.items(), key=lambda kv: -len(kv[1]))
    print("\nmost widely used columns (hash -> name, table count):")
    for h, tables in by_use[:25]:
        print(f"  {h:<12} {recovered.get(h, '?'):<24} {len(tables)} tables")

    unknown_common = [(h, len(t)) for h, t in by_use if h not in recovered]
    print(f"\nstill-unknown hashes: {len(unknown_common)}; most used:")
    for h, cnt in unknown_common[:12]:
        print(f"  {h:<12} used in {cnt} tables (e.g. {hash_tables[h][0]})")

    if out_path:
        with open(out_path, 'w', encoding='utf-8') as out:
            out.write("hash\tname\ttable_count\texample_table\n")
            for h, tables in by_use:
                out.write(f"{h}\t{recovered.get(h, '')}\t{len(tables)}\t{tables[0]}\n")
        print(f"\nwrote {out_path}")


if __name__ == '__main__':
    main()
