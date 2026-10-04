"""Optional MCP Apps presentation; the browser picker also works without a widget."""
from pathlib import Path
from urllib.parse import urlsplit

from gif_communication.contracts import require


RESOURCE_URI = "ui://gif-chat/picker"
RESOURCE_MIME_TYPE = "text/html;profile=mcp-app"
HOST_SUPPORT = "Browser picker; optional MCP Apps button when the host supports it."
PICKER_TOOL = {
    "name": "open_gif_picker",
    "title": "Open GIF picker",
    "description": "Open the private local GIF picker. Choose an original GIF and copy its inspection request back to this conversation.",
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    "outputSchema": {
        "type": "object",
        "properties": {"url": {"type": "string"}, "host_support": {"type": "string"}},
        "required": ["url", "host_support"],
        "additionalProperties": False,
    },
    "_meta": {"ui": {"resourceUri": RESOURCE_URI}},
}


def resource_descriptor():
    return {"uri": RESOURCE_URI, "name": "GIF picker", "description": "Open the private local GIF picker.",
            "mimeType": RESOURCE_MIME_TYPE}


def resource():
    """Return a static template; session capability URLs arrive only as tool results."""
    return {"contents": [{
        "uri": RESOURCE_URI,
        "mimeType": RESOURCE_MIME_TYPE,
        "text": (Path(__file__).parent / "web" / "widget.html").read_text(encoding="utf-8"),
        "_meta": {"ui": {"prefersBorder": True,
                          "csp": {"connectDomains": [], "resourceDomains": [], "frameDomains": []}}},
    }]}


def picker_result(url):
    """Keep the live capability URL useful in text-only hosts without saving it."""
    try:
        parsed = urlsplit(url) if isinstance(url, str) else None
        valid = (parsed is not None and parsed.scheme == "http"
                 and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                 and parsed.port is not None and not parsed.username and not parsed.password
                 and not any(char.isspace() for char in url))
    except ValueError:
        valid = False
    require(valid, "invalid_picker_url", "The private picker must use a local HTTP URL.")
    return {
        "isError": False,
        "structuredContent": {"url": url, "host_support": HOST_SUPPORT},
        "content": [{"type": "text", "text": "Open the private GIF picker: " + url
                     + "\nChoose an original GIF and copy its inspection request, then return to this conversation and paste it. This link lasts only for this local session."}],
    }
