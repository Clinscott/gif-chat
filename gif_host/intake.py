"""Stage one bounded original through a process-owned private input directory."""
import hashlib
import os
from pathlib import Path
import secrets
import stat
from gif_communication.contracts import DEFAULTS, GifError, require
from gif_communication.intake import require_private_root


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_nlink)


class HostRoot:
    def __init__(self, source_root, private_root):
        self.private = private_root
        self.path = Path(source_root)
        require(self.path.is_absolute(), "invalid_root", "Configure an absolute approved source directory.")
        self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            require_private_root(self.fd)
            self.root_identity = os.fstat(self.fd)
        except Exception:
            os.close(self.fd)
            self.fd = None
            raise

    def close(self):
        self.private.close()
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def check_root(self):
        require_private_root(self.fd)
        current = os.stat(self.path, follow_symlinks=False)
        require(stat.S_ISDIR(current.st_mode) and
                (current.st_dev, current.st_ino) == (self.root_identity.st_dev, self.root_identity.st_ino),
                "source_changed", "The approved source directory changed; restart this host process.")

    def snapshot(self, relative, limits=DEFAULTS, cancelled=lambda: False):
        require(isinstance(relative, str) and 0 < len(relative) <= 1024 and "\x00" not in relative,
                "invalid_source", "Select one relative original GIF path.")
        parts = relative.split("/")
        require(all(p not in ("", ".", "..") for p in parts) and "\\" not in relative and ":" not in relative,
                "invalid_source", "Absolute paths, URLs, traversal and alternate separators are unsupported.")
        opened, links = [], []
        stage_name, stage_fd = None, None
        try:
            self.check_root()
            require_private_root(self.private.fd)
            opened.append(os.dup(self.fd))
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=opened[-1])
                links.append((opened[-1], part, os.fstat(child)))
                opened.append(child)
            parent_fd = opened[-1]
            source_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                                dir_fd=parent_fd)
            opened.append(source_fd)
            before = os.fstat(source_fd)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                    "invalid_source", "Select a regular original with no symlink or hard-link aliases.")
            require(before.st_size <= limits.source_bytes, "source_too_large", "Select a GIF of at most 20 MiB.")
            candidate_name = secrets.token_hex(16) + ".gif"
            stage_fd = os.open(candidate_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                               0o600, dir_fd=self.private.fd)
            stage_name = candidate_name
            size, digest = 0, hashlib.sha256()
            while True:
                require(not cancelled(), "cancelled", "Inspection was cancelled.")
                block = os.read(source_fd, min(64 * 1024, limits.source_bytes + 1 - size))
                if not block:
                    break
                size += len(block)
                require(size <= limits.source_bytes, "source_too_large", "The source grew beyond the byte limit.")
                digest.update(block)
                view = memoryview(block)
                while view:
                    written = os.write(stage_fd, view)
                    require(written > 0, "source_unavailable", "Private staging failed safely.")
                    view = view[written:]
            os.close(stage_fd)
            stage_fd = None
            after = os.fstat(source_fd)
            linked = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            require(identity(before) == identity(after) == identity(linked) and size == before.st_size,
                    "source_changed", "The original changed during intake; select a stable original and retry.")
            for ancestor, name, old in links:
                current = os.stat(name, dir_fd=ancestor, follow_symlinks=False)
                require(stat.S_ISDIR(current.st_mode) and (old.st_dev, old.st_ino) == (current.st_dev, current.st_ino),
                        "source_changed", "The source directory changed during intake.")
            self.check_root()
            staged = self.private.snapshot(stage_name, limits, cancelled)
            require(hashlib.sha256(staged).digest() == digest.digest(),
                    "identity_mismatch", "Private staging identity changed; inspect the stable original again.")
            return staged
        except OSError:
            raise GifError("source_unavailable", "The selected original is unavailable or outside the approved source directory.") from None
        finally:
            if stage_fd is not None:
                os.close(stage_fd)
            if stage_name is not None:
                os.unlink(stage_name, dir_fd=self.private.fd)
            for fd in reversed(opened):
                os.close(fd)
