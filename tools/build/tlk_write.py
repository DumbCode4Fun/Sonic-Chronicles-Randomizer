"""
Editor/writer for this game's TLK talk tables (`strings.tlk` and the per-language
variants) — the dialogue text the Phase 2 proof of concept targets.

A TLK is a GFF4 file of content type `TLK ` whose root holds a list of 8-byte
entries, each `{uint32 stringId, uint32 stringOffset}`. `stringOffset` is relative
to the file's `dataOffset`, or `0xFFFFFFFF` for "no string". At that location sits
a `uint32` character count (**including a trailing NUL**) followed by the text, in
**8-bit CP-1252** — not UTF-16, unlike every other GFF4 type in this game.

Design: **surgical edit, not re-serialization.**
Re-serializing from scratch would reorder the string blob and produce a wholly
different file. Instead this keeps the original bytes and only touches what must
change, which gives three useful properties:
  * a no-op save is **byte-identical** to the input;
  * a real edit produces a **minimal diff** (good for small patches);
  * the original's string **deduplication is preserved** — 487 offsets in
    `strings.tlk` are shared by more than one entry.

That last point is a correctness trap: editing a shared string in place would
silently change the text of every entry pointing at it. So a shared string is
**never** edited in place — a fresh copy is appended and only the target entry is
repointed. An unshared string is written in place when the new text is no longer
than the old, and appended otherwise.

Usage:
    py tlk_write.py <rom.nds> --verify
    py tlk_write.py <rom.nds> --set <stringId>=<new text> --out <strings.tlk>
"""
import collections
import struct
import sys

ENCODING = 'cp1252'
NO_STRING = 0xFFFFFFFF


class TlkFile:
    def __init__(self, data: bytes):
        self.data = bytearray(data)
        if bytes(self.data[0:4]) != b'GFF ' or bytes(self.data[12:16]) != b'TLK ':
            raise ValueError("not a TLK GFF4 file")
        self.data_offset, = struct.unpack_from('<I', self.data, 0x18)
        root_list_off, = struct.unpack_from('<I', self.data, self.data_offset)
        self.count_pos = self.data_offset + root_list_off
        self.count, = struct.unpack_from('<I', self.data, self.count_pos)
        self.entries_pos = self.count_pos + 4
        # How many entries point at each offset — shared offsets must not be
        # edited in place.
        self._sharers = collections.Counter(
            self.entry_offset(i) for i in range(self.count)
            if self.entry_offset(i) != NO_STRING)

    # --- entry access ---

    def entry(self, i):
        return struct.unpack_from('<II', self.data, self.entries_pos + i * 8)

    def entry_id(self, i):
        return self.entry(i)[0]

    def entry_offset(self, i):
        return self.entry(i)[1]

    def _set_entry_offset(self, i, off):
        struct.pack_into('<I', self.data, self.entries_pos + i * 8 + 4, off)

    def index_of_id(self, string_id):
        hits = [i for i in range(self.count) if self.entry_id(i) == string_id]
        if not hits:
            raise KeyError(f"no entry with string id {string_id}")
        if len(hits) > 1:
            raise KeyError(f"string id {string_id} appears {len(hits)} times "
                           f"(indices {hits[:5]}); edit by index instead")
        return hits[0]

    def get_string(self, i):
        off = self.entry_offset(i)
        if off == NO_STRING:
            return None
        pos = self.data_offset + off
        n, = struct.unpack_from('<I', self.data, pos)
        return self.data[pos + 4:pos + 4 + n].decode(ENCODING, 'replace').rstrip('\x00')

    def is_shared(self, i):
        off = self.entry_offset(i)
        return off != NO_STRING and self._sharers[off] > 1

    # --- editing ---

    def set_string(self, i, text):
        """Set entry `i`'s text. Returns a short note on how it was stored."""
        encoded = text.encode(ENCODING) + b'\x00'
        off = self.entry_offset(i)

        if off != NO_STRING and not self.is_shared(i):
            pos = self.data_offset + off
            old_n, = struct.unpack_from('<I', self.data, pos)
            if len(encoded) <= old_n:
                # Write in place. Keep the original count so trailing bytes stay
                # inside this string's own slot rather than bleeding into the next.
                self.data[pos + 4:pos + 4 + old_n] = encoded + b'\x00' * (old_n - len(encoded))
                return f"in place ({old_n} byte slot, {len(encoded)} used)"

        # Append a fresh string and repoint only this entry.
        while len(self.data) % 4:
            self.data.append(0)
        new_off = len(self.data) - self.data_offset
        self.data.extend(struct.pack('<I', len(encoded)))
        self.data.extend(encoded)
        while len(self.data) % 4:
            self.data.append(0)
        self._set_entry_offset(i, new_off)
        self._sharers[new_off] += 1
        if off != NO_STRING:
            self._sharers[off] -= 1
        reason = 'shared string, repointed' if off != NO_STRING and self._sharers[off] >= 1 else 'appended'
        return f"{reason} (new offset {new_off}, {len(encoded)} bytes)"

    def serialize(self) -> bytes:
        return bytes(self.data)


