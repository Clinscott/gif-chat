"""Bounded, keyless Commons search. Original bytes are fetched only on selection."""
from dataclasses import dataclass
from html.parser import HTMLParser
import http.client
import json
import math
import socket
import time
from urllib.parse import quote, urlencode, urlsplit

from gif_communication.contracts import DEFAULTS, GifError
from gif_communication.parser import parse


PROVIDER = "Wikimedia Commons"
API_URL = "https://commons.wikimedia.org/w/api.php"
API_BYTES = 512 * 1024
SEARCH_PAGES = 24
SEARCH_RESULTS = 12
QUERY_CHARS = 160
NETWORK_SECONDS = 5.0
PREVIEW_HOSTS = frozenset(("upload.wikimedia.org", "thumb.wikimedia.org"))


class RepositoryError(Exception):
    """Messages are deliberately safe to show in the local picker."""


def normalize_query(query):
    if (not isinstance(query, str) or not 0 < len(query) <= QUERY_CHARS or
            any(ord(character) < 32 or ord(character) == 127 for character in query)):
        raise RepositoryError("Enter a search of 1 to 160 characters.")
    try:
        encoded = query.encode("utf-8")
    except UnicodeError:
        raise RepositoryError("Enter a valid search phrase.") from None
    if len(encoded) > 640:
        raise RepositoryError("Enter a search of 1 to 160 characters.")
    query = " ".join(query.split())
    if not query:
        raise RepositoryError("Enter a search phrase.")
    return query


def safe_link(value):
    """An attribution link is never fetched or interpreted as an instruction."""
    if (not isinstance(value, str) or not value or len(value) > 2048 or
            any(ord(character) <= 32 or ord(character) == 127 for character in value)):
        return None
    try:
        parts = urlsplit(value)
        if (parts.scheme not in ("https", "http") or not parts.hostname or
                parts.username is not None or parts.password is not None):
            return None
        parts.port  # Reject malformed ports.
    except ValueError:
        return None
    return value


def media_url(value, *, preview=False):
    if not safe_link(value):
        return False
    try:
        parts = urlsplit(value)
        hosts = PREVIEW_HOSTS if preview else frozenset(("upload.wikimedia.org",))
        return (parts.scheme == "https" and parts.netloc in hosts and
                parts.path.startswith("/wikipedia/commons/") and
                "\\" not in parts.path and not parts.fragment)
    except ValueError:
        return False


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, _attributes):
        if tag in ("script", "style"):
            self.hidden += 1
        elif not self.hidden:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1
        elif not self.hidden:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value, maximum=300):
    if not isinstance(value, str) or len(value) > 8192:
        return ""
    parser = _PlainText()
    parser.feed(value)
    parser.close()
    text = " ".join("".join(parser.parts).split())
    text = "".join(character for character in text
                   if ord(character) >= 32 and ord(character) != 127 and
                   not 0x202A <= ord(character) <= 0x202E and
                   not 0x2066 <= ord(character) <= 0x2069)
    return text.strip()[:maximum]


def _network_bytes(url, maximum, mime):
    """Read one fixed HTTPS resource with one wall deadline and no redirects."""
    parts = urlsplit(url)
    connection = http.client.HTTPSConnection(parts.hostname, timeout=NETWORK_SECONDS)
    deadline = time.monotonic() + NETWORK_SECONDS
    try:
        connection.connect()
        transport = connection.sock

        def remaining():
            seconds = deadline - time.monotonic()
            if seconds <= 0:
                raise RepositoryError("The GIF repository took too long. Try again.")
            transport.settimeout(seconds)

        remaining()
        target = parts.path + ("?" + parts.query if parts.query else "")
        connection.request("GET", target, headers={
            "User-Agent": "GIFChat/0.5.0 (https://github.com/Clinscott/gif-chat)",
            "Accept": mime, "Accept-Encoding": "identity", "Connection": "close"})
        remaining()
        response = connection.getresponse()
        if response.status != 200:
            # This deliberately includes every redirect, even within Commons.
            raise RepositoryError("The GIF repository is unavailable. Try again.")
        content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != mime or response.getheader("Content-Encoding", "identity") != "identity":
            raise RepositoryError("The repository returned unsupported media.")
        content_length = response.getheader("Content-Length")
        if content_length is not None:
            if not content_length.isascii() or not content_length.isdigit() or int(content_length) > maximum:
                raise RepositoryError("The repository response exceeds the local size limit.")
        raw = bytearray()
        while len(raw) <= maximum:
            remaining()
            chunk = response.read1(min(64 * 1024, maximum + 1 - len(raw)))
            if time.monotonic() > deadline:
                raise RepositoryError("The GIF repository took too long. Try again.")
            if not chunk:
                break
            raw.extend(chunk)
            if response.isclosed():
                # HTTPResponse closes its stream when the declared body is complete.
                # The saved transport can already be closed at this point.
                break
        if len(raw) > maximum:
            raise RepositoryError("The repository response exceeds the local size limit.")
        if content_length is not None and len(raw) != int(content_length):
            raise RepositoryError("The repository response was incomplete. Try again.")
        return bytes(raw)
    except RepositoryError:
        raise
    except (OSError, socket.timeout, http.client.HTTPException, ValueError):
        raise RepositoryError("The GIF repository is unavailable. Try again.") from None
    finally:
        connection.close()


