import type { CandidateMetadata, Capabilities, CompatibilityAssessment, DeploymentPackage, EvidenceRecord, HardwareProfileDetail, HardwareProfileSummary, InterfaceMapping, InventoryView, MigrationPreview, ProjectState, SourceConnectionInput, SourceConnectionTest, SourceUpload, TargetBaseline, TargetCommit, TargetCommitApproval, TargetCommitReconcile, TargetPreflight, TargetReconcile, TargetRecovery, TargetStage } from './types'

const LOCAL_API_HOST = typeof window !== 'undefined' && window.location.hostname === 'localhost' ? 'localhost' : '127.0.0.1'
export const API_BASE = (import.meta.env.VITE_CONFIGHOP_API_URL || `http://${LOCAL_API_HOST}:8000/api/v1`).replace(/\/$/, '')
export const MAX_TEXT_PREVIEW_BYTES = 10 * 1024 * 1024

export class ApiClientError extends Error {
  constructor(public code: string, message: string, public status: number) { super(message) }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { ...(typeof File !== 'undefined' && init.body instanceof File ? { 'Content-Type': 'application/xml' } : init.body ? { 'Content-Type': 'application/json' } : {}),
        ...(init.method && init.method !== 'GET' ? { 'X-ConfigHop-Client': 'web' } : {}), ...init.headers },
      cache: 'no-store',
      credentials: 'include',
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiClientError('API_UNAVAILABLE', `ConfigHop service is unavailable at ${API_BASE}.`, 0)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: { code?: string; message?: string } } | null
    throw new ApiClientError(body?.error?.code || 'INTERNAL_ERROR', body?.error?.message || 'The request could not be completed.', response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function xml(path: string, signal?: AbortSignal): Promise<Blob> {
  let response: Response
  try { response = await fetch(`${API_BASE}${path}`, { cache: 'no-store', credentials: 'include', signal }) }
  catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiClientError('API_UNAVAILABLE', `ConfigHop service is unavailable at ${API_BASE}.`, 0)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: { code?: string; message?: string } } | null
    throw new ApiClientError(body?.error?.code || 'INTERNAL_ERROR', body?.error?.message || 'XML is not available.', response.status)
  }
  return response.blob()
}

