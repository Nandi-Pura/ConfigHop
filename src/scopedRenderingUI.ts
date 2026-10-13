import type { CompatibilityFinding, HardwarePort, HardwareProfileSummary, MigrationFinding, MigrationPreview, PhysicalInterfaceView, TargetRenderSupport } from './api/types'

export type RenderScope = 'SAFE_PATH' | 'REVIEW' | 'BLOCKED' | 'PENDING' | 'FULL' | 'ANALYSIS_ONLY'
export type RowFinding = CompatibilityFinding | MigrationFinding

const labels: Record<RenderScope, string> = {
  SAFE_PATH: 'SAFE PATH', REVIEW: 'REVIEW', BLOCKED: 'BLOCKED', PENDING: 'PENDING', FULL: 'FULL', ANALYSIS_ONLY: 'ANALYSIS ONLY',
}

const findingLabels: Record<string, string> = {
  TARGET_AUTO_ONLY_LINK_SERIALIZATION_UNVERIFIED: 'Link Serialization Unverified',
  TARGET_AUTO_ONLY_LINK_SETTING_NOT_APPLICABLE: 'Target Link Setting Not Applicable',
  TARGET_INTERFACE_GROUP_RENDERING_UNQUALIFIED: 'Target Rendering Not Qualified',
  SCOPED_TARGET_ACTIVE_INTERFACE_MAPPING_REQUIRED: 'Explicit Mapping Required',
  SCOPED_TARGET_DEPENDENCY_COVERAGE_INSUFFICIENT: 'Dependency Coverage Insufficient',
  TARGET_MEDIA_INCOMPATIBLE: 'Physical Media Incompatible',
  UNMODELED_INTERFACE_REFERENCE: 'Unmodeled Interface Reference',
}

export const scopeLabel = (scope: RenderScope) => labels[scope]
export const targetRenderLabel = (support?: TargetRenderSupport) => support === 'SCOPED' ? 'Hardware Verified · Scoped Rendering' : support === 'ANALYSIS_ONLY' ? 'Hardware Verified · Analysis Only' : support === 'SUPPORTED' ? 'Hardware Verified · Renderer Supported' : 'Verified Profile'
export const shouldShowNativeSpeedChoice = (port?: HardwarePort) => port?.required_condition === 'MANUAL_NATIVE_PORT_SPEED'
export const canSelectPortForAnalysis = (port: HardwarePort, support?: TargetRenderSupport) => port.candidate_support !== 'BLOCKED' || support === 'SCOPED' && port.required_condition === 'TARGET_LINK_SERIALIZATION_UNVERIFIED'
export const sourceLinkFact = (value: string | null, explicit: boolean) => explicit ? `${value ?? '(empty)'} · explicit` : 'Default / absent'
export const targetCapability = (condition?: HardwarePort['required_condition']) => condition === 'AUTO_ONLY_LINK_FIELDS_ABSENT' ? 'Auto-negotiation only' : condition === 'TARGET_LINK_SERIALIZATION_UNVERIFIED' ? 'Rendering qualification pending' : condition === 'MANUAL_NATIVE_PORT_SPEED' ? 'Explicit native speed required' : condition === 'BREAKOUT_MODE' ? 'Breakout mode required' : 'Profile supported'

export function findingLabel(finding: RowFinding, source?: PhysicalInterfaceView): string {
  if (finding.code === 'TARGET_AUTO_ONLY_LINK_SERIALIZATION_UNVERIFIED' && source) {
    const values = [source.link_speed_explicit ? source.link_speed : null, source.link_duplex_explicit ? source.link_duplex : null]
    return values.some((value) => value && value.toLowerCase() !== 'auto') ? 'Manual Link Setting Requires Resolution' : 'Explicit Auto Serialization Unverified'
  }
  return findingLabels[finding.code] ?? finding.code.replaceAll('_', ' ').toLowerCase().replace(/^./, (first) => first.toUpperCase())
}

export function linkFindingExplanation(finding: RowFinding | undefined, source: PhysicalInterfaceView): string | null {
  if (finding?.code !== 'TARGET_AUTO_ONLY_LINK_SERIALIZATION_UNVERIFIED') return null
  if (source.link_speed_explicit && source.link_speed && source.link_speed.toLowerCase() !== 'auto') return 'Manual source speed cannot be safely migrated to this auto-negotiation only target.'
  if (source.link_duplex_explicit && source.link_duplex && source.link_duplex.toLowerCase() !== 'auto') return 'Manual source duplex cannot be safely migrated to this auto-negotiation only target.'
  return 'This target port is auto-negotiation only, but the source contains an explicit link setting. ConfigHop will not infer whether the target XML should preserve, remove, or rewrite that node.'
}

export function rowFindings(source: string, target: string, preview: MigrationPreview | null): RowFinding[] {
  if (!preview) return []
  const assignment = preview.hardware_assessment?.effective_assignments.find((item) => item.source_interface === source)
  const impact = preview.impacts.find((item) => item.source_interface === source)
  const all = [...(assignment?.findings ?? []), ...(impact?.findings ?? []),
    ...(preview.hardware_assessment?.findings ?? []), ...preview.findings]
  const seen = new Set<string>()
  return all.filter((finding) => {
    if (finding.source_interface !== source || finding.target_interface && finding.target_interface !== target) return false
    const key = `${finding.code}|${finding.source_interface}|${finding.target_interface}|${finding.message}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  }).sort((a, b) => ({ ERROR: 0, WARNING: 1, INFO: 2 })[a.severity] - ({ ERROR: 0, WARNING: 1, INFO: 2 })[b.severity])
}

export function rowRenderScope(profile: HardwareProfileSummary | null, port: HardwarePort | undefined, preview: MigrationPreview | null, findings: RowFinding[]): RenderScope {
  if (profile?.target_render_support === 'ANALYSIS_ONLY') return 'ANALYSIS_ONLY'
  if (!preview) return 'PENDING'
  if (profile?.target_render_support === 'SUPPORTED') return findings.some((item) => item.severity === 'ERROR') ? 'BLOCKED' : findings.some((item) => item.severity === 'WARNING') ? 'REVIEW' : 'FULL'
  if (profile?.target_render_support !== 'SCOPED') return 'PENDING'
  if (findings.some((item) => item.severity === 'ERROR')) return 'BLOCKED'
  if (findings.some((item) => item.severity === 'WARNING')) return 'REVIEW'
  if (port?.required_condition === 'TARGET_LINK_SERIALIZATION_UNVERIFIED') return 'BLOCKED'
  return port?.required_condition === 'AUTO_ONLY_LINK_FIELDS_ABSENT' ? 'SAFE_PATH' : 'PENDING'
}

export function scopedReadiness(profile: HardwareProfileSummary | null, preview: MigrationPreview | null, blockedRows: number, activeRows: number) {
  if (profile?.target_render_support !== 'SCOPED') return null
  const status = preview?.overall_status ?? preview?.status
  if (!status) return { status: 'PENDING', detail: 'Awaiting current backend preview' }
  if (status === 'BLOCKED') return { status, detail: blockedRows ? `${blockedRows} interface${blockedRows === 1 ? '' : 's'} blocked · resolve mapping findings` : 'Backend findings block candidate generation' }
  if (status === 'REVIEW_REQUIRED') return { status, detail: 'Engineer review required' }
  return { status, detail: `${activeRows} interfaces qualified · 0 blocked` }
}