@dataclass(frozen=True)
class Candidate:
    title: str
    original_url: str
    preview_url: str
    source_url: str
    license: str
    license_url: str | None
    author: str
    bytes: int
    width: int
    height: int
    frames: int
    duration_ms: int | None

    def public(self, handle):
        return {"id": handle, "title": self.title, "preview_url": self.preview_url,
                "source_url": self.source_url, "license": self.license,
                "license_url": self.license_url, "author": self.author,
                "bytes": self.bytes, "width": self.width, "height": self.height,
                "frames": self.frames, "duration_ms": self.duration_ms}

    def attribution(self):
        return {"provider": PROVIDER, "title": self.title, "author": self.author,
                "license": self.license, "license_url": self.license_url,
                "source_url": self.source_url}


class CommonsRepository:
    def __init__(self, fetch=None):
        self._fetch = fetch if fetch is not None else _network_bytes

    def _get(self, url, maximum, mime):
        if mime == "application/json":
            parts = urlsplit(url)
            admitted = (parts.scheme == "https" and parts.netloc == "commons.wikimedia.org" and
                        parts.path == "/w/api.php" and not parts.fragment)
        else:
            admitted = media_url(url)
        if not admitted:
            raise RepositoryError("The repository returned an unsupported media address.")
        try:
            raw = self._fetch(url, maximum, mime)
        except RepositoryError:
            raise
        except (OSError, ValueError, http.client.HTTPException):
            raise RepositoryError("The GIF repository is unavailable. Try again.") from None
        if not isinstance(raw, bytes) or len(raw) > maximum:
            raise RepositoryError("The repository response exceeds the local size limit.")
        return raw

    def search(self, query):
        query = normalize_query(query)
        url = API_URL + "?" + urlencode({
            "action": "query", "format": "json", "formatversion": "2",
            "generator": "search", "gsrsearch": query + ' filemime:"image/gif"',
            "gsrnamespace": "6", "gsrlimit": str(SEARCH_PAGES),
            "prop": "imageinfo", "iiprop": "url|size|mime|metadata|extmetadata", "iiurlwidth": "220"})
        raw = self._get(url, API_BYTES, "application/json")
        try:
            response = json.loads(raw)
            if not isinstance(response, dict) or "error" in response:
                raise ValueError()
            result = response.get("query", {})
            if not isinstance(result, dict):
                raise ValueError()
            pages = result.get("pages", [])
            if not isinstance(pages, list) or len(pages) > SEARCH_PAGES:
                raise ValueError()
        except (ValueError, UnicodeError, RecursionError):
            raise RepositoryError("The repository returned an invalid search response. Try again.") from None
        candidates = []
        pages.sort(key=lambda page: page.get("index", SEARCH_PAGES + 1)
                   if isinstance(page, dict) and type(page.get("index")) is int else SEARCH_PAGES + 1)
        for page in pages:
            candidate = self._candidate(page)
            if candidate is not None and len(candidates) < SEARCH_RESULTS:
                candidates.append(candidate)
        return candidates

    @staticmethod
    def _candidate(page):
        if not isinstance(page, dict):
            return None
        title = page.get("title")
        images = page.get("imageinfo")
        if not isinstance(title, str) or len(title) > 300 or not title.startswith("File:"):
            return None
        if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
            return None
        image = images[0]
        original, preview = image.get("url"), image.get("thumburl")
        size, width, height = (image.get(key) for key in ("size", "width", "height"))
        if (image.get("mime") != "image/gif" or not media_url(original) or
                not media_url(preview, preview=True) or
                any(type(number) is not int for number in (size, width, height)) or
                not 0 < size <= DEFAULTS.source_bytes or
                not 0 < width <= DEFAULTS.edge or not 0 < height <= DEFAULTS.edge):
            return None
        metadata = image.get("metadata", [])
        if not isinstance(metadata, list) or len(metadata) > 64:
            return None
        properties = {item.get("name"): item.get("value") for item in metadata
                      if isinstance(item, dict) and isinstance(item.get("name"), str)}
        frames = properties.get("frameCount")
        if type(frames) is not int or not 1 < frames <= DEFAULTS.frames:
            return None
        duration = properties.get("duration")
        duration_ms = None
        if duration is not None:
            if type(duration) not in (float, int) or not math.isfinite(duration) or not 0 < duration <= 30:
                return None
            duration_ms = round(duration * 1000)
        if width * height * frames > DEFAULTS.pixels:
            return None
        extended = image.get("extmetadata", {})
        if not isinstance(extended, dict) or len(extended) > 64:
            return None

        def attribute(key, maximum=300):
            entry = extended.get(key, {})
            return plain_text(entry.get("value"), maximum) if isinstance(entry, dict) else ""

        license_entry = extended.get("LicenseUrl", {})
        license_url = safe_link(license_entry.get("value")) if isinstance(license_entry, dict) else None
        source = safe_link(image.get("descriptionurl")) or "https://commons.wikimedia.org/wiki/" + quote(title, safe="")
        return Candidate(plain_text(title[5:]), original, preview, source,
                         attribute("LicenseShortName", 120) or "License not listed",
                         license_url, attribute("Artist") or attribute("Credit") or "Author not listed",
                         size, width, height, frames, duration_ms)

    def download(self, candidate):
        raw = self._get(candidate.original_url, DEFAULTS.source_bytes, "image/gif")
        try:
            info = parse(raw)
        except GifError:
            raise RepositoryError("This GIF exceeds the local limits or is unsupported. Choose another.") from None
        if (len(raw) != candidate.bytes or info["canvas_width"] != candidate.width or
                info["canvas_height"] != candidate.height or info["frame_count"] != candidate.frames):
            raise RepositoryError("This GIF changed after the search. Search again to select its current original.")
        return raw
