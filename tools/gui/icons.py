"""
Decode a Nintendo DS NCGR tile image + NCLR palette into something Tkinter can show.

Only enough of the formats to draw an inventory icon in the mod builder:

  NCGR  'RGCN' + 16-byte generic header, then a 'RAHC' section whose header gives
        the size in 8x8 tiles and the bit depth, followed by tile-ordered pixels.
        Pixels are palette indices, laid out one whole tile at a time rather than
        row by row, so they have to be de-tiled.
  NCLR  'RLCN' + 16-byte header, then a 'PLTT' section of BGR555 colours, each a
        16-bit word with 5 bits per channel.

Returns a PPM byte string, which `tkinter.PhotoImage(data=...)` accepts directly,
so there is no Pillow dependency.
"""
import struct

import lz77


def _sections(raw, magic):
    if raw[:4] != magic:
        raise ValueError('expected %r, got %r' % (magic, raw[:4]))
    return raw[16:]


def read_palette(raw):
    """NCLR -> [(r, g, b)]"""
    sec = _sections(raw, b'RLCN')
    if sec[:4] != b'TTLP':
        raise ValueError('no PLTT section')
    bitdepth, = struct.unpack_from('<I', sec, 8)
    data_off, = struct.unpack_from('<I', sec, 20)
    data = sec[8 + data_off:]
    count = len(data) // 2
    out = []
    for i in range(count):
        v, = struct.unpack_from('<H', data, i * 2)
        r = (v & 0x1F) << 3
        g = ((v >> 5) & 0x1F) << 3
        b = ((v >> 10) & 0x1F) << 3
        out.append((r | r >> 5, g | g >> 5, b | b >> 5))
    return out


