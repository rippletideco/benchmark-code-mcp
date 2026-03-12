from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Literal

AgentExecutable = Literal['codex', 'claude']


def resolve_agent_cli_executable(name: AgentExecutable) -> str | None:
    override = os.environ.get(f'{name.upper()}_EXECUTABLE', '').strip()
    if override:
        if '/' not in override:
            executable = shutil.which(override)
            if executable:
                return executable
        else:
            candidate = Path(override).expanduser()
            if _is_executable(candidate):
                return str(candidate)

    executable = shutil.which(name)
    if executable:
        return executable

    for candidate in _candidate_executables(name):
        if _is_executable(candidate):
            return str(candidate)
    return None


def _candidate_executables(name: AgentExecutable) -> list[Path]:
    home = Path.home()
    candidates = [
        home / '.local' / 'bin' / name,
        home / 'bin' / name,
    ]
    if name == 'codex':
        candidates.extend(_glob_candidates(home, '.vscode-server/extensions/openai.chatgpt-*/bin/*/codex'))
        candidates.extend(_glob_candidates(home, '.vscode/extensions/openai.chatgpt-*/bin/*/codex'))
    return candidates


def _glob_candidates(root: Path, pattern: str) -> list[Path]:
    return sorted(root.glob(pattern), reverse=True)


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)
