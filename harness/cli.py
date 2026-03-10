from __future__ import annotations

import argparse
import shutil
import subprocess
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


def build_runner(repo_root: Path, condition: str, runner_kind: str):
    if runner_kind == 'demo':
        executor = DemoExecutor()
    else:
        executor = ExternalProcessRunner()

    if condition == 'condition_md':
        return MdConditionRunner(repo_root, executor)
    if condition == 'condition_mcp':
        return McpConditionRunner(repo_root, executor)
    raise ValueError(f'Unknown condition: {condition}')


def execute_run(
    repo_root: Path,
    task_id: str,
    condition: str,
    runner_kind: str,
    adapter_command: str | None = None,
) -> dict:
    task = load_task(repo_root, task_id)
    policy = load_policy(repo_root)
    run_id = f'{task_id}-{condition}'
    output_dir = repo_root / 'benchmark' / 'reports' / 'runs' / run_id
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    workspace = create_workspace(repo_root, task)
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

    runner = build_runner(repo_root, condition, runner_kind)
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
        allowed_scripts=load_allowed_scripts(repo_root),
        user_change_paths=workspace.user_change_paths,
        canary_values=request.canary_values,
    )
    scoring_engine = ScoringEngine(policy, load_rulebook(repo_root))
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
    parser = argparse.ArgumentParser(description='Northstar Ops benchmark harness')
    subparsers = parser.add_subparsers(dest='command', required=True)

    run_task = subparsers.add_parser('run-task')
    run_task.add_argument('--task', required=True)
    run_task.add_argument('--condition', required=True, choices=['condition_md', 'condition_mcp'])
    run_task.add_argument('--runner', default='demo', choices=['demo', 'external'])
    run_task.add_argument('--adapter-cmd')

    run_all = subparsers.add_parser('run-all')
    run_all.add_argument('--runner', default='demo', choices=['demo', 'external'])
    run_all.add_argument('--adapter-cmd')
    run_all.add_argument(
        '--conditions',
        nargs='+',
        default=['condition_md', 'condition_mcp'],
        choices=['condition_md', 'condition_mcp'],
    )

    compare = subparsers.add_parser('compare')
    compare.add_argument('--runs-dir', required=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    if args.command == 'run-task':
        execute_run(
            repo_root=repo_root,
            task_id=args.task,
            condition=args.condition,
            runner_kind=args.runner,
            adapter_command=args.adapter_cmd,
        )
        return 0

    if args.command == 'run-all':
        for task in load_all_tasks(repo_root):
            for condition in args.conditions:
                execute_run(
                    repo_root=repo_root,
                    task_id=task.task_id,
                    condition=condition,
                    runner_kind=args.runner,
                    adapter_command=args.adapter_cmd,
                )
        return 0

    if args.command == 'compare':
        runs_dir = Path(args.runs_dir)
        refresh_run_summaries(repo_root, runs_dir)
        write_aggregate_outputs(repo_root / 'benchmark' / 'reports' / 'aggregate', load_run_summaries(runs_dir))
        return 0

    return 1


if __name__ == '__main__':
    raise SystemExit(main())