def read_tiles(raw):
    """NCGR -> (width, height, [palette index per pixel], bpp)"""
    sec = _sections(raw, b'RGCN')
    if sec[:4] != b'RAHC':
        raise ValueError('no CHAR section')
    tiles_y, tiles_x, fmt = struct.unpack_from('<HHI', sec, 8)
    datasize, = struct.unpack_from('<I', sec, 24)
    data = sec[32:32 + datasize]
    bpp = 8 if fmt == 4 else 4
    if tiles_x in (0xFFFF, 0) or tiles_y in (0xFFFF, 0):
        total = datasize * (1 if bpp == 8 else 2) // 64
        tiles_x = min(total, 4) or 1
        tiles_y = max(1, total // tiles_x)
    w, h = tiles_x * 8, tiles_y * 8
    px = [0] * (w * h)
    if bpp == 8:
        vals = list(data)
    else:
        vals = []
        for b in data:
            vals.append(b & 0x0F)
            vals.append(b >> 4)
    i = 0
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            for y in range(8):
                for x in range(8):
                    if i < len(vals):
                        px[(ty * 8 + y) * w + (tx * 8 + x)] = vals[i]
                    i += 1
    return w, h, px, bpp


def _bbox(w, h, px):
    """Tight box around the non-transparent pixels, or None if the image is empty.

    These sprites sit in a mostly empty canvas — a typical 64x64 item icon is ~92%
    palette index 0 — so drawing the whole canvas leaves a small picture stranded in
    one corner. Cropping to the art is what makes them look right.
    """
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        base = y * w
        for x in range(w):
            if px[base + x]:
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    return None if x1 < 0 else (x0, y0, x1, y1)


def to_ppm(ncgr_raw, nclr_raw, scale=2, transparent=(240, 240, 240), crop=True):
    """Decode to a PPM byte string for tkinter.PhotoImage(data=...).

    Palette index 0 is the DS's transparency convention, so it is painted with the
    widget background colour rather than left black. With `crop`, the output is
    trimmed to the artwork and squared off about its centre, so icons come out
    centred and comparable instead of adrift in empty canvas.
    """
    pal = read_palette(nclr_raw)
    w, h, px, _ = read_tiles(ncgr_raw)
    x0, y0, x1, y1 = 0, 0, w - 1, h - 1
    if crop:
        box = _bbox(w, h, px)
        if box:
            bx0, by0, bx1, by1 = box
            side = max(bx1 - bx0 + 1, by1 - by0 + 1)
            cx, cy = (bx0 + bx1) // 2, (by0 + by1) // 2
            x0 = max(0, min(w - side, cx - side // 2))
            y0 = max(0, min(h - side, cy - side // 2))
            x1, y1 = x0 + side - 1, y0 + side - 1
    ow, oh = x1 - x0 + 1, y1 - y0 + 1
    rows = []
    for y in range(y0, y1 + 1):
        row = bytearray()
        for x in range(x0, x1 + 1):
            idx = px[y * w + x]
            rgb = transparent if idx == 0 else (pal[idx] if idx < len(pal) else (255, 0, 255))
            row += bytes(rgb) * scale
        for _ in range(scale):
            rows.append(bytes(row))
    body = b''.join(rows)
    return b'P6\n%d %d\n255\n' % (ow * scale, oh * scale) + body


def load(herf, ncgr_name, nclr_name, scale=2, transparent=(240, 240, 240), crop=True):
    """Read both resources out of the archive and decode. Returns None on any failure."""
    try:
        rmap = {n.lower(): n for n in herf.names.values()}
        c = herf.read(rmap[ncgr_name.lower()])
        p = herf.read(rmap[nclr_name.lower()])
        if ncgr_name.lower().endswith('.small'):
            c = bytes(lz77.read_small(c, 0, len(c)))
        if nclr_name.lower().endswith('.small'):
            p = bytes(lz77.read_small(p, 0, len(p)))
        return to_ppm(c, p, scale, transparent, crop)
    except Exception:
        return None


def load_parts(herf, prefix, nclr_name, cols=2, rows=2, scale=2,
               transparent=(240, 240, 240), crop=True):
    """Assemble a multi-part sprite into one image.

    Item icons are **not** single images: each is split into `cols x rows` separate
    NCGR resources named `<prefix>0` .. `<prefix>N`, laid out left-to-right then
    top-to-bottom. Every item icon in this game is four 64x64 quadrants forming a
    128x128 picture, so rendering `<prefix>0` alone shows only the top-left corner —
    which looks like a fragment of unrelated art rather than an obviously missing
    piece, and is easy to mistake for a broken decoder.
    """
    try:
        rmap = {n.lower(): n for n in herf.names.values()}
        pal_raw = herf.read(rmap[nclr_name.lower()])
        if nclr_name.lower().endswith('.small'):
            pal_raw = bytes(lz77.read_small(pal_raw, 0, len(pal_raw)))
        pal = read_palette(pal_raw)

        grids = []
        for i in range(cols * rows):
            key = rmap.get(('%s%d.NCGR.small' % (prefix, i)).lower())
            if key is None:
                return None
            raw = herf.read(key)
            raw = bytes(lz77.read_small(raw, 0, len(raw)))
            grids.append(read_tiles(raw))
        tw, th = grids[0][0], grids[0][1]
        W, H = tw * cols, th * rows
        px = [0] * (W * H)
        for i, (gw, gh, gp, _) in enumerate(grids):
            ox, oy = (i % cols) * tw, (i // cols) * th
            for y in range(gh):
                src = y * gw
                dst = (oy + y) * W + ox
                px[dst:dst + gw] = gp[src:src + gw]

        x0, y0, x1, y1 = 0, 0, W - 1, H - 1
        if crop:
            box = _bbox(W, H, px)
            if box:
                bx0, by0, bx1, by1 = box
                side = max(bx1 - bx0 + 1, by1 - by0 + 1)
                cx, cy = (bx0 + bx1) // 2, (by0 + by1) // 2
                x0 = max(0, min(W - side, cx - side // 2))
                y0 = max(0, min(H - side, cy - side // 2))
                x1, y1 = x0 + side - 1, y0 + side - 1
        ow, oh = x1 - x0 + 1, y1 - y0 + 1
        rows_out = []
        for y in range(y0, y1 + 1):
            row = bytearray()
            for x in range(x0, x1 + 1):
                idx = px[y * W + x]
                rgb = transparent if idx == 0 else (pal[idx] if idx < len(pal) else (255, 0, 255))
                row += bytes(rgb) * scale
            for _ in range(scale):
                rows_out.append(bytes(row))
        return b'P6\n%d %d\n255\n' % (ow * scale, oh * scale) + b''.join(rows_out)
    except Exception:
        return None
