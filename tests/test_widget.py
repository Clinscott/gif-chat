"""MCP resource contract and synthetic browser bridge tests; no host installation."""
import json
import re
import shutil
import subprocess
import unittest

from gif_communication.contracts import GifError
from gif_host.ui import PICKER_TOOL, RESOURCE_MIME_TYPE, RESOURCE_URI, picker_result, resource, resource_descriptor


# Reserved test fixture, never a real session capability.
FIXTURE_URL = "http://127.0.0.1:43123/fixture-only-picker"


class WidgetTests(unittest.TestCase):
    def test_resource_and_tool_contract_without_session_data(self):
        descriptor = resource_descriptor()
        content, = resource()["contents"]
        self.assertEqual(descriptor["uri"], PICKER_TOOL["_meta"]["ui"]["resourceUri"])
        self.assertEqual(content["uri"], RESOURCE_URI)
        self.assertEqual(content["mimeType"], RESOURCE_MIME_TYPE)
        self.assertEqual(content["_meta"]["ui"]["csp"],
                         {"connectDomains": [], "resourceDomains": [], "frameDomains": []})
        self.assertNotIn(FIXTURE_URL, content["text"])
        self.assertNotRegex(content["text"], r'<(?:script|link|img)[^>]+(?:src|href)="https?://')
        self.assertNotIn("fetch(", content["text"])
        self.assertIn('type="button" disabled aria-label=', content["text"])
        self.assertIn('role="status" aria-live="polite"', content["text"])
        self.assertEqual(PICKER_TOOL["inputSchema"],
                         {"type": "object", "properties": {}, "additionalProperties": False})
        result = picker_result(FIXTURE_URL)
        self.assertEqual(result["structuredContent"]["url"], FIXTURE_URL)
        self.assertEqual(set(result["structuredContent"]), {"url", "host_support"})
        self.assertIn(FIXTURE_URL, result["content"][0]["text"])
        self.assertIn("return to this conversation", result["content"][0]["text"])
        self.assertEqual(picker_result("http://127.0.0.1:80/picker")["structuredContent"]["url"],
                         "http://127.0.0.1:80/picker")

    def test_result_rejects_nonlocal_or_malformed_links(self):
        for url in [None, "https://example.test/picker", "http://127.0.0.1/picker",
                    "http://user:password@127.0.0.1:1234/", "http://127.0.0.1:invalid/",
                    "http://127.0.0.1:1234/\nprivate"]:
            with self.subTest(url=url), self.assertRaises(GifError) as raised:
                picker_result(url)
            self.assertEqual(raised.exception.code, "invalid_picker_url")

    @unittest.skipUnless(shutil.which("node"), "Node is required for the synthetic bridge test")
    def test_bridge_button_fallback_and_teardown(self):
        script = re.search(r"<script>(.*?)</script>", resource()["contents"][0]["text"], re.S).group(1)
        harness = r'''
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
function app() {
  const messages = [], timers = new Map(), listeners = new Map(), opens = [], observers = [];
  let timerId = 0;
  function element(id) {
    return {disabled: id === "gif-button", hidden: id === "browser-link", textContent: "",
      handlers: {}, addEventListener(name, fn) {this.handlers[name] = fn;},
      removeAttribute(name) {delete this[name];},
      click() {if (id === "browser-link") opens.push(this.href); else return this.handlers.click();}};
  }
  const elements = Object.fromEntries(["gif-button", "browser-link", "status"].map(id => [id, element(id)]));
  const parent = {postMessage(value) {messages.push(value);}};
  const window = {parent, addEventListener(name, fn) {listeners.set(name, fn);},
    removeEventListener(name) {listeners.delete(name);}};
  const body = {getBoundingClientRect() {return {width:400, height:180};}};
  const context = {window, document: {body, getElementById(id) {return elements[id];}}, URL,
    ResizeObserver: class {constructor(callback) {this.callback=callback; observers.push(this);}
      observe() {} disconnect() {this.disconnected=true;}},
    setTimeout(fn) {const id=++timerId; timers.set(id, () => {timers.delete(id); fn();}); return id;},
    clearTimeout(id) {timers.delete(id);}};
  vm.runInNewContext(input.script, context);
  const deliver = (message, source=parent) => listeners.get("message")?.({data: message, source});
  const tick = () => new Promise(resolve => setImmediate(resolve));
  return {elements, messages, opens, timers, observers, deliver, tick,
    reply(id, result) {deliver({jsonrpc:"2.0", id, result});},
    tool(url=input.url) {deliver({jsonrpc:"2.0", method:"ui/notifications/tool-result",
      params:{structuredContent:{url, host_support:"fixture"}}});}};
}
(async () => {
  const standard = app();
  const initialize = standard.messages[0];
  assert.equal(initialize.method, "ui/initialize");
  assert.equal(initialize.params.protocolVersion, "2026-01-26");
  assert.equal(initialize.params.appCapabilities.availableDisplayModes[0], "inline");
  assert.equal(standard.elements["gif-button"].disabled, true);
  standard.reply(initialize.id, {protocolVersion:"2026-01-26", hostCapabilities:{openLinks:{}}});
  await standard.tick();
  assert.equal(standard.messages[1].method, "ui/notifications/initialized");
  assert.equal(standard.messages[2].method, "ui/notifications/size-changed");
  assert.equal(standard.messages[2].params.height, 180);
  standard.observers[0].callback();
  standard.observers[0].callback();
  assert.equal(standard.timers.size, 1); // Debounce repeated observer callbacks.
  for (const timer of [...standard.timers.values()]) timer();
  assert.equal(standard.messages.length, 3); // Unchanged dimensions do not notify again.
  standard.deliver({jsonrpc:"2.0", method:"ui/notifications/tool-result",
    params:{structuredContent:{url:input.url}}}, {});
  assert.equal(standard.elements["gif-button"].disabled, true); // Reject unrelated windows.
  standard.tool();
  assert.equal(standard.elements["browser-link"].href, input.url);
  const click = standard.elements["gif-button"].click();
  const open = standard.messages.at(-1);
  assert.equal(open.method, "ui/open-link");
  assert.equal(open.params.url, input.url);
  standard.reply(open.id, {});
  await click;
  assert.equal(standard.opens.length, 0); // Host bridge owns this open.
  assert.match(standard.elements.status.textContent, /Picker opened/);

  const fallback = app();
  fallback.reply(fallback.messages[0].id, {protocolVersion:"2026-01-26", hostCapabilities:{}});
  await fallback.tick();
  fallback.tool();
  await fallback.elements["gif-button"].click();
  assert.deepEqual(fallback.opens, [input.url]); // Actual href used without openLinks.
  assert.equal(fallback.messages.some(m => m.method === "ui/open-link"), false);
  fallback.tool("https://example.test/not-local");
  assert.equal(fallback.elements["gif-button"].disabled, true);
  assert.equal(fallback.elements["browser-link"].href, undefined);
  fallback.tool("http://127.0.0.1:80/picker");
  assert.equal(fallback.elements["gif-button"].disabled, false); // Default-port normalization agrees with Python.

  for (const malformed of [null, {}, {protocolVersion:"unsupported", hostCapabilities:{openLinks:{}}}]) {
    const mismatch = app();
    mismatch.reply(mismatch.messages[0].id, malformed);
    await mismatch.tick();
    assert.equal(mismatch.messages.some(m => m.method === "ui/notifications/initialized"), false);
    mismatch.tool();
    await mismatch.elements["gif-button"].click();
    assert.deepEqual(mismatch.opens, [input.url]); // Incompatible bridge keeps the href fallback.
  }

  const unsupported = app();
  unsupported.reply(unsupported.messages[0].id, {protocolVersion:"2026-01-26", hostCapabilities:{openLinks:{}}});
  await unsupported.tick();
  unsupported.tool();
  const unsupportedClick = unsupported.elements["gif-button"].click();
  unsupported.deliver({jsonrpc:"2.0", id:unsupported.messages.at(-1).id,
    error:{code:-32601, message:"Unsupported"}});
  await unsupportedClick;
  assert.match(unsupported.elements.status.textContent, /browser link/);
  assert.equal(unsupported.elements["browser-link"].hidden, false);
  await unsupported.elements["gif-button"].click();
  assert.deepEqual(unsupported.opens, [input.url]);

  const timeout = app();
  timeout.reply(timeout.messages[0].id, {protocolVersion:"2026-01-26", hostCapabilities:{openLinks:{}}});
  await timeout.tick();
  timeout.tool();
  const timedClick = timeout.elements["gif-button"].click();
  for (const timer of [...timeout.timers.values()]) timer();
  await timedClick;
  assert.match(timeout.elements.status.textContent, /browser link/);
  assert.equal(timeout.elements["gif-button"].disabled, false);

  standard.deliver({jsonrpc:"2.0", id:77, method:"ui/resource-teardown", params:{}});
  assert.equal(standard.elements["gif-button"].disabled, true);
  assert.equal(standard.elements["browser-link"].href, undefined);
  assert.equal(standard.messages.at(-1).id, 77);
  assert.equal(standard.observers[0].disconnected, true);
  assert.equal(standard.timers.size, 0);
  console.log("widget bridge checks passed");
})().catch(error => {console.error(error); process.exitCode = 1;});
'''
        result = subprocess.run([shutil.which("node"), "-e", harness],
                                input=json.dumps({"script": script, "url": FIXTURE_URL}),
                                text=True, capture_output=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "widget bridge checks passed")


if __name__ == "__main__":
    unittest.main()
