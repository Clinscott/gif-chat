"""Sandboxed one-shot worker. Input bytes on stdin; bounded JSON only on stdout."""
import json
import resource
import sys
from dataclasses import fields
from pathlib import Path

# -I removes cwd/PYTHONPATH; load only the reviewed package beside this file.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gif_communication.contracts import GifError, Limits


def main():
    settings = json.loads(sys.argv[1])
    limits = Limits(**settings["limits"])
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits.output_bytes, limits.output_bytes))
    try:
        from gif_communication.decoder import decode
        data = sys.stdin.buffer.read(limits.source_bytes + 1)
        manifest, content = decode(data, settings["budget"], settings["interval"], limits)
        payload = {"manifest": manifest, "content": content,
                   "worker_reported_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    except GifError as error:
        payload = {"error": {"code": error.code, "message": error.message}}
    except (Exception, MemoryError):
        payload = {"error": {"code": "decode_failed", "message": "The GIF could not be decoded completely within local limits."}}
    wire = json.dumps(payload, separators=(",", ":")).encode()
    if len(wire) > limits.output_bytes:
        wire = b'{"error":{"code":"output_limit","message":"Encoded frame output exceeds the local cap."}}'
    sys.stdout.buffer.write(wire)


if __name__ == "__main__":
    main()
