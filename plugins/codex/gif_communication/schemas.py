"""Versioned JSON Schemas used by tools/list and exported in schemas/."""


def obj(properties, required=None):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required,
            "additionalProperties": False}


def number(low, high):
    return {"type": "integer", "minimum": low, "maximum": high}


def array(items, maximum):
    return {"type": "array", "items": items, "maxItems": maximum}


HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
HANDLE = {"type": "string", "pattern": "^gif1_[A-Za-z0-9_-]{43}$"}
TEXT = {"type": "string", "maxLength": 256}
RAW = {"anyOf": [number(0, 655350), {"type": "null"}]}
TIMING = {"index": number(0, 299), "start_ms": number(0, 29999), "raw_duration_ms": RAW,
          "effective_duration_ms": number(1, 30000), "disposal": number(0, 3)}
FRAME = obj({**TIMING, "selection_reason": {"enum": ["complete_interval", "interval_opening", "interval_ending", "temporal_bin_change"]},
             "image_sha256": HASH, "content_index": number(1, 12), "image_width": number(1, 640),
             "image_height": number(1, 640), "composited_rgba_sha256": HASH})
MANIFEST = obj({
    "schema_version": {"const": 1}, "inspection_id": HANDLE, "expires_at": {"type": "string", "format": "date-time", "maxLength": 40},
    "asset_sha256": HASH, "source_bytes": number(1, 20971520), "media_type": {"const": "image/gif"},
    "canvas_width": number(1, 2048), "canvas_height": number(1, 2048), "frame_count": number(1, 300),
    "loop_count": {"anyOf": [number(0, 65535), {"type": "null"}]},
    "timeline_duration_ms": number(1, 30000), "timeline": array(obj(TIMING), 300),
    "raw_frame_delays_ms": array(RAW, 300), "timing_policy": TEXT, "sample_policy": TEXT, "compositing_policy": {"const": "gif-composite-v1"},
    "decoded_all_frames": {"type": "boolean"}, "sampled": {"type": "boolean"}, "limits_hit": array(TEXT, 8),
    "frames": array(FRAME, 12), "coverage": obj({"start_ms": number(0, 29999), "end_ms": number(1, 30000),
        "eligible_frames": number(1, 300), "returned_frames": number(1, 12), "omitted_frame_indices": array(number(0, 299), 300)}),
    "decoder_version": {"const": "Pillow/12.3.0"}, "warnings": array(TEXT, 8),
    "work_pixels": number(1, 120000000), "cumulative_work_pixels": number(1, 120000000),
    "decoded_frame_count": number(1, 300), "image_count": number(1, 12),
    "additional_frame_budget_remaining": number(0, 12),
    "measurement": obj({"wall_ms": {"type": "number", "minimum": 0},
        "parent_sampled_peak_rss_bytes": number(0, 268435456), "worker_reported_peak_rss_bytes": number(0, 268435456),
        "rss_poll_interval_ms": {"const": 10}})
})
ERROR = obj({"schema_version": {"const": 1}, "error": obj({"code": {"type": "string", "pattern": "^[a-z_]{1,48}$"}, "message": TEXT})})
OUTPUT = {"type": "object", "oneOf": [MANIFEST, ERROR]}
SOURCE = {"oneOf": [obj({"kind": {"const": "local_file"}, "path": {"type": "string", "minLength": 1, "maxLength": 1024}}),
                        obj({"kind": {"const": "host_asset"}, "asset_id": {"type": "string", "minLength": 1, "maxLength": 512}})]}
