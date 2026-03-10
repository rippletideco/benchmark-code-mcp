# Northstar Ops Benchmark Repository

Northstar Ops is a compact benchmark repository for comparing coding-agent behavior under two instruction-delivery conditions:

- `condition_md`: markdown/system-prompt style instruction injection
- `condition_mcp`: structured MCP-style context injection

The comparison target is not general model quality. The benchmark is designed to surface instruction-following, repo awareness, validation discipline, safety behavior, and end-to-end completion.

## Repository Layout

- `web/`: Vite + React + TypeScript dashboard app used as the coding target
- `benchmark/`: task specs, prompts, condition bundles, fixtures, policy, and generated reports
- `harness/`: Python orchestration, logging, scoring, reporting, and adapter interfaces
- `protected/`: canary and instruction-safety files that normal tasks must not touch
- `docs/`: architecture, task-authoring, scoring, and integration guidance

## Setup

```bash
make setup
```

That installs the web dependencies with `pnpm`, creates `.venv`, and installs the editable Python harness with `pytest`.

## Common Commands

```bash
make web-dev
make check
make benchmark-demo
make benchmark-compare
make benchmark-codex
```

Equivalent direct commands:

```bash
pnpm --dir web lint
pnpm --dir web typecheck
pnpm --dir web test --run
.venv/bin/pytest harness/tests
.venv/bin/python -m harness.cli run-all --runner demo --conditions condition_md condition_mcp
.venv/bin/python -m harness.cli compare --runs-dir benchmark/reports/runs
.venv/bin/python -m harness.cli run-all --runner external --conditions condition_md condition_mcp --adapter-cmd "python3 scripts/adapter_codex.py {request_file}"
```

## Benchmark Commands

Run one task:

```bash
.venv/bin/python -m harness.cli run-task \
  --task mobile_drawer_route_close \
  --condition condition_mcp \
  --runner demo
```

Run the full demo matrix:

```bash
make benchmark-demo
```

Compare generated runs:

```bash
make benchmark-compare
```

Run the real Codex CLI benchmark:

```bash
codex login
make benchmark-codex
```

## Output Locations

- Per-run artifacts: `benchmark/reports/runs/<task_id>-<condition>/`
- Aggregate comparison artifacts: `benchmark/reports/aggregate/<timestamp>/`
- Raw event log: `events.jsonl`
- Machine-readable summary: `summary.json`
- Human-readable report: `report.md`, `report.html`
- Aggregate comparison: `comparison.json`, `comparison.csv`, `comparison.md`

## What Ships In The App

The product app is intentionally realistic but compact:

- shell navigation in `web/src/components/shell/`
- feature pages in `web/src/features/{dashboard,orders,customers,settings}/`
- reusable design-system primitives in `web/src/components/ui/`
- internal API and mock data under `web/src/lib/api/`
- shared validation in `web/src/lib/forms/`
- colocated `*.test.tsx` files plus `*.benchmark.test.tsx` task validators

The source tree stays green. Each benchmark task applies a regression patch in a temp workspace, then the harness runs the selected condition against that seeded breakage. The task suite now includes 24 auto-checkable scenarios spanning shell behavior, customers, dashboard, orders, settings, protected-file safety, and dirty-worktree preservation.

## Current Demo Behavior

The built-in demo adapters are synthetic on purpose:

- `condition_mcp` performs the clean reverse-fix path and validates before concluding.
- `condition_md` intentionally includes a few softer and harder mistakes on selected tasks so the scoring/reporting pipeline produces a visible comparison.

These demo outputs are useful for validating the benchmark plumbing, not for making product claims.

## Next Steps For Real Integrations

- The markdown condition reads every `.md` file present in [benchmark/instructions/condition_md](/Users/guillaume_deramchi/Documents/mcp-code-rippletide-showcase/benchmark/instructions/condition_md).
- The MCP condition reads every `.json` file present in [benchmark/instructions/condition_mcp](/Users/guillaume_deramchi/Documents/mcp-code-rippletide-showcase/benchmark/instructions/condition_mcp) and automatically enables any JSON object that contains a top-level `mcpServers` block.
- The real Codex adapter lives in [adapter_codex.py](/Users/guillaume_deramchi/Documents/mcp-code-rippletide-showcase/scripts/adapter_codex.py) and is invoked by `make benchmark-codex`.
- The Codex adapter adds a benchmark wrapper that tells Codex to inspect the actual repo and prefer observed repo state if the injected context conflicts with the benchmark repo.
- Plug a real markdown/system-prompt runtime into the external adapter boundary while keeping `MdConditionRunner`.
- Plug a real MCP runtime/context provider into the same external adapter boundary while keeping `McpConditionRunner`.
- Keep the task specs, detectors, and reports unchanged.

See [architecture](docs/architecture.md), [integration](docs/integration.md), [scoring](docs/scoring.md), and [adding tasks](docs/adding_tasks.md).
