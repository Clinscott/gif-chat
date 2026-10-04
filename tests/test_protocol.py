import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from gif_communication.schemas import TOOLS
from tests.gif_factory import gif

PACKAGE = Path(__file__).resolve().parents[1]


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = gif([{"pixels": [1, 2]}, {"pixels": [2, 3]}, {"pixels": [3, 1]}])
        (self.root / "a.gif").write_bytes(self.data)
        self.proc = await asyncio.create_subprocess_exec(sys.executable, "-I", "-B", str(PACKAGE / "gif_communication/server.py"),
            "--allowed-root", str(self.root), "--isolated-session", stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=9 * 1024 * 1024,
            env={"PATH": "/usr/bin:/bin", "LANG": "C"})

    async def asyncTearDown(self):
        self.proc.stdin.close()
        await asyncio.wait_for(self.proc.wait(), 2)
        self.assertEqual((await self.proc.stderr.read()).decode(), "")
        self.temp.cleanup()

    async def send(self, message):
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", **message}).encode() + b"\n")
        await self.proc.stdin.drain()

    async def response(self):
        return json.loads(await asyncio.wait_for(self.proc.stdout.readline(), 6))

    async def initialize(self):
        await self.send({"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "synthetic-test", "version": "1"}}})
        result = await self.response()
        self.assertEqual(result["result"]["protocolVersion"], "2025-11-25")
        await self.send({"method": "notifications/initialized"})

    async def test_g20_exact_inventory_and_image_content(self):
        await self.initialize()
        await self.send({"id": 2, "method": "tools/list"})
        self.assertEqual((await self.response())["result"]["tools"], TOOLS)
        self.assertEqual([t["name"] for t in TOOLS], ["inspect_gif", "get_gif_frames"])
        await self.send({"id": 3, "method": "tools/call", "params": {"name": "inspect_gif", "arguments": {"source": {"kind": "local_file", "path": "a.gif"}}}})
        result = (await self.response())["result"]
        self.assertFalse(result["isError"], result)
        self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])
        self.assertEqual(result["structuredContent"]["asset_sha256"], hashlib.sha256(self.data).hexdigest())
        self.assertEqual([c["type"] for c in result["content"]], ["text", "image", "image", "image"])
        self.assertNotIn("_meta", result)
        self.assertNotIn(str(self.root), json.dumps(result))

    async def test_g18_no_estate_station_or_plugin_registration_needed(self):
        # This server was launched under an allowlist environment with neither estate nor Station.
        await self.initialize()
        await self.send({"id": 2, "method": "tools/call", "params": {"name": "inspect_gif", "arguments": {"source": {"kind": "local_file", "path": "a.gif"}}}})
        self.assertFalse((await self.response())["result"]["isError"])
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["a.gif"])

    async def test_g19_cancel_then_ping_and_retry(self):
        (self.root / "a.gif").write_bytes(gif([{"pixels": [i % 3 + 1], "width": 1, "height": 1} for i in range(28)], width=2048, height=2048))
        await self.initialize()
        await self.send({"id": 3, "method": "tools/call", "params": {"name": "inspect_gif", "arguments": {"source": {"kind": "local_file", "path": "a.gif"}}}})
        await asyncio.sleep(0.04)
        await self.send({"method": "notifications/cancelled", "params": {"requestId": 3}})
        await self.send({"id": 4, "method": "ping"})
        self.assertEqual((await self.response())["id"], 4)
        await asyncio.sleep(0.05)
        (self.root / "a.gif").write_bytes(self.data)
        await self.send({"id": 5, "method": "tools/call", "params": {"name": "inspect_gif", "arguments": {"source": {"kind": "local_file", "path": "a.gif"}}}})
        response = await self.response()
        self.assertEqual(response["id"], 5)
        self.assertFalse(response["result"]["isError"])

    async def test_initialization_and_unknown_methods_fail_closed(self):
        await self.send({"id": 0, "method": "tools/list"})
        self.assertEqual((await self.response())["error"]["code"], -32002)
        await self.initialize()
        await self.send({"id": 2, "method": "sampling/createMessage"})
        self.assertEqual((await self.response())["error"]["code"], -32601)
        await self.send({"id": 3, "method": "initialize", "params": {}})
        self.assertEqual((await self.response())["error"]["code"], -32601)

    async def test_invalid_json_does_not_echo_payload(self):
        self.proc.stdin.write(b'{"private":"synthetic-secret"\n')
        await self.proc.stdin.drain()
        response = await self.response()
        self.assertEqual(response["error"]["code"], -32700)
        self.assertNotIn("synthetic-secret", str(response))

    async def test_sigterm_exits_and_releases_root(self):
        await self.initialize()
        self.proc.send_signal(signal.SIGTERM)
        await asyncio.wait_for(self.proc.wait(), 2)
        from gif_communication.intake import LocalRoot
        root = LocalRoot(self.root, True)
        root.close()


if __name__ == "__main__":
    unittest.main()
