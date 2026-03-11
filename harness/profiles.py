from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Literal

from .compiler.instruction_compiler import load_prompt_sources
from .studio_models import PromptSource

ExecutionPreset = Literal['demo', 'codex', 'claude', 'custom']
TargetMode = Literal['included', 'custom']
InstructionSourceType = Literal['repo_file', 'inline']
McpSourceType = Literal['inline', 'file', 'command']


@dataclass(slots=True)
class InstructionSourceConfig:
    type: InstructionSourceType
    path: str | None = None
    content: str | None = None
    label: str | None = None


@dataclass(slots=True)
class McpSourceConfig:
    type: McpSourceType
    content: dict[str, Any] | str | None = None
    path: str | None = None
    command: str | None = None


@dataclass(slots=True)
class BenchmarkProfile:
    id: str
    name: str
    description: str
    target_mode: TargetMode
    execution_preset: ExecutionPreset
    instruction_sources: list[InstructionSourceConfig]
    mcp_source: McpSourceConfig
    max_workers: int
    default_repo_path: str | None = None
    tags: list[str] = field(default_factory=list)
    demo_rank: int = 0


@dataclass(slots=True)
class ResolvedMcpSource:
    type: McpSourceType
    raw_config: dict[str, Any]
    provenance: dict[str, Any]
    stderr: str = ''


def profiles_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: profiles_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: profiles_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [profiles_jsonable(item) for item in value]
    return value


def list_profiles(benchmark_root: Path) -> list[BenchmarkProfile]:
    profiles: list[BenchmarkProfile] = []
    for path in sorted((benchmark_root / 'benchmark' / 'profiles').glob('*.json')):
        profiles.append(load_profile(benchmark_root, path.stem))
    return sorted(profiles, key=lambda item: (-item.demo_rank, item.name.lower()))


def load_profile(benchmark_root: Path, profile_id: str) -> BenchmarkProfile:
    profile_path = benchmark_root / 'benchmark' / 'profiles' / f'{profile_id}.json'
    if not profile_path.exists():
        raise FileNotFoundError(f'Unknown benchmark profile: {profile_id}')
    payload = json.loads(profile_path.read_text())
    return BenchmarkProfile(
        id=str(payload['id']),
        name=str(payload['name']),
        description=str(payload['description']),
        target_mode=str(payload['target_mode']),
        execution_preset=str(payload['execution_preset']),
        instruction_sources=[
            InstructionSourceConfig(
                type=str(item['type']),
                path=item.get('path'),
                content=item.get('content'),
                label=item.get('label'),
            )
            for item in payload.get('instruction_sources', [])
        ],
        mcp_source=McpSourceConfig(
            type=str(payload['mcp_source']['type']),
            content=payload['mcp_source'].get('content'),
            path=payload['mcp_source'].get('path'),
            command=payload['mcp_source'].get('command'),
        ),
        max_workers=int(payload.get('max_workers', 4)),
        default_repo_path=payload.get('default_repo_path'),
        tags=[str(item) for item in payload.get('tags', [])],
        demo_rank=int(payload.get('demo_rank', 0)),
    )


def execution_preset_to_runtime(
    preset: ExecutionPreset,
) -> tuple[Literal['demo', 'external'], Literal['codex', 'claude', 'custom']]:
    if preset == 'demo':
        return ('demo', 'codex')
    if preset == 'claude':
        return ('external', 'claude')
    if preset == 'custom':
        return ('external', 'custom')
    return ('external', 'codex')


def resolve_instruction_sources(
    config_items: list[InstructionSourceConfig],
    *,
    benchmark_root: Path,
) -> tuple[list[PromptSource], list[dict[str, Any]]]:
    prompt_sources: list[PromptSource] = []
    metadata: list[dict[str, Any]] = []
    repo_file_paths: list[Path] = []

    for item in config_items:
        if item.type == 'repo_file':
            if not item.path:
                raise ValueError('Instruction source `repo_file` requires `path`.')
            resolved_path = _resolve_path(item.path, benchmark_root, None)
            repo_file_paths.append(resolved_path)
            metadata.append(
                {
                    'type': item.type,
                    'label': item.label or resolved_path.name,
                    'origin': str(resolved_path),
                }
            )
            continue

        if item.type == 'inline':
            prompt_sources.append(
                PromptSource(
                    path=item.label or 'INLINE_INSTRUCTION.md',
                    content=item.content or '',
                    source_kind='markdown',
                )
            )
            metadata.append(
                {
                    'type': item.type,
                    'label': item.label or 'Inline instruction',
                    'origin': 'inline',
                }
            )
            continue

        raise ValueError(f'Unsupported instruction source type: {item.type}')

    if repo_file_paths:
        prompt_sources = [*prompt_sources, *load_prompt_sources(repo_file_paths)]

    return prompt_sources, metadata


def resolve_mcp_source(
    config: McpSourceConfig,
    *,
    benchmark_root: Path,
    source_root: Path | None,
) -> ResolvedMcpSource:
    if config.type == 'inline':
        raw = config.content if isinstance(config.content, dict) else json.loads(str(config.content or '{}'))
        return ResolvedMcpSource(
            type='inline',
            raw_config=raw,
            provenance={'origin': 'inline'},
        )

    if config.type == 'file':
        if not config.path:
            raise ValueError('MCP source `file` requires `path`.')
        resolved_path = _resolve_path(config.path, benchmark_root, source_root)
        return ResolvedMcpSource(
            type='file',
            raw_config=json.loads(resolved_path.read_text()),
            provenance={'origin': str(resolved_path)},
        )

    if config.type == 'command':
        if not config.command:
            raise ValueError('MCP source `command` requires `command`.')
        completed = subprocess.run(
            config.command,
            cwd=benchmark_root,
            text=True,
            capture_output=True,
            shell=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f'MCP command failed with exit code {completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}'
            )
        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError('MCP command did not return valid JSON.') from exc
        return ResolvedMcpSource(
            type='command',
            raw_config=raw,
            provenance={'origin': config.command},
            stderr=completed.stderr,
        )

    raise ValueError(f'Unsupported MCP source type: {config.type}')


def build_inline_mcp_source(content: str) -> McpSourceConfig:
    return McpSourceConfig(type='inline', content=content)


def build_file_mcp_source(path: str) -> McpSourceConfig:
    return McpSourceConfig(type='file', path=path)


def build_command_mcp_source(command: str) -> McpSourceConfig:
    return McpSourceConfig(type='command', command=command)


def build_profile_payload(profile: BenchmarkProfile, proof_run: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = profiles_jsonable(profile)
    payload['proof_run'] = proof_run
    return payload


def _resolve_path(candidate: str, benchmark_root: Path, source_root: Path | None) -> Path:
    raw = Path(candidate).expanduser()
    if raw.is_absolute():
        return raw.resolve()

    search_roots = [benchmark_root]
    if source_root is not None:
        search_roots.insert(0, source_root)

    for base in search_roots:
        resolved = (base / raw).resolve()
        if resolved.exists():
            return resolved

    return (search_roots[0] / raw).resolve()
