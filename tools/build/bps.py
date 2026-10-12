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


#: Block size for the source index. It must be at most half of `RESYNC_WINDOW`, which is
#: what makes the index *complete*: if the needle occurs at source position p, then the
#: first BLOCK-aligned offset q >= p satisfies q <= p + BLOCK - 1 and q + BLOCK <= p +
#: 2*BLOCK <= p + RESYNC_WINDOW, so that whole aligned block lies inside the needle. The
#: block therefore appears in the index, at one of BLOCK possible offsets into the needle.
#: Checking all BLOCK offsets cannot miss an occurrence.
INDEX_BLOCK = 16
#: Above this many index candidates for one offset, fall back to `bytes.find`. A hash with
#: thousands of hits means a highly repetitive block - a run of zero padding, of which an
#: NDS ROM has a great deal - and for exactly those needles `find` succeeds almost
#: immediately. Verifying every candidate would be slower than the scan it replaces.
INDEX_MAX_CANDIDATES = 64


class _SourceIndex:
    """Answers `source.find(needle)` for a 32-byte needle without scanning the source.

    **Why this exists.** Measured 2026-10-12 on the randomizer build: `resync` spent 87%
    of the runtime in 22,102 whole-buffer scans, each reading 134 MB only to conclude a
    32-byte window is absent. The encoder advances one literal byte at a time through
    genuinely new data and asks again at every byte, so a region of novel bytes costs one
    full scan per byte. Rejecting an absent needle is the entire problem.

    **It returns exactly what `bytes.find` returns, and that is the point.** Two cheaper
    schemes were tried first and both were refused on evidence: giving up on whole-buffer
    scans after a run of failures was 2x faster and made the patch **69% larger**, and
    rate-limiting them has the same shape of risk. The scans do find real matches
    elsewhere in the ROM. So this does not approximate them - it enumerates every
    occurrence through the index, takes the lowest, and is therefore substitutable for
    `find` rather than a trade against patch size.

    **Measured 2026-10-12 on the randomizer build**, same code, index on against index off:

        no index   859.1 s   38643 bytes   sha 9fd8772302b31675
        index      179.4 s   38643 bytes   sha 9fd8772302b31675

    **Byte-identical, 4.8x faster.** Index build cost is 3.1 s of that. Rejecting 200
    absent needles went from 4.40 s to 0.045 s, which is the 98x that the whole thing
    rests on. A separate correctness sweep of 855 needles - lifted from the source, from
    the target, random, the source's first and last 32 bytes, one straddling the end of
    the indexed region, and the degenerate all-0x00 and all-0xFF cases - found zero
    disagreements with `bytes.find`.

    One trap worth recording, because it cost a run: the `build/*.bps` files on disk are
    **not** a valid baseline for this comparison. They predate the day's `bps.py` commits,
    so they differ by 19 bytes for an unrelated reason (the `_match_len` step change) and
    comparing against them looks exactly like the index having changed the output. The
    only comparison that answers the question is index on versus index off, same code.

    Requires numpy. Without it `create` keeps the original full-scan path, which is slow
    but correct; patch creation is opt-out at build time for that reason.
    """

    PRIME = 0x9E3779B97F4A7C15

    def __init__(self, source, np):
        self.np = np
        self.source = source
        m = len(source) // INDEX_BLOCK
        arr = np.frombuffer(source, dtype=np.uint8)
        # Two uint64 per 16-byte block, read in place - no copy of the ROM.
        pairs = arr[:m * INDEX_BLOCK].view('<u8').reshape(m, 2)
        h = self._mix(pairs[:, 0], pairs[:, 1])
        order = np.argsort(h, kind='stable')
        self.hashes = h[order]
        self.offsets = order.astype(np.uint64) * np.uint64(INDEX_BLOCK)
        del h, order

    def _mix(self, a, b):
        np = self.np
        p = np.uint64(self.PRIME)
        h = (a * p) ^ b
        h ^= h >> np.uint64(29)
        h = h * p
        h ^= h >> np.uint64(32)
        return h

    def _key(self, block):
        np = self.np
        pair = np.frombuffer(block, dtype='<u8')
        return self._mix(pair[0:1], pair[1:2])[0]

    def find(self, needle):
        """The lowest position of `needle` in the source, or -1 - same as bytes.find."""
        np = self.np
        best = -1
        src = self.source
        ln = len(needle)
        for d in range(INDEX_BLOCK):
            key = self._key(needle[d:d + INDEX_BLOCK])
            lo = int(np.searchsorted(self.hashes, key, 'left'))
            hi = int(np.searchsorted(self.hashes, key, 'right'))
            if hi - lo > INDEX_MAX_CANDIDATES:
                return src.find(needle)
            for k in range(lo, hi):
                p = int(self.offsets[k]) - d
                # A hash hit is a candidate, never an answer: verify the actual bytes.
                if 0 <= p and (best < 0 or p < best) and src[p:p + ln] == needle:
                    best = p
        return best


def _build_index(source):
    """A `_SourceIndex` if numpy is importable and the source is worth indexing."""
    if len(source) < (1 << 20):
        return None
    try:
        import numpy as np
    except ImportError:
        return None
    try:
        return _SourceIndex(source, np)
    except Exception:
        # An index is an optimisation. If anything about it fails - memory, a numpy
        # version that dislikes the view - the full scan is still correct.
        return None


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

    index = _build_index(source)

    def resync(at):
        """Find where target[at:] reappears in source.

        Searches near `at` first, so a local match wins over a coincidental far one. The
        near search is bounded to +/-4 MB and is cheap; the *global* one is what used to
        dominate, at 87% of the runtime in 22,102 whole-buffer scans of 134 MB each.

        `_SourceIndex` replaces that global scan with an index lookup and returns the
        identical answer, so the patch is byte-for-byte what the scan produced. Without
        numpy there is no index and the scan runs as before - correct, just slow.

        Two cheaper schemes were tried before this and both were refused: giving up on
        whole-buffer scans after a run of failures was 2x faster and made the patch 69%
        larger, and rate-limiting them has the same shape of risk. Patch size is a
        permanent property of an artifact people distribute; build time is not.
        """
        needle = bytes(target[at:at + RESYNC_WINDOW])
        if len(needle) < RESYNC_WINDOW:
            return None
        lo = max(0, at - RESYNC_NEAR)
        found = source.find(needle, lo, at + RESYNC_NEAR)
        if found < 0:
            found = index.find(needle) if index else source.find(needle)
        return found if found >= 0 else None

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
