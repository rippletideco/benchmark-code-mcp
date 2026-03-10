from pathlib import Path

from harness.task_loader import load_all_tasks


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_all_task_assets_exist() -> None:
    tasks = load_all_tasks(REPO_ROOT)
    assert len(tasks) == 24

    for task in tasks:
        assert (REPO_ROOT / task.prompt_file).exists(), task.task_id
        if task.setup_patch:
            assert (REPO_ROOT / task.setup_patch).exists(), task.task_id
        if task.seed_user_changes_patch:
            assert (REPO_ROOT / task.seed_user_changes_patch).exists(), task.task_id
        assert task.required_validations, task.task_id
