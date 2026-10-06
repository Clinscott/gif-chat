# GIF Chat 0.5.0 search verification

Verified on macOS on 2026-10-06 with Python 3.12.14 and Pillow 12.3.0.
The shared picker now searches Wikimedia Commons, retrieves an explicitly selected
original and prepares a request with author, license and source attribution.

| Check | Observed result |
| --- | --- |
| Source suite | 110 tests passed in 8.561 seconds |
| Claude mod checks | 8 passed; existing draft preservation and single submission behavior retained |
| Complete Codex and Claude packages | 9 stdio MCP requests per package passed, including inspection, follow-up, local upload and owned shutdown |
| Real in-app browser search | `cat` returned 12 animated GIF candidates with licenses and authors |
| Real selection and staging | `Walking cat.gif` downloaded and produced the inspection request with attribution |
| Original-to-frame check | 32,940 original bytes, 5 frames and 5 ordered images; 0.058 seconds for local inspection |
| Separate model evaluation calls | None |

The selected public test original is
[Walking cat.gif](https://commons.wikimedia.org/wiki/File:Walking_cat.gif),
by Sheilagraber, licensed [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0).
Its SHA-256 is
`b611c348e2406f883c6e0de80313896d2ead67b3b67e65392131096911e2ecfc`.
The original and private process URLs are excluded from the repository and release.
The inspection timing covers local decoding of this one GIF, not search latency,
provider performance or model response time.

The first live download exposed a completed-response socket bug. The downloader
read the complete body, then tried to set a deadline on the closed transport.
A regression test using a real `HTTPResponse` reproduced the failure and passes
after the fix. A second candidate failed the existing structural GIF preflight
and wrote no inbox file; the decoder's acceptance rules were preserved.

Network requests use fixed Commons hosts, reject redirects and cap response sizes.
Search handles expire after ten minutes and are replaced by the next search.
The picker permits 40 searches and four saved originals per process. Search never
downloads an original or sends a model request. Previews load only when requested.
The five-second network budget includes connection/read checks; operating-system
DNS resolution is not a hard deadline guarantee.

The source checks cover unsafe URLs, redirects, bad media, metadata rendering,
expired/foreign handles, cross-origin access, stale UI results and exact byte
preservation. Reproduce them with `tools/check.py`, the Claude offline runner and
`tools/smoke_plugins.py`, using the documented pinned development dependencies.

This is observed browser-picker and local image transport behavior. It does not
establish native Codex composer injection, newly installed 0.5.0 plugins, animated
attachment resolution or a model-accuracy improvement. The user still copies the
prepared request into the chat. Installed 0.4.0 evidence remains in
[the previous release checks](VERIFICATION.md).
