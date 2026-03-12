from __future__ import annotations

import json
import stat
from pathlib import Path

from harness.agent_registry import list_agent_backends, resolve_external_adapter_command
from harness.executable_resolver import resolve_agent_cli_executable


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_resolve_external_adapter_command_supports_codex_claude_and_custom() -> None:
    codex_command = resolve_external_adapter_command(
        benchmark_root=REPO_ROOT,
        agent_backend='codex',
        adapter_command=None,
    )
    claude_command = resolve_external_adapter_command(
        benchmark_root=REPO_ROOT,
        agent_backend='claude',
        adapter_command=None,
    )
    custom_command = resolve_external_adapter_command(
        benchmark_root=REPO_ROOT,
        agent_backend='custom',
        adapter_command='python3 adapter.py {request_file}',
    )

    assert codex_command.endswith('scripts/adapter_codex.py {request_file}')
    assert claude_command.endswith('scripts/adapter_claude.py {request_file}')
    assert custom_command == 'python3 adapter.py {request_file}'


def test_list_agent_backends_marks_codex_as_default_external_backend() -> None:
    backends = list_agent_backends(REPO_ROOT)
    backend_keys = {backend.key for backend in backends}

    assert {'codex', 'claude', 'custom'} <= backend_keys
    assert any(backend.key == 'codex' and backend.default_for_external for backend in backends)
    assert any(backend.key == 'custom' and backend.requires_custom_command for backend in backends)


def test_resolve_agent_cli_executable_finds_codex_in_vscode_extension_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv('CODEX_EXECUTABLE', raising=False)
    monkeypatch.setenv('PATH', '/usr/bin:/bin')
    monkeypatch.setenv('HOME', str(tmp_path))
    binary = (
        tmp_path
        / '.vscode-server'
        / 'extensions'
        / 'openai.chatgpt-26.304.20706-linux-arm64'
        / 'bin'
        / 'linux-aarch64'
        / 'codex'
    )
    binary.parent.mkdir(parents=True)
    binary.write_text('#!/bin/sh\nexit 0\n')
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)

    assert resolve_agent_cli_executable('codex') == str(binary)


def test_list_agent_backends_marks_fallback_codex_as_available_and_authenticated(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv('CODEX_EXECUTABLE', raising=False)
    monkeypatch.delenv('CLAUDE_EXECUTABLE', raising=False)
    monkeypatch.setenv('PATH', '/usr/bin:/bin')
    monkeypatch.setenv('HOME', str(tmp_path))

    codex_binary = (
        tmp_path
        / '.vscode-server'
        / 'extensions'
        / 'openai.chatgpt-26.304.20706-linux-arm64'
        / 'bin'
        / 'linux-aarch64'
        / 'codex'
    )
    codex_binary.parent.mkdir(parents=True)
    codex_binary.write_text('#!/bin/sh\nexit 0\n')
    codex_binary.chmod(codex_binary.stat().st_mode | stat.S_IXUSR)

    class Completed:
        def __init__(self, returncode: int, stdout: str = '', stderr: str = '') -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(command: list[str], **_: object) -> Completed:
        executable = Path(command[0]).name
        if executable == 'codex':
            return Completed(returncode=0, stdout='Logged in using ChatGPT\n')
        return Completed(
            returncode=0,
            stdout=json.dumps(
                {'loggedIn': True, 'authMethod': 'api_key', 'apiProvider': 'firstParty'}
            ),
        )

    monkeypatch.setattr('harness.agent_registry.subprocess.run', fake_run)

    backends = list_agent_backends(REPO_ROOT)
    codex_backend = next(backend for backend in backends if backend.key == 'codex')

    assert codex_backend.available is True
    assert codex_backend.authenticated is True
    assert codex_backend.command_preview is not None
