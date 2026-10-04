import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from gif_communication.contracts import DEFAULTS, GifError
from gif_communication.supervisor import run_process, run_decode, sandbox_command
from tests.gif_factory import gif


def command(code):
    worker = Path(__file__).resolve().parents[1] / "gif_communication/worker.py"
    return sandbox_command(worker, [])[:-1] + ["-c", code]


class SupervisorTests(unittest.IsolatedAsyncioTestCase):
    async def test_g15_timeout_kills_owned_worker(self):
        with self.assertRaises(GifError) as error:
            await run_process(command("import time; time.sleep(3)"), b"", replace(DEFAULTS, wall_seconds=0.1))
        self.assertEqual(error.exception.code, "timeout")

    async def test_g15_output_cap(self):
        with self.assertRaises(GifError) as error:
            await run_process(command("import sys; sys.stdout.write('x'*100000)"), b"", replace(DEFAULTS, output_bytes=4096))
        self.assertEqual(error.exception.code, "output_limit")

    async def test_g15_external_memory_watchdog(self):
        with self.assertRaises(GifError) as error:
            await run_process(command("import time; x=bytearray(80*1024*1024); time.sleep(2)"), b"",
                              replace(DEFAULTS, worker_bytes=40 * 1024 * 1024))
        self.assertEqual(error.exception.code, "memory_limit")

    async def test_g15_actual_worker_cancellation_reaps_pid(self):
        original = asyncio.create_subprocess_exec
        created = asyncio.Event()
        process = None
        async def track(*args, **kwargs):
            nonlocal process
            process = await original(*args, **kwargs)
            created.set()
            return process
        with patch("gif_communication.supervisor.asyncio.create_subprocess_exec", side_effect=track):
            task = asyncio.create_task(run_process(command("import time; time.sleep(3)"), b""))
            await created.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertIsNotNone(process.returncode)
        with self.assertRaises(ProcessLookupError):
            os.kill(process.pid, 0)

    async def test_network_original_reads_writes_and_exec_denied(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "sentinel"
            target.write_text("synthetic private data")
            code = """import socket,subprocess,os,json
checks={}
operations={
 'read':lambda:open(PATH).read(),
 'write':lambda:open(PATH,'w').write('changed'),
 'network':lambda:socket.socket().connect(('127.0.0.1',9)),
 'exec':lambda:subprocess.run(['/usr/bin/true'],check=True)
}
for name,operation in operations.items():
 try: operation(); checks[name]=False
 except PermissionError: checks[name]=True
checks['environment']=not bool(os.environ.get('GIF_TEST_SECRET'))
print(json.dumps(checks))
""".replace("PATH", repr(str(target)))
            with patch.dict(os.environ, {"GIF_TEST_SECRET": "synthetic"}):
                output, _ = await run_process(command(code), b"")
            self.assertEqual(json.loads(output), {"read": True, "write": True, "network": True, "exec": True, "environment": True})
            self.assertEqual(target.read_text(), "synthetic private data")

    async def test_near_pixel_limit_measured(self):
        # Tiny delta rectangles still require 117,440,512 composited canvas-pixels.
        data = gif([{"pixels": [i % 3 + 1], "width": 1, "height": 1} for i in range(28)], width=2048, height=2048)
        manifest, _ = await run_decode(data, 12)
        self.assertEqual(manifest["work_pixels"], 117440512)
        self.assertLess(manifest["measurement"]["wall_ms"], 5000)
        self.assertLess(manifest["measurement"]["worker_reported_peak_rss_bytes"], DEFAULTS.worker_bytes)


if __name__ == "__main__":
    unittest.main()
