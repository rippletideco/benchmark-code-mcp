from __future__ import annotations

import json
from pathlib import Path

from harness.profiles import (
    BenchmarkProfile,
    InstructionSourceConfig,
    McpSourceConfig,
    build_command_mcp_source,
    build_file_mcp_source,
    build_inline_mcp_source,
    execution_preset_to_runtime,
    list_profiles,
    load_profile,
    resolve_instruction_sources,
    resolve_mcp_source,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_profiles_are_discoverable_from_repo() -> None:
    profiles = list_profiles(REPO_ROOT)
    profile_ids = {profile.id for profile in profiles}

    assert {'quick-demo', 'anthropic-demo'} <= profile_ids


def test_load_profile_reads_committed_profile() -> None:
    profile = load_profile(REPO_ROOT, 'anthropic-demo')

    assert profile.execution_preset == 'claude'
    assert profile.mcp_source.type == 'file'
    assert profile.instruction_sources


def test_resolve_instruction_sources_supports_repo_file_and_inline() -> None:
    profile = BenchmarkProfile(
        id='test',
        name='Test',
        description='Test profile',
        target_mode='included',
        execution_preset='demo',
        instruction_sources=[],
        mcp_source=McpSourceConfig(type='inline', content={}),
        max_workers=1,
    )
    profile.instruction_sources = [
        InstructionSourceConfig(
            type='repo_file',
            path='benchmark/profiles/prompts/studio-default.md',
            label='Default',
        ),
        InstructionSourceConfig(
            type='inline',
            content='Never overwrite user changes.',
            label='Inline',
        ),
    ]

    prompt_sources, metadata = resolve_instruction_sources(
        profile.instruction_sources,
        benchmark_root=REPO_ROOT,
    )

    assert len(prompt_sources) == 2
    assert any(item['type'] == 'repo_file' for item in metadata)
    assert any(source.source_kind == 'markdown' for source in prompt_sources)


def test_resolve_mcp_source_supports_inline_file_and_command(tmp_path: Path) -> None:
    inline = resolve_mcp_source(
        build_inline_mcp_source('{"mcpServers":{"inline":{"type":"http","url":"https://inline"}}}'),
        benchmark_root=REPO_ROOT,
        source_root=None,
    )
    file_path = tmp_path / 'source.json'
    file_path.write_text('{"mcpServers":{"file":{"type":"http","url":"https://file"}}}')
    file_source = resolve_mcp_source(
        build_file_mcp_source(str(file_path)),
        benchmark_root=REPO_ROOT,
        source_root=None,
    )
    command_source = resolve_mcp_source(
        build_command_mcp_source(
            "python3 - <<'PY'\nimport json\nprint(json.dumps({'mcpServers': {'command': {'type': 'http', 'url': 'https://command'}}}))\nPY"
        ),
        benchmark_root=REPO_ROOT,
        source_root=None,
    )

    assert 'inline' in inline.raw_config['mcpServers']
    assert 'file' in file_source.raw_config['mcpServers']
    assert 'command' in command_source.raw_config['mcpServers']


def test_execution_preset_maps_to_runtime() -> None:
    assert execution_preset_to_runtime('demo') == ('demo', 'codex')
    assert execution_preset_to_runtime('codex') == ('external', 'codex')
    assert execution_preset_to_runtime('claude') == ('external', 'claude')
