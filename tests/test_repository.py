import hashlib
import http.client
import io
import json
from unittest.mock import Mock, patch
import unittest
from urllib.parse import parse_qs, urlsplit

from gif_communication.contracts import DEFAULTS
from gif_host.repository import (API_BYTES, Candidate, CommonsRepository, RepositoryError,
                                 SEARCH_PAGES, _network_bytes, media_url, normalize_query,
                                 plain_text, safe_link)
from tests.gif_factory import gif


ORIGINAL_URL = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Dance.gif?download=1"
PREVIEW_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Dance.gif/220px-Dance.gif"


def page(original=None, **image_changes):
    original = original if original is not None else gif([{"pixels": [1, 2]}, {"pixels": [2, 1]}])
    image = {"url": ORIGINAL_URL, "thumburl": PREVIEW_URL, "mime": "image/gif",
             "size": len(original), "width": 2, "height": 1,
             "descriptionurl": "https://commons.wikimedia.org/wiki/File:Dance.gif",
             "metadata": [{"name": "frameCount", "value": 2}, {"name": "duration", "value": .2}],
             "extmetadata": {"Artist": {"value": '<a href="https://artist.example">Someone</a>'},
                             "LicenseShortName": {"value": "CC BY-SA 4.0"},
                             "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"}}}
    image.update(image_changes)
    return {"title": "File:Dance.gif", "index": 1, "imageinfo": [image]}


