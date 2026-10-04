"""Read exactly one opened regular file relative to a trusted directory descriptor."""
import ctypes
import errno
import fcntl
import os
from pathlib import Path
import stat
import sys
from .contracts import DEFAULTS, GifError, require


def require_private_root(fd):
    info = os.fstat(fd)
    require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
            "isolation_required", "The input directory must be user-owned, mode 0700 and free of extended ACL entries.")
    require(sys.platform == "darwin", "isolation_required", "Root ACL validation requires the supported macOS runtime.")
    # Descriptor-based ACL inspection avoids reopening a replaceable pathname.
    lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    lib.acl_get_fd_np.argtypes = [ctypes.c_int, ctypes.c_int]
    lib.acl_get_fd_np.restype = ctypes.c_void_p
    lib.acl_get_entry.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
    lib.acl_get_entry.restype = ctypes.c_int
    lib.acl_free.argtypes = [ctypes.c_void_p]
    ctypes.set_errno(0)
    acl = lib.acl_get_fd_np(fd, 0x100)  # ACL_TYPE_EXTENDED
    if not acl:
        require(ctypes.get_errno() == errno.ENOENT, "isolation_required", "The input directory ACL could not be verified.")
        return
    try:
        entry = ctypes.c_void_p()
        ctypes.set_errno(0)
        status = lib.acl_get_entry(acl, 0, ctypes.byref(entry))  # ACL_FIRST_ENTRY
        require(status == -1 and ctypes.get_errno() == errno.ENOENT,
                "isolation_required", "Use a private input directory without extended ACL entries.")
    finally:
        lib.acl_free(acl)


class LocalRoot:
    def __init__(self, path, isolated_session=False):
        require(isolated_session, "isolation_required", "Launch one dedicated stdio process and private input root for this session.")
        path = Path(path)
        require(path.is_absolute(), "invalid_root", "The trusted launch configuration requires an absolute private input root.")
        self.fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            require_private_root(self.fd)
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            os.close(self.fd)
            self.fd = None
            raise

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def snapshot(self, relative, limits=DEFAULTS, cancelled=lambda: False):
        require(isinstance(relative, str) and 0 < len(relative) <= 1024 and "\x00" not in relative,
                "invalid_source", "Select one relative local GIF path.")
        parts = relative.split("/")
        require(all(part not in ("", ".", "..") for part in parts) and "\\" not in relative and ":" not in relative,
                "invalid_source", "Absolute paths, URLs, traversal and alternate separators are unsupported.")
        require_private_root(self.fd)
        opened = [os.dup(self.fd)]
        links = []
        try:
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=opened[-1])
                links.append((opened[-1], part, os.fstat(child)))
                opened.append(child)
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=opened[-1])
            parent_fd = opened[-1]
            opened.append(fd)
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                    "invalid_source", "Select a regular file with no symlink or hard-link aliases.")
            require(before.st_size <= limits.source_bytes, "source_too_large", "Select a GIF of at most 20 MiB.")
            chunks, size = [], 0
            while True:
                require(not cancelled(), "cancelled", "Inspection was cancelled.")
                block = os.read(fd, min(64 * 1024, limits.source_bytes + 1 - size))
                if not block:
                    break
                chunks.append(block)
                size += len(block)
                require(size <= limits.source_bytes, "source_too_large", "The source grew beyond the byte limit.")
            after = os.fstat(fd)
            linked = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            def identity(info):
                return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)
            require(identity(before) == identity(after) == identity(linked) and size == before.st_size,
                    "source_changed", "The source changed during intake; select a stable original and retry.")
            for ancestor, name, old in links:
                current = os.stat(name, dir_fd=ancestor, follow_symlinks=False)
                require((old.st_dev, old.st_ino) == (current.st_dev, current.st_ino) and stat.S_ISDIR(current.st_mode),
                        "source_changed", "The source directory changed during intake.")
            require_private_root(self.fd)
            return b"".join(chunks)
        except OSError:
            raise GifError("source_unavailable", "The selected file is unavailable or is not safely inside the configured root.") from None
        finally:
            for fd in reversed(opened):
                os.close(fd)
