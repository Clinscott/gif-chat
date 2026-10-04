import asyncio
import base64
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from jsonschema import Draft202012Validator
from gif_communication.schemas import INPUTS, OUTPUT
from gif_communication.service import Service, validate
from gif_communication.contracts import GifError
from tests.gif_factory import gif

PACKAGE = Path(__file__).resolve().parents[1]


class SchemaTests(unittest.IsolatedAsyncioTestCase):
    async def test_exported_schemas_are_valid_and_match_runtime(self):
        for name, schema in {**INPUTS, "evidence": OUTPUT}.items():
            published = json.loads((PACKAGE / "schemas" / f"{name}.v1.json").read_text())
            Draft202012Validator.check_schema(published)
            self.assertEqual({k: v for k, v in published.items() if k not in ("$schema", "$id")}, schema)

    async def test_success_and_error_results_validate(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "x.gif").write_bytes(gif([{"pixels": [1, 2]}, {"pixels": [2, 3], "delay": 0}]))
            service = Service(root, True)
            try:
                validator = Draft202012Validator(OUTPUT)
                result = await service.call("inspect_gif", {"source": {"kind": "local_file", "path": "x.gif"}})
                self.assertFalse(result["isError"])
                validator.validate(result["structuredContent"])
                for frame in result["structuredContent"]["frames"]:
                    block = result["content"][frame["content_index"]]
                    self.assertEqual(block["type"], "image")
                    self.assertEqual(hashlib.sha256(base64.b64decode(block["data"])).hexdigest(), frame["image_sha256"])
                bad = await service.call("inspect_gif", {"source": {"kind": "local_file", "path": "../x.gif"}})
                validator.validate(bad["structuredContent"])
                self.assertTrue(bad["isError"])
                # Unknown fields are rejected by both public contract and runtime.
                for source in ({"kind": "local_file", "path": "x.gif", "root": "/"}, {"kind": "local_file", "path": "x.gif", "asset_id": "x"}):
                    arguments = {"source": source}
                    self.assertTrue(list(Draft202012Validator(INPUTS["inspect_gif"]).iter_errors(arguments)))
                    with self.assertRaises(GifError):
                        validate("inspect_gif", arguments)
            finally:
                service.close()

    async def test_remaining_work_allows_prefix_reconstruction(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "x.gif").write_bytes(gif([{"pixels": [1, 2]}, {"pixels": [2, 3]}, {"pixels": [3, 1]}]))
            service = Service(root, True)
            service.limits = replace(service.limits, pixels=8)
            try:
                first = await service.call("inspect_gif", {"source": {"kind": "local_file", "path": "x.gif"}})
                self.assertFalse(first["isError"])
                second = await service.call("get_gif_frames", {"inspection_id": first["structuredContent"]["inspection_id"],
                    "start_ms": 0, "end_ms": 100, "frame_budget": 1})
                self.assertFalse(second["isError"], second)
                self.assertEqual(second["structuredContent"]["cumulative_work_pixels"], 8)
            finally:
                service.close()
