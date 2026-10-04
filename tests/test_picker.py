import hashlib
import http.client
import json
import os
from pathlib import Path
import tempfile
import unittest

from gif_host.picker import Picker
from tests.gif_factory import gif


class PickerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        os.chmod(self.root, 0o700)
        self.picker = Picker(str(self.root))

    def tearDown(self):
        self.picker.close()
        self.temporary.cleanup()

    def request(self, method, path, data=None, headers=None):
        client = http.client.HTTPConnection(self.picker.authority, timeout=6)
        try:
            client.request(method, path, body=data, headers=headers or {})
            response = client.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            client.close()

    def test_page_and_no_ambient_inbox_discovery(self):
        status, raw, headers = self.request("GET", self.picker.prefix + "/")
        self.assertEqual(status, 200)
        self.assertIn(b'Say it with motion', raw)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.request("GET", "/")[0], 403)
        self.assertEqual(self.request("GET", self.picker.prefix + "/../runtime-lock.json")[0], 404)

    def test_user_selection_preserves_exact_original_and_builds_prompt(self):
        original = gif([{"pixels": [1, 2]}, {"pixels": [2, 1]}])
        status, raw, _ = self.request("POST", self.picker.prefix + "/stage", original,
                                      {"Origin": self.picker.origin, "Content-Type": "image/gif"})
        self.assertEqual(status, 200, raw)
        result = json.loads(raw)
        path = self.root / result["path"]
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(result["sha256"], hashlib.sha256(original).hexdigest())
        self.assertIn('"path":"' + result["path"] + '"', result["prompt"])
        self.assertNotIn(str(self.root), result["prompt"])
        self.picker.close()
        self.assertTrue(path.exists())  # Selected originals are user-owned inbox data.

    def test_cross_origin_wrong_host_and_missing_origin_cannot_write(self):
        original = gif([{"pixels": [1, 2]}])
        for headers in ({}, {"Origin": "http://attacker.example"},
                        {"Origin": self.picker.origin, "Host": "attacker.example"},
                        {"Origin": self.picker.origin, "Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.request("POST", self.picker.prefix + "/stage", original, headers)[0], 403)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_media_and_oversized_inputs_do_not_write(self):
        self.assertEqual(self.request("POST", self.picker.prefix + "/stage", b"not a gif",
                                      {"Origin": self.picker.origin})[0], 400)
        self.assertEqual(self.request("POST", self.picker.prefix + "/stage", b"",
                                      {"Origin": self.picker.origin, "Content-Length": "20971521"})[0], 413)
        self.assertEqual(list(self.root.iterdir()), [])
