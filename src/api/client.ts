import type { CandidateMetadata, CompatibilityAssessment, EvidenceRecord, HardwareProfileDetail, HardwareProfileSummary, InterfaceMapping, InventoryView, MigrationPreview, ProjectState } from './types'

export const API_BASE = (import.meta.env.VITE_CONFIGHOP_API_URL || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '')
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
  try { response = await fetch(`${API_BASE}${path}`, { cache: 'no-store', signal }) }
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
  createProject: (signal?: AbortSignal) => request<ProjectState>('/projects', { method: 'POST', signal }),
  getProject: (id: string, signal?: AbortSignal) => request<ProjectState>(`/projects/${id}`, { signal }),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
  uploadSource: (id: string, file: File, signal?: AbortSignal) => request<{ filename: string; size_bytes: number }>(`/projects/${id}/source`, {
    method: 'PUT', body: file, signal, headers: { 'X-ConfigHop-Filename': file.name },
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
