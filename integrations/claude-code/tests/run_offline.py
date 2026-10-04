"""Validate the real plugin, then test its mod with disposable placeholder options."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]


def main() -> int:
    validated = subprocess.run(
        ["claude", "plugin", "validate", "--strict", str(PLUGIN)], check=False
    )
    if validated.returncode:
        return validated.returncode

    # `claude plugin test` loads the manifest before running any test and does
    # not prompt for required userConfig. Supply inert values in a disposable
    # copy; never write the user's Claude Code configuration.
    with tempfile.TemporaryDirectory(prefix="gif-claude-mod-test-") as temporary:
        test_plugin = Path(temporary) / "claude-code"
        shutil.copytree(PLUGIN, test_plugin)
        manifest = test_plugin / ".claude-plugin" / "plugin.json"
        data = json.loads(manifest.read_text())
        data["userConfig"]["python_executable"]["default"] = sys.executable
        data["userConfig"]["source_root"]["default"] = temporary
        data["userConfig"]["runtime_lock"]["default"] = str(Path(temporary) / "runtime-lock.json")
        manifest.write_text(json.dumps(data))
        config_dir = Path(temporary) / "claude-config"
        config_dir.mkdir()
        environment = dict(os.environ, CLAUDE_CONFIG_DIR=str(config_dir))
        tested = subprocess.run(
            ["claude", "plugin", "test", str(test_plugin)],
            check=False,
            env=environment,
        )
        return tested.returncode


if __name__ == "__main__":
    raise SystemExit(main())
