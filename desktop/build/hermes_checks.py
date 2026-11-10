"""Hermes' own checks on the built Desktop half, run with the Python that runs Hermes:

- the Desktop admission lint (`hermes_cli.plugin_validate_desktop.desktop_surface_findings`), the rule
  `hermes plugins validate` applies to desktop/plugin.js;
- the install-time security scan (`tools.plugin_guard.scan_plugin`) on a copy of the plugin folder as it
  ships, under its shipped name `unblockbruecke` (without desktop/build/node_modules): verdict `safe`
  means no HIGH finding, so a Desktop or non-interactive install is not blocked.

    /opt/hermes/.venv/bin/python hermes_checks.py <plugin dir>     prints one JSON line

Pattern: plugins/eselsbruecke/desktop/build/hermes_checks.py.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/opt/hermes")
from hermes_cli.plugin_validate_desktop import desktop_surface_findings  # noqa: E402
from tools.plugin_guard import scan_plugin  # noqa: E402

SHIPPED_NAME = "unblockbruecke"


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    lint = desktop_surface_findings((root / "desktop" / "plugin.js").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        pkg = Path(tmp) / SHIPPED_NAME
        shutil.copytree(root, pkg, ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache"))
        result = scan_plugin(pkg)
    by = Counter((getattr(f, "severity", None), getattr(f, "pattern_id", None)) for f in result.findings)
    high = [f"{p} in {getattr(f, 'file', None)}" for f in result.findings
            for p in [getattr(f, "pattern_id", None)] if str(getattr(f, "severity", "")).lower() in ("high", "critical")]
    desktop = [f"{getattr(f, 'severity', None)}:{getattr(f, 'pattern_id', None)}" for f in result.findings
               if "desktop" in str(getattr(f, "file", ""))]
    print(json.dumps({"name": SHIPPED_NAME, "lint": [{"rule": r, "line": n} for r, n in lint], "verdict": result.verdict, "high": high,
                      "desktop_findings": desktop, "findings": {f"{s}:{p}": n for (s, p), n in sorted(by.items(), key=str)}}))


if __name__ == "__main__":
    main()
