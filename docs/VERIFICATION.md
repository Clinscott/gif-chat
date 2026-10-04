# GIF Chat 0.4.0 release verification

Local release checks completed on 2026-10-04. Tested macOS runtime: Python
3.12.14, Pillow 12.3.0; selected runtime explicitly enrolled into an ignored
local fingerprint lock. CLI inspection: Codex 0.157.0 and Claude Code 2.1.289.

| Layer | Observed result | What it establishes |
| --- | --- | --- |
| Source suite | 82 tests passed, 4.321 seconds | Decoder, schemas, protocol, isolation, runtime enrollment, picker, widget and package ownership guards |
| Claude strict validation | Source template and complete staged plugin passed | Host-recognized manifest and mod API usage |
| Claude offline mod suite | 8 passed, 0 failed | Supported terminal/Desktop UI trees, GIF button, path panel, command, cancel, validation and explicit deferred submission through mocked APIs |
| Two complete packages | 9 actual stdio MCP requests per package passed | Initialization, tool discovery, original inspection, follow-up, traversal rejection, UI resources and local picker opening |
| Packaged image delivery | 2 ordered PNG image blocks per fixture; all hashes matched | Actual MCP image bytes match the decoder manifest and original SHA-256 |
| Picker-to-package intake | Uploaded original was byte-exact and then inspected successfully | Explicit browser selection can enter the approved inbox for either adapter |
| Owned shutdown | Both stdio processes exited 0; picker ports closed | Package-owned picker lifetime ends with its MCP process |
| Browser integration | Real file chooser, request preparation and opt-in playback passed; 390 px viewport had no overflow or page errors | Actual local browser picker behavior, independent of native host UI |
| Hosted macOS CI | [Passed on source commit 948682a](https://github.com/Clinscott/gif-chat/actions/runs/37245403782) | Clean checkout, publicly provisioned pinned Python/Pillow, all source tests and both packaged MCP checks |
| Package and library inventories | Both plugin inventories and four original assets/posters verified | Shipped files have reproducible SHA-256 identities |

All release checks made **zero model calls**. No plugin was installed or activated,
and no host settings were changed. The browser check used an existing Chrome
executable with a temporary test profile; the bundled Playwright browser binaries
were absent. The committed picker screenshot contains no session URL or user media.

During development, strict Claude validation rejected nested helpers receiving
the mod API; supported top-level helpers fixed that error. Independent review
found package replacement could erase unrecorded empty directories/FIFOs; the
builder now rejects all unexpected entries and changed owned files. Canonical
temporary roots fixed three test setup errors caused by macOS's `/var` symlink.
The final source and package checks above passed after these repairs.

**Not established:** actual native Claude/Codex plugin loading, native button
painting, Codex MCP Apps rendering, native attachment resolution, model-level
understanding in either installed host, a hard 256 MiB peak-memory ceiling,
population success rate, or token/latency improvement from the new UI.

## Reproduce

With the enrolled macOS runtime and development dependencies:

```sh
export GIF_RUNTIME_LOCK="$PWD/.local/runtime-lock.json"
.venv/bin/python tools/check.py
.venv/bin/python integrations/claude-code/tests/run_offline.py
.venv/bin/python tools/build_plugins.py --output plugins
.venv/bin/python tools/smoke_plugins.py
```

For optional browser checks, provision Playwright's browser or set
`GIF_BROWSER_EXECUTABLE` to an existing compatible Chrome executable:

```sh
npm install
npx playwright install chromium
.venv/bin/python tools/browser_check.py
```

The source suite's widget bridge test requires Node and reports a skip if absent.
The eight Claude mod tests require the compatible Claude CLI and make no model
calls. GitHub CI runs source/package checks; its result is separate from these
local receipts. The operator-shut-down experiment campaign remains stopped.

The first hosted run stopped before tests because actions/setup-python did not provide Python 3.12.14 for macOS. The corrected workflow provisions the pinned version through uv; the successful run above is retained separately from that initial failure. No runtime version or decoder contract was relaxed.
