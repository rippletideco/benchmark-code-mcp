import io
import time
from pathlib import Path

from fastapi.testclient import TestClient

from harness.server.app import create_app


def _create_pytest_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / 'api-sample-repo'
    repo_root.mkdir()
    (repo_root / 'pyproject.toml').write_text(
        '[project]\nname = "api-sample-repo"\nversion = "0.1.0"\n\n'
        '[tool.pytest.ini_options]\npythonpath = ["."]\n'
    )
    return repo_root


def test_server_creates_run_and_exports_bundle(tmp_path: Path) -> None:
    repo_root = _create_pytest_repo(tmp_path)
    client = TestClient(create_app())

    agents_response = client.get('/api/agents')
    assert agents_response.status_code == 200
    assert agents_response.json()['default_external_agent'] == 'codex'
    profiles_response = client.get('/api/profiles')
    assert profiles_response.status_code == 200
    assert any(profile['id'] == 'anthropic-demo' for profile in profiles_response.json()['profiles'])

    response = client.post(
        '/api/runs',
        data={
            'repo_path': str(repo_root),
            'mcp_json': '{"mcpServers":{"rippletide":{"type":"http","url":"https://mcp.example.test"}}}',
            'runner_kind': 'demo',
            'agent_backend': 'codex',
            'max_workers': '2',
        },
        files=[
            (
                'instruction_files',
                (
                    'AGENTS.md',
                    io.BytesIO(b'Validate before concluding.\nNever overwrite user changes.\n'),
                    'text/markdown',
                ),
            )
        ],
    )
    assert response.status_code == 200
    run_id = response.json()['run_id']

    status = 'queued'
    deadline = time.time() + 120
    final_payload = {}
    while time.time() < deadline:
        final_payload = client.get(f'/api/runs/{run_id}').json()
        status = final_payload['status']
        if status in {'completed', 'failed'}:
            break
        time.sleep(0.2)

    assert status == 'completed', final_payload
    assert final_payload['summary']['runnable_task_count'] >= 1
    assert final_payload['summary']['inputs']['agent_backend'] == 'codex'

    export_response = client.get(f'/api/runs/{run_id}/export')
    assert export_response.status_code == 200
    assert export_response.headers['content-type'] == 'application/zip'


def test_server_can_run_against_the_included_repo_without_repo_path() -> None:
    client = TestClient(create_app())

    response = client.post(
        '/api/runs',
        data={
            'runner_kind': 'demo',
            'agent_backend': 'codex',
            'mcp_json': '{}',
            'max_workers': '2',
        },
    )
    assert response.status_code == 200
    run_id = response.json()['run_id']

    deadline = time.time() + 120
    final_payload = {}
    while time.time() < deadline:
        final_payload = client.get(f'/api/runs/{run_id}').json()
        if final_payload['status'] in {'completed', 'failed'}:
            break
        time.sleep(0.2)

    assert final_payload['status'] == 'completed', final_payload
    assert final_payload['summary']['source_root']


def test_server_can_load_and_run_a_profile() -> None:
    client = TestClient(create_app())

    profile_response = client.get('/api/profiles/anthropic-demo')
    assert profile_response.status_code == 200
    assert profile_response.json()['id'] == 'anthropic-demo'
    assert profile_response.json()['execution_preset'] == 'claude'

    response = client.post('/api/profiles/quick-demo/run')
    assert response.status_code == 200
    run_id = response.json()['run_id']

    deadline = time.time() + 120
    final_payload = {}
    while time.time() < deadline:
        final_payload = client.get(f'/api/runs/{run_id}').json()
        if final_payload['status'] in {'completed', 'failed'}:
            break
        time.sleep(0.2)

    assert final_payload['status'] == 'completed', final_payload
    assert final_payload['summary']['inputs']['profile_id'] == 'quick-demo'
