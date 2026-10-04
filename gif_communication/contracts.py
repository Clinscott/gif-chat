"""Local safety budgets, not provider limits."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    source_bytes: int = 20 * 1024 * 1024
    edge: int = 2048
    frames: int = 300
    duration_ms: int = 30_000
    pixels: int = 120_000_000
    worker_bytes: int = 256 * 1024 * 1024
    wall_seconds: float = 5.0
    output_bytes: int = 8 * 1024 * 1024
    long_edge: int = 640
    initial_images: int = 12
    additional_images: int = 12
    ttl_seconds: float = 900.0
    inspections: int = 4


DEFAULTS = Limits()
PYTHON_VERSION = "3.12.14"
PILLOW_VERSION = "12.3.0"
TIMING_POLICY = "gif-delay-v1: positive centiseconds preserved; missing/zero -> 100ms"
SAMPLE_POLICY = "change-bins-v1: endpoints plus strongest visual changes in temporal bins"


class GifError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)

    def result(self):
        import json
        body = {"schema_version": 1, "error": {"code": self.code, "message": self.message}}
        return {"isError": True, "structuredContent": body,
                "content": [{"type": "text", "text": json.dumps(body, separators=(",", ":"))}]}


def require(condition, code="malformed_gif", message="The GIF structure is invalid or incomplete."):
    if not condition:
        raise GifError(code, message)
