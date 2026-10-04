# Codex GIF Chat plugin

This template becomes the self-contained `plugins/codex` package through
`python tools/build_plugins.py --output plugins`. The public repository marketplace
at `.agents/plugins/marketplace.json` makes it discoverable as `gif-chat`.

The inspected Codex CLI 0.157.0 supports this compatibility manifest and stdio
layout. Relative `cwd: "."` resolves at the plugin root. Supply trusted environment
values before loading: `GIF_PYTHON` (absolute pinned Python 3.12.14 with Pillow
12.3.0), `GIF_RUNTIME_LOCK` (absolute enrolled lock), `GIF_SOURCE_ROOT` (absolute
private 0700 user-owned inbox without an extended ACL), and optional
`GIF_LIBRARY_ENABLED=1` to enable four bundled original reaction GIFs.

The launcher downloads nothing and fails closed on missing configuration or a
runtime identity mismatch. Use a separate approved inbox and dedicated MCP process
per conversation; global enablement alone does not establish isolation.

Ask the agent to open the GIF picker, or give it an original's relative path.
`open_gif_picker` provides a private local browser link and optional MCP Apps GIF
button. Text-only hosts remain usable. Native Codex resource rendering is not
verified, and this package does not inject an arbitrary native composer action.
`inspect_gif` and `get_gif_frames` return ordered PNG evidence to the current
conversation. Native attachment IDs are unavailable.

Source/package tests and direct stdio delivery do not establish installed plugin
loading or actual native UI behavior. See the root README and release verification.

References: [Codex packaging and marketplaces](https://developers.openai.com/plugins/build/plugins),
[optional MCP UI](https://developers.openai.com/plugins/build/chatgpt-ui).
