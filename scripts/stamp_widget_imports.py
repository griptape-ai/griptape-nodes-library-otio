"""Stamp the relative imports in each widget folder with a hash of the widget's files.

The engine adds a content hash to a widget's entry file URL, so the browser fetches the entry again when it changes.
The files the entry imports (`./_ops.js` and so on) get no hash, and a page that has already loaded them keeps the
old copy. The entry then asks an old module for something new and the widget fails to load.

This script writes `?v=<hash>` onto every relative import in every widget file, where the hash covers all the files in
the folder. Change any file and every import URL changes with it. The stamps are left out of the hash, so running the
script twice changes nothing.

    python scripts/stamp_widget_imports.py           stamp the files
    python scripts/stamp_widget_imports.py --check   exit 1 if any stamp is out of date
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

WIDGETS_DIR = Path(__file__).resolve().parent.parent / "otio_nodes" / "widgets"
IMPORT = re.compile(r"""(from\s+['"])(\.{1,2}/[^'"?]+\.js)(\?v=[0-9a-f]{8})?(['"])""")
STAMP = re.compile(r"\?v=[0-9a-f]{8}")


def widget_files(folder: Path) -> list[Path]:
    return sorted(folder.glob("*.js"))


def folder_hash(folder: Path) -> str:
    """Hash every .js file in the folder, ignoring the stamps themselves."""
    digest = hashlib.sha256()
    for path in widget_files(folder):
        digest.update(path.name.encode())
        digest.update(STAMP.sub("", path.read_text(encoding="utf-8")).encode())
    return digest.hexdigest()[:8]


def stamped(text: str, version: str) -> str:
    return IMPORT.sub(lambda m: f"{m.group(1)}{m.group(2)}?v={version}{m.group(4)}", text)


def stale_files(folder: Path) -> list[Path]:
    version = folder_hash(folder)
    return [
        p
        for p in widget_files(folder)
        if stamped(p.read_text(encoding="utf-8"), version) != p.read_text(encoding="utf-8")
    ]


def stamp_folder(folder: Path) -> list[Path]:
    """Rewrite out-of-date files. Return the ones that changed."""
    version = folder_hash(folder)
    changed = []
    for path in widget_files(folder):
        text = path.read_text(encoding="utf-8")
        new = stamped(text, version)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed.append(path)
    return changed


def widget_folders(root: Path = WIDGETS_DIR) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []


def main(argv: list[str]) -> int:
    check = "--check" in argv
    status = 0
    for folder in widget_folders():
        if check:
            stale = stale_files(folder)
            for path in stale:
                print(f"{path.relative_to(WIDGETS_DIR.parent.parent)}: import stamps are out of date")
            status = 1 if stale else status
        else:
            for path in stamp_folder(folder):
                print(f"stamped {path.relative_to(WIDGETS_DIR.parent.parent)}")
    if check and status:
        print("Run `make fix` (or python scripts/stamp_widget_imports.py) to update them.")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
