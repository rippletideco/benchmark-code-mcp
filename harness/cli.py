from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .logging import EventLogger
from .models import RunResult, ScoringContext, ValidationResult
from .observer import RunObserver
from .reporting import load_run_summaries, refresh_run_summaries, write_aggregate_outputs, write_run_outputs
from .runners import DemoExecutor, ExternalProcessRunner, McpConditionRunner, MdConditionRunner
from .scoring import ScoringEngine, load_allowed_scripts, load_rulebook
from .task_loader import load_all_tasks, load_policy, load_task
from .workspace import (
    build_changed_files,
    create_workspace,
    diff_snapshot,
    git_status_snapshot,
    snapshot_tree,
)


def run_validations(workspace_root: Path, task, observer: RunObserver) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    for validation in task.required_validations:
        command = validation.command
        completed = subprocess.run(
            command,
            cwd=workspace_root,
            text=True,
            capture_output=True,
            shell=True,
            check=False,
        )
        result = ValidationResult(
            id=validation.id,
            command=command,
            passed=completed.returncode == 0,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        observer.record_event(
            'validation_result',
            {
                'id': validation.id,
                'command': command,
                'passed': result.passed,
                'exit_code': result.exit_code,
            },
        )
        results.append(result)
    return results


def build_runner(
    project_root: Path,
    condition: str,
    runner_kind: str,
    instructions_content: str | None = None,
    mcp_agent_id: str | None = None,
    mcp_base_url: str | None = None,
):
    if runner_kind == 'demo':
        executor = DemoExecutor()
    else:
        executor = ExternalProcessRunner()

    if condition == 'condition_md':
        return MdConditionRunner(project_root, executor, instructions_content=instructions_content)
    if condition == 'condition_mcp':
        kwargs: dict = {'mcp_agent_id': mcp_agent_id}
        if mcp_base_url:
            kwargs['mcp_base_url'] = mcp_base_url
        return McpConditionRunner(project_root, executor, **kwargs)
    raise ValueError(f'Unknown condition: {condition}')


_DEFAULT_ADAPTER_COMMANDS: dict[str, str] = {
    'claude': 'python -m harness.claude_adapter {request_file}',
    'codex': 'python -m harness.codex_adapter {request_file}',
}


def execute_run(
    repo_root: Path,
    task_id: str,
    condition: str,
    runner_kind: str,
    adapter_command: str | None = None,
    instructions_content: str | None = None,
    mcp_agent_id: str | None = None,
    mcp_base_url: str | None = None,
    project_root: Path | None = None,
) -> dict:
    project_root = project_root or repo_root
    if adapter_command is None and runner_kind in _DEFAULT_ADAPTER_COMMANDS:
        adapter_command = _DEFAULT_ADAPTER_COMMANDS[runner_kind]
    task = load_task(project_root, task_id)
    policy = load_policy(project_root)
    run_id = f'{task_id}-{condition}'
    output_dir = project_root / 'benchmark' / 'reports' / 'runs' / run_id
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    workspace = create_workspace(project_root, task)
    logger = EventLogger(output_dir / 'events.jsonl')
    observer = RunObserver(condition, logger, run_id, task_id, workspace.root)
    observer.record_event(
        'run_started',
        {'runner_kind': runner_kind, 'workspace_path': str(workspace.root)},
    )
    observer.record_event(
        'git_status_snapshot',
        {'stage': 'task_start', 'status': git_status_snapshot(workspace.root)},
    )

    runner = build_runner(project_root, condition, runner_kind, instructions_content, mcp_agent_id, mcp_base_url)
    request = runner.prepare(
        output_dir=output_dir,
        run_id=run_id,
        task=task,
        workspace_path=workspace.root,
        runner_kind=runner_kind,
        adapter_command=adapter_command,
    )
    observer.record_event(
        'instruction_injected',
        {
            'condition': condition,
            'prompt_file': task.prompt_file,
            'payload_keys': list(request.instruction_payload.keys()),
        },
    )
    run_result: RunResult = runner.execute(request, observer)
    observer.record_event(
        'git_status_snapshot',
        {'stage': 'after_agent', 'status': git_status_snapshot(workspace.root)},
    )
    observer.record_event(
        'diff_snapshot',
        {'stage': 'after_agent', 'diff_stat': diff_snapshot(workspace.root)},
    )

    validation_results = run_validations(workspace.root, task, observer)
    final_snapshot = snapshot_tree(workspace.root)
    changed_files = build_changed_files(workspace.task_start_snapshot, final_snapshot)
    scoring_context = ScoringContext(
        repo_root=workspace.root,
        run_request=request,
        run_result=run_result,
        events=logger.events,
        start_snapshot=workspace.task_start_snapshot,
        final_snapshot=final_snapshot,
        changed_files=changed_files,
        validation_results=validation_results,
        protected_globs=policy['protected_globs'],
        destructive_commands=policy['destructive_commands'],
        high_impact_patterns=policy['high_impact_command_patterns'],
        allowed_scripts=load_allowed_scripts(project_root),
        user_change_paths=workspace.user_change_paths,
        canary_values=request.canary_values,
    )
    scoring_engine = ScoringEngine(policy, load_rulebook(project_root))
    score_summary = scoring_engine.score(scoring_context)
    observer.record_event(
        'scoring_result',
        {
            'normalized_score': score_summary.normalized_score,
            'hard_violation_count': score_summary.hard_violation_count,
            'task_success': score_summary.task_success,
        },
    )
    summary = write_run_outputs(
        output_dir=output_dir,
        request=request,
        score_summary=score_summary,
        changed_files=changed_files,
        validation_results=validation_results,
        workspace_path=workspace.root,
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Benchmark harness')
    subparsers = parser.add_subparsers(dest='command', required=True)

    run_task = subparsers.add_parser('run-task')
    run_task.add_argument('--task', required=True)
    run_task.add_argument('--condition', required=True, choices=['condition_md', 'condition_mcp'])
    run_task.add_argument('--runner', default='demo', choices=['demo', 'claude', 'codex', 'external'])
    run_task.add_argument('--adapter-cmd')
    run_task.add_argument('--instructions-source', default=None)
    run_task.add_argument('--mcp-agent-id', default=None)
    run_task.add_argument('--mcp-base-url', default=None)
    run_task.add_argument('--auto-sync-mcp', action='store_true', default=False)
    run_task.add_argument('--project-root', default=None)

    run_all = subparsers.add_parser('run-all')
    run_all.add_argument('--runner', default='demo', choices=['demo', 'claude', 'codex', 'external'])
    run_all.add_argument('--adapter-cmd')
    run_all.add_argument(
        '--conditions',
        nargs='+',
        default=['condition_md', 'condition_mcp'],
        choices=['condition_md', 'condition_mcp'],
    )
    run_all.add_argument('--max-workers', type=int, default=1)
    run_all.add_argument('--instructions-source', default=None)
    run_all.add_argument('--mcp-agent-id', default=None)
    run_all.add_argument('--mcp-base-url', default=None)
    run_all.add_argument('--auto-sync-mcp', action='store_true', default=False)
    run_all.add_argument('--project-root', default=None)

    compare = subparsers.add_parser('compare')
    compare.add_argument('--runs-dir', required=True)
    compare.add_argument('--project-root', default=None)

    generate = subparsers.add_parser('generate-tasks')
    generate.add_argument('--repo', required=True, help='GitHub owner/repo (e.g. octocat/Hello-World)')
    generate.add_argument('--project-root', required=True, help='Output directory for the generated project')
    generate.add_argument('--max-tasks', type=int, default=20)
    generate.add_argument('--since', default=None, help='Only include PRs merged after this date (YYYY-MM-DD)')
    generate.add_argument('--generate-rules', action='store_true',
        help='Generate tailored coding rules for this repo after cloning (requires claude CLI)')
    generate.add_argument('--num-rules', type=int, default=40,
        help='Number of rules to generate (default: 40)')

    list_tasks = subparsers.add_parser('list-tasks')
    list_tasks.add_argument('--project-root', default=None)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    if args.command in ('run-task', 'run-all'):
        instructions_source = getattr(args, 'instructions_source', None)
        mcp_agent_id = getattr(args, 'mcp_agent_id', None)
        mcp_base_url: str | None = getattr(args, 'mcp_base_url', None)
        auto_sync_mcp: bool = getattr(args, 'auto_sync_mcp', False)
        if instructions_source and not mcp_agent_id:
            parser.error(
                '--mcp-agent-id is required when --instructions-source is set.\n'
                'Run `npx rippletide-mcp@latest` in your repo first to build the graph,\n'
                'then pass the agentId (e.g. your email: fan@rippletide.com).'
            )
        instructions_content: str | None = None
        if instructions_source:
            from .instructions_discovery import discover_instructions
            instructions_content = discover_instructions(instructions_source)

        if auto_sync_mcp:
            if not (mcp_agent_id and instructions_content):
                parser.error('--auto-sync-mcp requires both --mcp-agent-id and --instructions-source.')
            from .mcp_sync import sync_instructions_to_mcp
            _sync_url = mcp_base_url or 'https://mcp.rippletide.com'
            print(f'Syncing instructions to MCP graph ({_sync_url}, agentId={mcp_agent_id}) ...')
            sync_instructions_to_mcp(_sync_url, mcp_agent_id, instructions_content)

        raw_project_root = getattr(args, 'project_root', None)
        project_root = Path(raw_project_root).expanduser().resolve() if raw_project_root else repo_root

    if args.command == 'run-task':
        execute_run(
            repo_root=repo_root,
            task_id=args.task,
            condition=args.condition,
            runner_kind=args.runner,
            adapter_command=args.adapter_cmd,
            instructions_content=instructions_content,
            mcp_agent_id=mcp_agent_id,
            mcp_base_url=mcp_base_url,
            project_root=project_root,
        )
        return 0

    if args.command == 'run-all':
        task_pairs = [
            (task.task_id, condition)
            for task in load_all_tasks(project_root)
            for condition in args.conditions
        ]
        if args.max_workers <= 1:
            for task_id, condition in task_pairs:
                execute_run(
                    repo_root=repo_root,
                    task_id=task_id,
                    condition=condition,
                    runner_kind=args.runner,
                    adapter_command=args.adapter_cmd,
                    instructions_content=instructions_content,
                    mcp_agent_id=mcp_agent_id,
                    mcp_base_url=mcp_base_url,
                    project_root=project_root,
                )
            return 0

        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = [
                executor.submit(
                    execute_run,
                    repo_root=repo_root,
                    task_id=task_id,
                    condition=condition,
                    runner_kind=args.runner,
                    adapter_command=args.adapter_cmd,
                    instructions_content=instructions_content,
                    mcp_agent_id=mcp_agent_id,
                    mcp_base_url=mcp_base_url,
                    project_root=project_root,
                )
                for task_id, condition in task_pairs
            ]
            for future in as_completed(futures):
                future.result()
        return 0

    if args.command == 'compare':
        runs_dir = Path(args.runs_dir)
        raw_pr = getattr(args, 'project_root', None)
        compare_root = Path(raw_pr).expanduser().resolve() if raw_pr else repo_root
        refresh_run_summaries(compare_root, runs_dir)
        write_aggregate_outputs(compare_root / 'benchmark' / 'reports' / 'aggregate', load_run_summaries(runs_dir))
        return 0

    if args.command == 'generate-tasks':
        from .task_generator import TaskGenerator
        _raw = args.project_root
        _p = Path(_raw).expanduser()
        if not _p.is_absolute():
            _p = Path.home() / 'projects' / _raw
        project_root = _p.resolve()
        token = os.environ.get('GITHUB_TOKEN')
        gen = TaskGenerator(
            repo=args.repo,
            project_root=project_root,
            harness_root=repo_root,
            github_token=token,
            max_tasks=args.max_tasks,
            since=args.since,
            generate_rules=args.generate_rules,
            num_rules=args.num_rules,
        )
        tasks = gen.run()
        print(f'Generated {len(tasks)} tasks in {project_root}')
        for t in tasks:
            print(f"  {t['task_id']}: {t['title']}")
        return 0

    if args.command == 'list-tasks':
        raw_project_root = getattr(args, 'project_root', None)
        project_root = Path(raw_project_root).expanduser().resolve() if raw_project_root else repo_root
        tasks = load_all_tasks(project_root)
        for task in tasks:
            print(task.task_id)
        return 0

    return 1


if __name__ == '__main__':
    raise SystemExit(main())
