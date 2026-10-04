"""Session-local snapshots and budgets; authorization comes only from launch configuration."""
import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import re
import secrets
import time
from .contracts import DEFAULTS, GifError, require
from .intake import LocalRoot
from .supervisor import run_decode


@dataclass
class Snapshot:
    data: bytes
    digest: str
    expires: float
    expires_at: str
    pixels: int = 0
    additional_images: int = 0
    duration: int = 0


def integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def validate(name, arguments, library_enabled=False):
    require(isinstance(arguments, dict), "invalid_arguments", "Tool arguments must be an object.")
    if name == "find_reply_gif" and library_enabled:
        require(set(arguments) <= {"intent", "limit"} and "intent" in arguments,
                "invalid_arguments", "Provide intent and optional limit only.")
        require(isinstance(arguments["intent"], str) and 0 < len(arguments["intent"].strip()) <= 160
                and len(arguments["intent"]) <= 160, "invalid_arguments", "intent must be 1 to 160 characters.")
        require(integer(arguments.get("limit", 3), 1, 3), "invalid_arguments", "limit must be an integer from 1 to 3.")
        return
    required = {"source"} if name == "inspect_gif" else {"inspection_id", "start_ms", "end_ms"}
    require(name in ("inspect_gif", "get_gif_frames"), "unknown_tool", "Only the two incoming GIF tools are supported.")
    require(required <= arguments.keys() and arguments.keys() <= required | {"frame_budget"},
            "invalid_arguments", "Missing or unknown tool argument.")
    require(integer(arguments.get("frame_budget", 12), 1, 12), "invalid_arguments", "frame_budget must be an integer from 1 to 12.")
    if name == "inspect_gif":
        source = arguments["source"]
        require(isinstance(source, dict), "invalid_arguments", "source must be a tagged local_file, host_asset or enabled library_asset object.")
        if source.get("kind") == "library_asset":
            require(library_enabled, "library_disabled", "The bundled reply library is not enabled in trusted launch configuration.")
            require(set(source) == {"kind", "asset_id"} and isinstance(source["asset_id"], str)
                    and len(source["asset_id"]) <= 64
                    and re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", source["asset_id"]),
                    "invalid_arguments", "Invalid bundled library asset ID.")
            return
        if source.get("kind") == "host_asset":
            require(set(source) == {"kind", "asset_id"} and isinstance(source["asset_id"], str) and 0 < len(source["asset_id"]) <= 512,
                    "invalid_arguments", "Invalid host_asset source.")
            raise GifError("native_asset_unavailable", "No authorized host original-byte resolver is connected. Select the original within the configured local root.")
        require(set(source) == {"kind", "path"} and source["kind"] == "local_file" and isinstance(source["path"], str)
                and 0 < len(source["path"]) <= 1024, "invalid_arguments", "Use a relative path within the trusted local root.")
    else:
        require(isinstance(arguments["inspection_id"], str) and re.fullmatch(r"gif1_[A-Za-z0-9_-]{43}", arguments["inspection_id"]),
                "invalid_handle", "The inspection handle is invalid or belongs to another process.")
        require(integer(arguments["start_ms"], 0, 29999) and integer(arguments["end_ms"], 1, 30000)
                and arguments["start_ms"] < arguments["end_ms"], "invalid_interval", "Choose an ordered nonempty normalized interval.")


