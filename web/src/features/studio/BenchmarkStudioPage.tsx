import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { InlineNotice } from '../../components/ui/InlineNotice';
import {
  buildStudioEventsUrl,
  buildStudioExportUrl,
  createStudioRun,
  getAgentCatalog,
  getStudioRun,
} from '../../lib/studio/api';
import type {
  AgentBackendStatus,
  BenchmarkPrecheckResponse,
  BenchmarkRuleCoverageItem,
  CreateStudioRunInput,
  StudioEventEnvelope,
  StudioRunDetails,
} from '../../lib/studio/types';
import styles from './BenchmarkStudioPage.module.css';

type VisibleAgentKey = 'codex' | 'claude';
type VisibleAgentStatus = AgentBackendStatus & { key: VisibleAgentKey };

const DEFAULT_MCP_JSON = `{
  "mcpServers": {
    "rippletide": {
      "type": "http",
      "url": "https://mcp.rippletide.com/mcp"
    }
  }
}`;

const FALLBACK_AGENTS: AgentBackendStatus[] = [
  {
    key: 'codex',
    label: 'Codex',
    description: 'OpenAI Codex CLI benchmark adapter.',
    available: true,
    authenticated: true,
    default_for_external: true,
    command_preview: null,
    auth_message: 'Default external agent.',
    requires_custom_command: false,
  },
  {
    key: 'claude',
    label: 'Claude Code',
    description: 'Anthropic Claude Code CLI benchmark adapter.',
    available: true,
    authenticated: true,
    default_for_external: false,
    command_preview: null,
    auth_message: 'Detected from the backend at runtime.',
    requires_custom_command: false,
  },
  {
    key: 'custom',
    label: 'Custom command',
    description: 'Any adapter command that implements the benchmark NDJSON contract.',
    available: true,
    authenticated: false,
    default_for_external: false,
    command_preview: null,
    auth_message: 'Provide an adapter command.',
    requires_custom_command: true,
  },
];

function isVisibleAgent(agent: AgentBackendStatus): agent is VisibleAgentStatus {
  return agent.key === 'codex' || agent.key === 'claude';
}

function isAgentSelectable(agent: VisibleAgentStatus | null | undefined): boolean {
  return Boolean(agent?.available && agent.authenticated);
}

function formatPercent(value: number | undefined): string {
  if (typeof value !== 'number') {
    return 'Pending';
  }
  return `${Math.round(value * 100)}%`;
}

