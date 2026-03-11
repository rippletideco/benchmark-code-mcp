from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from .service import StudioRunManager


def create_app() -> FastAPI:
    benchmark_root = Path(__file__).resolve().parents[2]
    manager = StudioRunManager(benchmark_root)
    app = FastAPI(title='Dynamic Benchmark Studio', version='0.1.0')
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_methods=['*'],
        allow_headers=['*'],
    )

    @app.get('/api/health')
    def health() -> dict[str, str]:
        return {'status': 'ok'}

    @app.post('/api/runs')
    async def create_run(
        profile_id: str | None = Form(default=None),
        repo_path: str | None = Form(default=None),
        repo_archive: UploadFile | None = File(default=None),
        instruction_files: list[UploadFile] | None = File(default=None),
        mcp_json: str = Form(default='{}'),
        mcp_source_type: str | None = Form(default=None),
        mcp_source_path: str | None = Form(default=None),
        mcp_source_command: str | None = Form(default=None),
        runner_kind: str = Form(default='demo'),
        agent_backend: str = Form(default='codex'),
        adapter_command: str | None = Form(default=None),
        max_workers: int = Form(default=4),
    ) -> dict[str, str]:
        state = manager.create_run(
            profile_id=profile_id,
            repo_path=repo_path,
            repo_archive=repo_archive,
            instruction_files=instruction_files or [],
            mcp_json=mcp_json,
            mcp_source_type=mcp_source_type,
            mcp_source_path=mcp_source_path,
            mcp_source_command=mcp_source_command,
            runner_kind=runner_kind,
            agent_backend=agent_backend,
            adapter_command=adapter_command,
            max_workers=max(1, min(max_workers, 16)),
        )
        return {'run_id': state.run_id, 'status': state.status}

    @app.get('/api/agents')
    def list_agents() -> dict:
        return {'default_external_agent': 'codex', 'agents': manager.list_agents()}

    @app.get('/api/profiles')
    def list_profiles() -> dict:
        return {'profiles': manager.list_profiles()}

    @app.get('/api/profiles/{profile_id}')
    def get_profile(profile_id: str) -> dict:
        payload = manager.get_profile(profile_id)
        if payload is None:
            raise HTTPException(status_code=404, detail='Profile not found.')
        return payload

    @app.post('/api/profiles/{profile_id}/run')
    async def create_profile_run(
        profile_id: str,
        repo_path: str | None = Form(default=None),
        repo_archive: UploadFile | None = File(default=None),
        instruction_files: list[UploadFile] | None = File(default=None),
        adapter_command: str | None = Form(default=None),
    ) -> dict[str, str]:
        state = manager.create_run(
            profile_id=profile_id,
            repo_path=repo_path,
            repo_archive=repo_archive,
            instruction_files=instruction_files or [],
            mcp_json='{}',
            mcp_source_type=None,
            mcp_source_path=None,
            mcp_source_command=None,
            runner_kind='demo',
            agent_backend='codex',
            adapter_command=adapter_command,
            max_workers=4,
        )
        return {'run_id': state.run_id, 'status': state.status}

    @app.get('/api/demo/anthropic')
    def anthropic_demo() -> dict:
        payload = manager.get_profile('anthropic-demo')
        if payload is None:
            raise HTTPException(status_code=404, detail='Anthropic demo profile not found.')
        return payload

    @app.get('/api/runs/{run_id}')
    def get_run(run_id: str) -> dict:
        state = manager.get_state(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail='Run not found.')

        state_path = state.root / 'state.json'
        if state_path.exists():
            payload = json.loads(state_path.read_text())
        else:
            payload = {'run_id': state.run_id, 'status': state.status}

        summary_path = state.root / 'summary.json'
        if summary_path.exists():
            payload['summary'] = json.loads(summary_path.read_text())
        bundle_paths = {
            'normalized_rules': str(state.root / 'bundle' / 'normalized_rules.json'),
            'mcp_manifest': str(state.root / 'bundle' / 'mcp_manifest.json'),
            'alignment': str(state.root / 'bundle' / 'alignment.json'),
            'generated_tasks': str(state.root / 'bundle' / 'generated_tasks.json'),
        }
        payload['bundle_paths'] = bundle_paths
        return payload

    @app.get('/api/runs/{run_id}/events')
    async def stream_events(run_id: str) -> StreamingResponse:
        state = manager.get_state(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail='Run not found.')

        async def event_stream():
            log_path = state.root / 'studio_events.jsonl'
            position = 0
            while True:
                if log_path.exists():
                    with log_path.open('r', encoding='utf-8') as handle:
                        handle.seek(position)
                        for line in handle:
                            yield f'data: {line.strip()}\n\n'
                        position = handle.tell()

                state_path = state.root / 'state.json'
                if state_path.exists():
                    payload = json.loads(state_path.read_text())
                    if payload.get('status') in {'completed', 'failed'}:
                        yield f'data: {json.dumps({"event_type": "stream_closed", "payload": payload})}\n\n'
                        break
                await asyncio.sleep(0.25)

        return StreamingResponse(event_stream(), media_type='text/event-stream')

    @app.get('/api/runs/{run_id}/export')
    def export_run(run_id: str) -> FileResponse:
        try:
            archive_path = manager.export_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail='Run not found.') from exc
        return FileResponse(archive_path, filename=archive_path.name, media_type='application/zip')

    return app


app = create_app()
