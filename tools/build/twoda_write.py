"""
Field-level editor for the plain-text 2DA tables (`.itm`, `.spl`, `.2da`).

This is the cheapest modding surface in the game: item stats and ability
magnitudes live in these tables, and ability upgrade tiers differ only in a single
`Data` value (see REVERSE_ENGINEERING_LOG.md), so rebalancing is literally a
one-number change.

Editing them as raw text with a hand-rolled regex is a trap, because the files are
inconsistently delimited — most rows use tabs, some use runs of spaces, values may
carry trailing spaces (`10 `), and item names contain single spaces. This module
edits a cell **by row label and column name**, rewriting only that field's
characters and leaving every other byte — including the file's cosmetic
alignment padding — untouched.

Usage as a library:
    from twoda_write import set_cell
    new_bytes, note = set_cell(raw_bytes, 'GRT+', 'Data', '99')
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'recon'))

from twoda import parse_2da, split_row  # noqa: E402

ENCODING = 'cp1252'


def _field_spans(line: str):
    """Character spans of each field in a 2DA line, using the same delimiter rule
    as the reader: a tab, or a run of 2+ spaces, separates fields."""
    spans = []
    pos = 0
    for part in re.split(r'(\t|\s{2,})', line):
        if not part:
            continue
        if re.fullmatch(r'\t|\s{2,}', part):
            pos += len(part)
            continue
        stripped = part.strip()
        if stripped:
            lead = len(part) - len(part.lstrip())
            spans.append((pos + lead, pos + lead + len(stripped)))
        pos += len(part)
    return spans


def set_cell(raw: bytes, row_label: str, column: str, value, allow_noop=False) -> tuple:
    """Return (new_bytes, note). Raises if the row or column isn't found.

    By default also raises when the cell already holds `value`, which catches a
    mistargeted edit in one-off use. Bulk rewriting (e.g. applying a whole
    rebalance where some items already match) should pass `allow_noop=True`.
    """
    table = parse_2da(raw)
    if column not in table.columns:
        raise KeyError(f"no column {column!r}; columns are {table.columns}")
    col_index = table.columns.index(column)

    text = raw.decode(ENCODING)
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = text.split(newline)

    value = str(value)
    for i, line in enumerate(lines):
        fields = split_row(line)
        if not fields or fields[0] != row_label:
            continue
        # field 0 is the row label, so the column's field index is offset by one
        target = col_index + 1
        spans = _field_spans(line)
        if target >= len(spans):
            raise ValueError(f"row {row_label!r} has {len(spans) - 1} values, "
                             f"cannot set column index {col_index}")
        s, e = spans[target]
        old = line[s:e]
        if old == value:
            if not allow_noop:
                raise ValueError(f"{row_label}.{column} is already {value!r}")
            return raw, f"{row_label}.{column}: already {value!r}, unchanged" 
        lines[i] = line[:s] + value + line[e:]
        new_raw = newline.join(lines).encode(ENCODING)
        # Prove the change took, through the reader rather than by assumption.
        check = parse_2da(new_raw).get(row_label)
        if check is None or check[column] != value:
            raise RuntimeError(f"edit did not round-trip: {row_label}.{column} "
                               f"reads back as {check and check[column]!r}")
        return new_raw, f"{row_label}.{column}: {old!r} -> {value!r}"

    raise KeyError(f"no row labelled {row_label!r}; labels are {table.labels[:12]}")


def add_row(raw: bytes, row_label: str, values: dict) -> tuple:
    """Append a row to a 2DA. `values` maps column name -> value; columns not
    given are filled with '0'. The `ID` column is auto-assigned as the next
    sequential index, matching how the game's own tables number their rows.

    Formatting follows the file's existing style: fields are tab-separated, which
    the reader accepts regardless of the cosmetic alignment used elsewhere in the
    file.
    """
    table = parse_2da(raw)
    text = raw.decode(ENCODING)
    newline = '\r\n' if '\r\n' in text else '\n'

    next_id = 0
    for _, vals in table.rows:
        try:
            next_id = max(next_id, int(vals.get('ID', 0)) + 1)
        except (TypeError, ValueError):
            pass

    cells = []
    for col in table.columns:
        if col == 'ID':
            cells.append(str(next_id))
        else:
            cells.append(str(values.get(col, '0')))
    line = row_label + '\t' + '\t'.join(cells)

    lines = text.split(newline)
    while lines and not lines[-1].strip():
        lines.pop()
    lines.append(line)
    new_raw = (newline.join(lines) + newline).encode(ENCODING)

    check = parse_2da(new_raw)
    if len(check.rows) != len(table.rows) + 1:
        raise RuntimeError(f"row count {len(check.rows)}, expected {len(table.rows) + 1}")
    # Verify the row we actually appended — the last one. Looking it up by label
    # would find the FIRST row with that label, which is wrong whenever a label
    # repeats (e.g. an item carrying several VFX rows).
    got_label, got = check.rows[-1]
    if got_label != row_label:
        raise RuntimeError(f"appended row is labelled {got_label!r}, expected {row_label!r}")
    for col, want in values.items():
        if got.get(col) != str(want):
            raise RuntimeError(f"{row_label}.{col} reads back as {got.get(col)!r}, expected {want!r}")
    return new_raw, f"added row {row_label} (ID {next_id}): {values}"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    print(__doc__)


if __name__ == '__main__':
    main()