function formatDisplayLabel(value: string): string {
  const normalized = value.replaceAll('_', ' ');
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function formatEventLabel(eventType: string): string {
  const label = eventType.replaceAll('_', ' ');
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function getCoverageStatusClass(
  status: BenchmarkRuleCoverageItem['coverage']['status']
): string {
  switch (status) {
    case 'covered':
      return styles.statusCovered;
    case 'missing':
      return styles.statusMissing;
    case 'ambiguous':
      return styles.statusAmbiguous;
    case 'not_applicable':
      return styles.statusNeutral;
    default:
      return '';
  }
}

function getNumber(
  payload: Record<string, unknown> | undefined,
  key: string
): number | undefined {
  const value = payload?.[key];
  return typeof value === 'number' ? value : undefined;
}

function getString(
  payload: Record<string, unknown> | undefined,
  key: string
): string | undefined {
  const value = payload?.[key];
  return typeof value === 'string' ? value : undefined;
}

function buildInput(
  repoPath: string,
  instructionMarkdown: string,
  mcpJson: string,
  agentBackend: VisibleAgentKey
): CreateStudioRunInput {
  return {
    repoPath,
    instructionMarkdown,
    mcpJson,
    agentBackend,
  };
}

function describeEvent(event: StudioEventEnvelope): string {
  switch (event.event_type) {
    case 'run_created':
      return 'The run is queued and waiting for the harness.';
    case 'precheck_ready': {
      const precheck = event.payload?.precheck;
      if (precheck && typeof precheck === 'object') {
        const precheckPayload = precheck as Record<string, unknown>;
        const benchmarkableRules = getNumber(precheckPayload, 'benchmarkable_rules');
        const coveredRules = getNumber(precheckPayload, 'covered_rules');
        if (benchmarkableRules != null && coveredRules != null) {
          return `${coveredRules}/${benchmarkableRules} benchmarkable rules mapped before execution.`;
        }
      }
      return 'Coverage snapshot completed.';
    }
    case 'task_completed': {
      const taskId = getString(event.payload, 'task_id');
      const condition = getString(event.payload, 'condition');
      const completedTasks = getNumber(event.payload, 'completed_tasks');
      const totalTasks = getNumber(event.payload, 'total_tasks');
      if (taskId && condition && completedTasks != null && totalTasks != null) {
        return `${taskId} finished for ${condition}. Progress ${completedTasks}/${totalTasks}.`;
      }
      return 'One condition run finished.';
    }
    case 'run_failed':
      return getString(event.payload, 'error') ?? 'The run failed.';
    default:
      return 'Harness activity received.';
  }
}

export function BenchmarkStudioPage(): JSX.Element {
  const [agents, setAgents] = useState<AgentBackendStatus[]>(FALLBACK_AGENTS);
  const [selectedAgentKey, setSelectedAgentKey] = useState<VisibleAgentKey>('codex');
  const [repoPath, setRepoPath] = useState('');
  const [instructionMarkdown, setInstructionMarkdown] = useState('');
  const [mcpJson, setMcpJson] = useState(DEFAULT_MCP_JSON);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [runDetails, setRunDetails] = useState<StudioRunDetails | null>(null);
  const [events, setEvents] = useState<StudioEventEnvelope[]>([]);
  const eventSourceRef = useRef<EventSource | null>(null);

  const visibleAgents = useMemo(
    () => agents.filter(isVisibleAgent),
    [agents]
  );
  const selectedAgent = useMemo(
    () => visibleAgents.find((agent) => agent.key === selectedAgentKey) ?? null,
    [selectedAgentKey, visibleAgents]
  );
  const markdownIssue =
    instructionMarkdown.trim().length > 0 ? null : 'Paste the markdown brief to run the benchmark.';
  const mcpJsonIssue = useMemo(() => {
    if (mcpJson.trim().length === 0) {
      return 'Paste the MCP JSON config.';
    }
    try {
      JSON.parse(mcpJson);
      return null;
    } catch {
      return 'MCP JSON is invalid.';
    }
  }, [mcpJson]);
  const runSummary = runDetails?.summary;
  const latestPrecheckEvent = useMemo(
    () => events.find((event) => event.event_type === 'precheck_ready') ?? null,
    [events]
  );
  const coverageSnapshot = useMemo(() => {
    if (runSummary?.precheck) {
      return runSummary.precheck;
    }
    const precheck = latestPrecheckEvent?.payload?.precheck;
    if (precheck && typeof precheck === 'object') {
      return precheck as BenchmarkPrecheckResponse['precheck'];
    }
    return null;
  }, [latestPrecheckEvent, runSummary]);
  const latestTaskCompletedEvent = useMemo(
    () => events.find((event) => event.event_type === 'task_completed') ?? null,
    [events]
  );
  const liveProgress = useMemo(() => {
    const completedTasks = getNumber(latestTaskCompletedEvent?.payload, 'completed_tasks');
    const totalTasks = getNumber(latestTaskCompletedEvent?.payload, 'total_tasks');
    const remainingSeconds = getNumber(
      latestTaskCompletedEvent?.payload,
      'estimated_remaining_seconds'
    );

    if (completedTasks != null && totalTasks != null) {
      return {
        value: `${completedTasks}/${totalTasks}`,
        helper:
          remainingSeconds != null
            ? `Estimated ${Math.max(Math.round(remainingSeconds), 0)}s remaining`
            : 'Condition runs are progressing.',
      };
    }

    if (runSummary?.runs && runSummary.runnable_task_count != null) {
      return {
        value: `${runSummary.runs.length}/${runSummary.runnable_task_count * 2}`,
        helper: 'Completed condition runs.',
      };
    }

    return {
      value: formatDisplayLabel(runDetails?.status ?? 'idle'),
      helper: 'Live progress updates appear here while the run is active.',
    };
  }, [latestTaskCompletedEvent, runDetails?.status, runSummary]);
  const generatedTaskCount = runSummary?.runnable_task_count ?? coverageSnapshot?.benchmarkable_rules;
  const exportHref = runId ? buildStudioExportUrl(runId) : null;
  const canSubmit =
    !submitting && markdownIssue == null && mcpJsonIssue == null && isAgentSelectable(selectedAgent);

  useEffect(() => {
    void getAgentCatalog()
      .then((payload) => {
        setAgents(payload.agents);
      })
      .catch((catalogLookupError) => {
        const message =
          catalogLookupError instanceof Error
            ? catalogLookupError.message
            : 'Failed to load the agent catalog.';
        setCatalogError(message);
      });
  }, []);

  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  useEffect(() => {
    if (isAgentSelectable(selectedAgent)) {
      return;
    }

    const nextAgent =
      visibleAgents.find((agent) => agent.default_for_external && isAgentSelectable(agent)) ??
      visibleAgents.find((agent) => isAgentSelectable(agent)) ??
      visibleAgents[0];

    if (nextAgent && nextAgent.key !== selectedAgentKey) {
      setSelectedAgentKey(nextAgent.key);
    }
  }, [selectedAgent, selectedAgentKey, visibleAgents]);

  async function refreshRun(runIdentifier: string): Promise<void> {
    const details = await getStudioRun(runIdentifier);
    setRunDetails(details);
  }

  function connectToEvents(runIdentifier: string): void {
    eventSourceRef.current?.close();
    const eventSource = new EventSource(buildStudioEventsUrl(runIdentifier));
    eventSourceRef.current = eventSource;
    eventSource.onmessage = (message) => {
      try {
        const payload = JSON.parse(message.data) as StudioEventEnvelope;
        if (payload.event_type === 'stream_closed') {
          void refreshRun(runIdentifier);
          eventSource.close();
          return;
        }
        setEvents((current) => [payload, ...current].slice(0, 20));
        void refreshRun(runIdentifier);
      } catch {
        setEvents((current) => [
          {
            event_type: 'client_parse_warning',
            payload: { raw: message.data },
          },
          ...current,
        ]);
      }
    };
    eventSource.onerror = () => {
      eventSource.close();
    };
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!canSubmit || selectedAgent == null) {
      return;
    }

    eventSourceRef.current?.close();
    setSubmitting(true);
    setError(null);
    setRunId(null);
    setRunDetails(null);
    setEvents([]);

    try {
      const response = await createStudioRun(
        buildInput(repoPath, instructionMarkdown, mcpJson, selectedAgent.key)
      );
      setRunId(response.run_id);
      await refreshRun(response.run_id);
      connectToEvents(response.run_id);
    } catch (submitError) {
      const message = submitError instanceof Error ? submitError.message : 'Unknown benchmark error.';
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className={styles.page}>
      <div className={styles.hero}>
        <Card className={styles.heroPrimary}>
          <span className={styles.eyebrow}>Benchmark Studio</span>
          <h2 className={styles.title}>Paste the rules. Paste the MCP. Run.</h2>
          <p className={styles.copy}>
            The Studio now runs in one shot: pick the agent, optionally point to a sandbox repo,
            then let the harness generate tasks, validations, and the final MD-vs-MCP report.
          </p>
        </Card>

        <Card className={styles.heroSecondary}>
          <span className={styles.metricLabel}>Flow</span>
          <ol className={styles.heroList}>
            <li>Choose Codex or Claude Code.</li>
            <li>Paste the markdown brief and the MCP JSON.</li>
            <li>Optionally set a repo path. Empty falls back to this benchmark repo.</li>
            <li>Run once and review the score, coverage snapshot, and live log.</li>
          </ol>
        </Card>
      </div>

      {catalogError ? <InlineNotice tone="info">{catalogError}</InlineNotice> : null}
      {error ? <InlineNotice tone="error">{error}</InlineNotice> : null}
      {runDetails?.error ? <InlineNotice tone="error">{runDetails.error}</InlineNotice> : null}

      <div className={styles.layout}>
        <Card className={styles.formCard}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionEyebrow}>One-shot setup</span>
            <h3 className={styles.sectionTitle}>Everything needed for a single benchmark run</h3>
          </div>

          <form className={styles.form} onSubmit={(event) => void handleSubmit(event)}>
            <div className={styles.sectionBlock}>
              <div className={styles.blockHeader}>
                <h4 className={styles.blockTitle}>Agent</h4>
                <p className={styles.helper}>
                  One run uses one connected agent. Codex and Claude stay side by side for quick
                  switching.
                </p>
              </div>
              <div className={styles.choiceGrid}>
                {visibleAgents.map((agent) => {
                  const selectable = isAgentSelectable(agent);
                  return (
                    <button
                      key={agent.key}
                      type="button"
                      className={[
                        styles.choiceCard,
                        selectedAgentKey === agent.key ? styles.choiceCardSelected : '',
                        selectable ? '' : styles.choiceCardDisabled,
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      aria-pressed={selectedAgentKey === agent.key}
                      disabled={!selectable}
                      onClick={() => setSelectedAgentKey(agent.key)}
                    >
                      <div className={styles.choiceHeader}>
                        <strong>{agent.label}</strong>
                        <span className={styles.choiceStatus}>
                          {agent.default_for_external ? 'Default' : 'Ready'}
                        </span>
                      </div>
                      <p className={styles.choiceDescription}>{agent.description}</p>
                      <p className={styles.choiceMeta}>
                        {selectable ? agent.auth_message : 'Connect this agent in the backend first.'}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className={styles.sectionBlock}>
              <div className={styles.blockHeader}>
                <h4 className={styles.blockTitle}>Sandbox repo</h4>
                <p className={styles.helper}>
                  Leave this empty to benchmark against the current showcase repo.
                </p>
              </div>
              <label className={styles.field}>
                <span className={styles.label}>Repo path</span>
                <input
                  className={styles.input}
                  placeholder="/Users/you/Documents/your-repo"
                  value={repoPath}
                  onChange={(inputEvent) => setRepoPath(inputEvent.target.value)}
                />
              </label>
            </div>

            <div className={styles.sectionBlock}>
              <div className={styles.blockHeader}>
                <h4 className={styles.blockTitle}>Inputs</h4>
                <p className={styles.helper}>
                  The markdown brief is required and the MCP config is sent inline as JSON.
                </p>
              </div>
              <label className={styles.field}>
                <span className={styles.label}>Markdown brief</span>
                <textarea
                  className={styles.textarea}
                  rows={10}
                  value={instructionMarkdown}
                  placeholder="Paste the benchmark markdown, AGENTS rules, or the exact brief to compare."
                  onChange={(inputEvent) => setInstructionMarkdown(inputEvent.target.value)}
                />
              </label>
              <label className={styles.field}>
                <span className={styles.label}>MCP JSON config</span>
                <textarea
                  className={styles.textarea}
                  rows={10}
                  value={mcpJson}
                  onChange={(inputEvent) => setMcpJson(inputEvent.target.value)}
                />
              </label>
              {markdownIssue ? <InlineNotice tone="info">{markdownIssue}</InlineNotice> : null}
              {mcpJsonIssue ? <InlineNotice tone="error">{mcpJsonIssue}</InlineNotice> : null}
              {!isAgentSelectable(selectedAgent) ? (
                <InlineNotice tone="error">
                  Connect Codex or Claude Code in the backend before launching a run.
                </InlineNotice>
              ) : null}
            </div>

            <div className={styles.actions}>
              <Button type="submit" disabled={!canSubmit}>
                {submitting ? 'Running…' : 'Run benchmark'}
              </Button>
            </div>
          </form>
        </Card>

        <div className={styles.sideColumn}>
          <Card className={styles.statusCard}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionEyebrow}>Current run</span>
              <h3 className={styles.sectionTitle}>Execution status</h3>
            </div>

            <div className={styles.metricGrid}>
              <div className={styles.metricCard}>
                <span className={styles.metricLabel}>Agent</span>
                <strong className={styles.metricValue}>
                  {runSummary?.inputs?.agent_backend
                    ? formatDisplayLabel(runSummary.inputs.agent_backend)
                    : selectedAgent?.label ?? 'Unavailable'}
                </strong>
              </div>
              <div className={styles.metricCard}>
                <span className={styles.metricLabel}>Tasks generated</span>
                <strong className={styles.metricValue}>
                  {generatedTaskCount ?? 'Pending'}
                </strong>
              </div>
              <div className={styles.metricCard}>
                <span className={styles.metricLabel}>Progress</span>
                <strong className={styles.metricValue}>{liveProgress.value}</strong>
                <span className={styles.metricMeta}>{liveProgress.helper}</span>
              </div>
            </div>

            <dl className={styles.definitionList}>
              <div>
                <dt>Status</dt>
                <dd>{formatDisplayLabel(runDetails?.status ?? 'idle')}</dd>
              </div>
              <div>
                <dt>Source root</dt>
                <dd>
                  {runSummary?.source_root ?? (repoPath.trim() || 'Benchmark repo fallback')}
                </dd>
              </div>
              <div>
                <dt>Run id</dt>
                <dd>{runId ?? 'Not started yet'}</dd>
              </div>
            </dl>

            {exportHref ? (
              <a className={styles.exportLink} href={exportHref}>
                Export latest run bundle
              </a>
            ) : null}
          </Card>

          <Card className={styles.statusCard}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionEyebrow}>Live activity</span>
              <h3 className={styles.sectionTitle}>Readable progress log</h3>
            </div>

            <div className={styles.activityList}>
              {events.length ? (
                events.slice(0, 6).map((event, index) => (
                  <article
                    key={`${event.event_type}-${event.timestamp ?? index}`}
                    className={styles.activityItem}
                  >
                    <div className={styles.activityHeader}>
                      <strong>{formatEventLabel(event.event_type)}</strong>
                      <span>{event.timestamp ?? 'live'}</span>
                    </div>
                    <p className={styles.activityCopy}>{describeEvent(event)}</p>
                  </article>
                ))
              ) : (
                <p className={styles.emptyState}>
                  Launch a run to see task generation, coverage, and condition progress live.
                </p>
              )}
            </div>
          </Card>
        </div>
      </div>

      {runSummary?.md_summary && runSummary?.mcp_summary ? (
        <Card className={styles.resultsCard}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionEyebrow}>Results</span>
            <h3 className={styles.sectionTitle}>MD vs MCP benchmark</h3>
          </div>

          <div className={styles.metricGrid}>
            <div className={styles.metricCard}>
              <span className={styles.metricLabel}>MD adherence</span>
              <strong className={styles.metricValue}>
                {formatPercent(runSummary.md_summary.adherence_rate)}
              </strong>
            </div>
            <div className={styles.metricCard}>
              <span className={styles.metricLabel}>MCP adherence</span>
              <strong className={styles.metricValue}>
                {formatPercent(runSummary.mcp_summary.adherence_rate)}
              </strong>
            </div>
            <div className={styles.metricCard}>
              <span className={styles.metricLabel}>Runtime</span>
              <strong className={styles.metricValue}>
                {Math.round((runSummary.benchmark_runtime_ms ?? 0) / 1000)}s
              </strong>
            </div>
          </div>

          <div className={styles.runGrid}>
            {(runSummary.category_comparisons ?? []).map((category) => (
              <article key={category.category} className={styles.runTile}>
                <span className={styles.runTileHeader}>{formatDisplayLabel(category.category)}</span>
                <strong className={styles.runTileTitle}>MD {formatPercent(category.md_rate)}</strong>
                <strong className={styles.runTileTitle}>MCP {formatPercent(category.mcp_rate)}</strong>
                <span className={styles.runTileMeta}>
                  Delta {Math.round(category.delta * 100)} pts
                </span>
              </article>
            ))}
          </div>

          <details className={styles.detailPanel}>
            <summary className={styles.detailSummary}>Coverage snapshot</summary>
            {coverageSnapshot ? (
              <div className={styles.detailContent}>
                <div className={styles.summaryRow}>
                  <span className={styles.summaryPill}>
                    Benchmarkable {coverageSnapshot.benchmarkable_rules}
                  </span>
                  <span className={styles.summaryPill}>
                    Covered {coverageSnapshot.covered_rules}
                  </span>
                  <span className={styles.summaryPill}>
                    Missing {coverageSnapshot.missing_rules}
                  </span>
                  <span className={styles.summaryPill}>
                    Ambiguous {coverageSnapshot.ambiguous_rules}
                  </span>
                </div>

                <div className={styles.ruleList}>
                  {coverageSnapshot.rules.map((rule) => (
                    <article key={rule.rule_id} className={styles.ruleItem}>
                      <div className={styles.ruleHeader}>
                        <div className={styles.ruleIdentity}>
                          <span className={styles.ruleId}>{rule.rule_id}</span>
                          <div className={styles.ruleMetaRow}>
                            <span className={styles.ruleChip}>
                              {formatDisplayLabel(rule.category)}
                            </span>
                            <span className={styles.ruleChip}>
                              {formatDisplayLabel(rule.severity)}
                            </span>
                            <span className={styles.ruleChip}>
                              {formatDisplayLabel(rule.coverage.evidence_source)}
                            </span>
                          </div>
                        </div>
                        <span
                          className={[
                            styles.statusBadge,
                            getCoverageStatusClass(rule.coverage.status),
                          ]
                            .filter(Boolean)
                            .join(' ')}
                        >
                          {formatDisplayLabel(rule.coverage.status)}
                        </span>
                      </div>
                      <p className={styles.ruleStatement}>{rule.raw_text}</p>
                      <div className={styles.ruleFooter}>
                        <span className={styles.ruleEvidence}>{rule.coverage.explanation}</span>
                        <span className={styles.ruleSource}>Source {rule.source_file}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            ) : (
              <p className={styles.emptyState}>Coverage snapshot not available yet.</p>
            )}
          </details>

          <details className={styles.detailPanel}>
            <summary className={styles.detailSummary}>Rule-by-rule diff</summary>
            <div className={styles.detailContent}>
              {(runSummary.rule_comparisons ?? []).length ? (
                <div className={styles.activityList}>
                  {(runSummary.rule_comparisons ?? []).map((item) => (
                    <article key={item.rule_id} className={styles.activityItem}>
                      <div className={styles.activityHeader}>
                        <strong>{item.rule_id}</strong>
                        <span>{formatDisplayLabel(item.category)}</span>
                      </div>
                      <p className={styles.activityCopy}>
                        MD {item.md_verdict} · MCP {item.mcp_verdict} · Delta{' '}
                        {Math.round(item.delta * 100)} pts
                      </p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className={styles.emptyState}>No rule diff available for this run.</p>
              )}
            </div>
          </details>

          <details className={styles.detailPanel}>
            <summary className={styles.detailSummary}>Raw live log</summary>
            <div className={styles.detailContent}>
              {events.length ? (
                <div className={styles.eventList}>
                  {events.map((event, index) => (
                    <div
                      key={`${event.event_type}-${event.timestamp ?? index}`}
                      className={styles.eventItem}
                    >
                      <div className={styles.eventMeta}>
                        <span>{formatEventLabel(event.event_type)}</span>
                        <span>{event.timestamp ?? 'live'}</span>
                      </div>
                      <pre className={styles.eventPayload}>
                        {JSON.stringify(event.payload ?? {}, null, 2)}
                      </pre>
                    </div>
                  ))}
                </div>
              ) : (
                <p className={styles.emptyState}>No live events recorded for this run.</p>
              )}
            </div>
          </details>
        </Card>
      ) : null}
    </section>
  );
}
