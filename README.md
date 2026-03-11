# Northstar Ops Benchmark Repository

Northstar Ops is a local benchmark studio for comparing coding-agent behavior under two context-delivery modes:

- `condition_md`: rules delivered as Markdown / system-prompt context
- `condition_mcp`: rules delivered through MCP context

The benchmark target is rule adherence, not generic model quality. The Studio is built to answer:

- does the agent respect the rules better with `MD` or with `MCP`?
- how many rules from the `.md` are actually represented in the MCP?
- which rules fail only in `MD`, only in `MCP`, or in both?

## What This Repo Contains

- `web/`: the Studio UI and the compact benchmark target app
- `harness/`: Python orchestration, precheck, benchmark execution, scoring, adapters
- `benchmark/`: task fixtures, policies, profiles, prompts, and reports
- `scripts/`: thin wrappers for starting the Studio and external agent adapters
- `protected/`: canary and protected files used by the benchmark
- `docs/`: architecture and integration notes

## Prerequisites

You need these installed locally:

- `python3` with venv support
- `pnpm`
- for real agent runs:
  - `codex` if you want Codex runs
  - `claude` if you want Claude Code runs

## Setup

From the repo root:

```bash
make setup
```

This does all local bootstrap:

- installs frontend dependencies with `pnpm`
- creates `.venv`
- installs the editable Python harness with dev dependencies

## Fastest Way To Try The Project

```bash
make studio
```

Then open:

- `http://localhost:5173/studio`

This starts both:

- the FastAPI backend on `http://127.0.0.1:8008`
- the Vite frontend on `http://localhost:5173`

If you prefer launching them separately:

```bash
make studio-server
pnpm studio:web
```

## How To Use The Studio

The Studio now runs as a single one-shot flow.

Steps:

1. Open `/studio`
2. Choose one connected agent:
   - `Codex`
   - `Claude Code`
3. Paste the markdown brief you want to benchmark
4. Paste the MCP JSON config inline
5. Optionally set a local repo path for the sandbox
   - if empty, the Studio falls back to this benchmark repo
6. Click `Run benchmark`
7. Watch the harness generate tasks, validations, and the final `MD vs MCP` comparison

The primary UI intentionally removes profile selection, precheck confirmation, file uploads, and MCP mode switching to keep the benchmark flow short and explicit.

## What The Benchmark Actually Does

The UI is single-step, but the harness still performs two internal phases:

### 1. Coverage snapshot

Before execution, the harness:

1. parses the pasted `.md`
2. normalizes rules into canonical benchmark rules
3. checks whether those rules are represented in the MCP
4. records a coverage snapshot:
   - `covered`
   - `missing`
   - `ambiguous`
   - `not_applicable`

This is no longer a user-facing gate in the Studio UI. It is kept as internal benchmark metadata and shown only as a secondary detail after launch.

### 2. Benchmark execution

The harness then:

1. compiles one executable benchmark task per benchmarkable rule
2. runs every task under `condition_md`
3. runs the same tasks under `condition_mcp`
4. runs the full matrix in parallel
5. compares:
   - `MD adherence`
   - `MCP adherence`
   - rule-by-rule diff
   - category-level diff
   - `md_only`, `mcp_only`, and shared violations

The comparison axis remains strictly `MD vs MCP` rule adherence.

## MCP Input

The primary Studio flow accepts MCP config as pasted inline JSON only.

This keeps the UI friction low and makes the benchmark input explicit in one screen.

Versioned MCP examples still live in the repo for compatibility and scripted usage:

- `benchmark/profiles/mcp/rippletide.mcp.json`
- `benchmark/profiles/mcp/quick-demo.mcp.json`

## Profiles

Profiles are still versioned in `benchmark/profiles/` for scripted runs, fixtures, and backwards-compatible backend flows.

Current examples:

- `benchmark/profiles/anthropic-demo.json`
- `benchmark/profiles/quick-demo.json`

They are no longer the primary path in the `/studio` UI.

For local validation from the repo root, use:

```bash
pnpm web:test -- --run
```

## Built-In Agents

The primary Studio surface currently exposes:

- `Codex`
- `Claude Code`

The backend still reports full agent availability via `GET /api/agents`.

## Running From The CLI

### Start The Studio

```bash
make studio
```

or

```bash
pnpm studio:start
```

### Run The Legacy Demo Matrix

```bash
make benchmark-demo
```

### Run The Legacy External Matrix With Codex

```bash
make benchmark-codex
```

### Run The Legacy External Matrix With Claude Code

```bash
make benchmark-claude
```

### Compare Legacy Benchmark Reports

```bash
make benchmark-compare
```

### Full Repo Validation

```bash
make check
```

## Outputs

### Legacy benchmark outputs

- per-run: `benchmark/reports/runs/<task_id>-<condition>/`
- aggregate: `benchmark/reports/aggregate/<timestamp>/`

### Studio outputs

- run folders: `benchmark/reports/studio_runs/<run_id>/`
- exports: `benchmark/reports/studio_runs/<run_id>-export.zip`

Each Studio run may contain:

- `state.json`
- `summary.json`
- `studio_events.jsonl`
- `bundle/`
- per-task run folders under `runs/`

## How To Read The Result

For a successful benchmark run, focus on:

- `precheck.missing_rules`
- `md_summary.adherence_rate`
- `mcp_summary.adherence_rate`
- `rule_comparisons`
- `category_comparisons`
- `violations`

Interpretation:

- if `MCP` adherence is higher than `MD`, MCP is helping the agent respect the rules better
- if `MD` and `MCP` are close, the delivery method is not materially changing behavior
- if many rules are missing from MCP during precheck, the comparison is weakened and should be treated carefully

## Realistic Limitations

The Studio does not benchmark every possible repo perfectly.

It runs best when the target repo has a detectable test runner:

- `vitest`
- `jest`
- `pytest`

If no supported runner is found, the Studio can still complete precheck and MCP coverage diagnostics, but the execution path becomes limited.

The benchmark is currently strongest on operational and behavioral rules such as:

- validation discipline
- user-change preservation
- protected file safety
- tool usage discipline
- destructive command avoidance

It is less suitable than a hardcoded domain-specific suite for extremely product-specific regressions.

## Troubleshooting

### The backend does not start

Use:

```bash
make setup
make studio-server
```

If that works, prefer `make studio` afterward so backend and frontend start together from the repo-managed environment.

### Codex or Claude Code is not available

Check:

- `GET /api/agents`
- the Studio UI availability badges

You need the relevant CLI installed and authenticated locally.

### The MCP coverage is low

This usually means one of:

- the MCP source is incomplete
- the `.md` has rules not represented in MCP
- the MCP export command returned stale or partial data

In that case:

1. fix the MCP source if possible
2. rerun precheck
3. only continue to benchmark if the warning is acceptable for your use case

## Useful Files

- architecture: `docs/architecture.md`
- integration details: `docs/integration.md`
- scoring: `docs/scoring.md`
- adding tasks: `docs/adding_tasks.md`
- scripts overview: `scripts/README.md`

## Recommended Workflow For Teams

1. put recurring setups into `benchmark/profiles/`
2. prefer MCP `file` or `command` over `inline` for serious runs
3. use the Studio precheck before every benchmark
4. export the run bundle when sharing results
5. compare `MD` vs `MCP` on rule adherence, not only task success
