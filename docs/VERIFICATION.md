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

The source/package checks above made **zero model calls**. The subsequent
installation and model checks are recorded separately below. The browser check used an existing Chrome
executable with a temporary test profile; the bundled Playwright browser binaries
were absent. The committed picker screenshot contains no session URL or user media.

During development, strict Claude validation rejected nested helpers receiving
the mod API; supported top-level helpers fixed that error. Independent review
found package replacement could erase unrecorded empty directories/FIFOs; the
builder now rejects all unexpected entries and changed owned files. Canonical
temporary roots fixed three test setup errors caused by macOS's `/var` symlink.
The final source and package checks above passed after these repairs.

Native UI rendering, native attachment resolution, a hard 256 MiB peak-memory
ceiling, population success rate, and token/latency improvement from the new UI
require evidence beyond the source/package checks above.

## Installed-host follow-up, 2026-10-04

The operator requested installation, model evaluation and native UI checks after
publication. Both supported plugin managers installed and enabled **0.4.0** from
the public marketplace pinned to `v0.4.0`. The installed Codex and Claude packages
were byte-equal to their published ZIPs; the release assets were not replaced.
Codex added the GIF marketplace/plugin entries. Claude's marketplace and enablement
are local to this project; its required plugin options are stored in user settings.
Private media inboxes, runtime locks, account state and raw host receipts are not
published.

| Installed layer | Observed result |
| --- | --- |
| Codex CLI 0.157.0 | Installed plugin supplied `inspect_gif` in two fresh sessions; each completed one successful MCP call and a model answer |
| Claude Code 2.1.289 | Installed plugin enabled; strict validation passed; native `mcp list` connected to `plugin:gif-chat:gif-communication` in 0.897 seconds |
| Codex desktop UI | Computer-use access was rejected: `Computer Use is not allowed to use the app 'com.openai.codex' for safety reasons.` No desktop button or MCP Apps painting claim follows from the CLI checks |
| Claude native terminal UI | Actual installed mod painted `[ GIF ]`; keyboard activation opened the path panel while preserving an existing draft. `/gif`, invalid-path rejection, Escape and the Cancel button were observed in the native TUI |
| Claude model/Desktop | CLI reported `Not logged in` and `API Usage Billing`; no Claude model call was made. Desktop was signed in and actively in use; Desktop pixels and valid Inspect submission remain unverified |

The two Codex tasks used neutral copies of the versioned public fixtures and
withheld the oracle. The retained trace contains no non-GIF tool calls. Each tool
result included the exact original SHA-256, ordered PNG blocks and a three-frame
timeline. Case 1 has two unique PNGs because its first and last frames repeat.
An independent review graded the requested direction and temporal order against
the frozen oracle.

| Case | Answer | Result | Whole CLI time | Input tokens | Cached input, included in input | Output tokens | Reported reasoning tokens |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Middle gesture, `asset-01.gif` | Upward, then returns downward | Pass | 20.675 s | 36,079 | 17,280 | 256 | 0 |
| Color order, `asset-02.gif` | Blue → green → red | Pass | 17.696 s | 46,448 | 39,424 | 220 | 0 |

Source identities: `asset-01.gif` is 1,195 bytes, SHA-256
`b4cd7e561f6d0eaa9ca91df663791866d18a59f0f6ba2119f97471b9cd0c9fcb`;
`asset-02.gif` is 943 bytes, SHA-256
`6650fc094ed866c44454f2c8c05302448a5b65496bf1f2ff1a0979f1fd3e72d6`.
Both model runs exited 0 with complete output, reaped processes and observed
absence of their owned process groups. The reasoning field was explicitly zero
in both usage records. The CLI default model was requested; its backend name was
not exposed in the retained events and remains unknown.

Two local configuration failures and one rejected model-alias request preceded
these completed turns. They produced no GIF tool calls or answers and are retained
separately from the successful cases. The test launch was corrected without
overwriting unrelated host settings.

The Claude terminal check accepted trust only for this reviewed GIF Chat project.
The pane rendered its Original GIF input, Inspect GIF button and Cancel button.
Submitting `../../clip.gif` showed the path-validation message without an
inspection request. Escape closed the pane. With `draft-preservation-check` in
the main prompt, keyboard activation of the GIF button opened the pane and the
Cancel button closed it; the draft remained visible. The session exited 0 and no
MCP process matching its exact private inbox remained. These are actual native
terminal rendering observations, not the earlier mocked UI tests or Desktop
screenshots. Two earlier custom-PTY attempts stopped at the trust screen and are
retained separately. A valid Inspect action was withheld because the CLI lacked
subscription authentication and displayed API billing; no paid fallback ran.

**Limits:** two synthetic tasks establish this installed Codex path's smoke-test
behavior, not population accuracy, a token saving, a latency improvement or Claude
model understanding. Terminal UI success does not establish Desktop rendering or
an authenticated Claude model turn. Token counts cover the entire host context and are not the
incremental cost of a GIF. Cached tokens are already included in input; reasoning
tokens are part of output. Times include CLI startup, tool execution, model work
and shutdown. No dollar bill or allowance reduction is inferred from these counts.
The CLI trace establishes returned image blocks and subsequent answers; it is not
a capture of the provider's internal request payload or native desktop painting.

## Reproduce

For installed Codex evaluation, first install the pinned marketplace/plugin using
the README commands. Set `GIF_PYTHON`, `GIF_RUNTIME_LOCK`, `GIF_LIBRARY_ENABLED=0`
and a unique 0700 `GIF_SOURCE_ROOT` for each case. Copy only its fixture there as
`clip-01.gif` or `clip-02.gif`, mode 0600. Use a separate empty `CASE_WORKSPACE`.
The tested invocation was:

```sh
env -u OPENAI_API_KEY -u CODEX_API_KEY -u OPENAI_BASE_URL \
  -u OPENAI_ORG_ID -u OPENAI_PROJECT_ID -u AZURE_OPENAI_API_KEY \
  codex exec --ignore-user-config --json --ephemeral --color never \
  --sandbox read-only --skip-git-repo-check --cd "$CASE_WORKSPACE" \
  -c 'marketplaces.gif-chat.source_type="git"' \
  -c 'marketplaces.gif-chat.source="https://github.com/Clinscott/gif-chat.git"' \
  -c 'marketplaces.gif-chat.ref="v0.4.0"' \
  -c 'project_doc_max_bytes=0' \
  -c 'plugins={"gif-chat@gif-chat"={enabled=true}}' \
  -c 'features.multi_agent=false' -c 'features.multi_agent_v2=false' \
  -c 'features.memories=false' -c 'features.chronicle=false' \
  -c 'web_search="disabled"' -
```

Each stdin prompt requested `inspect_gif` for the neutral local path, then asked
either "Which direction does the brief gesture in the middle move?" or "What is
the temporal color sequence?" It required frame order/timestamps, sampling limits
and uncertainty; allowed at most one follow-up; forbade file/oracle access, shell,
browsing, delegation, edits, picker calls and fallback. The local wrapper retained
JSONL and stderr, imposed a 150-second timeout per invocation and reaped its owned
process group. No API-key fallback or quota reset was used. Running these commands
requires a signed-in account and consumes its model allowance; the source tests
below do not run them.

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
local receipts.

The first hosted run stopped before tests because actions/setup-python did not provide Python 3.12.14 for macOS. The corrected workflow provisions the pinned version through uv; the successful run above is retained separately from that initial failure. No runtime version or decoder contract was relaxed.