def load_tlk_from_rom(rom_path, path_in_rom='/strings.tlk'):
    sys.path.insert(0, __import__('os').path.join(
        __import__('os').path.dirname(__import__('os').path.abspath(__file__))))
    from rom_build import Rom
    with open(rom_path, 'rb') as f:
        rom = Rom(f.read())
    fid = rom.file_id(path_in_rom)
    return rom, fid, TlkFile(rom.file_bytes(fid))


def verify(rom_path):
    rom, fid, tlk = load_tlk_from_rom(rom_path)
    original = rom.file_bytes(fid)
    ok_noop = tlk.serialize() == original
    print(f"entries: {tlk.count}")
    with_text = sum(1 for i in range(tlk.count) if tlk.entry_offset(i) != NO_STRING)
    shared = sum(1 for i in range(tlk.count) if tlk.is_shared(i))
    print(f"entries with text: {with_text}   entries sharing a string with another: {shared}")
    print(f"NO-OP SERIALIZE BYTE-IDENTICAL: {ok_noop}")

    # Round-trip an edit through the real reader.
    sys.path.insert(0, 'tools/recon')
    from gff4 import GFF4

    # Pick an unshared entry with text, so we can exercise the in-place path.
    target = next(i for i in range(tlk.count)
                  if tlk.entry_offset(i) != NO_STRING and not tlk.is_shared(i)
                  and len(tlk.get_string(i)) > 20)
    before = tlk.get_string(target)
    short_text = "MOD TEST SHORT"
    note1 = tlk.set_string(target, short_text)
    g = GFF4(tlk.serialize())
    entries = g.root()[19001]
    read_back = entries[target][19003]
    print(f"\nin-place edit (entry {target}, id {tlk.entry_id(target)}):")
    print(f"  before : {before[:60]!r}")
    print(f"  wrote  : {short_text!r}  [{note1}]")
    print(f"  re-read: {read_back!r}   MATCH: {read_back == short_text}")

    # Now a longer string, forcing the append path.
    long_text = "MOD TEST " + "X" * 400
    note2 = tlk.set_string(target, long_text)
    g2 = GFF4(tlk.serialize())
    rb2 = g2.root()[19001][target][19003]
    print(f"\nappend edit (same entry, text longer than original slot):")
    print(f"  wrote  : {len(long_text)} chars  [{note2}]")
    print(f"  re-read matches: {rb2 == long_text}")

    # And a shared string must be repointed, never edited in place.
    shared_idx = next((i for i in range(tlk.count) if tlk.is_shared(i)), None)
    if shared_idx is not None:
        off = tlk.entry_offset(shared_idx)
        peers = [i for i in range(tlk.count)
                 if i != shared_idx and tlk.entry_offset(i) == off]
        peer_before = tlk.get_string(peers[0])
        note3 = tlk.set_string(shared_idx, "SHARED EDIT TEST")
        g3 = GFF4(tlk.serialize())
        e3 = g3.root()[19001]
        peer_after = e3[peers[0]][19003]
        print(f"\nshared-string edit (entry {shared_idx}, shared with {len(peers)} others):")
        print(f"  [{note3}]")
        print(f"  edited entry re-reads as : {e3[shared_idx][19003]!r}")
        print(f"  peer entry unchanged     : {peer_after == peer_before}")
        return ok_noop and read_back == short_text and rb2 == long_text and peer_after == peer_before
    return ok_noop and read_back == short_text and rb2 == long_text


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rom_path = sys.argv[1]
    if '--verify' in sys.argv:
        sys.exit(0 if verify(rom_path) else 1)

    rom, fid, tlk = load_tlk_from_rom(rom_path)
    out_path = None
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == '--set':
            sid, text = args[i + 1].split('=', 1)
            idx = tlk.index_of_id(int(sid))
            note = tlk.set_string(idx, text)
            print(f"set id {sid} (index {idx}): {note}")
            i += 2
        elif args[i] == '--out':
            out_path = args[i + 1]
            i += 2
        else:
            i += 1
    if out_path:
        with open(out_path, 'wb') as f:
            f.write(tlk.serialize())
        print(f"wrote {out_path} ({len(tlk.serialize())} bytes)")


if __name__ == '__main__':
    main()