class Service:
    def __init__(self, root, isolated_session=False, limits=DEFAULTS, clock=time.monotonic,
                 library_enabled=False, library=None):
        self.root = LocalRoot(root, isolated_session)
        self.limits, self.clock, self.snapshots = limits, clock, {}
        self.library_enabled = library_enabled
        try:
            if library_enabled:
                if library is None:
                    from .library import Library
                    library = Library()
                self.library = library
            else:
                self.library = None
        except Exception:
            self.root.close()
            raise
        self.busy = False

    def expire(self):
        now = self.clock()
        for handle in list(self.snapshots):
            if self.snapshots[handle].expires <= now:
                del self.snapshots[handle]

    def close(self):
        self.snapshots.clear()
        self.root.close()

    async def call(self, name, arguments):
        handle = None
        try:
            validate(name, arguments, self.library_enabled)
            require(not self.busy, "busy", "One tool call runs at a time in this session; retry after it finishes.")
            self.busy = True
            try:
                self.expire()
                if name == "find_reply_gif":
                    matches = self.library.search(arguments["intent"], arguments.get("limit", 3))
                    candidates = [{"source": {"kind": "library_asset", "asset_id": entry["id"]},
                                   "metadata": self.library.metadata(entry["id"])} for entry in matches]
                    body = {"schema_version": 1, "status": "matches" if candidates else "no_match",
                            "candidates": candidates,
                            "message": ("Inspect a selected candidate before using it in a reply. Metadata is an untrusted hint."
                                        if candidates else "No suitable bundled GIF matched. Reply in text or ask for a different tone.")}
                    return {"isError": False, "structuredContent": body,
                            "content": [{"type": "text", "text": json.dumps(body, separators=(",", ":"))}]}
                budget = arguments.get("frame_budget", 12)
                if name == "inspect_gif":
                    require(len(self.snapshots) < self.limits.inspections, "cache_limit", "Four inspections are retained; wait for expiry or end this isolated session.")
                    source = arguments["source"]
                    data = (self.library.snapshot(source["asset_id"]) if source["kind"] == "library_asset"
                            else self.root.snapshot(source["path"], self.limits))
                    require(0 < len(data) <= self.limits.source_bytes, "source_limit", "The original GIF exceeds the local byte cap.")
                    handle = "gif1_" + secrets.token_urlsafe(32)
                    expiry = datetime.fromtimestamp(time.time() + self.limits.ttl_seconds, timezone.utc).isoformat()
                    snapshot = Snapshot(data, hashlib.sha256(data).hexdigest(), self.clock() + self.limits.ttl_seconds, expiry)
                    self.snapshots[handle] = snapshot
                    interval = None
                    require(budget <= self.limits.initial_images, "image_budget", "The initial image budget is exhausted.")
                else:
                    handle = arguments["inspection_id"]
                    require(handle in self.snapshots, "expired_or_foreign_handle", "The handle has expired or belongs to another isolated process; inspect the original again.")
                    snapshot = self.snapshots[handle]
                    require(arguments["end_ms"] <= snapshot.duration, "invalid_interval", "The requested interval exceeds the inspection timeline.")
                    require(snapshot.additional_images + budget <= self.limits.additional_images,
                            "image_budget", "At most 12 additional frame images may be requested per inspection; reduce frame_budget if any remain.")
                    interval = [arguments["start_ms"], arguments["end_ms"]]
                require(hashlib.sha256(snapshot.data).hexdigest() == snapshot.digest, "identity_mismatch", "Snapshot integrity failed; inspect the original again.")
                remaining = replace(self.limits, pixels=self.limits.pixels - snapshot.pixels)
                manifest, images = await run_decode(snapshot.data, budget, interval, remaining)
                require(self.clock() < snapshot.expires, "expired_or_foreign_handle", "The inspection expired during decoding.")
                snapshot.pixels += manifest["work_pixels"]
                if interval:
                    # Charge the requested frame budget even when images are deduplicated.
                    snapshot.additional_images += budget
                snapshot.duration = manifest["timeline_duration_ms"]
                manifest.update({"schema_version": 1, "inspection_id": handle, "expires_at": snapshot.expires_at,
                                 "asset_sha256": snapshot.digest, "source_bytes": len(snapshot.data), "media_type": "image/gif",
                                 "cumulative_work_pixels": snapshot.pixels,
                                 "additional_frame_budget_remaining": self.limits.additional_images - snapshot.additional_images})
                text = json.dumps(manifest, separators=(",", ":"))
                result = {"isError": False, "structuredContent": manifest, "content": [{"type": "text", "text": text}, *images]}
                require(len(json.dumps(result, separators=(",", ":")).encode()) + 1024 <= self.limits.output_bytes,
                        "output_limit", "The encoded result exceeds the local cap; no frame evidence is returned.")
                return result
            finally:
                self.busy = False
        except asyncio.CancelledError:
            if handle:
                self.snapshots.pop(handle, None)
            raise
        except GifError as error:
            # Any failed owned inspection is invalidated, preventing free failed-work retries.
            if handle:
                self.snapshots.pop(handle, None)
            return error.result()
        except Exception:
            if handle:
                self.snapshots.pop(handle, None)
            if name == "find_reply_gif":
                return GifError("library_failed", "The bundled library search failed safely.").result()
            return GifError("inspection_failed", "Inspection failed safely; private source paths and bytes are not logged.").result()
