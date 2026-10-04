"""Bounded GIF structure preflight. Pixel decoding belongs to the worker."""
from .contracts import DEFAULTS, GifError, require


def parse(data: bytes, limits=DEFAULTS, *, rendering=False):
    require(len(data) <= limits.source_bytes, "source_too_large", "Select a GIF of at most 20 MiB.")
    require(data[:6] in (b"GIF87a", b"GIF89a"), "unsupported_media", "Only original GIF87a/GIF89a bytes are supported; URLs and other media are not fetched.")
    pos = 6

    def take(count):
        nonlocal pos
        require(pos + count <= len(data))
        value = data[pos:pos + count]
        pos += count
        return value

    def blocks(capture=False):
        # Skip uninterpreted bytes in place. Never retain a list per subblock.
        nonlocal pos
        count, payload = 0, None
        while True:
            size = take(1)[0]
            if size == 0:
                return count, payload
            require(pos + size <= len(data))
            count += 1
            if capture:
                require(count == 1 and size == 3)
                payload = data[pos:pos + size]
            pos += size

    screen = take(7)
    width, height = int.from_bytes(screen[:2], "little"), int.from_bytes(screen[2:4], "little")
    require(0 < width <= limits.edge and 0 < height <= limits.edge,
            "canvas_limit", "The GIF canvas exceeds the local 2048 by 2048 limit or is empty.")
    global_palette = take(3 * 2 ** ((screen[4] & 7) + 1)) if screen[4] & 128 else None
    require(global_palette is None or screen[5] < len(global_palette) // 3)
    rectangles = []
    frames, elapsed, loop, control = [], 0, None, None
    while True:
        tag = take(1)[0]
        if tag == 0x3B:
            require(pos == len(data) and frames and control is None)
            break
        if tag == 0x21:
            kind = take(1)[0]
            if kind == 0xF9:
                require(control is None and take(1) == b"\x04")
                control = take(4)
                require(take(1) == b"\x00")
                require((control[0] >> 2) & 7 <= 3, "unsupported_disposal", "Reserved GIF disposal is not supported.")
                require(not control[0] & 2, "unsupported_timing", "User-input-controlled GIF timing is unsupported.")
                require(not control[0] & 0xE0)
            elif kind == 0xFF:
                require(take(1) == b"\x0b")
                identifier = take(11)
                known = identifier in (b"NETSCAPE2.0", b"ANIMEXTS1.0")
                count, payload = blocks(capture=known)
                if known:
                    require(loop is None and count == 1 and payload[0] == 1)
                    loop = int.from_bytes(payload[1:], "little")
            elif kind == 0xFE:
                blocks()  # Comments are content, never output or instructions.
            elif kind == 0x01:
                raise GifError("unsupported_plain_text", "GIF plain-text rendering blocks are unsupported; no complete visual claim can be made.")
            else:
                raise GifError("unsupported_extension", "The GIF contains an unsupported extension.")
            continue
        require(tag == 0x2C)
        require(len(frames) < limits.frames, "frame_limit", "The GIF exceeds the local 300-frame limit.")
        desc = take(9)
        left, top, fw, fh = [int.from_bytes(desc[i:i + 2], "little") for i in (0, 2, 4, 6)]
        require(fw > 0 and fh > 0 and left + fw <= width and top + fh <= height)
        require(not desc[8] & 0x18)
        palette = take(3 * 2 ** ((desc[8] & 7) + 1)) if desc[8] & 128 else global_palette
        require(palette is not None, "unsupported_palette", "Each frame requires a palette in this original GIF.")
        transparent = control[3] if control and control[0] & 1 else None
        require(transparent is None or transparent < len(palette) // 3)
        image_start = pos
        require(2 <= take(1)[0] <= 8)
        require(blocks()[0] > 0)
        if rendering:
            rectangles.append({"left": left, "top": top, "width": fw, "height": fh,
                               "interlaced": bool(desc[8] & 64), "palette": palette,
                               "transparent": transparent, "image_start": image_start, "image_end": pos})
        raw = int.from_bytes(control[1:3], "little") * 10 if control else None
        effective = raw if raw else 100
        frames.append({"index": len(frames), "start_ms": elapsed, "raw_duration_ms": raw,
                       "effective_duration_ms": effective, "disposal": (control[0] >> 2) & 7 if control else 0})
        elapsed += effective
        control = None
        require(elapsed <= limits.duration_ms, "timeline_limit", "The normalized GIF timeline exceeds 30 seconds.")
        require(width * height * len(frames) <= limits.pixels, "work_limit", "The GIF exceeds the local composited-pixel budget.")
    result = {"canvas_width": width, "canvas_height": height, "frame_count": len(frames),
              "loop_count": loop, "timeline_duration_ms": elapsed, "timeline": frames}
    if rendering:
        background = tuple(global_palette[screen[5] * 3:screen[5] * 3 + 3]) + (255,) if global_palette else (0, 0, 0, 0)
        return result, {"background": background, "rectangles": rectangles}
    return result
