# Evaluation Walkthrough

This guide walks through a complete evaluation from scratch: finding a GitHub repo, generating tasks from its PR history, and running a full MD vs MCP benchmark.

## Prerequisites

- Python venv set up (`make setup` from repo root)
- `claude` CLI installed and authenticated
- `GITHUB_TOKEN` env var set (for private repos or to avoid rate limits)
- MCP agent ID (e.g. your email: `fan@rippletide.com`)

---

## Step 1 — Pick a GitHub repo

You need a repo that has:
- Active merged PRs with real code changes (feat, fix, refactor — not just docs or config)
- A test suite (vitest, jest, or pytest) so there's real ground truth to validate against

The harness automatically skips maintenance-only PRs and PRs with empty diffs. You don't need "Fixes #N" in PR bodies — any PR with implementation files and tests qualifies.

Skipped prefixes (both `chore:` and `chore(` styles are caught):
- `chore`, `docs`, `ci`, `build`, `style`, `release`, `bump`, `revert`
- PR titles containing: copyright, license, codeowners, changelog, .gitignore, workflow

Good candidates:
- `anthropics/claude-plugins-official`
- `google/a2ui`
- Your own private repo

What makes a good task: a small, targeted PR (under ~300 lines changed) that modifies implementation files and includes or touches tests.

---

## Step 2 — Generate tasks from it

```bash
cd ~/projects/benchmark-code-mcp

GITHUB_TOKEN=ghp_xxx \
.venv/bin/python -m harness.cli generate-tasks \
  --repo owner/repo \
  --project-root my-benchmark \
  --max-tasks 10 \
  --generate-rules \
  --num-rules 40
```

This:
1. Clones the repo into `~/projects/my-benchmark/`
2. Fetches up to 250 merged PRs from GitHub, skips maintenance commits
3. For each qualifying PR: splits files into test vs implementation, creates a reverse-diff patch, writes a prompt from the PR title and description, writes the task JSON
4. Scaffolds `benchmark/tasks/`, `benchmark/prompts/`, `benchmark/fixtures/`, `protected/canary.env`
5. **`--generate-rules`**: inspects the cloned repo (README, language markers, test framework, file tree) and calls `claude -p` to generate 40 coding rules tailored to that specific codebase. Written to `benchmark/instructions/condition_md/instructions.md`. These become the rules the MD condition injects into the agent's prompt — and that the MCP condition is evaluated against.

Omit `--generate-rules` if you want to supply your own instruction file manually via `--instructions-source` at run time.

Output looks like:
```
Cloning owner/repo into ~/projects/my-benchmark ...
Fetching qualifying PRs from GitHub ...
Found 23 qualifying PRs, generating up to 10 tasks ...
  [1] pr_819_fix_promise_for_angular_renderer_actions
  [2] pr_798_enforce_that_tabs_have_at_least_one_item
  ...
Generating 40 tailored rules for owner/repo ...
  Written to ~/projects/my-benchmark/benchmark/instructions/condition_md/instructions.md
Generated 10 tasks in ~/projects/my-benchmark
```

---

## Step 3 — Check what tasks were created

```bash
.venv/bin/python -m harness.cli list-tasks \
  --project-root ~/projects/my-benchmark
```

---

## Step 4 — Dry run to verify setup (no API cost)

Pick one task ID from the list above and confirm the workspace, patch, and scoring pipeline all work:

```bash
.venv/bin/python -m harness.cli run-task \
  --project-root ~/projects/my-benchmark \
  --task <task_id> \
  --condition condition_md \
  --runner demo
```

Check the output:
```bash
cat ~/projects/my-benchmark/benchmark/reports/runs/<task_id>-condition_md/summary.json
```

If it ran without errors, the workspace is healthy. `--runner demo` uses a fake agent — no API cost.

---

## Step 5 — Real run, MD condition (rules injected inline)

The MD condition injects all rules directly into the agent's prompt context before it starts coding.
`--auto-sync-mcp` also pushes the rules into the MCP graph — run this once per instructions change to keep both conditions in sync.

```bash
.venv/bin/python -m harness.cli run-task \
  --project-root ~/projects/my-benchmark \
  --task <task_id> \
  --condition condition_md \
  --runner claude \
  --instructions-source ~/projects/rippletide-platform \
  --mcp-agent-id fan@rippletide.com \
  --auto-sync-mcp
```

---

## Step 6 — Real run, MCP condition (rules retrieved from graph)

The MCP condition does NOT inject rules into the prompt. The agent must call `recall` on the MCP server to fetch them. If it skips `recall`, it codes without knowing the rules — and will score lower on instruction adherence.

```bash
.venv/bin/python -m harness.cli run-task \
  --project-root ~/projects/my-benchmark \
  --task <task_id> \
  --condition condition_mcp \
  --runner claude \
  --instructions-source ~/projects/rippletide-platform \
  --mcp-agent-id fan@rippletide.com
```

---

## Step 7 — Run all tasks at once

```bash
.venv/bin/python -m harness.cli run-all \
  --project-root ~/projects/my-benchmark \
  --conditions condition_md condition_mcp \
  --runner claude \
  --instructions-source ~/projects/rippletide-platform \
  --mcp-agent-id fan@rippletide.com \
  --auto-sync-mcp \
  --max-workers 2
```

---

## Step 8 — Compare results

```bash
.venv/bin/python -m harness.cli compare \
  --runs-dir ~/projects/my-benchmark/benchmark/reports/runs
```

Then read the aggregate report:
```bash
cat ~/projects/my-benchmark/benchmark/reports/aggregate/*/comparison.md
```

The key numbers to compare across conditions:

| Metric | MD | MCP |
|---|---|---|
| `task_success` rate | X% | X% |
| `normalized_score` avg | 0.XX | 0.XX |
| `instruction_adherence_rate` | 0.XX | 0.XX |
| `hard_violation_count` total | N | N |

If MCP `instruction_adherence_rate` is higher than MD, the knowledge graph is helping the agent follow rules better than inline injection. If they are close, the delivery method is not making a material difference.

---

## Reference: available CLI flags

```
generate-tasks
  --repo            GitHub owner/repo (required)
  --project-root    Output directory; bare names resolve to ~/projects/<name>
  --max-tasks       Max tasks to generate (default: 20)
  --since           Only PRs merged after this date (YYYY-MM-DD)
  --generate-rules  Generate tailored coding rules for this repo after cloning
  --num-rules       Number of rules to generate (default: 40)

list-tasks
  --project-root    Project to list tasks from

run-task
  --task            Task ID (required)
  --condition       condition_md | condition_mcp (required)
  --runner          demo | claude | codex | external
  --instructions-source  Path to repo, file, or .zip with CLAUDE.md / AGENTS.md
  --mcp-agent-id    Agent ID for MCP graph (e.g. fan@rippletide.com)
  --mcp-base-url    MCP server base URL (default: https://mcp.rippletide.com)
  --auto-sync-mcp   Push instructions to MCP graph before running
  --project-root    Project root (default: harness repo)
  --adapter-cmd     Custom adapter command (external runner only)

run-all
  --conditions      One or both of: condition_md condition_mcp
  --max-workers     Parallel workers (default: 1)
  (all other run-task flags apply)

compare
  --runs-dir        Path to runs directory
  --project-root    Project root for loading tasks (default: harness repo)
```
