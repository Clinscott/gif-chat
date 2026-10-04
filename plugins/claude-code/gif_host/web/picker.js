"use strict";
const el = (id) => document.getElementById(id);
let selected = null, objectUrl = null, playing = false;
el("choose").addEventListener("click", () => el("file").click());
el("file").addEventListener("change", async () => {
  el("result").hidden = true;
  const file = el("file").files[0];
  if (!file || file.size === 0 || file.size > 20 * 1024 * 1024) {
    selected = null; el("preview").hidden = true;
    el("status").textContent = "Choose a GIF between 1 byte and 20 MiB."; return;
  }
  const header = new TextDecoder().decode(await file.slice(0, 6).arrayBuffer());
  if (!["GIF87a", "GIF89a"].includes(header)) {
    selected = null; el("preview").hidden = true;
    el("status").textContent = "This file is not an original GIF."; return;
  }
  selected = file;
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = URL.createObjectURL(file);
  // Keep motion opt-in, including for reduced-motion users.
  el("image").removeAttribute("src"); playing = false;
  el("motion").textContent = "Play preview";
  el("filename").textContent = file.name;
  el("preview").hidden = false;
  el("status").textContent = "Selected · Use this GIF saves the original in your inbox.";
});
el("motion").addEventListener("click", () => {
  playing = !playing;
  if (playing) el("image").src = objectUrl;
  else el("image").removeAttribute("src");
  el("motion").textContent = playing ? "Stop preview" : "Play preview";
});
el("stage").addEventListener("click", async () => {
  if (!selected) return;
  el("stage").disabled = true;
  try {
    const response = await fetch("stage", {method:"POST", headers:{"Content-Type":"image/gif"}, body:selected});
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || "Could not stage this GIF.");
    el("prompt").value = value.prompt;
    el("digest").textContent = "SHA-256 " + value.sha256 + " · " + value.bytes + " bytes";
    el("result").hidden = false;
    el("copy-status").textContent = "";
    el("status").textContent = "Original saved. Your agent can now inspect its frames.";
    el("copy").focus();
  } catch(error) { el("status").textContent = error.message; }
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
