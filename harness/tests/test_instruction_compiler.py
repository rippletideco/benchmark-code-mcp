from pathlib import Path

from harness.compiler.instruction_compiler import InstructionCompiler
from harness.studio_models import PromptSource


def test_instruction_compiler_extracts_actionable_rules(monkeypatch) -> None:
    monkeypatch.setattr(InstructionCompiler, '_extract_with_codex', lambda self, sources, repo_root: None)
    compiler = InstructionCompiler()
    compiled = compiler.compile(
        [
            PromptSource(
                path='AGENTS.md',
                source_kind='agents',
                content=(
                    '## Core rules\n\n'
                    '1. Validate before concluding.\n'
                    '2. Never overwrite user changes in `docs/`.\n'
                    '3. Prefer rg when searching files.\n'
                ),
            )
        ],
        Path.cwd(),
    )

    assert compiled.rules
    assert any(rule.category == 'validation' for rule in compiled.rules)
    assert any(rule.category == 'worktree' for rule in compiled.rules)
    assert any(rule.requirement_level == 'hard' for rule in compiled.rules)


def test_instruction_compiler_extracts_all_studio_default_rules(monkeypatch) -> None:
    monkeypatch.setattr(InstructionCompiler, '_extract_with_codex', lambda self, sources, repo_root: None)
    compiler = InstructionCompiler()
    source = PromptSource(
        path='studio-default.md',
        source_kind='markdown',
        content=(
            'Validate before concluding.\n'
            'Make the smallest safe change.\n'
            'Explore the repository before editing.\n'
            'Do not overwrite user changes.\n'
        ),
    )
    compiled_rules = compiler._extract_deterministically(source)

    assert len(compiled_rules) == 4
    assert any(rule.category == 'scope' and 'smallest safe change' in rule.normalized_claim for rule in compiled_rules)
    assert any(rule.category == 'scope' and 'explore the repository before editing' in rule.normalized_claim for rule in compiled_rules)


def test_extract_with_codex_uses_resolved_executable(monkeypatch) -> None:
    compiler = InstructionCompiler()
    source = PromptSource(
        path='AGENTS.md',
        source_kind='agents',
        content='Validate before concluding.\n',
    )
    seen_command: list[str] = []

    class Completed:
        returncode = 0
        stderr = ''
        stdout = (
            '{"type":"item.completed","item":{"type":"agent_message","text":"'
            '{\\"rules\\":[{\\"id\\":\\"agents-1\\",\\"source_kind\\":\\"agents\\",'
            '\\"source_file\\":\\"AGENTS.md\\",\\"scope_path\\":\\"/\\",'
            '\\"category\\":\\"validation\\",\\"requirement_level\\":\\"hard\\",'
            '\\"normalized_claim\\":\\"validate before concluding\\",'
            '\\"raw_text\\":\\"Validate before concluding.\\",'
            '\\"confidence\\":0.84,\\"enforceability\\":\\"high\\"}]}"}}\n'
        )

    monkeypatch.setattr(
        'harness.compiler.instruction_compiler.resolve_agent_cli_executable',
        lambda name: '/opt/openai/bin/codex' if name == 'codex' else None,
    )

    def fake_run(command: list[str], **_: object) -> Completed:
        seen_command[:] = command
        return Completed()

    monkeypatch.setattr('harness.compiler.instruction_compiler.subprocess.run', fake_run)
    compiled = compiler._extract_with_codex([source], Path('/tmp/repo'))

    assert compiled is not None
    assert seen_command[0] == '/opt/openai/bin/codex'
