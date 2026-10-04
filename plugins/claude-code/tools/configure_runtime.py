"""Explicit local enrollment; no dependency installation or host configuration."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gif_communication.contracts import GifError
from gif_communication.runtime import DEFAULT_LOCK, ENROLLMENT, fingerprint


def enroll(lock=DEFAULT_LOCK):
    lock = Path(lock)
    if not lock.is_absolute():
        raise ValueError("--lock must be an absolute user-controlled output path")
    document = {"schema_version": 2, "enrollment": dict(ENROLLMENT), "runtime": fingerprint()}
    encoded = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode()
    lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
    return lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK,
                        help="absolute destination (default: this package's .local/runtime-lock.json); existing files are never overwritten")
    args = parser.parse_args(argv)
    try:
        lock = enroll(args.lock)
    except (GifError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"Local runtime enrolled: {lock}")
    print("This records your local fingerprint; it does not qualify the original tested runtime or native host behavior.")
    print(f"Set GIF_RUNTIME_LOCK={lock} in trusted host settings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
