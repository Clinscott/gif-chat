"""Small MCP stdio server with an optional bundled library."""
import argparse
import asyncio
import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gif_communication import __version__
from gif_communication.contracts import GifError
from gif_communication.schemas import tools_for
from gif_communication.service import Service
from gif_communication.runtime import verify


async def serve(service):
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=16384)
    input_transport, _ = await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
    output_transport, output_protocol = await loop.connect_write_pipe(lambda: asyncio.streams.FlowControlMixin(loop=loop), sys.stdout.buffer)
    writer = asyncio.StreamWriter(output_transport, output_protocol, None, loop)
    tasks, initialized, ready = {}, False, False
    write_lock = asyncio.Lock()

    async def send(payload):
        async with write_lock:
            writer.write(json.dumps({"jsonrpc": "2.0", **payload}, separators=(",", ":"), allow_nan=False).encode() + b"\n")
            await writer.drain()

    async def error(request_id, code, message):
        await send({"id": request_id, "error": {"code": code, "message": message}})

    async def execute(request_id, name, arguments):
        try:
            result = await service.call(name, arguments)
            await send({"id": request_id, "result": result})
        except asyncio.CancelledError:
            pass  # MCP cancellation terminates work; no late success is emitted.
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            tasks.pop(request_id, None)

    async def janitor():
        while True:
            await asyncio.sleep(0.25)
            service.expire()

    cleanup = asyncio.create_task(janitor())
    try:
        while True:
            try:
                line = await reader.readline()
            except ValueError:
                await error(None, -32700, "Protocol message exceeds the 16 KiB input limit.")
                break
            if not line:
                break
            try:
                def no_constant(_):
                    raise ValueError("nonfinite")
                request = json.loads(line, parse_constant=no_constant)
                if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
                    raise ValueError("invalid")
            except (ValueError, UnicodeError, RecursionError):
                await error(None, -32700, "Invalid JSON-RPC message.")
                continue
            method, params = request["method"], request.get("params", {})
            request_id = request.get("id")
            if not isinstance(params, dict) or ("id" in request and (type(request_id) not in (str, int) or len(str(request_id)) > 128)):
                await error(None, -32600, "Invalid request envelope.")
                continue
            if "id" not in request:
                if method == "notifications/initialized" and initialized:
                    ready = True
                elif method == "notifications/cancelled":
                    cancelled_id = params.get("requestId")
                    if type(cancelled_id) in (str, int) and cancelled_id in tasks:
                        tasks[cancelled_id].cancel()
                continue
            if request_id in tasks:
                await error(request_id, -32600, "Duplicate active request id.")
            elif method == "initialize" and not initialized:
                offered = params.get("protocolVersion")
                if not isinstance(offered, str) or not isinstance(params.get("capabilities"), dict) or not isinstance(params.get("clientInfo"), dict):
                    await error(request_id, -32602, "Invalid initialization parameters.")
                    continue
                version = offered if offered in ("2025-11-25", "2025-06-18", "2024-11-05") else "2025-11-25"
                initialized = True
                capabilities = {"tools": {"listChanged": False}}
                if hasattr(service, "resources_list"):
                    capabilities["resources"] = {"listChanged": False}
                await send({"id": request_id, "result": {"protocolVersion": version, "capabilities": capabilities,
                    "serverInfo": {"name": "gif-communication", "version": __version__}}})
            elif not ready:
                await error(request_id, -32002, "Initialize this isolated session before using tools.")
            elif method == "ping":
                await send({"id": request_id, "result": {}})
            elif method == "tools/list":
                await send({"id": request_id, "result": {"tools": tools_for(service.library_enabled) + getattr(service, "extra_tools", [])}})
            elif method == "resources/list" and hasattr(service, "resources_list"):
                await send({"id": request_id, "result": {"resources": service.resources_list()}})
            elif method == "resources/read" and hasattr(service, "resource_read"):
                try:
                    resource = service.resource_read(params.get("uri"))
                    await send({"id": request_id, "result": resource})
                except ValueError:
                    await error(request_id, -32602, "Unknown UI resource.")
            elif method == "tools/call":
                if not isinstance(params.get("name"), str) or set(params) - {"name", "arguments", "_meta"}:
                    await error(request_id, -32602, "Invalid tool call.")
                elif tasks:
                    await send({"id": request_id, "result": GifError("busy", "One tool call runs at a time in this session.").result()})
                else:
                    tasks[request_id] = asyncio.create_task(execute(request_id, params["name"], params.get("arguments", {})))
            else:
                await error(request_id, -32601, "Method not supported by this isolated incoming-GIF server.")
    finally:
        cleanup.cancel()
        pending = list(tasks.values())
        for task in pending:
            task.cancel()
        await asyncio.gather(cleanup, *pending, return_exceptions=True)
        service.close()
        input_transport.close()
        writer.close()


async def run(service):
    loop, task = asyncio.get_running_loop(), asyncio.current_task()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, task.cancel)
    await serve(service)


def main():
    parser = argparse.ArgumentParser(description="Dedicated per-session incoming GIF MCP server")
    parser.add_argument("--allowed-root", required=True)
    parser.add_argument("--isolated-session", action="store_true")
    parser.add_argument("--library", action="store_true", help="Enable the bundled reply library from trusted launch configuration")
    args = parser.parse_args()
    try:
        verify()
        service = Service(args.allowed_root, args.isolated_session, library_enabled=args.library)
        asyncio.run(run(service))
    except (KeyboardInterrupt, asyncio.CancelledError, BrokenPipeError):
        pass
    except (GifError, OSError) as error:
        code = error.code if isinstance(error, GifError) else "startup_failed"
        message = ("The bundled library could not be verified."
                   if code.startswith("library_") else
                   "Private input root and isolated process configuration are required.")
        print(json.dumps({"error": code, "message": message}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
