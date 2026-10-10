"""
GFF4 (BioWare Generic File Format v4.0/4.1) reader for this game's `.gff`,
`.gda`, `.dlg`, `.gui`, `.plo`, `.are` and `.tlk` files.

Format implemented from xoreos' gff4file.cpp/.h and verified against the game's
own files — see REVERSE_ENGINEERING_LOG.md.

File layout:
    0x00  char[4]  "GFF "
    0x04  char[4]  version, "V4.0" or "V4.1"
    0x08  char[4]  platform ID, always "PC  " in this game
    0x0C  char[4]  content type FourCC (e.g. "G2DA", "CONV", "AREA", "TLK ")
    0x10  char[4]  content type version (e.g. "V0.2")
    0x14  uint32   structCount
    [V4.1 only: uint32 stringCount, uint32 stringOffset]
    uint32   dataOffset
    then structCount x 16-byte struct templates:
        uint32 label (FourCC, e.g. "gtop"/"colm"/"rows")
        uint32 fieldCount
        uint32 fieldOffset   (absolute, from file start)
        uint32 size          (byte size of one instance of this struct)
    then, at each template's fieldOffset, fieldCount x 12-byte field defs:
        uint32 label         (numeric field ID — GFF4 uses IDs, not names)
        uint32 typeAndFlags  (type = low 16 bits, flags = high 16 bits)
        uint32 offset        (offset of this field within a struct instance)

Flags (high 16 bits of typeAndFlags):
    0x8000 LIST       0x4000 STRUCT       0x2000 REFERENCE

**When the STRUCT flag is set, `type` is a struct-template index, not a
primitive type code.** (Verified: every STRUCT-flagged field in all 1329 GFF4
files in the ROM carries a type value that is a valid template index.)

Value location, relative to a struct instance's base offset `base`:
  * LIST: read uint32 at base+offset -> a list offset relative to dataOffset;
    at dataOffset+listOffset sits a uint32 element count, with the elements
    immediately following it.
  * REFERENCE: read uint32 at base+offset -> offset relative to dataOffset of
    the actual value.
  * otherwise the value sits inline at base+offset.

Strings (type 14) are stored out-of-line: a uint32 offset relative to
dataOffset, pointing at a uint32 character count followed by the characters.
The count includes a trailing NUL and counts *characters*, not bytes.

**String encoding differs by content type in this game** (verified both ways
against real files):
  * `TLK ` files store **8-bit** text (CP-1252) — 1 byte per character.
  * every other type stores standard **UTF-16LE** — 2 bytes per character.
Decoding a TLK as UTF-16 silently yields CJK mojibake (adjacent ASCII bytes
pair into CJK code points) and reads twice as far as the string actually
extends, so getting this wrong corrupts quietly rather than failing.
"""
import struct
import sys

MAGIC = b'GFF '

FLAG_LIST = 0x8000
FLAG_STRUCT = 0x4000
FLAG_REF = 0x2000

(T_UINT8, T_SINT8, T_UINT16, T_SINT16, T_UINT32, T_SINT32, T_UINT64, T_SINT64,
 T_FLOAT32, T_FLOAT64, T_VECTOR3F) = range(11)
T_VECTOR4F, T_QUATERNIONF, T_STRING, T_COLOR4F, T_MATRIX4X4F = 12, 13, 14, 15, 16
T_TLKSTRING, T_NDSFIXED, T_ASCIISTRING = 17, 18, 20
T_STRUCT, T_GENERIC = 65534, 65535

TYPE_NAMES = {
    T_UINT8: 'uint8', T_SINT8: 'sint8', T_UINT16: 'uint16', T_SINT16: 'sint16',
    T_UINT32: 'uint32', T_SINT32: 'sint32', T_UINT64: 'uint64', T_SINT64: 'sint64',
    T_FLOAT32: 'float32', T_FLOAT64: 'float64', T_VECTOR3F: 'vector3f',
    T_VECTOR4F: 'vector4f', T_QUATERNIONF: 'quaternionf', T_STRING: 'string',
    T_COLOR4F: 'color4f', T_MATRIX4X4F: 'matrix4x4f', T_TLKSTRING: 'tlkstring',
    T_NDSFIXED: 'ndsfixed', T_ASCIISTRING: 'asciistring',
    T_STRUCT: 'struct', T_GENERIC: 'generic',
}

