import os
from pathlib import Path
import tempfile
import unittest
from tools.build_plugins import build, verify


class ReleasePackageTests(unittest.TestCase):
    def test_inventory_rejects_extra_directory_and_special_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            build(root)
            extra = root / "codex/user-data"
            extra.mkdir()
            with self.assertRaises(ValueError):
                verify(root / "codex")
            with self.assertRaises(ValueError):
                build(root)
            self.assertTrue(extra.is_dir())
            extra.rmdir()
            os.mkfifo(extra)
            with self.assertRaises(ValueError):
                verify(root / "codex")
            with self.assertRaises(ValueError):
                build(root)
            self.assertTrue(extra.exists())

    def test_rebuild_preserves_modified_user_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            build(root)
            owned = root / "codex/README.md"
            owned.write_text("user changes")
            with self.assertRaises(ValueError):
                build(root)
            self.assertEqual(owned.read_text(), "user changes")

    def test_rebuild_and_both_package_identities(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            before = build(root)
            after = build(root)
            self.assertEqual(before, after)
            for host in before:
                self.assertEqual(verify(root / host)["host"], host)

    def test_symlinked_root_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target = root / "preserve"
            target.mkdir()
            (root / "codex").symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                build(root)
            self.assertTrue(target.is_dir())