ASSET_ID = {"type": "string", "maxLength": 64, "pattern": "^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"}
LIBRARY_SOURCE = obj({"kind": {"const": "library_asset"}, "asset_id": ASSET_ID})
ENABLED_SOURCE = {"oneOf": [*SOURCE["oneOf"], LIBRARY_SOURCE]}
INPUTS = {
    "inspect_gif": obj({"source": SOURCE, "frame_budget": number(1, 12)}, ["source"]),
    "get_gif_frames": obj({"inspection_id": HANDLE, "start_ms": number(0, 29999), "end_ms": number(1, 30000),
                           "frame_budget": number(1, 12)}, ["inspection_id", "start_ms", "end_ms"])
}
LIBRARY_INPUTS = {
    "inspect_gif": obj({"source": ENABLED_SOURCE, "frame_budget": number(1, 12)}, ["source"]),
    "find_reply_gif": obj({"intent": {"type": "string", "minLength": 1, "maxLength": 160, "pattern": "\\S"},
                           "limit": number(1, 3)}, ["intent"])
}
LIBRARY_METADATA = obj({
    "id": LIBRARY_SOURCE["properties"]["asset_id"],
    "title": {"type": "string", "maxLength": 240}, "description": {"type": "string", "maxLength": 240},
    "tags": {"type": "array", "minItems": 1, "maxItems": 24,
             "items": {"type": "string", "maxLength": 32, "pattern": "^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"}},
    "spoke": {"type": "string", "maxLength": 240},
    "tone": {"type": "string", "maxLength": 240},
    "avoid_when": {"type": "array", "minItems": 1, "maxItems": 6,
                   "items": {"type": "string", "maxLength": 240}},
    "file": {"type": "string", "pattern": "^assets/[a-z][a-z0-9-]*\\.gif$"},
    "poster": {"type": "string", "pattern": "^posters/[a-z][a-z0-9-]*\\.png$"},
    "sha256": HASH, "poster_sha256": HASH,
    "bytes": number(1, 1048576), "width": number(1, 640), "height": number(1, 480),
    "frame_count": number(2, 24), "duration_ms": number(20, 3000),
    "provenance": obj({"kind": {"type": "string", "maxLength": 240},
                       "creator": {"type": "string", "maxLength": 240},
                       "source": {"type": "string", "maxLength": 240},
                       "rights": {"const": "MIT"}})
})
FIND_RESULT = obj({"schema_version": {"const": 1}, "status": {"enum": ["matches", "no_match"]},
                   "candidates": array(obj({"source": LIBRARY_SOURCE, "metadata": LIBRARY_METADATA}), 3),
                   "message": {"type": "string", "maxLength": 256}})
FIND_OUTPUT = {"type": "object", "oneOf": [FIND_RESULT, ERROR]}
DESCRIPTIONS = {
    "inspect_gif": "Inspect original GIF bytes within the configured private root. Returns ordered composited PNG evidence and timing, with a 15-minute process-scoped handle. Native asset resolution is unavailable in v1. Temporary snapshots only; no network or conversation storage.",
    "get_gif_frames": "Retrieve a bounded normalized time interval from the same immutable inspection. At most 12 additional frame images and 120 million cumulative canvas-pixels. No source reopen. Expired or foreign handles fail explicitly."
}
LIBRARY_DESCRIPTION = "Search the optional bundled GIF library by conversation intent. Returns up to three asset references and provenance hints, or no_match with a text fallback. Inspect a selected asset explicitly before using it; search does not decode or send media."
LIBRARY_INSPECT_DESCRIPTION = "Inspect original GIF bytes from the configured private root or an explicitly selected bundled library_asset. Returns ordered composited PNG evidence and timing, with a 15-minute process-scoped handle. Native host asset resolution remains unavailable."
TOOLS = [{"name": name, "description": DESCRIPTIONS[name], "inputSchema": schema, "outputSchema": OUTPUT,
          "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}}
         for name, schema in INPUTS.items()]


def tools_for(library_enabled=False):
    if not library_enabled:
        return TOOLS
    enabled = [dict(TOOLS[0], description=LIBRARY_INSPECT_DESCRIPTION,
                    inputSchema=LIBRARY_INPUTS["inspect_gif"]), TOOLS[1]]
    enabled.append({"name": "find_reply_gif", "description": LIBRARY_DESCRIPTION,
                    "inputSchema": LIBRARY_INPUTS["find_reply_gif"], "outputSchema": FIND_OUTPUT,
                    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                                    "idempotentHint": True, "openWorldHint": False}})
    return enabled