FIXED_SIZES = {
    T_UINT8: 1, T_SINT8: 1, T_UINT16: 2, T_SINT16: 2, T_UINT32: 4, T_SINT32: 4,
    T_UINT64: 8, T_SINT64: 8, T_FLOAT32: 4, T_FLOAT64: 8, T_VECTOR3F: 12,
    T_VECTOR4F: 16, T_QUATERNIONF: 16, T_COLOR4F: 16, T_MATRIX4X4F: 64,
    T_TLKSTRING: 8, T_NDSFIXED: 4, T_STRING: 4, T_ASCIISTRING: 4, T_GENERIC: 4,
}

UNPACK = {
    T_UINT8: '<B', T_SINT8: '<b', T_UINT16: '<H', T_SINT16: '<h',
    T_UINT32: '<I', T_SINT32: '<i', T_UINT64: '<Q', T_SINT64: '<q',
    T_FLOAT32: '<f', T_FLOAT64: '<d',
}


class Field:
    __slots__ = ('label', 'type', 'flags', 'offset')

    def __init__(self, label, ftype, flags, offset):
        self.label, self.type, self.flags, self.offset = label, ftype, flags, offset

    @property
    def is_list(self):
        return bool(self.flags & FLAG_LIST)

    @property
    def is_struct(self):
        return bool(self.flags & FLAG_STRUCT)

    @property
    def is_ref(self):
        return bool(self.flags & FLAG_REF)

    def __repr__(self):
        fl = ''.join(c for c, b in (('L', self.is_list), ('S', self.is_struct), ('R', self.is_ref)) if b)
        tn = f'tmpl#{self.type}' if self.is_struct else TYPE_NAMES.get(self.type, f'?{self.type}')
        return f'<{self.label} {tn}{"/" + fl if fl else ""} @{self.offset}>'


class Template:
    __slots__ = ('label', 'size', 'fields')

    def __init__(self, label, size, fields):
        self.label, self.size, self.fields = label, size, fields


