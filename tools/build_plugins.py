"""Build self-contained host plugins from an explicit public source allowlist."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.4.0"
MODULES = ("__init__", "contracts", "parser", "decoder", "intake", "runtime", "schemas",
           "server", "service", "supervisor", "worker", "library")
HOST_MODULES = ("__init__", "intake", "server", "picker", "ui")
ASSETS = ("celebrate-stars", "thanks-glow", "waiting-moon", "sorry-feather")


def source_files(host):
    if host not in ("codex", "claude-code"):
        raise ValueError("Unknown host package")
    sources = {name: name for name in ("LICENSE", ".python-version", "requirements.txt",
                                     "bin/gif-communication-host", "bin/gif-picker", "tools/configure_runtime.py")}
    for directory, names in (("gif_communication", MODULES), ("gif_host", HOST_MODULES)):
        sources.update({f"{directory}/{name}.py": f"{directory}/{name}.py" for name in names})
    for name in ("picker.html", "picker.css", "picker.js", "widget.html"):
        sources[f"gif_host/web/{name}"] = f"gif_host/web/{name}"
    for name in ("inspect_gif.v1", "inspect_gif.v2", "get_gif_frames.v1", "evidence.v1",
                 "find_reply_gif.v1", "find_reply_gif_result.v1"):
        sources[f"schemas/{name}.json"] = f"schemas/{name}.json"
    sources["library/catalog.json"] = "library/catalog.json"
    for asset in ASSETS:
        for folder, suffix in (("assets", "gif"), ("posters", "png")):
            name = f"library/{folder}/{asset}.{suffix}"
            sources[name] = name
    names = [".mcp.json", "README.md", "skills/gif-communication/SKILL.md"]
    names += ([".codex-plugin/plugin.json"] if host == "codex" else
              [".claude-plugin/plugin.json", "hooks/hooks.json", "hooks/register.js"])
    sources.update({name: f"integrations/{host}/{name}" for name in names})
    return sources


def inventory(host):
    entries = []
    for target, source in sorted(source_files(host).items()):
        path = ROOT / source
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing or symlinked source: " + source)
        raw = path.read_bytes()
        entries.append({"path": target, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                        "mode": "0755" if target.startswith("bin/") else "0644"})
    return entries


def validate_tree(package, data):
    entries = data["files"]
    if (data.get("generated_by") != "tools/build_plugins.py" or
            {e["path"] for e in entries} != set(source_files(data["host"])) or
            len(entries) != len(source_files(data["host"]))):
        raise ValueError("Unknown package ownership or paths")
    digest = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if digest != data.get("content_sha256"):
        raise ValueError("Package inventory digest mismatch")
    expected = {entry["path"] for entry in entries} | {"PACKAGE-CONTENTS.json"}
    expected_dirs = {parent.as_posix() for name in expected for parent in Path(name).parents if parent.as_posix() != "."}
    actual, actual_dirs = set(), set()
    for path in package.rglob("*"):
        mode = path.lstat().st_mode
        relative = path.relative_to(package).as_posix()
        if stat.S_ISREG(mode):
            actual.add(relative)
        elif stat.S_ISDIR(mode):
            actual_dirs.add(relative)
        else:
            raise ValueError("Symlink or special entry in package")
    if actual != expected or actual_dirs != expected_dirs:
        raise ValueError("Unexpected or missing plugin files/directories")
    for entry in entries:
        path = package / entry["path"]
        if (hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"] or
                len(path.read_bytes()) != entry["bytes"] or
                (path.stat().st_mode & 0o777) != int(entry["mode"], 8)):
            raise ValueError("Plugin identity mismatch: " + entry["path"])


def verify(package):
    package = Path(package)
    if package.is_symlink():
        raise ValueError("Symlinked plugin root")
    data = json.loads((package / "PACKAGE-CONTENTS.json").read_text())
    entries = data["files"]
    if data["version"] != VERSION or entries != inventory(data["host"]):
        raise ValueError("Plugin differs from reviewed source")
    validate_tree(package, data)
    return data


def build(output):
    packages = {}
    for host in ("codex", "claude-code"):
        package = output / host
        if any(p.is_symlink() for p in [package, *package.parents]):
            raise ValueError("Refuse a symlinked output path")
        if package.exists():
            # Only replace a previous generated package with exactly its recorded leaves.
            manifest = package / "PACKAGE-CONTENTS.json"
            prior = json.loads(manifest.read_text())
            if prior.get("host") != host:
                raise ValueError("Refuse to replace another host's package")
            validate_tree(package, prior)
            shutil.rmtree(package)
        package.mkdir(parents=True)
        entries = inventory(host)
        for entry in entries:
            target = package / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / source_files(host)[entry["path"]], target)
            target.chmod(int(entry["mode"], 8))
        digest = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        manifest = {"schema_version": 1, "version": VERSION, "host": host,
                    "generated_by": "tools/build_plugins.py", "content_sha256": digest, "files": entries}
        (package / "PACKAGE-CONTENTS.json").write_text(json.dumps(manifest, indent=2) + "\n")
        verify(package)
        packages[host] = {"path": str(package), "content_sha256": digest, "files": len(entries)}
    return packages


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "plugins")
    args = parser.parse_args()
    print(json.dumps(build(args.output.absolute()), indent=2))
