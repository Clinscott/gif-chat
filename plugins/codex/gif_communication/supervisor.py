"""Parent-controlled timeout, cancellation, RSS and pipe limits on macOS."""
import asyncio
import ctypes
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
from .contracts import DEFAULTS, GifError, require


def resident_bytes(pid):
    # proc_pidinfo(PROC_PIDTASKINFO), struct proc_taskinfo: virtual then resident size.
    lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    lib.proc_pidinfo.restype = ctypes.c_int
    buffer = ctypes.create_string_buffer(96)
    count = lib.proc_pidinfo(pid, 4, 0, buffer, len(buffer))
    return int.from_bytes(buffer.raw[8:16], sys.byteorder) if count >= 16 else None


def sandbox_command(worker, arguments):
    require(sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists(),
            "sandbox_unavailable", "This version requires the qualified macOS process sandbox.")
    # Worker reads runtime/source code and OS libraries, never the input root.
    roots = {str(Path(sys.base_prefix).resolve()), str(Path(sys.prefix).resolve()),
             str(Path(__file__).resolve().parents[1] / "gif_communication"),
             "/System", "/usr/lib", "/Library/Apple/System/Library"}
    read_rules = " ".join("(subpath " + json.dumps(path) + ")" for path in sorted(roots))
    profile = '(version 1)(deny default)(allow process-exec (literal ' + json.dumps(str(Path(sys.executable).resolve())) + '))'
    profile += '(allow file-read* ' + read_rules + ' (literal "/") (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))'
    profile += '(allow file-read* (literal ' + json.dumps(str(Path(__file__).resolve().parents[1])) + '))'
    profile += '(allow sysctl-read)(allow process-info* (target self))(allow signal (target self))'
    # No file writes, child processes, or network access are granted.
    return ["/usr/bin/sandbox-exec", "-p", profile, sys.executable, "-I", "-B", str(worker), *arguments]


async def run_process(command, data, limits=DEFAULTS):
    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.PIPE,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                                                env={"PATH": "/usr/bin:/bin", "LANG": "C", "PYTHONDONTWRITEBYTECODE": "1"},
                                                start_new_session=True)
    peak = 0

    async def read_output():
        chunks, total = [], 0
        while True:
            chunk = await proc.stdout.read(64 * 1024)
            if not chunk:
                return b"".join(chunks)
            total += len(chunk)
            require(total <= limits.output_bytes, "output_limit", "Worker output exceeded the byte cap.")
            chunks.append(chunk)

    async def feed():
        try:
            proc.stdin.write(data)
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            proc.stdin.close()

    async def watch():
        nonlocal peak
        while proc.returncode is None:
            rss = resident_bytes(proc.pid)
            if rss is not None:
                peak = max(peak, rss)
                require(rss <= limits.worker_bytes, "memory_limit", "Worker exceeded the local resident-memory budget.")
            require(time.monotonic() - started < limits.wall_seconds, "timeout", "Decoding exceeded the local wall-time budget.")
            await asyncio.sleep(0.01)

    tasks = [asyncio.create_task(read_output()), asyncio.create_task(feed()), asyncio.create_task(watch())]
    try:
        output, _, _ = await asyncio.wait_for(asyncio.gather(*tasks), limits.wall_seconds)
        code = await proc.wait()
        require(code == 0, "worker_failed", "The isolated decoder exited without a valid result.")
        return output, {"wall_ms": round((time.monotonic() - started) * 1000, 3),
                        "parent_sampled_peak_rss_bytes": peak, "rss_poll_interval_ms": 10}
    except asyncio.TimeoutError:
        raise GifError("timeout", "Decoding exceeded the local wall-time budget.") from None
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def run_decode(data, budget, interval=None, limits=DEFAULTS):
    worker = Path(__file__).with_name("worker.py")
    command = sandbox_command(worker, [json.dumps({"budget": budget, "interval": interval, "limits": asdict(limits)})])
    output, measured = await run_process(command, data, limits)
    try:
        result = json.loads(output)
    except (ValueError, UnicodeError):
        raise GifError("worker_failed", "The isolated worker did not return valid evidence.") from None
    if "error" in result:
        raise GifError(result["error"]["code"], result["error"]["message"])
    require(result["worker_reported_peak_rss_bytes"] <= limits.worker_bytes,
            "memory_limit", "The worker reported peak memory above the local budget; evidence was discarded.")
    result["manifest"]["measurement"] = {**measured, "worker_reported_peak_rss_bytes": result["worker_reported_peak_rss_bytes"]}
    return result["manifest"], result["content"]
