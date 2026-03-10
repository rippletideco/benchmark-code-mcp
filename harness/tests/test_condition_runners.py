from pathlib import Path

from harness.runners.base import Executor
from harness.runners.md_runner import MdConditionRunner
from harness.runners.mcp_runner import McpConditionRunner
from harness.task_loader import load_task


REPO_ROOT = Path(__file__).resolve().parents[2]


class NoopExecutor(Executor):
    def execute(self, request, observer):  # pragma: no cover
        raise NotImplementedError


def test_md_runner_loads_the_provided_markdown_bundle() -> None:
    task = load_task(REPO_ROOT, 'mobile_drawer_route_close')
    runner = MdConditionRunner(REPO_ROOT, NoopExecutor())
    request = runner.prepare(
        output_dir=REPO_ROOT / 'benchmark' / 'reports' / 'runs' / 'test-md',
        run_id='test-md',
        task=task,
        workspace_path=REPO_ROOT,
        runner_kind='external',
    )

    bundle = request.instruction_payload['instruction_bundle']
    assert bundle
    assert all(item['path'].endswith('.md') for item in bundle)
    assert any('Verify before finishing.' in item['content'] for item in bundle)


def test_mcp_runner_detects_a_generic_server_config_file() -> None:
    task = load_task(REPO_ROOT, 'mobile_drawer_route_close')
    runner = McpConditionRunner(REPO_ROOT, NoopExecutor())
    request = runner.prepare(
        output_dir=REPO_ROOT / 'benchmark' / 'reports' / 'runs' / 'test-mcp',
        run_id='test-mcp',
        task=task,
        workspace_path=REPO_ROOT,
        runner_kind='external',
    )

    server_config = request.instruction_payload['mcp_server_config']
    assert 'mcpServers' in server_config
    assert server_config['mcpServers']
    first_server = next(iter(server_config['mcpServers'].values()))
    assert first_server['type'] == 'http'
