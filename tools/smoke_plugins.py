"""Exercise complete packages over real stdio MCP, without starting a model."""
import argparse
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_plugins import verify


def smoke(package):
    verify(package)
    with tempfile.TemporaryDirectory(prefix="gif-chat-smoke-") as temporary:
        source_root = Path(temporary) / "inbox"
        source_root.mkdir(mode=0o700)
        original = (ROOT / "tests/fixtures/asset-01.gif").read_bytes()
        (source_root / "clip.gif").write_bytes(original)
        env = {"PATH": "/usr/bin:/bin", "GIF_PYTHON": sys.executable,
               "GIF_SOURCE_ROOT": str(source_root), "GIF_RUNTIME_LOCK": os.environ.get("GIF_RUNTIME_LOCK", str(ROOT / ".local/runtime-lock.json"))}
        child = subprocess.Popen(["/bin/sh", str(package / "bin/gif-communication-host")],
                                 cwd=package, env=env, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        selector = selectors.DefaultSelector()
        os.set_blocking(child.stdout.fileno(), False)
        os.set_blocking(child.stderr.fileno(), False)
        selector.register(child.stdout, selectors.EVENT_READ, "stdout")
        selector.register(child.stderr, selectors.EVENT_READ, "stderr")
        buffer = bytearray()
        request_id = 0
        picker = None

        def rpc(method, params):
            nonlocal request_id, buffer
            request_id += 1
            request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            child.stdin.write(json.dumps(request).encode() + b"\n")
            deadline = time.monotonic() + 10
            while b"\n" not in buffer:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Packaged MCP response deadline")
                for key, _ in selector.select(0.1):
                    raw = os.read(key.fileobj.fileno(), 65536)
                    if key.data == "stderr" or not raw:
                        raise RuntimeError("Packaged MCP startup/transport failure")
                    buffer.extend(raw)
                    if len(buffer) > 9 * 1024 * 1024:
                        raise RuntimeError("MCP response exceeded limit")
            line, _, remainder = buffer.partition(b"\n")
            buffer = bytearray(remainder)
            response = json.loads(line)
            if response.get("id") != request_id or "error" in response:
                raise RuntimeError("MCP response identity/error mismatch")
            return response["result"]

        def inspect(path):
            result = rpc("tools/call", {"name": "inspect_gif", "arguments": {
                "source": {"kind": "local_file", "path": path}, "frame_budget": 6}})
            assert result["isError"] is False, result
            evidence = result["structuredContent"]
            assert evidence["asset_sha256"] == hashlib.sha256(original).hexdigest()
            for frame in evidence["frames"]:
                content = result["content"][frame["content_index"]]
                raw = base64.b64decode(content["data"], validate=True)
                assert raw.startswith(b"\x89PNG\r\n\x1a\n")
                assert hashlib.sha256(raw).hexdigest() == frame["image_sha256"]
            return evidence

        try:
            initialized = rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                             "clientInfo": {"name": "gif-chat-smoke", "version": "1"}})
            assert initialized["serverInfo"]["version"] == "0.4.0"
            assert "resources" in initialized["capabilities"]
            child.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            names = [tool["name"] for tool in rpc("tools/list", {})["tools"]]
            assert names == ["inspect_gif", "get_gif_frames", "open_gif_picker"]
            evidence = inspect("clip.gif")
            followup = rpc("tools/call", {"name": "get_gif_frames", "arguments": {
                "inspection_id": evidence["inspection_id"], "start_ms": 0,
                "end_ms": evidence["timeline_duration_ms"], "frame_budget": 3}})
            assert followup["isError"] is False
            denied = rpc("tools/call", {"name": "inspect_gif", "arguments": {
                "source": {"kind": "local_file", "path": "../escape.gif"}}})
            assert denied["isError"] is True
            resources = rpc("resources/list", {})["resources"]
            resource = rpc("resources/read", {"uri": resources[0]["uri"]})["contents"][0]
            assert resource["mimeType"] == "text/html;profile=mcp-app"
            assert "GIF" in resource["text"]
            result = rpc("tools/call", {"name": "open_gif_picker", "arguments": {}})
            assert result["isError"] is False
            picker = urlsplit(result["structuredContent"]["url"])
            client = http.client.HTTPConnection(picker.hostname, picker.port, timeout=6)
            try:
                client.request("POST", picker.path + "stage", body=original,
                               headers={"Origin": f"http://{picker.netloc}", "Content-Type": "image/gif"})
                response = client.getresponse()
                staged = json.loads(response.read())
                assert response.status == 200, staged
                assert (source_root / staged["path"]).read_bytes() == original
            finally:
                client.close()
            inspect(staged["path"])
        finally:
            child.stdin.close()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)
            selector.close()
            for stream in (child.stdout, child.stderr):
                stream.close()
        assert child.returncode == 0, "MCP did not shut down normally"
        if picker:
            client = http.client.HTTPConnection(picker.hostname, picker.port, timeout=1)
            try:
                try:
                    client.request("GET", picker.path)
                except OSError:
                    pass
                else:
                    raise AssertionError("Process-owned picker remained reachable after shutdown")
            finally:
                client.close()
        verify(package)
        return {"host": package.name, "passed": True, "tools": names,
                "source_sha256": hashlib.sha256(original).hexdigest(),
                "ordered_png_images": evidence["image_count"], "stdio_calls": request_id,
                "picker_upload_byte_exact": True, "owned_shutdown": True,
                "native_host_loading": "not_exercised", "model_calls": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugins", type=Path, default=ROOT / "plugins")
    args = parser.parse_args()
    print(json.dumps([smoke((args.plugins / host).resolve()) for host in ("codex", "claude-code")], indent=2))