class RepositoryTests(unittest.TestCase):
    def repository(self, pages, original=None):
        def fetch(url, maximum, mime):
            self.fetched.append((url, maximum, mime))
            if mime == "application/json":
                return json.dumps({"query": {"pages": pages}}).encode()
            return original
        self.fetched = []
        return CommonsRepository(fetch)

    def test_search_is_fixed_bounded_and_does_not_fetch_original(self):
        repository = self.repository([page()])
        candidate = repository.search("  happy cat  ")[0]
        self.assertEqual(len(self.fetched), 1)
        address, limit, mime = self.fetched[0]
        parts = urlsplit(address)
        self.assertEqual((parts.scheme, parts.netloc, parts.path),
                         ("https", "commons.wikimedia.org", "/w/api.php"))
        parameters = parse_qs(parts.query)
        self.assertEqual(parameters["gsrsearch"], ['happy cat filemime:"image/gif"'])
        self.assertEqual(parameters["gsrnamespace"], ["6"])
        self.assertEqual(parameters["gsrlimit"], [str(SEARCH_PAGES)])
        self.assertEqual(parameters["iiurlwidth"], ["220"])
        self.assertEqual((limit, mime), (API_BYTES, "application/json"))
        self.assertEqual(candidate.author, "Someone")
        self.assertEqual(candidate.duration_ms, 200)
        self.assertNotIn("original_url", candidate.public("opaque"))

    def test_search_sorts_index_filters_static_and_bounds_results(self):
        pages = []
        for index in range(24, 0, -1):
            entry = page()
            entry.update(index=index, title="File:Animation" + str(index) + ".gif")
            pages.append(entry)
        pages[-1]["imageinfo"][0]["metadata"] = [{"name": "frameCount", "value": 1}]
        results = self.repository(pages).search("motion")
        self.assertEqual(len(results), 12)
        self.assertEqual(results[0].title, "Animation2.gif")
        self.assertEqual(results[-1].title, "Animation13.gif")

    def test_query_bounds_controls_and_non_strings(self):
        for query in (None, True, 1, "", "  ", "a" * 161, "cat\n", "\x00", "\ud800"):
            with self.subTest(query=repr(query)), self.assertRaises(RepositoryError):
                normalize_query(query)
        repository = self.repository([])
        repository.search("cat&gsrnamespace=0")
        self.assertEqual(parse_qs(urlsplit(self.fetched[0][0]).query)["gsrnamespace"], ["6"])

    def test_hostile_original_and_preview_addresses_are_never_fetched(self):
        bad = ["http://upload.wikimedia.org/wikipedia/commons/a.gif",
               "https://upload.wikimedia.org.evil.example/wikipedia/commons/a.gif",
               "https://upload.wikimedia.org@evil.example/wikipedia/commons/a.gif",
               "https://upload.wikimedia.org:443/wikipedia/commons/a.gif",
               "https://127.0.0.1/wikipedia/commons/a.gif",
               "file:///private/a.gif", "javascript:alert(1)",
               "https://upload.wikimedia.org/elsewhere/a.gif",
               "https://upload.wikimedia.org/wikipedia/commons/a.gif#fragment"]
        for address in bad:
            with self.subTest(address=address):
                repository = self.repository([page(url=address), page(thumburl=address)])
                self.assertEqual(repository.search("cat"), [])
                self.assertEqual(len(self.fetched), 1)
        thumb = "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Dance.gif/220px-Dance.gif"
        self.assertTrue(media_url(thumb, preview=True))
        self.assertFalse(media_url(thumb))

    def test_source_budgets_filter_unsupported_results(self):
        invalid = [{"size": DEFAULTS.source_bytes + 1}, {"size": True}, {"width": 2049},
                   {"height": 0}, {"mime": "video/webm"},
                   {"metadata": [{"name": "frameCount", "value": 301}]},
                   {"metadata": [{"name": "frameCount", "value": 2}, {"name": "duration", "value": 31}]},
                   {"metadata": []}, {"metadata": [{"name": "frameCount", "value": "2"}]}]
        for changes in invalid:
            with self.subTest(changes=changes):
                self.assertEqual(self.repository([page(**changes)]).search("cat"), [])

    def test_attribution_is_plain_text_and_links_have_safe_schemes(self):
        extended = {"Artist": {"value": '<script>secret()</script><b>Alice &amp; Bob</b>\u202E'},
                    "LicenseShortName": {"value": '<a href="javascript:bad()">CC BY</a>'},
                    "LicenseUrl": {"value": "javascript:bad()"}}
        candidate = self.repository([page(extmetadata=extended, descriptionurl="data:text/html,bad")]).search("cat")[0]
        self.assertEqual(candidate.author, "Alice & Bob")
        self.assertEqual(candidate.license, "CC BY")
        self.assertIsNone(candidate.license_url)
        self.assertEqual(candidate.source_url, "https://commons.wikimedia.org/wiki/File%3ADance.gif")
        for address in ("javascript:alert(1)", "data:x", "https://x.example/\n", "https://user@x.example/", "https://x.example:bad/"):
            self.assertIsNone(safe_link(address))
        self.assertEqual(plain_text("<b>" + "a" * 400 + "</b>"), "a" * 300)
        self.assertEqual(plain_text("a" * 8193), "")

    def test_download_uses_exact_original_including_query_and_validates_identity(self):
        original = gif([{"pixels": [1, 2]}, {"pixels": [2, 1]}])
        repository = self.repository([page(original)], original)
        candidate = repository.search("dance")[0]
        downloaded = repository.download(candidate)
        self.assertEqual(downloaded, original)
        self.assertEqual(hashlib.sha256(downloaded).digest(), hashlib.sha256(original).digest())
        self.assertEqual(self.fetched[1], (ORIGINAL_URL, DEFAULTS.source_bytes, "image/gif"))

    def test_invalid_changed_or_oversize_original_is_rejected(self):
        original = gif([{"pixels": [1, 2]}, {"pixels": [2, 1]}])
        for downloaded in (b"not a GIF", original + b"x", gif([{"pixels": [1, 2]}]),
                           b"x" * (DEFAULTS.source_bytes + 1)):
            with self.subTest(length=len(downloaded)):
                repository = self.repository([page(original)], downloaded)
                candidate = repository.search("dance")[0]
                with self.assertRaises(RepositoryError):
                    repository.download(candidate)

    def test_download_defends_against_forged_candidate_address(self):
        candidate = Candidate("Forged", "https://localhost/secret", PREVIEW_URL,
                              "https://commons.wikimedia.org/", "Unknown", None, "Unknown", 1, 2, 1, 2, None)
        fetch = Mock()
        with self.assertRaises(RepositoryError):
            CommonsRepository(fetch).download(candidate)
        fetch.assert_not_called()

    def test_response_limits_and_errors_do_not_expose_repository_data(self):
        payloads = [b"broken", b"[]", b'{"query":[]}', b'{"error":{"info":"private URL secret"}}',
                    b"[" * 2000 + b"]" * 2000,
                    json.dumps({"query": {"pages": [page()] * 25}}).encode(), b"x" * (API_BYTES + 1)]
        for payload in payloads:
            with self.subTest(length=len(payload)), self.assertRaises(RepositoryError) as error:
                CommonsRepository(lambda *_: payload).search("cat")
            self.assertNotIn("secret", str(error.exception))
        def failed(*_):
            raise OSError("secret key and private URL")
        with self.assertRaises(RepositoryError) as error:
            CommonsRepository(failed).search("cat")
        self.assertNotIn("secret", str(error.exception))


