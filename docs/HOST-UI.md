# GIF picker and host UI

The supported entry point is the `open_gif_picker` MCP tool. It returns a private loopback URL that opens a real browser picker. This route is usable from Codex and Claude Code even when the host does not render a widget. Keep the local adapter process running while using the picker. Choose a GIF, copy the resulting inspection request, and paste it into the same conversation.

The optional MCP Apps resource adds a **GIF** button in compatible hosts. The tool descriptor points `_meta.ui.resourceUri` to `ui://gif-chat/picker`; `resources/read` serves a self-contained `text/html;profile=mcp-app` document. OpenAI documents this as an optional UI layer and requires tools to remain useful without it. Its UI documentation explicitly describes iframe rendering in ChatGPT; it does not establish rendering in every Codex or Claude Code surface. [OpenAI UI documentation](https://developers.openai.com/plugins/build/chatgpt-ui)

The widget initializes the standard JSON-RPC bridge with `ui/initialize`, declares inline display support, checks the negotiated version, and confirms readiness with `ui/notifications/initialized`. It reports size changes for flexible containers and receives the live URL through `ui/notifications/tool-result`. It uses `ui/open-link` only when the host advertises `hostCapabilities.openLinks`. A normal browser link remains available if the bridge capability is absent, unsupported, or fails. The host can still restrict navigation. [MCP Apps specification](https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx)

The resource contains no session URL, external scripts, images, fonts, or network requests. Its CSP declares empty connection, resource, and frame allowlists. File selection and upload happen in the separate loopback picker, so the iframe does not need local-fetch permissions or host-specific file APIs. The capability URL belongs to the active private session: do not copy it into issues, screenshots, committed examples, or published logs. The widget keeps it in memory and clears it on teardown.

## Codex capability boundary

Local inspection on 2026-10-04 reported `codex-cli 0.157.0`. The installed CLI exposes plugin and MCP management commands; its help did not expose an API for injecting arbitrary native composer buttons. CLI version and help inspection alone do not prove desktop widget rendering.

OpenAI's plugin architecture supports MCP tools and shared plugin packaging across ChatGPT and Codex, with surface-specific capabilities. The documented composer and sidebar UI extensions are ChatGPT features. This package therefore offers the browser picker and an optional standard MCP Apps button; it does not claim a new native Codex composer action. [Plugin architecture](https://developers.openai.com/plugins/concepts/plugins), [OpenAI UI extensions](https://developers.openai.com/plugins/build/extensions)

## Verification

Run `python -m unittest tests.test_widget`. The tests check the resource/tool contract and execute the widget JavaScript against a synthetic host bridge, including link opening, capability/version fallback, size reporting, invalid-link rejection, timeout, and teardown. Node is needed for the JavaScript test; that test reports a skip if Node is absent. These checks establish the portable component's behavior. Actual rendering in an installed host requires a separate host acceptance check.
