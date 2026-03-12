from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from ..executable_resolver import resolve_agent_cli_executable
from ..studio_models import (
    CompiledInstructions,
    InstructionConflict,
    InstructionRule,
    PromptSource,
)

RULE_LINE_PATTERN = re.compile(r'^\s*(?:[-*]|\d+\.)\s+(?P<body>.+?)\s*$')
PATH_PATTERN = re.compile(r'`([^`/][^`]*)`|`(/[^`]*)`|(?:(?:in|under|within)\s+([A-Za-z0-9_./-]+))')


def _source_kind(path: str) -> str:
    upper = path.upper()
    if upper.endswith('AGENTS.MD'):
        return 'agents'
    if upper.endswith('CLAUDE.MD'):
        return 'claude'
    if upper.endswith('.MD'):
        return 'markdown'
    return 'text'


def _normalize_claim(line: str) -> str:
    lowered = re.sub(r'`([^`]+)`', r'\1', line.lower())
    lowered = re.sub(r'[^a-z0-9/._ -]+', ' ', lowered)
    return re.sub(r'\s+', ' ', lowered).strip()


def _scope_from_text(line: str) -> str:
    match = PATH_PATTERN.search(line)
    if not match:
        return '/'
    candidate = next(group for group in match.groups() if group)
    return candidate.strip()


def _category_for_line(line: str) -> str:
    lowered = line.lower()
    if any(token in lowered for token in ('validate', 'test', 'lint', 'typecheck', 'build')):
        return 'validation'
    if any(token in lowered for token in ('secret', 'token', 'protected', 'env', 'credential')):
        return 'safety'
    if any(token in lowered for token in ('overwrite', 'preserve', 'revert', 'worktree', 'dirty')):
        return 'worktree'
    if any(token in lowered for token in ('tool', 'shell', 'command', 'apply_patch', 'rg ')):
        return 'tooling'
    if any(token in lowered for token in ('mcp', 'context graph', 'server', 'resource', 'prompt')):
        return 'mcp'
    if any(
        token in lowered
        for token in (
            'smallest change',
            'smallest safe change',
            'smallest',
            'minimal',
            'scope',
            'focus',
            'explore',
            'repository',
            'before editing',
        )
    ):
        return 'scope'
    if any(token in lowered for token in ('quality', 'robust', 'safe', 'correct')):
        return 'quality'
    return 'other'


def _requirement_level(line: str) -> str:
    lowered = line.lower()
    if any(token in lowered for token in ('must', 'never', 'always', 'do not', 'cannot', 'required')):
        return 'hard'
    if any(token in lowered for token in ('should', 'prefer', 'recommended', 'ideally')):
        return 'soft'
    return 'informational'


def _enforceability(line: str) -> str:
    category = _category_for_line(line)
    if category in {'validation', 'safety', 'worktree', 'tooling'}:
        return 'high'
    if category in {'scope', 'mcp'}:
        return 'medium'
    return 'low'


def _confidence_for_line(line: str) -> float:
    if RULE_LINE_PATTERN.match(line):
        return 0.84
    if any(token in line.lower() for token in ('must', 'never', 'should', 'prefer')):
        return 0.72
    return 0.58


