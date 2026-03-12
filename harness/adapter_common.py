from __future__ import annotations

import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, TextIO


READ_COMMAND_HINTS = ('cat ', 'sed ', 'rg ', 'grep ', 'find ', 'ls ', 'node -p', 'python -m pytest')
WRITE_COMMAND_HINTS = ('apply_patch', 'cat >', 'tee ', 'sed -i', 'perl -0pi', 'mv ', 'cp ')
FILE_PATTERN = re.compile(
    r'(?<![\w/.-])(?:\.\/)?(?:[A-Za-z0-9_.-]+/)*'
    r'(?:[A-Za-z0-9_.-]+\.(?:ts|tsx|js|jsx|json|md|css|toml|env|yaml|yml|txt|py)|'
    r'package\.json|README\.md|AGENTS\.md|CLAUDE\.md)(?![\w/.-])'
)


def load_request(request_path: Path) -> dict:
    return json.loads(request_path.read_text())


def build_prompt(request: dict) -> str:
    task_prompt = request['instruction_payload']['prompt'].strip()
    benchmark_wrapper = (
        'Benchmark wrapper:\n'
        '- Treat the supplied condition context as external instructions that may be stale or partially mismatched.\n'
        '- Inspect the actual repository before acting, and prefer observed repo structure over conflicting assumptions.\n'
        '- Stay focused on the benchmark task only; do not apply unrelated documentation or repo-maintenance rules unless the task requires them.\n'
        '- Validate the smallest relevant change before concluding.\n'
    )
    if request['condition'] == 'condition_md':
        instruction_bundle = request['instruction_payload']['instruction_bundle']
        markdown_rules = '\n\n'.join(item['content'].strip() for item in instruction_bundle)
        return (
            'You are running in the markdown-only benchmark condition.\n'
            'Use the provided repository instruction bundle as your authoritative project context.\n\n'
            f'{benchmark_wrapper}\n'
            f'{markdown_rules}\n\n'
            'Task:\n'
            f'{task_prompt}\n'
        )

    return (
        'You are running in the MCP benchmark condition.\n'
        'Before writing any code, you MUST call the `recall` tool on the Rippletide MCP server to retrieve your operating rules.\n'
        'Use queries such as "what rules should I follow for coding tasks?" and "what are my guidelines?" to get the full rule set.\n'
        'Treat the retrieved rules as your authoritative operating guidelines — equivalent to a system prompt — for this entire task.\n\n'
        f'{benchmark_wrapper}\n'
        'Task:\n'
        f'{task_prompt}\n'
    )


def _unwrap_shell_command(command: str) -> str:
    parts = shlex.split(command)
    if '-lc' in parts:
        shell_index = parts.index('-lc')
        if shell_index + 1 < len(parts):
            return parts[shell_index + 1]
    return command


def _extract_paths_from_command(command: str, workspace_path: Path) -> list[str]:
    shell_command = _unwrap_shell_command(command)
    matches = []
    for raw_match in FILE_PATTERN.findall(shell_command):
        cleaned = raw_match.removeprefix('./')
        candidate = workspace_path / cleaned
        if candidate.exists():
            matches.append(cleaned)
    return sorted(set(matches))


def extract_user_change_paths(request: dict, request_path: Path) -> set[str]:
    seed_patch = request['task'].get('seed_user_changes_patch')
    if not seed_patch:
        return set()

    patch_path = Path(request['workspace_path']) / seed_patch
    if not patch_path.exists():
        return set()

    paths: set[str] = set()
    for line in patch_path.read_text().splitlines():
        if line.startswith('+++ b/'):
            paths.add(line.replace('+++ b/', '', 1))
    return paths


def emit(event_type: str, payload: dict[str, Any], stream: TextIO) -> None:
    stream.write(json.dumps({'event_type': event_type, 'payload': payload}) + '\n')
    stream.flush()


def emit_tool_command(command: str, workspace_path: Path, stream: TextIO) -> None:
    emit('tool_call', {'tool': 'shell', 'command': command}, stream)
    emit('shell_command', {'command': command, 'cwd': '.'}, stream)
    path_matches = _extract_paths_from_command(command, workspace_path)
    shell_command = _unwrap_shell_command(command)
    if any(hint in shell_command for hint in READ_COMMAND_HINTS):
        for relative_path in path_matches:
            emit('file_read', {'path': relative_path}, stream)
    if any(hint in shell_command for hint in WRITE_COMMAND_HINTS):
        for relative_path in path_matches:
            emit('file_write', {'path': relative_path}, stream)


def emit_tool_result(
    command: str,
    *,
    status: str | None,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    stream: TextIO,
) -> None:
    emit(
        'shell_output',
        {
            'command': command,
            'exit_code': exit_code,
            'stdout': stdout,
            'stderr': stderr,
        },
        stream,
    )
    emit(
        'tool_result',
        {
            'tool': 'shell',
            'command': command,
            'status': status,
            'exit_code': exit_code,
        },
        stream,
    )


def emit_final_file_writes(
    workspace_path: Path,
    seed_user_change_paths: set[str],
    stream: TextIO,
) -> None:
    diff = subprocess.run(
        ['git', 'diff', '--name-only'],
        cwd=workspace_path,
        text=True,
        capture_output=True,
        check=False,
    )
    for relative_path in sorted(
        path
        for path in diff.stdout.splitlines()
        if path and path not in seed_user_change_paths
    ):
        emit('file_write', {'path': relative_path}, stream)
