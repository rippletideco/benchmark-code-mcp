from __future__ import annotations

import json
import shutil
import threading
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from ..agent_registry import list_agent_backends, resolve_external_adapter_command, serialize_agent_backends
from ..alignment import McpManifestCompiler, RuleAlignmentEngine
from ..compiler.instruction_compiler import InstructionCompiler, load_prompt_sources
from ..engine import execute_task_matrix
from ..logging import utc_now_iso
from ..profiles import (
    BenchmarkProfile,
    InstructionSourceConfig,
    McpSourceConfig,
    build_command_mcp_source,
    build_file_mcp_source,
    build_inline_mcp_source,
    build_profile_payload,
    execution_preset_to_runtime,
    list_profiles,
    load_profile,
    profiles_jsonable,
    resolve_instruction_sources,
    resolve_mcp_source,
)
from ..studio import build_dynamic_bundle, probe_repo_capabilities
from ..studio_models import DynamicRunBundle, studio_jsonable


@dataclass(slots=True)
class StudioRunState:
    run_id: str
    root: Path
    status: str = 'queued'
    error: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    bundle: DynamicRunBundle | None = None


@dataclass(slots=True)
class UploadedBlob:
    filename: str
    content: bytes


class StudioRunManager:
    def __init__(self, benchmark_root: Path) -> None:
        self.benchmark_root = benchmark_root
        self.runs_root = benchmark_root / 'benchmark' / 'reports' / 'studio_runs'
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self._states: dict[str, StudioRunState] = {}
        self._lock = threading.Lock()

    def create_run(
        self,
        *,
        profile_id: str | None,
        repo_path: str | None,
        repo_archive: UploadFile | None,
        instruction_files: list[UploadFile],
        mcp_json: str,
        mcp_source_type: str | None,
        mcp_source_path: str | None,
        mcp_source_command: str | None,
        runner_kind: str,
        agent_backend: str,
        adapter_command: str | None,
        max_workers: int,
    ) -> StudioRunState:
        run_id = uuid.uuid4().hex[:12]
        run_root = self.runs_root / run_id
        run_root.mkdir(parents=True, exist_ok=True)
        state = StudioRunState(run_id=run_id, root=run_root)
        with self._lock:
            self._states[run_id] = state

        archive_blob = None
        if repo_archive is not None:
            archive_blob = UploadedBlob(
                filename=repo_archive.filename or 'repository.zip',
                content=repo_archive.file.read(),
            )
        instruction_blobs = [
            UploadedBlob(
                filename=upload.filename or f'instruction-{index}.md',
                content=upload.file.read(),
            )
            for index, upload in enumerate(instruction_files, start=1)
        ]

        thread = threading.Thread(
            target=self._run_job,
            kwargs={
                'state': state,
                'profile_id': profile_id,
                'repo_path': repo_path,
                'repo_archive': archive_blob,
                'instruction_files': instruction_blobs,
                'mcp_json': mcp_json,
                'mcp_source_type': mcp_source_type,
                'mcp_source_path': mcp_source_path,
                'mcp_source_command': mcp_source_command,
                'runner_kind': runner_kind,
                'agent_backend': agent_backend,
                'adapter_command': adapter_command,
                'max_workers': max_workers,
            },
            daemon=True,
        )
        thread.start()
        self._write_state(state)
        self._append_event(state, 'run_created', {'status': state.status})
        return state

    def get_state(self, run_id: str) -> StudioRunState | None:
        with self._lock:
            state = self._states.get(run_id)
            if state is not None:
                return state

        run_root = self.runs_root / run_id
        state_path = run_root / 'state.json'
        if not run_root.exists() or not state_path.exists():
            return None

        payload = json.loads(state_path.read_text())
        state = StudioRunState(
            run_id=run_id,
            root=run_root,
            status=payload.get('status', 'completed'),
            error=payload.get('error'),
            summary=payload.get('summary') or {},
        )
        with self._lock:
            self._states[run_id] = state
        return state

    def _run_job(
        self,
        *,
        state: StudioRunState,
        profile_id: str | None,
        repo_path: str | None,
        repo_archive: UploadedBlob | None,
        instruction_files: list[UploadedBlob],
        mcp_json: str,
        mcp_source_type: str | None,
        mcp_source_path: str | None,
        mcp_source_command: str | None,
        runner_kind: str,
        agent_backend: str,
        adapter_command: str | None,
        max_workers: int,
    ) -> None:
        try:
            profile = load_profile(self.benchmark_root, profile_id) if profile_id else None
            resolved_runner_kind, resolved_agent_backend = self._resolve_runtime(
                profile, runner_kind, agent_backend
            )
            resolved_adapter_command = adapter_command
            if resolved_runner_kind == 'external' and not resolved_adapter_command:
                resolved_adapter_command = resolve_external_adapter_command(
                    benchmark_root=self.benchmark_root,
                    agent_backend=resolved_agent_backend,
                    adapter_command=adapter_command,
                )

            self._set_status(state, 'preparing')
            source_root = self._resolve_source_root(
                state.root,
                repo_path,
                repo_archive,
                profile.default_repo_path if profile is not None else None,
            )
            self._append_event(state, 'source_ready', {'source_root': str(source_root)})

            prompt_sources, instruction_metadata = self._resolve_instruction_sources(
                state.root,
                source_root,
                instruction_files,
                profile,
            )
            compiled = InstructionCompiler().compile(prompt_sources, self.benchmark_root)
            self._append_event(
                state,
                'instructions_compiled',
                {'rule_count': len(compiled.rules), 'extraction_mode': compiled.extraction_mode},
            )

            resolved_mcp_source = self._resolve_mcp_source(
                profile=profile,
                source_root=source_root,
                mcp_json=mcp_json,
                mcp_source_type=mcp_source_type,
                mcp_source_path=mcp_source_path,
                mcp_source_command=mcp_source_command,
            )
            manifest = McpManifestCompiler().compile(resolved_mcp_source.raw_config)
            alignment = RuleAlignmentEngine().align(compiled, manifest)
            capabilities = probe_repo_capabilities(source_root)
            bundle = build_dynamic_bundle(
                bundle_root=state.root / 'bundle',
                source_root=source_root,
                inputs={
                    'profile_id': profile.id if profile is not None else None,
                    'profile_name': profile.name if profile is not None else None,
                    'repo_path': str(source_root),
                    'runner_kind': resolved_runner_kind,
                    'agent_backend': resolved_agent_backend,
                    'adapter_command': resolved_adapter_command,
                    'instruction_sources': instruction_metadata,
                    'mcp_source_type': resolved_mcp_source.type,
                    'mcp_source_origin': resolved_mcp_source.provenance.get('origin'),
                },
                compiled_instructions=compiled,
                mcp_manifest=manifest,
                alignment_issues=alignment,
                capabilities=capabilities,
            )
            state.bundle = bundle
            self._append_event(
                state,
                'bundle_ready',
                {
                    'supported_tasks': len([item for item in bundle.generated_tasks if item.task is not None]),
                    'alignment_issues': len(alignment),
                    'repo_supported': capabilities.supported,
                },
            )

            runnable_tasks = [item.task for item in bundle.generated_tasks if item.task is not None]
            if not runnable_tasks:
                state.summary = self._build_summary(bundle, [])
                self._set_status(state, 'completed')
                return

            self._set_status(state, 'running')
            run_items = []
            for generated in bundle.generated_tasks:
                if generated.task is None:
                    continue
                prompt_text = Path(generated.task.prompt_file).read_text()
                md_payload = {
                    'prompt': prompt_text,
                    'instruction_bundle': [
                        {'path': source.path, 'content': source.content}
                        for source in bundle.compiled_instructions.sources
                    ],
                }
                mcp_payload = {
                    'prompt': prompt_text,
                    'mcp_json_bundle': [{'path': 'uploaded_mcp.json', 'content': bundle.mcp_manifest.raw_config}],
                    'mcp_server_config': bundle.mcp_manifest.raw_config if bundle.mcp_manifest.raw_config.get('mcpServers') else None,
                }
                run_items.extend(
                    [
                        {
                            'task': generated.task,
                            'condition': 'condition_md',
                            'instruction_payload': md_payload,
                            'runner_kind': resolved_runner_kind,
                            'adapter_command': resolved_adapter_command,
                            'output_dir': state.root / 'runs' / f'{generated.task.task_id}-condition_md',
                            'protected_globs': generated.task.forbidden_files,
                            'allowed_scripts': set(bundle.capabilities.available_scripts),
                        },
                        {
                            'task': generated.task,
                            'condition': 'condition_mcp',
                            'instruction_payload': mcp_payload,
                            'runner_kind': resolved_runner_kind,
                            'adapter_command': resolved_adapter_command,
                            'output_dir': state.root / 'runs' / f'{generated.task.task_id}-condition_mcp',
                            'protected_globs': generated.task.forbidden_files,
                            'allowed_scripts': set(bundle.capabilities.available_scripts),
                        },
                    ]
                )

            summaries = execute_task_matrix(
                benchmark_root=self.benchmark_root,
                source_root=source_root,
                run_items=run_items,
                max_workers=max_workers,
                on_status=lambda event_type, payload: self._append_event(state, event_type, payload),
            )
            bundle.run_summaries = summaries
            state.summary = self._build_summary(bundle, summaries)
            (state.root / 'summary.json').write_text(json.dumps(state.summary, indent=2))
            self._set_status(state, 'completed')
        except Exception as exc:  # pragma: no cover - exercised via integration tests
            state.error = str(exc)
            self._append_event(state, 'run_failed', {'error': state.error})
            self._set_status(state, 'failed')

    def _resolve_source_root(
        self,
        run_root: Path,
        repo_path: str | None,
        repo_archive: UploadedBlob | None,
        default_repo_path: str | None,
    ) -> Path:
        if repo_path:
            candidate = Path(repo_path).expanduser().resolve()
            if not candidate.exists():
                raise FileNotFoundError(f'Repository path does not exist: {candidate}')
            return candidate

        if default_repo_path:
            candidate = Path(default_repo_path).expanduser().resolve()
            if not candidate.exists():
                raise FileNotFoundError(f'Default repository path does not exist: {candidate}')
            return candidate

        if repo_archive is None:
            return self.benchmark_root

        archive_dir = run_root / 'uploaded_repo'
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / repo_archive.filename
        archive_path.write_bytes(repo_archive.content)

        extract_dir = run_root / 'source'
        with zipfile.ZipFile(archive_path) as zip_handle:
            zip_handle.extractall(extract_dir)

        children = [path for path in extract_dir.iterdir() if path.is_dir()]
        if len(children) == 1:
            return children[0]
        return extract_dir

    def _materialize_instruction_files(
        self,
        run_root: Path,
        source_root: Path,
        instruction_files: list[UploadedBlob],
    ) -> list[Path]:
        materialized: list[Path] = []
        instructions_dir = run_root / 'instructions'
        instructions_dir.mkdir(parents=True, exist_ok=True)
        for upload in instruction_files:
            target = instructions_dir / upload.filename
            target.write_bytes(upload.content)
            materialized.append(target)

        if materialized:
            return materialized

        for candidate_name in ('AGENTS.md', 'CLAUDE.md'):
            candidate = source_root / candidate_name
            if candidate.exists():
                copied = instructions_dir / candidate.name
                copied.write_text(candidate.read_text())
                materialized.append(copied)

        if not materialized:
            fallback = instructions_dir / 'SYSTEM_PROMPT.md'
            fallback.write_text('Validate before concluding. Make the smallest safe change. Explore before editing.\n')
            materialized.append(fallback)
        return materialized

    def _resolve_instruction_sources(
        self,
        run_root: Path,
        source_root: Path,
        instruction_files: list[UploadedBlob],
        profile: BenchmarkProfile | None,
    ) -> tuple[list, list[dict[str, Any]]]:
        if instruction_files:
            paths = self._materialize_instruction_files(run_root, source_root, instruction_files)
            return load_prompt_sources(paths), [
                {'type': 'upload', 'origin': str(path), 'label': path.name} for path in paths
            ]

        if profile is not None and profile.instruction_sources:
            return resolve_instruction_sources(profile.instruction_sources, benchmark_root=self.benchmark_root)

        paths = self._materialize_instruction_files(run_root, source_root, [])
        return load_prompt_sources(paths), [
            {'type': 'auto', 'origin': str(path), 'label': path.name} for path in paths
        ]

    def _resolve_mcp_source(
        self,
        *,
        profile: BenchmarkProfile | None,
        source_root: Path,
        mcp_json: str,
        mcp_source_type: str | None,
        mcp_source_path: str | None,
        mcp_source_command: str | None,
    ):
        if mcp_source_type:
            source = self._build_mcp_source_from_request(
                mcp_json=mcp_json,
                mcp_source_type=mcp_source_type,
                mcp_source_path=mcp_source_path,
                mcp_source_command=mcp_source_command,
            )
        elif profile is not None:
            source = profile.mcp_source
        else:
            source = build_inline_mcp_source(mcp_json)

        return resolve_mcp_source(
            source,
            benchmark_root=self.benchmark_root,
            source_root=source_root,
        )

    def _build_mcp_source_from_request(
        self,
        *,
        mcp_json: str,
        mcp_source_type: str,
        mcp_source_path: str | None,
        mcp_source_command: str | None,
    ) -> McpSourceConfig:
        if mcp_source_type == 'file':
            if not mcp_source_path:
                raise ValueError('MCP source path is required for `file` mode.')
            return build_file_mcp_source(mcp_source_path)
        if mcp_source_type == 'command':
            if not mcp_source_command:
                raise ValueError('MCP source command is required for `command` mode.')
            return build_command_mcp_source(mcp_source_command)
        return build_inline_mcp_source(mcp_json)

    def _resolve_runtime(
        self,
        profile: BenchmarkProfile | None,
        runner_kind: str,
        agent_backend: str,
    ) -> tuple[str, str]:
        if profile is None:
            return runner_kind, agent_backend
        resolved_runner_kind, resolved_agent_backend = execution_preset_to_runtime(
            profile.execution_preset
        )
        return resolved_runner_kind, resolved_agent_backend

    def _build_summary(self, bundle: DynamicRunBundle, run_summaries: list[dict[str, Any]]) -> dict[str, Any]:
        summary = {
            'run_id': bundle.bundle_root.parent.name,
            'status': 'completed',
            'source_root': str(bundle.source_root),
            'inputs': bundle.inputs,
            'alignment': {
                'issue_count': len(bundle.alignment_issues),
                'by_status': self._group_alignment(bundle.alignment_issues),
            },
            'capabilities': studio_jsonable(bundle.capabilities),
            'generated_task_count': len(bundle.generated_tasks),
            'runnable_task_count': len([item for item in bundle.generated_tasks if item.task is not None]),
            'runs': run_summaries,
        }
        if run_summaries:
            summary['benchmark'] = {
                'average_score': round(
                    sum(item['normalized_score'] for item in run_summaries) / len(run_summaries),
                    4,
                ),
                'task_success_rate': round(
                    sum(1 for item in run_summaries if item['task_success']) / len(run_summaries),
                    4,
                ),
            }
        return summary

    def _group_alignment(self, issues) -> dict[str, int]:
        counts: dict[str, int] = {}
        for issue in issues:
            counts[issue.status] = counts.get(issue.status, 0) + 1
        return counts

    def _append_event(self, state: StudioRunState, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            'timestamp': utc_now_iso(),
            'run_id': state.run_id,
            'event_type': event_type,
            'payload': payload,
        }
        with (state.root / 'studio_events.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(event) + '\n')

    def _write_state(self, state: StudioRunState) -> None:
        payload = {
            'run_id': state.run_id,
            'status': state.status,
            'error': state.error,
            'summary': state.summary,
        }
        (state.root / 'state.json').write_text(json.dumps(payload, indent=2))

    def _set_status(self, state: StudioRunState, status: str) -> None:
        state.status = status
        self._write_state(state)

    def export_run(self, run_id: str) -> Path:
        state = self.get_state(run_id)
        if state is None:
            raise KeyError(run_id)
        archive_base = state.root.parent / f'{run_id}-export'
        if archive_base.with_suffix('.zip').exists():
            archive_base.with_suffix('.zip').unlink()
        return Path(shutil.make_archive(str(archive_base), 'zip', root_dir=state.root))

    def list_agents(self) -> list[dict]:
        return serialize_agent_backends(list_agent_backends(self.benchmark_root))

    def list_profiles(self) -> list[dict[str, Any]]:
        return [
            build_profile_payload(profile, self._find_best_summary(profile=profile))
            for profile in list_profiles(self.benchmark_root)
        ]

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        try:
            profile = load_profile(self.benchmark_root, profile_id)
        except FileNotFoundError:
            return None
        return build_profile_payload(profile, self._find_best_summary(profile=profile))

    def get_anthropic_demo(self) -> dict[str, Any]:
        payload = self.get_profile('anthropic-demo')
        if payload is None:
            raise FileNotFoundError('Anthropic demo profile not found.')
        return payload

    def _find_best_summary(self, *, profile: BenchmarkProfile) -> dict[str, Any] | None:
        best_summary: dict[str, Any] | None = None
        best_score = -1.0
        expected_runner_kind, expected_agent_backend = execution_preset_to_runtime(
            profile.execution_preset
        )
        for summary_path in self.runs_root.glob('*/summary.json'):
            payload = json.loads(summary_path.read_text())
            inputs = payload.get('inputs') or {}
            benchmark = payload.get('benchmark') or {}
            if payload.get('status') != 'completed':
                continue
            if inputs.get('profile_id') == profile.id:
                score = float(benchmark.get('average_score') or 0.0)
                if score >= best_score:
                    best_score = score
                    best_summary = payload
                continue
            if inputs.get('runner_kind') != expected_runner_kind:
                continue
            if inputs.get('agent_backend') != expected_agent_backend:
                continue
            score = float(benchmark.get('average_score') or 0.0)
            if score >= best_score:
                best_score = score
                best_summary = payload
        return best_summary
