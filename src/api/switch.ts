import { request } from './client'

export type SwitchStatement = { line: number; source: string; scope: string; feature: string; values: string[]; status: string; render_supported: boolean; dependencies: string[] }
export type SwitchSettings = { revision: number; target_os: 'AOS_CX'; target_version: string; capability_id: 'hpe-aruba-jl663a' | null; mappings: Record<string, number> }
export type SwitchProject = { project_id: string; revision: number; inventory: { source_version: string; interfaces: { name: string; kind: 'Physical' | 'LAG' | 'SVI' | 'Loopback' | 'Other'; line: number }[]; statements: SwitchStatement[] }; settings: SwitchSettings | null }
export type SwitchPreview = { project_id: string; revision: number; candidate: { text: string; sha256: string; status: string; findings: { severity: string; code: string; message: string; scope: string; line: number | null }[]; report: SwitchStatement[]; coverage: Record<string, number>; resolved_interfaces: Record<string, string>; deployment_verified: boolean } }
export const switchApi = {
  inspect: (text: string, source_version: string, signal?: AbortSignal) => request<SwitchProject>('/switch-projects', { method: 'POST', body: JSON.stringify({ text, source_version, source_os: 'IOS_XE' }), signal }),
  get: (id: string, signal?: AbortSignal) => request<SwitchProject>(`/switch-projects/${encodeURIComponent(id)}`, { signal }),
  delete: (id: string) => request<void>(`/switch-projects/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  preview: (id: string, settings: SwitchSettings, signal?: AbortSignal) => request<SwitchPreview>(`/switch-projects/${encodeURIComponent(id)}/preview`, { method: 'PUT', body: JSON.stringify(settings), signal }),
  export: (preview: SwitchPreview, acknowledge_review: boolean, signal?: AbortSignal) => request<{ text: string; filename: string; sha256: string; revision: number }>(`/switch-projects/${encodeURIComponent(preview.project_id)}/export`, { method: 'POST', body: JSON.stringify({ revision: preview.revision, sha256: preview.candidate.sha256, acknowledge_review }), signal }),
}
