"""Optional browser integration check with synthetic media; no host installation."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gif_host.picker import Picker


if __name__ == "__main__":
    (ROOT / "build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="browser-inbox-", dir=ROOT / "build") as temporary:
        picker = Picker(temporary)
        try:
            result = subprocess.run([os.environ.get("GIF_NODE", "node"), str(ROOT / "tools/browser_check.cjs"), picker.url],
                                    cwd=ROOT, timeout=45)
            raise SystemExit(result.returncode)
        finally:
            picker.close()
