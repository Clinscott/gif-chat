"""Independent tiny GIF encoder: explicit pixels, local rectangles and clear-code LZW.

No Pillow encoding or compositing is used for pixel correctness expectations.
"""
import struct

BLACK = (0, 0, 0, 255)
RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)
BLUE = (0, 0, 255, 255)
PALETTE = (BLACK, RED, GREEN, BLUE)


def subblocks(data):
    return b"".join(bytes([len(data[i:i + 255])]) + data[i:i + 255] for i in range(0, len(data), 255)) + b"\x00"


def lzw(pixels):
    # Frequent CLEAR prevents dictionary growth; all codes remain three bits wide.
    codes = [code for pixel in pixels for code in (4, pixel)] + [5]
    value = sum(code << (3 * i) for i, code in enumerate(codes))
    return value.to_bytes((len(codes) * 3 + 7) // 8, "little")


def gif(frames, width=2, height=1, loop=None):
    result = b"GIF89a" + struct.pack("<HHBBB", width, height, 0x81, 0, 0)
    result += bytes(channel for rgb in PALETTE for channel in rgb[:3])
    if loop is not None:
        result += b"!\xff\x0bNETSCAPE2.0\x03\x01" + struct.pack("<H", loop) + b"\x00"
    for frame in frames:
        raw = frame.get("delay", 100)
        transparent = frame.get("transparent")
        if raw is not None:
            flags = frame.get("disposal", 1) * 4 + (transparent is not None)
            result += b"!\xf9\x04" + bytes([flags]) + struct.pack("<H", raw // 10) + bytes([transparent or 0, 0])
        x, y = frame.get("x", 0), frame.get("y", 0)
        fw, fh = frame.get("width", width), frame.get("height", height)
        palette = frame.get("palette")
        result += b"," + struct.pack("<HHHHB", x, y, fw, fh, 0x81 if palette else 0)
        if palette:
            result += bytes(channel for rgb in palette for channel in rgb[:3])
        result += b"\x02" + subblocks(lzw(frame["pixels"]))
    return result + b";"
