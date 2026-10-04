# Claude Code GIF Chat plugin and mod

The [gif-chat](https://github.com/Clinscott/gif-chat) plugin supplies the bounded GIF MCP tools, a focused skill, and a supported Claude Code mod. A **GIF** button above the chat prompt opens an original-path pane. Enter a GIF path relative to your configured source directory, then press Enter or **Inspect GIF** to queue one inspection request in the current conversation. **Cancel** or Esc closes the pane without submitting. Opening it or typing a path submits nothing, and the mod leaves the conversation's prompt draft alone.

Claude Code mods require version **2.1.287 or newer**. The button and pane are supported in the terminal and Claude Desktop's Code tab. The VS Code chat panel and noninteractive/SDK sessions do not draw mod UI; use `/gif <relative-path.gif>` there. `/gif` without a path also opens the pane on supported surfaces. The pane accepts a path; it does not claim a native file-dialog or native attachment API. You can use the shared local GIF picker to select an original and paste its returned relative path.

The button and command defer one `$.prompt.submit` until the initiating callback returns. They do not decode the original in the mod, invoke a separate model, monitor prompts, or send media to another chat.

The plugin manifest requires three options: the absolute Python executable, the runtime enrollment lock created by `tools/configure_runtime.py`, and an absolute, user-owned source directory with mode 0700 and no extended ACL. The MCP configuration passes those values to `bin/gif-communication-host`. That shared launcher owns one private input root per MCP process. Local runtime enrollment does not establish the original pinned runtime or native host qualification. The optional local reply library is disabled by default. The source directory must contain only originals authorized for that session; `local_file.path` is relative to it. The `host_asset` variant still returns `native_asset_unavailable` until an authorized native attachment resolver exists.

This directory is a source template. Stage the complete plugin with `python3 tools/build_plugins.py`; the resulting package root includes the shared launcher and runtime. Its `.mcp.json` uses `${CLAUDE_PLUGIN_ROOT}` to locate the launcher, so it does not depend on Claude Code's working directory or on a copied repository location. The launcher receives `GIF_SOURCE_ROOT`, `GIF_PYTHON`, and `GIF_RUNTIME_LOCK` from the required plugin options and does not download dependencies. For a session-only load, use `claude --plugin-dir <staged-plugin-directory>`.

Offline source and mod checks:

```sh
claude plugin validate --strict integrations/claude-code
python3 integrations/claude-code/tests/run_offline.py
```

The offline runner validates the original manifest, then runs `claude plugin test` against a disposable copy with placeholder configuration. The tests exercise the command, both supported UI element trees, explicit submission, cancellation, unsafe paths, and submission failure with mocked APIs. Claude Code's test runner requires values for the manifest's three required options before any test can run. These checks do not install, activate, sign in, or run a model. They establish source behavior and element validity, while actual painting, native attachment intake, and host image rendering require a real session observation.

References: [Claude plugin manifest](https://code.claude.com/docs/en/plugins-reference), [plugin MCP servers](https://code.claude.com/docs/en/mcp#plugin-provided-mcp-servers), [mod interface and supported controls](https://code.claude.com/docs/en/plugins/mods/interface), [mod surfaces and version requirements](https://code.claude.com/docs/en/plugins/mods/overview), and [mod tests](https://code.claude.com/docs/en/plugins/mods/test).
