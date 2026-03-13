"""Discover markdown instruction content from a file path, directory, or zip archive."""

from __future__ import annotations

import zipfile
from pathlib import Path

_PRIORITY_NAMES = ["CLAUDE.md", "AGENTS.md", ".claude/CLAUDE.md"]


def discover_instructions(source: str | Path) -> str:
    """Return markdown content from a file, directory, or .zip archive.

    - Directory: probes CLAUDE.md, AGENTS.md, .claude/CLAUDE.md in priority order.
    - .zip: returns the first CLAUDE.md or AGENTS.md entry found inside.
    - Anything else: read the file directly.

    Raises FileNotFoundError if no suitable file is found.
    """
    path = Path(source).expanduser()

    if path.suffix == ".zip":
        return _from_zip(path)
    elif path.is_dir():
        return _from_dir(path)
    else:
        if not path.exists():
            raise FileNotFoundError(f"Instructions file not found: {path}")
        return path.read_text()


def _from_dir(directory: Path) -> str:
    for name in _PRIORITY_NAMES:
        candidate = directory / name
        if candidate.exists():
            return candidate.read_text()
    raise FileNotFoundError(
        f"No instructions file found in {directory}. "
        f"Expected one of: {', '.join(_PRIORITY_NAMES)}"
    )


def _from_zip(zip_path: Path) -> str:
    if not zip_path.exists():
        raise FileNotFoundError(f"Zip archive not found: {zip_path}")
    target_names = {"CLAUDE.md", "AGENTS.md"}
    with zipfile.ZipFile(zip_path) as zf:
        for entry in zf.infolist():
            filename = Path(entry.filename).name
            if filename in target_names:
                return zf.read(entry.filename).decode()
    raise FileNotFoundError(
        f"No CLAUDE.md or AGENTS.md found inside {zip_path}"
    )
