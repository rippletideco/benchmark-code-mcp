from __future__ import annotations

import io
import json
from pathlib import Path

from harness.codex_adapter import (
    build_codex_command,
    build_prompt,
    extract_user_change_paths,
    translate_codex_stream,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def make_request(condition: str) -> dict:
    if condition == 'condition_md':
        return {
            'condition': condition,
            'workspace_path': str(REPO_ROOT),
            'task': {'seed_user_changes_patch': None},
            'instruction_payload': {
                'prompt': 'Fix the task.',
                'instruction_bundle': [
                    {
                        'path': 'benchmark/instructions/condition_md/any_name.md',
                        'content': 'This repository is a Turborepo monorepo.',
                    }
                ],
            },
        }

    return {
        'condition': condition,
        'workspace_path': str(REPO_ROOT),
        'task': {'seed_user_changes_patch': 'benchmark/fixtures/user_changes/orders_export_user_note.patch'},
        'instruction_payload': {
            'prompt': 'Fix the task.',
            'mcp_json_bundle': [
                {
                    'path': 'benchmark/instructions/condition_mcp/context.json',
                    'content': {'condition': 'condition_mcp'},
                }
            ],
            'mcp_server_config': {
                'mcpServers': {
                    'example_server': {
                        'type': 'http',
                        'url': 'https://example.com/mcp?agentId=test',
                    }
                }
            },
        },
    }


def test_build_prompt_uses_markdown_bundle_for_md_condition() -> None:
    prompt = build_prompt(make_request('condition_md'))
    assert 'markdown-only benchmark condition' in prompt
    assert 'This repository is a Turborepo monorepo.' in prompt


def test_build_command_includes_mcp_server_for_mcp_condition() -> None:
    command = build_codex_command(make_request('condition_mcp'))
    joined = ' '.join(command)
    assert 'mcp_servers={}' in joined
    assert 'mcp_servers.example_server.url="https://example.com/mcp?agentId=test"' in joined
    assert 'mcp_servers.example_server.enabled=true' in joined


def test_build_command_uses_resolved_codex_executable(monkeypatch) -> None:
    monkeypatch.setattr(
        'harness.codex_adapter.resolve_agent_cli_executable',
        lambda name: '/opt/openai/bin/codex' if name == 'codex' else None,
    )

    command = build_codex_command(make_request('condition_md'))

    assert command[0] == '/opt/openai/bin/codex'


def test_extract_user_change_paths_reads_seed_patch() -> None:
    request_path = REPO_ROOT / 'benchmark' / 'reports' / 'runs' / 'fake' / 'run_request.json'
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(make_request('condition_mcp')))
    paths = extract_user_change_paths(make_request('condition_mcp'), request_path)
    assert 'web/src/features/orders/OrdersPage.tsx' in paths


class FakeProcess:
    def __init__(self, stdout_lines: list[str], stderr_text: str = '') -> None:
        self.stdout = io.StringIO('\n'.join(stdout_lines) + '\n')
        self.stderr = io.StringIO(stderr_text)


def test_translate_codex_stream_maps_events() -> None:
    stream = io.StringIO()
    process = FakeProcess(
        [
            json.dumps({'type': 'thread.started', 'thread_id': 't1'}),
            json.dumps({'type': 'turn.started'}),
            json.dumps({'type': 'item.completed', 'item': {'id': '1', 'type': 'agent_message', 'text': 'Checking repo'}}),
            json.dumps({'type': 'item.started', 'item': {'id': '2', 'type': 'command_execution', 'command': "/bin/zsh -lc 'cat package.json'", 'status': 'in_progress'}}),
            json.dumps({'type': 'item.completed', 'item': {'id': '2', 'type': 'command_execution', 'command': "/bin/zsh -lc 'cat package.json'", 'aggregated_output': '{}', 'exit_code': 0, 'status': 'completed'}}),
            json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 1, 'output_tokens': 1}}),
        ]
    )

    final_message, saw_turn_completed, stderr_output = translate_codex_stream(
        process, REPO_ROOT, make_request('condition_md'), stream
    )
    events = [json.loads(line) for line in stream.getvalue().splitlines()]

    assert saw_turn_completed is True
    assert final_message == 'Checking repo'
    assert stderr_output == ''
    assert any(event['event_type'] == 'shell_command' for event in events)
    assert any(event['event_type'] == 'file_read' for event in events)
    assert any(event['event_type'] == 'shell_output' for event in events)
