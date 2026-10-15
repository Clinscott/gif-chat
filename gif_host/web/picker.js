"use strict";
const el = (id) => document.getElementById(id);
let selected = null, objectUrl = null, playing = false, searchEpoch = 0, fileEpoch = 0;
const safeLink = (value, hosts) => {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password &&
      !url.port && hosts.includes(url.hostname) ? url.href : null;
  } catch { return null; }
};
// Presentation only: a status line's words plus an optional tone for its mark.
const say = (id, text, tone) => {
  el(id).textContent = text;
  if (tone) el(id).setAttribute("data-tone", tone); else el(id).removeAttribute("data-tone");
};
const sourceLink = (href) => {
  const link = document.createElement("a"); link.href = href;
  link.target = "_blank"; link.rel = "noopener noreferrer";
  link.className = "source"; link.textContent = "Commons page";
  return link;
};
// Presentation only: one cell per frame (up to 24) so motion length reads at a glance.
const frameStrip = (item) => {
  if (!Number.isInteger(item.frames) || item.frames < 1) return null;
  const strip = document.createElement("p"); strip.className = "frames";
  const cells = document.createElement("span"); cells.className = "cells";
  cells.setAttribute("aria-hidden", "true");
  if (item.frames > 24) cells.classList.add("more");
  for (let index = 0; index < Math.min(item.frames, 24); index += 1) cells.append(document.createElement("i"));
  const label = document.createElement("span"); label.className = "frames-label";
  label.textContent = item.frames + (item.frames === 1 ? " frame" : " frames") +
    (Number.isFinite(item.duration_ms) && item.duration_ms > 0 ?
      " · " + (item.duration_ms / 1000).toFixed(1) + " s" : "");
  strip.append(cells, label);
  return strip;
};
function clearSelection() {
  selected = null;
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = null;
  el("image").removeAttribute("src"); playing = false;
  el("motion").textContent = "Play";
  el("preview").hidden = true;
  el("result").hidden = true;
  for (const card of el("search-results").children) card.classList.remove("selected");
}
function chooseRepository(item, card) {
  fileEpoch += 1;
  clearSelection();
  selected = {kind: "repository", item};
  el("motion").textContent = "Load preview";
  card.classList.add("selected");
  el("filename").textContent = item.title + " · " + item.license;
  el("preview").hidden = false;
  say("status", "Picked. Prepare for chat fetches the full original from Wikimedia Commons.");
  el("stage").focus();
}
el("search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = el("query").value.trim();
  if (!query) return;
  const epoch = ++searchEpoch;
  fileEpoch += 1;
  clearSelection();
  el("search-results").replaceChildren();
  el("search").disabled = true;
  say("search-status", "Looking on Wikimedia Commons…", "busy");
  try {
    const response = await fetch("search", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({query})});
    const value = await response.json();
    if (epoch !== searchEpoch) return;
    if (!response.ok) throw new Error(value.error || "Search isn’t working right now. Try again, or use a file.");
    for (const item of value.results) {
      const card = document.createElement("div"); card.className = "gif-card";
      const title = document.createElement("h3"); title.textContent = item.title;
      const info = document.createElement("p"); info.className = "meta";
      info.textContent = item.license + (item.author ? " · " + item.author : "") +
        " · " + Math.ceil(item.bytes / 1024) + " KiB";
      const choose = document.createElement("button"); choose.type = "button";
      choose.className = "pick-button";
      choose.textContent = "Pick"; choose.setAttribute("aria-label", "Pick " + item.title);
      choose.addEventListener("click", () => chooseRepository(item, card));
      card.append(title, info, choose);
      const source = safeLink(item.source_url, ["commons.wikimedia.org"]);
      if (source) card.append(sourceLink(source));
      const strip = frameStrip(item);
      if (strip) card.append(strip);
      el("search-results").append(card);
    }
    say("search-status", value.results.length ?
      value.results.length + " found. Pick one to preview or use it." :
      "Nothing usable for that search. Try other words, or use a file.", value.results.length ? "" : "empty");
  } catch (error) {
    if (epoch === searchEpoch) say("search-status", error.message, "error");
  } finally { if (epoch === searchEpoch) el("search").disabled = false; }
});
el("choose").addEventListener("click", () => el("file").click());
el("file").addEventListener("change", async () => {
  const epoch = ++fileEpoch;
  clearSelection();
  const file = el("file").files[0];
  if (!file || file.size === 0 || file.size > 20 * 1024 * 1024) {
    say("status", "Pick a GIF file up to 20 MiB.", "error"); return;
  }
  const header = new TextDecoder().decode(await file.slice(0, 6).arrayBuffer());
  if (epoch !== fileEpoch) return;
  if (!["GIF87a", "GIF89a"].includes(header)) {
    say("status", "That file isn’t a GIF.", "error"); return;
  }
  selected = {kind: "local", file};
  objectUrl = URL.createObjectURL(file);
  el("filename").textContent = file.name;
  el("preview").hidden = false;
  say("status", "Picked. Prepare for chat keeps an exact copy in your private inbox.");
});
el("motion").addEventListener("click", () => {
  if (!selected) return;
  playing = !playing;
  const preview = selected.kind === "local" ? objectUrl :
    safeLink(selected.item.preview_url, ["upload.wikimedia.org", "thumb.wikimedia.org"]);
  if (playing && preview) el("image").src = preview;
  else { el("image").removeAttribute("src"); playing = false; }
  el("motion").textContent = selected.kind === "local" ?
    (playing ? "Stop" : "Play") : (playing ? "Hide preview" : "Load preview");
});
el("stage").addEventListener("click", async () => {
  if (!selected || el("stage").disabled) return;
  const selection = selected;
  el("stage").disabled = true;
  say("status", selection.kind === "repository" ? "Fetching the original from Wikimedia Commons…" :
    "Saving an exact copy…", "busy");
  try {
    const remote = selection.kind === "repository";
    const response = await fetch(remote ? "select" : "stage", {method:"POST",
      headers:{"Content-Type": remote ? "application/json" : "image/gif"},
      body: remote ? JSON.stringify({id: selection.item.id}) : selection.file});
    const value = await response.json();
    if (selection !== selected) return;
    if (!response.ok) throw new Error(value.error || "That GIF couldn’t be prepared. Try another.");
    el("prompt").value = value.prompt;
    el("digest").textContent = "SHA-256 " + value.sha256 + " · " + value.bytes + " bytes";
    el("attribution").hidden = !remote;
    if (remote) {
      const item = selection.item;
      el("attribution").textContent = "Wikimedia Commons · " + item.title + " · " + item.license +
        (item.author ? " · " + item.author : "");
      const source = safeLink(item.source_url, ["commons.wikimedia.org"]);
      if (source) el("attribution").append(document.createElement("br"), sourceLink(source));
    }
    el("result").hidden = false;
    el("copy-status").textContent = "";
    say("status", "Ready. Copy the request below into your chat.", "ok");
    el("copy").focus();
  } catch(error) { if (selection === selected) say("status", error.message, "error"); }
  finally { el("stage").disabled = false; }
});
el("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(el("prompt").value);
    el("copy-status").textContent = "Copied. Paste it into your chat.";
  } catch {
    el("prompt").focus(); el("prompt").select();
    el("copy-status").textContent = "Selected. Copy it with your keyboard.";
  }
});
window.addEventListener("pagehide", () => { if (objectUrl) URL.revokeObjectURL(objectUrl); });
