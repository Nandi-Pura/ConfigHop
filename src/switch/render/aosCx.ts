import { renderVlan } from '../config/aruba/vlan.ts'
import { isClaimVerified, isVerified } from '../evidence.ts'
import type { SourceReference } from '../intent/types.ts'
import type { TargetAosCxIntent, TargetFeatureStatus } from '../mapping/types.ts'
import type { SwitchPlatformSelection } from '../types.ts'

export interface RenderFinding {
  code: 'RENDER_BLOCKED' | 'RENDER_SKIPPED'
  severity: 'error' | 'warning'
  message: string
  sourceRefs: SourceReference[]
}

export interface RenderedConfig {
  kind: 'vlan' | 'interface'
  id: string
  sourceRefs: SourceReference[]
}

export interface AosCxRenderResult {
  configuration: string
  findings: RenderFinding[]
  emitted: RenderedConfig[]
  targetPlatform: TargetAosCxIntent['targetPlatform']
  status: TargetFeatureStatus
  blocked: boolean
}

const cloneRefs = (refs: SourceReference[]) => refs.map((ref) => ({ ...ref }))
const blocked = (findings: RenderFinding[], message: string, sourceRefs: SourceReference[] = []) =>
  findings.push({ code: 'RENDER_BLOCKED', severity: 'warning', message, sourceRefs: cloneRefs(sourceRefs) })
const skipped = (findings: RenderFinding[], message: string, sourceRefs: SourceReference[] = []) =>
  findings.push({ code: 'RENDER_SKIPPED', severity: 'warning', message, sourceRefs: cloneRefs(sourceRefs) })

/** Render only status-READY VLANs and basic Layer-2 interfaces with explicit target support. */
export function renderAosCx(intent: TargetAosCxIntent, selection?: SwitchPlatformSelection): AosCxRenderResult {
  const findings: RenderFinding[] = []
  const emitted: RenderedConfig[] = []
  const platform = intent.targetPlatform
  if (!selection || platform.hardwareId !== selection.hardware.id || platform.osId !== selection.os.id || platform.compatibilityStatus !== 'READY' || selection.compatibility.status !== 'READY' || selection.os.lifecycleStatus !== 'ACTIVE' || selection.hardware.hardwareRole === 'management-module' || selection.hardware.hardwareRole === 'line-card' || !isVerified(selection.compatibility.evidenceIds) || !isClaimVerified(selection.compatibility.evidenceIds, 'os-compatibility', selection.os.train)) {
    blocked(findings, 'Rendering requires matching standalone target hardware, an active AOS-CX release, and explicit READY compatibility evidence.')
    return { configuration: '', findings, emitted, targetPlatform: { ...platform }, status: 'REVIEW_REQUIRED', blocked: true }
  }

  const lines: string[] = []
  const renderVlanItem = selection.hardware.capabilities.vlan === 'SUPPORTED'
  for (const vlan of [...intent.vlans].sort((a, b) => a.vlanId - b.vlanId)) {
    if (vlan.status !== 'READY' || !renderVlanItem) {
      blocked(findings, `VLAN ${vlan.vlanId} was not rendered: mapping status is ${vlan.status} or target VLAN capability is not SUPPORTED.`, vlan.sourceRefs)
      continue
    }
    if (!Number.isInteger(vlan.vlanId) || vlan.vlanId < 1 || vlan.vlanId > 4094) {
      blocked(findings, `VLAN ${vlan.vlanId} was not rendered: VLAN ID must be 1-4094.`, vlan.sourceRefs)
      continue
    }
    lines.push(renderVlan(vlan.vlanId, vlan.name))
    emitted.push({ kind: 'vlan', id: String(vlan.vlanId), sourceRefs: cloneRefs(vlan.sourceRefs) })
    if (vlan.description || vlan.adminState) skipped(findings, `VLAN ${vlan.vlanId} description/admin state has no verified renderer contract.`, vlan.sourceRefs)
  }

  for (const iface of [...intent.interfaces].sort((a, b) => a.targetInterfaceId.localeCompare(b.targetInterfaceId))) {
    if (iface.status !== 'READY' || iface.adminState === 'unknown' || !selection.hardware.ports.some((port) => port.id === iface.targetInterfaceId)) {
      blocked(findings, `Interface ${iface.targetInterfaceId} was not rendered: status, administrative state, or target port is not verified.`, iface.sourceRefs)
      continue
    }
    const supported = iface.role === 'access'
      ? selection.hardware.capabilities.accessVlan === 'SUPPORTED'
      : iface.role === 'trunk' && selection.hardware.capabilities.trunk === 'SUPPORTED' && (!iface.trunkNativeVlan || selection.hardware.capabilities.nativeVlan === 'SUPPORTED')
    if (!supported || (iface.role === 'access' && iface.accessVlan == null)) {
      blocked(findings, `Interface ${iface.targetInterfaceId} was not rendered: role or required VLAN capability is not verified.`, iface.sourceRefs)
      continue
    }
    const interfaceLines = [`interface ${iface.targetInterfaceId}`, `    ${iface.adminState === 'up' ? 'no shutdown' : 'shutdown'}`]
    if (iface.role === 'access') interfaceLines.push(`    vlan access ${iface.accessVlan}`)
    if (iface.role === 'trunk') {
      if (iface.trunkNativeVlan != null) interfaceLines.push(`    vlan trunk native ${iface.trunkNativeVlan}`)
      if (iface.trunkAllowedVlans?.length) interfaceLines.push(`    vlan trunk allowed ${iface.trunkAllowedVlans.map((range) => range.start === range.end ? range.start : `${range.start}-${range.end}`).join(',')}`)
    }
    lines.push(interfaceLines.join('\n'))
    emitted.push({ kind: 'interface', id: iface.targetInterfaceId, sourceRefs: cloneRefs(iface.sourceRefs) })
    if (iface.description || iface.voiceVlan != null || iface.edgePort || iface.lagId || iface.portAccess) skipped(findings, `Interface ${iface.targetInterfaceId} contains non-rendered semantics.`, iface.sourceRefs)
  }

  for (const [label, items] of Object.entries({ system: intent.system ? [intent.system] : [], lags: intent.lags, svis: intent.svis, acls: intent.acls, vrfs: intent.vrfs, stp: intent.stp ? [intent.stp] : [], vsf: intent.vsf ? [intent.vsf] : [] })) {
    for (const item of items) skipped(findings, `${label} is outside the AOS-CX renderer foundation.`, item.sourceRefs)
  }
  if (intent.nac) skipped(findings, 'nac is outside the AOS-CX renderer foundation.', [...intent.nac.radiusServers, ...intent.nac.radiusGroups, intent.nac.aaa, intent.nac.global].flatMap((item) => item.sourceRefs))
  return { configuration: lines.join('\n\n'), findings, emitted, targetPlatform: { ...platform }, status: findings.some((finding) => finding.code === 'RENDER_BLOCKED') ? 'REVIEW_REQUIRED' : 'READY', blocked: false }
}
