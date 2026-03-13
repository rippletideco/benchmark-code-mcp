from __future__ import annotations

import json
from pathlib import Path

from ..task_loader import read_prompt
from ..models import RunRequest, TaskSpec
from .base import AgentRunner


_DEFAULT_MCP_BASE_URL = 'https://mcp.rippletide.com'


class McpConditionRunner(AgentRunner):
    def __init__(
        self,
        repo_root: Path,
        executor,
        mcp_agent_id: str | None = None,
        mcp_base_url: str = _DEFAULT_MCP_BASE_URL,
    ) -> None:
        super().__init__(repo_root, executor)
        self._mcp_agent_id = mcp_agent_id
        self._mcp_base_url = mcp_base_url.rstrip('/')

    def prepare(
        self,
        output_dir: Path,
        run_id: str,
        task: TaskSpec,
        workspace_path: Path,
        runner_kind: str,
        adapter_command: str | None = None,
    ) -> RunRequest:
        if self._mcp_agent_id is not None:
            json_bundle = []
            mcp_server_config = {
                'mcpServers': {
                    'rippletide': {
                        'type': 'http',
                        'url': f'{self._mcp_base_url}/mcp?agentId={self._mcp_agent_id}',
                    }
                }
            }
        else:
            bundle_dir = self.repo_root / 'benchmark' / 'instructions' / 'condition_mcp'
            json_bundle = [
                {
                    'path': str(path.relative_to(self.repo_root)),
                    'content': json.loads(path.read_text()),
                }
                for path in sorted(bundle_dir.glob('*.json'))
            ]
            mcp_server_config = self._merge_mcp_server_configs(json_bundle)
        canary_values = (self.repo_root / 'protected' / 'canary.env').read_text().splitlines()
        return RunRequest(
            run_id=run_id,
            task=task,
            condition='condition_mcp',
            workspace_path=workspace_path,
            output_dir=output_dir,
            instruction_payload={
                'prompt': read_prompt(self.repo_root, task),
                'mcp_json_bundle': json_bundle,
                'mcp_server_config': mcp_server_config,
            },
            protected_globs=task.forbidden_files,
            canary_values=canary_values,
            runner_kind=runner_kind,
            adapter_command=adapter_command,
        )

    @staticmethod
    def _merge_mcp_server_configs(json_bundle: list[dict]) -> dict | None:
        merged_servers: dict = {}
        for item in json_bundle:
            content = item.get('content')
            if not isinstance(content, dict):
                continue
            mcp_servers = content.get('mcpServers')
            if isinstance(mcp_servers, dict):
                merged_servers.update(mcp_servers)

        if not merged_servers:
            return None
        return {'mcpServers': merged_servers}
