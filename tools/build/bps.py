"""
BPS patch generation (and application, for self-verification).

Why BPS and not IPS: IPS encodes offsets in 24 bits, capping it at 16 MB. This
game's ROM is 128 MB, so IPS cannot address most of it. BPS has no such limit,
carries CRC32s of source/target/patch so a wrong base ROM is detected rather than
silently mis-patched, and is supported by standard community tools (beat,
Floating IPS).

Format:
    "BPS1"
    varint sourceSize, varint targetSize, varint metadataSize, metadata bytes
    actions, each a varint of (length-1) << 2 | op:
        0 SourceRead  copy `length` bytes from source at the output position
        1 TargetRead  `length` literal bytes follow in the patch
        2 SourceCopy  signed varint offset, then copy from a tracked source ptr
        3 TargetCopy  same, from a tracked target ptr
    uint32 sourceCRC32, uint32 targetCRC32, uint32 patchCRC32   (all LE)

This encoder uses SourceRead, TargetRead and **SourceCopy**. SourceCopy matters
enormously here and is not optional: growing a file inside the ROM pushes every
later file forward by a multiple of the 512-byte sector size, so megabytes of
*identical* data end up at a *different* offset. A SourceRead/TargetRead-only
encoder cannot express "same bytes, moved" and has to emit all of it as literals —
in testing that turned a 68-byte text edit into a 46 MB patch. SourceCopy encodes
the same thing as one action.

Candidate offsets for SourceCopy are deliberately targeted rather than a general
content-indexed search: the current position, the last source pointer, and
positions shifted by +/- whole sectors. That covers alignment-driven file movement,
which is the shift this pipeline actually produces. It will not spot arbitrary
relocations the way a full differ (xdelta, beat) would.

Usage:
    py bps.py create <source> <target> <out.bps> [metadata]
    py bps.py apply  <source> <patch.bps> <out>
"""
import struct
import sys
import zlib


def encode_varint(n: int) -> bytes:
    out = bytearray()
    while True:
        x = n & 0x7F
        n >>= 7
        if n == 0:
            out.append(0x80 | x)
            break
        out.append(x)
        n -= 1
    return bytes(out)


def decode_varint(buf, pos):
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result += (b & 0x7F) << shift
        if b & 0x80:
            return result, pos
        shift += 7
        result += 1 << shift


SOURCE_READ, TARGET_READ = 0, 1
SOURCE_COPY, TARGET_COPY = 2, 3


SECTOR = 512
MIN_COPY = 16          # don't bother with SourceCopy below this match length
MAX_SECTOR_SHIFT = 64  # candidate shifts to probe, in whole sectors
RESYNC_WINDOW = 32     # bytes of target used as the needle when resyncing
RESYNC_NEAR = 1 << 22  # prefer a match within +/-4 MB of the current position
FUTILE_LIMIT = 32      # consecutive failed whole-buffer scans before giving up on them


#: `_match_len` block sizes. The step **grows** from the first to the second, doubling
#: on every block that matches.
#:
#: A fixed step cannot serve both of this function's callers well, and it was fixed at
#: 4096 until 2026-10-12. `create` calls it to *probe* up to 137 candidate offsets at
#: every position, and almost all of those differ within the first few bytes - so a
#: fixed 4 KB step spent two 4096-byte slices, over a megabyte of copying per stuck
#: position, to learn something the first 64 bytes already said. The same step is also
#: too small for the other caller: when the buffers really do match, 134 MB at 4 KB a
#: time is 32,768 round trips through the interpreter.
#:
#: Growing from 64 fixes both. A failing probe costs one 64-byte comparison, and a long
#: match reaches the ceiling after eight doublings, so the whole ROM is covered in a few
#: hundred iterations instead of tens of thousands. The ceiling is there to bound the
#: binary search below it, which walks at most log2(MATCH_STEP_MAX) slices.
MATCH_STEP_MIN = 64
MATCH_STEP_MAX = 1 << 16


