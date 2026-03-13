from __future__ import annotations

from pathlib import Path

from ..task_loader import read_prompt
from ..models import RunRequest, TaskSpec
from .base import AgentRunner


class MdConditionRunner(AgentRunner):
    def __init__(self, repo_root: Path, executor, instructions_content: str | None = None) -> None:
        super().__init__(repo_root, executor)
        self._instructions_content = instructions_content

    def prepare(
        self,
        output_dir: Path,
        run_id: str,
        task: TaskSpec,
        workspace_path: Path,
        runner_kind: str,
        adapter_command: str | None = None,
    ) -> RunRequest:
        if self._instructions_content is not None:
            bundle = [{'path': 'instructions.md', 'content': self._instructions_content}]
        else:
            bundle_dir = self.repo_root / 'benchmark' / 'instructions' / 'condition_md'
            bundle = [
                {'path': str(path.relative_to(self.repo_root)), 'content': path.read_text()}
                for path in sorted(bundle_dir.glob('*.md'))
            ]
        canary_values = (self.repo_root / 'protected' / 'canary.env').read_text().splitlines()
        return RunRequest(
            run_id=run_id,
            task=task,
            condition='condition_md',
            workspace_path=workspace_path,
            output_dir=output_dir,
            instruction_payload={
                'prompt': read_prompt(self.repo_root, task),
                'instruction_bundle': bundle,
            },
            protected_globs=task.forbidden_files,
            canary_values=canary_values,
            runner_kind=runner_kind,
            adapter_command=adapter_command,
        )