class NetworkTests(unittest.TestCase):
    def connection(self, *, status=200, content_type="image/gif", body=b"GIF", length=None, encoding=None):
        response = Mock()
        response.status = status
        headers = {"Content-Type": content_type}
        if length is not None:
            headers["Content-Length"] = length
        if encoding is not None:
            headers["Content-Encoding"] = encoding
        response.getheader.side_effect = lambda name, default=None: headers.get(name, default)
        chunks = [body, b""]
        response.read1.side_effect = lambda _: chunks.pop(0)
        connection = Mock()
        connection.getresponse.return_value = response
        return connection

    def test_no_redirects_are_followed(self):
        for status in (301, 302, 303, 307, 308):
            connection = self.connection(status=status)
            with patch("gif_host.repository.http.client.HTTPSConnection", return_value=connection), self.assertRaises(RepositoryError):
                _network_bytes(ORIGINAL_URL, 100, "image/gif")
            connection.request.assert_called_once()
            connection.close.assert_called_once()

    def test_headers_body_and_deadline_are_bounded(self):
        cases = [dict(length="101"), dict(length="secret"), dict(length="4"),
                 dict(body=b"x" * 101), dict(encoding="gzip"), dict(content_type="text/html")]
        for arguments in cases:
            connection = self.connection(**arguments)
            with self.subTest(arguments=arguments), patch("gif_host.repository.http.client.HTTPSConnection", return_value=connection), self.assertRaises(RepositoryError):
                _network_bytes(ORIGINAL_URL, 100, "image/gif")
        connection = self.connection()
        with patch("gif_host.repository.http.client.HTTPSConnection", return_value=connection), patch("gif_host.repository.time.monotonic", side_effect=[0, 6]), self.assertRaises(RepositoryError):
            _network_bytes(ORIGINAL_URL, 100, "image/gif")
        connection.request.assert_not_called()

    def test_exact_bytes_and_query_are_preserved_without_decoding(self):
        connection = self.connection(length="3")
        with patch("gif_host.repository.http.client.HTTPSConnection", return_value=connection):
            self.assertEqual(_network_bytes(ORIGINAL_URL, 100, "image/gif"), b"GIF")
        self.assertEqual(connection.request.call_args.args[:2],
                         ("GET", "/wikipedia/commons/a/ab/Dance.gif?download=1"))
        self.assertTrue(connection.sock.settimeout.called)

    def test_completed_http_response_can_close_transport_after_last_chunk(self):
        class ClosingStream(io.BytesIO):
            def close(self):
                transport.closed = True
                super().close()

        class Transport:
            closed = False

            def makefile(self, _mode):
                return ClosingStream(b"HTTP/1.1 200 OK\r\nContent-Type: image/gif\r\n"
                                     b"Content-Length: 3\r\nConnection: close\r\n\r\nGIF")

            def settimeout(self, _seconds):
                if self.closed:
                    raise OSError("transport is already closed")

        transport = Transport()
        response = http.client.HTTPResponse(transport)
        response.begin()
        connection = Mock()
        connection.sock = transport
        connection.getresponse.return_value = response
        with patch("gif_host.repository.http.client.HTTPSConnection", return_value=connection):
            self.assertEqual(_network_bytes(ORIGINAL_URL, 100, "image/gif"), b"GIF")
        self.assertTrue(response.isclosed())
        self.assertTrue(transport.closed)
