"""
Reader for this game's `.small` resources. Pure standard library.

`.small` is a 4-byte wrapper around a payload:
    byte  0     compression type: 0x00 = stored (raw), 0x10 = LZ77/LZSS
    bytes 1-3   payload (decompressed) size, 24-bit little-endian
    bytes 4+    the payload itself

For type 0x00 the payload is copied out verbatim. For type 0x10 it is an LZ77
stream, decoded as below.
Then, repeating until the output reaches the declared size:
    one flag byte, bits processed MSB (bit 7) -> LSB (bit 0), each bit describing
    one block:
      bit 0 -> literal: copy the next 1 byte straight to the output
      bit 1 -> back-reference: read 2 bytes B1,B2;
               length = (B1 >> 4) + 3
               disp   = (((B1 & 0x0F) << 8) | B2) + 1
               copy `length` bytes from (outputPos - disp), one byte at a time
               so that overlapping/self-referencing copies work.

Usage as a library:
    from lz77 import decompress, is_lz77
    raw = decompress(data, offset)

Usage as a CLI:
    py lz77.py <rom.nds> <herf_contents.tsv> [out_dir]
      Validates every `.small` resource listed in the TSV, and (if out_dir is
      given) writes the decompressed files there.
"""
import os
import sys


STORED = 0x00
LZ77 = 0x10


def is_lz77(data: bytes, offset: int = 0) -> bool:
    return len(data) > offset + 4 and data[offset] == LZ77


def declared_size(data: bytes, offset: int = 0) -> int:
    return data[offset + 1] | (data[offset + 2] << 8) | (data[offset + 3] << 16)


def read_small(data: bytes, offset: int, limit: int) -> bytearray:
    """Read a `.small` resource (either compression type) and return its payload."""
    ctype = data[offset]
    if ctype == STORED:
        size = declared_size(data, offset)
        return bytearray(data[offset + 4:offset + 4 + size])
    if ctype == LZ77:
        return decompress(data, offset, limit=limit)
    raise ValueError(f"unknown .small compression type 0x{ctype:02X} at 0x{offset:X}")


def decompress(data: bytes, offset: int = 0, limit: int = None) -> bytearray:
    """Decompress the LZ77 stream starting at `offset`. `limit` optionally caps
    how far into `data` we may read (i.e. the compressed resource's size)."""
    if data[offset] != LZ77:
        raise ValueError(f"not LZ77 type 0x10 (got 0x{data[offset]:02X}) at 0x{offset:X}")

    size = declared_size(data, offset)
    end = offset + limit if limit is not None else len(data)
    pos = offset + 4
    out = bytearray()

    while len(out) < size:
        if pos >= end:
            raise ValueError(f"ran out of input at 0x{pos:X} with {len(out)}/{size} bytes decoded")
        flags = data[pos]
        pos += 1
        for bit in range(7, -1, -1):
            if len(out) >= size:
                break
            if pos >= end:
                raise ValueError(f"ran out of input mid-block at 0x{pos:X}")
            if (flags >> bit) & 1:
                b1 = data[pos]
                b2 = data[pos + 1]
                pos += 2
                length = (b1 >> 4) + 3
                disp = (((b1 & 0x0F) << 8) | b2) + 1
                if disp > len(out):
                    raise ValueError(f"back-reference before start of output (disp={disp}, have={len(out)})")
                for _ in range(length):
                    out.append(out[len(out) - disp])
                    if len(out) >= size:
                        break
            else:
                out.append(data[pos])
                pos += 1

    return out


# Nitro-format magics, as stored on disk (little-endian, so they read reversed).
NITRO_MAGICS = {
    b'RGCN': 'NCGR (tile graphics)',
    b'RLCN': 'NCLR (palette)',
    b'RECN': 'NCER (cell bank)',
    b'RNAN': 'NANR (cell animation)',
    b'RCSN': 'NSCR (tilemap)',
    b'RTFN': 'NFTR (font)',
    b'BTX0': 'NSBTX (texture archive)',
    b'BMD0': 'NSBMD (3D model)',
    b'BCA0': 'NSBCA (skeletal/joint animation)',
    b'BTP0': 'NSBTP (texture pattern animation)',
    b'BTA0': 'NSBTA (texture SRT animation)',
    b'BVA0': 'NSBVA (visibility animation)',
    b'BMA0': 'NSBMA (material animation)',
}


def inspect(raw: bytes):
    """Light sanity check on a decompressed Nitro file: returns (label, internal_size)."""
    magic = bytes(raw[:4])
    label = NITRO_MAGICS.get(magic)
    internal = None
    if label and len(raw) >= 16:
        # Standard Nitro header: magic(4) BOM(2) version(2) filesize(4) headersize(2) sections(2)
        internal = raw[8] | (raw[9] << 8) | (raw[10] << 16) | (raw[11] << 24)
    return label, magic, internal


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    rom_path, tsv_path = sys.argv[1], sys.argv[2]
    out_dir = sys.argv[3] if len(sys.argv) > 3 else None
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(rom_path, 'rb') as f:
        data = f.read()

    rows = []
    with open(tsv_path, encoding='utf-8') as f:
        next(f)
        for line in f:
            name, h, size, off_in_herf, abs_off = line.rstrip('\n').split('\t')
            if name.lower().endswith('.small'):
                rows.append((name, int(size), int(abs_off)))

    ok = 0
    failures = []
    type_counts = {}
    magic_counts = {}
    size_mismatch = []

    for name, size, abs_off in rows:
        ctype = data[abs_off]
        type_counts[ctype] = type_counts.get(ctype, 0) + 1
        try:
            raw = read_small(data, abs_off, limit=size)
        except Exception as e:
            failures.append((name, str(e)))
            continue

        declared = declared_size(data, abs_off)
        if len(raw) != declared:
            size_mismatch.append((name, len(raw), declared))

        label, magic, internal = inspect(raw)
        key = label or f"unrecognized magic {magic!r}"
        magic_counts[key] = magic_counts.get(key, 0) + 1
        if internal is not None and internal != len(raw):
            size_mismatch.append((name, f"internal={internal}", f"actual={len(raw)}"))
        ok += 1

        if out_dir:
            inner = name[:-len('.small')]
            safe = inner.replace('/', '_').replace('\\', '_')
            with open(os.path.join(out_dir, safe), 'wb') as o:
                o.write(raw)

    print(f"total .small resources: {len(rows)}")
    print(f"read successfully: {ok}")
    print(f"failures: {len(failures)}")
    print(f"size mismatches (declared vs actual, or Nitro-internal vs actual): {len(size_mismatch)}")
    print("\nby compression type:")
    for t, v in sorted(type_counts.items()):
        label = {STORED: 'stored/raw', LZ77: 'LZ77'}.get(t, 'unknown')
        print(f"  0x{t:02X} ({label}): {v}")
    print("\npayload content by detected format:")
    for k, v in sorted(magic_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v}")
    if failures[:5]:
        print("\nsample failures:", failures[:5])
    if size_mismatch[:5]:
        print("\nsample size mismatches:", size_mismatch[:5])


if __name__ == '__main__':
    main()
