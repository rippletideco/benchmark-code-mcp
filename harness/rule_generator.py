"""Generate tailored coding rules for a cloned repository using the Claude CLI."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def _gather_repo_context(repo_path: Path) -> str:
    parts: list[str] = []

    # README
    readme = repo_path / 'README.md'
    if readme.exists():
        parts.append(f'### README.md\n{readme.read_text()[:3000]}')

    # Existing instruction files
    for name in ('CLAUDE.md', 'AGENTS.md'):
        p = repo_path / name
        if p.exists():
            parts.append(f'### {name}\n{p.read_text()[:2000]}')
            break

    # Language / framework indicators
    indicators: list[str] = []
    for marker in ('package.json', 'pyproject.toml', 'go.mod', 'Cargo.toml', 'pom.xml'):
        if (repo_path / marker).exists():
            indicators.append(marker)
    if indicators:
        parts.append(f'### Build / language files present\n' + ', '.join(indicators))

    # Test framework from package.json
    pkg_json = repo_path / 'package.json'
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            all_deps = {
                **pkg.get('devDependencies', {}),
                **pkg.get('dependencies', {}),
            }
            detected = [k for k in ('vitest', 'jest', 'mocha', 'pytest') if k in all_deps]
            if detected:
                parts.append(f'### Test frameworks detected\n' + ', '.join(detected))
        except (json.JSONDecodeError, OSError):
            pass

    # File tree sample (up to 30 paths)
    try:
        result = subprocess.run(
            ['git', 'ls-files', '--cached'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        file_list = [l for l in result.stdout.splitlines() if l.strip()][:30]
        if file_list:
            parts.append('### Sample file paths\n' + '\n'.join(file_list))
    except OSError:
        pass

    return '\n\n'.join(parts)


def generate_repo_rules(repo_path: Path, n_rules: int = 40) -> str:
    """Inspect a cloned repo and call `claude -p` to generate n_rules tailored rules.

    Returns a markdown string. Raises RuntimeError if the CLI call fails.
    """
    context = _gather_repo_context(repo_path)

    prompt = (
        f'You are analyzing a GitHub repository to generate coding rules for a benchmark agent.\n\n'
        f'## Repository Context\n\n{context}\n\n'
        f'## Task\n\n'
        f'Generate exactly {n_rules} specific, actionable coding rules tailored to THIS repository.\n'
        f'Focus on: language and framework conventions, test patterns, file structure, '
        f'import patterns, code style observed in this codebase.\n'
        f'Format as a numbered markdown list. Each rule must be specific (not a generic platitude).\n'
        f'Output ONLY the numbered rules — no preamble, no headers, no explanation.\n'
    )

    # Strip CLAUDECODE so the subprocess can launch even inside a running Claude session
    env = os.environ.copy()
    env.pop('CLAUDECODE', None)

    try:
        result = subprocess.run(
            ['claude', '-p', '--output-format', 'text'],
            input=prompt,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            'claude CLI not found. Install it and authenticate before using --generate-rules.'
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f'claude CLI exited with code {exc.returncode}.\nstderr: {exc.stderr[:500]}'
        ) from exc

    return result.stdout.strip()
