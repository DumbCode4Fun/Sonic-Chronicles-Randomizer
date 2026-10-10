"""
Parser for this game's plain-text 2DA tables (`.2da`, `.itm`, `.spl`).

Layout, as confirmed against the game's files:
    line 1   "2DA V2.0" followed by space padding
    line 2   blank
    line 3   column header row: leading whitespace (the row-label column has no
             name), then the column names
    line 4+  data rows: a row label, then one value per column

Delimiting is **inconsistent within the same file** — these are hand-maintained
files and both conventions appear:
  * most rows are tab-delimited, with runs of tabs used for cosmetic alignment;
  * some rows (e.g. the trailing VFX rows of Item2.ITM) use runs of spaces
    instead.
Meanwhile values themselves may contain single spaces (item names such as
"Chaos Emerald 1"), and they are *not* quoted, so this game's files don't follow
the strict BioWare 2DA convention of quoting such values.

The rule that satisfies all of the above: **a tab, or a run of 2+ spaces,
delimits a field; a single space belongs to the value.** Empty fields (from
alignment runs) are dropped and remaining fields stripped.

`****` (a run of asterisks) is BioWare's conventional "empty" marker.

Usage as a library:
    from twoda import parse_2da
    table = parse_2da(raw_bytes)
    table.columns          -> ['ID', 'EffectId', ...]
    table.rows             -> [(label, {col: value}), ...]
    table.get('HealHP')    -> {col: value} for that row label

Usage as a CLI:
    py twoda.py <rom.nds> <herf_contents.tsv> <name>      # dump one table
    py twoda.py <rom.nds> <herf_contents.tsv> --ext .itm  # audit every table
"""
import re
import sys


EMPTY = '****'


def split_row(line: str):
    """Split a 2DA line into fields. A tab, or a run of 2+ spaces, delimits;
    a single space is kept as part of the value (item names contain them and
    are not quoted in this game's files)."""
    return [f.strip() for f in re.split(r'\t|\s{2,}', line) if f.strip()]


class Table:
    def __init__(self, version, columns, rows):
        self.version = version
        self.columns = columns
        self.rows = rows  # list of (label, dict)

    def get(self, label):
        for lbl, vals in self.rows:
            if lbl == label:
                return vals
        return None

    @property
    def labels(self):
        return [lbl for lbl, _ in self.rows]


def parse_2da(raw: bytes) -> Table:
    text = raw.decode('ascii', 'replace')
    lines = text.splitlines()
    if not lines or not lines[0].startswith('2DA'):
        raise ValueError(f"not a 2DA file (first line: {lines[0][:32]!r})")
    version = lines[0].strip()

    # Find the header row: first non-blank line after line 0.
    idx = 1
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx >= len(lines):
        return Table(version, [], [])

    columns = split_row(lines[idx])
    rows = []
    for line in lines[idx + 1:]:
        if not line.strip():
            continue
        parts = split_row(line)
        label, values = parts[0], parts[1:]
        # Pad/truncate defensively so a malformed row can't silently shift columns.
        vals = {}
        for i, col in enumerate(columns):
            vals[col] = values[i] if i < len(values) else None
        rows.append((label, vals))
        if len(values) != len(columns):
            vals['__arity_mismatch__'] = f"{len(values)} values vs {len(columns)} columns"
    return Table(version, columns, rows)


def load_index(tsv_path):
    index = {}
    with open(tsv_path, encoding='utf-8') as f:
        next(f)
        for line in f:
            name, h, size, oih, abs_off = line.rstrip('\n').split('\t')
            index[name] = (int(size), int(abs_off))
    return index


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    rom_path, tsv_path, target = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(rom_path, 'rb') as f:
        data = f.read()
    index = load_index(tsv_path)
    sys.stdout.reconfigure(encoding='utf-8')

    if target != '--ext':
        size, off = index[target]
        t = parse_2da(data[off:off + size])
        print(f"{target}: version={t.version!r} columns={t.columns}")
        for lbl, vals in t.rows:
            print(f"  {lbl:28} " + "  ".join(f"{c}={vals[c]}" for c in t.columns))
        return

    ext = sys.argv[4].lower()
    names = sorted(n for n in index if n.lower().endswith(ext))
    print(f"auditing {len(names)} '{ext}' tables\n")

    colsets = {}
    label_counts = {}
    mismatches = []
    failures = []
    for name in names:
        size, off = index[name]
        try:
            t = parse_2da(data[off:off + size])
        except Exception as e:
            failures.append((name, str(e)))
            continue
        colsets[tuple(t.columns)] = colsets.get(tuple(t.columns), 0) + 1
        for lbl, vals in t.rows:
            label_counts[lbl] = label_counts.get(lbl, 0) + 1
            if '__arity_mismatch__' in vals:
                mismatches.append((name, lbl, vals['__arity_mismatch__']))

    print(f"parse failures: {len(failures)}")
    print(f"rows whose value count != column count: {len(mismatches)}")
    print(f"\ndistinct column layouts: {len(colsets)}")
    for cols, n in sorted(colsets.items(), key=lambda kv: -kv[1]):
        print(f"  [{n} files] {list(cols)}")
    print(f"\nrow labels seen ({len(label_counts)} distinct), by frequency:")
    for lbl, n in sorted(label_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {lbl:32} {n}")
    if failures[:5]:
        print("\nsample failures:", failures[:5])
    if mismatches[:8]:
        print("\nsample arity mismatches:", mismatches[:8])


if __name__ == '__main__':
    main()
