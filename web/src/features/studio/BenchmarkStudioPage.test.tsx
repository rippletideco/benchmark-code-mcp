import { act, render, screen, waitFor } from '@testing-library/react';
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

function buildAgentCatalog() {
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
        command_preview: 'python3 scripts/adapter_codex.py {request_file}',
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
        command_preview: 'python3 scripts/adapter_claude.py {request_file}',
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
  };
}

function buildProfiles() {
  return {
    profiles: [
      {
        id: 'anthropic-demo',
        name: 'Anthropic demo',
        description: 'Included repo plus Claude Code and the shared rippletide MCP profile.',
        target_mode: 'included',
        execution_preset: 'claude',
        instruction_sources: [
          {
            type: 'repo_file',
            path: 'benchmark/profiles/prompts/studio-anthropic.md',
            label: 'Anthropic demo prompt',
          },
        ],
        mcp_source: {
          type: 'file',
          path: 'benchmark/profiles/mcp/rippletide.mcp.json',
        },
        max_workers: 2,
        tags: ['demo', 'anthropic'],
        demo_rank: 100,
        proof_run: {
          run_id: '15ddae9ccd6e',
          status: 'completed',
          inputs: {
            profile_id: 'anthropic-demo',
            profile_name: 'Anthropic demo',
            agent_backend: 'claude',
            runner_kind: 'external',
            mcp_source_type: 'file',
            mcp_source_origin: 'benchmark/profiles/mcp/rippletide.mcp.json',
          },
          benchmark: {
            average_score: 0.8473,
            task_success_rate: 1,
          },
        },
      },
      {
        id: 'quick-demo',
        name: 'Quick demo',
        description: 'Fastest path for testing the included benchmark repo after cloning.',
        target_mode: 'included',
        execution_preset: 'demo',
        instruction_sources: [],
        mcp_source: {
          type: 'file',
          path: 'benchmark/profiles/mcp/rippletide.mcp.json',
        },
        max_workers: 2,
        tags: ['demo', 'quickstart'],
        demo_rank: 20,
        proof_run: null,
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

  it('renders profile-first quick start cards', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => buildAgentCatalog() })
      .mockResolvedValueOnce({ ok: true, json: async () => buildProfiles() });
    vi.stubGlobal('fetch', fetchMock);

    render(<BenchmarkStudioPage />);

    expect(
      screen.getByRole('heading', {
        name: /run reusable benchmark profiles instead of rebuilding the mcp by hand/i,
      })
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/profiles');
    });

    expect(screen.getAllByRole('button', { name: /anthropic demo/i })[0]).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /run selected profile/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /export proof run/i })).toHaveAttribute(
      'href',
      '/api/runs/15ddae9ccd6e/export'
    );
  });

  it('can launch a profile run and then launch a custom one-off run', async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => buildAgentCatalog() })
      .mockResolvedValueOnce({ ok: true, json: async () => buildProfiles() })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ run_id: 'profile-run', status: 'queued' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ run_id: 'profile-run', status: 'running' }) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          run_id: 'profile-run',
          status: 'completed',
          summary: {
            inputs: {
              profile_id: 'anthropic-demo',
              profile_name: 'Anthropic demo',
              agent_backend: 'claude',
              runner_kind: 'external',
              mcp_source_type: 'file',
            },
            benchmark: { average_score: 0.84, task_success_rate: 1 },
            alignment: { issue_count: 4, by_status: { matched: 2 } },
            capabilities: {
              supported: true,
              support_reason: 'Detected a pytest-compatible repository.',
              test_runner: 'pytest',
            },
            runs: [],
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          run_id: 'custom-run',
          status: 'queued',
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ run_id: 'custom-run', status: 'running' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          run_id: 'custom-run',
          status: 'completed',
          summary: {
            inputs: {
              profile_id: null,
              agent_backend: 'custom',
              runner_kind: 'external',
              mcp_source_type: 'command',
            },
            benchmark: { average_score: 0.8, task_success_rate: 1 },
            alignment: { issue_count: 1, by_status: { matched: 1 } },
            capabilities: {
              supported: true,
              support_reason: 'Detected a pytest-compatible repository.',
              test_runner: 'pytest',
            },
            runs: [],
          },
        }),
      });
    vi.stubGlobal('fetch', fetchMock);

    render(<BenchmarkStudioPage />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/profiles');
    });

    await user.click(screen.getByRole('button', { name: /run selected profile/i }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          (call) =>
            call[0] === '/api/profiles/anthropic-demo/run' &&
            (call[1] as { method?: string } | undefined)?.method === 'POST'
        )
      ).toBe(true);
    });
    expect(MockEventSource.instances[0]?.url).toBe('/api/runs/profile-run/events');

    await act(async () => {
      MockEventSource.instances[0].emit({
        event_type: 'stream_closed',
        payload: { status: 'completed' },
      });
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Anthropic demo', level: 4 })).toBeInTheDocument();
      expect(screen.getByText(/84%/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /custom adapter/i }));
    await user.click(screen.getByRole('button', { name: /another local repo/i }));
    await user.type(screen.getByLabelText(/local repo path/i), '/tmp/rippletide-platform');
    await user.click(screen.getByText(/manual instruction and mcp overrides/i));
    await user.selectOptions(screen.getByLabelText(/mcp source type/i), 'command');
    await user.type(screen.getByLabelText(/mcp export command/i), 'python3 scripts/export-mcp.py');
    await user.type(
      screen.getByLabelText(/custom adapter command/i),
      'python3 /abs/path/to/adapter.py {request_file}'
    );
    await user.click(screen.getByRole('button', { name: /launch custom run/i }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          (call) =>
            call[0] === '/api/runs' &&
            (call[1] as { method?: string } | undefined)?.method === 'POST'
        )
      ).toBe(true);
    });
  });
});
