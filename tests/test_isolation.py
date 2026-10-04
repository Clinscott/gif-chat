import asyncio
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import subprocess
import time
import unittest
from unittest.mock import patch
from gif_communication.contracts import DEFAULTS, GifError
from gif_communication.intake import LocalRoot
from gif_communication.service import Service
from tests.gif_factory import gif


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = gif([{"pixels": [1, 2]}])
        (self.root / "a.gif").write_bytes(self.data)
        self.reader = LocalRoot(self.root, True)

    def tearDown(self):
        self.reader.close()
        self.temp.cleanup()

    def test_requires_trusted_isolation_and_private_root(self):
        with self.assertRaises(GifError):
            LocalRoot(self.root)
        public = self.root / "public"
        public.mkdir(mode=0o755)
        with self.assertRaises(GifError):
            LocalRoot(public, True)

    def test_root_extended_acl_rejected_at_open_and_after_launch(self):
        acl = "everyone allow list,search,readattr,readextattr,readsecurity"
        directory = self.root / "acl-root"
        directory.mkdir(mode=0o700)
        subprocess.run(["/bin/chmod", "+a", acl, str(directory)], check=True)
        with self.assertRaises(GifError) as error:
            LocalRoot(directory, True)
        self.assertEqual(error.exception.code, "isolation_required")
        subprocess.run(["/bin/chmod", "+a", acl, str(self.root)], check=True)
        with self.assertRaises(GifError) as error:
            self.reader.snapshot("a.gif")
        self.assertEqual(error.exception.code, "isolation_required")

    def test_root_permissions_changed_during_read_fail_closed(self):
        original_read = os.read
        def changing_read(fd, count):
            data = original_read(fd, count)
            self.root.chmod(0o755)
            return data
        with patch("gif_communication.intake.os.read", side_effect=changing_read), self.assertRaises(GifError) as error:
            self.reader.snapshot("a.gif")
        self.assertEqual(error.exception.code, "isolation_required")

    def test_only_one_process_owns_root(self):
        with self.assertRaises(BlockingIOError):
            LocalRoot(self.root, True)

    def test_g16_traversal_and_absolute_paths(self):
        for name in ("../a.gif", "/etc/passwd", "a/../a.gif", "a//b", "a\\b", "https://x/y.gif", "./a.gif", "a\x00.gif"):
            with self.subTest(name=name), self.assertRaises(GifError):
                self.reader.snapshot(name)

    def test_g16_symlinks_devices_fifos_and_hardlinks(self):
        (self.root / "link.gif").symlink_to(self.root / "a.gif")
        (self.root / "dir").symlink_to(self.root, target_is_directory=True)
        (self.root / "device").symlink_to("/dev/zero")
        os.mkfifo(self.root / "fifo")
        for name in ("link.gif", "dir/a.gif", "device", "fifo"):
            with self.subTest(name=name), self.assertRaises(GifError):
                self.reader.snapshot(name)
        os.link(self.root / "a.gif", self.root / "alias.gif")
        with self.assertRaises(GifError):
            self.reader.snapshot("alias.gif")

    def test_g16_source_replacement_race(self):
        original_read = os.read
        called = False
        def racing_read(fd, count):
            nonlocal called
            data = original_read(fd, count)
            if not called:
                called = True
                replacement = self.root / "replacement"
                replacement.write_bytes(self.data)
                replacement.replace(self.root / "a.gif")
            return data
        with patch("gif_communication.intake.os.read", side_effect=racing_read), self.assertRaises(GifError) as error:
            self.reader.snapshot("a.gif")
        self.assertEqual(error.exception.code, "source_changed")

    def test_g16_source_mutation_race(self):
        original_read = os.read
        called = False
        def racing_read(fd, count):
            nonlocal called
            data = original_read(fd, count)
            if not called:
                called = True
                (self.root / "a.gif").write_bytes(b"changed")
            return data
        with patch("gif_communication.intake.os.read", side_effect=racing_read), self.assertRaises(GifError):
            self.reader.snapshot("a.gif")

    def test_size_and_cancellation(self):
        with self.assertRaises(GifError):
            self.reader.snapshot("a.gif", replace(DEFAULTS, source_bytes=1))
        with self.assertRaises(GifError) as error:
            self.reader.snapshot("a.gif", cancelled=lambda: True)
        self.assertEqual(error.exception.code, "cancelled")
        self.assertEqual((self.root / "a.gif").read_bytes(), self.data)


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = gif([{"pixels": [1, 2]}, {"pixels": [2, 3]}, {"pixels": [3, 1]}])
        (self.root / "a.gif").write_bytes(self.data)
        self.service = Service(self.root, True)

    async def asyncTearDown(self):
        self.service.close()
        self.temp.cleanup()

    async def inspect(self, **extra):
        return await self.service.call("inspect_gif", {"source": {"kind": "local_file", "path": "a.gif"}, **extra})

    async def test_g19_followup_is_same_immutable_snapshot(self):
        first = await self.inspect(frame_budget=2)
        self.assertFalse(first["isError"], first)
        handle = first["structuredContent"]["inspection_id"]
        (self.root / "a.gif").write_bytes(b"replaced")
        follow = await self.service.call("get_gif_frames", {"inspection_id": handle, "start_ms": 100, "end_ms": 200, "frame_budget": 1})
        self.assertFalse(follow["isError"], follow)
        self.assertEqual(follow["structuredContent"]["asset_sha256"], hashlib.sha256(self.data).hexdigest())
        self.assertEqual(follow["structuredContent"]["frames"][0]["index"], 1)
        self.assertEqual(follow["structuredContent"]["cumulative_work_pixels"], 10)
        self.assertEqual((self.root / "a.gif").read_bytes(), b"replaced")

    async def test_g16_foreign_handles(self):
        first = await self.inspect()
        with tempfile.TemporaryDirectory() as other_root:
            other = Service(other_root, True)
            try:
                result = await other.call("get_gif_frames", {"inspection_id": first["structuredContent"]["inspection_id"], "start_ms": 0, "end_ms": 100})
                self.assertEqual(result["structuredContent"]["error"]["code"], "expired_or_foreign_handle")
            finally:
                other.close()

    async def test_g19_expiry_and_shutdown_cleanup(self):
        first = await self.inspect()
        handle = first["structuredContent"]["inspection_id"]
        self.service.clock = lambda: time.monotonic() + 1000
        self.service.expire()
        result = await self.service.call("get_gif_frames", {"inspection_id": handle, "start_ms": 0, "end_ms": 100})
        self.assertTrue(result["isError"])
        self.assertEqual(self.service.snapshots, {})
        self.assertEqual(list(self.root.iterdir()), [self.root / "a.gif"])

    async def test_output_and_cumulative_image_budgets(self):
        first = await self.inspect(frame_budget=2)
        handle = first["structuredContent"]["inspection_id"]
        args = {"inspection_id": handle, "start_ms": 0, "end_ms": 300, "frame_budget": 6}
        for _ in range(2):
            self.assertFalse((await self.service.call("get_gif_frames", args))["isError"])
        final = await self.service.call("get_gif_frames", args)
        self.assertEqual(final["structuredContent"]["error"]["code"], "image_budget")
        self.assertNotIn(handle, self.service.snapshots)

    async def test_work_budget_cumulative_and_integrity_check(self):
        self.service.limits = replace(DEFAULTS, pixels=10)
        first = await self.inspect()
        handle = first["structuredContent"]["inspection_id"]
        result = await self.service.call("get_gif_frames", {"inspection_id": handle, "start_ms": 200, "end_ms": 300, "frame_budget": 1})
        self.assertEqual(result["structuredContent"]["error"]["code"], "work_limit")
        self.service.limits = DEFAULTS
        first = await self.inspect()
        handle = first["structuredContent"]["inspection_id"]
        self.service.snapshots[handle].data = b"mutated"
        result = await self.service.call("get_gif_frames", {"inspection_id": handle, "start_ms": 0, "end_ms": 100})
        self.assertEqual(result["structuredContent"]["error"]["code"], "identity_mismatch")

    async def test_strict_inputs_native_asset_and_unknown_tool(self):
        cases = [("inspect_gif", {"source": {"kind": "host_asset", "asset_id": "real-id-not-resolvable"}}),
                 ("inspect_gif", {"source": {"kind": "local_file", "path": "a.gif"}, "principal": "admin"}),
                 ("inspect_gif", {"source": {"kind": "local_file", "path": "a.gif"}, "frame_budget": True}),
                 ("find_reply_gif", {}), ("inspect_gif", None)]
        for name, args in cases:
            result = await self.service.call(name, args)
            self.assertTrue(result["isError"])
            self.assertNotIn(str(self.root), json.dumps(result))

    async def test_g15_cancellation_discards_snapshot(self):
        started = asyncio.Event()
        async def stalled(*args):
            started.set()
            await asyncio.sleep(60)
        with patch("gif_communication.service.run_decode", side_effect=stalled):
            task = asyncio.create_task(self.inspect())
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(self.service.snapshots, {})
        self.assertFalse(self.service.busy)

    async def test_cache_limit_and_invalid_interval(self):
        for _ in range(4):
            self.assertFalse((await self.inspect())["isError"])
        result = await self.inspect()
        self.assertEqual(result["structuredContent"]["error"]["code"], "cache_limit")
        handle = next(iter(self.service.snapshots))
        result = await self.service.call("get_gif_frames", {"inspection_id": handle, "start_ms": 0, "end_ms": 301})
        self.assertEqual(result["structuredContent"]["error"]["code"], "invalid_interval")


if __name__ == "__main__":
    unittest.main()
