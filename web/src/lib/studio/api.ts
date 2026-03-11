import type {
  AgentCatalogResponse,
  BenchmarkProfilesResponse,
  CreateStudioRunInput,
  DemoProfileResponse,
  CreateStudioRunResponse,
  StudioRunDetails,
} from './types';

function getBaseUrl(): string {
  const baseUrl = import.meta.env.VITE_STUDIO_API_BASE_URL;
  return typeof baseUrl === 'string' && baseUrl.length > 0 ? baseUrl : '';
}

export async function createStudioRun(
  input: CreateStudioRunInput
): Promise<CreateStudioRunResponse> {
  const formData = new FormData();
  if (input.profileId) {
    formData.set('profile_id', input.profileId);
  }
  if (input.repoPath.trim()) {
    formData.set('repo_path', input.repoPath.trim());
  }
  if (input.repoArchive) {
    formData.set('repo_archive', input.repoArchive);
  }
  input.instructionFiles.forEach((file) => {
    formData.append('instruction_files', file);
  });
  formData.set('mcp_json', input.mcpJson);
  if (input.mcpSourceType) {
    formData.set('mcp_source_type', input.mcpSourceType);
  }
  if (input.mcpSourcePath?.trim()) {
    formData.set('mcp_source_path', input.mcpSourcePath.trim());
  }
  if (input.mcpSourceCommand?.trim()) {
    formData.set('mcp_source_command', input.mcpSourceCommand.trim());
  }
  formData.set('runner_kind', input.runnerKind);
  formData.set('agent_backend', input.agentBackend);
  if (input.adapterCommand.trim()) {
    formData.set('adapter_command', input.adapterCommand.trim());
  }
  formData.set('max_workers', String(input.maxWorkers));

  const response = await fetch(`${getBaseUrl()}/api/runs`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`Run creation failed with status ${response.status}.`);
  }
  return response.json();
}

export async function createStudioProfileRun(profileId: string): Promise<CreateStudioRunResponse> {
  const response = await fetch(`${getBaseUrl()}/api/profiles/${profileId}/run`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`Profile run failed with status ${response.status}.`);
  }
  return response.json();
}

export async function getStudioRun(runId: string): Promise<StudioRunDetails> {
  const response = await fetch(`${getBaseUrl()}/api/runs/${runId}`);
  if (!response.ok) {
    throw new Error(`Run lookup failed with status ${response.status}.`);
  }
  return response.json();
}

export async function getAgentCatalog(): Promise<AgentCatalogResponse> {
  const response = await fetch(`${getBaseUrl()}/api/agents`);
  if (!response.ok) {
    throw new Error(`Agent lookup failed with status ${response.status}.`);
  }
  return response.json();
}

export async function getAnthropicDemoProfile(): Promise<DemoProfileResponse> {
  const response = await fetch(`${getBaseUrl()}/api/demo/anthropic`);
  if (!response.ok) {
    throw new Error(`Demo lookup failed with status ${response.status}.`);
  }
  return response.json();
}

export async function getBenchmarkProfiles(): Promise<BenchmarkProfilesResponse> {
  const response = await fetch(`${getBaseUrl()}/api/profiles`);
  if (!response.ok) {
    throw new Error(`Profiles lookup failed with status ${response.status}.`);
  }
  return response.json();
}

export function buildStudioEventsUrl(runId: string): string {
  return `${getBaseUrl()}/api/runs/${runId}/events`;
}

export function buildStudioExportUrl(runId: string): string {
  return `${getBaseUrl()}/api/runs/${runId}/export`;
}
