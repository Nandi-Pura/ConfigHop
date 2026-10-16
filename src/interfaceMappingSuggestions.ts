import type { HardwarePort, HardwareProfileDetail, InterfaceMapping, MigrationPreview, PhysicalInterfaceView } from './api/types'
import { canSelectPortForAnalysis, rowFindings } from './scopedRenderingUI'

export const suggestionGroups = ['RECOMMENDED', 'OTHER AVAILABLE', 'NOT QUALIFIED / UNAVAILABLE'] as const
type SuggestionGroup = typeof suggestionGroups[number]
const naturalOrder = new Intl.Collator('en', { numeric: true })
const sameSet = (left: string[], right: string[]) => left.length === right.length && left.every(value => right.includes(value))

export function hardwareFit(source?: HardwarePort, target?: HardwarePort) {
  const sharedMedia = source?.media_capabilities.filter(value => target?.media_capabilities.includes(value)) ?? []
  const sharedRates = source?.speed_capabilities.filter(value => target?.speed_capabilities.includes(value)) ?? []
  if (!source?.media_capabilities.length || !target?.media_capabilities.length || !source.speed_capabilities.length || !target.speed_capabilities.length) {
    return { status: 'UNKNOWN', detail: 'Unknown — incomplete hardware metadata', sharedMedia, sharedRates } as const
  }
  if (!sharedMedia.length || !sharedRates.length) {
    return { status: 'MISMATCH', detail: !sharedMedia.length ? 'Mismatch — no documented media overlap' : 'Mismatch — no documented rate overlap', sharedMedia, sharedRates } as const
  }
  return { status: 'COMPATIBLE', detail: 'Compatible capability', sharedMedia, sharedRates } as const
}

export const portCapabilityLabel = (port?: HardwarePort) => port
  ? `${port.media_capabilities.map(media => ({ SFP_PLUS: 'SFP+', QSFP_PLUS: 'QSFP+' })[media] ?? media).join('/') || 'Media unknown'} | ${port.speed_capabilities.join('/') || 'Rates unknown'}`
  : 'Hardware capability unknown'

function includesMapping(source: string, target: string, preview: MigrationPreview | null) {
  if (!preview) return false
  const submitted = preview.mappings?.find(item => item.source_interface === source)
  if (submitted) return submitted.target_interface === target
  const assignment = preview.hardware_assessment?.effective_assignments.find(item => item.source_interface === source)
  return assignment ? assignment.target_interface === target : source === target
}

export function backendMappingStatus(source: string, target: string, preview: MigrationPreview | null) {
  if (!preview || !includesMapping(source, target, preview)) return 'Pending backend validation'
  const assignment = preview.hardware_assessment?.effective_assignments.find(item => item.source_interface === source && item.target_interface === target)
  const findings = rowFindings(source, target, preview)
  const statuses = [preview.overall_status ?? preview.status, assignment?.status]
  if (statuses.includes('BLOCKED') || findings.some(item => item.severity === 'ERROR')) return 'BLOCKED'
  if (statuses.includes('REVIEW_REQUIRED') || findings.some(item => item.severity === 'WARNING')) return 'REVIEW_REQUIRED'
  return preview.overall_status ?? preview.status
}

export function rankTargetInterfaces({ source, sourceProfile, targetProfile, mappings, sources, preview }: {
  source: PhysicalInterfaceView
  sourceProfile: HardwareProfileDetail | null
  targetProfile: HardwareProfileDetail | null
  mappings: InterfaceMapping[]
  sources: PhysicalInterfaceView[]
  preview: MigrationPreview | null
}) {
  const sourcePort = sourceProfile?.port_details.find(port => port.name === source.name)
  const assigned = new Set(mappings.filter(item => item.source_interface !== source.name).map(item => item.target_interface))
  for (const other of sources) {
    if (other.name !== source.name && !mappings.some(item => item.source_interface === other.name)) assigned.add(other.name)
  }
  return (targetProfile?.port_details ?? []).map(port => {
    const fit = hardwareFit(sourcePort, port)
    const selectable = canSelectPortForAnalysis(port, targetProfile?.target_render_support)
    const assignment = preview?.hardware_assessment?.effective_assignments.find(item => item.source_interface === source.name && item.target_interface === port.name)
    const findings = includesMapping(source.name, port.name, preview) ? rowFindings(source.name, port.name, preview) : []
    const blocked = assignment?.status === 'BLOCKED' || findings.some(item => item.severity === 'ERROR')
    const unqualified = !selectable || port.candidate_support === 'BLOCKED' || port.availability === 'BREAKOUT_CHILD' || targetProfile?.target_render_support === 'ANALYSIS_ONLY' || blocked
    const group: SuggestionGroup = unqualified ? 'NOT QUALIFIED / UNAVAILABLE' : fit.status === 'COMPATIBLE' && !assigned.has(port.name) ? 'RECOMMENDED' : 'OTHER AVAILABLE'
    const score = [
      suggestionGroups.indexOf(group),
      fit.status === 'COMPATIBLE' ? 0 : fit.status === 'UNKNOWN' ? 1 : 2,
      sourcePort && sameSet(sourcePort.media_capabilities, port.media_capabilities) ? 0 : 1,
      sourcePort && sameSet(sourcePort.speed_capabilities, port.speed_capabilities) ? 0 : 1,
      port.availability === 'NATIVE' ? 0 : 1,
      assigned.has(port.name) ? 1 : 0,
      assignment?.status === 'REVIEW_REQUIRED' || findings.some(item => item.severity === 'WARNING') ? 1 : 0,
      port.required_condition === 'NONE' ? 0 : 1,
    ]
    return { port, fit, group, selectable, assigned: assigned.has(port.name), score }
  }).sort((left, right) => {
    for (let index = 0; index < left.score.length; index++) {
      const difference = left.score[index] - right.score[index]
      if (difference) return difference
    }
    return naturalOrder.compare(left.port.name, right.port.name) || left.port.name.localeCompare(right.port.name, 'en')
  }).map(({ score: _score, ...suggestion }) => suggestion)
}
