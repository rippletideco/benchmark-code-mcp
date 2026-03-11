export interface CreateStudioRunInput {
  repoPath: string;
  instructionMarkdown: string;
  mcpJson: string;
  agentBackend: 'codex' | 'claude';
}

export interface BenchmarkRuleCoverageItem {
  rule_id: string;
  source_rule_id: string;
  category: string;
  severity: string;
  benchmarkable: boolean;
  benchmark_family?: string | null;
  normalized_claim: string;
  raw_text: string;
  source_file: string;
  non_benchmarkable_reason: string;
  coverage: {
    status: 'covered' | 'missing' | 'ambiguous' | 'not_applicable';
    evidence_source: 'manifest' | 'live_mcp' | 'both' | 'none';
    explanation: string;
  };
}

export interface BenchmarkPrecheckResponse {
  profile_id?: string | null;
  profile_name?: string | null;
  source_root: string;
  runner_kind: string;
  agent_backend: string;
  instruction_sources: Array<{
    type: string;
    origin: string;
    label: string;
  }>;
  mcp_source_type: string;
  mcp_source_origin?: string | null;
  capabilities: {
    language: string | null;
    test_runner: string | null;
    supported: boolean;
    support_reason: string;
  };
  precheck: {
    total_rules: number;
    benchmarkable_rules: number;
    excluded_rules: number;
    covered_rules: number;
    missing_rules: number;
    ambiguous_rules: number;
    requires_confirmation: boolean;
    thresholds: {
      missing_count: number;
      missing_percent: number;
    };
    rules: BenchmarkRuleCoverageItem[];
  };
}

export interface CreateStudioRunResponse {
  run_id: string;
  status: string;
}

export interface StudioRunSummary {
  run_id: string;
  status: string;
  source_root?: string;
  runnable_task_count?: number;
  inputs?: {
    profile_id?: string | null;
    profile_name?: string | null;
    runner_kind?: string;
    agent_backend?: string;
    adapter_command?: string | null;
    instruction_sources?: Array<{
      type: string;
      origin: string;
      label: string;
    }>;
    mcp_source_type?: string;
    mcp_source_origin?: string | null;
  };
  alignment?: {
    issue_count: number;
    by_status: Record<string, number>;
  };
  capabilities?: {
    language: string | null;
    test_runner: string | null;
    supported: boolean;
    support_reason: string;
  };
  precheck?: BenchmarkPrecheckResponse['precheck'];
  md_summary?: {
    rule_count: number;
    adherence_rate: number;
    pass_count: number;
    partial_count: number;
    fail_count: number;
  };
  mcp_summary?: {
    rule_count: number;
    adherence_rate: number;
    pass_count: number;
    partial_count: number;
    fail_count: number;
  };
  rule_comparisons?: Array<{
    rule_id: string;
    category: string;
    md_verdict: 'pass' | 'partial' | 'fail' | 'not_applicable';
    mcp_verdict: 'pass' | 'partial' | 'fail' | 'not_applicable';
    delta: number;
    md_result: {
      verdict: string;
      ratio: number;
      evidence: string[];
    };
    mcp_result: {
      verdict: string;
      ratio: number;
      evidence: string[];
    };
  }>;
  category_comparisons?: Array<{
    category: string;
    md_rate: number;
    mcp_rate: number;
    delta: number;
    rule_count: number;
  }>;
  violations?: {
    md_only: string[];
    mcp_only: string[];
    shared: string[];
  };
  benchmark_runtime_ms?: number;
  benchmark?: {
    average_score: number;
    task_success_rate: number;
  };
  runs?: Array<{
    run_id: string;
    task_id: string;
    condition: string;
    normalized_score: number;
    task_success: boolean;
    hard_violation_count: number;
  }>;
}

export interface StudioRunDetails {
  run_id: string;
  status: string;
  error?: string | null;
  summary?: StudioRunSummary;
}

export interface AgentBackendStatus {
  key: 'codex' | 'claude' | 'custom';
  label: string;
  description: string;
  available: boolean;
  authenticated: boolean;
  default_for_external: boolean;
  command_preview: string | null;
  auth_message: string;
  requires_custom_command: boolean;
}

export interface AgentCatalogResponse {
  default_external_agent: 'codex' | 'claude' | 'custom';
  agents: AgentBackendStatus[];
}

export interface StudioEventEnvelope {
  timestamp?: string;
  run_id?: string;
  event_type: string;
  payload?: Record<string, unknown>;
}
