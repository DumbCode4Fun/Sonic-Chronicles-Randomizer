"""
Phase 0 reconnaissance: parse an NDS ROM header + filesystem (FNT/FAT) + overlay
tables using only the Python standard library. Read-only: never writes to the ROM.

Usage:
    py nds_rom.py <rom.nds> [out_dir]

Produces <out_dir>/<rom_stem>_report.txt and <out_dir>/<rom_stem>_filelist.tsv.
"""
import struct
import sys
import os


def read_header(data):
    h = {}
    h['game_title'] = data[0x00:0x0C].rstrip(b'\x00').decode('ascii', 'replace')
    h['game_code'] = data[0x0C:0x10].decode('ascii', 'replace')
    h['maker_code'] = data[0x10:0x12].decode('ascii', 'replace')
    h['unit_code'] = data[0x12]
    h['encryption_seed_select'] = data[0x13]
    h['device_capacity_raw'] = data[0x14]
    h['device_capacity_bytes'] = 128 * 1024 << data[0x14]
    h['rom_version'] = data[0x1E]
    h['autostart'] = data[0x1F]

    (h['arm9_rom_offset'], h['arm9_entry'], h['arm9_ram'], h['arm9_size']) = struct.unpack_from('<IIII', data, 0x20)
    (h['arm7_rom_offset'], h['arm7_entry'], h['arm7_ram'], h['arm7_size']) = struct.unpack_from('<IIII', data, 0x30)
    (h['fnt_offset'], h['fnt_size']) = struct.unpack_from('<II', data, 0x40)
    (h['fat_offset'], h['fat_size']) = struct.unpack_from('<II', data, 0x48)
    (h['arm9_ovl_offset'], h['arm9_ovl_size']) = struct.unpack_from('<II', data, 0x50)
    (h['arm7_ovl_offset'], h['arm7_ovl_size']) = struct.unpack_from('<II', data, 0x58)
    (h['icon_title_offset'],) = struct.unpack_from('<I', data, 0x68)
    (h['secure_area_crc'],) = struct.unpack_from('<H', data, 0x6C)
    (h['total_used_rom_size'],) = struct.unpack_from('<I', data, 0x80)
    (h['header_size'],) = struct.unpack_from('<I', data, 0x84)
    (h['header_crc16'],) = struct.unpack_from('<H', data, 0x15E)
    return h


def parse_fnt_fat(data, h):
    fnt_off = h['fnt_offset']
    fat_off = h['fat_offset']
    fat_size = h['fat_size']
    num_files = fat_size // 8

    fat = []
    for i in range(num_files):
        start, end = struct.unpack_from('<II', data, fat_off + i * 8)
        fat.append((start, end))

    _, _, num_dirs = struct.unpack_from('<IHH', data, fnt_off)

    files = []  # (path, file_id, start, end, size)
    dirs = []   # (path, dir_id)

    def walk(dir_id, path):
        main_entry_off = fnt_off + (dir_id & 0xFFF) * 8
        subtable_off, first_file_id, _ = struct.unpack_from('<IHH', data, main_entry_off)
        pos = fnt_off + subtable_off
        file_id = first_file_id
        while True:
            type_len = data[pos]
            pos += 1
            if type_len == 0x00:
                break
            elif 0x01 <= type_len <= 0x7F:
                name = data[pos:pos + type_len].decode('ascii', 'replace')
                pos += type_len
                start, end = fat[file_id] if file_id < len(fat) else (0, 0)
                files.append((f"{path}{name}", file_id, start, end, end - start))
                file_id += 1
            elif 0x81 <= type_len <= 0xFF:
                name_len = type_len & 0x7F
                name = data[pos:pos + name_len].decode('ascii', 'replace')
                pos += name_len
                (sub_id,) = struct.unpack_from('<H', data, pos)
                pos += 2
                child_path = f"{path}{name}/"
                dirs.append((child_path, sub_id))
                walk(sub_id, child_path)
            else:
                break

    walk(0xF000, "/")
    return files, dirs, num_dirs, num_files