class InstructionCompiler:
    def compile(self, sources: list[PromptSource], repo_root: Path) -> CompiledInstructions:
        llm_result = self._extract_with_codex(sources, repo_root)
        if llm_result is not None:
            compiled = llm_result
            compiled.sources = sources
            return self._post_process(compiled)

        rules: list[InstructionRule] = []
        for source in sources:
            rules.extend(self._extract_deterministically(source))

        return self._post_process(
            CompiledInstructions(
                sources=sources,
                rules=rules,
                extraction_mode='deterministic',
            )
        )

    def _extract_deterministically(self, source: PromptSource) -> list[InstructionRule]:
        rules: list[InstructionRule] = []
        for index, raw_line in enumerate(source.content.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            candidate = RULE_LINE_PATTERN.match(line)
            body = candidate.group('body') if candidate else line
            if len(body) < 12:
                continue
            if not any(
                token in body.lower()
                for token in (
                    'must',
                    'should',
                    'prefer',
                    'never',
                    'do not',
                    'validate',
                    'test',
                    'protect',
                    'mcp',
                    'repo',
                    'worktree',
                    'command',
                    'file',
                    'smallest',
                    'safe change',
                    'explore',
                    'repository',
                    'before editing',
                )
            ):
                continue

            rule_id = f'{source.source_kind}-{index}'
            rules.append(
                InstructionRule(
                    id=rule_id,
                    source_kind=source.source_kind,
                    source_file=source.path,
                    scope_path=_scope_from_text(body),
                    category=_category_for_line(body),
                    requirement_level=_requirement_level(body),
                    normalized_claim=_normalize_claim(body),
                    raw_text=body,
                    confidence=_confidence_for_line(line),
                    enforceability=_enforceability(body),
                )
            )

        return rules

    def _extract_with_codex(
        self,
        sources: list[PromptSource],
        repo_root: Path,
    ) -> CompiledInstructions | None:
        executable = resolve_agent_cli_executable('codex')
        if executable is None:
            return None

        prompt = self._build_codex_prompt(sources)
        command = [
            executable,
            'exec',
            '--json',
            '--sandbox',
            'read-only',
            '-C',
            str(repo_root),
            '-c',
            'features.multi_agent=false',
            '-c',
            'features.memory_tool=false',
            '-',
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=repo_root,
                input=prompt,
                text=True,
                capture_output=True,
                check=False,
                timeout=8,
            )
        except subprocess.TimeoutExpired:
            return None

        last_message = ''
        for line in completed.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get('type') != 'item.completed':
                continue
            item = payload.get('item', {})
            if item.get('type') == 'agent_message':
                text = item.get('text', '')
                if text:
                    last_message = text

        return_code = completed.returncode
        if return_code != 0 or not last_message:
            return None

        try:
            raw = json.loads(last_message)
        except json.JSONDecodeError:
            return None

        try:
            rules = [
                InstructionRule(
                    id=str(item['id']),
                    source_kind=str(item['source_kind']),
                    source_file=str(item['source_file']),
                    scope_path=str(item.get('scope_path', '/')),
                    category=str(item['category']),
                    requirement_level=str(item['requirement_level']),
                    normalized_claim=str(item['normalized_claim']),
                    raw_text=str(item['raw_text']),
                    confidence=float(item['confidence']),
                    enforceability=str(item['enforceability']),
                )
                for item in raw.get('rules', [])
            ]
        except (KeyError, TypeError, ValueError):
            return None

        conflicts = [
            InstructionConflict(
                rule_ids=[str(value) for value in item.get('rule_ids', [])],
                reason=str(item.get('reason', '')),
            )
            for item in raw.get('conflicts', [])
        ]
        return CompiledInstructions(
            sources=[],
            rules=rules,
            conflicts=conflicts,
            shadowed_rules=[str(item) for item in raw.get('shadowed_rules', [])],
            low_confidence_rules=[str(item) for item in raw.get('low_confidence_rules', [])],
            extraction_mode='codex',
        )

    def _build_codex_prompt(self, sources: list[PromptSource]) -> str:
        source_blocks = '\n\n'.join(
            f'FILE: {source.path}\nTYPE: {source.source_kind}\nCONTENT:\n{source.content}'
            for source in sources
        )
        schema = {
            'rules': [
                {
                    'id': 'agents-12',
                    'source_kind': 'agents',
                    'source_file': 'AGENTS.md',
                    'scope_path': '/',
                    'category': 'validation',
                    'requirement_level': 'hard',
                    'normalized_claim': 'validate before conclude',
                    'raw_text': 'Validate before concluding.',
                    'confidence': 0.9,
                    'enforceability': 'high',
                }
            ],
            'conflicts': [{'rule_ids': ['agents-12', 'claude-9'], 'reason': 'opposite write policy'}],
            'shadowed_rules': ['agents-3'],
            'low_confidence_rules': ['markdown-17'],
        }
        return (
            'Extract actionable repository instruction rules from the provided files.\n'
            'Return JSON only. No markdown fences. Keep only agent-operational rules.\n'
            'Categories allowed: validation, safety, worktree, tooling, scope, quality, mcp, other.\n'
            'Requirement levels allowed: hard, soft, informational.\n'
            'Use compact normalized_claim strings.\n'
            f'Response schema example:\n{json.dumps(schema, indent=2)}\n\n'
            f'SOURCES:\n{source_blocks}\n'
        )

    def _post_process(self, compiled: CompiledInstructions) -> CompiledInstructions:
        seen_claims: dict[tuple[str, str], str] = {}
        shadowed_rules = set(compiled.shadowed_rules)
        low_confidence_rules = set(compiled.low_confidence_rules)
        conflicts = list(compiled.conflicts)

        for rule in compiled.rules:
            key = (rule.scope_path, rule.normalized_claim)
            previous_rule_id = seen_claims.get(key)
            if previous_rule_id:
                shadowed_rules.add(rule.id)
                conflicts.append(
                    InstructionConflict(
                        rule_ids=[previous_rule_id, rule.id],
                        reason='duplicate rule in same scope',
                    )
                )
            else:
                seen_claims[key] = rule.id

            if rule.confidence < 0.6:
                low_confidence_rules.add(rule.id)

        compiled.shadowed_rules = sorted(shadowed_rules)
        compiled.low_confidence_rules = sorted(low_confidence_rules)
        compiled.conflicts = self._dedupe_conflicts(conflicts)
        return compiled

    def _dedupe_conflicts(self, conflicts: list[InstructionConflict]) -> list[InstructionConflict]:
        deduped: dict[tuple[tuple[str, ...], str], InstructionConflict] = {}
        for conflict in conflicts:
            key = (tuple(sorted(conflict.rule_ids)), conflict.reason)
            deduped[key] = conflict
        return list(deduped.values())


def load_prompt_sources(paths: list[Path]) -> list[PromptSource]:
    return [
        PromptSource(
            path=str(path.name),
            content=path.read_text(),
            source_kind=_source_kind(path.name),
        )
        for path in paths
    ]
