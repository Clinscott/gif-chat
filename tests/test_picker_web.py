"""Deterministic browser-workflow checks against the picker JavaScript.

The small DOM below intentionally does not parse HTML. Repository metadata must
stay text, and asynchronous requests are controlled to exercise user changes
while earlier work is still pending. Native layout and browser behavior are
checked separately.
"""

from pathlib import Path
import shutil
import subprocess
import unittest


WEB = Path(__file__).resolve().parents[1] / "gif_host" / "web"

HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor(tag, id = '') {
    this.tagName = tag.toUpperCase(); this.id = id;
    this.children = []; this.attributes = {}; this.listeners = {};
    this.hidden = false; this.disabled = false; this.value = ''; this.files = [];
    this._text = ''; this.classes = new Set();
    this.classList = {
      add: (name) => this.classes.add(name),
      remove: (name) => this.classes.delete(name),
      contains: (name) => this.classes.has(name),
    };
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(x => x.textContent).join(''); }
  set innerHTML(value) { throw new Error('Untrusted content must not be parsed as HTML'); }
  set src(value) { this.attributes.src = String(value); }
  get src() { return this.attributes.src || ''; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  removeAttribute(name) { delete this.attributes[name]; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; this._text = ''; }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  fire(type) {
    return Promise.all((this.listeners[type] || []).map(callback =>
      callback({preventDefault() {}, target: this})));
  }
  click() { return this.fire('click'); }
  focus() { focused = this; }
  select() { this.wasSelected = true; }
}

let focused = null;
const elements = {};
const html = fs.readFileSync(process.argv[2] + '/picker.html', 'utf8');
for (const match of html.matchAll(/<([a-z]+)\b[^>]*\bid="([^"]+)"[^>]*>/g)) {
  const node = new Element(match[1], match[2]);
  node.hidden = /\bhidden\b/.test(match[0]);
  elements[node.id] = node;
}
const createdTags = [];
const document = {
  getElementById: id => { assert.ok(elements[id], 'Missing HTML element: ' + id); return elements[id]; },
  createElement: tag => { createdTags.push(tag); return new Element(tag); },
};
const window = new Element('window');
const requests = [], copied = [], revoked = [];
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
function fetch(url, options) {
  const pending = deferred();
  requests.push({url, options, pending});
  return pending.promise;
}
function reply(index, value, ok = true) {
  requests[index].pending.resolve({ok, async json() { return value; }});
}
const urlAPI = class extends URL {};
urlAPI.createObjectURL = file => 'blob:local/' + file.name;
urlAPI.revokeObjectURL = value => revoked.push(value);
const navigator = {clipboard: {async writeText(value) { copied.push(value); }}};
vm.runInNewContext(fs.readFileSync(process.argv[2] + '/picker.js', 'utf8'),
  {document, window, navigator, fetch, URL: urlAPI, TextDecoder}, {filename: 'picker.js'});

