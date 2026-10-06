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
function clearSelection() {
  selected = null;
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = null;
  el("image").removeAttribute("src"); playing = false;
  el("motion").textContent = "Play preview";
  el("preview").hidden = true;
  el("result").hidden = true;
  for (const card of el("search-results").children) card.classList.remove("selected");
}
function chooseRepository(item, card) {
  fileEpoch += 1;
  clearSelection();
  selected = {kind: "repository", item};
  el("motion").textContent = "Show preview";
  card.classList.add("selected");
  el("filename").textContent = item.title + " · " + item.license;
  el("preview").hidden = false;
  el("status").textContent = "Selected · Use this GIF retrieves the original from Wikimedia Commons.";
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
  el("search-status").textContent = "Searching Wikimedia Commons…";
  try {
    const response = await fetch("search", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({query})});
    const value = await response.json();
    if (epoch !== searchEpoch) return;
    if (!response.ok) throw new Error(value.error || "Search is unavailable. Try again or choose a local GIF.");
    for (const item of value.results) {
      const card = document.createElement("div"); card.className = "gif-card";
      const title = document.createElement("h3"); title.textContent = item.title;
      const info = document.createElement("p");
      info.textContent = item.license + (item.author ? " · " + item.author : "") +
        " · " + Math.ceil(item.bytes / 1024) + " KiB";
      const choose = document.createElement("button"); choose.type = "button";
      choose.textContent = "Choose GIF"; choose.setAttribute("aria-label", "Choose " + item.title);
      choose.addEventListener("click", () => chooseRepository(item, card));
      card.append(title, info, choose);
      const source = safeLink(item.source_url, ["commons.wikimedia.org"]);
      if (source) {
        const link = document.createElement("a"); link.href = source;
        link.target = "_blank"; link.rel = "noopener noreferrer";
        link.textContent = "Source and license"; card.append(document.createElement("br"), link);
      }
      el("search-results").append(card);
    }
    el("search-status").textContent = value.results.length ?
      value.results.length + " animated GIFs · Choose one, then preview it or use it." :
      "No compatible GIFs found. Try another search or choose a local file.";
  } catch (error) {
    if (epoch === searchEpoch) el("search-status").textContent = error.message;
  } finally { if (epoch === searchEpoch) el("search").disabled = false; }
});
el("choose").addEventListener("click", () => el("file").click());
el("file").addEventListener("change", async () => {
  const epoch = ++fileEpoch;
  clearSelection();
  const file = el("file").files[0];
  if (!file || file.size === 0 || file.size > 20 * 1024 * 1024) {
    el("status").textContent = "Choose a GIF between 1 byte and 20 MiB."; return;
  }
  const header = new TextDecoder().decode(await file.slice(0, 6).arrayBuffer());
  if (epoch !== fileEpoch) return;
  if (!["GIF87a", "GIF89a"].includes(header)) {
    el("status").textContent = "This file is not an original GIF."; return;
  }
  selected = {kind: "local", file};
  objectUrl = URL.createObjectURL(file);
  el("filename").textContent = file.name;
  el("preview").hidden = false;
  el("status").textContent = "Selected · Use this GIF saves the original in your inbox.";
});
el("motion").addEventListener("click", () => {
  if (!selected) return;
  playing = !playing;
  const preview = selected.kind === "local" ? objectUrl :
    safeLink(selected.item.preview_url, ["upload.wikimedia.org", "thumb.wikimedia.org"]);
  if (playing && preview) el("image").src = preview;
  else { el("image").removeAttribute("src"); playing = false; }
  el("motion").textContent = selected.kind === "local" ?
    (playing ? "Stop preview" : "Play preview") : (playing ? "Hide preview" : "Show preview");
});
el("stage").addEventListener("click", async () => {
  if (!selected || el("stage").disabled) return;
  const selection = selected;
  el("stage").disabled = true;
  el("status").textContent = selection.kind === "repository" ? "Retrieving the original GIF…" : "Saving the original GIF…";
  try {
    const remote = selection.kind === "repository";
    const response = await fetch(remote ? "select" : "stage", {method:"POST",
      headers:{"Content-Type": remote ? "application/json" : "image/gif"},
      body: remote ? JSON.stringify({id: selection.item.id}) : selection.file});
    const value = await response.json();
    if (selection !== selected) return;
    if (!response.ok) throw new Error(value.error || "Could not prepare this GIF. Try a different one.");
    el("prompt").value = value.prompt;
    el("digest").textContent = "SHA-256 " + value.sha256 + " · " + value.bytes + " bytes";
    el("attribution").hidden = !remote;
    if (remote) {
      const item = selection.item;
      el("attribution").textContent = "Wikimedia Commons · " + item.title + " · " + item.license +
        (item.author ? " · " + item.author : "");
      const source = safeLink(item.source_url, ["commons.wikimedia.org"]);
      if (source) {
        const link = document.createElement("a"); link.href = source; link.target = "_blank";
        link.rel = "noopener noreferrer"; link.textContent = "Source and license";
        el("attribution").append(document.createElement("br"), link);
      }
    }
    el("result").hidden = false;
    el("copy-status").textContent = "";
    el("status").textContent = "Original ready. Copy the request and paste it into your chat.";
    el("copy").focus();
  } catch(error) { if (selection === selected) el("status").textContent = error.message; }
  finally { el("stage").disabled = false; }
});
el("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(el("prompt").value);
    el("copy-status").textContent = "Copied. Paste into your chat when ready.";
  } catch {
    el("prompt").focus(); el("prompt").select();
    el("copy-status").textContent = "Select and copy the request above.";
  }
});
window.addEventListener("pagehide", () => { if (objectUrl) URL.revokeObjectURL(objectUrl); });
