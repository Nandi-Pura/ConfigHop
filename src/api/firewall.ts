import { request } from './client'

export type FirewallEntity = { name: string; scope: string; line: number | null }
export type FirewallIR = {
  source_vendor: 'fortios' | 'panos'; source_version: string; source_scope: string
  interfaces: (FirewallEntity & { kind: string; address: string | null })[]
  zones: (FirewallEntity & { interfaces: string[] })[]
  addresses: (FirewallEntity & { kind: string; value: string })[]
  address_groups: (FirewallEntity & { members: string[] })[]
  services: (FirewallEntity & { protocol: string; port: string })[]
  service_groups: (FirewallEntity & { members: string[] })[]
  policies: FirewallEntity[]; nat: FirewallEntity[]; routes: FirewallEntity[]; schedules: FirewallEntity[]
  findings: { severity: string; code: string; message: string; entity: string; line: number | null }[]
}
export type FirewallMappings = { interfaces: Record<string, string>; zones: Record<string, string>; addresses: Record<string, string>; services: Record<string, string>; policies: Record<string, string>; nat: Record<string, string> }
export type FirewallProject = { project_id: string; revision: number; inventory: FirewallIR }
export type FirewallPreview = { project_id: string; revision: number; candidate: { status: string; revision: number; sha256: string; syntax: 'xml' | 'cli'; text: string; findings: FirewallIR['findings']; coverage: { category: string; parsed: number; translated: number; rendered: number; validated: number; review_required: number; unsupported: number; blocked: number }[] } }
export const firewallApi = {
  inspect: (text: string, source_os: 'fortios' | 'panos', source_version: string, signal?: AbortSignal) => request<FirewallProject>('/firewall-projects', { method: 'POST', body: JSON.stringify({ text, source_os, source_version }), signal }),
  get: (id: string, signal?: AbortSignal) => request<FirewallProject>(`/firewall-projects/${encodeURIComponent(id)}`, { signal }),
  preview: (id: string, revision: number, target_os: 'fortios' | 'panos', target_version: string, mappings: FirewallMappings, signal?: AbortSignal) => request<FirewallPreview>(`/firewall-projects/${encodeURIComponent(id)}/preview`, { method: 'PUT', body: JSON.stringify({ revision, target_os, target_version, mappings }), signal }),
  export: (preview: FirewallPreview, acknowledge_review: boolean, signal?: AbortSignal) => request<{ filename: string; text: string; sha256: string; revision: number }>(`/firewall-projects/${encodeURIComponent(preview.project_id)}/export`, { method: 'POST', body: JSON.stringify({ revision: preview.revision, sha256: preview.candidate.sha256, acknowledge_review }), signal }),
  delete: (id: string) => request<void>(`/firewall-projects/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}
