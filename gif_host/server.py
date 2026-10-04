"""Host-configured source access plus one private session for each stdio process."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gif_communication.contracts import GifError, require
from gif_communication.intake import require_private_root
from gif_communication.runtime import verify
from gif_communication.server import run
from gif_communication.service import Service
from gif_host.intake import HostRoot
from gif_host.picker import Picker
from gif_host.ui import PICKER_TOOL, RESOURCE_URI, picker_result, resource, resource_descriptor


class HostService(Service):
    def __init__(self, source_root, library_enabled=False, session_parent=None):
        self.session = None
        self.picker = None
        self.source_root = source_root
        self.extra_tools = [PICKER_TOOL]
        if session_parent is not None:
            require(Path(session_parent).is_absolute(), "invalid_root", "The optional private session parent must be absolute.")
            fd = os.open(session_parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                require_private_root(fd)
            finally:
                os.close(fd)
        self.session = tempfile.TemporaryDirectory(prefix="gif-host-", dir=session_parent)
        try:
            # Remove any inherited extended ACL only from this newly owned directory.
            subprocess.run(["/bin/chmod", "-N", self.session.name], check=True,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.chmod(self.session.name, 0o700)
            super().__init__(self.session.name, True, library_enabled=library_enabled)
            try:
                self.root = HostRoot(source_root, self.root)
            except Exception:
                super().close()
                raise
        except Exception:
            self.session.cleanup()
            raise

    async def call(self, name, arguments):
        if name == "open_gif_picker":
            if not isinstance(arguments, dict) or arguments:
                return GifError("invalid_arguments", "The GIF picker takes no arguments.").result()
            try:
                if self.picker is None:
                    self.picker = Picker(self.source_root)
                return picker_result(self.picker.url)
            except (GifError, OSError):
                return GifError("picker_unavailable", "The local GIF picker could not start.").result()
        return await super().call(name, arguments)

    def resources_list(self):
        return [resource_descriptor()]

    def resource_read(self, uri):
        if uri != RESOURCE_URI:
            raise ValueError("Unknown resource")
        return resource()

    def close(self):
        if self.picker is not None:
            self.picker.close()
            self.picker = None
        super().close()
        if self.session is not None:
            self.session.cleanup()


def main():
    parser = argparse.ArgumentParser(description="GIF Communication host adapter")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--library", action="store_true")
    args = parser.parse_args()
    service = None
    try:
        verify()
        service = HostService(args.source_root, args.library, os.environ.get("GIF_SESSION_PARENT"))
        asyncio.run(run(service))
    except (KeyboardInterrupt, asyncio.CancelledError, BrokenPipeError):
        pass
    except (GifError, OSError, subprocess.SubprocessError) as error:
        code = error.code if isinstance(error, GifError) else "startup_failed"
        print(json.dumps({"error": code, "message": "Configure approved originals and the pinned runtime in trusted host settings."}), file=sys.stderr)
        return 1
    finally:
        if service is not None:
            service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
