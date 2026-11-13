#!/usr/bin/env python3
"""Update version references from the single source of truth.

The version SSOT is ``seqmodeller/resources/version.json``.  This script keeps
the UI strings and README download links in sync with it.

Usage:
    python dev/update_version.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "seqmodeller" / "resources" / "version.json"
ABOUT_UI = ROOT / "seqmodeller" / "resources" / "about.ui"
APP_UI = ROOT / "seqmodeller" / "resources" / "app.ui"
README = ROOT / "README.md"


def load_version_info() -> dict:
    try:
        return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Error: {VERSION_FILE} not found.")
        raise SystemExit(1) from None
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {VERSION_FILE}: {exc}")
        raise SystemExit(1) from None


def replace_in_file(path: Path, pattern: str, replacement: str) -> bool:
    if not path.exists():
        print(f"Warning: {path} not found, skipping...")
        return False
    content = path.read_text(encoding="utf-8")
    updated = re.sub(pattern, replacement, content)
    if updated == content:
        print(f"- No changes needed in {path.relative_to(ROOT)}")
        return False
    path.write_text(updated, encoding="utf-8")
    print(f"✓ Updated {path.relative_to(ROOT)}")
    return True


def main() -> int:
    info = load_version_info()
    version = info["version"]
    print(f"SeqModeller version: {version}")
    print(f"Build: {info.get('build', 'unknown')}")

    count = 0
    count += replace_in_file(
        ABOUT_UI,
        r"(\[SeqModeller\]\([^)]+\) \*v)[0-9]+\.[0-9]+\.[0-9]+(\*)",
        rf"\g<1>{version}\g<2>",
    )
    count += replace_in_file(
        APP_UI,
        r"(<string>SeqModeller - v)[0-9]+\.[0-9]+\.[0-9]+(</string>)",
        rf"\g<1>{version}\g<2>",
    )
    count += replace_in_file(
        README,
        r"(releases/download/v)[0-9]+\.[0-9]+\.[0-9]+(/SeqModeller-v)[0-9]+\.[0-9]+\.[0-9]+(_Linux_x86-64\.zip)",
        rf"\g<1>{version}\g<2>{version}\g<3>",
    )
    count += replace_in_file(
        README,
        r"(unzip SeqModeller-v)[0-9]+\.[0-9]+\.[0-9]+(_Linux_x86-64\.zip)",
        rf"\g<1>{version}\g<2>",
    )
    count += replace_in_file(
        README,
        r"(cd SeqModeller-v)[0-9]+\.[0-9]+\.[0-9]+(_Linux_x86-64)",
        rf"\g<1>{version}\g<2>",
    )
    print(f"\nUpdate complete: {count} file(s) changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
