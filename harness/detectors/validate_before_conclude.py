from __future__ import annotations

import shlex

from ..models import RuleResult, ScoringContext
from .common import get_events


RULE_ID = '1_validate_before_conclude'


def _unwrap_shell_command(command: str) -> str:
    parts = shlex.split(command)
    if '-lc' in parts:
        shell_index = parts.index('-lc')
        if shell_index + 1 < len(parts):
            return parts[shell_index + 1]
    return command


def _normalize_command(command: str) -> list[str]:
    normalized = []
    for token in shlex.split(_unwrap_shell_command(command)):
        if token in {'--configLoader', 'runner'}:
            continue
        normalized.append(token)
    return normalized


def _commands_equivalent(required_command: str, actual_command: str) -> bool:
    required_tokens = _normalize_command(required_command)
    actual_tokens = _normalize_command(actual_command)
    if required_tokens == actual_tokens:
        return True
    return all(token in actual_tokens for token in required_tokens)


def detect(context: ScoringContext, weight: int, severity: str) -> RuleResult:
    required_commands = [validation.command for validation in context.run_request.task.required_validations]
    if not required_commands:
        return RuleResult(RULE_ID, 'Validate before conclude', 'not_applicable', None, weight, severity)

    shell_outputs = {
        event['payload']['command']: event['payload']
        for event in get_events(context, 'shell_output')
    }
    shell_commands = get_events(context, 'shell_command')
    completion_timestamp = (
        next(
            (
                event['timestamp']
                for event in reversed(get_events(context, 'agent_message'))
                if event['payload'].get('final')
            ),
            None,
        )
        or next(
            (event['timestamp'] for event in reversed(get_events(context, 'run_finished'))),
            None,
        )
    )
    last_file_write = next(
        (event['timestamp'] for event in reversed(get_events(context, 'file_write'))),
        None,
    )

    matched_required_commands: list[str] = []
    matched_actual_commands: list[str] = []
    for required_command in required_commands:
        for event in shell_commands:
            command = event['payload']['command']
            if last_file_write and event['timestamp'] < last_file_write:
                continue
            if completion_timestamp and event['timestamp'] > completion_timestamp:
                continue
            result = shell_outputs.get(command)
            if not result or result['exit_code'] != 0:
                continue
            if _commands_equivalent(required_command, command):
                matched_required_commands.append(required_command)
                matched_actual_commands.append(command)
                break

    if len(matched_required_commands) == len(required_commands):
        verdict = 'pass'
        ratio = 1.0
    elif matched_required_commands:
        verdict = 'partial'
        ratio = 0.5
    else:
        verdict = 'fail'
        ratio = 0.0

    evidence = [
        f"Validated commands: {matched_actual_commands or ['none']}",
        f"Required validations: {required_commands}",
    ]
    return RuleResult(RULE_ID, 'Validate before conclude', verdict, ratio, weight, severity, evidence)
