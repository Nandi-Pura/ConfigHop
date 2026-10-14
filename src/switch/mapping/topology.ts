// Topology mapping for STP and VSF (Phase 3.3).

import type { StpConfig, VsfConfig, Finding } from '../intent/types.ts'
import type { SwitchHardware, CompatibilityStatus } from '../types.ts'
import type { TargetStpConfig, TargetVsfConfig, TargetFeatureStatus } from './types.ts'

export function mapStp(
  stp: StpConfig,
  defaultStatus: TargetFeatureStatus,
  findings: Finding[]
): TargetStpConfig {
  let targetMode: 'mstp' | 'rpvst' | 'unknown' = 'unknown'
  let status = defaultStatus

  if (stp.mode === 'rapid-pvst') {
    targetMode = 'rpvst'
  } else if (stp.mode === 'mstp') {
    targetMode = 'mstp'
  } else if (stp.mode === 'pvst') {
    targetMode = 'rpvst'
    status = 'REVIEW_REQUIRED'
    findings.push({
      code: 'MAPPING_SEMANTIC_DIFFERENCE',
      severity: 'warning',
      message: 'Cisco legacy PVST+ maps to AOS-CX RPVST+; verify Spanning-Tree topology and timing parameters.',
      sourceRef: stp.sourceRefs[0],
    })
  }

  return {
    mode: targetMode,
    status,
    sourceRefs: stp.sourceRefs.map(ref => ({ ...ref })),
  }
}

export function mapVsf(
  vsf: VsfConfig,
  targetHw: SwitchHardware,
  findings: Finding[]
): TargetVsfConfig {
  const hwVsf = targetHw.vsf
  let topoStatus: CompatibilityStatus = 'UNKNOWN'

  if (!hwVsf.supported || hwVsf.vsfStatus === 'UNSUPPORTED') {
    topoStatus = 'BLOCKED'
    findings.push({
      code: 'MAPPING_UNSUPPORTED_FEATURE',
      severity: 'error',
      message: `Source configuration uses stacking/VSF, but target hardware ${targetHw.productNumber} does not support VSF.`,
      sourceRef: vsf.sourceRefs[0],
    })
  } else if (hwVsf.vsfStatus === 'UNKNOWN') {
    topoStatus = 'UNKNOWN'
    findings.push({
      code: 'MAPPING_UNKNOWN_COMPATIBILITY',
      severity: 'warning',
      message: `Source configuration uses stacking, but target hardware ${targetHw.productNumber} VSF capability is UNKNOWN pending official documentation verification.`,
      sourceRef: vsf.sourceRefs[0],
    })
  } else {
    if (hwVsf.maxMembers && vsf.members.length > hwVsf.maxMembers) {
      topoStatus = 'BLOCKED'
      findings.push({
        code: 'MAPPING_UNSUPPORTED_FEATURE',
        severity: 'error',
        message: `Source stack size (${vsf.members.length}) exceeds target hardware ${targetHw.productNumber} maximum VSF member limit (${hwVsf.maxMembers}).`,
        sourceRef: vsf.sourceRefs[0],
      })
    } else {
      topoStatus = targetHw.compatibilityRules[0]?.status === 'READY' ? 'READY' : 'REVIEW_REQUIRED'
    }
  }

  return {
    enabled: vsf.enabled,
    topologySupport: topoStatus,
    notes: hwVsf.notes,
    status: topoStatus === 'READY' ? 'READY' : topoStatus === 'BLOCKED' ? 'UNSUPPORTED' : topoStatus === 'UNKNOWN' ? 'UNKNOWN' : 'REVIEW_REQUIRED',
    sourceRefs: vsf.sourceRefs.map(ref => ({ ...ref })),
  }
}
