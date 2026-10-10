"""
HERF archive parser (BioWare "Hashed ERF", used only in Sonic Chronicles: The
Dark Brotherhood). Format reverse-engineered from xoreos' herffile.cpp/.h and
confirmed against our own ROM — see REVERSE_ENGINEERING_LOG.md.

Usage as a library:
    from herf import parse_herf
    count, entries, name_map = parse_herf(data, base_offset, archive_size)

Usage as a CLI (requires a file listing produced by nds_rom.py):
    py herf.py <rom.nds> <filelist.tsv> <out_dir>
"""
import struct
import sys
import os

MAGIC = 0x00F1A5C0


def djb2_add(s: bytes) -> int:
    h = 5381
    for b in s:
        h = (h * 33 + b) & 0xFFFFFFFF
    return h


DJB2_ERFDICT = djb2_add(b'erf.dict')


def parse_herf(data: bytes, base: int, size: int):
    """Returns (resource_count, entries, name_map).
    entries: list of {'hash','size','offset'} (offset relative to `base`).
    name_map: dict hash -> name, built from the embedded erf.dict if present.
    """
    magic, count = struct.unpack_from('<II', data, base)
    if magic != MAGIC:
        raise ValueError(f"not a HERF archive (bad magic 0x{magic:X} at 0x{base:X})")

    entries = []
    off = base + 8
    for _ in range(count):
        h, sz, resoff = struct.unpack_from('<III', data, off)
        entries.append({'hash': h, 'size': sz, 'offset': resoff})
        off += 12

    name_map = {}
    for e in entries:
        if e['hash'] == DJB2_ERFDICT:
            dict_base = base + e['offset']
            _, dcount = struct.unpack_from('<II', data, dict_base)
            pos = dict_base + 8
            for _ in range(dcount):
                h = struct.unpack_from('<I', data, pos)[0]
                name = data[pos + 4:pos + 4 + 128].split(b'\x00', 1)[0].decode('ascii', 'replace')
                name_map[h] = name
                pos += 132
            break

    return count, entries, name_map


def load_listing(listing_path):
    files = []
    with open(listing_path, encoding='utf-8') as f:
        next(f)
        for line in f:
            path, fid, start, end, sz = line.rstrip('\n').split('\t')
            files.append((path, int(fid), int(start), int(end), int(sz)))
    return files


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    rom_path, listing_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)

    with open(rom_path, 'rb') as f:
        data = f.read()
    files = load_listing(listing_path)
    herfs = [t for t in files if t[0].lower().endswith('.herf')]

    for path, fid, start, end, size in herfs:
        count, entries, name_map = parse_herf(data, start, size)
        safe_name = os.path.splitext(os.path.basename(path))[0]
        out_path = os.path.join(out_dir, f"herf_{safe_name}_contents.tsv")
        with open(out_path, 'w', encoding='utf-8') as out:
            out.write("name\thash\tsize\toffset_in_herf\tabsolute_rom_offset\n")
            for e in entries:
                nm = name_map.get(e['hash'], '')
                out.write(f"{nm}\t{e['hash']}\t{e['size']}\t{e['offset']}\t{start + e['offset']}\n")
        print(f"{path}: {count} resources, {len(name_map)} names recovered -> {out_path}")


if __name__ == '__main__':
    main()