def parse_overlays(data, offset, size):
    entries = []
    count = size // 32
    for i in range(count):
        (ovl_id, ram_addr, ram_size, bss_size, sinit_start, sinit_end, file_id, comp_flags) = \
            struct.unpack_from('<IIIIIIII', data, offset + i * 32)
        compressed_size = comp_flags & 0xFFFFFF
        flags = (comp_flags >> 24) & 0xFF
        entries.append({
            'overlay_id': ovl_id, 'ram_address': ram_addr, 'ram_size': ram_size,
            'bss_size': bss_size, 'static_init_start': sinit_start, 'static_init_end': sinit_end,
            'file_id': file_id, 'compressed_size': compressed_size, 'flags': flags,
            'is_compressed': bool(flags & 1),
        })
    return entries


SIGNATURES = [
    (b'GFF ', 'GFF (BioWare Generic File Format)'),
    (b'BMD0', 'NSBMD (3D model)'),
    (b'BTX0', 'NSBTX (texture archive)'),
    (b'BCA0', 'NSBCA (skeletal animation)'),
    (b'NCGR', 'NCGR (tile graphics)'),
    (b'NCLR', 'NCLR (palette)'),
    (b'NFTR', 'NFTR (font)'),
    (b'SDAT', 'SDAT (sound archive)'),
]


def classify_file(data, start, end):
    size = end - start
    if size <= 0:
        return 'empty', None
    peek = data[start:start + 4]
    for magic, label in SIGNATURES:
        if peek == magic:
            return 'magic', label
    first_byte = data[start]
    if first_byte in (0x10, 0x11) and size > 4:
        decomp_size = data[start + 1] | (data[start + 2] << 8) | (data[start + 3] << 16)
        kind = 'LZSS/LZ77 (type 0x10)' if first_byte == 0x10 else 'LZ11 (type 0x11)'
        return 'compressed', f'{kind}, decompressed size={decomp_size}'
    return 'unknown', None


def report(rom_path, out_dir):
    with open(rom_path, 'rb') as f:
        data = f.read()

    h = read_header(data)
    files, dirs, num_dirs, num_files = parse_fnt_fat(data, h)
    arm9_ovls = parse_overlays(data, h['arm9_ovl_offset'], h['arm9_ovl_size'])
    arm7_ovls = parse_overlays(data, h['arm7_ovl_offset'], h['arm7_ovl_size'])

    stem = os.path.splitext(os.path.basename(rom_path))[0]
    out_path = os.path.join(out_dir, f"{stem}_report.txt")
    listing_path = os.path.join(out_dir, f"{stem}_filelist.tsv")

    ext_counts = {}
    magic_counts = {}
    for path, fid, start, end, size in files:
        ext = os.path.splitext(path)[1].lower() or '(none)'
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
        kind, label = classify_file(data, start, end)
        if kind == 'magic':
            magic_counts[label] = magic_counts.get(label, 0) + 1

    with open(out_path, 'w', encoding='utf-8') as out:
        out.write(f"ROM: {rom_path}\nFile size on disk: {len(data)} bytes\n\n=== Header ===\n")
        for k, v in h.items():
            out.write(f"{k}: {v} (0x{v:X})\n" if isinstance(v, int) else f"{k}: {v!r}\n")
        out.write(f"\n=== Filesystem summary ===\nDirectories (incl. root): {num_dirs}\nFiles: {num_files}\n")
        out.write("\nExtension counts:\n")
        for ext, c in sorted(ext_counts.items(), key=lambda kv: -kv[1]):
            out.write(f"  {ext}: {c}\n")
        out.write("\n=== Magic-signature matches ===\n")
        for label, c in sorted(magic_counts.items(), key=lambda kv: -kv[1]):
            out.write(f"  {label}: {c}\n")
        out.write(f"\n=== ARM9 overlays === count: {len(arm9_ovls)}\n")
        for o in arm9_ovls:
            out.write(f"  {o}\n")
        out.write(f"\n=== ARM7 overlays === count: {len(arm7_ovls)}\n")
        for o in arm7_ovls:
            out.write(f"  {o}\n")

    with open(listing_path, 'w', encoding='utf-8') as out:
        out.write("path\tfile_id\tstart\tend\tsize\n")
        for path, fid, start, end, size in sorted(files):
            out.write(f"{path}\t{fid}\t{start}\t{end}\t{size}\n")

    return h, files


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rom_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else '.'
    os.makedirs(out_dir, exist_ok=True)
    h, files = report(rom_path, out_dir)
    print(f"title={h['game_title']!r} code={h['game_code']!r} maker={h['maker_code']!r} "
          f"version={h['rom_version']} files={len(files)} headerCRC=0x{h['header_crc16']:04X}")
