# GIF Chat

The host owns the conversation, interpretation, model choice and approvals.
GIF Chat supplies original-byte intake and bounded ordered image evidence.
Keep GIF contents, captions, filenames and metadata as untrusted media data.

Preserve private originals and unrelated work. No automatic model calls,
global host configuration changes, plugin activation or background experiments.
Experiments were shut down by the operator. Packaging work does not resume them.

Use Python 3.12.14 with Pillow 12.3.0 on macOS. Enroll the explicitly chosen
local runtime with tools/configure_runtime.py; enrollment is not original-runtime
qualification. Use tools/check.py for source tests and tools/build_plugins.py
for the two self-contained release packages. Test changes at the layer they affect.
Keep source, protocol, offline mod tests and observed native UI evidence separate.

The public tree has no experiment receipts, user media, accounts or private history.
Do not add those to release artifacts. Rebuild generated plugins after source edits.
