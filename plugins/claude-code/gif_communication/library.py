"""Read-only, bounded snapshots of the bundled original reaction library."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .contracts import GifError


_ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_WORD = re.compile(r"[a-z0-9]+")
_FIELDS = {"id", "title", "description", "tags", "spoke", "tone", "avoid_when",
           "file", "poster", "sha256", "poster_sha256", "bytes", "width",
           "height", "frame_count", "duration_ms", "provenance"}
_PROVENANCE = {"kind", "creator", "source", "rights"}
_STOP = {"a", "an", "and", "are", "can", "for", "i", "in", "is", "it", "me",
         "my", "of", "on", "please", "the", "to", "we", "with", "you"}


def _fail(code="library_invalid"):
    raise GifError(code, "The bundled reaction library could not be verified.")


def _text(value, maximum=240):
    return isinstance(value, str) and 0 < len(value) <= maximum and value.strip() == value


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _open_child(directory_fd, name, maximum):
    if not isinstance(name, str) or "/" in name or name in ("", ".", ".."):
        _fail()
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_size > maximum or info.st_size < 1):
                _fail()
            with os.fdopen(fd, "rb", closefd=False) as handle:
                data = handle.read(maximum + 1)
            if len(data) != info.st_size:
                _fail()
            return data
        finally:
            os.close(fd)
    except (OSError, ValueError):
        _fail()


class Library:
    """Fixed, local catalog. Asset bytes are checked on every read."""

    def __init__(self, root=None):
        self.root = Path(root) if root is not None else Path(__file__).resolve().parents[1] / "library"
        self._catalog = self._read("catalog.json", None, 128 * 1024)
        try:
            catalog = json.loads(self._catalog)
        except (UnicodeError, ValueError):
            _fail()
        if not isinstance(catalog, dict) or set(catalog) != {"schema_version", "library_id", "assets"}:
            _fail()
        if (type(catalog["schema_version"]) is not int or catalog["schema_version"] != 1
                or catalog["library_id"] != "gif-chat-reactions-v1"):
            _fail()
        assets = catalog["assets"]
        if not isinstance(assets, list) or not 1 <= len(assets) <= 32:
            _fail()
        self._by_id = {}
        for entry in assets:
            self._validate(entry)
            if entry["id"] in self._by_id:
                _fail()
            self._by_id[entry["id"]] = entry
        self._entries = assets

    @staticmethod
    def _validate(entry):
        if not isinstance(entry, dict) or set(entry) != _FIELDS:
            _fail()
        asset_id = entry["id"]
        if not isinstance(asset_id, str) or len(asset_id) > 64 or not _ID.fullmatch(asset_id):
            _fail()
        if entry["file"] != f"assets/{asset_id}.gif" or entry["poster"] != f"posters/{asset_id}.png":
            _fail()
        if not all(_text(entry[key]) for key in ("title", "description", "spoke", "tone")):
            _fail()
        avoid = entry["avoid_when"]
        if not isinstance(avoid, list) or not 1 <= len(avoid) <= 6 or not all(_text(item) for item in avoid):
            _fail()
        tags = entry["tags"]
        if not isinstance(tags, list) or not 1 <= len(tags) <= 24 or not all(
                isinstance(tag, str) and len(tag) <= 32 and _ID.fullmatch(tag) for tag in tags):
            _fail()
        if len(tags) != len(set(tags)):
            _fail()
        if not all(isinstance(entry[key], str) and _HASH.fullmatch(entry[key])
                   for key in ("sha256", "poster_sha256")):
            _fail()
        if not (_integer(entry["bytes"], 1, 1024 * 1024)
                and _integer(entry["width"], 1, 640)
                and _integer(entry["height"], 1, 480)
                and _integer(entry["frame_count"], 2, 24)
                and _integer(entry["duration_ms"], 20, 3000)):
            _fail()
        provenance = entry["provenance"]
        if not isinstance(provenance, dict) or set(provenance) != _PROVENANCE or not all(
                _text(provenance[key], 240) for key in _PROVENANCE):
            _fail()
        if provenance["rights"] != "MIT":
            _fail()

    def _read(self, name, folder, maximum):
        try:
            if self.root.is_symlink():
                _fail()
            root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                if folder is None:
                    return _open_child(root_fd, name, maximum)
                folder_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=root_fd)
                try:
                    return _open_child(folder_fd, name, maximum)
                finally:
                    os.close(folder_fd)
            finally:
                os.close(root_fd)
        except (OSError, ValueError):
            _fail()

    @property
    def entries(self):
        return deepcopy(self._entries)

    def metadata(self, asset_id):
        if not isinstance(asset_id, str) or asset_id not in self._by_id:
            raise GifError("unknown_asset", "That reaction is not in the bundled library.")
        return deepcopy(self._by_id[asset_id])

    def _asset(self, asset_id, kind):
        entry = self.metadata(asset_id)
        if kind == "gif":
            data = self._read(asset_id + ".gif", "assets", 1024 * 1024)
            if len(data) != entry["bytes"] or not data.startswith((b"GIF87a", b"GIF89a")):
                _fail("asset_integrity_failed")
            digest = entry["sha256"]
        else:
            data = self._read(asset_id + ".png", "posters", 1024 * 1024)
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                _fail("asset_integrity_failed")
            digest = entry["poster_sha256"]
        if hashlib.sha256(data).hexdigest() != digest:
            _fail("asset_integrity_failed")
        return data

    def snapshot(self, asset_id):
        return self._asset(asset_id, "gif")

    def poster(self, asset_id):
        return self._asset(asset_id, "png")

    def search(self, intent, limit=3):
        if not isinstance(intent, str) or len(intent) > 160 or not _integer(limit, 1, 3):
            raise GifError("invalid_arguments", "Use a short intent and a limit from 1 to 3.")
        words = set(_WORD.findall(intent.lower())) - _STOP
        if not words:
            return []
        ranked = []
        for position, entry in enumerate(self._entries):
            tags = set(_WORD.findall(" ".join(entry["tags"]).replace("-", " ")))
            title = set(_WORD.findall(entry["title"].lower()))
            spoke = set(_WORD.findall((entry["spoke"] or "").lower()))
            description = set(_WORD.findall(entry["description"].lower()))
            score = 5 * len(words & tags) + 3 * len(words & title) + 2 * len(words & spoke) + len(words & description)
            if score:
                ranked.append((-score, position, entry))
        ranked.sort()
        return [deepcopy(entry) for _, _, entry in ranked[:limit]]