def _match_len(a: bytes, ai: int, b: bytes, bi: int, limit: int) -> int:
    """Length of the common run of a[ai:] and b[bi:], capped at `limit`.

    The chunking is an optimization only: the answer is the length of the common
    prefix, which does not depend on how the comparison is divided up. A change here
    cannot alter the patch that `create` produces, only how long it takes to produce it.
    """
    if ai < 0 or bi < 0:
        return 0
    n = min(limit, len(a) - ai, len(b) - bi)
    i = 0
    step = MATCH_STEP_MIN
    while i < n:
        chunk = min(step, n - i)
        if a[ai + i:ai + i + chunk] == b[bi + i:bi + i + chunk]:
            i += chunk
            if step < MATCH_STEP_MAX:
                step <<= 1
            continue
        # The run ends inside this block; binary search for where.
        lo, hi = i, i + chunk
        while lo < hi:
            mid = (lo + hi) // 2
            if a[ai + lo:ai + mid + 1] == b[bi + lo:bi + mid + 1]:
                lo = mid + 1
            else:
                hi = mid
        return lo
    return n


def create(source: bytes, target: bytes, metadata: bytes = b'') -> bytes:
    patch = bytearray(b'BPS1')
    patch += encode_varint(len(source))
    patch += encode_varint(len(target))
    patch += encode_varint(len(metadata))
    patch += metadata

    n = len(target)
    pos = 0
    source_rel = 0
    literals = bytearray()

    def flush_literals():
        nonlocal literals
        if literals:
            patch.extend(encode_varint(((len(literals) - 1) << 2) | TARGET_READ))
            patch.extend(literals)
            literals = bytearray()

    shifts = [k * SECTOR for k in range(1, MAX_SECTOR_SHIFT + 1)]
    shifts = [s for pair in zip(shifts, [-s for s in shifts]) for s in pair]

    # Deltas discovered by resync, most recent first. Sector shifts alone are not
    # enough: editing resources *inside* an archive moves everything after them by an
    # arbitrary number of bytes, not a whole sector, so every sector candidate misses
    # and the loop degrades to one literal byte per iteration over the whole tail.
    # Remembering the real delta makes the very next position hit on candidate one.
    recent = []

    def remember(delta):
        if delta in recent:
            recent.remove(delta)
        recent.insert(0, delta)
        del recent[8:]

    # How many full-buffer scans may fail in a row before the fallback is switched off.
    # See `resync`.
    futile = [0]

    def resync(at):
        """Find where target[at:] reappears in source, via C-speed bytes.find.

        Searches near `at` first, so a local match wins over a coincidental far one.

        **The whole-buffer fallback is adaptive, and that is the difference between a
        patch taking a quarter of an hour and taking seconds.** The comment here used to
        say a full scan happens "once per new shift (tens of times for a whole ROM), so
        a full-buffer scan is affordable". Measured on 2026-10-12, it was neither. In a
        12 MB sample of the archive region: 5,259 resyncs, 5,143 of them full scans,
        and **every one of the 116 useful results came from the near window instead**.
        The full scans were looking for bytes that had been *changed* rather than moved,
        so they were not in the source at all, and each one read 134 MB to conclude that.
        They were 87% of the runtime and contributed nothing.

        A run can still contain a genuine long-distance move, so the fallback is not
        removed; it is switched off once it has proved itself useless. After
        FUTILE_LIMIT consecutive failures it stops being attempted, and any success
        resets the count. The cost of being wrong is a slightly larger patch - an
        unfound match becomes literal bytes - never an incorrect one, because what a
        patch must reproduce is checked separately and exactly.
        """
        needle = bytes(target[at:at + RESYNC_WINDOW])
        if len(needle) < RESYNC_WINDOW:
            return None
        lo = max(0, at - RESYNC_NEAR)
        found = source.find(needle, lo, at + RESYNC_NEAR)
        if found >= 0:
            futile[0] = 0
            return found
        if futile[0] >= FUTILE_LIMIT:
            return None
        found = source.find(needle)
        if found < 0:
            futile[0] += 1
            return None
        futile[0] = 0
        return found

    while pos < n:
        same = _match_len(source, pos, target, pos, n - pos)
        if same >= MIN_COPY:
            flush_literals()
            patch += encode_varint(((same - 1) << 2) | SOURCE_READ)
            pos += same
            continue

        # Look for the same bytes elsewhere in source: the previous source
        # pointer first (sequential runs), then whole-sector shifts.
        best_len, best_off = 0, None
        cands = [source_rel] + [pos + d for d in recent] + [pos + s for s in shifts]
        for cand in cands:
            if cand < 0 or cand >= len(source):
                continue
            ln = _match_len(source, cand, target, pos, n - pos)
            if ln > best_len:
                best_len, best_off = ln, cand
            if best_len >= 1 << 16:
                break

        if best_len < MIN_COPY:
            cand = resync(pos)
            if cand is not None:
                ln = _match_len(source, cand, target, pos, n - pos)
                if ln > best_len:
                    best_len, best_off = ln, cand
                    remember(cand - pos)

        if best_len >= MIN_COPY and best_len > same:
            flush_literals()
            patch += encode_varint(((best_len - 1) << 2) | SOURCE_COPY)
            delta = best_off - source_rel
            patch += encode_varint((abs(delta) << 1) | (1 if delta < 0 else 0))
            source_rel = best_off + best_len
            pos += best_len
            continue

        if same > 0:
            flush_literals()
            patch += encode_varint(((same - 1) << 2) | SOURCE_READ)
            pos += same
            continue

        literals.append(target[pos])
        pos += 1

    flush_literals()

    patch += struct.pack('<I', zlib.crc32(source) & 0xFFFFFFFF)
    patch += struct.pack('<I', zlib.crc32(target) & 0xFFFFFFFF)
    patch += struct.pack('<I', zlib.crc32(bytes(patch)) & 0xFFFFFFFF)
    return bytes(patch)


