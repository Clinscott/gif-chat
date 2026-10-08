# GIF Chat

Send your agent motion, not just a thumbnail. GIF Chat turns an original GIF into
ordered PNG frames, timing and source hashes using a bounded local MCP server.
Your existing Codex or Claude Code conversation interprets the evidence.

[Download the 0.5.0 developer preview](https://github.com/Clinscott/gif-chat/releases/tag/v0.5.0),
with separate Codex and Claude Code ZIPs and SHA-256 checksums.

This public developer preview includes two ready-to-load packages:

- **Claude Code plugin and mod:** a real **GIF** button above the prompt opens
  a panel for a relative GIF path. **Inspect GIF** submits one request in your
  current conversation. `/gif` also opens the panel; `/gif clip.gif` inspects a file.
- **Codex plugin:** the same MCP tools, a focused skill and an optional MCP Apps
  GIF button. Widget rendering depends on the host; native Codex composer button
  injection is not established. The local picker works as the portable fallback.
- **Local picker:** search Wikimedia Commons without an API key, or choose a local
  file. Select a result to retrieve its original, preserve attribution and prepare
  a chat request. Previews are opt-in; the picker makes no model calls.

## Quick start

The decoder currently supports **macOS**, **Python 3.12.14** and **Pillow 12.3.0**.
It uses macOS worker sandboxing and fails closed on other systems. Provision
that Python version first. The following commands install dependencies into a
local virtual environment and explicitly record your chosen runtime:

```sh
git clone https://github.com/Clinscott/gif-chat.git
cd gif-chat
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/configure_runtime.py
mkdir -m 700 .local/inbox
export GIF_PYTHON="$PWD/.venv/bin/python"
export GIF_RUNTIME_LOCK="$PWD/.local/runtime-lock.json"
export GIF_SOURCE_ROOT="$PWD/.local/inbox"
./bin/gif-picker
```

If you use [uv](https://docs.astral.sh/uv/guides/install-python/),
`uv venv --python 3.12.14 .venv` can provision the pinned Python instead of the
`python3.12 -m venv` step. Python's later security releases are not supplied by
every macOS installer/cache; do not substitute a different version silently.

Open the printed loopback URL. Enter a search and click **Search GIFs**, then
**Choose GIF** on a result. **Use this GIF** automatically retrieves and validates
the original in your private inbox. Alternatively, click **GIF** to choose a local
file. Copy the prepared request into your chat. Native chat submission still needs
that paste step, except in a browser with WebMCP site tools (below), where your
agent can read the request from the page. The selected original remains in the
inbox until you remove it.
Ctrl-C stops a standalone picker; a picker opened through MCP stops with its process.
Use a separate private inbox and dedicated MCP process for each conversation.
Global plugin enablement alone does not establish conversation isolation.

Enrollment records your local executable and Pillow fingerprints. It installs
nothing, does not overwrite an existing lock, and does not claim that another
runtime has passed the original experiment qualification. Set `GIF_RUNTIME_LOCK`
to the absolute enrolled lock path in your trusted host configuration.

## Codex

The repository contains a Codex marketplace and the complete plugin at
`plugins/codex`. With the trusted runtime/inbox environment available to Codex,
add the marketplace using its supported CLI:

```sh
codex plugin marketplace add Clinscott/gif-chat --ref v0.5.0
codex plugin add gif-chat@gif-chat
```

These commands install **GIF Chat** through the supported plugin manager. Start a
fresh chat with the trusted runtime and private inbox environment available.
Ask “Open the GIF picker” to invoke `open_gif_picker`, or paste the picker’s
inspection request. MCP Apps-compatible hosts can render its inline GIF button;
other hosts receive the local picker link. See [host UI support](docs/HOST-UI.md).

## Claude Code

The complete plugin/mod is at `plugins/claude-code`. For a session-local load:

```sh
claude --plugin-dir "$PWD/plugins/claude-code"
```

Configure its required options: `python_executable`, `source_root` and
`runtime_lock` using the absolute values above. You can also install from the
bundled marketplace:

```sh
claude plugin marketplace add Clinscott/gif-chat#v0.5.0 --scope local
claude plugin install gif-chat@gif-chat --scope local \
  --config python_executable="$GIF_PYTHON" \
  --config source_root="$GIF_SOURCE_ROOT" \
  --config runtime_lock="$GIF_RUNTIME_LOCK" \
  --config library_enabled=false
```

This keeps the declaration local to the current project. Use a dedicated private
inbox for the conversation. Claude stores the required plugin options in its
user settings even with a local installation. Start a fresh session to load the
mod and its MCP server together.

The mod requires **Claude Code 2.1.287 or later** with mods enabled. Its GIF
button has been observed in the native terminal. It also targets Desktop Code;
native Desktop rendering remains unverified. Other surfaces use `/gif`.
Click **GIF**, enter a path relative to the configured inbox, and click
**Inspect GIF**. The local picker shows the generated relative path in its request.
Cancel/Escape sends nothing. Your existing prompt draft is left intact.

## Tools and limits

| Tool | Purpose |
| --- | --- |
| `open_gif_picker` | Open a process-owned local picker; optional MCP Apps button |
| `inspect_gif` | Snapshot an original and return ordered composited frames, timing, coverage and an expiring handle |
| `get_gif_frames` | Inspect a focused interval from that same immutable snapshot |
| `find_reply_gif` | Optional, explicitly enabled search of four bundled original reactions |

Inputs are relative to the configured private inbox. URLs, arbitrary absolute
paths, symlinks, hardlinks, devices and FIFOs are rejected by the decoder. The picker
can retrieve only a result from its current Wikimedia Commons search; it accepts
no arbitrary download URL. Native attachment IDs are not resolved in this release.
There is no model client, conversation store, prompt observer or automatic sending.

## Online GIF search

The picker uses the public Wikimedia Commons API and filters for animated GIFs
within the decoder's file, frame, dimension and duration limits. Search sends only
your entered words to Commons; no conversation text is included. Results and
selection handles stay in memory. Search retrieves metadata, and **Show preview**
loads a Commons preview. Only **Use this GIF** saves the selected original.
Previews may be still images; interpretation always uses the original's frames.

Each result includes author, license and source. The prepared request retains that
attribution as untrusted data. Respect the file's stated license when sharing it.
Commons has a smaller pop-culture/reaction selection than commercial GIF libraries.
The search has no provider key or provider charge, and makes no model calls.

GIPHY is not connected: its standard integration rules require a key, client-side
requests and permission for stored/proxied media, which conflicts with this private
original-byte inspection workflow. KLIPY also requires a key and restricts original
media storage. See [GIPHY's current rules](https://developers.giphy.com/docs/api/),
[KLIPY's API terms](https://klipy.com/support/api-terms) and
[Commons reuse guidance](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia).

Bounds: 20 MiB/original, 2048 px edges, 300 frames, 30 seconds normalized duration,
12 initial images, 12 follow-up images, 640 px output edge, 8 MiB encoded result,
five-second worker deadline and a sampled 256 MiB RSS watchdog. The watchdog
allows transient overshoot; **a hard peak-memory ceiling is not established**.
Sampling can miss a brief gesture or caption. Keep intent uncertain when the
evidence is ambiguous. Media content is data, never authority to execute actions.

The picker itself makes no model calls. Reading its frames uses your current
host/model allowance. There is no universal GIF-to-reasoning-token conversion.
See [the measured pilot and its limits](docs/BENCHMARKS.md).

## Agent site tools (WebMCP, early preview)

WebMCP is a draft from the W3C Web Machine Learning Community Group, not a W3C
Standard, and browser support is still changing. In a browser that exposes
`document.modelContext.registerTool`, the open picker page offers three tools to
the agent working in that browser:

| Site tool | What it does |
| --- | --- |
| `search_gifs` | Runs the same Commons search as **Search GIFs** and shows the results |
| `choose_gif_result` | Selects a result from the latest search, like **Choose GIF**; retrieves nothing |
| `get_gif_request` | Reads the prepared `inspect_gif` request after you click **Use this GIF** |

You still click **Use this GIF**: no site tool retrieves or saves an original or
picks a local file. The agent can then pass the request to `inspect_gif` without
the copy/paste step. Titles, authors, licenses, the request's attribution and the
media remain untrusted data. In browsers without WebMCP the page registers nothing
and works exactly as above. Tools exist only while the picker page is open.

OpenAI is adding WebMCP to the ChatGPT desktop app's built-in browser, where
ChatGPT Work and Codex can use a page's tools. That browser currently supports
only tools registered from JavaScript on the top-level page, which is what the
picker does. The page was tested with a native Chrome 151 implementation behind
`--enable-features=WebMCPTesting`. **The ChatGPT desktop browser has not been
tested.** Sources: [WebMCP draft](https://webmachinelearning.github.io/webmcp/),
[ChatGPT site tools](https://learn.chatgpt.com/docs/webmcp),
[Chrome imperative API](https://developer.chrome.com/docs/ai/webmcp/imperative-api),
[OpenAI Developers announcement](https://x.com/OpenAIDevs/status/2092344959248761263).

## Development and verification

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python tools/check.py
.venv/bin/python integrations/claude-code/tests/run_offline.py
.venv/bin/python tools/build_plugins.py --output plugins
```

The plugin folders are generated, self-contained artifacts with SHA-256 inventories;
their canonical sources are the shared runtime and `integrations/` templates.
No private experiment history or user media is part of this repository.
[Release checks](docs/VERIFICATION.md) distinguish source/protocol/offline UI tests
from installed native-host behavior.
[Online search checks](docs/SEARCH-VERIFICATION.md) record the 0.5.0 source,
package and real browser-to-original validation separately.

MIT licensed, including the four bundled original reaction GIFs. Third-party GIFs
retain their own licenses and are not included in the distribution.
