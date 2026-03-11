import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BenchmarkStudioPage } from './BenchmarkStudioPage';

class MockEventSource {
  static instances: MockEventSource[] = [];

  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  url: string;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close(): void {}

  emit(data: unknown): void {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent<string>);
  }
}

function buildAgentCatalog(
  overrides: Partial<{
    default_external_agent: 'codex' | 'claude' | 'custom';
    agents: Array<Record<string, unknown>>;
  }> = {}
) {
  return {
    default_external_agent: 'codex',
    agents: [
      {
        key: 'codex',
        label: 'Codex',
        description: 'OpenAI Codex CLI benchmark adapter.',
        available: true,
        authenticated: true,
        default_for_external: true,
        command_preview: null,
        auth_message: 'Logged in using ChatGPT',
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
        auth_message: 'Claude Code detected',
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
        auth_message: 'Provide a full adapter command.',
        requires_custom_command: true,
      },
    ],
    ...overrides,
  };
}

function buildBenchmarkSummary() {
  return {
    run_id: 'run-123',
    status: 'completed',
    source_root: '/tmp/repo',
    runnable_task_count: 3,
    inputs: {
      agent_backend: 'codex',
      mcp_source_type: 'inline',
      runner_kind: 'external',
    },
    precheck: {
      total_rules: 4,
      benchmarkable_rules: 3,
      excluded_rules: 1,
      covered_rules: 3,
      missing_rules: 0,
      ambiguous_rules: 0,
      requires_confirmation: false,
      thresholds: {
        missing_count: 5,
        missing_percent: 0.1,
      },
      rules: [
        {
          rule_id: 'benchmark-agents-1',
          source_rule_id: 'agents-1',
          category: 'validation',
          severity: 'hard',
          benchmarkable: true,
          benchmark_family: 'validate_before_conclude',
          normalized_claim: 'validate before conclude',
          raw_text: 'Validate before concluding.',
          source_file: 'AGENTS.md',
          non_benchmarkable_reason: '',
          coverage: {
            status: 'covered',
            evidence_source: 'manifest',
            explanation: 'Covered by the MCP manifest.',
          },
        },
      ],
    },
    md_summary: {
      rule_count: 3,
      adherence_rate: 0.66,
      pass_count: 2,
      partial_count: 0,
      fail_count: 1,
    },
    mcp_summary: {
      rule_count: 3,
      adherence_rate: 0.88,
      pass_count: 3,
      partial_count: 0,
      fail_count: 0,
    },
    category_comparisons: [
      {
        category: 'validation',
        md_rate: 0.66,
        mcp_rate: 0.88,
        delta: 0.22,
        rule_count: 3,
      },
    ],
    rule_comparisons: [
      {
        rule_id: 'benchmark-agents-1',
        category: 'validation',
        md_verdict: 'fail',
        mcp_verdict: 'pass',
        delta: 1,
        md_result: {
          verdict: 'fail',
          ratio: 0,
          evidence: ['MD failed to validate.'],
        },
        mcp_result: {
          verdict: 'pass',
          ratio: 1,
          evidence: ['MCP validated successfully.'],
        },
      },
    ],
    violations: {
      md_only: ['benchmark-agents-1'],
      mcp_only: [],
      shared: [],
    },
    benchmark_runtime_ms: 80000,
    runs: [
      {
        run_id: 'benchmark-agents-1-condition_md',
        task_id: 'benchmark-agents-1',
        condition: 'condition_md',
        normalized_score: 0,
        task_success: false,
        hard_violation_count: 1,
      },
      {
        run_id: 'benchmark-agents-1-condition_mcp',
        task_id: 'benchmark-agents-1',
        condition: 'condition_mcp',
        normalized_score: 1,
        task_success: true,
        hard_violation_count: 0,
      },
    ],
  };
}

