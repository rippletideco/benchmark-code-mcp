from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi import UploadFile

from harness.compiler.instruction_compiler import InstructionCompiler
from harness.server.service import StudioRunManager


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _disable_live_codex_instruction_extraction(monkeypatch) -> None:
    monkeypatch.setattr(InstructionCompiler, "_extract_with_codex", lambda self, sources, repo_root: None)


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _fake_codex_binary(path: Path) -> None:
    _write_executable(
        path,
        """#!/usr/bin/env python3
import json
import sys

_ = sys.stdin.read()
print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "codex ok"}}))
print(json.dumps({"type": "turn.completed"}))
""",
    )


def _fake_claude_binary(path: Path) -> None:
    _write_executable(
        path,
        """#!/usr/bin/env python3
import json
import sys

_ = sys.stdin.read()
print(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "claude ok"}]}}))
print(json.dumps({"type": "result", "subtype": "success", "result": "claude ok"}))
""",
    )


def _write_run_request(
    tmp_path: Path,
    *,
    cli_name: str,
    condition: str = "condition_md",
) -> Path:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()

    request_path = tmp_path / "run_request.json"
    request_path.write_text(
        json.dumps(
            {
                "workspace_path": str(workspace_path),
                "condition": condition,
                "instruction_payload": {
                    "prompt": "Fix the generated helper.",
                    "instruction_bundle": [
                        {"path": "AGENTS.md", "content": "Always validate the smallest relevant change."}
                    ],
                    "mcp_json_bundle": [{"path": "inline-mcp.json", "content": "{}"}],
                    "mcp_server_config": {},
                },
                "task": {"seed_user_changes_patch": None},
                "runner_kind": "external",
                "adapter_command": f"python3 scripts/adapter_{cli_name}.py {{request_file}}",
            }
        )
    )
    return request_path


def _run_entrypoint(
    tmp_path: Path,
    *,
    cli_name: str,
    binary_factory,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    binary_factory(bin_dir / cli_name)
    request_path = _write_run_request(tmp_path, cli_name=cli_name)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env.pop("PYTHONPATH", None)

    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / f"adapter_{cli_name}.py"), str(request_path)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _create_pytest_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "api-sample-repo"
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text(
        '[project]\nname = "api-sample-repo"\nversion = "0.1.0"\n\n'
        '[tool.pytest.ini_options]\npythonpath = ["."]\n'
    )
    return repo_root


def test_codex_adapter_entrypoint_runs_outside_repo_root(tmp_path: Path) -> None:
    completed = _run_entrypoint(tmp_path, cli_name="codex", binary_factory=_fake_codex_binary)

    assert completed.returncode == 0, completed.stderr
    events = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    assert events[-1]["event_type"] == "run_finished"
    assert events[-1]["payload"]["status"] == "completed"
    assert "ModuleNotFoundError" not in completed.stderr


def test_claude_adapter_entrypoint_runs_outside_repo_root(tmp_path: Path) -> None:
    completed = _run_entrypoint(tmp_path, cli_name="claude", binary_factory=_fake_claude_binary)

    assert completed.returncode == 0, completed.stderr
    events = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    assert events[-1]["event_type"] == "run_finished"
    assert events[-1]["payload"]["status"] == "completed"
    assert "ModuleNotFoundError" not in completed.stderr


def test_server_external_codex_run_uses_adapter_script(tmp_path: Path, monkeypatch) -> None:
    repo_root = _create_pytest_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_codex_binary(bin_dir / "codex")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    manager = StudioRunManager(REPO_ROOT)
    state = manager.create_benchmark_run(
        profile_id=None,
        repo_path=str(repo_root),
        repo_archive=None,
        instruction_files=[
            UploadFile(
                file=io.BytesIO(b"Validate before concluding.\nNever overwrite user changes.\n"),
                filename="AGENTS.md",
            )
        ],
        mcp_json='{"mcpServers":{"rippletide":{"type":"http","url":"https://mcp.example.test"}}}',
        mcp_source_type=None,
        mcp_source_path=None,
        mcp_source_command=None,
        runner_kind="external",
        agent_backend="codex",
        adapter_command=None,
        max_workers=2,
        confirmed_to_continue=True,
    )

    deadline = time.time() + 120
    while time.time() < deadline:
        current = manager.get_state(state.run_id)
        assert current is not None
        if current.status in {"completed", "failed"}:
            state = current
            break
        time.sleep(0.2)

    assert state.status == "completed", state.error
    assert state.summary["inputs"]["runner_kind"] == "external"
    assert state.summary["inputs"]["agent_backend"] == "codex"

    run_root = REPO_ROOT / "benchmark" / "reports" / "studio_runs" / state.run_id / "runs"
    events_files = sorted(run_root.glob("*/events.jsonl"))
    assert events_files
    sample_events = [json.loads(line) for line in events_files[0].read_text().splitlines() if line.strip()]
    run_finished = [event for event in sample_events if event["event_type"] == "run_finished"][-1]
    assert run_finished["payload"]["final_message"] != "External adapter ended without an explicit run_finished event."
