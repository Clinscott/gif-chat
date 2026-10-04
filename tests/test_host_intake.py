"""Adapter boundary checks use inert bytes; no decoder or host conversation."""
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from gif_communication.contracts import DEFAULTS, GifError
from gif_host.server import HostService


class HostIntakeTests(unittest.TestCase):
    def setUp(self):
        self.source = tempfile.TemporaryDirectory()
        self.parent = tempfile.TemporaryDirectory()
        self.path = Path(self.source.name)
        self.data = b"inert adapter boundary fixture"
        (self.path / "original.gif").write_bytes(self.data)
        self.service = HostService(self.path, session_parent=self.parent.name)
        self.session_path = Path(self.service.session.name)

    def tearDown(self):
        self.service.close()
        self.source.cleanup()
        self.parent.cleanup()

    def test_private_unique_roots_exact_copy_and_owned_cleanup(self):
        other = HostService(self.path, session_parent=self.parent.name)
        other_path = Path(other.session.name)
        try:
            self.assertNotEqual(other_path, self.session_path)
            self.assertEqual(self.session_path.stat().st_mode & 0o777, 0o700)
            self.assertEqual(self.service.root.snapshot("original.gif"), self.data)
            self.assertEqual(list(self.session_path.iterdir()), [])
            self.assertEqual((self.path / "original.gif").read_bytes(), self.data)
            self.service.close()
            self.assertFalse(self.session_path.exists())
            self.assertTrue(other_path.exists())
        finally:
            other.close()
        self.assertFalse(other_path.exists())

    def test_traversal_aliases_nonregular_and_nested_paths(self):
        (self.path / "nested").mkdir()
        (self.path / "nested/clip.gif").write_bytes(self.data)
        self.assertEqual(self.service.root.snapshot("nested/clip.gif"), self.data)
        (self.path / "link.gif").symlink_to(self.path / "original.gif")
        (self.path / "alias-dir").symlink_to(self.path / "nested")
        os.mkfifo(self.path / "fifo.gif")
        for relative in ("../original.gif", str(self.path / "original.gif"), "./original.gif", "nested//clip.gif",
                         "link.gif", "alias-dir/clip.gif", "fifo.gif", "https://x/clip.gif"):
            with self.subTest(relative=relative), self.assertRaises(GifError):
                self.service.root.snapshot(relative)
        os.link(self.path / "original.gif", self.path / "hard.gif")
        with self.assertRaises(GifError):
            self.service.root.snapshot("hard.gif")
        self.assertEqual(list(self.session_path.iterdir()), [])

    def test_bounded_source_and_cancellation_leave_no_copy(self):
        with self.assertRaises(GifError) as error:
            self.service.root.snapshot("original.gif", replace(DEFAULTS, source_bytes=2))
        self.assertEqual(error.exception.code, "source_too_large")
        with self.assertRaises(GifError) as error:
            self.service.root.snapshot("original.gif", cancelled=lambda: True)
        self.assertEqual(error.exception.code, "cancelled")
        self.assertEqual(list(self.session_path.iterdir()), [])

    def test_original_replacement_or_mutation_rejected(self):
        for mode in ("replace", "mutate"):
            (self.path / "original.gif").write_bytes(self.data)
            read = os.read
            called = False
            def racing_read(fd, count):
                nonlocal called
                block = read(fd, count)
                if not called:
                    called = True
                    original = self.path / "original.gif"
                    if mode == "replace":
                        replacement = self.path / "replacement.gif"
                        replacement.write_bytes(self.data)
                        replacement.replace(original)
                    else:
                        original.write_bytes(b"changed")
                return block
            with self.subTest(mode=mode), patch("gif_host.intake.os.read", side_effect=racing_read), self.assertRaises(GifError) as error:
                self.service.root.snapshot("original.gif")
            self.assertEqual(error.exception.code, "source_changed")
            self.assertEqual(list(self.session_path.iterdir()), [])

    def test_root_replacement_rejected_and_new_root_preserved(self):
        moved = self.path.with_name(self.path.name + "-moved")
        self.path.rename(moved)
        self.path.mkdir(mode=0o700)
        (self.path / "unrelated").write_bytes(b"preserve")
        try:
            with self.assertRaises(GifError) as error:
                self.service.root.snapshot("original.gif")
            self.assertEqual(error.exception.code, "source_changed")
            self.assertEqual((self.path / "unrelated").read_bytes(), b"preserve")
        finally:
            (self.path / "unrelated").unlink()
            self.path.rmdir()
            moved.rename(self.path)

    def test_constructor_failure_cleanup_and_private_parent(self):
        with self.assertRaises(GifError):
            HostService("relative", session_parent=self.parent.name)
        self.assertEqual(list(Path(self.parent.name).iterdir()), [self.session_path])
        Path(self.parent.name).chmod(0o755)
        with self.assertRaises(GifError):
            HostService(self.path, session_parent=self.parent.name)
        Path(self.parent.name).chmod(0o700)

    def test_source_permissions_rechecked_and_staging_digest_verified(self):
        self.path.chmod(0o755)
        with self.assertRaises(GifError) as error:
            self.service.root.snapshot("original.gif")
        self.assertEqual(error.exception.code, "isolation_required")
        self.path.chmod(0o700)
        with patch.object(self.service.root.private, "snapshot", return_value=b"substituted"), self.assertRaises(GifError) as error:
            self.service.root.snapshot("original.gif")
        self.assertEqual(error.exception.code, "identity_mismatch")
        self.assertEqual(list(self.session_path.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