class GFF4:
    def __init__(self, data: bytes):
        self.data = data
        if data[0:4] != MAGIC:
            raise ValueError(f"not a GFF file (magic {data[0:4]!r})")
        self.version = data[4:8].decode('ascii', 'replace')
        if self.version not in ('V4.0', 'V4.1'):
            raise ValueError(f"unsupported GFF version {self.version!r}")
        self.platform = data[8:12].decode('ascii', 'replace')
        self.type = data[12:16].decode('ascii', 'replace')
        self.type_version = data[16:20].decode('ascii', 'replace')

        pos = 0x14
        self.struct_count, = struct.unpack_from('<I', data, pos); pos += 4
        self.string_count = self.string_offset = None
        if self.version == 'V4.1':
            self.string_count, self.string_offset = struct.unpack_from('<II', data, pos)
            pos += 8
        self.data_offset, = struct.unpack_from('<I', data, pos); pos += 4

        # This game's TLK tables store 8-bit text; everything else is UTF-16LE.
        if self.type.strip() == 'TLK':
            self.string_encoding, self.char_width = 'cp1252', 1
        else:
            self.string_encoding, self.char_width = 'utf-16-le', 2

        self.templates = []
        for _ in range(self.struct_count):
            label = data[pos:pos + 4].decode('ascii', 'replace')
            field_count, field_offset, size = struct.unpack_from('<III', data, pos + 4)
            fields = []
            for j in range(field_count):
                fp = field_offset + j * 12
                if fp + 12 > len(data):
                    raise ValueError(f"field def at 0x{fp:X} past EOF ({len(data)})")
                flabel, taf, foff = struct.unpack_from('<III', data, fp)
                fields.append(Field(flabel, taf & 0xFFFF, (taf >> 16) & 0xFFFF, foff))
            self.templates.append(Template(label, size, fields))
            pos += 16

    # --- low level helpers ---

    def _u32(self, at):
        if at + 4 > len(self.data):
            raise ValueError(f"read past EOF at 0x{at:X}")
        return struct.unpack_from('<I', self.data, at)[0]

    def _decode_string_at(self, pos, ftype):
        """Decode a string whose *data* starts at `pos`: uint32 char count, then
        the characters. The count includes a trailing NUL.

        Width/encoding: type 20 (asciistring) is always 1 byte per character;
        type 14 (string) follows the file's encoding — 2-byte UTF-16LE normally,
        1-byte CP-1252 in TLK files.
        """
        if ftype == T_ASCIISTRING:
            width, encoding = 1, 'cp1252'
        else:
            width, encoding = self.char_width, self.string_encoding
        count = self._u32(pos)
        end = pos + 4 + count * width
        if end > len(self.data):
            raise ValueError(f"string at 0x{pos:X} length {count} past EOF")
        return self.data[pos + 4:end].decode(encoding, 'replace').rstrip('\x00')

    def _read_string_indirect(self, at, ftype):
        """Read a string whose *offset* (relative to dataOffset) sits at `at`."""
        off = self._u32(at)
        if off == 0xFFFFFFFF:
            return None
        return self._decode_string_at(self.data_offset + off, ftype)

    def _read_value(self, ftype, at):
        if ftype in UNPACK:
            return struct.unpack_from(UNPACK[ftype], self.data, at)[0]
        if ftype in (T_STRING, T_ASCIISTRING):
            return self._read_string_indirect(at, ftype)
        if ftype == T_NDSFIXED:
            # NDS fixed-point: 32-bit, 12 fractional bits (1.19.12 style)
            raw = struct.unpack_from('<i', self.data, at)[0]
            return raw / 4096.0
        if ftype == T_VECTOR3F:
            return struct.unpack_from('<3f', self.data, at)
        if ftype in (T_VECTOR4F, T_QUATERNIONF, T_COLOR4F):
            return struct.unpack_from('<4f', self.data, at)
        if ftype == T_MATRIX4X4F:
            return struct.unpack_from('<16f', self.data, at)
        if ftype == T_TLKSTRING:
            # two uint32s: a string ref and an offset to inline text
            a, b = struct.unpack_from('<II', self.data, at)
            return {'strref': a, 'offset': b}
        if ftype == T_GENERIC:
            return self._read_generic(at, 0)
        raise ValueError(f"unhandled field type {ftype}")

    def _read_generic(self, at, depth):
        """A generic is an 8-byte (typeAndFlags, offset) pair — the same
        type/flags encoding as a field definition, followed by an offset relative
        to dataOffset. When the STRUCT flag is set, `type` is a template index, so
        a generic is how GUI files store heterogeneous child widgets.
        """
        taf, off = struct.unpack_from('<II', self.data, at)
        ftype = taf & 0xFFFF
        flags = (taf >> 16) & 0xFFFF
        if off == 0xFFFFFFFF:
            return None
        target = self.data_offset + off
        if flags & FLAG_STRUCT:
            if not (0 <= ftype < self.struct_count):
                return {'__bad_generic__': f'template index {ftype} out of range'}
            return self.read_struct(ftype, target, depth + 1)
        if ftype in (T_STRING, T_ASCIISTRING):
            return self._decode_string_at(target, ftype)
        try:
            return self._read_value(ftype, target)
        except Exception as e:
            return {'__bad_generic__': str(e)}

    # --- struct decoding ---

    def read_struct(self, tmpl_index, base, depth=0, max_depth=24):
        if depth > max_depth:
            return {'__truncated__': True}
        tmpl = self.templates[tmpl_index]
        out = {}
        for f in tmpl.fields:
            try:
                out[f.label] = self._read_field(f, base, depth)
            except Exception as e:
                out[f.label] = {'__error__': str(e)}
        return out

    def _read_field(self, f, base, depth):
        at = base + f.offset

        if f.is_list:
            list_off = self._u32(at)
            if list_off == 0xFFFFFFFF:
                return []
            count_pos = self.data_offset + list_off
            count = self._u32(count_pos)
            start = count_pos + 4
            items = []
            if f.is_struct:
                tmpl = self.templates[f.type]
                for i in range(count):
                    items.append(self.read_struct(f.type, start + i * tmpl.size, depth + 1))
            elif f.type == T_GENERIC:
                # Generic list elements are 8-byte (typeAndFlags, offset) pairs.
                for i in range(count):
                    items.append(self._read_generic(start + i * 8, depth))
            elif f.type in (T_STRING, T_ASCIISTRING):
                # list of out-of-line strings: 4-byte offsets
                for i in range(count):
                    items.append(self._read_value(f.type, start + i * 4))
            else:
                sz = FIXED_SIZES.get(f.type, 4)
                for i in range(count):
                    items.append(self._read_value(f.type, start + i * sz))
            return items

        # A REFERENCE field holds an offset (relative to dataOffset) to the real
        # value. Once followed, `at` points at the value itself — so string types
        # must NOT then dereference a second time.
        dereferenced = False
        if f.is_ref:
            ref = self._u32(at)
            if ref == 0xFFFFFFFF:
                return None
            at = self.data_offset + ref
            dereferenced = True

        if f.is_struct:
            return self.read_struct(f.type, at, depth + 1)

        if f.type in (T_STRING, T_ASCIISTRING):
            if dereferenced:
                return self._decode_string_at(at, f.type)
            return self._read_string_indirect(at, f.type)

        return self._read_value(f.type, at)

    def root(self):
        """Decode the top-level struct (template 0) at the data offset."""
        return self.read_struct(0, self.data_offset)

    # --- structural validation (no semantics, just bounds/consistency) ---

    def validate(self):
        problems = []
        if self.data_offset > len(self.data):
            problems.append(f"dataOffset 0x{self.data_offset:X} > file size {len(self.data)}")
        for i, t in enumerate(self.templates):
            for f in t.fields:
                if f.is_struct and not (0 <= f.type < self.struct_count):
                    problems.append(f"tmpl[{i}] field {f.label}: STRUCT type {f.type} "
                                    f"is not a valid template index (count {self.struct_count})")
                if not f.is_struct and f.type not in TYPE_NAMES:
                    problems.append(f"tmpl[{i}] field {f.label}: unknown type {f.type}")
                if not f.is_list and not f.is_ref and not f.is_struct:
                    need = FIXED_SIZES.get(f.type)
                    if need is not None and f.offset + need > t.size:
                        problems.append(f"tmpl[{i}] field {f.label}: offset {f.offset}+{need} "
                                        f"exceeds struct size {t.size}")
        return problems