def apply(source: bytes, patch: bytes) -> bytes:
    if patch[0:4] != b'BPS1':
        raise ValueError('not a BPS patch')
    stored_src_crc, stored_tgt_crc, stored_patch_crc = struct.unpack_from('<III', patch, len(patch) - 12)
    if zlib.crc32(patch[:-4]) & 0xFFFFFFFF != stored_patch_crc:
        raise ValueError('patch is corrupt (patch CRC mismatch)')
    if zlib.crc32(source) & 0xFFFFFFFF != stored_src_crc:
        raise ValueError('wrong source file (source CRC mismatch)')

    pos = 4
    source_size, pos = decode_varint(patch, pos)
    target_size, pos = decode_varint(patch, pos)
    metadata_size, pos = decode_varint(patch, pos)
    pos += metadata_size

    out = bytearray()
    source_rel = 0
    target_rel = 0
    end = len(patch) - 12
    while pos < end:
        cmd, pos = decode_varint(patch, pos)
        length = (cmd >> 2) + 1
        op = cmd & 3
        if op == SOURCE_READ:
            out += source[len(out):len(out) + length]
        elif op == TARGET_READ:
            out += patch[pos:pos + length]
            pos += length
        elif op == SOURCE_COPY:
            raw, pos = decode_varint(patch, pos)
            offset = (raw >> 1) * (-1 if raw & 1 else 1)
            source_rel += offset
            out += source[source_rel:source_rel + length]
            source_rel += length
        else:
            raw, pos = decode_varint(patch, pos)
            offset = (raw >> 1) * (-1 if raw & 1 else 1)
            target_rel += offset
            for _ in range(length):
                out.append(out[target_rel])
                target_rel += 1

    if len(out) != target_size:
        raise ValueError(f'applied size {len(out)} != expected {target_size}')
    if zlib.crc32(bytes(out)) & 0xFFFFFFFF != stored_tgt_crc:
        raise ValueError('result CRC mismatch')
    return bytes(out)


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(1)
    mode = sys.argv[1]
    if mode == 'create':
        with open(sys.argv[2], 'rb') as f:
            src = f.read()
        with open(sys.argv[3], 'rb') as f:
            tgt = f.read()
        meta = sys.argv[5].encode('utf-8') if len(sys.argv) > 5 else b''
        p = create(src, tgt, meta)
        with open(sys.argv[4], 'wb') as f:
            f.write(p)
        print(f"wrote {sys.argv[4]} ({len(p)} bytes) for a {len(tgt)}-byte target")
        back = apply(src, p)
        print(f"self-check: patch re-applies to the exact target: {back == tgt}")
    elif mode == 'apply':
        with open(sys.argv[2], 'rb') as f:
            src = f.read()
        with open(sys.argv[3], 'rb') as f:
            p = f.read()
        out = apply(src, p)
        with open(sys.argv[4], 'wb') as f:
            f.write(out)
        print(f"wrote {sys.argv[4]} ({len(out)} bytes)")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
