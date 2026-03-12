from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .executable_resolver import resolve_agent_cli_executable

AgentKey = Literal['codex', 'claude', 'custom']


@dataclass(slots=True)
class AgentBackendStatus:
    key: AgentKey
    label: str
    description: str
    available: bool
    authenticated: bool
    default_for_external: bool
    command_preview: str | None
    auth_message: str
    requires_custom_command: bool = False


def list_agent_backends(benchmark_root: Path) -> list[AgentBackendStatus]:
    return [
        _detect_codex_backend(benchmark_root),
        _detect_claude_backend(benchmark_root),
        AgentBackendStatus(
            key='custom',
            label='Custom command',
            description='Use any external adapter command that implements the benchmark NDJSON contract.',
            available=True,
            authenticated=False,
            default_for_external=False,
            command_preview=None,
            auth_message='Provide a full adapter command.',
            requires_custom_command=True,
        ),
    ]


def resolve_external_adapter_command(
    *,
    benchmark_root: Path,
    agent_backend: str,
    adapter_command: str | None,
) -> str:
    cleaned_command = (adapter_command or '').strip()
    if agent_backend == 'custom':
        if not cleaned_command:
            raise ValueError('Custom agent backend requires an adapter command.')
        return cleaned_command
    if cleaned_command:
        return cleaned_command
    if agent_backend == 'claude':
        return f'python3 {benchmark_root / "scripts" / "adapter_claude.py"} {{request_file}}'
    if agent_backend == 'codex':
        return f'python3 {benchmark_root / "scripts" / "adapter_codex.py"} {{request_file}}'
    raise ValueError(f'Unknown agent backend: {agent_backend}')


def serialize_agent_backends(backends: list[AgentBackendStatus]) -> list[dict]:
    return [asdict(item) for item in backends]


def _detect_codex_backend(benchmark_root: Path) -> AgentBackendStatus:
    executable = resolve_agent_cli_executable('codex')
    command_preview = (
        f'python3 {benchmark_root / "scripts" / "adapter_codex.py"} {{request_file}}'
        if executable
        else None
    )
    authenticated = False
    auth_message = 'Codex CLI not found on this machine.'
    if executable:
        completed = subprocess.run(
            [executable, 'login', 'status'],
            text=True,
            capture_output=True,
            check=False,
        )
        combined_output = '\n'.join(
            part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
        )
        authenticated = completed.returncode == 0 and 'Logged in' in combined_output
        auth_message = combined_output or 'Codex detected.'
    return AgentBackendStatus(
        key='codex',
        label='Codex',
        description='OpenAI Codex CLI benchmark adapter.',
        available=bool(executable),
        authenticated=authenticated,
        default_for_external=True,
        command_preview=command_preview,
        auth_message=auth_message,
    )


def _detect_claude_backend(benchmark_root: Path) -> AgentBackendStatus:
    executable = resolve_agent_cli_executable('claude')
    command_preview = (
        f'python3 {benchmark_root / "scripts" / "adapter_claude.py"} {{request_file}}'
        if executable
        else None
    )
    authenticated = False
    auth_message = 'Claude Code CLI not found on this machine.'
    if executable:
        completed = subprocess.run(
            [executable, 'auth', 'status', '--json'],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0:
            try:
                payload = json.loads(completed.stdout)
                authenticated = bool(payload.get('loggedIn'))
                auth_method = payload.get('authMethod') or 'unknown'
                auth_message = (
                    f'Claude Code detected, auth={auth_method}, '
                    f'provider={payload.get("apiProvider", "unknown")}'
                )
            except json.JSONDecodeError:
                auth_message = completed.stdout.strip() or 'Claude Code detected.'
        else:
            auth_message = completed.stderr.strip() or completed.stdout.strip() or 'Claude Code detected.'
    return AgentBackendStatus(
        key='claude',
        label='Claude Code',
        description='Anthropic Claude Code CLI benchmark adapter.',
        available=bool(executable),
        authenticated=authenticated,
        default_for_external=False,
        command_preview=command_preview,
        auth_message=auth_message,
    )