# --- GDA convenience: GFF4-wrapped 2D table -------------------------------

GDA_COLUMNS = 10002
GDA_ROWS = 10003
GDA_COL_HASH = 10001
GDA_COL_TYPE = 10999


def read_gda(g: GFF4):
    """Return (columns, rows) for a G2DA file.
    columns: list of {'hash': int, 'type': int}
    rows:    list of dicts keyed by field label
    """
    if g.type.strip() != 'G2DA':
        raise ValueError(f"not a G2DA file (type {g.type!r})")
    root = g.root()
    cols = [{'hash': c.get(GDA_COL_HASH), 'type': c.get(GDA_COL_TYPE)}
            for c in root.get(GDA_COLUMNS, [])]
    return cols, root.get(GDA_ROWS, [])


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

    if target == '--validate':
        exts = ('.gff', '.gda', '.dlg', '.gui', '.plo', '.are', '.tlk')
        names = sorted(n for n in index if n.lower().endswith(exts))
        print(f"validating {len(names)} GFF4 files\n")
        failures, problem_files, types = [], [], {}
        total_problems = 0
        for n in names:
            size, off = index[n]
            try:
                g = GFF4(data[off:off + size])
            except Exception as e:
                failures.append((n, str(e)))
                continue
            key = (g.version, g.platform, g.type, g.type_version)
            types[key] = types.get(key, 0) + 1
            probs = g.validate()
            if probs:
                problem_files.append((n, probs[:3]))
                total_problems += len(probs)
        print(f"header parse failures: {len(failures)}")
        print(f"files with structural problems: {len(problem_files)} ({total_problems} problems)")
        print("\n(version, platform, type, typeVersion) -> count")
        for k, v in sorted(types.items(), key=lambda kv: -kv[1]):
            print(f"  {k}: {v}")
        for n, p in failures[:5]:
            print(f"  FAIL {n}: {p}")
        for n, p in problem_files[:5]:
            print(f"  PROBLEM {n}: {p}")
        return

    size, off = index[target]
    g = GFF4(data[off:off + size])
    print(f"{target}: {g.version} {g.platform!r} type={g.type!r} {g.type_version!r} "
          f"structs={g.struct_count} dataOffset=0x{g.data_offset:X}")
    for i, t in enumerate(g.templates):
        print(f"  tmpl[{i}] {t.label!r} size={t.size} fields={t.fields}")
    probs = g.validate()
    print(f"  structural problems: {probs if probs else 'none'}")
    import pprint
    pprint.pprint(g.root(), width=120, depth=6)


if __name__ == '__main__':
    main()