const el = id => elements[id];
const item = (id, overrides = {}) => ({
  id, title: 'Title ' + id, author: 'Author ' + id, license: 'CC BY-SA 4.0',
  bytes: 4096, source_url: 'https://commons.wikimedia.org/wiki/File:' + id + '.gif',
  preview_url: 'https://upload.wikimedia.org/wikipedia/commons/' + id + '.gif',
  ...overrides,
});
function search(query) { el('query').value = query; return el('search-form').fire('submit'); }
function card(index) { return el('search-results').children[index]; }
function choose(index) { return card(index).children.find(node => node.tagName === 'BUTTON').click(); }
async function load(items) {
  const completion = search('motion');
  reply(requests.length - 1, {results: items});
  await completion;
}
function file(name = 'original.gif', header = null) {
  const bytes = Buffer.from('GIF89a');
  return {name, size: 128,
    slice() { return {arrayBuffer: () => header ? header.promise :
      Promise.resolve(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength))}; },
  };
}
function finishHeader(pending) {
  const bytes = Buffer.from('GIF89a');
  pending.resolve(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
}
const ready = prompt => ({path: 'inbox/original.gif', sha256: 'f'.repeat(64), bytes: 128, prompt});

const scenarios = {
  async metadata_is_text_and_search_does_not_use_media() {
    const title = '<img src=x onerror="run()">';
    const author = '<script>run()</script>';
    const license = '<b>untrusted license</b>';
    await load([item('unsafe', {title, author, license,
      source_url: 'javascript:run()', preview_url: 'https://attacker.example/x.gif'}), item('safe')]);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].url, 'search');
    assert.deepEqual(JSON.parse(requests[0].options.body), {query: 'motion'});
    assert.equal(card(0).children[0].textContent, title);
    assert.ok(card(0).children[1].textContent.includes(author));
    assert.ok(card(0).children[1].textContent.includes(license));
    assert.equal(card(0).children.filter(node => node.tagName === 'A').length, 0);
    assert.equal(card(1).children.filter(node => node.tagName === 'A').length, 1);
    assert.ok(!createdTags.some(tag => ['script', 'img', 'iframe'].includes(tag)));
    assert.equal(el('preview').hidden, true);
    assert.equal(el('result').hidden, true);
    assert.equal(el('image').src, '');
    await choose(0);
    await el('motion').click();
    assert.equal(el('image').src, '');
    assert.equal(requests.length, 1);
  },

  async explicit_use_sends_candidate_id_and_copies_exact_server_prompt() {
    const candidate = item('opaque-candidate-id');
    await load([candidate]);
    await choose(0);
    assert.equal(requests.length, 1, 'Choosing must not retrieve or stage an original');
    assert.equal(el('image').src, '', 'Motion starts only when the person requests a preview');
    await el('motion').click();
    assert.equal(el('image').src, candidate.preview_url);
    const completion = el('stage').click();
    assert.equal(requests[1].url, 'select');
    assert.equal(requests[1].options.method, 'POST');
    assert.equal(requests[1].options.headers['Content-Type'], 'application/json');
    assert.deepEqual(JSON.parse(requests[1].options.body), {id: candidate.id});
    const prompt = 'Inspect exactly:\n{"path":"inbox/escaped \\"name\\".gif"}\n<untrusted caption>';
    reply(1, ready(prompt));
    await completion;
    assert.equal(el('prompt').value, prompt);
    assert.equal(el('result').hidden, false);
    assert.ok(el('attribution').textContent.includes(candidate.title));
    await el('copy').click();
    assert.deepEqual(copied, [prompt]);
    assert.equal(requests.length, 2, 'Copy must not call an API or model');
  },

  async newer_search_wins_when_earlier_request_finishes_last() {
    const old = search('old query');
    const current = search('new query');
    reply(1, {results: [item('new')]});
    await current;
    assert.equal(card(0).children[0].textContent, 'Title new');
    const status = el('search-status').textContent;
    reply(0, {results: [item('old')]});
    await old;
    assert.equal(card(0).children[0].textContent, 'Title new');
    assert.equal(el('search-status').textContent, status);
    assert.equal(el('search').disabled, false);
  },

  async retrieval_for_previous_selection_cannot_publish_a_request() {
    await load([item('first'), item('second')]);
    await choose(0);
    const previous = el('stage').click();
    await choose(1);
    const currentStatus = el('status').textContent;
    reply(1, ready('Wrong old request'));
    await previous;
    assert.equal(el('result').hidden, true);
    assert.equal(el('prompt').value, '');
    assert.equal(el('status').textContent, currentStatus);
    const current = el('stage').click();
    assert.deepEqual(JSON.parse(requests[2].options.body), {id: 'second'});
    reply(2, ready('Correct new request'));
    await current;
    assert.equal(el('prompt').value, 'Correct new request');
  },

  async search_invalidates_a_pending_local_file_selection() {
    const header = deferred();
    el('file').files = [file('previous.gif', header)];
    const previous = el('file').fire('change');
    const current = search('new choice');
    finishHeader(header);
    await previous;
    assert.equal(el('preview').hidden, true, 'A cleared selection must not return after its old file read');
    reply(0, {results: [item('new')]});
    await current;
    await el('stage').click();
    assert.equal(requests.length, 1, 'An old local file must not become usable after a search');
  },

  async repository_choice_invalidates_a_pending_local_file_selection() {
    await load([item('repository')]);
    const header = deferred();
    el('file').files = [file('previous.gif', header)];
    const previous = el('file').fire('change');
    await choose(0);
    finishHeader(header);
    await previous;
    assert.equal(el('filename').textContent, 'Title repository · CC BY-SA 4.0');
    const completion = el('stage').click();
    assert.equal(requests[1].url, 'select');
    reply(1, ready('Repository request'));
    await completion;
  },

  async local_upload_keeps_original_object_and_server_request() {
    const original = file();
    el('file').files = [original];
    await el('file').fire('change');
    assert.equal(el('preview').hidden, false);
    assert.equal(requests.length, 0);
    await el('motion').click();
    assert.equal(el('image').src, 'blob:local/original.gif');
    const completion = el('stage').click();
    assert.equal(requests[0].url, 'stage');
    assert.equal(requests[0].options.headers['Content-Type'], 'image/gif');
    assert.equal(requests[0].options.body, original);
    reply(0, ready('Exact local request\nwith its server path'));
    await completion;
    assert.equal(el('attribution').hidden, true);
    await el('copy').click();
    assert.deepEqual(copied, ['Exact local request\nwith its server path']);
    await window.fire('pagehide');
    assert.deepEqual(revoked, ['blob:local/original.gif']);
  },
};

(async () => {
  assert.ok(scenarios[process.argv[3]], 'Unknown workflow');
  await scenarios[process.argv[3]]();
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


class PickerWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("Node is required for deterministic picker UI checks")

    def check_workflow(self, scenario):
        result = subprocess.run(
            [self.node, "-e", HARNESS, "picker-web-test", str(WEB), scenario],
            text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_metadata_is_text_and_search_does_not_use_media(self):
        self.check_workflow("metadata_is_text_and_search_does_not_use_media")

    def test_explicit_use_sends_candidate_id_and_copies_exact_server_prompt(self):
        self.check_workflow("explicit_use_sends_candidate_id_and_copies_exact_server_prompt")

    def test_newer_search_wins_when_earlier_request_finishes_last(self):
        self.check_workflow("newer_search_wins_when_earlier_request_finishes_last")

    def test_retrieval_for_previous_selection_cannot_publish_a_request(self):
        self.check_workflow("retrieval_for_previous_selection_cannot_publish_a_request")

    def test_search_invalidates_a_pending_local_file_selection(self):
        self.check_workflow("search_invalidates_a_pending_local_file_selection")

    def test_repository_choice_invalidates_a_pending_local_file_selection(self):
        self.check_workflow("repository_choice_invalidates_a_pending_local_file_selection")

    def test_local_upload_keeps_original_object_and_server_request(self):
        self.check_workflow("local_upload_keeps_original_object_and_server_request")
