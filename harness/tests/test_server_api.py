import io
import time
from pathlib import Path

import pytest
from fastapi import UploadFile

from harness.agent_registry import AgentBackendStatus
from harness.compiler.instruction_compiler import InstructionCompiler
from harness.server.service import StudioRunManager
from harness.server import service as service_module


REPO_ROOT = Path(__file__).resolve().parents[2]


def _create_pytest_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / 'api-sample-repo'
    repo_root.mkdir()
    (repo_root / 'pyproject.toml').write_text(
        '[project]\nname = "api-sample-repo"\nversion = "0.1.0"\n\n'
        '[tool.pytest.ini_options]\npythonpath = ["."]\n'
    )
    return repo_root


@pytest.fixture(autouse=True)
def _disable_live_codex_instruction_extraction(monkeypatch) -> None:
    monkeypatch.setattr(InstructionCompiler, "_extract_with_codex", lambda self, sources, repo_root: None)
    monkeypatch.setattr(
        service_module,
        "list_agent_backends",
        lambda benchmark_root: [
            AgentBackendStatus(
                key="codex",
                label="Codex",
                description="OpenAI Codex CLI benchmark adapter.",
                available=True,
                authenticated=True,
                default_for_external=True,
                command_preview=None,
                auth_message="Default external agent.",
            ),
            AgentBackendStatus(
                key="claude",
                label="Claude Code",
                description="Anthropic Claude Code CLI benchmark adapter.",
                available=True,
                authenticated=True,
                default_for_external=False,
                command_preview=None,
                auth_message="Claude Code detected.",
            ),
            AgentBackendStatus(
                key="custom",
                label="Custom command",
                description="Use any external adapter command that implements the benchmark NDJSON contract.",
                available=True,
                authenticated=False,
                default_for_external=False,
                command_preview=None,
                auth_message="Provide a full adapter command.",
                requires_custom_command=True,
            ),
        ],
    )


def _create_benchmark_run(
    manager: StudioRunManager,
    *,
    profile_id: str | None,
    repo_path: str | None,
    instruction_text: bytes | None,
    mcp_json: str,
    runner_kind: str,
    agent_backend: str,
) -> str:
    instruction_files = []
    if instruction_text is not None:
        instruction_files.append(
            UploadFile(file=io.BytesIO(instruction_text), filename='AGENTS.md')
        )

    state = manager.create_benchmark_run(
        profile_id=profile_id,
        repo_path=repo_path,
        repo_archive=None,
        instruction_files=instruction_files,
        mcp_json=mcp_json,
        mcp_source_type=None,
        mcp_source_path=None,
        mcp_source_command=None,
        runner_kind=runner_kind,
        agent_backend=agent_backend,
        adapter_command=None,
        max_workers=2,
        confirmed_to_continue=True,
    )
    return state.run_id


def _wait_for_run(manager: StudioRunManager, run_id: str) -> dict:
    deadline = time.time() + 120
    final_payload = {}
    while time.time() < deadline:
        state = manager.get_state(run_id)
        assert state is not None
        final_payload = {
            'status': state.status,
            'summary': state.summary,
            'error': state.error,
        }
        if state.status in {'completed', 'failed'}:
            break
        time.sleep(0.2)
    return final_payload


def test_server_creates_run_and_exports_bundle(tmp_path: Path) -> None:
    repo_root = _create_pytest_repo(tmp_path)
    manager = StudioRunManager(REPO_ROOT)

    agents = manager.list_agents()
    assert any(agent['key'] == 'codex' and agent['default_for_external'] for agent in agents)
    profiles = manager.list_profiles()
    assert any(profile['id'] == 'anthropic-demo' for profile in profiles)

    run_id = _create_benchmark_run(
        manager,
        profile_id=None,
        repo_path=str(repo_root),
        instruction_text=b'Validate before concluding.\nNever overwrite user changes.\n',
        mcp_json='{"mcpServers":{"rippletide":{"type":"http","url":"https://mcp.example.test"}}}',
        runner_kind='demo',
        agent_backend='codex',
    )
    final_payload = _wait_for_run(manager, run_id)
    assert final_payload['status'] == 'completed', final_payload
    assert final_payload['summary']['runnable_task_count'] >= 1
    assert final_payload['summary']['inputs']['agent_backend'] == 'codex'
    report_path = REPO_ROOT / 'benchmark' / 'reports' / 'studio_runs' / run_id / 'benchmark_report.md'
    assert report_path.exists()

    export_path = manager.export_run(run_id)
    assert export_path.exists()
    assert export_path.suffix == '.zip'


def test_server_can_run_against_the_included_repo_without_repo_path() -> None:
    manager = StudioRunManager(REPO_ROOT)

    run_id = _create_benchmark_run(
        manager,
        profile_id=None,
        repo_path=None,
        instruction_text=None,
        mcp_json='{}',
        runner_kind='demo',
        agent_backend='codex',
    )

    final_payload = _wait_for_run(manager, run_id)

    assert final_payload['status'] == 'completed', final_payload
    assert final_payload['summary']['source_root']
    assert (REPO_ROOT / 'benchmark' / 'reports' / 'studio_runs' / run_id / 'benchmark_report.md').exists()


def test_server_can_load_and_run_a_profile() -> None:
    manager = StudioRunManager(REPO_ROOT)

    profile_payload = manager.get_profile('anthropic-demo')
    assert profile_payload is not None
    assert profile_payload['id'] == 'anthropic-demo'
    assert profile_payload['execution_preset'] == 'claude'

    run_id = _create_benchmark_run(
        manager,
        profile_id='quick-demo',
        repo_path=None,
        instruction_text=None,
        mcp_json='{}',
        runner_kind='demo',
        agent_backend='codex',
    )

    final_payload = _wait_for_run(manager, run_id)

    assert final_payload['status'] == 'completed', final_payload
    assert final_payload['summary']['inputs']['profile_id'] == 'quick-demo'
    assert (REPO_ROOT / 'benchmark' / 'reports' / 'studio_runs' / run_id / 'benchmark_report.md').exists()


def test_benchmark_endpoint_materializes_bundle_files(tmp_path: Path) -> None:
    repo_root = _create_pytest_repo(tmp_path)
    manager = StudioRunManager(REPO_ROOT)

    run_id = _create_benchmark_run(
        manager,
        profile_id=None,
        repo_path=str(repo_root),
        instruction_text=b'Validate before concluding.\n',
        mcp_json='{"mcpServers":{"local_demo":{"type":"inline","tools":[{"name":"validate before concluding"}]}}}',
        runner_kind='demo',
        agent_backend='codex',
    )

    final_payload = _wait_for_run(manager, run_id)

    assert final_payload['status'] == 'completed', final_payload
    run_root = REPO_ROOT / 'benchmark' / 'reports' / 'studio_runs' / run_id
    for path in (
        run_root / 'bundle' / 'normalized_rules.json',
        run_root / 'bundle' / 'mcp_manifest.json',
        run_root / 'bundle' / 'alignment.json',
        run_root / 'bundle' / 'generated_tasks.json',
    ):
        assert path.exists(), path
    assert (run_root / 'benchmark_report.md').exists()