describe('BenchmarkStudioPage', () => {
  beforeEach(() => {
    MockEventSource.instances.length = 0;
    vi.stubGlobal('EventSource', MockEventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the simplified one-shot flow and hides the old precheck path', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => buildAgentCatalog() });
    vi.stubGlobal('fetch', fetchMock);

    render(<BenchmarkStudioPage />);

    expect(
      screen.getByRole('heading', { name: /paste the rules\. paste the mcp\. run\./i })
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/agents');
    });

    expect(screen.queryByText(/run precheck/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/select a profile/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /run benchmark/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /codex/i })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(screen.getByText(/leave this empty to benchmark against the current showcase repo/i)).toBeInTheDocument();
  });

  it('requires markdown and valid json before enabling run', async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => buildAgentCatalog() });
    vi.stubGlobal('fetch', fetchMock);

    render(<BenchmarkStudioPage />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/agents');
    });

    const runButton = screen.getByRole('button', { name: /run benchmark/i });
    const markdownField = screen.getByLabelText(/markdown brief/i);
    const mcpField = screen.getByLabelText(/mcp json config/i);

    expect(runButton).toBeDisabled();

    await user.type(markdownField, 'Validate before concluding.');
    fireEvent.change(mcpField, { target: { value: '{bad json' } });

    expect(screen.getByText(/mcp json is invalid/i)).toBeInTheDocument();
    expect(runButton).toBeDisabled();

    fireEvent.change(mcpField, {
      target: {
        value: '{"mcpServers":{"demo":{"type":"http","url":"https://mcp.example.test"}}}',
      },
    });

    await waitFor(() => {
      expect(runButton).toBeEnabled();
    });
  });

  it('submits a single /api/runs request and renders live progress plus final results', async () => {
    const user = userEvent.setup();
    let runLookupCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (input === '/api/agents') {
        return {
          ok: true,
          json: async () => buildAgentCatalog(),
        };
      }

      if (input === '/api/runs') {
        return {
          ok: true,
          json: async () => ({ run_id: 'run-123', status: 'queued' }),
        };
      }

      if (input === '/api/runs/run-123') {
        runLookupCount += 1;
        return {
          ok: true,
          json: async () =>
            runLookupCount >= 3
              ? { run_id: 'run-123', status: 'completed', summary: buildBenchmarkSummary() }
              : { run_id: 'run-123', status: 'running' },
        };
      }

      throw new Error(`Unexpected fetch call: ${String(input)}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<BenchmarkStudioPage />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/agents');
    });

    await user.type(screen.getByLabelText(/markdown brief/i), 'Validate before concluding.');
    fireEvent.change(screen.getByLabelText(/mcp json config/i), {
      target: {
        value: '{"mcpServers":{"demo":{"type":"http","url":"https://mcp.example.test"}}}',
      },
    });
    await user.click(screen.getByRole('button', { name: /run benchmark/i }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some((call) => call[0] === '/api/runs')).toBe(true);
    });

    const createCall = fetchMock.mock.calls.find((call) => call[0] === '/api/runs');
    const formData = createCall?.[1] && (createCall[1] as { body?: FormData }).body;

    expect(formData).toBeInstanceOf(FormData);
    expect(formData?.get('runner_kind')).toBe('external');
    expect(formData?.get('agent_backend')).toBe('codex');
    expect(formData?.get('max_workers')).toBe('8');
    expect(formData?.get('repo_path')).toBeNull();
    expect(formData?.getAll('instruction_files')).toHaveLength(1);
    expect((formData?.get('instruction_files') as { name?: string } | null)?.name).toBe(
      'pasted-instructions.md'
    );
    expect(fetchMock.mock.calls.some((call) => call[0] === '/api/precheck')).toBe(false);
    expect(fetchMock.mock.calls.some((call) => call[0] === '/api/benchmark')).toBe(false);

    expect(MockEventSource.instances[0]?.url).toBe('/api/runs/run-123/events');

    await act(async () => {
      MockEventSource.instances[0].emit({
        event_type: 'precheck_ready',
        payload: {
          precheck: {
            total_rules: 4,
            benchmarkable_rules: 3,
            excluded_rules: 1,
            covered_rules: 3,
            missing_rules: 0,
            ambiguous_rules: 0,
            requires_confirmation: false,
            thresholds: {
              missing_count: 5,
              missing_percent: 0.1,
            },
            rules: [],
          },
        },
      });
      MockEventSource.instances[0].emit({
        event_type: 'task_completed',
        payload: {
          task_id: 'benchmark-agents-1',
          condition: 'condition_md',
          completed_tasks: 1,
          total_tasks: 6,
          estimated_remaining_seconds: 24,
        },
      });
      MockEventSource.instances[0].emit({
        event_type: 'stream_closed',
        payload: { status: 'completed' },
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/MD adherence/i)).toBeInTheDocument();
      expect(screen.getByText(/Tasks generated/i)).toBeInTheDocument();
      expect(screen.getAllByText(/88%/i).length).toBeGreaterThan(0);
      expect(screen.getByText('1/6')).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /export latest run bundle/i })).toHaveAttribute(
        'href',
        '/api/runs/run-123/export'
      );
    });
  });

  it('disables unavailable agents and falls back to an available default', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () =>
        buildAgentCatalog({
          default_external_agent: 'claude',
          agents: [
            {
              key: 'codex',
              label: 'Codex',
              description: 'OpenAI Codex CLI benchmark adapter.',
              available: true,
              authenticated: true,
              default_for_external: false,
              command_preview: null,
              auth_message: 'Logged in using ChatGPT',
              requires_custom_command: false,
            },
            {
              key: 'claude',
              label: 'Claude Code',
              description: 'Anthropic Claude Code CLI benchmark adapter.',
              available: true,
              authenticated: false,
              default_for_external: true,
              command_preview: null,
              auth_message: 'Claude login required',
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
              auth_message: 'Provide a full adapter command.',
              requires_custom_command: true,
            },
          ],
        }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<BenchmarkStudioPage />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/agents');
    });

    expect(screen.getByRole('button', { name: /claude code/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /codex/i })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(screen.getByText(/connect this agent in the backend first/i)).toBeInTheDocument();
  });
});
