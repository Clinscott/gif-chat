"""Streaming compositing with bounded, deterministic change/coverage selection."""
import base64
import hashlib
import io
import platform
import struct
from dataclasses import replace
import PIL
from PIL import Image, ImageChops, ImageStat
from .contracts import DEFAULTS, PILLOW_VERSION, PYTHON_VERSION, SAMPLE_POLICY, TIMING_POLICY, require
from .parser import parse


def composited_frames(data, info, rendering, count):
    """Decode bounded rectangles; apply disposal in logical-screen coordinates.

    gif-composite-v1 uses an initially transparent canvas if the first image has
    transparency. Disposal 2 clears transparently for a transparent image and
    otherwise uses the logical GLOBAL palette background, never a local palette.
    Undefined backgrounds (no global table) are transparent. Disposal 0 leaves
    pixels in place. Source bytes are never rewritten; single-frame wrappers are
    temporary decoder inputs only.
    """
    rectangles = rendering["rectangles"]
    transparent_clear = (0, 0, 0, 0)
    background = rendering["background"]
    initial = transparent_clear if rectangles[0]["transparent"] is not None else background
    canvas = Image.new("RGBA", (info["canvas_width"], info["canvas_height"]), initial)
    for i, rect in enumerate(rectangles[:count]):
        fw, fh, palette = rect["width"], rect["height"], rect["palette"]
        size_code = (len(palette) // 3).bit_length() - 2
        wrapper = b"GIF89a" + struct.pack("<HHBBB", fw, fh, 128 | size_code, 0, 0) + palette
        if rect["transparent"] is not None:
            wrapper += b"!\xf9\x04\x01\x00\x00" + bytes([rect["transparent"], 0])
        wrapper += b"," + struct.pack("<HHHHB", 0, 0, fw, fh, 64 if rect["interlaced"] else 0)
        wrapper += data[rect["image_start"]:rect["image_end"]] + b";"
        box = (rect["left"], rect["top"], rect["left"] + fw, rect["top"] + fh)
        disposal = info["timeline"][i]["disposal"]
        saved = canvas.crop(box) if disposal == 3 else None
        with Image.open(io.BytesIO(wrapper), formats=["GIF"]) as delta:
            layer = delta.convert("RGBA")
            require(layer.size == (fw, fh))
            canvas.alpha_composite(layer, (rect["left"], rect["top"]))
        yield canvas
        if disposal == 2:
            canvas.paste(transparent_clear if rect["transparent"] is not None else background, box)
        elif disposal == 3:
            canvas.paste(saved, box)


def decode(data, budget=12, interval=None, limits=DEFAULTS):
    require(platform.python_version() == PYTHON_VERSION and PIL.__version__ == PILLOW_VERSION,
            "runtime_mismatch", "Use the exact pinned Python and Pillow runtime.")
    info, rendering = parse(data, replace(limits, pixels=DEFAULTS.pixels), rendering=True)
    timeline = info["timeline"]
    start, end = interval if interval else (0, info["timeline_duration_ms"])
    eligible = [f["index"] for f in timeline if f["start_ms"] < end and f["start_ms"] + f["effective_duration_ms"] > start]
    require(eligible, "invalid_interval", "Select a nonempty interval within the normalized timeline.")
    first, last = eligible[0], eligible[-1]
    # Preceding frames MUST be reconstructed for disposal correctness.
    work_frames = last + 1
    require(info["canvas_width"] * info["canvas_height"] * work_frames <= limits.pixels,
            "work_limit", "The remaining composited-pixel budget cannot reconstruct this interval.")
    chosen, previous, hashes = {}, None, []
    bins = max(0, budget - 2)
    small = len(eligible) <= budget
    Image.MAX_IMAGE_PIXELS = limits.edge * limits.edge

    def frame_png(canvas):
        preview = canvas.copy()
        preview.thumbnail((limits.long_edge, limits.long_edge), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        preview.save(output, format="PNG", optimize=False)
        return output.getvalue(), preview.size

    for i, canvas in enumerate(composited_frames(data, info, rendering, work_frames)):
        digest = hashlib.sha256(canvas.tobytes()).hexdigest()
        hashes.append(digest)
        thumb = canvas.resize((64, 64), Image.Resampling.BOX).convert("RGB")
        change = sum(ImageStat.Stat(ImageChops.difference(thumb, previous)).sum) if previous else 0
        previous = thumb
        if i not in eligible:
            continue
        if small:
            slot, reason, score = i, "complete_interval", (0, 0, 0)
        elif i == first:
            slot, reason, score = -1, "interval_opening", (0, 0, 0)
        elif i == last and budget >= 2:
            slot, reason, score = -2, "interval_ending", (0, 0, 0)
        elif bins:
            t = timeline[i]["start_ms"]
            slot = min(bins - 1, max(0, (t - start) * bins // (end - start)))
            center = start + (slot + 0.5) * (end - start) / bins
            reason, score = "temporal_bin_change", (change, -abs(t - center), -i)
        else:
            continue
        if slot not in chosen or score > chosen[slot]["score"]:
            png, size = frame_png(canvas)
            chosen[slot] = {"frame": timeline[i], "png": png, "size": size, "reason": reason, "score": score}
            # Base64 and two copies of metadata must fit as a final MCP result.
            require(sum(len(v["png"]) for v in chosen.values()) * 4 // 3 < limits.output_bytes - 128_000,
                    "output_limit", "Selected images exceed the output cap; reduce the frame budget or supply a smaller original.")
    selected = sorted(chosen.values(), key=lambda item: item["frame"]["index"])
    content, frames, delivered = [], [], {}
    for sample in selected:
        png = sample["png"]
        digest = hashlib.sha256(png).hexdigest()
        if digest not in delivered:
            # Content index 0 is the manifest text added by the service.
            delivered[digest] = len(content) + 1
            content.append({"type": "image", "mimeType": "image/png", "data": base64.b64encode(png).decode("ascii")})
        frames.append({**sample["frame"], "selection_reason": sample["reason"], "image_sha256": digest,
                       "content_index": delivered[digest], "image_width": sample["size"][0], "image_height": sample["size"][1],
                       "composited_rgba_sha256": hashes[sample["frame"]["index"]]})
    selected_indices = {f["index"] for f in frames}
    warnings = []
    if any(f["raw_duration_ms"] in (None, 0) for f in timeline):
        warnings.append("ambiguous_timing: missing or zero delays normalized to 100ms; do not infer speed")
    if len(selected_indices) < len(eligible):
        warnings.append("sampled_motion: an omitted gesture or caption may require bounded follow-up")
    if max(info["canvas_width"], info["canvas_height"]) > limits.long_edge:
        warnings.append("downscaled_derivative: text may be unreadable; do not invent missing text")
    result = {**info, "raw_frame_delays_ms": [f["raw_duration_ms"] for f in timeline],
              "timing_policy": TIMING_POLICY, "sample_policy": SAMPLE_POLICY, "compositing_policy": "gif-composite-v1",
              "decoded_all_frames": work_frames == info["frame_count"],
              "sampled": len(selected_indices) < info["frame_count"], "limits_hit": [], "frames": frames,
              "coverage": {"start_ms": start, "end_ms": end, "eligible_frames": len(eligible),
                           "returned_frames": len(frames), "omitted_frame_indices": [i for i in eligible if i not in selected_indices]},
              "decoder_version": "Pillow/" + PIL.__version__, "warnings": warnings,
              "work_pixels": info["canvas_width"] * info["canvas_height"] * work_frames,
              "decoded_frame_count": work_frames, "image_count": len(content)}
    return result, content
