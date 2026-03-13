from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Verdict = Literal['pass', 'partial', 'fail', 'not_applicable']


@dataclass(slots=True)
class ValidationSpec:
    id: str
    command: str


@dataclass(slots=True)
class CompletionCheck:
    type: str
    value: str | None = None
    path: str | None = None


@dataclass(slots=True)
class WorkspaceFile:
    path: str
    content: str


@dataclass(slots=True)
class DiffLimits:
    max_files_changed: int
    max_lines_changed: int


@dataclass(slots=True)
class TaskSpec:
    task_id: str
    title: str
    prompt_file: str
    expected_files: list[str]
    allowed_files: list[str]
    forbidden_files: list[str]
    required_validations: list[ValidationSpec]
    forbidden_commands: list[str]
    completion_checks: list[CompletionCheck]
    clarification_allowed: bool
    diff_limits: DiffLimits
    setup_patch: str | None = None
    seed_user_changes_patch: str | None = None
    setup_files: list[WorkspaceFile] = field(default_factory=list)
    repair_files: list[WorkspaceFile] = field(default_factory=list)
    seed_user_files: list[WorkspaceFile] = field(default_factory=list)
    disallowed_code_patterns: list[str] = field(default_factory=list)
    protected_overrides: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'TaskSpec':
        return cls(
            task_id=payload['task_id'],
            title=payload['title'],
            prompt_file=payload['prompt_file'],
            expected_files=list(payload['expected_files']),
            allowed_files=list(payload['allowed_files']),
            forbidden_files=list(payload['forbidden_files']),
            required_validations=[
                ValidationSpec(**item) for item in payload['required_validations']
            ],
            forbidden_commands=list(payload.get('forbidden_commands', [])),
            completion_checks=[
                CompletionCheck(
                    type=item['type'],
                    value=item.get('value') or item.get('validation_id'),
                    path=item.get('path'),
                )
                for item in payload['completion_checks']
            ],
            clarification_allowed=payload['clarification_allowed'],
            diff_limits=DiffLimits(**payload['diff_limits']),
            setup_patch=payload.get('setup_patch'),
            seed_user_changes_patch=payload.get('seed_user_changes_patch'),
            setup_files=[WorkspaceFile(**item) for item in payload.get('setup_files', [])],
            repair_files=[WorkspaceFile(**item) for item in payload.get('repair_files', [])],
            seed_user_files=[WorkspaceFile(**item) for item in payload.get('seed_user_files', [])],
            disallowed_code_patterns=list(payload.get('disallowed_code_patterns', [])),
            protected_overrides=list(payload.get('protected_overrides', [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RuleResult:
    rule_id: str
    title: str
    verdict: Verdict
    ratio: float | None
    weight: int
    severity: Literal['hard', 'soft']
    evidence: list[str] = field(default_factory=list)

    def weighted_score(self) -> float:
        if self.ratio is None:
            return 0.0
        return self.ratio * self.weight


@dataclass(slots=True)
class ScoreSummary:
    total_score: float
    max_score: float
    normalized_score: float
    instruction_adherence_rate: float
    hard_violation_count: int
    task_success: bool
    rules: list[RuleResult]


@dataclass(slots=True)
class RunRequest:
    run_id: str
    task: TaskSpec
    condition: str
    workspace_path: Path
    output_dir: Path
    instruction_payload: dict[str, Any]
    protected_globs: list[str]
    canary_values: list[str]
    runner_kind: str
    adapter_command: str | None = None


@dataclass(slots=True)
class RunResult:
    final_message: str
    final_status: str
    tool_categories_exposed: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ValidationResult:
    id: str
    command: str
    passed: bool
    exit_code: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class ChangedFile:
    path: str
    status: str
    added_lines: int
    removed_lines: int


@dataclass(slots=True)
class ScoringContext:
    repo_root: Path
    run_request: RunRequest
    run_result: RunResult
    events: list[dict[str, Any]]
    start_snapshot: dict[str, str]
    final_snapshot: dict[str, str]
    changed_files: list[ChangedFile]
    validation_results: list[ValidationResult]
    protected_globs: list[str]
    destructive_commands: list[str]
    high_impact_patterns: list[str]
    allowed_scripts: set[str]
    user_change_paths: list[str]
    canary_values: list[str]


@dataclass(slots=True)
class WorkspaceContext:
    root: Path
    task_start_snapshot: dict[str, str]
    user_change_paths: list[str]
    temp_dir: Path