export const api = {
  getCapabilities: (signal?: AbortSignal) => request<Capabilities>('/capabilities', { signal }),
  createProject: (signal?: AbortSignal) => request<ProjectState>('/projects', { method: 'POST', signal }),
  getProject: (id: string, signal?: AbortSignal) => request<ProjectState>(`/projects/${id}`, { signal }),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
  uploadSource: (id: string, file: File, signal?: AbortSignal) => request<SourceUpload>(`/projects/${id}/source`, {
    method: 'PUT', body: file, signal, headers: { 'X-ConfigHop-Filename': file.name },
  }),
  testSourceConnection: (id: string, input: SourceConnectionInput, signal?: AbortSignal) => request<SourceConnectionTest>(`/projects/${id}/source/connection/test`, {
    method: 'POST', body: JSON.stringify(input), signal,
  }),
  collectSource: (id: string, input: SourceConnectionInput, signal?: AbortSignal) => request<SourceUpload>(`/projects/${id}/source/collect`, {
    method: 'POST', body: JSON.stringify(input), signal,
  }),
  testTargetConnection: (id: string, input: SourceConnectionInput, signal?: AbortSignal) => request<SourceConnectionTest>(`/projects/${id}/target/connection/test`, {
    method: 'POST', body: JSON.stringify(input), signal,
  }),
  collectTargetBaseline: (id: string, input: SourceConnectionInput & { expected_serial: string; expected_model: string }, signal?: AbortSignal) => request<TargetBaseline>(`/projects/${id}/target/baseline/collect`, {
    method: 'POST', body: JSON.stringify(input), signal,
  }),
  getTargetBaseline: (id: string, signal?: AbortSignal) => request<TargetBaseline>(`/projects/${id}/target/baseline`, { signal }),
  getDeploymentPackage: (id: string, signal?: AbortSignal) => request<DeploymentPackage>(`/projects/${id}/deployment-package`, { signal }),
  buildTargetPackage: (id: string, signal?: AbortSignal) => request<DeploymentPackage>(`/projects/${id}/target/package/build`, {
    method: 'POST', signal,
  }),
  reviewTargetPackage: (id: string, confirmedTargetHostname: string, acceptedFindingCodes: string[], signal?: AbortSignal) => request<DeploymentPackage>(`/projects/${id}/target/package/review`, {
    method: 'POST', body: JSON.stringify({ confirmed_target_hostname: confirmedTargetHostname, accepted_finding_codes: acceptedFindingCodes }), signal,
  }),
  checkTargetPreflight: (id: string, input: SourceConnectionInput & { expected_serial: string; expected_model: string; recovery_path_confirmed: boolean }, signal?: AbortSignal) => request<TargetPreflight>(`/projects/${id}/target/preflight/check`, {
    method: 'POST', body: JSON.stringify(input), signal,
  }),
  stageTargetPackage: (id: string, input: SourceConnectionInput & { expected_serial: string; expected_model: string; confirmed_target_hostname: string }, signal?: AbortSignal) => request<TargetStage>(`/projects/${id}/target/stage`, {
    method: 'POST', body: JSON.stringify(input), signal,
  }),
  reconcileTargetStage: (id: string, input: SourceConnectionInput & { expected_serial: string; expected_model: string; confirmed_target_hostname: string }, signal?: AbortSignal) => request<TargetReconcile>(`/projects/${id}/target/stage/reconcile`, {
    method: 'POST', body: JSON.stringify(input), signal,
  }),
  issueTargetCommitApproval: (id: string, input: { expected_serial: string; expected_model: string; confirmed_target_hostname: string }, signal?: AbortSignal) => request<TargetCommitApproval>(`/projects/${id}/target/commit/approval`, {
    method: 'POST', body: JSON.stringify(input), signal,
  }),
  commitTargetPackage: (id: string, input: SourceConnectionInput & { expected_serial: string; expected_model: string; confirmed_target_hostname: string; approval_token: string }, signal?: AbortSignal) => request<TargetCommit>(`/projects/${id}/target/commit`, {
    method: 'POST', body: JSON.stringify(input), signal,
  }),
  reconcileTargetCommit: (id: string, input: SourceConnectionInput & { expected_serial: string; expected_model: string; confirmed_target_hostname: string }, signal?: AbortSignal) => request<TargetCommitReconcile>(`/projects/${id}/target/commit/reconcile`, {
    method: 'POST', body: JSON.stringify(input), signal,
  }),
  recoverTargetPackage: (id: string, input: SourceConnectionInput & { expected_serial: string; expected_model: string; confirmed_target_hostname: string; recovery_confirmation: string }, signal?: AbortSignal) => request<TargetRecovery>(`/projects/${id}/target/recovery`, {
    method: 'POST', body: JSON.stringify(input), signal,
  }),
  getSource: (id: string, signal?: AbortSignal) => xml(`/projects/${id}/source`, signal),
  getInventory: (id: string, signal?: AbortSignal) => request<InventoryView>(`/projects/${id}/inventory`, { signal }),
  listProfiles: (signal?: AbortSignal) => request<HardwareProfileSummary[]>('/hardware-profiles', { signal }),
  getProfile: (id: string, signal?: AbortSignal) => request<HardwareProfileDetail>(`/hardware-profiles/${id}`, { signal }),
  listEvidence: (signal?: AbortSignal) => request<EvidenceRecord[]>('/evidence', { signal }),
  setSourceProfile: (id: string, profileId: string, train: string, signal?: AbortSignal) => request<ProjectState>(`/projects/${id}/source-profile`, {
    method: 'PUT', body: JSON.stringify({ profile_id: profileId || null, panos_train: train || null }), signal,
  }),
  setProfile: (id: string, profileId: string, train = '', signal?: AbortSignal) => request<ProjectState>(`/projects/${id}/target-profile`, {
    method: 'PUT', body: JSON.stringify({ profile_id: profileId || null, panos_train: train || null }), signal,
  }),
  compatibility: (id: string, mappings: InterfaceMapping[], signal?: AbortSignal) => request<CompatibilityAssessment>(`/projects/${id}/compatibility`, {
    method: 'POST', body: JSON.stringify({ mappings }), signal,
  }),
  preview: (id: string, mappings: InterfaceMapping[], signal?: AbortSignal) => request<MigrationPreview>(`/projects/${id}/preview`, {
    method: 'POST', body: JSON.stringify({ mappings }), signal,
  }),
  getPreview: (id: string, signal?: AbortSignal) => request<MigrationPreview>(`/projects/${id}/preview`, { signal }),
  candidate: (id: string, mappings: InterfaceMapping[], allowReview: boolean, signal?: AbortSignal) => request<CandidateMetadata>(`/projects/${id}/candidate`, {
    method: 'POST', body: JSON.stringify({ mappings, allow_review: allowReview }), signal,
  }),
  getCandidate: (id: string, signal?: AbortSignal) => request<CandidateMetadata>(`/projects/${id}/candidate`, { signal }),
  downloadCandidate: (id: string, signal?: AbortSignal) => xml(`/projects/${id}/candidate/download`, signal),
}
