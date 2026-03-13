from __future__ import annotations

import json
from pathlib import Path

from .models import TaskSpec


def load_policy(project_root: Path) -> dict:
    return json.loads((project_root / 'benchmark' / 'policy.json').read_text())


def load_task(project_root: Path, task_id: str) -> TaskSpec:
    task_path = project_root / 'benchmark' / 'tasks' / f'{task_id}.json'
    return TaskSpec.from_dict(json.loads(task_path.read_text()))


def load_all_tasks(project_root: Path) -> list[TaskSpec]:
    tasks_dir = project_root / 'benchmark' / 'tasks'
    task_paths = sorted(tasks_dir.glob('*.json'))
    return [TaskSpec.from_dict(json.loads(path.read_text())) for path in task_paths]


def read_prompt(project_root: Path, task: TaskSpec) -> str:
    prompt_path = Path(task.prompt_file)
    if not prompt_path.is_absolute():
        prompt_path = project_root / prompt_path
    return prompt_path.read_text()
