from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import TextIO

from .adapter_common import (
    build_prompt,
    emit,
    emit_final_file_writes,
    emit_tool_command,
    emit_tool_result,
    extract_user_change_paths,
    load_request,
)
from .executable_resolver import resolve_agent_cli_executable


def _format_config_key(prefix: str, key: str, field: str) -> str:
    if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key):
        return f'{prefix}.{key}.{field}'
    return f'{prefix}."{key}".{field}'


def build_codex_command(request: dict) -> list[str]:
    workspace_path = request['workspace_path']
    executable = resolve_agent_cli_executable('codex') or 'codex'
    command = [
        executable,
        'exec',
        '--json',
        '--ephemeral',
        '--sandbox',
        'workspace-write',
        '-C',
        workspace_path,
        '-c',
        'features.multi_agent=false',
        '-c',
        'features.child_agents_md=false',
        '-c',
        'features.memory_tool=false',
        '-c',
        'features.apps_mcp_gateway=false',
        '-c',
        'features.sqlite=false',
        '-c',
        'suppress_unstable_features_warning=true',
        '-c',
        'mcp_servers={}',
    ]

    if request['condition'] == 'condition_mcp':
        server_config = request['instruction_payload'].get('mcp_server_config') or {}
        for server_name, server_definition in server_config.get('mcpServers', {}).items():
            url = server_definition.get('url')
            bearer_token_env_var = server_definition.get('bearerTokenEnvVar')
            if url:
                command.extend(
                    ['-c', f'{_format_config_key("mcp_servers", server_name, "url")}="{url}"']
                )
                command.extend(
                    ['-c', f'{_format_config_key("mcp_servers", server_name, "enabled")}=true']
                )
            if bearer_token_env_var:
                command.extend(
                    [
                        '-c',
                        (
                            f'{_format_config_key("mcp_servers", server_name, "bearer_token_env_var")}'
                            f'="{bearer_token_env_var}"'
                        ),
                    ]
                )

    command.append('-')
    return command


def translate_codex_stream(
    process: subprocess.Popen[str],
    workspace_path: Path,
    request: dict,
    stream: TextIO,
) -> tuple[str, bool, str]:
    last_agent_message = ''
    saw_turn_completed = False

    assert process.stdout is not None
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = payload.get('type')
        if event_type == 'turn.completed':
            saw_turn_completed = True
            continue
        if event_type in {'thread.started', 'turn.started'}:
            continue
        if event_type not in {'item.started', 'item.completed'}:
            continue

        item = payload.get('item', {})
        item_type = item.get('type')
        is_started = event_type == 'item.started'

        if item_type == 'error':
            continue

        if item_type in {'agent_message', 'reasoning'} and not is_started:
            text = item.get('text', '')
            if text:
                last_agent_message = text
                emit(
                    'agent_message',
                    {'role': 'assistant' if item_type == 'agent_message' else 'reasoning', 'content': text},
                    stream,
                )
            continue

        if item_type == 'command_execution':
            command = item.get('command', '')
            if is_started:
                emit_tool_command(command, workspace_path, stream)
            else:
                emit_tool_result(
                    command,
                    status=item.get('status'),
                    exit_code=item.get('exit_code'),
                    stdout=item.get('aggregated_output', ''),
                    stderr='',
                    stream=stream,
                )
            continue

        if item_type == 'collab_tool_call':
            tool_payload = {
                'tool': item.get('tool'),
                'status': item.get('status'),
                'prompt': item.get('prompt'),
                'receiver_thread_ids': item.get('receiver_thread_ids', []),
            }
            emit('tool_call' if is_started else 'tool_result', tool_payload, stream)

    stderr_output = ''
    if process.stderr is not None:
        stderr_output = process.stderr.read()

    return last_agent_message, saw_turn_completed, stderr_output


def run_adapter(request_path: Path, stream: TextIO = sys.stdout) -> int:
    request = load_request(request_path)
    workspace_path = Path(request['workspace_path'])
    seed_user_change_paths = extract_user_change_paths(request, request_path)

    codex_command = build_codex_command(request)
    prompt = build_prompt(request)
    process = subprocess.Popen(
        codex_command,
        cwd=workspace_path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None
    process.stdin.write(prompt)
    process.stdin.close()

    final_message, saw_turn_completed, stderr_output = translate_codex_stream(
        process,
        workspace_path,
        request,
        stream,
    )
    return_code = process.wait()
    emit_final_file_writes(workspace_path, seed_user_change_paths, stream)
    emit(
        'run_finished',
        {
            'status': 'completed' if return_code == 0 and saw_turn_completed else 'failed',
            'final_message': final_message or 'Codex run completed.',
            'adapter': 'codex',
            'stderr': stderr_output,
        },
        stream,
    )
    return return_code
