"""Optional library contract without changing historical incoming-GIF fixtures."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from gif_communication.contracts import GifError
from gif_communication.schemas import FIND_OUTPUT, INPUTS, LIBRARY_INPUTS, tools_for
from gif_communication.service import Service, validate
from tests.gif_factory import gif


ROOT = Path(__file__).resolve().parents[1]


class FakeLibrary:
    def __init__(self, data):
        self.data = data
        self.item = {
            "id": "test-reply", "title": "A small test reply", "description": "A two-frame example",
            "tags": ["thanks"], "spoke": "corvus", "tone": "warm", "avoid_when": ["solemn news"],
            "file": "assets/test-reply.gif", "poster": "posters/test-reply.png",
            "sha256": hashlib.sha256(data).hexdigest(), "poster_sha256": "0" * 64,
            "bytes": len(data), "width": 2, "height": 1, "frame_count": 2,
            "duration_ms": 200,
            "provenance": {"kind": "generated", "creator": "test", "source": "local fixture", "rights": "MIT"},
        }

    def search(self, intent, limit=3):
        return [self.item] if "thanks" in intent.lower() else []

    def metadata(self, asset_id):
        if asset_id != self.item["id"]:
            raise GifError("unknown_library_asset", "The bundled asset is unavailable.")
        return dict(self.item)

    def snapshot(self, asset_id):
        self.metadata(asset_id)
        return self.data


class LibraryProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_inventory_and_source(self):
        self.assertEqual([tool["name"] for tool in tools_for()], ["inspect_gif", "get_gif_frames"])
        self.assertEqual(tools_for()[0]["inputSchema"], INPUTS["inspect_gif"])
        with tempfile.TemporaryDirectory() as root:
            service = Service(root, True)
            try:
                found = await service.call("find_reply_gif", {"intent": "thanks"})
                self.assertEqual(found["structuredContent"]["error"]["code"], "unknown_tool")
                chosen = await service.call("inspect_gif", {"source": {"kind": "library_asset", "asset_id": "test-reply"}})
                self.assertEqual(chosen["structuredContent"]["error"]["code"], "library_disabled")
                self.assertEqual(service.snapshots, {})
            finally:
                service.close()

    async def test_search_then_explicit_inspection(self):
        original = gif([{"pixels": [1, 2]}, {"pixels": [2, 3]}])
        library = FakeLibrary(original)
        with tempfile.TemporaryDirectory() as root:
            service = Service(root, True, library_enabled=True, library=library)
            try:
                tools = tools_for(True)
                self.assertEqual([tool["name"] for tool in tools], ["inspect_gif", "get_gif_frames", "find_reply_gif"])
                self.assertTrue(all(tool["annotations"]["readOnlyHint"] and
                                    not tool["annotations"]["openWorldHint"] for tool in tools))
                found = await service.call("find_reply_gif", {"intent": "Thanks for checking"})
                self.assertFalse(found["isError"], found)
                Draft202012Validator(FIND_OUTPUT).validate(found["structuredContent"])
                self.assertEqual(found["structuredContent"]["status"], "matches")
                self.assertEqual(service.snapshots, {})
                source = found["structuredContent"]["candidates"][0]["source"]
                self.assertEqual(source, {"kind": "library_asset", "asset_id": "test-reply"})
                inspected = await service.call("inspect_gif", {"source": source, "frame_budget": 2})
                self.assertFalse(inspected["isError"], inspected)
                self.assertEqual(inspected["structuredContent"]["asset_sha256"], library.item["sha256"])
                handle = inspected["structuredContent"]["inspection_id"]
                empty = await service.call("find_reply_gif", {"intent": "unmatched intent"})
                Draft202012Validator(FIND_OUTPUT).validate(empty["structuredContent"])
                self.assertEqual(empty["structuredContent"]["status"], "no_match")
                self.assertEqual(empty["structuredContent"]["candidates"], [])
                self.assertIn(handle, service.snapshots)
                library.data = b"changed after snapshot"
                follow = await service.call("get_gif_frames", {"inspection_id": handle, "start_ms": 0,
                                                               "end_ms": 100, "frame_budget": 1})
                self.assertFalse(follow["isError"], follow)
                self.assertEqual(follow["structuredContent"]["asset_sha256"], library.item["sha256"])
            finally:
                service.close()

    async def test_strict_public_schemas_and_runtime_rejection(self):
        published = {
            "inspect_gif.v2.json": LIBRARY_INPUTS["inspect_gif"],
            "find_reply_gif.v1.json": LIBRARY_INPUTS["find_reply_gif"],
            "find_reply_gif_result.v1.json": FIND_OUTPUT,
        }
        for filename, schema in published.items():
            document = json.loads((ROOT / "schemas" / filename).read_text())
            Draft202012Validator.check_schema(document)
            self.assertEqual({k: v for k, v in document.items() if k not in ("$schema", "$id")}, schema)
        for args in ({"intent": ""}, {"intent": " "}, {"intent": "x" * 161}, {"intent": "thanks", "limit": True},
                     {"intent": "thanks", "limit": 4}, {"intent": "thanks", "query": "hidden"}):
            self.assertTrue(list(Draft202012Validator(LIBRARY_INPUTS["find_reply_gif"]).iter_errors(args)))
            with self.assertRaises(GifError):
                validate("find_reply_gif", args, True)
        for source in ({"kind": "library_asset", "asset_id": "../escape"},
                       {"kind": "library_asset", "asset_id": "test-reply", "path": "x"}):
            args = {"source": source}
            self.assertTrue(list(Draft202012Validator(LIBRARY_INPUTS["inspect_gif"]).iter_errors(args)))
            with self.assertRaises(GifError):
                validate("inspect_gif", args, True)


if __name__ == "__main__":
    unittest.main()
