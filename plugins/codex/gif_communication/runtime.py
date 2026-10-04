"""Verify an explicitly enrolled local runtime without installing anything."""
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
from .contracts import GifError, require, PYTHON_VERSION, PILLOW_VERSION

DEFAULT_LOCK = Path(__file__).resolve().parents[1] / ".local" / "runtime-lock.json"
ENROLLMENT = {
    "kind": "user-local",
    "qualification": "not-original-tested-runtime",
    "installs_dependencies": False,
}


def selected_lock():
    value = os.environ.get("GIF_RUNTIME_LOCK")
    if not value:
        return DEFAULT_LOCK
    lock = Path(value)
    require(lock.is_absolute(), "runtime_mismatch", "GIF_RUNTIME_LOCK must be an absolute path from trusted host settings.")
    return lock


def fingerprint():
    require(platform.python_version() == PYTHON_VERSION and platform.system() == "Darwin",
            "runtime_mismatch", "This version requires macOS and the exact pinned Python runtime.")
    try:
        pillow_version = importlib.metadata.version("Pillow")
    except importlib.metadata.PackageNotFoundError:
        raise GifError("runtime_mismatch", "Pinned Pillow is required in the selected Python runtime.") from None
    require(pillow_version == PILLOW_VERSION, "runtime_mismatch", "Use the exact pinned Pillow version.")
    spec = importlib.util.find_spec("PIL")
    require(spec is not None and spec.origin, "runtime_mismatch", "Pinned Pillow is required in the selected Python runtime.")
    package = Path(spec.origin).parent
    items = []
    for path in sorted(package.rglob("*")):
        if path.is_file() and path.suffix in (".py", ".so", ".dylib"):
            items.append([path.relative_to(package).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()])
    return {"schema_version": 1, "python_version": platform.python_version(), "pillow_version": pillow_version,
            "platform": platform.system(), "machine": platform.machine(),
            "python_executable_sha256": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
            "pillow_code_tree_sha256": hashlib.sha256(json.dumps(items, separators=(",", ":")).encode()).hexdigest()}


def verify():
    lock = selected_lock()
    try:
        enrolled = json.loads(lock.read_text())
        require(type(enrolled) is dict and set(enrolled) == {"schema_version", "enrollment", "runtime"}
                and type(enrolled["schema_version"]) is int and enrolled["schema_version"] == 2
                and type(enrolled["enrollment"]) is dict and set(enrolled["enrollment"]) == set(ENROLLMENT)
                and all(type(enrolled["enrollment"][key]) is type(value) and enrolled["enrollment"][key] == value
                        for key, value in ENROLLMENT.items()),
                "runtime_mismatch", "Enroll the selected runtime explicitly before launch.")
        actual = fingerprint()
        expected = enrolled["runtime"]
        require(type(expected) is dict and set(expected) == set(actual)
                and all(type(expected[key]) is type(value) and expected[key] == value for key, value in actual.items()), "runtime_mismatch",
                "Runtime fingerprints differ from the enrolled local lock; enroll and review the intended runtime explicitly.")
    except (OSError, ValueError):
        raise GifError("runtime_mismatch", "A valid local runtime enrollment lock is required before launch.") from None
