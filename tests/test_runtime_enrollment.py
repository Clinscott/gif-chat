"""Local enrollment and drift checks; no decoder, media, host or model calls."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gif_communication import runtime
from gif_communication.contracts import GifError
from tools.configure_runtime import enroll


class RuntimeEnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.lock = self.root / "local" / "runtime-lock.json"
        self.fingerprint = {
            "schema_version": 1, "python_version": "3.12.14", "pillow_version": "12.3.0",
            "platform": "Darwin", "machine": "explicit-fake-architecture",
            "python_executable_sha256": "a" * 64, "pillow_code_tree_sha256": "b" * 64,
        }

    def tearDown(self):
        self.temp.cleanup()

    def enroll_fixture(self):
        with patch("tools.configure_runtime.fingerprint", return_value=deepcopy(self.fingerprint)):
            enroll(self.lock)
        return json.loads(self.lock.read_text())

    def verify_fixture(self, fingerprint=None):
        with patch.dict(os.environ, {"GIF_RUNTIME_LOCK": str(self.lock)}), \
                patch("gif_communication.runtime.fingerprint", return_value=fingerprint or deepcopy(self.fingerprint)):
            runtime.verify()

    def test_local_enrollment_is_private_and_not_original_qualification(self):
        document = self.enroll_fixture()
        self.assertEqual(document["runtime"], self.fingerprint)
        self.assertEqual(document["enrollment"]["qualification"], "not-original-tested-runtime")
        self.assertIs(document["enrollment"]["installs_dependencies"], False)
        self.assertEqual(self.lock.stat().st_mode & 0o777, 0o600)
        self.verify_fixture()

    def test_enrollment_refuses_existing_file_and_symlink(self):
        self.enroll_fixture()
        original = self.lock.read_bytes()
        with patch("tools.configure_runtime.fingerprint", return_value=self.fingerprint), self.assertRaises(FileExistsError):
            enroll(self.lock)
        self.assertEqual(self.lock.read_bytes(), original)
        alias = self.root / "alias.json"
        alias.symlink_to(self.lock)
        with patch("tools.configure_runtime.fingerprint", return_value=self.fingerprint), self.assertRaises(FileExistsError):
            enroll(alias)
        self.assertEqual(self.lock.read_bytes(), original)

    def test_default_and_explicit_absolute_lock_selection(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(runtime, "DEFAULT_LOCK", self.lock):
            self.assertEqual(runtime.selected_lock(), self.lock)
        with patch.dict(os.environ, {"GIF_RUNTIME_LOCK": "relative.json"}), self.assertRaises(GifError):
            runtime.selected_lock()
        with self.assertRaises(ValueError):
            enroll(Path("relative.json"))

    def test_missing_malformed_and_historical_lock_fail_closed(self):
        self.lock.parent.mkdir()
        for body in (None, b"{broken", json.dumps(self.fingerprint).encode(), b"[]", b"null"):
            with self.subTest(body=body):
                if body is not None:
                    self.lock.write_bytes(body)
                with self.assertRaises(GifError) as error:
                    self.verify_fixture()
                self.assertEqual(error.exception.code, "runtime_mismatch")

    def test_any_enrolled_fingerprint_field_drift_is_rejected(self):
        self.enroll_fixture()
        for key in self.fingerprint:
            changed = deepcopy(self.fingerprint)
            changed[key] = 2 if key == "schema_version" else "different"
            with self.subTest(key=key), self.assertRaises(GifError):
                self.verify_fixture(changed)

    def test_qualification_metadata_and_numeric_aliases_cannot_be_rewritten(self):
        original = self.enroll_fixture()
        variants = []
        qualification = deepcopy(original)
        qualification["enrollment"]["qualification"] = "original-tested-runtime"
        variants.append(qualification)
        boolean_alias = deepcopy(original)
        boolean_alias["runtime"]["schema_version"] = True
        variants.append(boolean_alias)
        zero_alias = deepcopy(original)
        zero_alias["enrollment"]["installs_dependencies"] = 0
        variants.append(zero_alias)
        for value in variants:
            self.lock.write_text(json.dumps(value))
            with self.assertRaises(GifError):
                self.verify_fixture()

    def test_fingerprint_requires_actual_pinned_versions_and_macos(self):
        for python, system, pillow in (("3.12.13", "Darwin", "12.3.0"),
                                       ("3.12.14", "Linux", "12.3.0"),
                                       ("3.12.14", "Darwin", "12.2.0")):
            with self.subTest(python=python, system=system, pillow=pillow), \
                    patch("gif_communication.runtime.platform.python_version", return_value=python), \
                    patch("gif_communication.runtime.platform.system", return_value=system), \
                    patch("gif_communication.runtime.importlib.metadata.version", return_value=pillow), \
                    self.assertRaises(GifError):
                runtime.fingerprint()

    def test_fingerprint_hashes_selected_executable_and_pillow_code(self):
        package = self.root / "PIL"
        package.mkdir()
        (package / "__init__.py").write_bytes(b"explicit inert package source")
        (package / "_imaging.so").write_bytes(b"explicit inert binary bytes")
        (package / "ignored.pyc").write_bytes(b"ignored bytecode")
        executable = self.root / "python"
        executable.write_bytes(b"explicit inert executable bytes")
        with patch("gif_communication.runtime.platform.python_version", return_value="3.12.14"), \
                patch("gif_communication.runtime.platform.system", return_value="Darwin"), \
                patch("gif_communication.runtime.platform.machine", return_value="explicit-fake-architecture"), \
                patch("gif_communication.runtime.importlib.metadata.version", return_value="12.3.0"), \
                patch("gif_communication.runtime.importlib.util.find_spec", return_value=SimpleNamespace(origin=str(package / "__init__.py"))), \
                patch("gif_communication.runtime.sys.executable", str(executable)):
            before = runtime.fingerprint()
            self.assertEqual(before["python_executable_sha256"], hashlib.sha256(executable.read_bytes()).hexdigest())
            (package / "ignored.pyc").write_bytes(b"different ignored bytecode")
            self.assertEqual(runtime.fingerprint(), before)
            (package / "_imaging.so").write_bytes(b"changed binary bytes")
            self.assertNotEqual(runtime.fingerprint()["pillow_code_tree_sha256"], before["pillow_code_tree_sha256"])


if __name__ == "__main__":
    unittest.main()
